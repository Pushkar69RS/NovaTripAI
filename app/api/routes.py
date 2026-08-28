"""The JSON API. Thin: every route is a lookup, one call into a module, a write."""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Iterator
from typing import Annotated, Any

import httpx
import psycopg
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from app.accounts import COOKIE, User, from_cookie
from app.chat.router import (
    Clarification,
    Question,
    answer,
    apply_edit,
    classify,
    resolve,
)
from app.demo import cached_demo
from app.katha.build import WORDS_PER_MIN, DbCatalogue, build, db_retriever
from app.katha.models import Depth, Katha, Scope
from app.llm.client import complete
from app.llm.intake import parse_intake
from app.llm.narrate import narrate_plan, narrate_segment
from app.planner.coldstart import (
    MIN_PLACES,
    ColdStartError,
    ColdStartReport,
    ensure_city,
    ensure_city_layer,
)
from app.planner.distance import DETOUR, haversine
from app.planner.engine import CENTROID_SQL, load, plan_all, scored_pool
from app.planner.models import Alternative, Plan, Reason, TripRequest, Verdict, hub_city
from app.planner.transport import attach
from app.rag.retrieve import TripContext
from app.voice.tts import cache_path, speak

log = logging.getLogger(__name__)


def db() -> Iterator[Any]:
    with psycopg.connect(os.environ["SUPABASE_DB_URL"]) as conn:
        yield conn


Db = Annotated[Any, Depends(db)]


def require_api_user(request: Request, conn: Db) -> User:
    """Every /api route needs the same session cookie the pages use. /health,
    which lives on the app rather than this router, stays open."""
    user = from_cookie(conn, request.cookies.get(COOKIE, ""))
    if user is None:
        raise HTTPException(401, "sign in first")
    return user


Me = Annotated[User, Depends(require_api_user)]

router = APIRouter(prefix="/api", dependencies=[Depends(require_api_user)])


def _json(value: Any) -> Any:
    return (
        value if isinstance(value, dict | list) or value is None else json.loads(value)
    )


# --------------------------------------------------------------------------- #
# trips
# --------------------------------------------------------------------------- #


def hub_alternatives(
    conn: Any, city: str, centre: tuple[float, float] | None
) -> list[Alternative]:
    """One "Plan <hub> instead" per hub within 300 km of the centre; every hub
    when the centre itself is unknown, because a hub plans without the model."""
    counts = dict(
        conn.execute("SELECT city, count(*) FROM poi GROUP BY city").fetchall()
    )
    out = []
    for hub, lat, lng in conn.execute(CENTROID_SQL).fetchall():
        if hub == city:
            continue
        km = None
        if centre is not None:
            km = round(haversine(centre[0], centre[1], float(lat), float(lng)) * DETOUR)
            if km > 300:
                continue
        where = (
            f"about {km} km by road, estimated" if km is not None else "a city we know"
        )
        out.append(
            Alternative(
                title=f"Plan {hub} instead",
                description=f"{hub} is {where}; we know {int(counts.get(hub, 0))} places there.",
                request_override={"destination_cities": [hub]},
            )
        )
    return out


def _store_verdict(
    conn: Any,
    request: TripRequest,
    user_id: int | None,
    verdict: Verdict,
    reports: list[ColdStartReport],
) -> dict:
    cold = [r.model_dump(mode="json") for r in reports]
    (trip_id,) = conn.execute(
        "INSERT INTO trip (request, status, alternatives, user_id, cold_start) "
        "VALUES (%s, %s, %s, %s, %s) RETURNING id",
        (
            request.model_dump_json(),
            "impossible",
            verdict.model_dump_json(),
            user_id,
            json.dumps(cold),
        ),
    ).fetchone()
    return {
        "id": str(trip_id),
        "status": "impossible",
        "verdict": verdict.model_dump(mode="json"),
        "cold_start": cold,
    }


def create(
    request: TripRequest, conn: Any, user_id: int | None = None, *, llm: Any = complete
) -> dict:
    """Cold-start any city we have never seen, plan, store, and return what the
    page needs. demo_seed.py uses this too.

    A planned trip keeps the best candidate in `plan` and the other two in
    `alternatives`; a verdict keeps its reasons and alternatives there instead.
    Every cold-start report rides along on `cold_start`.
    """
    reports: list[ColdStartReport] = []
    wanted = [(request.origin_city, False)] + [
        (c, True) for c in request.destination_cities
    ]
    for city, need_places in wanted:
        try:
            report = ensure_city(conn, city, need_places=need_places, llm=llm)
        except ColdStartError as exc:
            log.warning("cold start %s failed: %s", city, exc)
            verdict = Verdict(
                status="impossible",
                reasons=[
                    Reason(label="Could not reach the model", value=city, unit="")
                ],
                alternatives=hub_alternatives(conn, city, None),
            )
            return _store_verdict(conn, request, user_id, verdict, reports)
        reports.append(report)
        if need_places and report.poi_count < MIN_PLACES:
            verdict = Verdict(
                status="impossible",
                reasons=[
                    Reason(
                        label=f"Places we could find in {city}",
                        value=report.poi_count,
                        unit="places",
                    )
                ],
                alternatives=hub_alternatives(conn, city, report.centre),
            )
            return _store_verdict(conn, request, user_id, verdict, reports)

    result = plan_all(request, conn)
    if isinstance(result, Verdict):
        return _store_verdict(conn, request, user_id, result, reports)
    first, *others = result
    alternatives = [p.model_dump(mode="json") for p in others]
    cold = [r.model_dump(mode="json") for r in reports]
    (trip_id,) = conn.execute(
        "INSERT INTO trip (request, status, plan, alternatives, user_id, cold_start) "
        "VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
        (
            request.model_dump_json(),
            "planned",
            first.model_dump_json(),
            json.dumps(alternatives),
            user_id,
            json.dumps(cold),
        ),
    ).fetchone()
    return {
        "id": str(trip_id),
        "status": "planned",
        "plan": first.model_dump(mode="json"),
        "alternatives": alternatives,
        "cold_start": cold,
    }


class ParseIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


@router.post("/trips/parse")
def parse_trip(body: ParseIn) -> dict:
    """The traveller's own words into form fields; never a date, never a guess."""
    return parse_intake(body.text)


@router.post("/trips")
def create_trip(request: TripRequest, conn: Db, me: Me) -> dict:
    try:
        return create(request, conn, me.id)
    except ValueError as exc:  # "unknown city: X" from the planner, never a 500
        raise HTTPException(422, str(exc)) from exc


def load_trip(conn: Any, trip_id: str, user_id: int | None = None) -> dict:
    """One trip. With a user_id, a trip someone else owns is a 404, not a 403:
    the traveller has no business learning that the id exists."""
    row = conn.execute(
        "SELECT id, request, status, plan, alternatives, created_at, user_id, "
        "narration, cold_start FROM trip WHERE id = %s",
        (trip_id,),
    ).fetchone()
    if not row or (user_id is not None and row[6] is not None and row[6] != user_id):
        raise HTTPException(404, "no such trip")
    return {
        "id": str(row[0]),
        "request": _json(row[1]),
        "status": row[2],
        "plan": _json(row[3]),
        "alternatives": _json(row[4]),
        "created_at": row[5].isoformat(),
        "user_id": row[6],
        "narration": row[7] if len(row) > 7 else None,
        "cold_start": _json(row[8]) if len(row) > 8 else None,
    }


@router.get("/trips/{trip_id}")
def get_trip(trip_id: str, conn: Db, me: Me) -> dict:
    return load_trip(conn, trip_id, me.id)


class ChooseIn(BaseModel):
    index: int = Field(ge=0)


@router.post("/trips/{trip_id}/choose")
def choose_plan(trip_id: str, body: ChooseIn, conn: Db, me: Me) -> dict:
    """Make candidate `index` of [plan, *alternatives] the plan.

    The plan that was current joins the alternatives, so nothing is lost and
    the chat keeps editing whichever one the traveller is looking at.
    """
    trip = load_trip(conn, trip_id, me.id)
    if trip["status"] != "planned":
        raise HTTPException(409, "this trip has no plan to choose from")
    candidates = [trip["plan"], *(trip["alternatives"] or [])]
    if body.index >= len(candidates):
        raise HTTPException(404, "no such candidate")
    chosen = candidates.pop(body.index)
    conn.execute(
        "UPDATE trip SET plan = %s, alternatives = %s WHERE id = %s",
        (json.dumps(chosen), json.dumps(candidates), trip_id),
    )
    return load_trip(conn, trip_id, me.id)


class ChatIn(BaseModel):
    message: str = Field(min_length=1)
    language: str = "en"
    current_poi: int | None = None
    current_day: int | None = None


@router.post("/trips/{trip_id}/chat")
def chat(trip_id: str, body: ChatIn, conn: Db, me: Me) -> dict:
    trip = load_trip(conn, trip_id, me.id)
    if not trip["plan"]:
        raise HTTPException(409, "this trip has no plan to talk about")
    request = TripRequest.model_validate(trip["request"])
    plan = Plan.model_validate(trip["plan"])
    context = TripContext(
        current_poi=body.current_poi,
        current_day=body.current_day,
        has_elderly=request.has_elderly,
    )
    verdict = classify(body.message, plan)
    if isinstance(verdict, Question):
        reply = answer(verdict.text, conn, language=body.language, trip_context=context)
        return reply.model_dump()
    if isinstance(verdict, Clarification):
        return verdict.model_dump()

    loaded = load(request, conn)
    pois, edges, _legs, advisories, _centroids = loaded
    by_city: dict[str, list] = {}
    for p in scored_pool(pois, request, edges, advisories).values():
        by_city.setdefault(p.city, []).append(p)
    resolved = resolve(verdict, plan, by_city)
    if isinstance(resolved, Clarification):
        return resolved.model_dump()
    result = apply_edit(resolved, plan, request, loaded)
    attach([result.plan], request)
    # The paragraph described the old plan; the next load writes a new one.
    conn.execute(
        "UPDATE trip SET plan = %s, narration = NULL WHERE id = %s",
        (result.plan.model_dump_json(), trip_id),
    )
    return {
        "kind": "edit",
        "edit": resolved.model_dump(),
        "plan": result.plan.model_dump(mode="json"),
        "changed_day": result.changed_day,
        "change_summary": result.change_summary.model_dump(),
        "violations": result.violations,
    }


@router.post("/trips/{trip_id}/narrate")
def trip_narrate(trip_id: str, conn: Db, me: Me) -> dict:
    """The plan in a few words, written by the model and checked against the
    plan, stored once. A narration that failed its check is not returned."""
    trip = load_trip(conn, trip_id, me.id)
    if trip.get("narration"):
        return {"narration": trip["narration"], "source": "stored"}
    if not trip["plan"]:
        raise HTTPException(409, "this trip has no plan to describe")
    request = TripRequest.model_validate(trip["request"])
    plan = Plan.model_validate(trip["plan"])
    attach([plan], request)
    told = narrate_plan(plan, request, "en")
    if told.fell_back:
        raise HTTPException(502, "the narration did not pass its check")
    conn.execute("UPDATE trip SET narration = %s WHERE id = %s", (told.text, trip_id))
    return {"narration": told.text, "source": "narrator", "cost_usd": told.cost_usd}


# --------------------------------------------------------------------------- #
# katha
# --------------------------------------------------------------------------- #


class KathaIn(BaseModel):
    scope: Scope
    duration_min: int = Field(ge=1, le=30)
    depth: Depth = "quick"
    language: str = "en"
    trip_id: str | None = None


def _store_segments(conn: Any, tour_id: str, katha: Katha) -> None:
    conn.execute(
        "UPDATE tour SET segments = %s WHERE id = %s",
        (json.dumps([s.model_dump(mode="json") for s in katha.segments]), tour_id),
    )


def fill_narration(katha: Katha, city: str | None) -> tuple[bool, str]:
    """Give every segment a narration. (anything changed, where it came from).

    A Katha made of the same paragraphs as a warm_tts.py demo takes the demo's
    narration, so the review never waits on the model or the network for it.
    """
    missing = [s for s in katha.segments if s.narration is None]
    if not missing:
        return False, "stored"
    demo = cached_demo(katha)
    if demo is not None:
        for segment, text in zip(katha.segments, demo["narrations"], strict=True):
            segment.narration = text
        return True, "demo"
    for segment in missing:
        segment.narration = narrate_segment(
            segment.model_dump(),
            katha.language,
            place=(city or "") if segment.theme else (segment.spine_item or city or ""),
        ).text
    return True, "narrator"


def _city_layer_drafter(conn: Any) -> Any:
    """Draft the Katha city layer for a city that has none; never raises."""

    def draft(city: str) -> bool:
        try:
            n, cost = ensure_city_layer(conn, city)
        except (ValueError, TypeError, KeyError, RuntimeError, httpx.HTTPError) as exc:
            log.warning("city layer for %s not drafted: %s", city, exc)
            return False
        log.info("city layer %s: %d paragraphs, cost_usd=%.5f", city, n, cost)
        return n > 0

    return draft


@router.post("/katha")
def create_katha(body: KathaIn, conn: Db, me: Me) -> dict:
    try:
        katha = build(
            body.scope,
            body.duration_min,
            body.depth,
            body.language,
            body.trip_id,
            catalogue=DbCatalogue(conn),
            retriever=db_retriever(conn),
            drafter=_city_layer_drafter(conn),
        )
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    if cached_demo(katha) is not None:
        fill_narration(katha, None)  # the demo's words, no model call
    city = katha.spine[0].city if katha.spine else str(body.scope.id)
    (tour_id,) = conn.execute(
        "INSERT INTO tour (trip_id, city, duration_min, depth, segments, language, "
        "scope, total_words, user_id) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
        (
            body.trip_id,
            city,
            body.duration_min,
            body.depth,
            json.dumps([s.model_dump(mode="json") for s in katha.segments]),
            body.language,
            body.scope.model_dump_json(),
            katha.total_words,
            me.id,
        ),
    ).fetchone()
    katha.id = str(tour_id)
    return katha.model_dump(mode="json")


def load_katha(
    conn: Any, tour_id: str, user_id: int | None = None
) -> tuple[Katha, str | None, dict]:
    """(the Katha, its city, the tour row's own facts). Scoped like load_trip."""
    row = conn.execute(
        "SELECT id, duration_min, depth, segments, language, scope, total_words, "
        "city, trip_id, created_at, user_id FROM tour WHERE id = %s",
        (tour_id,),
    ).fetchone()
    if not row or (user_id is not None and row[10] is not None and row[10] != user_id):
        raise HTTPException(404, "no such katha")
    segments = _json(row[3]) or []
    scope = _json(row[5]) or {"kind": "city", "id": row[7]}
    katha = Katha(
        id=str(row[0]),
        scope=Scope.model_validate(scope),
        duration_min=row[1],
        depth=row[2],
        language=row[4],
        segments=segments,
        total_words=row[6] or sum(s["words"] for s in segments),
        spine=[],
        type_sequence=[s["chunk_type"] for s in segments],
    )
    meta = {
        "trip_id": str(row[8]) if row[8] else None,
        "created_at": row[9].isoformat(),
    }
    return katha, row[7], meta


@router.get("/katha/{tour_id}")
def get_katha(tour_id: str, conn: Db, me: Me) -> dict:
    katha, _, _ = load_katha(conn, tour_id, me.id)
    return katha.model_dump(mode="json")


@router.post("/katha/{tour_id}/narrate")
def katha_narrate(tour_id: str, conn: Db, me: Me) -> dict:
    """Every segment narrated in the Katha's language, stored, returned."""
    katha, city, _ = load_katha(conn, tour_id, me.id)
    changed, source = fill_narration(katha, city)
    if changed:
        _store_segments(conn, tour_id, katha)
    return katha.model_dump(mode="json") | {"narration_source": source}


@router.post("/katha/{tour_id}/audio")
def katha_audio(tour_id: str, conn: Db, me: Me) -> Response:
    """The whole Katha spoken, or 204 when speech is not available right now."""
    katha, city, _ = load_katha(conn, tour_id, me.id)
    changed, source = fill_narration(katha, city)
    if changed:
        _store_segments(conn, tour_id, katha)
    text = "\n\n".join(s.narration or s.text for s in katha.segments)
    cached = cache_path(text, katha.language).exists()
    audio = speak(text, katha.language)
    if audio is None:
        return Response(status_code=204, headers={"X-Voice": "none"})
    return Response(
        content=audio,
        media_type="audio/wav",
        headers={
            "X-Voice": "cached" if cached else "sarvam",
            "X-Narration": source,
        },
    )


# --------------------------------------------------------------------------- #
# places
# --------------------------------------------------------------------------- #

WORDS = "array_length(regexp_split_to_array(c.body, '\\s+'), 1)"


def coverage(conn: Any) -> list[dict]:
    """Per hub city: places with a sourced paragraph, paragraphs, minutes, centre."""
    rows = conn.execute(
        f"""
        SELECT p.city, avg(p.lat), avg(p.lng), count(DISTINCT p.id),
               count(DISTINCT c.poi_id), count(c.id), coalesce(sum({WORDS}), 0),
               (SELECT count(*) FROM doc_chunk x
                 WHERE x.city = p.city AND x.poi_id IS NULL AND NOT x.retired),
               (SELECT coalesce(sum(array_length(regexp_split_to_array(x.body, '\\s+'), 1)), 0)
                  FROM doc_chunk x
                 WHERE x.city = p.city AND x.poi_id IS NULL AND NOT x.retired)
        FROM poi p LEFT JOIN doc_chunk c ON c.poi_id = p.id AND NOT c.retired
        GROUP BY p.city ORDER BY p.city
        """
    ).fetchall()
    return [
        {
            "city": r[0],
            "lat": float(r[1]),
            "lng": float(r[2]),
            "pois": int(r[3]),
            "places": int(r[4]),
            "paragraphs": int(r[5]) + int(r[7]),
            "minutes": round((int(r[6]) + int(r[8])) / WORDS_PER_MIN),
        }
        for r in rows
    ]


@router.get("/places/coverage")
def places_coverage(conn: Db, cities: str = "") -> dict:
    """{typed city: poi rows we hold}, so the form can warn before it posts."""
    typed = list(dict.fromkeys(c.strip() for c in cities.split(",") if c.strip()))
    hubs = {c: hub_city(c) for c in typed}
    counts = dict(
        conn.execute(
            "SELECT city, count(*) FROM poi WHERE city = ANY(%s) GROUP BY city",
            (sorted(set(hubs.values())),),
        ).fetchall()
    )
    return {c: int(counts.get(h, 0)) for c, h in hubs.items()}


@router.get("/places/search")
def places_search(conn: Db, me: Me, q: str = "") -> dict:
    """Cities and places for the Katha search box, with minutes of material."""
    q = q.strip()
    cities = [
        {
            "kind": "city",
            "id": c["city"],
            "name": c["city"],
            "places": c["places"],
            "minutes": c["minutes"],
        }
        for c in coverage(conn)
        if not q or q.lower() in c["city"].lower()
    ]
    # pg_trgm is installed for this: "chamundi" has to find Chamundeshwari.
    rows = conn.execute(
        f"SELECT p.id, p.name, p.name_kn, p.city, "
        f"(SELECT coalesce(sum({WORDS}), 0) FROM doc_chunk c "
        f" WHERE c.poi_id = p.id AND NOT c.retired) AS words "
        "FROM poi p "
        "WHERE %(q)s = '' OR p.name ILIKE %(like)s OR coalesce(p.name_kn, '') LIKE %(like)s "
        "OR p.city ILIKE %(like)s OR similarity(p.name, %(q)s) > 0.25 "
        "ORDER BY (p.name ILIKE %(like)s) DESC, similarity(p.name, %(q)s) DESC, "
        "p.popularity DESC NULLS LAST, p.name LIMIT 12",
        {"q": q, "like": f"%{q}%"},
    ).fetchall()
    places = [
        {
            "kind": "place",
            "id": r[0],
            "name": r[1],
            "name_kn": r[2],
            "city": r[3],
            "minutes": round(int(r[4]) / WORDS_PER_MIN),
        }
        for r in rows
    ]
    return {"query": q, "results": cities + places}

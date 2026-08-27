"""The JSON API. Thin: every route is a lookup, one call into a module, a write."""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from typing import Annotated, Any

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from app.chat.router import (
    Clarification,
    Question,
    answer,
    apply_edit,
    classify,
    resolve,
)
from app.katha.build import DbCatalogue, build, db_retriever
from app.katha.models import Depth, Katha, Scope
from app.llm.narrate import narrate_segment
from app.planner.engine import load, scored_pool
from app.planner.engine import plan as plan_trip
from app.planner.models import Plan, TripRequest, Verdict
from app.rag.retrieve import TripContext
from app.voice.tts import speak

router = APIRouter(prefix="/api")


def db() -> Iterator[Any]:
    with psycopg.connect(os.environ["SUPABASE_DB_URL"]) as conn:
        yield conn


Db = Annotated[Any, Depends(db)]


def _json(value: Any) -> Any:
    return (
        value if isinstance(value, dict | list) or value is None else json.loads(value)
    )


# --------------------------------------------------------------------------- #
# trips
# --------------------------------------------------------------------------- #


@router.post("/trips")
def create_trip(request: TripRequest, conn: Db) -> dict:
    result = plan_trip(request, conn)
    if isinstance(result, Verdict):
        (trip_id,) = conn.execute(
            "INSERT INTO trip (request, status, alternatives) VALUES (%s, %s, %s) RETURNING id",
            (request.model_dump_json(), "impossible", result.model_dump_json()),
        ).fetchone()
        return {"id": str(trip_id), "verdict": result.model_dump(mode="json")}
    (trip_id,) = conn.execute(
        "INSERT INTO trip (request, status, plan) VALUES (%s, %s, %s) RETURNING id",
        (request.model_dump_json(), "planned", result.model_dump_json()),
    ).fetchone()
    return {"id": str(trip_id), "plan": result.model_dump(mode="json")}


def _trip(conn: Any, trip_id: str) -> dict:
    row = conn.execute(
        "SELECT id, request, status, plan, alternatives FROM trip WHERE id = %s",
        (trip_id,),
    ).fetchone()
    if not row:
        raise HTTPException(404, "no such trip")
    return {
        "id": str(row[0]),
        "request": _json(row[1]),
        "status": row[2],
        "plan": _json(row[3]),
        "alternatives": _json(row[4]),
    }


@router.get("/trips/{trip_id}")
def get_trip(trip_id: str, conn: Db) -> dict:
    return _trip(conn, trip_id)


class ChatIn(BaseModel):
    message: str = Field(min_length=1)
    language: str = "en"
    current_poi: int | None = None
    current_day: int | None = None


@router.post("/trips/{trip_id}/chat")
def chat(trip_id: str, body: ChatIn, conn: Db) -> dict:
    trip = _trip(conn, trip_id)
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
    conn.execute(
        "UPDATE trip SET plan = %s WHERE id = %s",
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


# --------------------------------------------------------------------------- #
# katha
# --------------------------------------------------------------------------- #


class KathaIn(BaseModel):
    scope: Scope
    duration_min: int = Field(ge=1, le=30)
    depth: Depth = "quick"
    language: str = "en"
    trip_id: str | None = None


@router.post("/katha")
def create_katha(body: KathaIn, conn: Db) -> dict:
    try:
        katha = build(
            body.scope,
            body.duration_min,
            body.depth,
            body.language,
            body.trip_id,
            catalogue=DbCatalogue(conn),
            retriever=db_retriever(conn),
        )
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    city = katha.spine[0].city if katha.spine else str(body.scope.id)
    (tour_id,) = conn.execute(
        "INSERT INTO tour (trip_id, city, duration_min, depth, segments, language, "
        "scope, total_words) VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
        (
            body.trip_id,
            city,
            body.duration_min,
            body.depth,
            json.dumps([s.model_dump(mode="json") for s in katha.segments]),
            body.language,
            body.scope.model_dump_json(),
            katha.total_words,
        ),
    ).fetchone()
    katha.id = str(tour_id)
    return katha.model_dump(mode="json")


def _katha(conn: Any, tour_id: str) -> tuple[Katha, str | None]:
    row = conn.execute(
        "SELECT id, duration_min, depth, segments, language, scope, total_words, city "
        "FROM tour WHERE id = %s",
        (tour_id,),
    ).fetchone()
    if not row:
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
    return katha, row[7]


@router.get("/katha/{tour_id}")
def get_katha(tour_id: str, conn: Db) -> dict:
    katha, _ = _katha(conn, tour_id)
    return katha.model_dump(mode="json")


@router.post("/katha/{tour_id}/audio")
def katha_audio(tour_id: str, conn: Db) -> Response:
    """The whole Katha spoken, or 204 when speech is not available right now."""
    katha, city = _katha(conn, tour_id)
    changed = False
    for segment in katha.segments:
        if segment.narration is None:
            narration = narrate_segment(
                segment.model_dump(),
                katha.language,
                place=segment.spine_item or city or "",
            )
            segment.narration = narration.text
            changed = True
    if changed:
        conn.execute(
            "UPDATE tour SET segments = %s WHERE id = %s",
            (json.dumps([s.model_dump(mode="json") for s in katha.segments]), tour_id),
        )
    text = "\n\n".join(s.narration or s.text for s in katha.segments)
    audio = speak(text, katha.language)
    if audio is None:
        return Response(status_code=204)
    return Response(content=audio, media_type="audio/wav")


# --------------------------------------------------------------------------- #
# places
# --------------------------------------------------------------------------- #


@router.get("/places/search")
def places_search(conn: Db, q: str = "") -> dict:
    """Cities and places for the Katha search box."""
    q = q.strip()
    cities = [
        {"kind": "city", "id": c, "name": c}
        for (c,) in conn.execute("SELECT DISTINCT city FROM poi ORDER BY city")
        if not q or q.lower() in c.lower()
    ]
    # pg_trgm is installed for this: "chamundi" has to find Chamundeshwari.
    rows = conn.execute(
        "SELECT id, name, name_kn, city FROM poi "
        "WHERE %(q)s = '' OR name ILIKE %(like)s OR coalesce(name_kn, '') LIKE %(like)s "
        "OR city ILIKE %(like)s OR similarity(name, %(q)s) > 0.25 "
        "ORDER BY (name ILIKE %(like)s) DESC, similarity(name, %(q)s) DESC, "
        "popularity DESC NULLS LAST, name LIMIT 12",
        {"q": q, "like": f"%{q}%"},
    ).fetchall()
    places = [
        {"kind": "place", "id": r[0], "name": r[1], "name_kn": r[2], "city": r[3]}
        for r in rows
    ]
    return {"query": q, "results": cities + places}

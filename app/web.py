"""The pages: Jinja2 and vanilla JS over the JSON API, no build step.

Every number on a page comes from the modules the API uses; the templates
format, they do not compute. The four team accounts sit behind a signed cookie
(see app/accounts.py); only the landing page and /health are public.
"""

from __future__ import annotations

import os
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import parse_qs

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.accounts import COOKIE, User, authenticate, from_cookie, sign
from app.api.routes import (
    Db,
    _json,
    coverage,
    load_katha,
    load_trip,
    places_search,
)
from app.demo import DEMO_REQUEST, find_demo_trip
from app.planner.engine import CENTROID_SQL, load, transfer_moves
from app.planner.models import Day, Plan, TripRequest
from app.planner.transport import attach
from app.planner.validate import DAY_END, DAY_END_ELDERLY, local_moves

ROOT = Path(__file__).resolve().parent
IST = timezone(timedelta(hours=5, minutes=30))
CITY_KN = {
    "Mysuru": "ಮೈಸೂರು",
    "Hampi": "ಹಂಪಿ",
    "Bengaluru": "ಬೆಂಗಳೂರು",
    "Chikmagalur": "ಚಿಕ್ಕಮಗಳೂರು",
    "Coorg": "ಕೊಡಗು",
}
LANGUAGE_NAMES = {"en": "English", "kn": "ಕನ್ನಡ", "hi": "हिन्दी"}
VARIANT_TITLE = {
    "steady": "The steady one",
    "interests": "The interests-first one",
    "popular": "The crowd-pleaser",
}
VARIANT_LEAN = {
    "steady": "The house mix: your interests first, then popularity, then what sits well together.",
    "interests": "Leans harder on what you said you're here for; a quieter stop can beat a famous one.",
    "popular": "Leans on the famous names and the places that pair well with them.",
}

pages = APIRouter(include_in_schema=False)
templates = Jinja2Templates(directory=str(ROOT / "templates"))


# --------------------------------------------------------------------------- #
# formatting filters
# --------------------------------------------------------------------------- #


def inr(n: Any) -> str:
    return f"₹{int(n or 0):,}"


def as_time(t: Any) -> time:
    return t if isinstance(t, time) else time.fromisoformat(str(t))


def clock12(t: Any) -> str:
    t = as_time(t)
    hour = t.hour % 12 or 12
    return f"{hour}:{t.minute:02d} {'pm' if t.hour >= 12 else 'am'}"


def hour12(t: Any) -> str:
    t = as_time(t)
    hour = t.hour % 12 or 12
    minutes = f":{t.minute:02d}" if t.minute else ""
    return f"{hour}{minutes} {'pm' if t.hour >= 12 else 'am'}"


def hmm(minutes: Any) -> str:
    hours, mins = divmod(int(minutes), 60)
    return f"{hours} h {mins:02d} m" if hours else f"{mins} m"


def as_date(d: Any) -> date:
    return d if isinstance(d, date) else date.fromisoformat(str(d))


def daterange(start: Any, days: int, long: bool = False) -> str:
    start = as_date(start)
    end = start + timedelta(days=max(int(days), 1) - 1)
    month = "%B" if long else "%b"
    if end == start:
        return f"{start.day} {start:{month}}"
    if start.month == end.month:
        return f"{start.day}–{end.day} {start:{month}}"
    return f"{start.day} {start:{month}}–{end.day} {end:{month}}"


def day_month(d: Any) -> str:
    d = as_date(d)
    return f"{d.day:02d} {d:%b}"


def weekday_date(d: Any) -> str:
    d = as_date(d)
    return f"{d:%a} {d.day} {d:%b}"


SINGULAR = {"days": "day", "cities": "city", "places": "place"}


def reason_value(r: dict) -> str:
    if r["unit"] == "minutes":
        return hmm(r["value"])
    unit = SINGULAR.get(r["unit"], r["unit"]) if r["value"] == 1 else r["unit"]
    return f"{r['value']} {unit}".strip()


def plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def party_text(req: TripRequest) -> str:
    """'2 adults (one over 60), 1 child' from travellers; 'N people' for a trip
    stored before travellers existed."""
    if not req.travellers:
        return f"{req.party_size} people"
    adults = [t for t in req.travellers if t.kind == "adult"]
    kids = [t for t in req.travellers if t.kind == "child"]
    elders = sum(t.age_band == "60+" for t in adults)
    text = plural(len(adults), "adult")
    if elders:
        text += f" ({'one' if elders == 1 else elders} over 60)"
    if kids:
        text += f", {len(kids)} {'child' if len(kids) == 1 else 'children'}"
    return text


templates.env.filters.update(
    {
        "inr": inr,
        "clock12": clock12,
        "hour12": hour12,
        "hmm": hmm,
        "daterange": daterange,
        "day_month": day_month,
        "weekday_date": weekday_date,
        "reason_value": reason_value,
        "plural": plural,
        "party": party_text,
    }
)


# --------------------------------------------------------------------------- #
# the session
# --------------------------------------------------------------------------- #


def signed_in(request: Request, conn: Any) -> User | None:
    """The user this request's cookie names, or None."""
    return from_cookie(conn, request.cookies.get(COOKIE, ""))


def require_user(request: Request, conn: Db) -> User:
    """A page behind the session cookie. Anonymous visitors are sent to sign in
    and come back to where they were going."""
    user = signed_in(request, conn)
    if user is None:
        raise HTTPException(
            303, headers={"Location": f"/signin?next={request.url.path}"}
        )
    return user


Me = Annotated[User, Depends(require_user)]


def render(
    request: Request, name: str, user: User | None = None, **context: Any
) -> HTMLResponse:
    context.setdefault("data", {})
    context["account"] = user
    return templates.TemplateResponse(request, name, context)


# --------------------------------------------------------------------------- #
# shared lookups
# --------------------------------------------------------------------------- #


def centroids(conn: Any) -> dict[str, list[float]]:
    return {r[0]: [float(r[1]), float(r[2])] for r in conn.execute(CENTROID_SQL)}


def poi_total(conn: Any) -> int:
    return int(conn.execute("SELECT count(*) FROM poi").fetchone()[0])


def day_limit(req: TripRequest) -> time:
    return req.day_end or (DAY_END_ELDERLY if req.gentle else DAY_END)


def short(name: str) -> str:
    """'Hotel RRR, Gandhi Square' -> 'Hotel RRR'; parentheses dropped."""
    head = name.split("(")[0].split(",")[0].strip()
    return head or name


def join_names(names: list[str]) -> str:
    if not names:
        return ""
    if len(names) == 1:
        return names[0]
    return ", ".join(names[:-1]) + " and " + names[-1]


def route_km(day: Day) -> float:
    """Day.route_km when the plan carries it; older plans add up their hops.

    A plan stored before Day.route_km existed deserialises to 0.0, which is not
    a measurement, so those fall through to the hops.
    """
    if day.route_km:
        return day.route_km
    return round(sum(m.km for m in local_moves(day)), 1)


def day_summary(day: Day) -> dict:
    return {
        "stops": len(day.stops),
        "km": route_km(day),
        "ends": clock12(day.ends_at),
        "hard": any(s.leg_type == "hard" for s in day.stops),
    }


def blurb(plan: Plan) -> str:
    stops = sum(len(d.stops) for d in plan.days)
    anchors = [
        short(s.name) for d in plan.days for s in d.stops if s.leg_type == "hard"
    ]
    latest = max((d.ends_at for d in plan.days), default=time(9, 0))
    km = round(sum(route_km(d) for d in plan.days), 1)
    around = f", built around {join_names(anchors)}" if anchors else ""
    return (
        f"{VARIANT_LEAN.get(plan.variant, '')} {plural(stops, 'stop')} over "
        f"{plural(len(plan.days), 'day')}{around}. Latest evening ends "
        f"{clock12(latest)}; {km} km between stops."
    )


def _poi_names(conn: Any, ids: list[int]) -> dict[int, dict]:
    if not ids:
        return {}
    rows = conn.execute(
        "SELECT id, name, name_kn, city FROM poi WHERE id = ANY(%s)", (ids,)
    ).fetchall()
    return {r[0]: {"name": r[1], "name_kn": r[2], "city": r[3]} for r in rows}


def trip_rows(conn: Any, limit: int, user_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT id, created_at, request, status, plan FROM trip "
        "WHERE user_id = %s ORDER BY created_at DESC LIMIT %s",
        (user_id, limit),
    ).fetchall()
    out = []
    for r in rows:
        req = TripRequest.model_validate(_json(r[2]))
        plan = _json(r[4])
        if plan:
            meta = f"{plural(req.days, 'day')} · {inr(plan['total_spend'])} · {plan['comfort']}"
            meta_home = (
                f"Trip · {plural(req.days, 'day')} · {party_text(req)} · "
                f"{plan['comfort']}"
            )
        else:
            meta = f"{plural(req.days, 'day')} · doesn't fit as asked"
            meta_home = "Trip · doesn't fit as asked"
        out.append(
            {
                "created": r[1],
                "date": daterange(req.start_date, req.days).upper(),
                "title": req.title,
                "meta": meta,
                "meta_home": meta_home,
                "href": f"/trips/{r[0]}",
                "action": "Open",
            }
        )
    return out


def katha_rows(conn: Any, limit: int, user_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT id, created_at, city, duration_min, depth, language, scope FROM tour "
        "WHERE user_id = %s ORDER BY created_at DESC LIMIT %s",
        (user_id, limit),
    ).fetchall()
    scopes = [_json(r[6]) or {"kind": "city", "id": r[2]} for r in rows]
    names = _poi_names(conn, [int(s["id"]) for s in scopes if s["kind"] == "place"])
    out = []
    for r, scope in zip(rows, scopes, strict=True):
        if scope["kind"] == "place":
            poi = names.get(int(scope["id"]), {})
            title = poi.get("name", r[2])
            if r[5] == "kn" and poi.get("name_kn"):
                title = poi["name_kn"]
        elif scope["kind"] == "day":
            title = f"Day {scope['id']} · {r[2]}"
        else:
            title = str(scope["id"])
        kind = scope["kind"]
        out.append(
            {
                "created": r[1],
                "date": day_month(r[1].astimezone(IST).date()).upper(),
                "title": title,
                "meta": (
                    f"{kind.capitalize()} · {r[3]} min · {r[4]} · "
                    f"{LANGUAGE_NAMES.get(r[5], r[5])}"
                ),
                "meta_home": f"Katha · {kind} · {r[3]} min · {r[4]}",
                "href": f"/katha/{r[0]}",
                "action": "Replay",
            }
        )
    return out


# --------------------------------------------------------------------------- #
# public pages
# --------------------------------------------------------------------------- #


@pages.get("/", response_class=HTMLResponse)
def landing(request: Request, conn: Db) -> HTMLResponse:
    trip_id = find_demo_trip(conn)
    if trip_id is None:
        row = conn.execute(
            "SELECT id FROM trip WHERE status = 'planned' ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        trip_id = str(row[0]) if row else None
    trip = load_trip(conn, trip_id) if trip_id else None
    day = None
    summary = None
    if trip and trip["plan"]:
        plan = Plan.model_validate(trip["plan"])
        chosen = plan.days[1] if len(plan.days) > 1 else plan.days[0]
        day = chosen.model_dump(mode="json")
        summary = day_summary(chosen)
    return render(
        request,
        "landing.html",
        user=signed_in(request, conn),
        trip=trip,
        day=day,
        summary=summary,
        data={"day": day, "centroids": centroids(conn) if day else {}},
    )


@pages.get("/signin", response_class=HTMLResponse)
def signin_form(request: Request) -> HTMLResponse:
    return render(
        request, "signin.html", next=request.query_params.get("next", "/home")
    )


@pages.post("/signin")
async def signin(request: Request, conn: Db) -> Any:
    # ponytail: parse_qs instead of Form(): the one form in the app is not
    # worth the python-multipart dependency.
    form = parse_qs((await request.body()).decode())
    email = form.get("email", [""])[0].strip().lower()
    password = form.get("password", [""])[0]
    nxt = form.get("next", ["/home"])[0]
    user = authenticate(conn, email, password)
    if user is None:
        error = (
            "That's not it. Four seeded accounts in this build."
            if os.environ.get("DEMO_PASSWORD")
            else "DEMO_PASSWORD is not set on the server, so nobody can sign in yet."
        )
        response = render(request, "signin.html", next=nxt, error=error, email=email)
        response.status_code = 401
        return response
    if not nxt.startswith("/") or nxt.startswith("//"):
        nxt = "/home"
    response = RedirectResponse(nxt, status_code=303)
    response.set_cookie(
        COOKIE,
        sign(user.id) or "",
        httponly=True,
        samesite="lax",
        max_age=7 * 24 * 3600,
    )
    return response


@pages.get("/signout")
def signout() -> RedirectResponse:
    response = RedirectResponse("/", status_code=303)
    response.delete_cookie(COOKIE)
    return response


# --------------------------------------------------------------------------- #
# app pages
# --------------------------------------------------------------------------- #


@pages.get("/home", response_class=HTMLResponse)
def home(request: Request, conn: Db, me: Me) -> HTMLResponse:
    now = datetime.now(IST)
    recent = sorted(
        trip_rows(conn, 3, me.id) + katha_rows(conn, 3, me.id),
        key=lambda r: r["created"],
        reverse=True,
    )[:3]
    return render(
        request,
        "home.html",
        user=me,
        nav="home",
        today=f"{now:%A}, {now.day} {now:%B}",
        recent=recent,
    )


@pages.get("/trips/new", response_class=HTMLResponse)
def trip_new(request: Request, conn: Db, me: Me) -> HTMLResponse:
    return render(
        request,
        "trip_new.html",
        user=me,
        nav="trips",
        defaults=DEMO_REQUEST,
        data={
            "poi_total": poi_total(conn),
            "defaults": DEMO_REQUEST.model_dump(mode="json"),
        },
    )


@pages.get("/trips/{trip_id}", response_class=HTMLResponse)
def trip_page(request: Request, trip_id: str, conn: Db, me: Me) -> HTMLResponse:
    trip = load_trip(conn, trip_id, me.id)
    req = TripRequest.model_validate(trip["request"])
    if trip["status"] != "planned" or not trip["plan"]:
        verdict = trip["alternatives"] or {
            "status": "impossible",
            "reasons": [],
            "alternatives": [],
        }
        _pois, _edges, legs, _adv, centres = load(req, conn)
        route = [req.origin_city, *req.destination_cities]
        try:
            moves = transfer_moves(req, legs, centres)
        except ValueError:  # a city nobody could place: no distance to draw
            moves = []
        labels = {r["label"]: r["value"] for r in verdict["reasons"]}
        found = [k for k in labels if k.startswith("Places we could find in ")]
        if found:
            city = found[0].removeprefix("Places we could find in ")
            prose = (
                f"We could find only {plural(int(labels[found[0]]), 'place')} in "
                f"{city}, and a day needs at least eight to choose from. What we "
                f"did find is drafted by the model and unverified."
            )
        elif "Could not reach the model" in labels:
            prose = (
                f"We have nothing on {labels['Could not reach the model']} yet, and "
                f"the model that drafts a new city could not be reached, so "
                f"nothing could be planned there right now."
            )
        elif "Cities with nothing open to visit" in labels:
            prose = (
                f"Nothing in {labels['Cities with nothing open to visit']} is open "
                f"to visit on these dates, so there is no day to build there."
            )
        else:
            prose = (
                f"{' → '.join(route)} is {hmm(labels.get('Travel between cities', 0))} "
                f"of travel before you've seen a single stone. "
                f"{'A day holds' if req.days == 1 else f'{req.days} days hold'} "
                f"{hmm(labels.get('Planning time available', 0))} of planning time; "
                f"this trip needs {hmm(labels.get('Total the trip needs', 0))}."
            )
        return render(
            request,
            "nofit.html",
            user=me,
            nav="trips",
            trip=trip,
            req=req,
            verdict=verdict,
            prose=prose,
            moves=moves,
            total_km=round(sum(m.km for m in moves)),
            estimated=any(m.is_estimated for m in moves),
            show_map=bool(moves) and sum(c in centres for c in route) >= 2,
            data={
                "request": trip["request"],
                "route": route,
                "cities": {c: centres[c] for c in route if c in centres},
                "legs": [m.model_dump() for m in moves],
                "alternatives": verdict["alternatives"],
            },
        )

    if "pick" in request.query_params:
        candidates = [trip["plan"], *(trip["alternatives"] or [])]
        plans = [Plan.model_validate(p) for p in candidates]
        cards = [
            {
                "index": i,
                "title": VARIANT_TITLE.get(p.variant, p.variant),
                "blurb": blurb(p),
                "spend": p.total_spend,
                "comfort": p.comfort,
                "plan_b": p.has_plan_b,
            }
            for i, p in enumerate(plans)
        ]
        tight = sum(p.comfort == "tight" for p in plans)
        if tight == 0:
            knees = ", and the evenings you asked for" if req.has_elderly else ""
            count = {2: "Both", 3: "All three"}.get(len(plans), f"All {len(plans)}")
            lede = f"{count} fit your budget and your evenings{knees}. They just make different trades."
        else:
            lede = (
                f"{len(plans) - tight} of the {len(plans)} fit comfortably; "
                f"{'the other is' if tight == 1 else f'{tight} are'} tight, and "
                f"{'says' if tight == 1 else 'say'} so. They make different trades."
            )
        return render(
            request,
            "choose.html",
            user=me,
            nav="trips",
            trip=trip,
            req=req,
            cards=cards,
            lede=lede + " Pick one; you can still change anything after.",
            data={"trip_id": trip["id"]},
        )

    plan = Plan.model_validate(trip["plan"])
    attach([plan], req)  # a trip stored before the line existed gets it now
    trip["plan"] = plan.model_dump(mode="json")
    limit = day_limit(req)
    return render(
        request,
        "trip.html",
        user=me,
        nav="trips",
        trip=trip,
        req=req,
        plan=plan,
        title=VARIANT_TITLE.get(plan.variant, plan.variant),
        data={
            "trip": trip,
            "poi_total": poi_total(conn),
            "centroids": centroids(conn),
            "day_limit": limit.strftime("%H:%M"),
            "city_kn": CITY_KN,
        },
    )


@pages.get("/katha", response_class=HTMLResponse)
def katha_home(request: Request, conn: Db, me: Me) -> HTMLResponse:
    q = request.query_params.get("q", "").strip()
    cov = coverage(conn)
    return render(
        request,
        "katha_home.html",
        user=me,
        nav="katha",
        q=q,
        coverage=cov,
        places=sum(c["places"] for c in cov),
        paragraphs=sum(c["paragraphs"] for c in cov),
        data={"coverage": cov, "results": places_search(conn, q)["results"], "q": q},
    )


def _place_of(spine_item: str) -> str:
    return spine_item.split(":")[0].strip()


@pages.get("/katha/{tour_id}", response_class=HTMLResponse)
def katha_page(request: Request, tour_id: str, conn: Db, me: Me) -> HTMLResponse:
    katha, city, meta = load_katha(conn, tour_id, me.id)
    scope = katha.scope
    trip = load_trip(conn, meta["trip_id"], me.id) if meta["trip_id"] else None
    trip_title = TripRequest.model_validate(trip["request"]).title if trip else None
    kn_title = None
    if scope.kind == "place":
        poi = _poi_names(conn, [int(scope.id)]).get(int(scope.id), {})
        scope_title = poi.get("name", str(scope.id))
        kn_title = poi.get("name_kn")
        city = poi.get("city", city)
    elif scope.kind == "day":
        scope_title = f"Day {scope.id} · {city}"
        kn_title = CITY_KN.get(city or "")
    else:
        scope_title = str(scope.id)
        kn_title = CITY_KN.get(scope_title)

    names = list(dict.fromkeys(_place_of(s.spine_item) for s in katha.segments))
    rows = conn.execute(
        "SELECT id, name, name_kn, lat, lng, opens, closes, closed_on FROM poi "
        "WHERE name = ANY(%s)",
        (names,),
    ).fetchall()
    places = {
        r[1]: {
            "id": r[0],
            "name": r[1],
            "name_kn": r[2],
            "lat": r[3],
            "lng": r[4],
            "opens": r[5].strftime("%H:%M") if r[5] else None,
            "closes": r[6].strftime("%H:%M") if r[6] else None,
            "closed_on": list(r[7] or []),
        }
        for r in rows
    }
    segments = []
    for s in katha.segments:
        place = _place_of(s.spine_item)
        theme = s.spine_item.split(":", 1)[1].strip() if ":" in s.spine_item else ""
        if scope.kind == "place" and theme:
            side = theme[:1].upper() + theme[1:]
        elif theme == "opening":
            side = f"{place} · to begin"
        else:
            side = short(place)
        body = s.narration or s.text
        source = next((r.name or r.url for r in s.sources if r.name or r.url), "")
        segments.append(
            {
                "title": s.title,
                "chunk_type": s.chunk_type,
                "is_legend": s.is_legend,
                "place": place,
                "side": side,
                "paragraphs": [p for p in body.split("\n\n") if p.strip()],
                "narrated": s.narration is not None,
                "source": source,
                "deeper": places.get(place, {}).get("id")
                if not (
                    scope.kind == "place"
                    and str(scope.id) == str(places.get(place, {}).get("id"))
                )
                else None,
            }
        )
    return render(
        request,
        "katha.html",
        user=me,
        nav="katha",
        katha=katha,
        city=city,
        scope_title=scope_title,
        kn_title=kn_title,
        segments=segments,
        trip=trip,
        trip_title=trip_title,
        language_name=LANGUAGE_NAMES.get(katha.language, katha.language),
        minutes_available=None,
        data={
            "katha": katha.model_dump(mode="json"),
            "places": places,
            "order": names,
            "scope_title": scope_title,
            "trip_id": meta["trip_id"],
            "city": city,
        },
    )


@pages.get("/saved", response_class=HTMLResponse)
def saved(request: Request, conn: Db, me: Me) -> HTMLResponse:
    return render(
        request,
        "saved.html",
        user=me,
        nav="trips",
        trips=trip_rows(conn, 30, me.id),
        kathas=katha_rows(conn, 30, me.id),
    )

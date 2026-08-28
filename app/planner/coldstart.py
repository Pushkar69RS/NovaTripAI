"""Cold start: a city nobody has seeded gets its places, its centre and its Katha
city layer drafted by a model before the planner runs.

Everything drafted here is trust='ai_generated' / source_name='ai_generated'
and stays that way until a verification pass promotes it. A city is drafted
once; the second request finds the rows.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import time
from time import perf_counter
from typing import Any

import httpx
from pydantic import BaseModel

from app.katha.city_layer import DRAFT_SHAPE, THEME_CHUNK_TYPE
from app.llm.client import Completion, complete
from app.llm.models import MODELS
from app.planner.distance import haversine
from app.planner.poi_rules import CATEGORIES, INDIA_BOX, poi_problems

log = logging.getLogger(__name__)

MIN_PLACES = 8  # fewer than this and there is no day to build
NEAR_KM = 60.0  # a drafted place has to sit this close to the centre it came with
MAX_TOKENS = 8000


class ColdStartError(RuntimeError):
    """The model or the network let us down. create() turns it into a Verdict."""


class ColdStartReport(BaseModel):
    city: str
    drafted_places: int = 0
    drafted_paragraphs: int = 0
    seconds: float = 0.0
    cost_usd: float = 0.0
    poi_count: int = 0  # rows in the city after the call, drafted or not
    centre: tuple[float, float] | None = None


PLACES_SYSTEM = (
    "You draft a table of real places for a travel planner. Real places only, "
    "that a traveller could visit this year; no hotels, no invented fees, no "
    "invented hours. If you are unsure of a fee, use 0; if unsure of closing "
    "days, use []; if unsure of hours, use 09:00 and 17:30. Answer with one JSON "
    "object and nothing else."
)


def places_prompt(city: str, *, want_places: bool) -> str:
    if not want_places:
        return (
            f"City: {city}, India.\n"
            'Return {"centre": {"lat": <float>, "lng": <float>, "name_kn": '
            "<the city name in Kannada script if it sits in a Kannada-speaking "
            'region, else null>}, "places": []}'
        )
    return (
        f"City: {city}, India.\n"
        'Return {"centre": {"lat": <float>, "lng": <float>, "name_kn": <Kannada '
        'name or null>}, "places": [20 to 25 objects]}.\n'
        "Each place object has exactly these keys: name (string), name_kn (string "
        "or null), category (one of "
        + ", ".join(sorted(CATEGORIES))
        + "), tags (list of short lowercase strings), typical_dwell_min (int), "
        'entry_fee_inr (int, per adult), opens ("HH:MM"), closes ("HH:MM"), '
        "closed_on (list of ISO weekdays 1=Mon..7=Sun), elderly_friendly (bool), "
        "popularity (int 1-5), lat (float), lng (float). Every place within 60 km "
        f"of the centre of {city}. Mix temples, monuments, museums, nature, "
        "viewpoints, markets, food and experiences."
    )


KATHA_SYSTEM = (
    "You write short spoken paragraphs about a city for a walking guide. Second "
    "person, plain words, short sentences, 80 to 130 words each. No marketing "
    "adjectives (no breathtaking, stunning, majestic, magnificent, iconic, "
    "vibrant, mesmerising, must-visit, nestled, picturesque, bustling, "
    "unforgettable, quaint, charming, hidden gem, rich cultural heritage). Facts "
    "you are not sure of are left out. A founding legend is told with the words "
    '"the story goes" and marked is_legend. Answer with one JSON object and '
    "nothing else."
)


def katha_prompt(city: str, places: list[str]) -> str:
    wanted = "\n".join(f"- {theme} at tier {tier}" for theme, tier in DRAFT_SHAPE)
    return (
        f"City: {city}, India. Known places there: {', '.join(places[:25]) or 'none'}.\n"
        'Return {"paragraphs": [12 objects]} with one object per line below, in '
        "this order, each with keys theme, tier, title (a short plain sentence, "
        "unique), body, is_legend (bool), leads_with (for worth_seeing: the name "
        "of the place the paragraph opens with, exactly as listed above; else "
        "null).\n"
        "Themes: identity = what the city is and why it exists; origins = how it "
        "began, the founding story or legend; rulers = the dynasties and eras that "
        "made it (tier 2 the essentials, tier 5 more); character = what it feels "
        "like today, streets, pace, people, sounds; food = what the city eats and "
        "where the tradition comes from; festivals = its festivals; worth_seeing = "
        "the places worth your time and why, two or three sentences each (tier 2 "
        "names the top three); practical = when to come, how many days, what to "
        "skip.\n" + wanted
    )


# --------------------------------------------------------------------------- #
# parsing and validation
# --------------------------------------------------------------------------- #


def _json_object(text: str) -> dict:
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    data = json.loads(text)
    if not isinstance(data, dict):
        raise TypeError("the model did not return a JSON object")
    return data


def _centre(data: dict) -> tuple[float, float, str | None]:
    c = data.get("centre") or {}
    lat, lng = float(c["lat"]), float(c["lng"])
    box = INDIA_BOX
    if not (box.lat_min <= lat <= box.lat_max and box.lng_min <= lng <= box.lng_max):
        raise ValueError("centre outside India")
    name_kn = c.get("name_kn")
    return lat, lng, str(name_kn) if name_kn else None


def valid_places(rows: list, centre: tuple[float, float]) -> list[dict]:
    """The rows that pass the seed rules, sit near the centre, and are new names."""
    seen: set[str] = set()
    out = []
    for raw in rows or []:
        if not isinstance(raw, dict):
            continue
        p = {**raw, "trust": "ai_generated"}
        p.setdefault("tags", [])
        p.setdefault("closed_on", [])
        p.setdefault("entry_fee_inr", 0)
        p.setdefault("popularity", 3)
        p.setdefault("elderly_friendly", True)
        if poi_problems(p, INDIA_BOX):
            continue
        key = str(p["name"]).strip().casefold()
        if key in seen:
            continue
        if haversine(centre[0], centre[1], float(p["lat"]), float(p["lng"])) > NEAR_KM:
            continue
        seen.add(key)
        out.append(p)
    return out


def _call(llm: Any, system: str, user: str) -> Completion:
    return llm(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        model=MODELS["draft_places"],
        temperature=0.0,
        json_mode=True,
        max_tokens=MAX_TOKENS,
    )


# --------------------------------------------------------------------------- #
# the database side
# --------------------------------------------------------------------------- #

INSERT_POI = """
INSERT INTO poi (name, name_kn, city, lat, lng, category, tags, typical_dwell_min,
                 entry_fee_inr, opens, closes, closed_on, elderly_friendly,
                 popularity, trust, source_url, last_verified)
VALUES (%(name)s, %(name_kn)s, %(city)s, %(lat)s, %(lng)s, %(category)s, %(tags)s,
        %(typical_dwell_min)s, %(entry_fee_inr)s, %(opens)s, %(closes)s,
        %(closed_on)s, %(elderly_friendly)s, %(popularity)s, 'ai_generated',
        NULL, NULL)
ON CONFLICT (name, city) DO NOTHING RETURNING id
"""
INSERT_CENTRE = (
    "INSERT INTO city_centre (name, lat, lng, name_kn, source) "
    "VALUES (%s, %s, %s, %s, 'ai_generated') ON CONFLICT (name) DO NOTHING"
)
INSERT_CHUNK = """
INSERT INTO doc_chunk (poi_id, city, title, body, chunk_type, is_legend, lang,
                       source_name, source_url, last_verified, aliases, retired,
                       theme, tier, embedding)
VALUES (%(poi_id)s, %(city)s, %(title)s, %(body)s, %(chunk_type)s, %(is_legend)s,
        'en', 'ai_generated', NULL, NULL, %(aliases)s, false, %(theme)s, %(tier)s,
        %(embedding)s::vector)
ON CONFLICT (city, title) DO NOTHING
"""


def poi_count(conn: Any, city: str) -> int:
    row = conn.execute("SELECT count(*) FROM poi WHERE city = %s", (city,)).fetchone()
    return int(row[0]) if row else 0


def has_centre(conn: Any, city: str) -> bool:
    return (
        conn.execute("SELECT 1 FROM city_centre WHERE name = %s", (city,)).fetchone()
        is not None
    )


def city_layer_count(conn: Any, city: str) -> int:
    row = conn.execute(
        "SELECT count(*) FROM doc_chunk WHERE city = %s AND theme IS NOT NULL AND NOT retired",
        (city,),
    ).fetchone()
    return int(row[0]) if row else 0


def _clock(value: Any) -> time | None:
    return time.fromisoformat(str(value)) if value else None


def insert_places(conn: Any, city: str, places: list[dict]) -> list[tuple[int, str]]:
    """(id, name) of every row that landed. A name already in the city is skipped."""
    landed = []
    for p in places:
        row = conn.execute(
            INSERT_POI,
            {
                "name": str(p["name"]).strip(),
                "name_kn": p.get("name_kn") or None,
                "city": city,
                "lat": float(p["lat"]),
                "lng": float(p["lng"]),
                "category": p["category"],
                "tags": [str(t) for t in p.get("tags", [])][:8],
                "typical_dwell_min": int(p["typical_dwell_min"]),
                "entry_fee_inr": int(p.get("entry_fee_inr", 0)),
                "opens": _clock(p.get("opens")),
                "closes": _clock(p.get("closes")),
                "closed_on": [int(d) for d in p.get("closed_on", [])],
                "elderly_friendly": bool(p.get("elderly_friendly", True)),
                "popularity": int(p.get("popularity", 3)),
            },
        ).fetchone()
        if row:
            landed.append((int(row[0]), str(p["name"]).strip()))
    return landed


def _vector(values: Any) -> str:
    return "[" + ",".join(f"{float(x):.6f}" for x in values) + "]"


def ensure_city_layer(
    conn: Any, city: str, *, llm: Any = complete, places: list[str] | None = None
) -> tuple[int, float]:
    """Draft the Katha city layer once. (paragraphs inserted, cost in USD).

    Raises on any model, network or shape problem; callers decide whether that
    is fatal. It never is for a trip.
    """
    if city_layer_count(conn, city):
        return 0, 0.0
    if places is None:
        places = [
            r[0]
            for r in conn.execute(
                "SELECT name FROM poi WHERE city = %s ORDER BY popularity DESC NULLS LAST, id LIMIT 25",
                (city,),
            ).fetchall()
        ]
    done = _call(llm, KATHA_SYSTEM, katha_prompt(city, places))
    data = _json_object(done.text)
    wanted = list(DRAFT_SHAPE)
    rows = []
    titles: set[str] = set()
    for item in data.get("paragraphs") or []:
        if not isinstance(item, dict):
            continue
        pair = (str(item.get("theme")), int(item.get("tier") or 0))
        title, body = (
            str(item.get("title") or "").strip(),
            str(item.get("body") or "").strip(),
        )
        words = len(body.split())
        if pair not in wanted or not title or title in titles or not 60 <= words <= 160:
            continue
        wanted.remove(pair)
        titles.add(title)
        rows.append(
            {
                "theme": pair[0],
                "tier": pair[1],
                "title": title,
                "body": body,
                "is_legend": bool(item.get("is_legend")) and pair[0] == "origins",
                "leads_with": item.get("leads_with"),
            }
        )
    if len(rows) < 8:
        raise ValueError(f"only {len(rows)} usable paragraphs came back for {city}")

    from app.rag.embed import CITY_KN, chunk_text, embed_passages

    by_name = {
        str(r[1]).strip().casefold(): int(r[0])
        for r in conn.execute(
            "SELECT id, name FROM poi WHERE city = %s", (city,)
        ).fetchall()
    }
    texts = [
        chunk_text(r["title"], r["body"], [city, CITY_KN.get(city, "")]) for r in rows
    ]
    vectors = embed_passages(texts)
    for r, vec in zip(rows, vectors, strict=True):
        lead = str(r["leads_with"] or "").strip().casefold()
        conn.execute(
            INSERT_CHUNK,
            {
                "poi_id": by_name.get(lead) if r["theme"] == "worth_seeing" else None,
                "city": city,
                "title": r["title"],
                "body": r["body"],
                "chunk_type": THEME_CHUNK_TYPE[r["theme"]],
                "is_legend": r["is_legend"],
                "aliases": city,
                "theme": r["theme"],
                "tier": r["tier"],
                "embedding": _vector(vec),
            },
        )
    return len(rows), float(done.cost_usd or 0.0)


def ensure_city(
    conn: Any, city: str, *, need_places: bool, llm: Any = complete
) -> ColdStartReport:
    """Make sure the planner can work with `city`. Drafts once, then finds the rows.

    need_places=True (a destination): the centre and 20-25 places, then the
    Katha city layer, fail-soft. need_places=False (the origin): the centre only.
    Raises ColdStartError when the model or the network fails.
    """
    started = perf_counter()
    count = poi_count(conn, city)
    report = ColdStartReport(city=city, poi_count=count)
    if count >= MIN_PLACES or (not need_places and has_centre(conn, city)):
        return report
    try:
        done = _call(llm, PLACES_SYSTEM, places_prompt(city, want_places=need_places))
        data = _json_object(done.text)
        lat, lng, name_kn = _centre(data)
    except Exception as exc:  # httpx, json, KeyError, ValueError: one honest verdict
        raise ColdStartError(f"could not draft {city}: {exc}") from exc
    report.cost_usd = float(done.cost_usd or 0.0)
    report.centre = (lat, lng)
    conn.execute(INSERT_CENTRE, (city, lat, lng, name_kn))
    latency = done.latency_ms
    if need_places:
        landed = insert_places(conn, city, valid_places(data.get("places"), (lat, lng)))
        report.drafted_places = len(landed)
        report.poi_count = count + len(landed)
        if report.poi_count >= MIN_PLACES:
            try:
                n, cost = ensure_city_layer(
                    conn, city, llm=llm, places=[n for _, n in landed]
                )
                report.drafted_paragraphs = n
                report.cost_usd += cost
            except (
                ValueError,
                TypeError,
                KeyError,
                RuntimeError,
                httpx.HTTPError,
            ) as exc:
                # fail-soft: the trip still plans
                log.warning("cold start %s: no Katha layer (%s)", city, exc)
    report.seconds = round(perf_counter() - started, 1)
    log.info(
        "cold start %s: %d places, %d paragraphs, %.1fs, cost_usd=%.5f latency_ms=%d",
        city,
        report.drafted_places,
        report.drafted_paragraphs,
        report.seconds,
        report.cost_usd,
        latency,
    )
    return report

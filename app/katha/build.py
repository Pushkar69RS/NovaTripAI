"""Katha assembly. No creativity in this file; it is scheduling.

    uv run python -m app.katha.build --demo

A Katha is a spoken walk of a fixed length. The word budget comes from the
duration, the spine comes from the scope (themes within a place, top places in
a city, the stops of a day), the budget is split across the spine by
popularity, and each spine item is filled from retrieval with the ids already
used carried forward so no paragraph repeats. The rhythm rules are enforced in
`arrange` and checked again in `check_rhythm`, which the tests call directly.

Retrieval and the catalogue are passed in, so the whole builder runs against an
in-memory corpus in the tests and against Postgres in the API.
"""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Callable
from typing import Any, Protocol

from app.katha.city_layer import THEME_ORDER, label_for
from app.rag.retrieve import Filters, Hit

from .models import Depth, Katha, Scope, Segment, SourceChunk, SourceRef, SpineItem

WORDS_PER_MIN = 145
MIN_WORDS = 90
OPENERS = {"hook", "story"}
LONG_KATHA_MIN = 5  # from here on, a story and a taste or sensory are required
DEEP_STRETCH = 1.3  # a deep segment may run this far past its share
FILL_TO = 0.85  # keep adding paragraphs until this share of the budget is spoken
RETRIEVE_K = 12

#: How much each type is favoured, by depth. Added to the retrieval score.
FAVOUR: dict[str, dict[str, float]] = {
    "quick": {
        "hook": 0.05,
        "story": 0.05,
        "taste": 0.04,
        "sensory": 0.015,
        "fact": 0.01,
        "practical": 0.0,
    },
    "deep": {
        "hook": 0.02,
        "story": 0.04,
        "taste": 0.02,
        "sensory": 0.045,
        "fact": 0.045,
        "practical": 0.025,
    },
}

#: Themes within one place. quick takes the first five, deep all seven.
PLACE_THEMES: list[tuple[str, str]] = [
    ("why it matters", "what happened here and why it matters"),
    ("the story", "the legend or story told about this place"),
    ("who built it", "who built it, when, and what it cost"),
    ("where to stand", "where to stand and what to look at"),
    ("what to eat", "what to eat here and nearby"),
    ("before you go", "timings, fees, shoes, what to skip"),
    ("what survived", "what was destroyed, what changed, what survived"),
]


def places_for(duration_min: int) -> int:
    """How many places a city Katha can carry: 2 min -> 2, 5 -> 4, 10 -> 6."""
    if duration_min <= 3:
        return 2
    if duration_min <= 7:
        return 4
    return 6


class Catalogue(Protocol):
    """What the builder needs to know about places, trips and the city layer."""

    def poi(self, poi_id: int) -> dict[str, Any] | None: ...

    def top_pois(self, city: str, n: int) -> list[dict[str, Any]]: ...

    def day_stops(self, trip_id: str, day_index: int) -> tuple[str, list[dict]]: ...

    def city_layer(self, city: str) -> list[dict[str, Any]]:
        """The themed paragraphs about the city itself, in theme order, then
        tier, then id. Keys: id, poi_id, poi_name, title, body, chunk_type,
        is_legend, source_name, source_url, theme, tier."""
        ...


Retriever = Callable[[str, Filters], list[Hit]]


# --------------------------------------------------------------------------- #
# spine and budget
# --------------------------------------------------------------------------- #


def spine_for(
    scope: Scope,
    duration_min: int,
    depth: Depth,
    catalogue: Catalogue,
    trip_id: str | None,
) -> list[SpineItem]:
    if scope.kind == "place":
        poi = catalogue.poi(int(scope.id))
        if poi is None:
            raise ValueError(f"no place with id {scope.id}")
        themes = PLACE_THEMES[:5] if depth == "quick" else PLACE_THEMES
        return [
            SpineItem(
                label=f"{poi['name']}: {label}",
                query=f"{query} {poi['name']}",
                poi_id=poi["id"],
                city=poi["city"],
                weight=1.0,
            )
            for label, query in themes
        ]

    if scope.kind == "city":
        city = str(scope.id)
        places = catalogue.top_pois(city, places_for(duration_min))
        if not places:
            raise ValueError(f"no places known in {city}")
    else:
        if trip_id is None:
            raise ValueError("a day Katha needs a trip_id")
        city, places = catalogue.day_stops(trip_id, int(scope.id))
        if not places:
            raise ValueError(f"day {scope.id} of trip {trip_id} has no stops")

    # A city or a day opens on the city itself, so the first segment can be a
    # city-level hook rather than a fact about the first stop.
    opener = SpineItem(
        label=f"{city}: opening",
        query=f"why {city} matters, the story of {city}",
        poi_id=None,
        city=city,
        weight=0.6,
    )
    return [opener] + [
        SpineItem(
            label=p["name"],
            query=f"{p['name']} {city}",
            poi_id=p["id"],
            city=city,
            weight=float(p.get("popularity") or 3),
        )
        for p in places
    ]


def split_budget(items: list[SpineItem], budget: int) -> list[SpineItem]:
    """Share the budget by weight, at least MIN_WORDS each; drop the tail if not."""
    items = list(items)
    while items and MIN_WORDS * len(items) > budget and len(items) > 1:
        items.pop()  # the least popular came last
    total = sum(i.weight for i in items)
    for item in items:
        item.words = max(MIN_WORDS, round(budget * item.weight / total))
    # squeeze the largest until the sum fits, never below the floor
    while sum(i.words for i in items) > budget:
        biggest = max(items, key=lambda i: i.words)
        if biggest.words <= MIN_WORDS:
            break
        biggest.words -= 5
    return items


# --------------------------------------------------------------------------- #
# arrangement and the rhythm rules
# --------------------------------------------------------------------------- #


def _segment(hit: Hit, item: SpineItem) -> Segment:
    # A thin place borrows city-level paragraphs; say so rather than filing a
    # wrestling story under the zoo.
    label = (
        item.label if hit.poi_id == item.poi_id or item.poi_id is None else item.city
    )
    return Segment(
        title=hit.title or label,
        chunk_type=hit.chunk_type,
        is_legend=hit.is_legend,
        body_source_chunks=[
            SourceChunk(
                id=hit.id,
                title=hit.title,
                body=hit.body,
                chunk_type=hit.chunk_type,
                is_legend=hit.is_legend,
            )
        ],
        sources=[SourceRef(name=hit.source_name, url=hit.source_url)],
        text=hit.body,
        words=len(hit.body.split()),
        spine_item=label,
    )


def _best(
    candidates: list[Hit], depth: Depth, previous: str | None, first: bool
) -> Hit | None:
    # A Katha opens on a hook or a story when one exists; after that the best
    # paragraph wins, whatever came before it.
    allowed = [h for h in candidates if not first or h.chunk_type in OPENERS]
    if not allowed and first:
        allowed = list(candidates)
    if not allowed:
        return None
    return max(allowed, key=lambda h: h.score + FAVOUR[depth][h.chunk_type])


def _fits(segments: list[Segment], position: int, chunk_type: str) -> bool:
    """Only the opener is protected: nothing but a hook or a story goes first."""
    return position != 0 or not segments or chunk_type in OPENERS


def arrange(
    pools: list[list[Hit]], items: list[SpineItem], depth: Depth, duration_min: int
) -> list[Segment]:
    """Pick segments item by item, honouring every rhythm rule as it goes."""
    segments: list[Segment] = []
    used: set[int] = set()

    for item, pool in zip(items, pools, strict=True):
        filled = 0
        stretch = DEEP_STRETCH if depth == "deep" else 1.0
        candidates = [h for h in pool if h.id not in used]
        while filled < item.words and candidates:
            previous = segments[-1].chunk_type if segments else None
            pick = _best(candidates, depth, previous, first=not segments)
            if pick is None:
                break
            if segments and filled + len(pick.body.split()) > item.words * stretch:
                # this one would overrun; a shorter candidate may still fit
                candidates.remove(pick)
                continue
            segments.append(_segment(pick, item))
            used.add(pick.id)
            filled += len(pick.body.split())
            candidates.remove(pick)

    # Second pass: the shares round to about one paragraph each, so a Katha can
    # come up well short of its minutes. Keep adding, most popular item first,
    # until it is close to budget or the pools run dry.
    budget = duration_min * WORDS_PER_MIN
    order = sorted(range(len(items)), key=lambda i: -items[i].weight)
    added = True
    while added and sum(s.words for s in segments) < budget * FILL_TO:
        added = False
        for n in order:
            item, pool = items[n], pools[n]
            candidates = [h for h in pool if h.id not in used]
            after = max(
                (p for p, s in enumerate(segments) if s.spine_item == item.label),
                default=len(segments) - 1,
            )
            position = after + 1
            ranked = sorted(
                candidates, key=lambda h: -(h.score + FAVOUR[depth][h.chunk_type])
            )
            for hit in ranked:
                if _fits(segments, position, hit.chunk_type):
                    segments.insert(position, _segment(hit, item))
                    used.add(hit.id)
                    added = True
                    break
            if sum(s.words for s in segments) >= budget * FILL_TO:
                break

    if duration_min >= LONG_KATHA_MIN:
        spare = [h for pool in pools for h in pool if h.id not in used]
        for needed in ({"story"},):
            if any(s.chunk_type in needed for s in segments):
                continue
            for hit in sorted(spare, key=lambda h: -h.score):
                if hit.chunk_type not in needed:
                    continue
                positions = [
                    p
                    for p in range(len(segments) + 1)
                    if _fits(segments, p, hit.chunk_type)
                ]
                if positions:
                    item = next(
                        (
                            i
                            for i, pool in zip(items, pools, strict=True)
                            if hit in pool
                        ),
                        items[0],
                    )
                    segments.insert(positions[-1], _segment(hit, item))
                    used.add(hit.id)
                    break
    return segments


def check_rhythm(segments: list[Segment], duration_min: int) -> list[str]:
    """Every rhythm rule a place or day Katha breaks. Empty means it holds.

    Three rules: a paragraph never repeats; the Katha opens on a hook or a
    story when it has one; five minutes or more carry at least one story.
    """
    problems: list[str] = []
    if not segments:
        return ["empty"]
    types = {s.chunk_type for s in segments}
    if segments[0].chunk_type not in OPENERS and types & OPENERS:
        problems.append(f"opens on {segments[0].chunk_type}, not hook or story")
    ids = [c.id for s in segments for c in s.body_source_chunks]
    if len(ids) != len(set(ids)):
        problems.append("a paragraph repeats")
    if duration_min >= LONG_KATHA_MIN and "story" not in types:
        problems.append("no story in a long Katha")
    return problems


# --------------------------------------------------------------------------- #
# the city Katha: a fixed portrait, no retrieval
# --------------------------------------------------------------------------- #


def city_katha(
    city: str,
    duration_min: int,
    depth: Depth,
    language: str,
    *,
    catalogue: Catalogue,
) -> Katha | None:
    """Every city-layer paragraph whose tier fits the minutes, in theme order.

    The same city and minutes always give the same Katha in the same order:
    no retrieval, no FAVOUR, no rhythm rules, and depth is ignored. None when
    the city has no layer yet.
    """
    rows = [
        r for r in catalogue.city_layer(city) if (r.get("tier") or 99) <= duration_min
    ]
    if not rows:
        return None
    segments = []
    for r in rows:
        label = label_for(r["theme"], city)
        segments.append(
            Segment(
                title=label,
                chunk_type=r["chunk_type"],
                is_legend=bool(r["is_legend"]),
                body_source_chunks=[
                    SourceChunk(
                        id=r["id"],
                        title=r["title"],
                        body=r["body"],
                        chunk_type=r["chunk_type"],
                        is_legend=bool(r["is_legend"]),
                    )
                ],
                sources=[SourceRef(name=r.get("source_name"), url=r.get("source_url"))],
                text=r["body"],
                words=len(r["body"].split()),
                # a worth_seeing paragraph is filed under the place it opens
                # with, so the locator pin and "Go deeper" resolve
                spine_item=r.get("poi_name") or label,
                theme=r["theme"],
            )
        )
    return Katha(
        scope=Scope(kind="city", id=city),
        duration_min=duration_min,
        depth=depth,
        language=language,
        segments=segments,
        total_words=sum(s.words for s in segments),
        spine=[],
        type_sequence=[s.chunk_type for s in segments],
    )


# --------------------------------------------------------------------------- #
# the builder
# --------------------------------------------------------------------------- #


def build(
    scope: Scope,
    duration_min: int,
    depth: Depth,
    language: str,
    trip_id: str | None = None,
    *,
    catalogue: Catalogue,
    retriever: Retriever,
    drafter: Callable[[str], object] | None = None,
) -> Katha:
    note = None
    if scope.kind == "city":
        city = str(scope.id)
        katha = city_katha(city, duration_min, depth, language, catalogue=catalogue)
        if katha is None and drafter is not None:
            drafter(city)  # the cold-start drafter; it swallows its own errors
            katha = city_katha(city, duration_min, depth, language, catalogue=catalogue)
        if katha is not None:
            return katha
        note = (
            f"We have nothing written about {city} as a city yet; "
            "here is what we have on its places."
        )
    budget = duration_min * WORDS_PER_MIN
    items = split_budget(
        spine_for(scope, duration_min, depth, catalogue, trip_id), budget
    )

    pools: list[list[Hit]] = []
    seen: list[int] = []
    for item in items:
        filters = Filters(city=item.city, exclude_ids=list(seen))
        if item.poi_id is not None:
            filters.poi_id = item.poi_id
        hits = retriever(item.query, filters)
        if len(hits) < 3 and item.poi_id is not None:
            # a thin place: borrow city-level paragraphs, never another place's
            hits += [
                h
                for h in retriever(
                    item.query, Filters(city=item.city, exclude_ids=list(seen))
                )
                if h.id not in {x.id for x in hits} and h.poi_id is None
            ]
        pools.append(hits)
        seen.extend(h.id for h in hits)  # over-fetch is fine; the next item digs deeper

    segments = arrange(pools, items, depth, duration_min)
    total = sum(s.words for s in segments)
    if total < budget * FILL_TO:
        # short of words: one more round, city-wide, past everything seen so far
        used = {c.id for s in segments for c in s.body_source_chunks}
        extra = retriever(
            items[0].query, Filters(city=items[0].city, exclude_ids=list(seen))
        )
        extra_item = SpineItem(
            label=f"{items[0].city}: more",
            query=items[0].query,
            poi_id=None,
            city=items[0].city,
            weight=1.0,
            words=budget - total,
        )
        pools.append([h for h in extra if h.id not in used])
        items.append(extra_item)
        segments = arrange(pools, items, depth, duration_min)

    problems = check_rhythm(segments, duration_min)
    if problems:
        raise RuntimeError(f"rhythm rules broken: {problems}")
    return Katha(
        scope=scope,
        duration_min=duration_min,
        depth=depth,
        language=language,
        segments=segments,
        total_words=sum(s.words for s in segments),
        spine=items,
        type_sequence=[s.chunk_type for s in segments],
        note=note,
    )


# --------------------------------------------------------------------------- #
# Postgres-backed catalogue and retriever
# --------------------------------------------------------------------------- #


class DbCatalogue:
    def __init__(self, db: Any) -> None:
        self.db = db

    def poi(self, poi_id: int) -> dict[str, Any] | None:
        row = self.db.execute(
            "SELECT id, name, name_kn, city, popularity FROM poi WHERE id = %s",
            (poi_id,),
        ).fetchone()
        return _poi(row) if row else None

    def top_pois(self, city: str, n: int) -> list[dict[str, Any]]:
        rows = self.db.execute(
            "SELECT p.id, p.name, p.name_kn, p.city, p.popularity FROM poi p "
            "WHERE p.city = %s AND EXISTS ("
            "  SELECT 1 FROM doc_chunk c WHERE c.poi_id = p.id AND NOT c.retired) "
            "ORDER BY p.popularity DESC NULLS LAST, p.id LIMIT %s",
            (city, n),
        ).fetchall()
        return [_poi(r) for r in rows]

    def day_stops(self, trip_id: str, day_index: int) -> tuple[str, list[dict]]:
        row = self.db.execute(
            "SELECT plan FROM trip WHERE id = %s", (trip_id,)
        ).fetchone()
        if not row or not row[0]:
            raise ValueError(f"trip {trip_id} has no plan")
        plan = row[0] if isinstance(row[0], dict) else json.loads(row[0])
        days = [d for d in plan["days"] if d["index"] == day_index]
        if not days:
            raise ValueError(f"trip {trip_id} has no day {day_index}")
        day = days[0]
        stops = [
            {"id": i["poi_id"], "name": i["name"], "popularity": 3}
            for i in day["items"]
            if i.get("kind") == "stop"
        ]
        return day["city"], stops

    def city_layer(self, city: str) -> list[dict[str, Any]]:
        rows = self.db.execute(
            "SELECT c.id, c.poi_id, p.name, c.title, c.body, c.chunk_type, "
            "c.is_legend, c.source_name, c.source_url, c.theme, c.tier "
            "FROM doc_chunk c LEFT JOIN poi p ON p.id = c.poi_id "
            "WHERE c.city = %s AND c.theme IS NOT NULL AND c.tier IS NOT NULL "
            "AND NOT c.retired "
            "ORDER BY array_position(%s::text[], c.theme), c.tier, c.id",
            (city, list(THEME_ORDER)),
        ).fetchall()
        return [
            {
                "id": r[0],
                "poi_id": r[1],
                "poi_name": r[2],
                "title": r[3],
                "body": r[4],
                "chunk_type": r[5],
                "is_legend": r[6],
                "source_name": r[7],
                "source_url": r[8],
                "theme": r[9],
                "tier": r[10],
            }
            for r in rows
        ]


def _poi(row: Any) -> dict[str, Any]:
    return {
        "id": row[0],
        "name": row[1],
        "name_kn": row[2],
        "city": row[3],
        "popularity": row[4],
    }


def db_retriever(db: Any) -> Retriever:
    from app.rag.retrieve import search

    return lambda query, filters: search(query, db, filters=filters, k=RETRIEVE_K)


def render(katha: Katha) -> str:
    lines = [
        (
            f"KATHA  {katha.scope.kind}={katha.scope.id}  {katha.duration_min} min  "
            f"{katha.depth}  {katha.language}  ->  {katha.total_words} words "
            f"(budget {katha.duration_min * WORDS_PER_MIN})"
        ),
        "spine: " + " | ".join(f"{i.label} ({i.words}w)" for i in katha.spine),
        "types: " + " -> ".join(katha.type_sequence),
        "",
    ]
    for n, s in enumerate(katha.segments, 1):
        legend = " (legend)" if s.is_legend else ""
        src = next((r.url or r.name for r in s.sources if r.url or r.name), "")
        lines.append(
            f"{n}. [{s.chunk_type}]{legend} {s.title}  <{s.spine_item}>  {s.words}w"
        )
        lines.append(f"   {s.text}")
        if src:
            lines.append(f"   source: {src}")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="build and print a Katha")
    parser.add_argument("--demo", action="store_true", help="5-minute Mysuru Katha")
    parser.add_argument("--minutes", type=int, default=5)
    parser.add_argument("--depth", default="quick", choices=("quick", "deep"))
    args = parser.parse_args()
    if not args.demo:
        parser.print_help()
        return 0

    import psycopg
    from dotenv import load_dotenv

    load_dotenv()
    with psycopg.connect(os.environ["SUPABASE_DB_URL"]) as conn:
        katha = build(
            Scope(kind="city", id="Mysuru"),
            args.minutes,
            args.depth,
            "en",
            catalogue=DbCatalogue(conn),
            retriever=db_retriever(conn),
        )
    print(render(katha))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

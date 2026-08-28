"""The Katha builder, run against the corpus files in memory. No database.

The retriever here scores by word overlap, which is crude, and that is the
point: the rhythm rules have to hold whatever retrieval hands the builder.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

import pytest

from app.katha.build import (
    MIN_WORDS,
    OPENERS,
    WORDS_PER_MIN,
    arrange,
    build,
    check_rhythm,
    split_budget,
)
from app.katha.city_layer import THEME_ORDER, theme_rank
from app.katha.models import Scope, Segment, SourceChunk, SpineItem
from app.rag.retrieve import Filters, Hit

ROOT = Path(__file__).resolve().parents[1]
POIS = json.loads((ROOT / "data" / "pois.json").read_text(encoding="utf-8"))["pois"]
POI_ID = {p["name"]: i for i, p in enumerate(POIS, 1)}
HUB = {"Srirangapatna": "Mysuru", "Belur": "Chikmagalur", "Halebidu": "Chikmagalur"}
ALIAS = {
    "Chamundi Hill": "Chamundeshwari Temple",
    "Daria Daulat Bagh": "Daria Daulat Bagh (Tipu Sultan's Summer Palace), Srirangapatna",
    "Vittala Temple": "Vittala Temple and Stone Chariot",
    "Chennakeshava Temple": "Chennakeshava Temple, Belur",
    "Hoysaleswara Temple": "Hoysaleswara Temple, Halebidu",
    "Bull Temple": "Bull Temple (Dodda Basavana Gudi)",
    "Mullayanagiri": "Mullayanagiri Peak",
}


def corpus() -> list[Hit]:
    curated = json.loads(
        (ROOT / "data" / "chunks_curated.json").read_text(encoding="utf-8")
    )["chunks"]
    generated = json.loads((ROOT / "data" / "chunks.json").read_text(encoding="utf-8"))[
        "chunks"
    ]
    hits = []
    for n, c in enumerate(curated + generated, 1):
        name = c.get("poi_name", c.get("poi"))
        name = ALIAS.get(name, name) if name else None
        hits.append(
            Hit(
                id=n,
                poi_id=POI_ID.get(name) if name else None,
                city=HUB.get(c["city"], c["city"]),
                title=c["title"],
                body=c["body"],
                chunk_type=c["chunk_type"],
                is_legend=bool(c["is_legend"]),
                source_name=c.get("source_name"),
                source_url=c.get("source_url"),
                score=0.0,
                retrievers=["dense"],
            )
        )
    return hits


CORPUS = corpus()
POI_NAME = {i: p["name"] for i, p in enumerate(POIS, 1)}


def city_layer_rows() -> list[dict]:
    """data/chunks_city.json the way seed_chunks.py lands it: new rows plus retags."""
    data = json.loads((ROOT / "data" / "chunks_city.json").read_text(encoding="utf-8"))
    by_key = {(h.city, h.title): h for h in CORPUS}
    rows = []
    for n, c in enumerate(data["chunks"], 1):
        if "body" in c:
            poi_id = POI_ID.get(c.get("poi")) if c.get("poi") else None
            rows.append(
                {
                    "id": 5000 + n,
                    "poi_id": poi_id,
                    "poi_name": POI_NAME.get(poi_id) if poi_id else None,
                    "city": c["city"],
                    "title": c["title"],
                    "body": c["body"],
                    "chunk_type": c["chunk_type"],
                    "is_legend": bool(c["is_legend"]),
                    "source_name": c.get("source_name"),
                    "source_url": c.get("source_url"),
                    "theme": c["theme"],
                    "tier": c["tier"],
                }
            )
        else:
            h = by_key[(c["city"], c["title"])]
            rows.append(
                {
                    "id": h.id,
                    "poi_id": h.poi_id,
                    "poi_name": POI_NAME.get(h.poi_id) if h.poi_id else None,
                    "city": h.city,
                    "title": h.title,
                    "body": h.body,
                    "chunk_type": h.chunk_type,
                    "is_legend": h.is_legend,
                    "source_name": h.source_name,
                    "source_url": h.source_url,
                    "theme": c["theme"],
                    "tier": c["tier"],
                }
            )
    return rows


CITY_LAYER = city_layer_rows()


def words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]+", text.lower()) if len(w) > 3}


def retriever(query: str, filters: Filters) -> list[Hit]:
    """Word overlap, filtered like the real thing, scored on the RRF scale."""
    q = words(query)
    out = []
    for h in CORPUS:
        if filters.city and h.city != filters.city:
            continue
        if filters.poi_id is not None and h.poi_id != filters.poi_id:
            continue
        if h.id in filters.exclude_ids:
            continue
        overlap = len(q & words(f"{h.title} {h.body}")) / max(1, len(q))
        out.append(h.model_copy(update={"score": round(0.016 * (0.5 + overlap), 6)}))
    return sorted(out, key=lambda h: (-h.score, h.id))[:12]


class MemoryCatalogue:
    def poi(self, poi_id: int):
        p = POIS[poi_id - 1]
        return {
            "id": poi_id,
            "name": p["name"],
            "city": p["city"],
            "popularity": p.get("popularity", 3),
        }

    def top_pois(self, city: str, n: int):
        with_chunks = {h.poi_id for h in CORPUS if h.poi_id}
        rows = [
            self.poi(i)
            for i, p in enumerate(POIS, 1)
            if p["city"] == city and i in with_chunks
        ]
        return sorted(rows, key=lambda r: (-r["popularity"], r["id"]))[:n]

    def day_stops(self, trip_id: str, day_index: int):
        return "Mysuru", [
            self.poi(POI_ID["Mysore Palace"]),
            self.poi(POI_ID["Devaraja Market"]),
        ]

    def city_layer(self, city: str):
        rows = [r for r in CITY_LAYER if r["city"] == city]
        return sorted(rows, key=lambda r: (theme_rank(r["theme"]), r["tier"], r["id"]))


class NoCityLayer(MemoryCatalogue):
    def city_layer(self, city: str):
        return []


CATALOGUE = MemoryCatalogue()


def make(scope: Scope, minutes: int, depth: str):
    return build(
        scope, minutes, depth, "en", "trip", catalogue=CATALOGUE, retriever=retriever
    )


# Place and day Kathas keep the retrieval path and the rhythm rules; the city
# Katha is a fixed portrait and is tested on its own below.
SCOPES = [
    Scope(kind="place", id=POI_ID["Mysore Palace"]),
    Scope(kind="place", id=POI_ID["Vittala Temple and Stone Chariot"]),
    Scope(kind="place", id=POI_ID["Chennakeshava Temple, Belur"]),
    Scope(kind="place", id=POI_ID["Virupaksha Temple"]),
    Scope(kind="place", id=POI_ID["Chamundeshwari Temple"]),
    Scope(kind="place", id=POI_ID["Hoysaleswara Temple, Halebidu"]),
    Scope(kind="day", id=1),
]
TWENTY = [
    (scope, minutes, depth)
    for scope in SCOPES
    for minutes, depth in ((2, "quick"), (5, "quick"), (10, "deep"))
][:20]
CITIES = ("Mysuru", "Hampi", "Bengaluru", "Chikmagalur", "Coorg")


# --------------------------------------------------------------------------- #
# rhythm: three rules
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(("scope", "minutes", "depth"), TWENTY)
def test_rhythm_rules_hold_across_twenty_kathas(scope, minutes, depth) -> None:
    katha = make(scope, minutes, depth)
    assert check_rhythm(katha.segments, minutes) == []
    ids = [c.id for s in katha.segments for c in s.body_source_chunks]
    assert len(ids) == len(set(ids))
    if {s.chunk_type for s in katha.segments} & OPENERS:
        assert katha.segments[0].chunk_type in OPENERS
    if minutes >= 5:
        assert "story" in {s.chunk_type for s in katha.segments}


def test_no_chunk_repeats_within_one_katha() -> None:
    katha = make(Scope(kind="place", id=POI_ID["Mysore Palace"]), 10, "deep")
    ids = [c.id for s in katha.segments for c in s.body_source_chunks]
    assert len(ids) == len(set(ids))
    assert len(ids) >= 6


def test_a_two_minute_katha_is_meaningfully_shorter_than_a_ten_minute_one() -> None:
    short = make(Scope(kind="place", id=POI_ID["Mysore Palace"]), 2, "quick")
    long = make(Scope(kind="place", id=POI_ID["Mysore Palace"]), 10, "deep")
    assert short.total_words < long.total_words * 0.5
    assert short.total_words <= 2 * WORDS_PER_MIN * 1.35
    assert long.total_words >= 10 * WORDS_PER_MIN * 0.6
    assert len(short.spine) < len(long.spine)


# --------------------------------------------------------------------------- #
# the city Katha: a fixed portrait
# --------------------------------------------------------------------------- #


def ids_of(katha) -> list[int]:
    return [c.id for s in katha.segments for c in s.body_source_chunks]


@pytest.mark.parametrize("city", CITIES)
def test_the_same_city_and_minutes_give_the_same_katha_twice(city) -> None:
    once, twice = (
        make(Scope(kind="city", id=city), 5, "quick"),
        make(Scope(kind="city", id=city), 5, "deep"),
    )
    assert ids_of(once) == ids_of(twice)  # depth is ignored for a city
    assert once.spine == [] and once.note is None
    assert [s.theme for s in once.segments] == sorted(
        (s.theme for s in once.segments), key=theme_rank
    )


@pytest.mark.parametrize("city", CITIES)
def test_tier_two_within_five_within_ten(city) -> None:
    two = ids_of(make(Scope(kind="city", id=city), 2, "quick"))
    five = ids_of(make(Scope(kind="city", id=city), 5, "quick"))
    ten = ids_of(make(Scope(kind="city", id=city), 10, "quick"))
    assert set(two) < set(five) < set(ten)
    assert len(ten) == 14


@pytest.mark.parametrize("city", CITIES)
def test_a_two_minute_city_katha_is_identity_rulers_and_worth_seeing(city) -> None:
    themes = [s.theme for s in make(Scope(kind="city", id=city), 2, "quick").segments]
    assert {"identity", "rulers", "worth_seeing"} <= set(themes)
    assert set(themes) <= set(THEME_ORDER)  # never a monument-interior theme
    ten = make(Scope(kind="city", id=city), 10, "quick")
    assert {s.theme for s in ten.segments} == set(THEME_ORDER)
    lead = next(s for s in ten.segments if s.theme == "worth_seeing")
    assert lead.spine_item in POI_ID  # "Go deeper" resolves to the place it opens with


def test_a_city_with_no_layer_falls_back_to_the_places_and_says_so() -> None:
    katha = build(
        Scope(kind="city", id="Mysuru"),
        5,
        "quick",
        "en",
        catalogue=NoCityLayer(),
        retriever=retriever,
    )
    assert katha.note == (
        "We have nothing written about Mysuru as a city yet; "
        "here is what we have on its places."
    )
    assert katha.segments and all(s.theme is None for s in katha.segments)
    drafted = []
    katha = build(
        Scope(kind="city", id="Mysuru"),
        5,
        "quick",
        "en",
        catalogue=NoCityLayer(),
        retriever=retriever,
        drafter=lambda city: drafted.append(city),
    )
    assert drafted == ["Mysuru"] and katha.note  # the drafter was tried first


def test_depth_changes_the_mix() -> None:
    quick = make(Scope(kind="place", id=POI_ID["Mysore Palace"]), 5, "quick")
    deep = make(Scope(kind="place", id=POI_ID["Mysore Palace"]), 5, "deep")
    q, d = Counter(quick.type_sequence), Counter(deep.type_sequence)
    assert len(deep.spine) > len(quick.spine)  # seven themes against five
    assert d["fact"] + d["sensory"] >= q["fact"] + q["sensory"]


def test_check_rhythm_names_every_broken_rule() -> None:
    def seg(kind: str, n: int) -> Segment:
        return Segment(
            title=f"t{n}",
            chunk_type=kind,
            is_legend=False,
            body_source_chunks=[
                SourceChunk(
                    id=n, title=None, body="x", chunk_type=kind, is_legend=False
                )
            ],
            sources=[],
            text="x",
            words=1,
            spine_item="s",
        )

    bad = [seg("fact", 1), seg("hook", 2), seg("fact", 1)]
    problems = check_rhythm(bad, 5)
    assert any("opens on fact" in p for p in problems)  # a hook exists, later
    assert any("repeats" in p for p in problems)
    assert any("no story" in p for p in problems)
    assert not any("adjacent" in p or "taste" in p for p in problems)
    assert check_rhythm([seg("hook", 1), seg("story", 2), seg("taste", 3)], 5) == []
    # two facts in a row are fine; with no hook or story anywhere, a fact may open
    assert check_rhythm([seg("fact", 1), seg("fact", 2), seg("practical", 3)], 5) == [
        "no story in a long Katha"
    ]
    assert check_rhythm([seg("fact", 1), seg("fact", 2)], 2) == []


def test_split_budget_respects_the_floor_and_the_cap() -> None:
    items = [
        SpineItem(label=str(i), query="q", poi_id=None, city="Mysuru", weight=w)
        for i, w in enumerate((5.0, 4.0, 3.0, 1.0))
    ]
    out = split_budget(items, 2 * WORDS_PER_MIN)
    assert all(i.words >= MIN_WORDS for i in out)
    assert sum(i.words for i in out) <= 2 * WORDS_PER_MIN
    assert len(out) <= 3  # 290 words cannot pay four items 90 each


def test_arrange_never_opens_on_a_fact_when_a_hook_exists() -> None:
    item = SpineItem(
        label="x", query="q", poi_id=None, city="Mysuru", weight=1, words=300
    )
    pool = retriever("Mysore Palace", Filters(city="Mysuru"))
    segments = arrange([pool], [item], "quick", 2)
    assert segments[0].chunk_type in OPENERS

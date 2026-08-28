"""Offline validation of data/pois.json (no database)."""

import json
from pathlib import Path

from app.planner.poi_rules import INDIA_BOX, KARNATAKA_BOX, poi_problems

DATA = json.loads(
    (Path(__file__).resolve().parents[1] / "data" / "pois.json").read_text(
        encoding="utf-8"
    )
)
POIS = DATA["pois"]
CATEGORIES = {
    "temple",
    "monument",
    "museum",
    "nature",
    "viewpoint",
    "market",
    "food",
    "experience",
}
RELATIONS = {"same_dynasty", "same_style", "pairs_well_with", "nearby"}
MODES = {"car", "bus", "train"}


def test_counts() -> None:
    assert 100 <= len(POIS) <= 115
    assert len(DATA["edges"]) >= 30
    assert len(DATA["intercity_legs"]) >= 10


def test_poi_fields() -> None:
    # The same rule set the cold start applies, against the Karnataka box.
    for p in POIS:
        assert poi_problems(p, KARNATAKA_BOX) == [], p["name"]
        assert p["category"] in CATEGORIES, p["name"]
        assert p.get("trust", "draft") in {"verified", "draft"}, p["name"]


def test_the_rules_catch_a_bad_row() -> None:
    good = {
        "name": "X",
        "lat": 12.9,
        "lng": 74.8,
        "category": "temple",
        "typical_dwell_min": 45,
        "opens": "09:00",
        "closes": "17:30",
    }
    assert poi_problems(good, KARNATAKA_BOX) == []
    assert poi_problems({**good, "lat": 28.6}, KARNATAKA_BOX) == ["outside the box"]
    assert poi_problems({**good, "lat": 28.6}, INDIA_BOX) == []
    assert "unknown category" in poi_problems({**good, "category": "hotel"}, INDIA_BOX)
    assert "opens is not HH:MM" in poi_problems({**good, "opens": "9am"}, INDIA_BOX)
    assert "closed_on must be ISO weekdays" in poi_problems(
        {**good, "closed_on": [0, 8]}, INDIA_BOX
    )


def test_no_duplicate_name_city() -> None:
    pairs = [(p["name"], p["city"]) for p in POIS]
    assert len(pairs) == len(set(pairs))
    names = [p["name"] for p in POIS]
    assert len(names) == len(set(names))  # edges reference POIs by bare name


def test_edges_and_legs_reference_known_things() -> None:
    names = {p["name"] for p in POIS}
    cities = {p["city"] for p in POIS}
    for e in DATA["edges"]:
        assert e["from"] in names and e["to"] in names, e
        assert e["relation"] in RELATIONS, e
    for leg in DATA["intercity_legs"]:
        assert leg["from"] in cities and leg["to"] in cities, leg
        assert leg["mode"] in MODES and leg["duration_min"] > 0, leg

"""Offline validation of data/pois.json (no database)."""

import json
from pathlib import Path

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
    for p in POIS:
        assert 11.5 <= p["lat"] <= 18.5, p["name"]
        assert 74.0 <= p["lng"] <= 78.6, p["name"]
        assert p["typical_dwell_min"] > 0, p["name"]
        assert p["category"] in CATEGORIES, p["name"]
        assert set(p.get("closed_on", [])) <= set(range(1, 8)), p["name"]
        assert 1 <= p.get("popularity", 3) <= 5, p["name"]
        assert p.get("entry_fee_inr", 0) >= 0, p["name"]
        assert p.get("trust", "draft") in {"verified", "draft"}, p["name"]
        if p.get("opens") and p.get("closes"):
            assert p["opens"] < p["closes"], p[
                "name"
            ]  # "HH:MM" strings compare correctly


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

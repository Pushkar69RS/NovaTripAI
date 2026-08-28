"""The rules a place row has to pass, whoever wrote it.

tests/test_seed_data.py checks data/pois.json against the Karnataka box; the
cold start checks a model's draft against the India box. Same rules, one
function, so the two can never drift apart.
"""

from __future__ import annotations

import re
from typing import NamedTuple

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
TRUSTS = {"verified", "draft", "ai_generated"}
HOURS = re.compile(r"^\d{2}:\d{2}$")


class Box(NamedTuple):
    lat_min: float
    lat_max: float
    lng_min: float
    lng_max: float


KARNATAKA_BOX = Box(11.5, 18.5, 74.0, 78.6)
INDIA_BOX = Box(6.0, 37.0, 68.0, 98.0)


def poi_problems(p: dict, box: Box) -> list[str]:
    """Every rule the row breaks. Empty means it can be inserted."""
    out: list[str] = []
    name = str(p.get("name") or "").strip()
    if not name:
        out.append("no name")
    try:
        lat, lng = float(p["lat"]), float(p["lng"])
    except (KeyError, TypeError, ValueError):
        out.append("lat/lng missing")
    else:
        if not (
            box.lat_min <= lat <= box.lat_max and box.lng_min <= lng <= box.lng_max
        ):
            out.append("outside the box")
    if not isinstance(p.get("typical_dwell_min"), int) or p["typical_dwell_min"] <= 0:
        out.append("dwell must be a positive int")
    if p.get("category") not in CATEGORIES:
        out.append("unknown category")
    closed = p.get("closed_on", [])
    if not isinstance(closed, list) or not set(closed) <= set(range(1, 8)):
        out.append("closed_on must be ISO weekdays")
    if not 1 <= p.get("popularity", 3) <= 5:
        out.append("popularity 1-5")
    fee = p.get("entry_fee_inr", 0)
    if not isinstance(fee, int) or fee < 0:
        out.append("fee must be a non-negative int")
    if p.get("trust", "draft") not in TRUSTS:
        out.append("unknown trust")
    opens, closes = p.get("opens"), p.get("closes")
    for label, value in (("opens", opens), ("closes", closes)):
        if value and not HOURS.match(str(value)):
            out.append(f"{label} is not HH:MM")
    both = opens and closes and HOURS.match(str(opens)) and HOURS.match(str(closes))
    if both and not opens < closes:
        out.append("opens after closes")
    tags = p.get("tags", [])
    if not isinstance(tags, list) or not all(isinstance(t, str) for t in tags):
        out.append("tags must be strings")
    return out

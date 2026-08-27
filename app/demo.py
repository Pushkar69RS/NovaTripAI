"""What makes the review demo deterministic: one canonical trip, two cached Kathas.

The canonical trip is the one the landing page draws and scripts/demo_seed.py
creates. The cached Kathas are what scripts/warm_tts.py left in var/tts/: when
a freshly built Katha is made of the same paragraphs in the same order, its
narration and audio are served from disk and nothing goes over the network.
"""

from __future__ import annotations

import json
from datetime import date, time
from typing import Any

from app.katha.models import Katha
from app.planner.models import TripRequest
from app.voice.tts import CACHE_DIR

DEMO_REQUEST = TripRequest(
    origin_city="Bengaluru",
    destination_cities=["Mysuru", "Srirangapatna"],
    start_date=date(2026, 9, 14),
    days=3,
    party_size=4,  # 2 adults + 1 elder + 1 child
    has_elderly=True,
    has_children=True,
    pace="comfortable",
    budget_inr=18000,
    transport="train",
    interest_tags=["heritage", "food"],
    notes="Amma tires by evening. And one really good breakfast, please.",
    day_one_start=time(9, 0),
    day_end=time(19, 0),
    preferences={
        "adults": "2",
        "elders": "1",
        "children": "1",
        "children_ages": "5–12",
        "walking": "Someone finds stairs hard",
        "mornings": "Easy mornings, please",
        "food": "No preference",
        "budget_covers": "Stay, Food, Tickets, Getting around",
        "stay": "Mid-range",
        "getting_around": "Hired car / cab",
        "must_see": "Mysore Palace",
    },
)

#: The fields that identify the canonical trip in the `trip` table.
DEMO_KEY = {
    "origin_city": DEMO_REQUEST.origin_city,
    "places": DEMO_REQUEST.places,
    "start_date": DEMO_REQUEST.start_date.isoformat(),
    "days": DEMO_REQUEST.days,
    "party_size": DEMO_REQUEST.party_size,
    "budget_inr": DEMO_REQUEST.budget_inr,
    "notes": DEMO_REQUEST.notes,
}


def find_demo_trip(conn: Any) -> str | None:
    """The canonical trip's id, or None when demo_seed.py has not run."""
    row = conn.execute(
        "SELECT id FROM trip WHERE status = 'planned' AND request @> %s::jsonb "
        "ORDER BY created_at LIMIT 1",
        (json.dumps(DEMO_KEY),),
    ).fetchone()
    return str(row[0]) if row else None


def _chunk_ids(segments: list[dict]) -> list[int]:
    return [c["id"] for s in segments for c in s["body_source_chunks"]]


def cached_demo(katha: Katha) -> dict | None:
    """The warm_tts record whose paragraphs, order and language match, if any."""
    path = CACHE_DIR / f"demo_{katha.language}.json"
    if not path.exists():
        return None
    record = json.loads(path.read_text(encoding="utf-8"))
    ours = _chunk_ids([s.model_dump() for s in katha.segments])
    theirs = _chunk_ids(record["katha"]["segments"])
    if ours != theirs or len(record["narrations"]) != len(katha.segments):
        return None
    return record

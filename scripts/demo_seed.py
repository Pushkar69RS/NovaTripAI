"""Create (or find) the canonical demo trip and print its URL.

    uv run python scripts/demo_seed.py

Bengaluru -> Mysuru & Srirangapatna, 3 days from 14 Sep 2026, 2 adults + 1 elder
+ 1 child, comfortable, Rs 18,000, heritage + food, "Amma tires by evening". The
landing page draws this trip's Day 2, so it has to exist before the review.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.api.routes import create, load_trip
from app.demo import DEMO_REQUEST, find_demo_trip

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    load_dotenv(ROOT / ".env")
    base = os.environ.get("BASE_URL", "http://127.0.0.1:8080").rstrip("/")
    with psycopg.connect(os.environ["SUPABASE_DB_URL"]) as conn:
        trip_id = find_demo_trip(conn)
        if trip_id is None:
            out = create(DEMO_REQUEST, conn)
            if out["status"] != "planned":
                print(f"the demo request came back as a verdict: {out['verdict']}")
                return 1
            trip_id = out["id"]
            print("created the demo trip")
        else:
            print("found the demo trip")
        trip = load_trip(conn, trip_id)
    m = trip["plan"]["metrics"]
    print(
        f"metrics: as listed {m['route_km_naive']} km | nearest-next "
        f"{m['route_km_before']} km | routed {m['route_km_after']} km | "
        f"repairs {m['repair_iterations']} | candidates {m['candidates_considered']} "
        f"| checks {m['constraint_checks_passed']}/{m['constraint_checks_total']} "
        f"| build {m['build_ms']} ms"
    )
    print(f"{base}/trips/{trip_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

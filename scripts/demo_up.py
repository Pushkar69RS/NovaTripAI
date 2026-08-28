"""Everything the demo needs, in one idempotent run. demo.ps1 calls this.

    uv run python scripts/demo_up.py

In order, one plain line per step: the environment and the database; the four
accounts; the three demo trips (created only when missing); the narrations and
the Mysuru Kannada Katha warmed so the stage does not touch the network; and a
five-line cue sheet, also written to var/cue.txt for the launcher to print.
Running it twice creates nothing new the second time.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import warnings
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import psycopg
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.accounts import TEAM, hash_password
from app.api.routes import create, load_katha
from app.demo import DEMO_REQUEST, cached_demo, find_demo_trip
from app.llm.client import complete
from app.planner.models import Traveller, TripRequest

ROOT = Path(__file__).resolve().parent.parent
OWNER = "rohan@travelyantra.in"
BASE = os.environ.get("BASE_URL", "http://127.0.0.1:8080").rstrip("/")

MANGALORE_REQUEST = TripRequest(
    origin_city="Bengaluru",
    destination_cities=["Mangalore"],
    start_date=date(2026, 9, 21),
    days=2,
    travellers=[
        Traveller(kind="adult", age_band="40-59"),
        Traveller(kind="adult", age_band="40-59"),
    ],
    transport="car",
    getting_around="own_car",
    budget_inr=12000,
    interest_tags=["nature"],
    notes="Review demo: a city the table had never seen.",
)
MANGALORE_KEY = {
    "origin_city": "Bengaluru",
    "destination_cities": ["Mangalore"],
    "start_date": "2026-09-21",
    "days": 2,
    "budget_inr": 12000,
}
NOFIT_REQUEST = TripRequest(
    origin_city="Bengaluru",
    destination_cities=["Mysuru", "Hampi"],
    start_date=date(2026, 9, 14),
    days=1,
    travellers=[
        Traveller(kind="adult", age_band="18-39"),
        Traveller(kind="adult", age_band="18-39"),
    ],
    transport="car",
    budget_inr=10000,
    interest_tags=["heritage"],
    notes="Review demo: two cities in one day.",
)
NOFIT_KEY = {
    "places": ["Mysuru", "Hampi"],
    "start_date": "2026-09-14",
    "days": 1,
    "budget_inr": 10000,
}


def say(line: str) -> None:
    print(line, flush=True)


# --------------------------------------------------------------------------- #
# steps
# --------------------------------------------------------------------------- #


def check_env() -> tuple[str, str]:
    """(database url, demo password), or exit 1 with the line to add."""
    load_dotenv(ROOT / ".env")
    url = os.environ.get("SUPABASE_DB_URL", "").strip()
    password = os.environ.get("DEMO_PASSWORD", "").strip()
    if not url:
        say(
            "SUPABASE_DB_URL is missing from .env; add: SUPABASE_DB_URL=postgresql://..."
        )
        sys.exit(1)
    if not password:
        say(
            "DEMO_PASSWORD is missing from .env; add: DEMO_PASSWORD=<the team password>"
        )
        sys.exit(1)
    say("env: .env loaded, DEMO_PASSWORD set")
    return url, password


def ping(url: str) -> None:
    host = urlparse(url).hostname or "?"
    try:
        with psycopg.connect(url, connect_timeout=5) as conn:
            conn.execute("SELECT 1").fetchone()
    except Exception:  # noqa: BLE001 - the message is the whole point here
        say(f"database unreachable ({host})")
        sys.exit(1)
    say(f"database: reachable ({host})")


def ensure_users(conn: Any, password: str) -> int:
    """The four accounts, upserted on email; the ownerless rows adopted. Returns Rohan's id."""
    for name, email in TEAM:
        conn.execute(
            "INSERT INTO app_user (email, name, password_hash) VALUES (%s, %s, %s) "
            "ON CONFLICT (email) DO UPDATE SET name = EXCLUDED.name, "
            "password_hash = EXCLUDED.password_hash",
            (email, name, hash_password(password)),
        )
    (owner,) = conn.execute(
        "SELECT id FROM app_user WHERE email = %s", (OWNER,)
    ).fetchone()
    for table in ("trip", "tour"):
        conn.execute(f"UPDATE {table} SET user_id = %s WHERE user_id IS NULL", (owner,))
    (total,) = conn.execute("SELECT count(*) FROM app_user").fetchone()
    say(f"accounts: {total} seeded, passwords from .env")
    return int(owner)


def find_trip(conn: Any, key: dict, status: str) -> str | None:
    row = conn.execute(
        "SELECT id FROM trip WHERE status = %s AND request @> %s::jsonb "
        "ORDER BY created_at LIMIT 1",
        (status, json.dumps(key)),
    ).fetchone()
    return str(row[0]) if row else None


def ensure_trips(
    conn: Any, owner: int, *, llm: Any = complete
) -> dict[str, str | None]:
    """The three demo trips, created only when missing. Never raises for Mangalore."""
    ids: dict[str, str | None] = {}

    trip_id = find_demo_trip(conn)
    if trip_id is None:
        out = create(DEMO_REQUEST, conn, owner)
        trip_id = out["id"]
        say(f"trip: canonical Mysuru trip created  {BASE}/trips/{trip_id}")
    else:
        say(f"trip: canonical Mysuru trip found    {BASE}/trips/{trip_id}")
    ids["canonical"] = trip_id

    trip_id = find_trip(conn, MANGALORE_KEY, "planned")
    if trip_id is None:
        try:
            out = create(MANGALORE_REQUEST, conn, owner, llm=llm)
        except Exception as exc:  # noqa: BLE001 - the demo must go on without it
            say(f"Mangalore demo skipped: {exc}")
            out = None
        if out is not None and out["status"] == "planned":
            trip_id = out["id"]
            reports = [r for r in out.get("cold_start", []) if r.get("drafted_places")]
            drafted = (
                f", {reports[0]['drafted_places']} places drafted" if reports else ""
            )
            say(f"trip: Mangalore trip created{drafted}  {BASE}/trips/{trip_id}")
        elif out is not None:
            reason = "; ".join(
                f"{r['label']}: {r['value']}" for r in out["verdict"]["reasons"]
            )
            say(f"Mangalore demo skipped: {reason}")
    else:
        say(f"trip: Mangalore trip found           {BASE}/trips/{trip_id}")
    ids["mangalore"] = trip_id

    trip_id = find_trip(conn, NOFIT_KEY, "impossible")
    if trip_id is None:
        out = create(NOFIT_REQUEST, conn, owner)
        trip_id = out["id"]
        say(f"trip: Mysuru + Hampi in a day created {BASE}/trips/{trip_id}")
    else:
        say(f"trip: Mysuru + Hampi in a day found   {BASE}/trips/{trip_id}")
    ids["nofit"] = trip_id
    return ids


def warm(conn: Any, ids: dict[str, str | None], password: str) -> bool:
    """Narrations stored and the Kannada Mysuru Katha built, through the app itself."""
    warnings.filterwarnings(
        "ignore"
    )  # the test client's deprecation notice is not a step
    from fastapi.testclient import TestClient

    from app.main import app

    logging.getLogger("httpx").setLevel(logging.WARNING)
    client = TestClient(app)
    signed = client.post(
        "/signin",
        data={"email": OWNER, "password": password, "next": "/home"},
        follow_redirects=False,
    )
    if signed.status_code != 303:
        say("warm: could not sign in through the app; narrations left to the page")
        return False

    for name in ("canonical", "mangalore"):
        trip_id = ids.get(name)
        if not trip_id:
            continue
        try:
            r = client.post(f"/api/trips/{trip_id}/narrate")
            say(
                f"narration: {name} {r.json().get('source', 'skipped') if r.status_code == 200 else 'skipped'}"
            )
        except Exception:  # noqa: BLE001 - the page narrates on load if this is missing
            say(f"narration: {name} skipped")

    row = conn.execute(
        "SELECT id FROM tour WHERE city = 'Mysuru' AND duration_min = 5 AND language = 'kn' "
        "AND scope->>'kind' = 'city' ORDER BY created_at DESC LIMIT 1"
    ).fetchone()
    tour_id = str(row[0]) if row else None
    if tour_id is not None and cached_demo(load_katha(conn, tour_id)[0]) is None:
        tour_id = None  # built before the city layer; a fresh one matches the cache
    if tour_id is None:
        r = client.post(
            "/api/katha",
            json={
                "scope": {"kind": "city", "id": "Mysuru"},
                "duration_min": 5,
                "depth": "quick",
                "language": "kn",
            },
        )
        if r.status_code != 200:
            say("katha: could not build the Mysuru Kannada Katha")
            return False
        tour_id = r.json()["id"]
        say(f"katha: Mysuru 5-minute Kannada Katha built  {BASE}/katha/{tour_id}")
    else:
        say(f"katha: Mysuru 5-minute Kannada Katha found  {BASE}/katha/{tour_id}")
    katha, _city, _meta = load_katha(conn, tour_id)
    record = cached_demo(katha)
    cached = bool(record and record.get("audio") and Path(record["audio"]).exists())
    say("voice: cached" if cached else "voice: NOT cached — will use browser voice")
    return cached


def cue_sheet(ids: dict[str, str | None]) -> list[str]:
    lines = [
        f"1. Canonical trip   {BASE}/trips/{ids.get('canonical')}",
        f"2. Mangalore trip   {BASE}/trips/{ids.get('mangalore') or '(skipped)'}",
        f"3. Doesn't fit      {BASE}/trips/{ids.get('nofit')}",
        f"4. Katha            {BASE}/katha",
        f"5. Sign in as {OWNER}",
    ]
    (ROOT / "var").mkdir(exist_ok=True)
    (ROOT / "var" / "cue.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return lines


def main() -> int:
    url, password = check_env()
    ping(url)
    with psycopg.connect(url) as conn:
        owner = ensure_users(conn, password)
        ids = ensure_trips(conn, owner)
        conn.commit()  # the app's own connections must see the new rows
        warm(conn, ids, password)
    say("")
    for line in cue_sheet(ids):
        say(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())

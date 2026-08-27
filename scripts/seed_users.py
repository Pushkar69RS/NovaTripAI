"""Seed the four team accounts from DEMO_PASSWORD.

    uv run python scripts/seed_users.py

Upserts on email, so a re-run resets the four passwords and adds nobody. Trips
and Kathas created before this migration have no owner; they are adopted by
Rohan so the demo trip stays visible on /saved.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.accounts import TEAM, hash_password

ROOT = Path(__file__).resolve().parent.parent
OWNER = "rohan@travelyantra.in"  # adopts the rows that predate the users table


def main() -> int:
    load_dotenv(ROOT / ".env")
    password = os.environ.get("DEMO_PASSWORD", "").strip()
    if not password:
        print("DEMO_PASSWORD is not set in .env; nothing seeded")
        return 1

    with psycopg.connect(os.environ["SUPABASE_DB_URL"]) as conn:
        for name, email in TEAM:
            conn.execute(
                "INSERT INTO app_user (email, name, password_hash) VALUES (%s, %s, %s) "
                "ON CONFLICT (email) DO UPDATE SET name = EXCLUDED.name, "
                "password_hash = EXCLUDED.password_hash",
                (email, name, hash_password(password)),
            )
            print(f"  {name:18s} {email}")

        (owner,) = conn.execute(
            "SELECT id FROM app_user WHERE email = %s", (OWNER,)
        ).fetchone()
        for table in ("trip", "tour"):
            adopted = conn.execute(
                f"UPDATE {table} SET user_id = %s WHERE user_id IS NULL",
                (owner,),
            ).rowcount
            if adopted:
                print(f"  {table}: {adopted} ownerless rows adopted by {OWNER}")

        (total,) = conn.execute("SELECT count(*) FROM app_user").fetchone()
    print(f"app_user: {total} accounts, all with the DEMO_PASSWORD from .env")
    return 0


if __name__ == "__main__":
    sys.exit(main())

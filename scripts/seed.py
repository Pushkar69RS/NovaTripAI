"""Full reload of poi, poi_edge, intercity_leg and advisory from data/pois.json.

    uv run python scripts/seed.py

TRUNCATE of those four tables is pre-approved (see CLAUDE.md). doc_chunk holds a
FK to poi, and Postgres refuses to truncate poi unless doc_chunk is truncated in
the same statement, so it is included only after confirming it is empty.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import date, time
from pathlib import Path

import psycopg
from dotenv import load_dotenv
from psycopg import sql

ROOT = Path(__file__).resolve().parent.parent
POI_COLS = [
    "name",
    "name_kn",
    "city",
    "district",
    "lat",
    "lng",
    "category",
    "tags",
    "typical_dwell_min",
    "entry_fee_inr",
    "opens",
    "closes",
    "closed_on",
    "best_time",
    "accessibility_notes",
    "elderly_friendly",
    "popularity",
    "source_url",
    "last_verified",
    "trust",
]
DEFAULTS = {
    "tags": [],
    "closed_on": [],
    "entry_fee_inr": 0,
    "elderly_friendly": True,
    "trust": "draft",
}
INSERT_POI = sql.SQL("INSERT INTO poi ({}) VALUES ({}) RETURNING id").format(
    sql.SQL(", ").join(map(sql.Identifier, POI_COLS)),
    sql.SQL(", ").join(sql.Placeholder(c) for c in POI_COLS),
)
INSERT_EDGE = (
    "INSERT INTO poi_edge (from_poi, to_poi, relation, weight) VALUES (%s, %s, %s, %s)"
)
INSERT_LEG = (
    "INSERT INTO intercity_leg (from_city, to_city, mode, distance_km, duration_min, notes) "
    "VALUES (%s, %s, %s, %s, %s, %s)"
)
INSERT_ADVISORY = (
    "INSERT INTO advisory (poi_id, city, severity, message, source, valid_until) "
    "VALUES (%s, %s, %s, %s, %s, current_date + %s)"
)


def poi_row(p: dict) -> dict:
    row = {c: p.get(c, DEFAULTS.get(c)) for c in POI_COLS}
    row["opens"] = time.fromisoformat(row["opens"]) if row["opens"] else None
    row["closes"] = time.fromisoformat(row["closes"]) if row["closes"] else None
    row["last_verified"] = (
        date.fromisoformat(row["last_verified"]) if row["last_verified"] else None
    )
    return row


def main() -> int:
    load_dotenv(ROOT / ".env")
    data = json.loads((ROOT / "data" / "pois.json").read_text(encoding="utf-8"))
    with psycopg.connect(os.environ["SUPABASE_DB_URL"]) as conn, conn.cursor() as cur:
        (chunks,) = cur.execute("SELECT count(*) FROM doc_chunk").fetchone()
        if chunks:
            print(
                f"doc_chunk has {chunks} rows referencing poi; ask Rohan before reloading"
            )
            return 1
        cur.execute(
            "TRUNCATE poi, poi_edge, intercity_leg, advisory, doc_chunk RESTART IDENTITY"
        )

        ids = {
            p["name"]: cur.execute(INSERT_POI, poi_row(p)).fetchone()[0]
            for p in data["pois"]
        }
        cur.executemany(
            INSERT_EDGE,
            [
                (ids[e["from"]], ids[e["to"]], e["relation"], e.get("weight", 1.0))
                for e in data["edges"]
            ],
        )
        legs = [
            (a, b, l["mode"], l.get("distance_km"), l["duration_min"], l.get("notes"))
            for l in data["intercity_legs"]
            for a, b in ((l["from"], l["to"]), (l["to"], l["from"]))
        ]
        cur.executemany(INSERT_LEG, legs)
        cur.executemany(
            INSERT_ADVISORY,
            [
                (
                    ids.get(a.get("poi")),
                    a.get("city"),
                    a["severity"],
                    a["message"],
                    a["source"],
                    a["valid_days"],
                )
                for a in data["advisories"]
            ],
        )

        for table in ("poi", "poi_edge", "intercity_leg", "advisory"):
            (n,) = cur.execute(
                sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(table))
            ).fetchone()
            print(f"{table}: {n}")
        for trust, n in cur.execute(
            "SELECT trust, count(*) FROM poi GROUP BY trust ORDER BY trust"
        ):
            print(f"  poi.trust={trust}: {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

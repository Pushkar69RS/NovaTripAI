"""Load the Katha corpus into doc_chunk and write the embeddings.

    uv run python scripts/seed_chunks.py

Two source files, in this order:

  data/chunks_curated.json   Rohan's hand-written paragraphs. Authoritative.
                             Loaded first, never rewritten here.
  data/chunks.json           Generated paragraphs that fill the gaps around them.

Both upsert on (city, title), so re-running is safe and never deletes. A row in
the table that neither file carries any more is marked retired, which retrieval
ignores; the row itself stays until Rohan decides to delete it.

Curated rows name places the way people say them (Belur, Srirangapatna, Chamundi
Hill). The poi table uses hub cities and full names, so a small map translates
on the way in. The file keeps its own words.

Embeddings are only recomputed for rows that lack one, unless --reembed is
passed. A body or alias change clears the old vector automatically.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

import psycopg
from dotenv import load_dotenv
from pgvector.psycopg import register_vector

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.rag.embed import BATCH, CITY_KN, chunk_text, embed_passages

ROOT = Path(__file__).resolve().parent.parent
CURATED_DATE = date(2026, 8, 27)  # the date on the curated file's own note

#: Locality in the curated file -> hub city in the poi table.
HUB = {"Srirangapatna": "Mysuru", "Belur": "Chikmagalur", "Halebidu": "Chikmagalur"}

#: Short place name in the curated file -> full name in the poi table.
POI_ALIAS = {
    "Chamundi Hill": "Chamundeshwari Temple",
    "Daria Daulat Bagh": "Daria Daulat Bagh (Tipu Sultan's Summer Palace), Srirangapatna",
    "Vittala Temple": "Vittala Temple and Stone Chariot",
    "Chennakeshava Temple": "Chennakeshava Temple, Belur",
    "Hoysaleswara Temple": "Hoysaleswara Temple, Halebidu",
    "Bull Temple": "Bull Temple (Dodda Basavana Gudi)",
    "Mullayanagiri": "Mullayanagiri Peak",
}

UPSERT = """
INSERT INTO doc_chunk
    (poi_id, city, title, body, chunk_type, is_legend, lang,
     source_name, source_url, last_verified, aliases, retired)
VALUES
    (%(poi_id)s, %(city)s, %(title)s, %(body)s, %(chunk_type)s, %(is_legend)s,
     %(lang)s, %(source_name)s, %(source_url)s, %(last_verified)s, %(aliases)s,
     false)
ON CONFLICT (city, title) DO UPDATE SET
    poi_id = excluded.poi_id,
    body = excluded.body,
    chunk_type = excluded.chunk_type,
    is_legend = excluded.is_legend,
    source_name = excluded.source_name,
    source_url = excluded.source_url,
    last_verified = excluded.last_verified,
    aliases = excluded.aliases,
    retired = false,
    embedding = CASE
        WHEN doc_chunk.body IS DISTINCT FROM excluded.body
          OR doc_chunk.aliases IS DISTINCT FROM excluded.aliases THEN NULL
        ELSE doc_chunk.embedding
    END
"""


def curated_rows() -> list[dict]:
    data = json.loads(
        (ROOT / "data" / "chunks_curated.json").read_text(encoding="utf-8")
    )
    out = []
    for c in data["chunks"]:
        name = c.get("poi_name")
        out.append(
            {
                "poi": POI_ALIAS.get(name, name) if name else None,
                "city": HUB.get(c["city"], c["city"]),
                "title": c["title"],
                "body": c["body"],
                "chunk_type": c["chunk_type"],
                "is_legend": bool(c.get("is_legend")),
                "lang": c.get("lang", "en"),
                "source_name": c.get("source_name"),
                "source_url": c.get("source_url"),
                "last_verified": CURATED_DATE.isoformat(),
                "origin": "curated",
            }
        )
    return out


def generated_rows() -> list[dict]:
    data = json.loads((ROOT / "data" / "chunks.json").read_text(encoding="utf-8"))
    return [{**c, "lang": "en", "origin": "generated"} for c in data["chunks"]]


def retire_absent(cur, live: set[tuple[str, str]]) -> list[tuple[str, str]]:
    """Switch off rows that no source file carries. Never deletes."""
    present = cur.execute(
        "SELECT city, title FROM doc_chunk WHERE NOT retired"
    ).fetchall()
    gone = [(c, t) for c, t in present if (c, t) not in live]
    for city, title in gone:
        cur.execute(
            "UPDATE doc_chunk SET retired = true WHERE city = %s AND title = %s",
            (city, title),
        )
    return gone


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--reembed", action="store_true", help="recompute every embedding"
    )
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    rows = curated_rows() + generated_rows()

    live: set[tuple[str, str]] = set()
    for r in rows:
        key = (r["city"], r["title"])
        if key in live:
            print(f"duplicate (city, title) across the two files: {key}")
            return 1
        live.add(key)

    with psycopg.connect(os.environ["SUPABASE_DB_URL"]) as conn:
        register_vector(conn)
        with conn.cursor() as cur:
            pois = {
                (name, city): (pid, name_kn)
                for pid, name, city, name_kn in cur.execute(
                    "SELECT id, name, city, name_kn FROM poi"
                )
            }
            missing = {
                (r["poi"], r["city"], r["origin"])
                for r in rows
                if r["poi"] and (r["poi"], r["city"]) not in pois
            }
            if missing:
                print(f"{len(missing)} chunks name a poi that is not in the table:")
                for name, city, origin in sorted(missing):
                    print(f"  [{origin}] {name!r} in {city}")
                return 1

            for r in rows:
                pid, name_kn = pois.get((r["poi"], r["city"]), (None, None))
                cur.execute(
                    UPSERT,
                    {
                        "poi_id": pid,
                        "city": r["city"],
                        "title": r["title"],
                        "body": r["body"],
                        "chunk_type": r["chunk_type"],
                        "is_legend": r["is_legend"],
                        "lang": r["lang"],
                        "source_name": r["source_name"],
                        "source_url": r["source_url"],
                        "last_verified": date.fromisoformat(r["last_verified"]),
                        # aliases feed body_tsv: what the chunk is about, not where
                        "aliases": " | ".join(n for n in (r["poi"], name_kn) if n),
                    },
                )
            curated = sum(r["origin"] == "curated" for r in rows)
            print(
                f"doc_chunk rows written: {len(rows)} "
                f"({curated} curated, {len(rows) - curated} generated)"
            )

            gone = retire_absent(cur, live)
            if gone:
                print(f"retired {len(gone)} rows no source file carries (not deleted)")

            if args.reembed:
                cur.execute("UPDATE doc_chunk SET embedding = NULL WHERE NOT retired")
            todo = cur.execute(
                "SELECT id, title, body, aliases, city FROM doc_chunk "
                "WHERE embedding IS NULL AND NOT retired ORDER BY id"
            ).fetchall()
            print(f"to embed: {len(todo)}")
            for start in range(0, len(todo), BATCH):
                batch = todo[start : start + BATCH]
                # The embedding does take the city: in 384 dimensions the place
                # is one feature among many and disambiguates rather than floods.
                vectors = embed_passages(
                    [
                        chunk_text(
                            title,
                            body,
                            [
                                *(aliases.split(" | ") if aliases else []),
                                city,
                                CITY_KN.get(city, ""),
                            ],
                        )
                        for _, title, body, aliases, city in batch
                    ]
                )
                cur.executemany(
                    "UPDATE doc_chunk SET embedding = %s WHERE id = %s",
                    [(vec, row[0]) for vec, row in zip(vectors, batch, strict=True)],
                )
                print(f"  embedded {min(start + BATCH, len(todo))}/{len(todo)}")

            total, live_n, embedded = cur.execute(
                "SELECT count(*), count(*) FILTER (WHERE NOT retired), "
                "count(*) FILTER (WHERE NOT retired AND embedding IS NOT NULL) "
                "FROM doc_chunk"
            ).fetchone()
            print(f"doc_chunk: {total} rows, {live_n} live, {embedded} embedded")
            for city, n in cur.execute(
                "SELECT city, count(*) FROM doc_chunk WHERE NOT retired "
                "GROUP BY city ORDER BY city"
            ):
                print(f"  {city}: {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

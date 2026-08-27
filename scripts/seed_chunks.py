"""Load data/chunks.json into doc_chunk and write the embeddings.

    uv run python scripts/seed_chunks.py

Upsert on (city, title), so re-running is safe and never deletes anything. The
first pass writes the rows, the second pass embeds them in batches. Embeddings
are only recomputed for rows that do not have one, unless --reembed is passed.

Note for later: once doc_chunk has rows, scripts/seed.py refuses to run, because
it truncates poi and Postgres will not let it leave a dangling FK. That is the
documented behaviour and it needs Rohan's go-ahead, not a flag.
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

UPSERT = """
INSERT INTO doc_chunk
    (poi_id, city, title, body, chunk_type, is_legend, lang,
     source_name, source_url, last_verified, aliases)
VALUES
    (%(poi_id)s, %(city)s, %(title)s, %(body)s, %(chunk_type)s, %(is_legend)s,
     %(lang)s, %(source_name)s, %(source_url)s, %(last_verified)s, %(aliases)s)
ON CONFLICT (city, title) DO UPDATE SET
    poi_id = excluded.poi_id,
    body = excluded.body,
    chunk_type = excluded.chunk_type,
    is_legend = excluded.is_legend,
    source_name = excluded.source_name,
    source_url = excluded.source_url,
    last_verified = excluded.last_verified,
    aliases = excluded.aliases,
    embedding = CASE
        WHEN doc_chunk.body IS DISTINCT FROM excluded.body
          OR doc_chunk.aliases IS DISTINCT FROM excluded.aliases THEN NULL
        ELSE doc_chunk.embedding
    END
RETURNING id
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--reembed", action="store_true", help="recompute every embedding"
    )
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    data = json.loads((ROOT / "data" / "chunks.json").read_text(encoding="utf-8"))[
        "chunks"
    ]

    with psycopg.connect(os.environ["SUPABASE_DB_URL"]) as conn:
        register_vector(conn)
        with conn.cursor() as cur:
            pois = {
                (name, city): (pid, name_kn)
                for pid, name, city, name_kn in cur.execute(
                    "SELECT id, name, city, name_kn FROM poi"
                )
            }
            poi_ids = {key: value[0] for key, value in pois.items()}
            missing = {
                (c["poi"], c["city"])
                for c in data
                if c["poi"] and (c["poi"], c["city"]) not in poi_ids
            }
            if missing:
                print(f"{len(missing)} chunks name a poi that is not in the table:")
                for name, city in sorted(missing):
                    print(f"  {name!r} in {city}")
                return 1

            for chunk in data:
                key = (chunk["poi"], chunk["city"])
                city = chunk["city"]
                names = pois.get(key, (None, None))
                cur.execute(
                    UPSERT,
                    {
                        # aliases feed body_tsv, so they hold what the chunk is
                        # about, not where it is. The city name would match every
                        # chunk in the city at the same rank, which is noise for a
                        # bag of words. Location is what Filters.city is for.
                        "aliases": " | ".join(n for n in (chunk["poi"], names[1]) if n),
                        "poi_id": poi_ids.get(key),
                        "city": chunk["city"],
                        "title": chunk["title"],
                        "body": chunk["body"],
                        "chunk_type": chunk["chunk_type"],
                        "is_legend": chunk["is_legend"],
                        "lang": "en",
                        "source_name": chunk["source_name"],
                        "source_url": chunk["source_url"],
                        "last_verified": date.fromisoformat(chunk["last_verified"]),
                    },
                )
            print(f"doc_chunk rows written: {len(data)}")

            if args.reembed:
                cur.execute("UPDATE doc_chunk SET embedding = NULL")
            todo = cur.execute(
                "SELECT id, title, body, aliases, city FROM doc_chunk "
                "WHERE embedding IS NULL ORDER BY id"
            ).fetchall()
            print(f"to embed: {len(todo)}")
            for start in range(0, len(todo), BATCH):
                batch = todo[start : start + BATCH]
                # The embedding does take the city: in 384 dimensions the place
                # is one feature among many and it disambiguates rather than floods.
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

            (total,) = cur.execute("SELECT count(*) FROM doc_chunk").fetchone()
            (embedded,) = cur.execute(
                "SELECT count(*) FROM doc_chunk WHERE embedding IS NOT NULL"
            ).fetchone()
            print(f"doc_chunk: {total} rows, {embedded} embedded")
            for city, n in cur.execute(
                "SELECT city, count(*) FROM doc_chunk GROUP BY city ORDER BY city"
            ):
                print(f"  {city}: {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

# travel-yantra — STATE
Project: travel-yantra
Purpose: AI travel planner + Karnataka virtual guide for BCS705 Phase-2 Review 1 on 28 Aug 2026.
Stack: Python 3.12 (uv), FastAPI, uvicorn, pydantic + pydantic-settings, jinja2, httpx, psycopg, numpy, sentence-transformers, pgvector; ruff + pytest.
Services: Supabase Postgres 17 + pgvector 0.8.2 + pg_trgm (project puzbpzdamygjosugoeeb, ap-south-1, session pooler on 5432); OpenRouter (deepseek/deepseek-chat) verified; embeddings computed locally with intfloat/multilingual-e5-small (cached, runs offline).
Exists now: app/main.py GET /health; scripts/check_env.py (preflight); db/migrations 001-003 applied; data/pois.json (112 POIs); scripts/seed.py; data/chunks.json (268 Katha paragraphs); scripts/seed_chunks.py; app/planner/ (deterministic planner); app/rag/ (embedding + hybrid retrieval); scripts/eval_retrieval.py; tests for health, check_env, seed data, planner and rag.
DB rows: poi 112, poi_edge 58, intercity_leg 40, advisory 1, doc_chunk 268 (all embedded), eval_run 8.
Gates: `uv run ruff check .`, `uv run ruff format --check .`, `uv run pytest` — all pass (37 tests).
Preflight: `uv run python scripts/check_env.py` before any DB or LLM task.

## Planner (app/planner/)
Pure Python, no LLM, no write. `plan(request, db)` reads; `build(...)` is the same
planner with every input in memory, which is how the tests run without a database.
Candidates → feasibility gate → k-means (own implementation, fixed seed) → nearest
neighbour → 2-opt → validator → bounded repair → three weight variants ranked by
(validity, interest, travel). Both routes are kept, so route_km_before survives for
the map toggle. Demo: `uv run python -m app.planner.engine --demo`.

## Katha corpus (data/chunks.json → doc_chunk)
268 paragraphs, 90–160 words each, written to be spoken aloud. By city: Mysuru 74,
Hampi 65, Chikmagalur 59 (Belur and Halebidu live under Chikmagalur, per the hub-city
rule), Bengaluru 45, Coorg 25. By type: fact 68, practical 61, story 47, sensory 47,
hook 25, taste 20. 24 are marked is_legend. 62 carry a source_url; the rest carry a
source_name only, per the sourcing cap. Deep sets of 10+ for Mysore Palace, Vittala,
Virupaksha and Chennakeshava Belur; Chamundi Hill has 10 spread over its three POI rows.
Seed with `uv run python scripts/seed_chunks.py` (upsert on (city, title), never
destructive; `--reembed` recomputes vectors).

## Retrieval (app/rag/)
- `embed.py` — multilingual-e5-small, loaded once on first use. Documents are encoded
  as "passage: ...", queries as "query: ...". Vectors are 384-dim and normalised.
  Indexed text is title + body + the POI name in English and Kannada + the city.
- `retrieve.py` — `search(query, db, filters=, k=8, trip_context=)`. Dense pgvector
  cosine over HNSW and Postgres full text over body_tsv, each over-fetching 20, fused
  with RRF (k=60), trimmed to k. Filters: city, poi_id, chunk_type, exclude_ids.
  Trip context appends the current stop and its city to the query, adds 0.15 to that
  POI's rows and 0.05 to rows mentioning steps or access when the party has elderly
  members. Below 0.81 cosine with no strict lexical match it returns nothing, and the
  caller is expected to say it does not know.

## Retrieval eval (scripts/eval_retrieval.py, eval_run id=8)
30 written questions (21 English, 6 Kannada, 3 Hinglish) plus a separate block of 10
name and keyword lookups. Expected chunks are named by title and resolved to ids at
run time.

    A. 30 written questions        Recall@5    MRR    p50 ms   p95 ms
       dense only                     0.933  0.882      58.5     67.2
       lexical only                   0.733  0.654      57.9     62.2
       hybrid + RRF                   0.933  0.877     116.0    125.7

    B. 10 name/keyword lookups     Recall@5    MRR    p50 ms   p95 ms
       dense only                     1.000  0.950      59.7     68.1
       lexical only                   1.000  1.000      28.1     29.0
       hybrid + RRF                   1.000  0.950      82.4     86.2

Refusal gate: 6/6 unanswerable queries returned nothing.

Honest reading: hybrid does NOT beat both single methods on this corpus. It matches the
better of the two in each regime and costs about twice the latency. Dense alone
dominates lexical at every point here, because 268 chunks and a strong multilingual
embedder leave little for term matching to add. Hybrid is kept because lexical is the
only method that gets exact names perfectly (MRR 1.000 on block B) and because the two
questions dense misses are ones lexical structurally cannot help with, not ones fusion
got wrong.

Known issue: RLS is disabled on every public table (Supabase advisor). The app connects as the postgres role over the pooler, so this only matters once the anon key is used; enable RLS with policies before that.
Known limit: Kannada Recall@5 is 0.833 against 0.952 for English. body_tsv is an English tsvector, so lexical scores 0.333 on Kannada and the dense side carries it alone.
Known limit: MIN_SIMILARITY 0.81 was calibrated against 12 real and 8 nonsense queries. The margin is about two points and the set is small.
Note: doc_chunk now has rows, so `scripts/seed.py` will refuse to run. That is by design and needs Rohan's go-ahead, not a flag.
Not yet: the planner and retrieval behind API routes, frontend, LLM narration, Katha assembly.
Next step (estimated): POST /plan and POST /katha over the planner and retriever, then the frontend.
Updated: 2026-08-28

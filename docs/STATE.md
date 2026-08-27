# travel-yantra — STATE
Project: travel-yantra
Purpose: AI travel planner + Karnataka virtual guide for BCS705 Phase-2 Review 1 on 28 Aug 2026.
Stack: Python 3.12 (uv), FastAPI, uvicorn, pydantic + pydantic-settings, jinja2, httpx, psycopg, numpy; ruff + pytest.
Services: Supabase Postgres 17 + pgvector 0.8.2 + pg_trgm (project puzbpzdamygjosugoeeb, ap-south-1, session pooler on 5432); OpenRouter (deepseek/deepseek-chat) verified; local multilingual-e5-small embeddings not yet wired.
Exists now: app/main.py GET /health; scripts/check_env.py (preflight); db/migrations/001_init.sql applied (poi, poi_edge, intercity_leg, advisory, doc_chunk, trip, tour, eval_run); data/pois.json (112 POIs, 58 edges, 20 legs, 1 advisory); scripts/seed.py (full reload); data/verification_report.md; tests for health, check_env and seed data.
DB rows: poi 112 (20 verified via Tavily, 92 draft), poi_edge 58, intercity_leg 40 (both directions), advisory 1, doc_chunk 0.
Gates: `uv run ruff check .`, `uv run ruff format --check .`, `uv run pytest` — all pass.
Preflight: `uv run python scripts/check_env.py` before any DB or LLM task.
Known issue: RLS is disabled on every public table (Supabase advisor). The app connects as the postgres role over the pooler, so this only matters once the anon key is used; enable RLS with policies before that.
Not yet: doc_chunk content and embeddings, planner, hybrid retrieval, frontend, LLM narration.
Next step (estimated): doc_chunk authoring + local e5 embedding pipeline, then the deterministic planner.
Updated: 2026-08-27

# travel-yantra — STATE
Project: travel-yantra
Purpose: AI travel planner + Karnataka virtual guide for BCS705 Phase-2 Review 1 on 28 Aug 2026.
Stack: Python 3.12 (uv), FastAPI, uvicorn, pydantic + pydantic-settings, jinja2, httpx, psycopg, numpy; ruff + pytest.
Planned services: Supabase Postgres + pgvector, OpenRouter (deepseek/deepseek-chat), local multilingual-e5-small embeddings.
Exists now: uv project + git, app/main.py with GET /health, scripts/check_env.py (read-only secrets preflight), tests/, CLAUDE.md, docs/, .env.example, .gitignore.
Gates: `uv run ruff check .`, `uv run ruff format --check .`, `uv run pytest` — all pass.
Preflight: `uv run python scripts/check_env.py` before any DB or LLM task.
Not yet: database code, frontend, LLM calls.
Next step: DB schema + seed.
Updated: 2026-08-27

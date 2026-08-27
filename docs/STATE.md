# travel-yantra — STATE
Project: travel-yantra
Purpose: AI travel planner + Karnataka virtual guide for BCS705 Phase-2 Review 1 on 28 Aug 2026.
Stack: Python 3.12 (uv), FastAPI, uvicorn, pydantic + pydantic-settings, jinja2, httpx, psycopg, numpy; ruff + pytest.
Services: Supabase Postgres 17 + pgvector 0.8.2 + pg_trgm (project puzbpzdamygjosugoeeb, ap-south-1, session pooler on 5432); OpenRouter (deepseek/deepseek-chat) verified; local multilingual-e5-small embeddings not yet wired.
Exists now: app/main.py GET /health; scripts/check_env.py (preflight); db/migrations/001_init.sql applied (poi, poi_edge, intercity_leg, advisory, doc_chunk, trip, tour, eval_run); data/pois.json (112 POIs, 58 edges, 20 legs, 1 advisory); scripts/seed.py (full reload); data/verification_report.md; app/planner/ (the deterministic planner); tests for health, check_env, seed data and the planner.
DB rows: poi 112 (20 verified via Tavily, 92 draft), poi_edge 58, intercity_leg 40 (both directions), advisory 1, doc_chunk 0.
Gates: `uv run ruff check .`, `uv run ruff format --check .`, `uv run pytest` — all pass (27 tests).
Preflight: `uv run python scripts/check_env.py` before any DB or LLM task.

## Planner (app/planner/)
Pure Python, no LLM anywhere, no write to the database. `plan(request, db)` reads;
`build(request, pois, edges, legs, advisories, centroids)` is the same planner with
every input already in memory, which is how the tests run without a connection.

- `models.py` — TripRequest, Poi, Advisory, Leg, Stop, Move, Day, Plan, PlanMetrics, Verdict.
  Pace capacity: relaxed 3, comfortable 4, packed 6 stops a day.
- `distance.py` — haversine; road minutes = straight km × 1.35 ÷ speed (22 km/h in
  a city, 45 km/h between). A stored `intercity_leg` row always beats the formula;
  the formula fallback is marked `is_estimated`.
- `cluster.py` — k-means++ with a fixed seed, written out (no sklearn), then
  `balance()` trims each cluster to pace capacity and returns the overflow as a
  spill pool the engine keeps in reserve.
- `route.py` — nearest neighbour, then 2-opt (capped at 200 iterations, only
  strictly improving reversals). `optimise()` returns both orders and both
  distances; the pre-2-opt route is never discarded.
- `validate.py` — pure. CLOSED_DAY, OUTSIDE_HOURS, OVER_BUDGET, DAY_TOO_LONG,
  NO_MEAL_GAP, TRAVEL_OVERRUN, ADVISORY_CLOSED. Each violation carries a machine
  code, a plain sentence, its day, and the stop it names where there is one.
- `engine.py` — candidates → feasibility gate → clusters → route → schedule →
  validate → repair → three weight variants ranked by (validity, interest,
  travel). Demo: `uv run python -m app.planner.engine --demo`.

Day shape: starts 09:00, 12 h of planning time; one hard anchor per day (the
highest-scoring stop) which repair never drops; soft stops carry a silent 1.15×
dwell buffer rounded up to 5 minutes, never surfaced. Repair drops the soft stop
a violation names, otherwise the day's lowest-scoring soft stop, least-repaired
day first, 8 iterations maximum.

Demo output (Mysuru, 2 days from Bengaluru, comfortable, party of 2): 4 stops a
day, lunch on both days, 31/31 checks, 0 repairs, build 6 ms.

Known issue: RLS is disabled on every public table (Supabase advisor). The app connects as the postgres role over the pooler, so this only matters once the anon key is used; enable RLS with policies before that.
Known limit: Coorg has one midday food POI, so a Coorg leg longer than a day trips NO_MEAL_GAP on the days it cannot feed. More food rows fix it, not more code.
Not yet: doc_chunk content and embeddings, hybrid retrieval, the planner behind an API route, frontend, LLM narration.
Next step (estimated): doc_chunk authoring + local e5 embedding pipeline, then POST /plan over the planner.
Updated: 2026-08-27

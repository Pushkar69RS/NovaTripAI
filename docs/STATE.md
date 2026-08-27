# travel-yantra — STATE
Project: travel-yantra
Purpose: AI travel planner + Karnataka virtual guide for BCS705 Phase-2 Review 1 on 28 Aug 2026.
Stack: Python 3.12 (uv), FastAPI + Jinja2 + one vanilla JS file (no framework, no build step), pydantic,
httpx, psycopg, numpy, sentence-transformers, pgvector; ruff + pytest; python-pptx for the deck builder.
Services: Supabase Postgres 17 + pgvector + pg_trgm (project puzbpzdamygjosugoeeb, ap-south-1, session
pooler on 5432); OpenRouter (classify deepseek/deepseek-chat; narrate_plan and narrate_katha
google/gemini-3.1-flash-lite); Sarvam bulbul:v3 for speech; embeddings local (multilingual-e5-small).
Gates: `uv run ruff check .`, `uv run ruff format --check .`, `uv run pytest` — all pass (101 tests).
Preflight: `uv run python scripts/check_env.py` before any DB or LLM task.
Run: `uv run uvicorn app.main:app --port 8000`; `uv run python scripts/demo_seed.py` creates or finds the
canonical demo trip and prints its URL. Measured OpenRouter spend for the whole project to date: $0.0214.
DB: poi 112, poi_edge 58, intercity_leg 40, advisory 1, doc_chunk 311 rows of which 257 live (54 retired),
app_user 4, trip and tour rows owned by their creator, eval_run 9.
Migrations: 001 core, 002 doc_chunk key, 003 aliases, 004 retired + tour shape, 005 app_user + user_id.

## Accounts (app/accounts.py, db/migrations/005_users.sql)
Four team accounts, seeded by `uv run python scripts/seed_users.py` from DEMO_PASSWORD:
nithin@ / pushkar@ / rishab@ / rohan@travelyantra.in (all @travelyantra.in). No sign-up, no reset.
`app_user` is named that because `user` is reserved in Postgres. Passwords are stored as
pbkdf2_sha256$200000$salt$digest; the plaintext never reaches the database. The session cookie is
`<user id>.<HMAC of the id under DEMO_PASSWORD>`, so changing the password invalidates every session.
trip.user_id and tour.user_id are set on create; /saved and /home list only your own rows, and a trip or
Katha someone else owns is a 404, not a 403. Every /api route now requires the same cookie (401 without
it); /health and the landing page stay open. The seed adopted the 6 trips and 5 tours that predate the
table so Rohan keeps the demo data.

## Frontend (app/web.py, app/templates/, app/static/) — unchanged this session apart from auth
Pages: / (landing), /signin, /signout, /home, /trips/new, /trips/{id} (plan; `?pick` chooser; a verdict
renders the doesn't-fit page), /katha, /katha/{id}, /saved. Templates format; every number comes from the
modules the API uses, handed to ty.js as JSON in `#page-data`.
Design: app/static/ty.css is the mockup's CSS verbatim plus an app-only block that adds no colour and no
font. Fonts self-hosted in app/static/fonts. Zero external requests on any page load.
Maps: inline SVG from real lat/lng; the As listed / As routed toggle draws Day.naive_order against the
built order with Day.naive_km / Day.route_km in the footer.

## Planner (app/planner/) — deterministic
k-means → NN → 2-opt → validate → repair. Day.naive_order / Day.naive_km ("as listed": stops in
candidate-score order, what an itinerary that never routes visits), Day.route_km measured the same way,
PlanMetrics.route_km_naive. `build_all()` takes every scoring variant (steady / interests / popular) to a
plan, best first; `build()` is its first. TripRequest normalises localities to hub cities and carries
day_one_start, day_end and preferences. `feasibility()` adds a Reason per transfer leg.
Canonical demo trip (Bengaluru → Mysuru & Srirangapatna, 3 days from 14 Sep 2026, 2 adults + 1 elder +
1 child, comfortable, ₹18,000, heritage + food): as listed 34.98 km | nearest-next 30.9 km | routed
30.9 km | repairs 3 | candidates 27 of 112 | checks 37/37 | build 3 ms. Day 2 alone: 10.53 → 6.45 km.

## Retrieval, Katha, narrator, voice, chat — unchanged
Dense + lexical fused with RRF k=60; refusal below 0.81 cosine with no strict lexical match. Eval
(eval_run 9): hybrid Recall@5 0.867 on the merged corpus, 0.933 before the merge, MRR 0.772, p50 110 ms;
10 name lookups 0.900; refusal gate 6/6. Katha builder unchanged. Narration on gemini-3.1-flash-lite with
the post-check; warm_tts re-run passed 14/14. A Katha made of the same paragraphs as a warm_tts demo takes
the demo narration and the cached WAV — verified end to end in Kannada (X-Voice: cached, no model call).

## Review 1 deliverables (docs/review1/)
`Travel_Yantra_Phase2_Review1.pptx` — 16 slides, built by `uv run python scripts/build_deck.py` from the
department template in docs/review1/template/. The template's slide order, placeholders, fonts, footer and
numbering are untouched; slides are only reused or duplicated from it. Continuations of one mandated
section are labelled "(contd.)": Methodology ×2, Demonstration ×3, Results ×2. A References slide closes
the deck because the template's own CONTENT slide lists it. Diagrams (pipeline, repair-loop flowchart,
evidence bars, distance bars, status columns) are drawn in the template's own theme colours and
Times New Roman. Screenshots 01, 04, 07, 08, 09, 10, 11, 12, 17, 18, 19 carry one caption each.
`Travel_Yantra_Phase2_Review1_Script.md` — 5:51 speaking + 2:00 demo + 2:00 Q&A, per-slide timing,
speaker rotation, demo cues, ten anticipated questions and a break-glass section.

Known issue: RLS disabled on every public table; enable before the anon key is used. The API is now behind
the session cookie, which was the more urgent of the two.
Known limit: 92 of 112 POIs are unverified draft data, labelled estimated in the UI.
Known limit: Coorg has a single midday food POI, so a long Coorg leg trips the meal-gap rule.
Known limit: map segments are straight lines, not road geometry; the kilometres use a detour factor.
Known limit: the chooser ranks each variant under its own weights; on the demo trip "popular" wins.
Known limit: 54 retired doc_chunk rows await `DELETE FROM doc_chunk WHERE retired` — Rohan's call.
Not yet: Objectives 2, 3, 4 (five languages, WhatsApp and voice, live booking); Hindi voice end to end;
RLS; sign-up; deployment (post-review by decision).
Next step (estimated): the review at 11:00; then RLS before any anon key.
Updated: 2026-08-28

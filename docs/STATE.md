# travel-yantra — STATE
Project: travel-yantra
Purpose: AI travel planner + Karnataka virtual guide for BCS705 Phase-2 Review 1 on 28 Aug 2026.
Stack: Python 3.12 (uv), FastAPI + Jinja2 + one vanilla JS file (no framework, no build step), pydantic,
httpx, psycopg, numpy, sentence-transformers, pgvector; ruff + pytest.
Services: Supabase Postgres 17 + pgvector + pg_trgm (project puzbpzdamygjosugoeeb, ap-south-1, session
pooler on 5432); OpenRouter (classify deepseek/deepseek-chat; narrate_plan and narrate_katha
google/gemini-3.1-flash-lite); Sarvam bulbul:v3 for speech; embeddings local (multilingual-e5-small).
Gates: `uv run ruff check .`, `uv run ruff format --check .`, `uv run pytest` — all pass (95 tests).
Preflight: `uv run python scripts/check_env.py` before any DB or LLM task.
Run: `uv run uvicorn app.main:app --port 8000`; `uv run python scripts/demo_seed.py` creates or finds the
canonical demo trip and prints its URL. Sign in at /signin as rohan@travelyantra.in with DEMO_PASSWORD
(.env; listed in .env.example). Landing and /health are public; every other page needs the cookie.
DB: poi 112, poi_edge 58, intercity_leg 40, advisory 1, doc_chunk 311 rows of which 257 live (54 retired,
not deleted), trip rows from the walk-through (canonical demo + drafts), tour rows likewise, eval_run 9.
Migrations: 001 core, 002 doc_chunk (city,title) key, 003 aliases, 004 retired + tour shape. None added.

## Frontend (app/web.py, app/templates/, app/static/)
Pages: / (landing), /signin, /signout, /home, /trips/new, /trips/{id} (plan; `?pick` is the chooser; an
impossible trip renders the doesn't-fit page), /katha, /katha/{id}, /saved. Templates format; every number
comes from the same modules the API uses, embedded as JSON in `#page-data` for ty.js.
Design: app/static/ty.css is docs/design/travel-yantra-mockup-v3.html's CSS verbatim (tokens, type stack,
components; only its screen switcher left out) plus an app-only block that adds no colour and no font.
Fonts self-hosted in app/static/fonts (Bricolage Grotesque, IBM Plex Sans, Anek Kannada as variable files;
IBM Plex Mono 400/500 static; latin, latin-ext and Kannada subsets). Zero external requests on any page,
checked in the Playwright network log; the demo survives dead WiFi on the browser side (the DB is remote).
Maps: inline SVG from real lat/lng. Day maps: equirectangular onto the day's bounding box + padding, aspect
kept, numbered pins in visit order, hard stop filled, the intercity transfer dashed in from the frame edge
with mode and minutes, pins closer than 30px nudged apart. The As listed / As routed toggle draws
Day.naive_order against the built order with Day.naive_km / Day.route_km in the footer. Karnataka maps use
the mockup's outline and the projection its city dots were placed with (fitted from five cities).
Landing: the right column draws the canonical demo trip's Day 2 live (falls back to the latest planned
trip, then to an honest empty card) and a hint line with its listed/routed km and build ms.
Flow: three-step form with every mocked field (localities such as Srirangapatna resolve to their hub
city; day-one departure and "day ends by" reach the planner; the rest travel as `preferences`) → POST
/api/trips → interstitial filled from PlanMetrics (candidates of 112, clusters, listed → routed km,
checks passed, fixes, build ms; "The plan is computed, not guessed."; sixth stage says "templates · no AI
in this part") → chooser over plan + alternatives (real cost, comfort word, Tight in laterite, Plan B) →
plan view (day tabs, rail with dashed moves and a closing "Back at the hotel" card, map, trace drawer fed by
PlanMetrics, summary strip from Day fields, pin↔card focus both ways) → chat rail (POST /api/trips/{id}/chat,
quick chips "Make Day n lighter" / "One more food stop" / "ಕನ್ನಡದಲ್ಲಿ ಹೇಳಿ"); an edit prints the dashed
"Day 2 rebuilt · Days 1 and 3 untouched" line from change_summary and redraws only that day.
Doesn't-fit page: Verdict.reasons as the math block (one row per transfer leg, km in the label),
Verdict.alternatives as "Build this" cards that POST the overridden request, the two-city Karnataka SVG.
Katha: home with search over GET /api/places/search (minutes of material per place and city) and the
coverage map (places with a sourced paragraph per city, from the DB: 106 of 112); player with
duration/depth/language pickers (POST /api/katha and navigate), type chips (hook/story in laterite),
Legend chip and "As the legend goes ·" source line, "Go deeper →" to a deep place Katha, locator SVG,
play → POST /api/katha/{id}/audio into an <audio> blob (X-Voice cached|sarvam), browser speechSynthesis
when audio is unavailable; Kannada/Hindi pages call /narrate on load and swap the text in.
Screenshots: docs/screenshots/01–20 (1280×800) from the walk-through: landing, sign in, home, form ×3,
building, chooser, plan routed, Day 2 as listed, trace, chat edit, day Katha, place Katha, Katha home,
search, city Katha, playing (Sarvam · cached), doesn't fit, saved.

## Planner (app/planner/) — deterministic, plus the as-listed baseline and three variants
k-means → NN → 2-opt → validate → repair, unchanged. New: Day.naive_order / Day.naive_km ("as listed": the
day's stops in candidate-score order, the order a plain list — a pure LLM itinerary — visits them) and
Day.route_km measured the same way; PlanMetrics.route_km_naive. `build_all()` takes every scoring variant
(VARIANTS steady / interests / popular → Plan.variant) to a plan, best first; `build()` is its first.
TripRequest gained `places` (what was typed), `day_one_start`, `day_end`, `preferences`; destination and
origin cities are normalised to hub cities (LOCALITIES). `feasibility()` adds a Reason per transfer leg.
Canonical demo trip (Bengaluru → Mysuru & Srirangapatna, 3 days from 14 Sep 2026, 2 adults + 1 elder +
1 child, comfortable, ₹18,000, heritage + food, "Amma tires by evening"): as listed 34.98 km | nearest-next
30.9 km | routed 30.9 km | repairs 3 | candidates 27 of 112 | checks 37/37 | build 3 ms. Day 2 alone:
10.53 km listed against 6.45 km routed. The test asserts route_km_naive > route_km_after on this request.

## Corpus (data/chunks_curated.json + data/chunks.json → doc_chunk) — unchanged
257 live paragraphs: 45 curated by Rohan (authoritative, loaded first, never rewritten) and 212 generated.
By city: Mysuru 70, Hampi 62, Chikmagalur 55, Bengaluru 45, Coorg 25.

## Retrieval (app/rag/) — unchanged
Dense (pgvector HNSW) + lexical (tsvector, strict then OR fallback) fused with RRF k=60; refusal below
0.81 cosine with no strict lexical match. Eval (eval_run 9, 30 questions): hybrid Recall@5 0.867, MRR
0.772, p50 110 ms; 10 name lookups 0.900; refusal gate 6/6. The embedder is warmed in a thread at startup.

## Katha builder (app/katha/build.py) — unchanged
budget = minutes × 145 words; spine by scope; budget split by popularity; rhythm rules in `arrange()` and
`check_rhythm()`; a second pass fills to 85% of budget. `--demo` prints the 5-minute Mysuru Katha.

## Narrator (app/llm/) — models switched
`narrate_segment()` / `narrate_plan()` on google/gemini-3.1-flash-lite (Rohan's pick, id checked on the
live OpenRouter /models list on 2026-08-28); classify stays on deepseek/deepseek-chat. Post-check flags any
number, year or (English) name not in the input, any %, and a cut-off completion; retry at 0, then the
corpus text. warm_tts.py re-run on the new model: 14 of 14 segments passed the check (one on the retry).

## Voice (app/voice/tts.py) — unchanged, plus the demo short-circuit
Sarvam bulbul:v3, speaker roopa, 22050 Hz WAV, cached in var/tts by sha256(voice, lang, text). A Katha made
of the same paragraphs as a warm_tts demo (app/demo.py `cached_demo`) takes the demo narration and the
cached WAV: no model, no network. demo_en 235 s, demo_kn 310 s of audio on disk.

## Chat (app/chat/router.py) — widened
Questions never reach the model. Edits are parsed to JSON, then: a day named in the message beats the
model's day_index; a target that is a kind of place ("one more food stop") resolves to the best unused
POI of that category, preferring one that serves lunch; lighter/gentler/heavier are pace words; the edit
keeps the traveller's message. One day is rebuilt; the others stay byte-identical.

## API (app/api/routes.py)
POST /api/trips (plan + the two alternatives stored on the row), GET /api/trips/{id}, POST
/api/trips/{id}/choose, POST /api/trips/{id}/chat, POST /api/katha, GET /api/katha/{id}, POST
/api/katha/{id}/narrate, POST /api/katha/{id}/audio (204 when speech is unavailable), GET
/api/places/search (cities and places with minutes of material), GET /health. `create()` is shared with
scripts/demo_seed.py; `coverage()` with the Katha home.

Known issue: RLS disabled on every public table; enable before the anon key is used.
Known issue: the API is not behind the session cookie, only the pages are.
Known limit: the chooser ranks each variant by its interest score under its own weights (pre-existing);
on the demo trip the "popular" variant comes out recommended.
Known limit: `rebuild_day` scores with the house weights whatever variant built the plan, so a stop
added by chat can outrank the day's anchor and survive a violation; the validator then flags it and the
plan turns tight (seen once: a breakfast-only place added into an afternoon).
Known limit: 54 retired doc_chunk rows await `DELETE FROM doc_chunk WHERE retired` — Rohan's call.
Not yet: plan narration surfaced in the UI (narrate_plan is wired, unused), Hindi voice end to end, RLS,
sign-up, deployment (post-review by decision).
Next step (estimated): the review; then RLS before any anon key; Vercel after.
Updated: 2026-08-28

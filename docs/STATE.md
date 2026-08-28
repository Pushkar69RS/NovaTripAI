# travel-yantra — STATE
Project: travel-yantra
Purpose: AI travel planner + Karnataka virtual guide for BCS705 Phase-2 Review 1 on 28 Aug 2026 at 11:00.
Stack: Python 3.12 (uv), FastAPI + Jinja2 + one vanilla JS file (no framework, no build step), pydantic,
httpx, psycopg, numpy, sentence-transformers, pgvector; ruff + pytest; python-pptx for the deck builder.
Services: Supabase Postgres 17 + pgvector + pg_trgm (project puzbpzdamygjosugoeeb, ap-south-1, session
pooler on 5432); OpenRouter (classify deepseek/deepseek-chat; narrate_plan, narrate_katha, draft_places
and parse_intake google/gemini-3.1-flash-lite, ids checked against the live /models list on 28 Aug);
Sarvam bulbul:v3 for speech; embeddings local (multilingual-e5-small).
Gates: `uv run ruff check .`, `uv run ruff format --check .`, `uv run pytest` — all pass (144 tests, ~19 s).
Preflight: `uv run python scripts/check_env.py` before any DB or LLM task.
Run: `uv run uvicorn app.main:app --port 8080`; `uv run python scripts/demo_seed.py` creates or finds the
canonical demo trip and prints its metrics line. OpenRouter spend this run: about $0.04 (estimated).
DB: poi 135 (20 verified, 92 draft, 23 ai_generated — all of Mangalore), doc_chunk 354 rows of which 300
live (82 carry a theme: 14 per hub plus 12 drafted for Mangalore; 23 legends; 54 retired), city_centre 6
(5 poi_average + Mangalore ai_generated), app_user 4, trip 9, tour 16, eval_run 10.
Migrations: 001 core, 002 doc_chunk key, 003 aliases, 004 retired + tour shape, 005 app_user + user_id,
006 intake and cold start (trust ai_generated, doc_chunk.theme/tier, city_centre, trip.narration/cold_start).
Git: history rewritten on 28 Aug so no commit carries a Co-Authored-By trailer (CLAUDE.md rule 8);
`backup-before-rewrite` and `backup-before-remove-claude` are local branches Rohan deletes after the review.

## Intake (app/templates/trip_new.html, init.trip_new in app/static/ty.js, app/llm/intake.py)
A free-text box at the top ("Tell us about the trip in your own words") posts to /api/trips/parse:
parse_intake() asks google/gemini-3.1-flash-lite for JSON, validates it strictly as ParsedIntake (every field
optional, extra keys forbidden), never invents a date (a date is kept only when the text names one), and
on any failure returns an empty fill with "Couldn't read that — fill it in by hand". The form works without it.
Three steps: where & when (origin, up to three places, date, days, getting there, getting around once there);
who's going (adults/children steppers with one age row each — adult 18-39/40-59/60+, child under 3/3-5/
6-12/13-17 — trip type chips, pace, day should end by, food); money & tastes (budget total or per person
with the other figure live, one fixed line about what it covers, interests pre-ticked from the trip type,
must-see, skip). A summary card restates the inputs and up to three lines that are true for them.
Removed because the planner never acted on them: leave-on-day-one, elders counter, children's ages, walking,
mornings, budget-covers, stay style, the second free-text box. Before posting, the form asks
/api/places/coverage and says when it must learn a city first ("about 20 seconds").
TripRequest: travellers derive party_size, has_elderly, has_children; has_toddler = a child under six;
`gentle` (elder or toddler) gives 19:00 evenings, elderly-friendly places only, and never a packed day;
trip_type seeds interest_tags only when none were ticked; `skip` words remove places by name, tag or
category; must_see, food, notes and trip_type reach the narrator. Explicit party_size/has_elderly still win
when travellers is empty, so stored trips keep working. day_one_start and the preferences bag are gone.

## Cold start (app/planner/coldstart.py, app/planner/poi_rules.py)
create() runs ensure_city() for the origin and every destination before plan_all. A city with fewer than
eight poi rows gets one json-mode call (temperature 0) for its centre and 20-25 real places; every row passes
the seed file's own rules (poi_rules.poi_problems, India box), is deduped on name and must sit within 60 km
of the centre; survivors are inserted as trust='ai_generated', the centre into city_centre, and the Katha
city layer is drafted the same way, fail-soft. The origin gets only a centre. Fewer than eight survivors, or a
model or network failure, is a Verdict (reason "Places we could find in X" or "Could not reach the model")
with a "Plan <hub> instead" alternative for every hub within 300 km — never a 500; an unknown city that still
has no centre is a 422 ("unknown city: X"). The report rides on trip.cold_start and the create() response.
Measured: Mangalore, 28 Aug — 23 places, 12 paragraphs, 32.0 s, $0.0092; the second request found the rows.
seed.py refuses to run while ai_generated rows exist unless --include-ai-generated is passed.

## Plan page (app/web.py, app/templates/trip.html, init.trip)
POST /api/trips/{id}/narrate writes the plan up "In a few words" with narrate_plan (checked against the
plan; the traveller's notes, food, trip type, must-see and skip are in its input), stores it once on
trip.narration, and a chat edit clears it; a narration that fails its check is a 502 and the block stays
hidden. Every day carries a getting-around line (app/planner/transport.py): the traveller's choice wins, on
'suggest' an elder or toddler means cabs, a low per-head budget means autos and public transport, else cabs;
costed from the hops inside the city, estimated, shown and NOT added to the total or validated. Stops with
trust ai_generated wear "AI-drafted · unverified" and their why ends "Hours and fee are the model's draft, not
verified." Eyebrows read "2 adults (one over 60), 1 child" from travellers ("N people" for old trips); the
chooser says "the evenings you asked for"; the doesn't-fit page renders a cold-start verdict without a map.
Maps (mapInto in ty.js): Leaflet 1.9.4 self-hosted in app/static/leaflet (loaded on signed-in pages only) over
CARTO Positron tiles — no key, no account — on the plan day map (numbered pins, hard stops ringed laterite,
routed solid / as-listed dashed, the transfer as a dashed line with its duration), the doesn't-fit legs, the Katha
coverage map (a pin per region with its place count) and the Katha locator (the lit place, later ones dimmed).
The SVG sketch is drawn first and stays underneath; if no tile loads within four seconds the map is removed and
the sketch remains (verified with the tile host blocked). The landing page keeps the SVG and makes no request.

## Katha (app/katha/build.py, app/katha/city_layer.py, data/chunks_city.json)
A city Katha is a fixed portrait: the city's theme/tier rows (identity, origins, rulers, character, food,
festivals, worth_seeing, practical; tiers 2, 5, 10) in theme order, every row whose tier fits the minutes —
no retrieval, no rhythm rules, no variation; depth is ignored; the same city and minutes always tell the same
story. Each hub has 14 paragraphs (31 new + 39 retagged from the existing corpus); a worth_seeing paragraph
is filed under the place it opens with so "Go deeper" and the pin resolve. A city with no layer tries the
cold-start drafter, else falls back to its places and says so. Place and day Kathas keep retrieval under three
rhythm rules: no paragraph repeats; open on a hook or a story when there is one; a story in five minutes or
more. The player shows no type or legend chips; a legend's source line says "As the story goes ·"; the depth
picker is hidden for a city; the lede reads "Mysuru in 5 minutes — what it is, who made it, what it eats,
what is worth your time." warm_tts re-run 28 Aug: 17 of 18 segments passed the fact-check (en 8/9, kn 9/9).

## Planner (app/planner/) — core unchanged
k-means → NN → 2-opt → validate → repair, untouched this run. intercity_move() raises ValueError('unknown
city: X') instead of a KeyError; centroids come from poi averages first and city_centre for the rest.
Canonical demo trip (Bengaluru → Mysuru & Srirangapatna, 3 days from 14 Sep 2026, 2 adults 40-59 + 1 adult
60+ + 1 child 6-12, family, comfortable, ₹18,000, heritage + food, cabs): as listed 34.98 km | nearest-next
30.9 km | routed 30.9 km | repairs 3 | candidates 27 of 135 | checks 37/37 | build 4 ms. Day 2: 10.53 → 6.45 km.

## Retrieval — re-measured after the city layer (eval_run 10, 28 Aug)
Dense + lexical fused with RRF k=60; refusal below 0.81 cosine with no strict lexical match. 30 written
questions: dense Recall@5 0.867 / MRR 0.753 / p50 69 ms; lexical 0.600 / 0.473 / 57 ms; hybrid 0.867 / 0.753
/ p50 129 ms (p95 154). 10 name lookups: dense 0.900 / 0.907; lexical 0.900 / 0.783; hybrid 0.900 / 0.857.
By language (hybrid): English 0.857, Kannada 0.833, Hinglish 1.000. Refusal gate 6/6. Hybrid ties dense; it
does not beat it. Against the previous run: Recall@5 unchanged, MRR 0.772 → 0.753, p50 110 → 129 ms.

## Accounts (app/accounts.py) — unchanged
Four @travelyantra.in accounts seeded from DEMO_PASSWORD; signed cookie; every /api route behind it; a trip
or Katha someone else owns is a 404; /health and the landing page stay open.

## Review 1 deliverables (docs/review1/)
`Travel_Yantra_Phase2_Review1.pptx` from `uv run python scripts/build_deck.py` (template slides only reused or
duplicated; numbers from docs/review1/numbers.md), `Travel_Yantra_Phase2_Review1_Script.md` (10 minutes: about
6 speaking, 2 demo, 2 Q&A), docs/review1/numbers.md (every figure with the command it came from), screenshots
01–20 plus the 28 Aug captures (04b–07c, 08b, 09b–09f, 10b, 12b, 14b, 15b, 17b, 17c, 19b, 19c).

Known issue: RLS disabled on every public table; enable before the anon key is used.
Known limit: 92 draft places are unverified and labelled estimated; 23 Mangalore places are model-drafted and
labelled AI-drafted · unverified until a verification pass promotes them.
Known limit: the getting-around cost is shown, estimated, and not yet counted against the budget.
Known limit: must_see reaches the narrator and the chat, not the solver.
Known limit: routes are drawn as straight segments between stops, on tiles or on the sketch; kilometres use a
detour factor. Tiles need the network; the sketch does not.
Known limit: a cold-started destination has no intercity_leg row, so the transfer is the formula
(Bengaluru → Mangalore comes out at 536 minutes by train, estimated).
Known limit: 54 retired doc_chunk rows await `DELETE FROM doc_chunk WHERE retired` — Rohan's call.
Not yet: Objectives 2, 3, 4 (five languages, WhatsApp and voice, live booking); Hindi voice end to end; RLS;
sign-up; deployment (post-review by decision); OpenStreetMap as the place source for Review 2.
Next step (estimated): the review at 11:00; then count getting-around against the budget and validate it.
Updated: 2026-08-28

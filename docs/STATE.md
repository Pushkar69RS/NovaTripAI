# travel-yantra — STATE
Project: travel-yantra
Purpose: AI travel planner + Karnataka virtual guide for BCS705 Phase-2 Review 1 on 28 Aug 2026.
Stack: Python 3.12 (uv), FastAPI, pydantic, httpx, psycopg, numpy, sentence-transformers, pgvector; ruff + pytest.
Services: Supabase Postgres 17 + pgvector + pg_trgm (project puzbpzdamygjosugoeeb, ap-south-1, session pooler on 5432); OpenRouter (three jobs, see app/llm/models.py); Sarvam bulbul:v3 for speech; embeddings local (intfloat/multilingual-e5-small, cached, offline).
Gates: `uv run ruff check .`, `uv run ruff format --check .`, `uv run pytest` — all pass (81 tests).
Preflight: `uv run python scripts/check_env.py` before any DB or LLM task.
DB: poi 112, poi_edge 58, intercity_leg 40, advisory 1, doc_chunk 311 rows of which 257 live (54 retired, not deleted), trip and tour rows from the API, eval_run 9.
Migrations: 001 core, 002 doc_chunk (city,title) key, 003 aliases in body_tsv, 004 doc_chunk.retired + tour.language/scope/total_words.

## Corpus (data/chunks_curated.json + data/chunks.json → doc_chunk)
257 live paragraphs: 45 curated by Rohan (authoritative, loaded first, never rewritten; only
source_url was attached, 24 of them, 19/20 fact+practical) and 212 generated around them.
56 generated drafts that overlapped a curated paragraph for the same place were dropped from
chunks.json; their rows are `retired`, retrieval ignores them, DELETE is Rohan's call.
By city (live): Mysuru 70, Hampi 62, Chikmagalur 55 (Belur/Halebidu under the hub city), Bengaluru 45, Coorg 25.
Curated localities (Srirangapatna, Belur, Halebidu) and short names (Chamundi Hill, Vittala Temple…)
are mapped to the poi table on load in scripts/seed_chunks.py; the file keeps its own words.

## Planner (app/planner/) — unchanged, plus `rebuild_day()` and a `day_start` on build_day
Pure, no LLM, no write. Deterministic k-means → NN → 2-opt → validate → repair. `rebuild_day()`
runs steps 3–6 for one day only so a chat edit can leave every other Day object untouched.

## Retrieval (app/rag/) — unchanged, plus `NOT retired`
Dense (pgvector HNSW) + lexical (tsvector, strict then OR fallback) fused with RRF k=60; refusal
below 0.81 cosine with no strict lexical match. Eval (eval_run id=9, 311-row table, 30 questions):

    A. 30 written questions      Recall@5   MRR    p50 ms   p95 ms
       dense only                   0.867  0.761     76.6   3827.2*
       lexical only                 0.633  0.551     57.3    106.0
       hybrid + RRF                 0.867  0.772    110.0    115.1
    B. 10 name/keyword lookups      0.900 / 0.900 / 0.900 Recall@5 (dense / lexical / hybrid)
    refusal gate 6/6.  * one network stall; p50 is the honest number.

Down from 0.933 before the merge: three curated answers phrase things differently from the
questions, and the Kannada "stone chariot" query no longer lands in the top 20 (e5-small on a
short Kannada query against a paragraph that never says Hampi or Vittala in the body).

## Katha builder (app/katha/build.py) — scheduling, no creativity
budget = minutes × 145 words. Spine: place → 5 themes (quick) or 7 (deep); city → a city-level
opener + top places by popularity capped 2/4/6 by duration; day → the trip's stops in order.
Budget split by popularity, floor 90 words, tail items dropped if they cannot be paid. Retrieval
per item carries exclude_ids forward; a thin place may borrow city-level paragraphs and the
segment is then labelled as the city. Rhythm rules are enforced in `arrange()` and re-checked by
`check_rhythm()` (the tests call it directly): opens on hook|story, no adjacent same type, ≥5 min
needs a story and a taste|sensory, quick favours hook/story/taste, deep favours fact/sensory and
longer segments. A second pass fills to 85% of budget. Demo: `uv run python -m app.katha.build --demo`.

## Narrator (app/llm/) — two jobs, one fact-check
`narrate_plan()` and `narrate_segment()` via OpenRouter. Post-check flags any number or year not in
the input (Indic digits normalised), any capitalised English name not in the input, any %, and a
completion cut off by the token cap. Failure → retry at temperature 0 → fallback to the retrieved
text lightly joined. Legends get "The story goes" / "ಕಥೆಯ ಪ್ರಕಾರ" / "कहते हैं" prepended if missing.
Kannada/Hindi names cannot be checked (no capitals, transliterated); documented, not hidden.
`app/llm/models.py` maps job → model. `narrate_katha` is still deepseek/deepseek-chat (the model
check_env verifies) pending Rohan's pick from `scripts/pick_model.py`, which ran three current
models on one Mysore Palace segment in Kannada and chose nothing.

## Voice (app/voice/tts.py)
Sarvam bulbul:v3, speaker roopa, 22050 Hz WAV, ≤2000-char pieces joined with `wave`. Cached in
var/tts/<sha256(voice,lang,text)>.wav (gitignored). Any error → None → browser speech.
`scripts/warm_tts.py` builds the 5-min Mysuru Katha, narrates it in en and kn, caches both, and
writes var/tts/demo_en.json and demo_kn.json for an offline demo.

## Chat (app/chat/router.py)
Messages without an edit verb are Questions and never reach the model. Edits are parsed by the
model into strict JSON, validated, resolved against the real plan (one clarifying question on any
doubt), then applied with `rebuild_day()`. Other days are the same objects, so byte-identical by
construction; tests assert it on the serialised days.

## API (app/api/routes.py)
POST /api/trips, GET /api/trips/{id}, POST /api/trips/{id}/chat, POST /api/katha, GET /api/katha/{id},
POST /api/katha/{id}/audio (204 when speech is unavailable), GET /api/places/search?q= (pg_trgm),
GET /health. Trips persist in `trip`, Kathas in `tour`. Smoke-tested end to end against the DB.

Known issue: RLS disabled on every public table; enable before the anon key is used.
Known limit: 54 retired doc_chunk rows await `DELETE FROM doc_chunk WHERE retired` — Rohan's call.
Known limit: `scripts/seed.py` refuses to run while doc_chunk has rows (FK); by design.
Not yet: frontend, plan narration surfaced in the API, Hindi voice tested end to end, RLS.
Next step (estimated): the frontend over these routes; Rohan's Kannada model pick.
Updated: 2026-08-28

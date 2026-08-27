# Decisions

- 2026-08-27 — Form-first intake: a structured form collects trip constraints before any chat.
- 2026-08-27 — Planner is deterministic (cluster + 2-opt + validator); the LLM only parses chat edits and narrates.
- 2026-08-27 — Supabase Postgres + pgvector is the single store (relational data and vectors).
- 2026-08-27 — Hybrid retrieval (full-text + vector) fused with Reciprocal Rank Fusion (RRF).
- 2026-08-27 — Embeddings computed locally with intfloat/multilingual-e5-small; no embedding API.
- 2026-08-27 — Demo runs on localhost for the review; Vercel deployment comes post-review.
- 2026-08-27 — No orchestration framework (LangChain, LlamaIndex, etc.) in v1.
- 2026-08-27 — poi.city is the hub city (Mysuru, Hampi, Bengaluru, Chikmagalur, Coorg) used for clustering and intercity legs; the locality (Srirangapatna, Belur, Halebidu, Kushalnagar...) lives in the name and tags.
- 2026-08-27 — Extensions live in the `extensions` schema (Supabase convention); the migration references `extensions.vector` explicitly so nothing depends on search_path.
- 2026-08-27 — seed.py is a full reload (TRUNCATE ... RESTART IDENTITY of poi, poi_edge, intercity_leg, advisory). doc_chunk is included only while it is empty (Postgres requires it because of the FK); once it has rows the seed aborts and asks.
- 2026-08-27 — Web verification (Tavily) covers only the top-20 Mysuru/Hampi POIs; a verified row cites exactly one source_url and the report lists disagreeing sources. Everything else stays trust=draft and is labelled estimated.

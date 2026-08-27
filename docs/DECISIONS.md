# Decisions

- 2026-08-27 — Form-first intake: a structured form collects trip constraints before any chat.
- 2026-08-27 — Planner is deterministic (cluster + 2-opt + validator); the LLM only parses chat edits and narrates.
- 2026-08-27 — Supabase Postgres + pgvector is the single store (relational data and vectors).
- 2026-08-27 — Hybrid retrieval (full-text + vector) fused with Reciprocal Rank Fusion (RRF).
- 2026-08-27 — Embeddings computed locally with intfloat/multilingual-e5-small; no embedding API.
- 2026-08-27 — Demo runs on localhost for the review; Vercel deployment comes post-review.
- 2026-08-27 — No orchestration framework (LangChain, LlamaIndex, etc.) in v1.

# CLAUDE.md — travel-yantra rulebook

Reload this every session. These rules are non-negotiable.

1. Start every reply with "Rohan".
2. Before finishing any task, run in order and fix any failures:
   - `uv run ruff check .`
   - `uv run ruff format --check .`
   - `uv run pytest`
3. Commit small with imperative messages; push at the end of every task.
4. Never run destructive DB operations (DROP, DELETE, TRUNCATE, resets) without asking Rohan first.
5. Never put secrets in code or commits — env vars only (see `.env.example`).
6. When a fact could be stale, label it "estimated" rather than asserting it.
7. `docs/STATE.md` stays under 150 lines and is rewritten, not appended.

## Preflight

Run `uv run python scripts/check_env.py` before any task that touches the database or an LLM. It is read-only, masks every secret, and exits 1 on any FAIL.

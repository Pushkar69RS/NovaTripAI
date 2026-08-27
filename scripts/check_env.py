"""Read-only preflight: verify the secrets in .env actually work.

    uv run python scripts/check_env.py

Never prints a secret in full. Makes no changes to the database.
Exit code 0 when every check is PASS or WARN, 1 when any check FAILs.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from urllib.parse import unquote, urlsplit

import httpx
import psycopg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
OPENROUTER = "https://openrouter.ai/api/v1"
POOLER_HOST = "pooler.supabase.com"

# Substring of a Postgres error message -> the usual cause.
DB_HINTS = [
    ("authentication failed", "wrong password"),
    (
        "tenant/user",
        "wrong project ref in the username (postgres.<ref>) or wrong pooler region",
    ),
    ("could not translate host name", "wrong host"),
    (
        "unreachable",
        "likely the IPv6-only direct connection; switch to the session pooler URL",
    ),
    ("timeout", "firewall, or the Supabase project is paused"),
    ("timed out", "firewall, or the Supabase project is paused"),
]

SECRETS: list[str] = []  # filled by main(); every printed line is redacted against it


def mask(secret: str | None) -> str:
    """First 8 and last 4 characters only; short values are hidden entirely."""
    if not secret:
        return "<empty>"
    if len(secret) <= 12:
        return "*" * len(secret)
    return f"{secret[:8]}...{secret[-4:]}"


def out(line: str) -> None:
    for secret in SECRETS:
        line = line.replace(secret, mask(secret))
    print(line)


def check_db_url(url: str) -> str:
    """Check 1: shape of SUPABASE_DB_URL, offline."""
    if not url:
        out("  SUPABASE_DB_URL is missing or empty")
        return "FAIL"
    if "[YOUR-PASSWORD]" in url:
        out("  SUPABASE_DB_URL still contains the [YOUR-PASSWORD] placeholder")
        return "FAIL"
    u = urlsplit(url)
    try:
        host, port = u.hostname, u.port or 5432
    except ValueError:
        host, port = None, None
    if not host:
        out(
            "  could not parse host/port; percent-encode special characters in the password"
        )
        return "FAIL"
    db = u.path.lstrip("/") or "<none>"
    out(
        f"  host={mask(host)} port={port} user={mask(u.username)} db={db} "
        f"password={mask(u.password)}"
    )
    status = "PASS"
    if POOLER_HOST not in host:
        out(
            f"  WARN host is not the session pooler ({POOLER_HOST}); the direct connection "
            "is IPv6-only and usually unreachable from Indian home broadband"
        )
        status = "WARN"
    if port == 6543:
        out(
            "  WARN port 6543 is the transaction pooler (no prepared statements); expected 5432"
        )
        status = "WARN"
    return status


def check_db_connect(url: str) -> str:
    """Check 2: connect and read server facts. SELECT only, read-only transaction."""
    try:
        with psycopg.connect(url, connect_timeout=10) as conn:
            conn.read_only = True
            with conn.cursor() as cur:
                version = cur.execute("SELECT version()").fetchone()[0]
                database, now = cur.execute(
                    "SELECT current_database(), now()"
                ).fetchone()
                exts = {
                    name: (default, installed)
                    for name, default, installed in cur.execute(
                        "SELECT name, default_version, installed_version "
                        "FROM pg_available_extensions WHERE name IN ('vector', 'pg_trgm')"
                    )
                }
                tables = [
                    t
                    for (t,) in cur.execute(
                        "SELECT tablename FROM pg_tables "
                        "WHERE schemaname = 'public' ORDER BY tablename"
                    )
                ]
    except psycopg.Error as exc:
        # libpq repeats the error once per resolved IP; the first line says it all.
        message = str(exc).strip().splitlines()[0]
        hint = next(
            (h for needle, h in DB_HINTS if needle in message.lower()),
            "unrecognised error; check the URL and the Supabase dashboard",
        )
        out(f"  {type(exc).__name__}: {message}")
        out(f"  hint: {hint}")
        return "FAIL"
    out(f"  server: {version}")
    out(f"  database={database} now={now}")
    for name in ("vector", "pg_trgm"):
        if name not in exts:
            out(f"  extension {name}: NOT AVAILABLE")
            continue
        default, installed = exts[name]
        state = f"INSTALLED ({installed})" if installed else "NOT INSTALLED"
        out(f"  extension {name}: AVAILABLE (default {default}), {state}")
    out(f"  public tables: {', '.join(tables) or '(none)'}")
    return "PASS"


def check_openrouter(key: str, model: str) -> str:
    """Check 3: key validity, then a minimal chat completion."""
    if not key:
        out("  OPENROUTER_API_KEY is missing or empty")
        return "FAIL"
    headers = {"Authorization": f"Bearer {key}"}
    with httpx.Client(base_url=OPENROUTER, headers=headers, timeout=30) as client:
        try:
            r = client.get("/key")
        except httpx.HTTPError as exc:
            out(f"  {type(exc).__name__}: {exc}")
            return "FAIL"
        if r.status_code == 401:
            out("  401 Unauthorized: the key is wrong or has been revoked")
            return "FAIL"
        if r.status_code != 200:
            out(f"  HTTP {r.status_code}: {r.text[:200]}")
            return "FAIL"
        d = r.json().get("data", {})
        remaining = d.get("limit_remaining")
        out(
            f"  key={mask(key)} label={d.get('label')!r} usage=${d.get('usage')} "
            f"limit={d.get('limit')} remaining={'no limit set' if remaining is None else remaining}"
        )
        if not model:
            out("  WARN OPENROUTER_MODEL is empty; chat test skipped")
            return "WARN"
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": "Reply with the single word: ok"}],
            "max_tokens": 5,
            "temperature": 0,
        }
        try:
            r = client.post("/chat/completions", json=payload)
            r.raise_for_status()
            body = r.json()
            reply = (body["choices"][0]["message"]["content"] or "").strip()
        except httpx.HTTPStatusError as exc:
            reason = f"HTTP {exc.response.status_code}: {exc.response.text[:200]}"
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
            reason = f"{type(exc).__name__}: {exc}"
        else:
            out(f"  chat: model={body.get('model')} reply={reply!r}")
            return "PASS"
    out(f"  WARN chat test failed for {model}: {reason}")
    out("  the narration model is still being chosen and will be finalised later")
    return "WARN"


def check_hygiene(secrets: list[str]) -> str:
    """Check 4: .env is ignored and no tracked file contains a secret."""
    status = "PASS"
    ignored = (
        subprocess.run(
            ["git", "check-ignore", "-q", ".env"], cwd=ROOT, check=False
        ).returncode
        == 0
    )
    listing = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True
    )
    tracked = [t for t in listing.stdout.decode().split("\0") if t]
    if not ignored or ".env" in tracked:
        out(
            "  !!! FAIL .env is not ignored by git (or is already tracked); fix .gitignore first"
        )
        status = "FAIL"
    else:
        out("  .env is ignored by git")
    needles = [s.encode() for s in secrets]
    leaks = [
        t
        for t in tracked
        if (ROOT / t).is_file() and any(n in (ROOT / t).read_bytes() for n in needles)
    ]
    if leaks:
        out(
            f"  !!! FAIL secret found in tracked files: {', '.join(leaks)}; remove and rotate it"
        )
        status = "FAIL"
    else:
        out(f"  no secret found in {len(tracked)} tracked files")
    return status


def run(title: str, check: Callable[[], str]) -> str:
    out(f"== {title}")
    status = check()
    out(f"-> {status}\n")
    return status


def main() -> int:
    load_dotenv(ROOT / ".env")
    db_url = os.environ.get("SUPABASE_DB_URL", "").strip()
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    model = os.environ.get("OPENROUTER_MODEL", "").strip()
    password = (urlsplit(db_url).password or "") if db_url else ""
    SECRETS.extend(dict.fromkeys(s for s in (key, password, unquote(password)) if s))

    r1 = run("Check 1: DB URL shape", lambda: check_db_url(db_url))

    def db_connect() -> str:
        if r1 == "FAIL":
            out("  skipped: SUPABASE_DB_URL is unusable (see check 1)")
            return "FAIL"
        return check_db_connect(db_url)

    r2 = run("Check 2: DB connectivity", db_connect)
    r3 = run("Check 3: OpenRouter", lambda: check_openrouter(key, model))
    r4 = run("Check 4: secret hygiene", lambda: check_hygiene(SECRETS))

    results = {
        "DB URL shape": r1,
        "DB connectivity": r2,
        "OpenRouter": r3,
        "Secret hygiene": r4,
    }
    out("== Summary")
    for name, status in results.items():
        out(f"  {status:4} {name}")
    fails = sum(s == "FAIL" for s in results.values())
    warns = sum(s == "WARN" for s in results.values())
    out(f"  {fails} FAIL, {warns} WARN, {len(results) - fails - warns} PASS")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())

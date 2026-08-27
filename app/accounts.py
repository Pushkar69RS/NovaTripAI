"""The four team accounts, their passwords, and the session cookie.

No sign-up and no reset: scripts/seed_users.py writes the four rows and this
module reads them. The plaintext password never reaches the database — only a
salted PBKDF2 digest — and the cookie carries a user id signed with
DEMO_PASSWORD, so a changed password invalidates every session.
"""

from __future__ import annotations

import hashlib
import hmac
import os
from typing import Any

from pydantic import BaseModel

ITERATIONS = 200_000
ALGORITHM = "pbkdf2_sha256"
COOKIE = "ty_session"

#: The team, in USN order. Emails are firstname@travelyantra.in.
TEAM: list[tuple[str, str]] = [
    ("Nithin G", "nithin@travelyantra.in"),
    ("Pushkar Reddy S", "pushkar@travelyantra.in"),
    ("Rishab Paul", "rishab@travelyantra.in"),
    ("Rohan Balu", "rohan@travelyantra.in"),
]


class User(BaseModel):
    id: int
    email: str
    name: str

    @property
    def first(self) -> str:
        return self.name.split()[0]

    @property
    def initials(self) -> str:
        parts = self.name.split()
        return (parts[0][0] + (parts[-1][0] if len(parts) > 1 else "")).upper()


def hash_password(password: str, salt: bytes | None = None) -> str:
    """`pbkdf2_sha256$<iterations>$<salt>$<digest>`, all hex."""
    salt = salt or os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, ITERATIONS)
    return f"{ALGORITHM}${ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Constant-time check of a password against a stored hash."""
    try:
        algorithm, iterations, salt, digest = stored.split("$")
        if algorithm != ALGORITHM:
            return False
        again = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), bytes.fromhex(salt), int(iterations)
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(again.hex(), digest)


# --------------------------------------------------------------------------- #
# the session cookie: "<user id>.<signature>"
# --------------------------------------------------------------------------- #


def _secret() -> str:
    return os.environ.get("DEMO_PASSWORD", "")


def sign(user_id: int) -> str | None:
    """The cookie value for a user, or None when no DEMO_PASSWORD is set."""
    secret = _secret()
    if not secret:
        return None
    mac = hmac.new(secret.encode(), str(user_id).encode(), hashlib.sha256).hexdigest()
    return f"{user_id}.{mac}"


def unsign(cookie: str) -> int | None:
    """The user id a cookie carries, or None when it is missing or forged."""
    if not cookie or "." not in cookie:
        return None
    raw, _, _mac = cookie.partition(".")
    if not raw.isdigit():
        return None
    expected = sign(int(raw))
    if expected is None or not hmac.compare_digest(cookie, expected):
        return None
    return int(raw)


# --------------------------------------------------------------------------- #
# lookups
# --------------------------------------------------------------------------- #


def by_email(conn: Any, email: str) -> tuple[User, str] | None:
    """(user, password hash) for an email address, or None."""
    row = conn.execute(
        "SELECT id, email, name, password_hash FROM app_user WHERE lower(email) = %s",
        (email.strip().lower(),),
    ).fetchone()
    if not row:
        return None
    return User(id=row[0], email=row[1], name=row[2]), row[3]


def by_id(conn: Any, user_id: int) -> User | None:
    row = conn.execute(
        "SELECT id, email, name FROM app_user WHERE id = %s", (user_id,)
    ).fetchone()
    return User(id=row[0], email=row[1], name=row[2]) if row else None


def from_cookie(conn: Any, cookie: str) -> User | None:
    """The signed-in user a request's cookie names, or None."""
    user_id = unsign(cookie)
    return by_id(conn, user_id) if user_id is not None else None


def authenticate(conn: Any, email: str, password: str) -> User | None:
    """The user when the password matches, or None. Never says which was wrong."""
    found = by_email(conn, email)
    if found is None or not _secret():
        return None
    user, stored = found
    return user if verify_password(password, stored) else None

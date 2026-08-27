"""Password hashing and the session cookie, offline."""

from __future__ import annotations

import pytest

from app.accounts import TEAM, User, hash_password, sign, unsign, verify_password


@pytest.fixture
def secret(monkeypatch):
    monkeypatch.setenv("DEMO_PASSWORD", "pw")
    return "pw"


def test_the_team_is_four_firstname_addresses() -> None:
    assert len(TEAM) == 4
    assert [e for _, e in TEAM] == [
        "nithin@travelyantra.in",
        "pushkar@travelyantra.in",
        "rishab@travelyantra.in",
        "rohan@travelyantra.in",
    ]


def test_a_hash_verifies_only_its_own_password() -> None:
    stored = hash_password("yantra-2026")
    assert stored.startswith("pbkdf2_sha256$")
    assert "yantra-2026" not in stored  # the plaintext never reaches the column
    assert verify_password("yantra-2026", stored)
    assert not verify_password("yantra-2025", stored)
    assert not verify_password("", stored)
    assert not verify_password("yantra-2026", "not-a-hash")
    assert hash_password("x") != hash_password("x")  # salted


def test_a_cookie_round_trips_and_a_forged_one_does_not(secret) -> None:
    cookie = sign(7)
    assert cookie is not None and cookie.startswith("7.")
    assert unsign(cookie) == 7
    assert unsign("8." + cookie.split(".")[1]) is None  # another user's signature
    assert unsign("7.deadbeef") is None
    assert unsign("7") is None
    assert unsign("") is None


def test_without_a_demo_password_nothing_is_signed(monkeypatch) -> None:
    monkeypatch.delenv("DEMO_PASSWORD", raising=False)
    assert sign(1) is None
    assert unsign("1.anything") is None


def test_the_avatar_initials_come_from_the_name() -> None:
    assert User(id=1, email="a@b", name="Rohan Balu").initials == "RB"
    assert User(id=2, email="a@b", name="Pushkar Reddy S").initials == "PS"
    assert User(id=3, email="a@b", name="Nithin G").first == "Nithin"

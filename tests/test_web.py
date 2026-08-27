"""The pages: the session gate, sign-in, and a self-contained landing page."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.routes import db
from app.main import app
from app.web import COOKIE, daterange, session_token, short

client = TestClient(app)
EMAIL = "rohan@travelyantra.in"


class NoRows:
    """A connection with an empty database, enough for the public pages."""

    def execute(self, *_args, **_kwargs):
        return self

    def fetchone(self):
        return None

    def fetchall(self):
        return []

    def __iter__(self):
        return iter([])


@pytest.fixture
def password(monkeypatch):
    monkeypatch.setenv("DEMO_PASSWORD", "pw")
    return "pw"


@pytest.fixture
def empty_db():
    app.dependency_overrides[db] = lambda: NoRows()
    yield
    app.dependency_overrides.clear()


def test_app_pages_redirect_to_signin_without_a_session(password) -> None:
    for path in ("/home", "/trips/new", "/saved", "/katha", "/trips/x", "/katha/x"):
        r = client.get(path, follow_redirects=False)
        assert r.status_code == 303, path
        assert r.headers["location"] == f"/signin?next={path}"


def test_signin_sets_the_cookie_and_a_wrong_password_does_not(password) -> None:
    bad = client.post(
        "/signin", data={"email": EMAIL, "password": "nope"}, follow_redirects=False
    )
    assert bad.status_code == 401
    assert COOKIE not in bad.cookies
    assert "not it. One seeded account" in bad.text  # Jinja escapes the apostrophe

    ok = client.post(
        "/signin",
        data={"email": EMAIL, "password": password, "next": "/saved"},
        follow_redirects=False,
    )
    assert ok.status_code == 303
    assert ok.headers["location"] == "/saved"
    assert ok.cookies.get(COOKIE) == session_token()


def test_an_open_redirect_in_next_is_ignored(password) -> None:
    r = client.post(
        "/signin",
        data={"email": EMAIL, "password": password, "next": "//evil.example"},
        follow_redirects=False,
    )
    assert r.headers["location"] == "/home"


def test_no_demo_password_means_nobody_signs_in(monkeypatch) -> None:
    monkeypatch.delenv("DEMO_PASSWORD", raising=False)
    r = client.post(
        "/signin", data={"email": EMAIL, "password": ""}, follow_redirects=False
    )
    assert r.status_code == 401
    assert session_token() is None


def test_the_landing_page_is_public_and_makes_no_external_request(empty_db) -> None:
    r = client.get("/")
    assert r.status_code == 200
    assert "fonts.googleapis" not in r.text and "gstatic" not in r.text
    assert "http://" not in r.text and "https://" not in r.text
    assert "/static/fonts.css" in r.text
    assert "No trip yet" in r.text  # honest empty state, nothing hardcoded


def test_health_stays_open() -> None:
    assert client.get("/health").status_code == 200


def test_formatting_helpers() -> None:
    assert daterange("2026-09-14", 3) == "14–16 Sep"
    assert daterange("2026-09-30", 2) == "30 Sep–1 Oct"
    assert daterange("2026-09-14", 1) == "14 Sep"
    assert short("Hotel RRR, Gandhi Square") == "Hotel RRR"
    assert short("Brindavan Gardens (KRS Dam)") == "Brindavan Gardens"

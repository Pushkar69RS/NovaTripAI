"""The pages: the session gate, sign-in, and a self-contained landing page."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.accounts import COOKIE, hash_password, sign
from app.api.routes import db
from app.main import app
from app.web import daterange, short

client = TestClient(app)
EMAIL = "rohan@travelyantra.in"
PASSWORD = "pw"


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


class OneUser(NoRows):
    """A connection that knows exactly one account: Rohan, with PASSWORD."""

    ROW = (4, EMAIL, "Rohan Balu", hash_password(PASSWORD))

    def execute(self, query, params=None, *_a, **_k):
        self.query, self.params = query, params
        return self

    def fetchone(self):
        q = self.query
        if "FROM app_user" in q and "password_hash" in q:
            return self.ROW if self.params[0] == EMAIL else None
        if "FROM app_user" in q:
            return self.ROW[:3] if self.params[0] == 4 else None
        if "count(*)" in q:
            return (0,)
        return None


@pytest.fixture
def password(monkeypatch):
    monkeypatch.setenv("DEMO_PASSWORD", PASSWORD)
    app.dependency_overrides[db] = lambda: OneUser()
    yield PASSWORD
    app.dependency_overrides.clear()


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


def test_the_api_needs_the_same_cookie_and_health_does_not(password) -> None:
    for path in ("/api/trips/x", "/api/katha/x", "/api/places/search"):
        assert client.get(path).status_code == 401, path
    assert client.post("/api/trips", json={}).status_code == 401
    assert client.get("/health").status_code == 200


def test_signin_sets_the_cookie_and_a_wrong_password_does_not(password) -> None:
    bad = client.post(
        "/signin", data={"email": EMAIL, "password": "nope"}, follow_redirects=False
    )
    assert bad.status_code == 401
    assert COOKIE not in bad.cookies
    assert "not it. Four seeded accounts" in bad.text  # Jinja escapes the apostrophe

    unknown = client.post(
        "/signin",
        data={"email": "nobody@travelyantra.in", "password": password},
        follow_redirects=False,
    )
    assert unknown.status_code == 401

    ok = client.post(
        "/signin",
        data={"email": EMAIL, "password": password, "next": "/saved"},
        follow_redirects=False,
    )
    assert ok.status_code == 303
    assert ok.headers["location"] == "/saved"
    assert ok.cookies.get(COOKIE) == sign(4)


def test_an_open_redirect_in_next_is_ignored(password) -> None:
    r = client.post(
        "/signin",
        data={"email": EMAIL, "password": password, "next": "//evil.example"},
        follow_redirects=False,
    )
    assert r.headers["location"] == "/home"


def test_no_demo_password_means_nobody_signs_in(monkeypatch, empty_db) -> None:
    monkeypatch.delenv("DEMO_PASSWORD", raising=False)
    r = client.post(
        "/signin", data={"email": EMAIL, "password": ""}, follow_redirects=False
    )
    assert r.status_code == 401
    assert sign(1) is None


def test_the_landing_page_is_public_and_makes_no_external_request(empty_db) -> None:
    r = client.get("/")
    assert r.status_code == 200
    assert "fonts.googleapis" not in r.text and "gstatic" not in r.text
    assert "http://" not in r.text and "https://" not in r.text
    assert "/static/fonts.css" in r.text
    assert "No trip yet" in r.text  # honest empty state, nothing hardcoded


def test_the_form_asks_only_what_the_planner_acts_on(password) -> None:
    client.cookies.set(COOKIE, sign(4))
    r = client.get("/trips/new")
    client.cookies.clear()
    assert r.status_code == 200
    text = r.text.lower()
    for gone in ("leave on day one", "walking", "mornings", "elders"):
        assert gone not in text, gone
    for kept in (
        "tell us about the trip in your own words",
        "fill the form from this",
        "getting around once there",
        "we show what it costs per day, estimated.",
        "how full should the days be",
        "total for everyone",
        "this covers tickets, food and getting around. stay and the journey there are separate.",
        "written up by templates · the ai reads it to you on the next page",
    ):
        assert kept in text, kept


class OneTrip(OneUser):
    """Rohan's one planned trip, with or without its narration."""

    narration: str | None = None

    def fetchone(self):
        q = self.query
        if "FROM trip WHERE id" in q:
            return (
                "t1",
                json.dumps(TRIP_REQUEST),
                "planned",
                json.dumps(TRIP_PLAN),
                None,
                datetime(2026, 8, 28, tzinfo=UTC),
                4,
                self.narration,
                None,
            )
        return super().fetchone()


TRIP_REQUEST = {
    "origin_city": "Bengaluru",
    "destination_cities": ["Mysuru"],
    "start_date": "2026-09-14",
    "days": 1,
    "travellers": [
        {"kind": "adult", "age_band": "40-59"},
        {"kind": "adult", "age_band": "60+"},
        {"kind": "child", "age_band": "6-12"},
    ],
    "budget_inr": 9000,
}
TRIP_PLAN = {
    "days": [
        {
            "index": 1,
            "date": "2026-09-14",
            "city": "Mysuru",
            "items": [],
            "ends_at": "18:00:00",
        }
    ],
    "total_spend": 0,
    "comfort": "comfortable",
    "has_plan_b": False,
    "metrics": {
        "route_km_before": 0,
        "route_km_after": 0,
        "improvement_pct": 0,
        "repair_iterations": 0,
        "candidates_considered": 0,
        "build_ms": 1,
        "constraint_checks_passed": 0,
        "constraint_checks_total": 0,
    },
}


def test_the_plan_page_shows_the_narration_only_when_it_exists(password) -> None:
    conn = OneTrip()
    app.dependency_overrides[db] = lambda: conn
    client.cookies.set(COOKIE, sign(4))
    bare = client.get("/trips/t1")
    assert bare.status_code == 200
    assert "In a few words" not in bare.text
    assert "2 adults (one over 60), 1 child" in bare.text  # not "3 people"
    conn.narration = "Three easy stops and an early evening."
    told = client.get("/trips/t1")
    assert "In a few words" in told.text and conn.narration in told.text
    assert "checked against it" in told.text
    client.cookies.clear()


def test_health_stays_open() -> None:
    assert client.get("/health").status_code == 200


def test_formatting_helpers() -> None:
    assert daterange("2026-09-14", 3) == "14–16 Sep"
    assert daterange("2026-09-30", 2) == "30 Sep–1 Oct"
    assert daterange("2026-09-14", 1) == "14 Sep"
    assert short("Hotel RRR, Gandhi Square") == "Hotel RRR"
    assert short("Brindavan Gardens (KRS Dam)") == "Brindavan Gardens"

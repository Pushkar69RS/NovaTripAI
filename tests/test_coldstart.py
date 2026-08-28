"""Cold start against a fake connection and a scripted model. No network."""

from __future__ import annotations

import json
from datetime import date
from typing import ClassVar

import pytest
from fastapi.testclient import TestClient

from app.accounts import COOKIE, hash_password, sign
from app.api import routes
from app.api.routes import create, db
from app.llm.client import Completion
from app.main import app
from app.planner.coldstart import (
    ColdStartError,
    ensure_city,
    ensure_city_layer,
    valid_places,
)
from app.planner.models import Traveller, TripRequest

CENTRE = (12.8698, 74.8426)  # Mangalore


def place(i: int, **over) -> dict:
    return {
        "name": f"Place {i}",
        "name_kn": None,
        "category": ["temple", "monument", "nature", "food"][i % 4],
        "tags": ["heritage"],
        "typical_dwell_min": 45,
        "entry_fee_inr": 0,
        "opens": "09:00",
        "closes": "17:30",
        "closed_on": [],
        "elderly_friendly": True,
        "popularity": 3,
        "lat": CENTRE[0] + 0.01 * (i % 5),
        "lng": CENTRE[1] + 0.01 * (i // 5),
    } | over


def payload(n: int) -> str:
    return json.dumps(
        {
            "centre": {"lat": CENTRE[0], "lng": CENTRE[1], "name_kn": "ಮಂಗಳೂರು"},
            "places": [place(i) for i in range(n)],
        }
    )


class FakeLlm:
    def __init__(self, *replies: str | Exception) -> None:
        self.replies = list(replies)
        self.calls = 0

    def __call__(self, messages, *, model, temperature, json_mode, **kw) -> Completion:
        self.calls += 1
        reply = self.replies.pop(0) if self.replies else "{}"
        if isinstance(reply, Exception):
            raise reply
        return Completion(reply, model, 100, 900, 0.0004, 1200)


class FakeConn:
    """Just enough Postgres: counts, inserts and the hub centroids."""

    HUBS: ClassVar[list[tuple]] = [
        ("Mysuru", 12.3387, 76.6679),
        ("Bengaluru", 12.9824, 77.5943),
    ]

    def __init__(self) -> None:
        self.pois: dict[str, list[dict]] = {"Mysuru": [{}] * 28, "Bengaluru": [{}] * 23}
        self.centres: dict[str, tuple] = {}
        self.chunks: list[dict] = []
        self.trips: list[tuple] = []
        self.rows: list = []

    def execute(self, sql, params=None, *_a, **_k):
        q = " ".join(sql.split())
        p = params
        self.rows = []
        if "count(*) FROM poi WHERE city = %s" in q:
            self.rows = [(len(self.pois.get(p[0], [])),)]
        elif "FROM city_centre WHERE name" in q:
            self.rows = [(1,)] if p[0] in self.centres else []
        elif "FROM doc_chunk WHERE city = %s AND theme" in q:
            self.rows = [(sum(c["city"] == p[0] for c in self.chunks),)]
        elif q.startswith("INSERT INTO poi"):
            city = p["city"]
            names = {r.get("name") for r in self.pois.get(city, [])}
            if p["name"] not in names:
                self.pois.setdefault(city, []).append(dict(p))
                self.rows = [(len(self.pois[city]),)]
        elif q.startswith("INSERT INTO city_centre"):
            self.centres.setdefault(p[0], tuple(p[1:]))
        elif q.startswith("INSERT INTO doc_chunk"):
            self.chunks.append(dict(p))
        elif q.startswith("INSERT INTO trip"):
            self.trips.append(tuple(p))
            self.rows = [("trip-1",)]
        elif "SELECT city, count(*) FROM poi" in q:
            self.rows = [(c, len(v)) for c, v in self.pois.items()]
        elif "avg(lat), avg(lng) FROM poi GROUP BY city" in q:
            self.rows = list(self.HUBS)
        elif "SELECT id, name FROM poi WHERE city" in q:
            self.rows = [
                (i + 1, r.get("name")) for i, r in enumerate(self.pois.get(p[0], []))
            ]
        elif "FROM app_user" in q:
            self.rows = [
                (4, "rohan@travelyantra.in", "Rohan Balu", hash_password("pw"))
            ]
        return self

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return list(self.rows)

    def __iter__(self):
        return iter(self.rows)


def request(city: str = "Mangalore") -> TripRequest:
    return TripRequest(
        origin_city="Bengaluru",
        destination_cities=[city],
        start_date=date(2026, 9, 14),
        days=2,
        travellers=[Traveller(kind="adult", age_band="40-59")] * 2,
        budget_inr=10000,
    )


def test_twenty_valid_rows_become_ai_generated_places_and_a_centre() -> None:
    conn, llm = FakeConn(), FakeLlm(payload(20), "{}")
    report = ensure_city(conn, "Mangalore", need_places=True, llm=llm)
    assert report.drafted_places >= 8
    assert len(conn.pois["Mangalore"]) == 20
    assert "Mangalore" in conn.centres and conn.centres["Mangalore"][2] == "ಮಂಗಳೂರು"
    assert report.centre == CENTRE and report.cost_usd > 0
    assert report.drafted_paragraphs == 0  # the Katha layer failed soft on "{}"

    again = ensure_city(conn, "Mangalore", need_places=True, llm=llm)
    assert (
        again.drafted_places == 0 and llm.calls == 2
    )  # the second request found the rows


def test_the_origin_gets_only_a_centre() -> None:
    conn, llm = FakeConn(), FakeLlm(payload(0))
    report = ensure_city(conn, "Udupi", need_places=False, llm=llm)
    assert report.drafted_places == 0 and "Udupi" in conn.centres
    assert ensure_city(conn, "Udupi", need_places=False, llm=llm).cost_usd == 0
    assert llm.calls == 1


def test_a_seeded_hub_needs_nothing() -> None:
    llm = FakeLlm()
    assert (
        ensure_city(FakeConn(), "Mysuru", need_places=True, llm=llm).drafted_places == 0
    )
    assert llm.calls == 0


def test_the_rules_drop_far_duplicate_and_bad_rows() -> None:
    rows = [
        place(0),
        place(0),  # duplicate name
        place(1, lat=CENTRE[0] + 2.0),  # 200 km away
        place(2, category="hotel"),
        place(3, opens="9am"),
        "not a row",
    ]
    assert [p["name"] for p in valid_places(rows, CENTRE)] == ["Place 0"]


def test_three_rows_give_a_verdict_not_an_exception() -> None:
    conn = FakeConn()
    out = create(request(), conn, llm=FakeLlm(payload(3), "{}"))
    assert out["status"] == "impossible"
    reasons = {r["label"]: r["value"] for r in out["verdict"]["reasons"]}
    assert reasons["Places we could find in Mangalore"] == 3
    titles = [a["title"] for a in out["verdict"]["alternatives"]]
    assert "Plan Mysuru instead" in titles  # within 300 km of the centre
    assert out["cold_start"][1]["drafted_places"] == 3
    assert conn.trips and conn.trips[0][1] == "impossible"


def test_a_raising_model_gives_the_same_verdict() -> None:
    out = create(request(), FakeConn(), llm=FakeLlm(RuntimeError("no network")))
    assert out["status"] == "impossible"
    assert out["verdict"]["reasons"][0]["label"] == "Could not reach the model"
    assert len(out["verdict"]["alternatives"]) == 2  # every hub when there is no centre
    with pytest.raises(ColdStartError):
        ensure_city(FakeConn(), "Mangalore", need_places=True, llm=FakeLlm("not json"))


def test_the_katha_city_layer_lands_with_a_theme_and_a_tier(monkeypatch) -> None:
    from app.katha.city_layer import DRAFT_SHAPE

    monkeypatch.setattr(
        "app.rag.embed.embed_passages", lambda texts: [[0.0] * 384 for _ in texts]
    )
    body = " ".join(["word"] * 90)
    paragraphs = [
        {
            "theme": theme,
            "tier": tier,
            "title": f"{theme} {tier}",
            "body": body,
            "is_legend": theme == "origins",
            "leads_with": "Place 1" if theme == "worth_seeing" else None,
        }
        for theme, tier in DRAFT_SHAPE
    ]
    conn = FakeConn()
    conn.pois["Mangalore"] = [place(i) for i in range(10)]
    n, cost = ensure_city_layer(
        conn, "Mangalore", llm=FakeLlm(json.dumps({"paragraphs": paragraphs}))
    )
    assert n == 12 and cost > 0
    themes = {(c["theme"], c["tier"]) for c in conn.chunks}
    assert themes == set(DRAFT_SHAPE)
    lead = next(
        c for c in conn.chunks if c["theme"] == "worth_seeing" and c["tier"] == 2
    )
    assert lead["poi_id"] == 2  # "Go deeper" resolves to the place it leads with
    assert all(c["embedding"].startswith("[") for c in conn.chunks)


@pytest.fixture
def signed_in(monkeypatch):
    monkeypatch.setenv("DEMO_PASSWORD", "pw")
    conn = FakeConn()
    app.dependency_overrides[db] = lambda: conn
    client = TestClient(app)
    client.cookies.set(COOKIE, sign(4))
    yield client, conn
    app.dependency_overrides.clear()


def test_the_api_answers_422_with_the_city_name(signed_in, monkeypatch) -> None:
    client, _conn = signed_in
    # A cold start that had nothing to do, and no centre for Xanadu anywhere.
    monkeypatch.setattr(
        routes,
        "ensure_city",
        lambda conn, city, *, need_places, llm: routes.ColdStartReport(
            city=city, poi_count=99
        ),
    )
    r = client.post("/api/trips", json=request("Xanadu").model_dump(mode="json"))
    assert r.status_code == 422
    assert r.json()["detail"] == "unknown city: Xanadu"


def test_coverage_counts_by_typed_name(signed_in) -> None:
    client, _conn = signed_in
    r = client.get(
        "/api/places/coverage", params={"cities": "Mysuru, mangalore,Srirangapatna"}
    )
    assert r.status_code == 200
    assert r.json() == {"Mysuru": 28, "mangalore": 0, "Srirangapatna": 28}

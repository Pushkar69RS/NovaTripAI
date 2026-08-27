"""The deterministic planner, exercised against data/pois.json (no database).

The seed file is the same data the `poi` table holds, so these tests cover the
real planning path without a connection. Ids are the 1-based seed order.
"""

from __future__ import annotations

import json
import random
from datetime import date, time, timedelta
from pathlib import Path

from app.planner.cluster import balance, kmeans
from app.planner.distance import haversine, intercity_move
from app.planner.engine import (
    WEIGHTS,
    attempt,
    build,
    day_pools,
    select_candidates,
)
from app.planner.models import (
    Advisory,
    Leg,
    Move,
    Plan,
    Poi,
    TripRequest,
    Verdict,
)
from app.planner.route import matrices, nearest_neighbour, total, two_opt

DATA = json.loads(
    (Path(__file__).resolve().parents[1] / "data" / "pois.json").read_text(
        encoding="utf-8"
    )
)
POI_FIELDS = set(Poi.model_fields) - {"id", "score"}
NAME_TO_ID = {p["name"]: i for i, p in enumerate(DATA["pois"], 1)}


def pois() -> list[Poi]:
    return [
        Poi(id=i, **{k: v for k, v in p.items() if k in POI_FIELDS})
        for i, p in enumerate(DATA["pois"], 1)
    ]


def edges() -> list[tuple[int, int, float]]:
    return [
        (NAME_TO_ID[e["from"]], NAME_TO_ID[e["to"]], e.get("weight", 1.0))
        for e in DATA["edges"]
    ]


def legs() -> list[Leg]:
    """Both directions, exactly as scripts/seed.py inserts them."""
    return [
        Leg(
            from_city=a,
            to_city=b,
            mode=leg["mode"],
            distance_km=leg.get("distance_km"),
            duration_min=leg["duration_min"],
        )
        for leg in DATA["intercity_legs"]
        for a, b in ((leg["from"], leg["to"]), (leg["to"], leg["from"]))
    ]


def advisories() -> list[Advisory]:
    return [
        Advisory(
            poi_id=NAME_TO_ID.get(a.get("poi", "")),
            city=a.get("city"),
            severity=a["severity"],
            message=a["message"],
        )
        for a in DATA["advisories"]
    ]


def centroids() -> dict[str, tuple[float, float]]:
    out: dict[str, list[tuple[float, float]]] = {}
    for p in DATA["pois"]:
        out.setdefault(p["city"], []).append((p["lat"], p["lng"]))
    return {
        city: (sum(x for x, _ in pts) / len(pts), sum(y for _, y in pts) / len(pts))
        for city, pts in out.items()
    }


def run(request: TripRequest, extra: list[Advisory] | None = None) -> Plan | Verdict:
    return build(
        request, pois(), edges(), legs(), advisories() + (extra or []), centroids()
    )


def next_weekday(start: date, iso: int) -> date:
    while start.isoweekday() != iso:
        start += timedelta(days=1)
    return start


def trip(**over: object) -> TripRequest:
    base = {
        "origin_city": "Bengaluru",
        "destination_cities": ["Mysuru"],
        "start_date": date(2026, 9, 1),
        "days": 2,
        "party_size": 2,
        "pace": "comfortable",
        "budget_inr": 20000,
        "transport": "any",
        "interest_tags": ["heritage", "palace", "food"],
    }
    return TripRequest(**(base | over))


def scatter(n: int, seed: int) -> list[Poi]:
    """n throwaway POIs scattered around Mysuru, for the routing tests."""
    rng = random.Random(seed)
    return [
        Poi(
            id=i,
            name=f"P{i}",
            city="Mysuru",
            lat=12.30 + rng.uniform(-0.15, 0.15),
            lng=76.65 + rng.uniform(-0.15, 0.15),
            category="monument",
            typical_dwell_min=60,
        )
        for i in range(n)
    ]


# --------------------------------------------------------------------------- #
# distance
# --------------------------------------------------------------------------- #


def test_haversine_matches_the_known_bengaluru_mysuru_distance() -> None:
    # Vidhana Soudha to Mysore Palace: about 126 km as the crow flies
    # (the road, at the 1.35 detour factor, lands near the published 145 km).
    km = haversine(12.9716, 77.5946, 12.3052, 76.6552)
    assert 125.0 <= km <= 127.0
    assert haversine(12.3052, 76.6552, 12.3052, 76.6552) == 0.0


def test_intercity_leg_row_beats_the_formula() -> None:
    stored = intercity_move("Bengaluru", "Mysuru", "train", legs(), centroids())
    assert stored.minutes == 120  # the train row, not 227 from the formula
    assert stored.mode == "train"
    assert stored.km == 140.0

    invented = intercity_move(
        "Mysuru",
        "Nowhere",
        "car",
        legs(),
        {
            "Mysuru": (12.3052, 76.6552),
            "Nowhere": (13.3052, 76.6552),
        },
    )
    assert invented.is_estimated is True
    assert invented.minutes > 0


# --------------------------------------------------------------------------- #
# routing
# --------------------------------------------------------------------------- #


def test_two_opt_never_returns_a_longer_route() -> None:
    for seed in range(20):
        stops = scatter(8, seed)
        minutes, _ = matrices(stops)
        before = nearest_neighbour(stops, 0)
        after = two_opt(before, minutes)
        assert total(after, minutes) <= total(before, minutes)
        assert sorted(after) == sorted(before)  # same stops, only reordered


def test_two_opt_improves_a_deliberately_bad_order() -> None:
    stops = scatter(8, seed=7)
    minutes, _ = matrices(stops)
    scrambled = [0, 5, 1, 6, 2, 7, 3, 4]
    improved = two_opt(scrambled, minutes)
    assert total(improved, minutes) < total(scrambled, minutes)


# --------------------------------------------------------------------------- #
# clustering
# --------------------------------------------------------------------------- #


def test_kmeans_returns_exactly_k_non_empty_clusters() -> None:
    points = [(p.lat, p.lng) for p in pois() if p.city == "Mysuru"]
    for k in (1, 2, 3, 5):
        clusters = kmeans(points, k)
        assert len(clusters) == k
        assert all(clusters)
        assert sorted(i for c in clusters for i in c) == list(range(len(points)))


def test_kmeans_is_deterministic() -> None:
    points = [(p.lat, p.lng) for p in pois() if p.city == "Hampi"]
    assert kmeans(points, 3) == kmeans(points, 3)


def test_balance_caps_every_cluster_at_pace_capacity() -> None:
    points = [(p.lat, p.lng) for p in pois() if p.city == "Mysuru"]
    scores = [float(i) for i in range(len(points))]
    kept, spill = balance(kmeans(points, 3), points, 4, scores)
    assert all(len(c) <= 4 for c in kept)
    assert sum(len(c) for c in kept) + len(spill) == len(points)


# --------------------------------------------------------------------------- #
# the engine
# --------------------------------------------------------------------------- #


def test_mysuru_alone_in_two_days_is_a_valid_plan() -> None:
    result = run(trip())
    assert isinstance(result, Plan)
    assert len(result.days) == 2
    assert all(day.stops for day in result.days)
    m = result.metrics
    assert m.constraint_checks_passed == m.constraint_checks_total
    assert result.comfort in {"comfortable", "tight"}


def test_mysuru_and_hampi_in_one_day_is_impossible_with_alternatives() -> None:
    result = run(trip(destination_cities=["Mysuru", "Hampi"], days=1))
    assert isinstance(result, Verdict)
    assert result.status == "impossible"
    assert 2 <= len(result.alternatives) <= 3
    labels = {r.label: r.value for r in result.reasons}
    assert labels["Total the trip needs"] > labels["Planning time available"]
    assert all(alt.request_override for alt in result.alternatives)


def test_a_poi_closed_on_monday_never_appears_in_a_monday_plan() -> None:
    monday = next_weekday(date(2026, 9, 1), 1)
    result = run(trip(start_date=monday, days=3))
    assert isinstance(result, Plan)
    by_id = {p.id: p for p in pois()}
    shut = [p for p in by_id.values() if p.city == "Mysuru" and 1 in p.closed_on]
    assert shut, "the fixture needs a Monday closure for this test to mean anything"
    for day in result.days:
        for stop in day.stops:
            assert day.date.isoweekday() not in by_id[stop.poi_id].closed_on


def test_an_advisory_closed_poi_is_excluded_entirely() -> None:
    palace = NAME_TO_ID["Mysore Palace"]
    result = run(
        trip(),
        [Advisory(poi_id=palace, severity="closed", message="Structural survey.")],
    )
    assert isinstance(result, Plan)
    assert palace not in {s.poi_id for d in result.days for s in d.stops}


def test_over_budget_triggers_repair_rather_than_failure() -> None:
    result = run(trip(budget_inr=600))
    assert isinstance(result, Plan), "a tight budget trims the day, it does not fail"
    assert result.metrics.repair_iterations > 0
    assert result.total_spend <= 600, "the repair loop brought the fees back in"
    assert all(day.stops for day in result.days)


def test_an_elderly_party_never_gets_a_day_ending_after_1900() -> None:
    result = run(trip(has_elderly=True, days=3, pace="packed"))
    assert isinstance(result, Plan)
    assert all(day.ends_at <= time(19, 0) for day in result.days)
    by_id = {p.id: p for p in pois()}
    assert all(by_id[s.poi_id].elderly_friendly for d in result.days for s in d.stops)


def test_hard_stops_survive_repair() -> None:
    request = trip(budget_inr=600)
    args = (pois(), edges(), legs(), advisories(), centroids())
    anchors = {
        max(pool.chosen, key=lambda p: (p.score, -p.id)).id
        for pool in day_pools(
            request,
            select_candidates(pois(), request, edges(), advisories()),
            legs(),
            centroids(),
        )
        if pool.chosen
    }
    result = attempt(request, *args, WEIGHTS[0])
    assert result.repairs > 0, "this request must exercise the repair loop"
    hard = [s for d in result.days for s in d.stops if s.leg_type == "hard"]
    assert {s.poi_id for s in hard} <= anchors
    assert len(hard) == len([d for d in result.days if d.stops])


def test_route_km_before_is_never_less_than_after() -> None:
    for days in (2, 3, 4):
        result = run(trip(days=days))
        assert isinstance(result, Plan)
        assert result.metrics.route_km_before >= result.metrics.route_km_after


def test_plan_build_completes_under_2000ms() -> None:
    result = run(trip(destination_cities=["Mysuru", "Hampi"], days=5))
    assert isinstance(result, Plan)
    assert result.metrics.build_ms < 2000


def test_the_itinerary_carries_no_scores_or_percentages() -> None:
    result = run(trip())
    assert isinstance(result, Plan)
    itinerary = json.dumps([d.model_dump(mode="json") for d in result.days])
    assert "score" not in itinerary
    assert "%" not in itinerary
    assert "1.15" not in itinerary  # the silent buffer is never surfaced
    assert result.comfort in {"comfortable", "tight"}


def test_intercity_transfers_are_first_class_day_items() -> None:
    result = run(trip(destination_cities=["Mysuru", "Coorg"], days=4))
    assert isinstance(result, Plan)
    transfers = [
        i
        for d in result.days
        for i in d.items
        if isinstance(i, Move) and i.from_name in {"Bengaluru", "Mysuru", "Coorg"}
    ]
    assert [t.from_name for t in transfers] == ["Bengaluru", "Mysuru"]
    assert all(t.minutes > 0 and t.km > 0 for t in transfers)


def test_soft_stops_are_padded_and_hard_stops_are_not() -> None:
    result = run(trip())
    assert isinstance(result, Plan)
    by_id = {p.id: p for p in pois()}
    for day in result.days:
        for stop in day.stops:
            typical = by_id[stop.poi_id].typical_dwell_min
            if stop.leg_type == "hard":
                assert stop.dwell_min == typical
            else:
                assert stop.dwell_min >= typical
                assert stop.dwell_min % 5 == 0


def test_every_stop_explains_itself_in_one_sentence() -> None:
    result = run(trip())
    assert isinstance(result, Plan)
    for day in result.days:
        for stop in day.stops:
            assert stop.why.endswith(".")
            assert stop.why.count(".") == 1

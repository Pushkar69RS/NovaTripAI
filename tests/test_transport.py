"""Getting around: the suggestion rule and the per-day estimate."""

from __future__ import annotations

from datetime import date, time

from app.planner.models import Day, Move, Traveller, TripRequest
from app.planner.transport import CAB_DAY, attach, day_transport, suggest_mode


def req(**over) -> TripRequest:
    base = {
        "origin_city": "Bengaluru",
        "destination_cities": ["Mysuru"],
        "start_date": date(2026, 9, 14),
        "days": 2,
        "travellers": [Traveller(kind="adult", age_band="40-59")] * 2,
        "budget_inr": 12000,
    }
    return TripRequest(**(base | over))


def test_an_elder_or_a_toddler_gets_a_cab() -> None:
    elder = req(travellers=[Traveller(kind="adult", age_band="60+")], budget_inr=500)
    assert suggest_mode(elder) == "cab"
    toddler = req(
        travellers=[
            Traveller(kind="adult", age_band="40-59"),
            Traveller(kind="child", age_band="3-5"),
        ],
        budget_inr=500,
    )
    assert suggest_mode(toddler) == "cab"


def test_a_low_per_head_budget_gets_autos_and_public_transport() -> None:
    assert suggest_mode(req(budget_inr=4000)) == "auto_public"  # 1,000 a head a day
    assert suggest_mode(req(budget_inr=12000)) == "cab"  # 3,000 a head a day


def test_the_travellers_choice_wins() -> None:
    assert suggest_mode(req(getting_around="own_car", budget_inr=500)) == "own_car"
    elder = req(travellers=[Traveller(kind="adult", age_band="60+")])
    assert suggest_mode(elder.model_copy(update={"getting_around": "auto_public"})) == (
        "auto_public"
    )


def day() -> Day:
    return Day(
        index=1,
        date=date(2026, 9, 14),
        city="Mysuru",
        items=[
            Move(
                from_name="Bengaluru",
                to_name="Mysuru",
                minutes=180,
                km=140,
                mode="train",
                is_estimated=True,
            ),
            Move(
                from_name="Mysore Palace",
                to_name="Devaraja Market",
                minutes=8,
                km=1.2,
                mode="car",
                is_estimated=True,
            ),
            Move(
                from_name="Devaraja Market",
                to_name="Mysore Zoo",
                minutes=12,
                km=2.8,
                mode="car",
                is_estimated=True,
            ),
        ],
        ends_at=time(18, 0),
        road_km=144.0,
    )


def test_the_estimate_counts_only_the_hops_inside_the_city() -> None:
    cab = day_transport(req(getting_around="cab"), day())
    assert cab.km == 4.0 and cab.est_cost_inr == CAB_DAY["Mysuru"] and cab.is_estimated
    car = day_transport(req(getting_around="own_car"), day())
    assert car.est_cost_inr == 32  # 4 km at 8 a km, not the 140 km transfer
    auto = day_transport(req(getting_around="auto_public"), day())
    assert auto.est_cost_inr == 2 * 60 + 100
    unknown = day_transport(
        req(getting_around="cab"), day().model_copy(update={"city": "Mangalore"})
    )
    assert unknown.est_cost_inr == 2600  # the default for a cold-started city


def test_attach_gives_every_day_its_line() -> None:
    from app.planner.models import Plan, PlanMetrics

    plan = Plan(
        days=[day()],
        total_spend=0,
        comfort="comfortable",
        has_plan_b=False,
        metrics=PlanMetrics(
            route_km_before=0,
            route_km_after=0,
            improvement_pct=0,
            repair_iterations=0,
            candidates_considered=0,
            build_ms=0,
            constraint_checks_passed=0,
            constraint_checks_total=0,
        ),
    )
    attach([plan], req())
    assert plan.days[0].getting_around is not None
    assert plan.days[0].getting_around.mode == "cab"
    assert "getting_around" in plan.model_dump(mode="json")["days"][0]

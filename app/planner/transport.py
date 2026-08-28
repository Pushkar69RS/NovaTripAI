"""Getting around inside a city, costed per day. Every figure is estimated.

A small table per hub, one default for a cold-started city. The cost is shown
next to the day and is not added to the plan's total and not validated against
the budget; that is the next step, recorded in DECISIONS.
"""

from __future__ import annotations

from .models import Day, DayTransport, Plan, TripRequest

#: A full-day cab, rupees, by hub. A city we cold-started takes the default.
CAB_DAY: dict[str, int] = {
    "Bengaluru": 3000,
    "Mysuru": 2400,
    "Hampi": 2200,
    "Chikmagalur": 2600,
    "Coorg": 2800,
}
CAB_DEFAULT = 2600
OWN_CAR_PER_KM = 8
AUTO_PER_KM, AUTO_BASE = 25, 60
BUS_PER_HEAD_DAY = 150
LOW_PER_HEAD_DAY = 1200  # below this a day of autos and buses is the honest suggestion

MODE_LABEL = {
    "cab": "cabs",
    "own_car": "own car",
    "auto_public": "autos and public transport",
}


def suggest_mode(request: TripRequest) -> str:
    """The traveller's choice wins; on 'suggest' the party and the budget decide."""
    if request.getting_around != "suggest":
        return request.getting_around
    if request.gentle:
        return "cab"
    per_head_day = (
        request.budget_inr / max(1, request.party_size) / max(1, request.days)
    )
    return "auto_public" if per_head_day < LOW_PER_HEAD_DAY else "cab"


def local_moves(day: Day, request: TripRequest) -> list:
    """The hops inside the city; the transfer in from another city is not one."""
    cities = {request.origin_city, *request.destination_cities}
    return [m for m in day.moves if m.from_name not in cities]


def day_transport(request: TripRequest, day: Day) -> DayTransport:
    mode = suggest_mode(request)
    hops = local_moves(day, request)
    km = round(sum(m.km for m in hops), 1)
    if mode == "cab":
        est = CAB_DAY.get(day.city, CAB_DEFAULT)
        why = f"a full-day cab in {day.city} runs about ₹2,200–3,000"
    elif mode == "own_car":
        est = round(km * OWN_CAR_PER_KM)
        why = f"fuel at about ₹{OWN_CAR_PER_KM} a km for {km} km"
    else:
        est = len(hops) * AUTO_BASE + round(km * AUTO_PER_KM)
        why = (
            f"autos at about ₹{AUTO_PER_KM} a km plus ₹{AUTO_BASE} a ride; a day of "
            f"buses is about ₹{BUS_PER_HEAD_DAY} a head"
        )
    return DayTransport(mode=mode, est_cost_inr=est, km=km, why=why)


def attach(plans: list[Plan], request: TripRequest) -> None:
    """Give every day its getting-around line. Idempotent."""
    for plan in plans:
        for day in plan.days:
            day.getting_around = day_transport(request, day)

"""Constraint checks over a built plan.

Pure: it reads days and returns violations, each carrying a machine code for the
repair loop and a plain sentence for the traveller. Nothing here mutates a day.
"""

from __future__ import annotations

from datetime import time

from pydantic import BaseModel

from .models import Advisory, Day, Move, Poi, Stop, TripRequest

DAY_END = time(20, 0)
DAY_END_ELDERLY = time(19, 0)
LUNCH_FROM, LUNCH_TO = 12 * 60, 15 * 60
LONG_STRETCH_MIN = 5 * 60  # no meal for longer than this, over midday, is a gap
TRAVEL_SHARE = 0.45  # local moves may not exceed this much of the day

#: Per-stop checks, per-day checks, plus the one budget check.
STOP_CHECKS = 3
DAY_CHECKS = 3


class Violation(BaseModel):
    code: str
    message: str
    day_index: int
    poi_id: int | None = None


def checks_total(days: list[Day]) -> int:
    stops = sum(len(d.stops) for d in days)
    return stops * STOP_CHECKS + len(days) * DAY_CHECKS + 1


def _closed_by_advisory(
    poi: Poi, city: str, advisories: list[Advisory]
) -> Advisory | None:
    for a in advisories:
        if a.severity != "closed":
            continue
        if a.poi_id == poi.id or (a.city and a.city == city):
            return a
    return None


def _mins(t: time) -> int:
    return t.hour * 60 + t.minute


def local_moves(day: Day) -> list[Move]:
    """The day's own hops. A transfer into the city is not sightseeing travel."""
    lead = day.items[0] if day.items else None
    transfer = lead if isinstance(lead, Move) else None
    return [m for m in day.moves if m is not transfer]


def travel_outlier(day: Day) -> int | None:
    """The stop whose own hops cost the most: the one stretching the day out.

    Naming it lets the repair drop the stop that is actually causing the
    overrun. Dropping a near neighbour instead only makes the ratio worse.
    """
    lead = day.items[0] if day.items else None
    transfer = lead if isinstance(lead, Move) else None
    cost: dict[int, int] = {}
    for n, item in enumerate(day.items):
        if not isinstance(item, Stop):
            continue
        beside = (day.items[k] for k in (n - 1, n + 1) if 0 <= k < len(day.items))
        cost[item.poi_id] = sum(
            m.minutes for m in beside if isinstance(m, Move) and m is not transfer
        )
    return max(cost, key=lambda poi_id: cost[poi_id]) if cost else None


def meal_gap(stops: list[Stop], pois: dict[int, Poi]) -> bool:
    """True when a stretch over five hours with no food stop covers midday."""
    fed = [
        (_mins(s.arrive), _mins(s.depart))
        for s in stops
        if pois[s.poi_id].category == "food"
    ]
    stretches, opened = [], _mins(stops[0].arrive)
    for start, end in sorted(fed):
        stretches.append((opened, start))
        opened = end
    stretches.append((opened, _mins(stops[-1].depart)))
    return any(
        end - start > LONG_STRETCH_MIN and start < LUNCH_TO and end > LUNCH_FROM
        for start, end in stretches
    )


def validate(
    days: list[Day],
    request: TripRequest,
    pois: dict[int, Poi],
    advisories: list[Advisory],
    total_spend: int,
) -> list[Violation]:
    """Every violation in the plan, in the order the checks are defined."""
    out: list[Violation] = []
    limit = request.day_end or (DAY_END_ELDERLY if request.gentle else DAY_END)

    for day in days:
        stops = day.stops
        for stop in stops:
            poi = pois[stop.poi_id]

            # Advisories come first: a closed POI invalidates everything downstream.
            advisory = _closed_by_advisory(poi, day.city, advisories)
            if advisory is not None:
                out.append(
                    Violation(
                        code="ADVISORY_CLOSED",
                        message=(
                            f"{stop.name} is under a closure advisory: "
                            f"{advisory.message}"
                        ),
                        day_index=day.index,
                        poi_id=poi.id,
                    )
                )
            if day.date.isoweekday() in poi.closed_on:
                out.append(
                    Violation(
                        code="CLOSED_DAY",
                        message=f"{stop.name} is closed on {day.date:%A}.",
                        day_index=day.index,
                        poi_id=poi.id,
                    )
                )
            if (poi.opens and stop.arrive < poi.opens) or (
                poi.closes and stop.depart > poi.closes
            ):
                opens = f"{poi.opens:%H:%M}" if poi.opens else "open"
                closes = f"{poi.closes:%H:%M}" if poi.closes else "close"
                out.append(
                    Violation(
                        code="OUTSIDE_HOURS",
                        message=(
                            f"{stop.name} is scheduled "
                            f"{stop.arrive:%H:%M}-{stop.depart:%H:%M}, outside its "
                            f"{opens}-{closes} hours."
                        ),
                        day_index=day.index,
                        poi_id=poi.id,
                    )
                )

        if day.ends_at > limit:
            out.append(
                Violation(
                    code="DAY_TOO_LONG",
                    message=(
                        f"Day {day.index} ends at {day.ends_at:%H:%M}, "
                        f"past the {limit:%H:%M} the party should be back by."
                    ),
                    day_index=day.index,
                )
            )

        if stops:
            travel = sum(m.minutes for m in local_moves(day))
            span = travel + sum(s.dwell_min for s in stops)
            if meal_gap(stops, pois):
                out.append(
                    Violation(
                        code="NO_MEAL_GAP",
                        message=(
                            f"Day {day.index} goes more than five hours over "
                            f"midday with no meal stop."
                        ),
                        day_index=day.index,
                    )
                )
            if travel > TRAVEL_SHARE * span:
                out.append(
                    Violation(
                        code="TRAVEL_OVERRUN",
                        message=(
                            f"Day {day.index} spends {travel} of its {span} minutes "
                            f"in transit rather than at a stop."
                        ),
                        day_index=day.index,
                        poi_id=travel_outlier(day),
                    )
                )

    if total_spend > request.budget_inr:
        out.append(
            Violation(
                code="OVER_BUDGET",
                message=(
                    f"Entry fees come to Rs {total_spend} against a budget of "
                    f"Rs {request.budget_inr}."
                ),
                day_index=max((d.index for d in days), default=1),
            )
        )
    return out

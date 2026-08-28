"""The deterministic planner.

Pure Python: no LLM call, no write to the database. `plan()` reads candidate
POIs, gates the request on arithmetic, then clusters, routes, schedules,
validates and repairs until the itinerary holds. The same request always
produces the same plan.

    uv run python -m app.planner.engine --demo
"""

from __future__ import annotations

import argparse
import math
import os
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from itertools import pairwise
from time import perf_counter
from typing import Any

from .cluster import balance, kmeans
from .distance import haversine, intercity_move, local_hop
from .models import (
    Advisory,
    Alternative,
    Day,
    Leg,
    Move,
    Plan,
    PlanMetrics,
    Poi,
    Reason,
    Stop,
    Traveller,
    TripRequest,
    Verdict,
)
from .route import as_listed, optimise
from .validate import Violation, checks_total, validate

DAY_START = time(9, 0)
DAY_BUDGET_MIN = 12 * 60  # planning minutes available per day
SOFT_BUFFER = 1.15  # silent padding on soft stops; never surfaced
BUFFER_STEP = 5  # buffered dwell is rounded up to this many minutes
MAX_WAIT_MIN = 60  # willing to wait this long for a stop to open, no longer
MAX_REPAIRS = 8
TIGHT_SHARE = 0.8  # required over this share of available and the plan is tight
LUNCH_FROM, LUNCH_TO = time(12, 0), time(15, 0)

#: (interest tag, popularity, poi_edge) weights. The first is the house scoring;
#: the other two are the sibling candidates ranked against it.
WEIGHTS: list[tuple[float, float, float]] = [
    (3.0, 2.0, 1.0),
    (3.5, 1.5, 1.0),
    (2.5, 2.5, 1.2),
]
#: One name per WEIGHTS entry, for the chooser: the house mix, the one that
#: leans on the traveller's tags, the one that leans on the famous names.
VARIANTS = ("steady", "interests", "popular")

Point = tuple[float, float]
Edge = tuple[int, int, float]


# --------------------------------------------------------------------------- #
# time helpers
# --------------------------------------------------------------------------- #


def mins(t: time) -> int:
    return t.hour * 60 + t.minute


def clock(m: int) -> time:
    return time(23, 59) if m >= 24 * 60 else time(m // 60, m % 60)


# --------------------------------------------------------------------------- #
# step 1 - candidates
# --------------------------------------------------------------------------- #


def allot_days(request: TripRequest) -> list[tuple[str, int]]:
    """Days per destination city, in request order, remainder to the front.

    Every city gets at least one day even when there are more cities than days;
    the feasibility gate is what turns that over-subscription into a verdict.
    """
    n = len(request.destination_cities)
    if request.days < n:
        return [(city, 1) for city in request.destination_cities]
    base, extra = divmod(request.days, n)
    return [
        (city, base + (1 if i < extra else 0))
        for i, city in enumerate(request.destination_cities)
    ]


def fee_cap(request: TripRequest) -> int:
    """Per-stop entry fee band. The budget itself is checked by the validator."""
    per_head = request.budget_inr // request.party_size
    return max(150, per_head // max(1, request.days * request.capacity))


def closed_by_advisory(poi: Poi, advisories: list[Advisory]) -> bool:
    return any(
        a.severity == "closed" and (a.poi_id == poi.id or a.city == poi.city)
        for a in advisories
    )


def skipped(poi: Poi, request: TripRequest) -> bool:
    """A place the traveller asked to skip: a word of theirs in its name, tags
    or category. "zoos" reaches "Mysore Zoo" because a trailing s is dropped."""
    # ponytail: substring match; a stemmer if "art" ever has to miss "market"
    words = {w.strip().lower().rstrip("s") for w in request.skip if w.strip()}
    haystack = " ".join([poi.name, poi.category, *poi.tags]).lower()
    return any(w and w in haystack for w in words)


def eligible(
    pois: list[Poi], request: TripRequest, advisories: list[Advisory]
) -> list[Poi]:
    """Everything the request could legitimately visit. Advisories come first."""
    cap = fee_cap(request)
    return [
        p
        for p in pois
        if p.city in request.destination_cities
        and not closed_by_advisory(p, advisories)
        and (not request.gentle or p.elderly_friendly)
        and p.entry_fee_inr <= cap
        and not skipped(p, request)
    ]


def score(
    pois: list[Poi],
    request: TripRequest,
    edges: list[Edge],
    weights: tuple[float, float, float],
) -> None:
    """Set `score` in place: tag overlap, popularity, one-hop edge from a seed."""
    tag_w, pop_w, edge_w = weights
    wanted = {t.lower() for t in request.interest_tags}
    for p in pois:
        overlap = len(wanted & {t.lower() for t in p.tags})
        p.score = tag_w * overlap + pop_w * p.popularity

    seeds: set[int] = set()
    for city in request.destination_cities:
        ranked = sorted(
            (p for p in pois if p.city == city), key=lambda p: (-p.score, p.id)
        )
        seeds.update(p.id for p in ranked[:2])

    neighbours: dict[int, float] = {}
    for a, b, w in edges:
        if a in seeds:
            neighbours[b] = max(neighbours.get(b, 0.0), w)
        if b in seeds:
            neighbours[a] = max(neighbours.get(a, 0.0), w)
    for p in pois:
        if p.id in neighbours and p.id not in seeds:
            p.score += edge_w * neighbours[p.id]


MEAL_OPEN_BY, MEAL_SHUT_AFTER = time(14, 0), time(13, 0)


def feeds_at_midday(poi: Poi) -> bool:
    """A food stop the party can actually eat lunch at."""
    return (
        poi.category == "food"
        and (poi.opens is None or poi.opens <= MEAL_OPEN_BY)
        and (poi.closes is None or poi.closes >= MEAL_SHUT_AFTER)
    )


def select_candidates(
    pois: list[Poi],
    request: TripRequest,
    edges: list[Edge],
    advisories: list[Advisory],
    weights: tuple[float, float, float] = WEIGHTS[0],
) -> list[Poi]:
    """The top `days * capacity * 2` scored POIs of each destination city.

    Plus, if the top slice missed them, one lunch stop per day: a shortlist that
    cannot feed the party leaves the repair loop deleting sights to answer
    NO_MEAL_GAP, which is the wrong end of the problem.
    """
    pool = [p.model_copy() for p in eligible(pois, request, advisories)]
    score(pool, request, edges, weights)
    out: list[Poi] = []
    for city, nd in allot_days(request):
        ranked = sorted(
            (p for p in pool if p.city == city), key=lambda p: (-p.score, p.id)
        )
        picked = ranked[: nd * request.capacity * 2]
        seated = {p.id for p in picked if feeds_at_midday(p)}
        for p in ranked:
            if len(seated) >= nd:
                break
            if feeds_at_midday(p) and p.id not in seated:
                picked.append(p)
                seated.add(p.id)
        out.extend(picked)
    return out


# --------------------------------------------------------------------------- #
# step 2 - feasibility gate
# --------------------------------------------------------------------------- #


def transfer_moves(
    request: TripRequest, legs: list[Leg], centroids: dict[str, Point]
) -> list[Move]:
    route = [request.origin_city, *request.destination_cities]
    return [
        intercity_move(a, b, request.transport, legs, centroids)
        for a, b in pairwise(route)
    ]


def _from_origin(
    request: TripRequest, legs: list[Leg], centroids: dict[str, Point], city: str
) -> int:
    return intercity_move(
        request.origin_city, city, request.transport, legs, centroids
    ).minutes


def build_alternatives(
    request: TripRequest,
    required: int,
    legs: list[Leg],
    centroids: dict[str, Point],
) -> list[Alternative]:
    """Two or three concrete ways to make the request fit."""
    needed = max(request.days + 1, math.ceil(required / DAY_BUDGET_MIN))
    out = [
        Alternative(
            title=f"Take {needed} days instead of {request.days}",
            description=(
                f"The same cities fit once the trip has {needed} days of travel "
                f"and sightseeing time."
            ),
            request_override={"days": needed},
        )
    ]
    cities = list(request.destination_cities)
    if len(cities) > 1:
        ordered = sorted(
            cities, key=lambda c: _from_origin(request, legs, centroids, c)
        )
        nearest, farthest = ordered[0], ordered[-1]
        keep = [c for c in cities if c != farthest]
        out.append(
            Alternative(
                title=f"Drop {farthest}",
                description=(
                    f"{farthest} is the longest haul from {request.origin_city}; "
                    f"without it the rest fits into the {request.days} "
                    f"{'day' if request.days == 1 else 'days'} you have."
                ),
                request_override={"destination_cities": keep},
            )
        )
        if keep != [nearest]:
            out.append(
                Alternative(
                    title=f"Keep only {nearest}",
                    description=(
                        f"{nearest} is the closest to {request.origin_city} and "
                        f"leaves the most time on the ground."
                    ),
                    request_override={"destination_cities": [nearest]},
                )
            )
    return out


def feasibility(
    request: TripRequest,
    candidates: list[Poi],
    legs: list[Leg],
    centroids: dict[str, Point],
) -> tuple[int, int, list[Reason]]:
    """(required minutes, available minutes, the arithmetic behind both)."""
    moves = transfer_moves(request, legs, centroids)
    travel = sum(m.minutes for m in moves)
    anchors = 0
    for city, _ in allot_days(request):
        in_city = [p for p in candidates if p.city == city]
        if in_city:
            anchors += max(in_city, key=lambda p: (p.score, -p.id)).typical_dwell_min
    required = travel + anchors
    available = request.days * DAY_BUDGET_MIN
    reasons = [
        Reason(
            label=(
                f"{m.from_name} → {m.to_name} by {m.mode}, {m.km:g} km"
                + (" (estimated)" if m.is_estimated else "")
            ),
            value=m.minutes,
            unit="minutes",
        )
        for m in moves
    ] + [
        Reason(label="Travel between cities", value=travel, unit="minutes"),
        Reason(
            label="Minimum time at one sight per city", value=anchors, unit="minutes"
        ),
        Reason(label="Total the trip needs", value=required, unit="minutes"),
        Reason(label="Planning time available", value=available, unit="minutes"),
        Reason(label="Days requested", value=request.days, unit="days"),
        Reason(
            label="Cities requested",
            value=len(request.destination_cities),
            unit="cities",
        ),
    ]
    return required, available, reasons


# --------------------------------------------------------------------------- #
# steps 3-5 - clusters, route, schedule
# --------------------------------------------------------------------------- #


def why(
    poi: Poi,
    *,
    is_anchor: bool,
    prev: Move | None,
    first: bool,
    last: bool,
    arrive: time,
    request: TripRequest,
) -> str:
    """One plain sentence about why this stop sits here. Template, never an LLM."""
    if is_anchor:
        return "Fixed entry slot, so the day is arranged around it."
    if prev is not None and prev.minutes >= 30:
        word = {"walk": "walk", "train": "train ride", "bus": "bus ride"}.get(
            prev.mode, "drive"
        )
        return f"Placed after the {prev.minutes}-minute {word} from {prev.from_name}."
    if poi.category == "food" and LUNCH_FROM <= arrive <= LUNCH_TO:
        return "Sits in the middle of the day so the party eats before the afternoon."
    if first and poi.opens is not None and poi.opens <= DAY_START:
        return "Already open at the start of the day, so it goes first."
    if last and poi.closes is not None and poi.closes >= time(18, 0):
        return "Stays open late, so it closes out the day."
    wanted = {t.lower() for t in request.interest_tags}
    shared = [t for t in poi.tags if t.lower() in wanted]
    if shared:
        return f"Matches your interest in {shared[0]}."
    return "Grouped with the neighbouring stops to keep the driving short."


def build_day(
    index: int,
    on: date,
    city: str,
    chosen: list[Poi],
    request: TripRequest,
    arrival: Move | None,
    entry: Point,
    day_start: time = DAY_START,
) -> tuple[Day, float, float]:
    """(Day, route km before 2-opt, route km after). Both routes are kept."""
    if not chosen:
        empty = Day(index=index, date=on, city=city, items=[], ends_at=day_start)
        return empty, 0.0, 0.0

    start = min(
        range(len(chosen)),
        key=lambda i: haversine(entry[0], entry[1], chosen[i].lat, chosen[i].lng),
    )
    _before, after, km_before, km_after = optimise(chosen, start)
    listed, km_naive = as_listed(chosen)
    ordered = [chosen[i] for i in after]
    anchor = max(ordered, key=lambda p: (p.score, -p.id))

    items: list[Stop | Move] = []
    now = mins(day_start)
    walk_km = road_km = 0.0
    spend = 0
    if arrival is not None:
        items.append(arrival)
        now += arrival.minutes
        road_km += arrival.km

    previous: Poi | None = None
    for position, poi in enumerate(ordered):
        move: Move | None = None
        if previous is not None:
            minutes, km, mode = local_hop(previous, poi)
            move = Move(
                from_name=previous.name,
                to_name=poi.name,
                minutes=minutes,
                km=km,
                mode=mode,
                is_estimated=True,
            )
            items.append(move)
            now += minutes
            if mode == "walk":
                walk_km += km
            else:
                road_km += km

        hard = poi is anchor
        dwell = poi.typical_dwell_min
        if not hard:
            dwell = math.ceil(dwell * SOFT_BUFFER / BUFFER_STEP) * BUFFER_STEP
        arrive = now
        if poi.opens is not None and 0 < mins(poi.opens) - arrive <= MAX_WAIT_MIN:
            arrive = mins(poi.opens)
        depart = arrive + dwell
        now = depart
        cost = poi.entry_fee_inr * request.party_size
        spend += cost
        items.append(
            Stop(
                poi_id=poi.id,
                name=poi.name,
                name_kn=poi.name_kn,
                lat=poi.lat,
                lng=poi.lng,
                arrive=clock(arrive),
                depart=clock(depart),
                dwell_min=dwell,
                cost_inr=cost,
                leg_type="hard" if hard else "soft",
                tags=poi.tags,
                note=None,
                trust=poi.trust,
                why=why(
                    poi,
                    is_anchor=hard,
                    prev=move if move is not None else arrival,
                    first=position == 0,
                    last=position == len(ordered) - 1,
                    arrive=clock(arrive),
                    request=request,
                ),
            )
        )
        previous = poi

    day = Day(
        index=index,
        date=on,
        city=city,
        items=items,
        ends_at=clock(now),
        walk_km=round(walk_km, 2),
        road_km=round(road_km, 2),
        spend_inr=spend,
        naive_order=[chosen[i].id for i in listed],
        naive_km=km_naive,
        route_km=km_after,
    )
    return day, km_before, km_after


@dataclass
class Pool:
    """The raw material of one day, before it is scheduled."""

    on: date
    city: str
    chosen: list[Poi]
    arrival: Move | None
    entry: Point
    start: time = DAY_START


MEAL_FROM_STOPS = 3  # a day of this many stops runs long enough to need feeding


def _seat_a_meal(
    chosen: list[Poi], in_city: list[Poi], spill: list[int], weekday: int
) -> None:
    """Trade a day's weakest stop for somewhere to eat, if it has none.

    A day that runs over midday without a food stop trips NO_MEAL_GAP, and the
    repair loop can only answer that by deleting sights. Seating the meal here
    is the cheaper fix.
    """
    if len(chosen) < MEAL_FROM_STOPS or any(p.category == "food" for p in chosen):
        return
    # ponytail: the meal comes from the day's own spare candidates. Reaching into
    # another day's cluster would need the whole city re-balanced.
    kitchens = [
        i
        for i in spill
        if feeds_at_midday(in_city[i]) and weekday not in in_city[i].closed_on
    ]
    if not kitchens:
        return
    middle = (
        sum(p.lat for p in chosen) / len(chosen),
        sum(p.lng for p in chosen) / len(chosen),
    )
    pick = min(
        kitchens,
        key=lambda i: haversine(middle[0], middle[1], in_city[i].lat, in_city[i].lng),
    )
    spill.remove(pick)
    chosen.remove(min(chosen, key=lambda p: (p.score, -p.id)))
    chosen.append(in_city[pick])


def day_pools(
    request: TripRequest,
    candidates: list[Poi],
    legs: list[Leg],
    centroids: dict[str, Point],
) -> list[Pool]:
    """Assign cities to days and cluster each city's candidates within its days."""
    pools: list[Pool] = []
    previous_city = request.origin_city
    index = 0
    for city, nd in allot_days(request):
        in_city = [p for p in candidates if p.city == city]
        points = [(p.lat, p.lng) for p in in_city]
        spill: list[int] = []
        clusters: list[list[int]] = [[] for _ in range(nd)]
        if in_city:
            clusters, spill = balance(
                kmeans(points, nd),
                points,
                request.capacity,
                [p.score for p in in_city],
            )
            # ponytail: clusters go to days nearest-the-city-centre first. A
            # nearest-neighbour tour over cluster centroids would shave a little
            # more driving; worth it only once days per city goes above three.
            centre = centroids.get(city, points[0])
            clusters.sort(
                key=lambda c: min(
                    haversine(centre[0], centre[1], points[i][0], points[i][1])
                    for i in c
                )
            )

        for n in range(nd):
            on = request.start_date + timedelta(days=index)
            weekday = on.isoweekday()
            members = clusters[n] if n < len(clusters) else []
            chosen = [
                in_city[i] for i in members if weekday not in in_city[i].closed_on
            ]
            if len(chosen) < request.capacity and spill:
                anchor = (
                    (chosen[0].lat, chosen[0].lng)
                    if chosen
                    else centroids.get(city, points[0])
                )
                spare = sorted(
                    (i for i in spill if weekday not in in_city[i].closed_on),
                    key=lambda i: haversine(
                        anchor[0], anchor[1], in_city[i].lat, in_city[i].lng
                    ),
                )
                for i in spare[: request.capacity - len(chosen)]:
                    spill.remove(i)
                    chosen.append(in_city[i])
            _seat_a_meal(chosen, in_city, spill, weekday)
            arrival = (
                intercity_move(previous_city, city, request.transport, legs, centroids)
                if n == 0 and previous_city != city
                else None
            )
            fallback = (chosen[0].lat, chosen[0].lng) if chosen else (0.0, 0.0)
            pools.append(
                Pool(
                    on,
                    city,
                    chosen,
                    arrival,
                    centroids.get(city, fallback),
                    DAY_START,
                )
            )
            index += 1
        previous_city = city
    return pools


# --------------------------------------------------------------------------- #
# steps 6-8 - validate, repair, rank
# --------------------------------------------------------------------------- #


@dataclass
class Attempt:
    """One scoring variant taken all the way to a validated set of days."""

    days: list[Day]
    violations: list[Violation]
    km_before: float
    km_after: float
    km_naive: float
    repairs: int
    interest: float
    spend: int

    @property
    def travel_minutes(self) -> int:
        return sum(m.minutes for d in self.days for m in d.moves)

    @property
    def rank(self) -> tuple[int, float, int]:
        """Valid first, then the most interesting, then the least travelling."""
        return (1 if self.violations else 0, -self.interest, self.travel_minutes)


def drop_for(pool: Pool, violation: Violation) -> Poi | None:
    """The soft stop to give up for this violation, or None if none will help.

    The lowest-scoring soft stop of the offending day, except when the violation
    names a stop of its own - then that is the one in the way. Hard stops are
    never dropped, so a violation on the anchor has no repair here.
    """
    if not pool.chosen:
        return None
    anchor = max(pool.chosen, key=lambda p: (p.score, -p.id))
    if violation.poi_id == anchor.id:
        return None
    soft = [p for p in pool.chosen if p is not anchor]
    if not soft:
        return None
    named = [p for p in soft if p.id == violation.poi_id]
    return named[0] if named else min(soft, key=lambda p: (p.score, -p.id))


def attempt(
    request: TripRequest,
    pois: list[Poi],
    edges: list[Edge],
    legs: list[Leg],
    advisories: list[Advisory],
    centroids: dict[str, Point],
    weights: tuple[float, float, float],
) -> Attempt:
    """Build, validate and repair one candidate itinerary."""
    candidates = select_candidates(pois, request, edges, advisories, weights)
    by_id = {p.id: p for p in candidates}
    pools = day_pools(request, candidates, legs, centroids)
    built = [
        build_day(n + 1, p.on, p.city, p.chosen, request, p.arrival, p.entry, p.start)
        for n, p in enumerate(pools)
    ]

    def check() -> list[Violation]:
        days = [d for d, _, _ in built]
        return validate(
            days, request, by_id, advisories, sum(d.spend_inr for d in days)
        )

    repairs = 0
    spent: dict[int, int] = {}
    violations = check()
    while violations and repairs < MAX_REPAIRS:
        fixable = [
            (v, drop)
            for v in violations
            if (drop := drop_for(pools[v.day_index - 1], v)) is not None
        ]
        if not fixable:  # nothing left that dropping a soft stop can fix
            break
        # Least-repaired day first, so one stubborn day cannot eat the budget
        # and leave a later day untouched.
        violation, victim = min(fixable, key=lambda f: spent.get(f[0].day_index, 0))
        spent[violation.day_index] = spent.get(violation.day_index, 0) + 1
        n = violation.day_index - 1
        pool = pools[n]
        pool.chosen.remove(victim)
        built[n] = build_day(
            n + 1,
            pool.on,
            pool.city,
            pool.chosen,
            request,
            pool.arrival,
            pool.entry,
            pool.start,
        )
        repairs += 1
        violations = check()

    days = [d for d, _, _ in built]
    return Attempt(
        days=days,
        violations=violations,
        km_before=round(sum(b for _, b, _ in built), 2),
        km_after=round(sum(a for _, _, a in built), 2),
        km_naive=round(sum(d.naive_km for d in days), 2),
        repairs=repairs,
        interest=sum(by_id[s.poi_id].score for d in days for s in d.stops),
        spend=sum(d.spend_inr for d in days),
    )


# --------------------------------------------------------------------------- #
# rebuilding one day, for the chat edits
# --------------------------------------------------------------------------- #


def scored_pool(
    pois: list[Poi], request: TripRequest, edges: list[Edge], advisories: list[Advisory]
) -> dict[int, Poi]:
    """Every eligible POI, scored, by id. Wider than the shortlist on purpose:
    a traveller may ask for a stop the shortlist never held."""
    pool = [p.model_copy() for p in eligible(pois, request, advisories)]
    score(pool, request, edges, WEIGHTS[0])
    return {p.id: p for p in pool}


def rebuild_day(
    plan: Plan,
    request: TripRequest,
    loaded: Loaded,
    day_index: int,
    poi_ids: list[int],
    *,
    start: time = DAY_START,
    pace: str | None = None,
) -> tuple[Day, list[Violation], int]:
    """Steps 3-6 for one day only: order, schedule, validate, repair.

    Every other day is left exactly as it was; the caller splices the result in.
    Returns the day, whatever it still violates, and the repairs it took.
    """
    pois, edges, _legs, advisories, centroids = loaded
    req = request if pace is None else request.model_copy(update={"pace": pace})
    scored = scored_pool(pois, req, edges, advisories)
    unknown = [i for i in poi_ids if i not in scored]
    if unknown:
        raise ValueError(f"not eligible for this trip: {unknown}")
    old = plan.days[day_index - 1]
    chosen = [scored[i] for i in poi_ids]
    first = old.items[0] if old.items else None
    arrival = first if isinstance(first, Move) and first.to_name == old.city else None
    fallback = (chosen[0].lat, chosen[0].lng) if chosen else (0.0, 0.0)
    pool = Pool(old.date, old.city, chosen, arrival, centroids.get(old.city, fallback))
    by_id = {p.id: p for p in pois} | scored

    def rebuilt() -> Day:
        return build_day(
            old.index,
            pool.on,
            pool.city,
            pool.chosen,
            req,
            pool.arrival,
            pool.entry,
            start,
        )[0]

    def check(day: Day) -> list[Violation]:
        days = [*plan.days[: day_index - 1], day, *plan.days[day_index:]]
        spend = sum(d.spend_inr for d in days)
        return [
            v
            for v in validate(days, req, by_id, advisories, spend)
            if v.day_index == day.index or v.code == "OVER_BUDGET"
        ]

    day = rebuilt()
    repairs = 0
    violations = check(day)
    while violations and repairs < MAX_REPAIRS:
        victim = next(
            (d for v in violations if (d := drop_for(pool, v)) is not None), None
        )
        if victim is None:
            break
        pool.chosen.remove(victim)
        day = rebuilt()
        repairs += 1
        violations = check(day)
    return day, violations, repairs


# --------------------------------------------------------------------------- #
# the entry points
# --------------------------------------------------------------------------- #


def build(
    request: TripRequest,
    pois: list[Poi],
    edges: list[Edge],
    legs: list[Leg],
    advisories: list[Advisory],
    centroids: dict[str, Point],
) -> Plan | Verdict:
    """The best plan, or the verdict. Every input in memory; touches no IO."""
    result = build_all(request, pois, edges, legs, advisories, centroids)
    return result if isinstance(result, Verdict) else result[0]


def _plan(
    variant: str,
    best: Attempt,
    others: list[Attempt],
    *,
    required: int,
    available: int,
    considered: int,
    build_ms: int,
) -> Plan:
    total = checks_total(best.days)
    gained = (
        round((best.km_before - best.km_after) / best.km_before * 100, 1)
        if best.km_before
        else 0.0
    )
    return Plan(
        days=best.days,
        total_spend=best.spend,
        comfort="tight"
        if required > TIGHT_SHARE * available or best.violations
        else "comfortable",
        has_plan_b=any(not a.violations for a in others),
        variant=variant,
        metrics=PlanMetrics(
            route_km_before=best.km_before,
            route_km_after=best.km_after,
            route_km_naive=best.km_naive,
            improvement_pct=gained,
            repair_iterations=best.repairs,
            candidates_considered=considered,
            build_ms=build_ms,
            constraint_checks_passed=total - len(best.violations),
            constraint_checks_total=total,
        ),
    )


def build_all(
    request: TripRequest,
    pois: list[Poi],
    edges: list[Edge],
    legs: list[Leg],
    advisories: list[Advisory],
    centroids: dict[str, Point],
) -> list[Plan] | Verdict:
    """Every scoring variant taken to a plan, best first, or the verdict.

    The first is the plan; the others are the alternatives the chooser offers.
    """
    started = perf_counter()
    considered = len(eligible(pois, request, advisories))
    house = select_candidates(pois, request, edges, advisories, WEIGHTS[0])
    required, available, reasons = feasibility(request, house, legs, centroids)

    barren = [c for c, _ in allot_days(request) if not any(p.city == c for p in house)]
    if barren:
        return Verdict(
            status="impossible",
            reasons=[
                *reasons,
                Reason(
                    label="Cities with nothing open to visit",
                    value=", ".join(barren),
                    unit="",
                ),
            ],
            alternatives=build_alternatives(request, required, legs, centroids),
        )
    if required > available or request.days < len(request.destination_cities):
        return Verdict(
            status="impossible",
            reasons=reasons,
            alternatives=build_alternatives(request, required, legs, centroids),
        )

    attempts = sorted(
        (
            (variant, attempt(request, pois, edges, legs, advisories, centroids, w))
            for variant, w in zip(VARIANTS, WEIGHTS, strict=True)
        ),
        key=lambda va: va[1].rank,
    )
    build_ms = int((perf_counter() - started) * 1000)
    return [
        _plan(
            variant,
            a,
            [b for _, b in attempts if b is not a],
            required=required,
            available=available,
            considered=considered,
            build_ms=build_ms,
        )
        for variant, a in attempts
    ]


POI_SQL = """
SELECT p.id, p.name, p.name_kn, p.city, p.lat, p.lng, p.category, p.tags,
       p.typical_dwell_min, p.entry_fee_inr, p.opens, p.closes, p.closed_on,
       p.elderly_friendly, p.popularity, p.trust
FROM poi p
WHERE p.city = ANY(%(cities)s)
  AND p.entry_fee_inr <= %(fee_cap)s
  AND (NOT %(elderly)s OR p.elderly_friendly)
  AND NOT EXISTS (
        SELECT 1 FROM advisory a
        WHERE a.severity = 'closed'
          AND current_date BETWEEN a.valid_from AND a.valid_until
          AND (a.poi_id = p.id OR a.city = p.city))
ORDER BY p.id
"""
ADVISORY_SQL = """
SELECT poi_id, city, severity, message FROM advisory
WHERE current_date BETWEEN valid_from AND valid_until
"""
LEG_SQL = """
SELECT from_city, to_city, mode, distance_km, duration_min, is_estimated
FROM intercity_leg WHERE from_city = ANY(%s) OR to_city = ANY(%s)
"""
EDGE_SQL = "SELECT from_poi, to_poi, coalesce(weight, 1.0) FROM poi_edge"
CENTROID_SQL = "SELECT city, avg(lat), avg(lng) FROM poi GROUP BY city"
#: Fills in only the cities with no poi rows (a cold-started origin, say).
CENTRE_SQL = "SELECT name, lat, lng FROM city_centre"

Loaded = tuple[list[Poi], list[Edge], list[Leg], list[Advisory], dict[str, Point]]


def load(request: TripRequest, db: Any) -> Loaded:
    """Read-only. Columns are selected positionally, so any row factory works."""
    cities = [request.origin_city, *request.destination_cities]
    pois = [
        Poi(
            id=r[0],
            name=r[1],
            name_kn=r[2],
            city=r[3],
            lat=r[4],
            lng=r[5],
            category=r[6],
            tags=list(r[7] or []),
            typical_dwell_min=r[8],
            entry_fee_inr=r[9],
            opens=r[10],
            closes=r[11],
            closed_on=list(r[12] or []),
            elderly_friendly=r[13],
            popularity=r[14] or 3,
            trust=r[15] or "draft",
        )
        for r in db.execute(
            POI_SQL,
            {
                "cities": request.destination_cities,
                "fee_cap": fee_cap(request),
                "elderly": request.gentle,
            },
        ).fetchall()
    ]
    advisories = [
        Advisory(poi_id=r[0], city=r[1], severity=r[2], message=r[3])
        for r in db.execute(ADVISORY_SQL).fetchall()
    ]
    legs = [
        Leg(
            from_city=r[0],
            to_city=r[1],
            mode=r[2],
            distance_km=r[3],
            duration_min=r[4],
            is_estimated=r[5],
        )
        for r in db.execute(LEG_SQL, (cities, cities)).fetchall()
    ]
    edges = [(r[0], r[1], float(r[2])) for r in db.execute(EDGE_SQL).fetchall()]
    centroids = {
        r[0]: (float(r[1]), float(r[2])) for r in db.execute(CENTROID_SQL).fetchall()
    }
    for r in db.execute(CENTRE_SQL).fetchall():
        centroids.setdefault(r[0], (float(r[1]), float(r[2])))
    return pois, edges, legs, advisories, centroids


def plan(request: TripRequest, db: Any) -> Plan | Verdict:
    """Plan a trip. Reads from `db`; writes nothing, anywhere."""
    return build(request, *load(request, db))


def plan_all(request: TripRequest, db: Any) -> list[Plan] | Verdict:
    """All three ranked candidates, or the verdict. Reads only."""
    return build_all(request, *load(request, db))


# --------------------------------------------------------------------------- #
# --demo
# --------------------------------------------------------------------------- #


def render(result: Plan | Verdict, request: TripRequest) -> str:
    """The plan as terminal text."""
    if isinstance(result, Verdict):
        lines = [f"VERDICT: {result.status}", ""]
        lines += [
            f"  {r.label:38s} {r.value} {r.unit}".rstrip() for r in result.reasons
        ]
        lines.append("")
        lines.append("Alternatives")
        for alt in result.alternatives:
            lines += [f"  * {alt.title}", f"      {alt.description}"]
        return "\n".join(lines)

    head = (
        f"{' + '.join(request.destination_cities)} - {request.days} days from "
        f"{request.origin_city} - {request.pace} pace - party of {request.party_size}"
    )
    lines = [head, "=" * len(head)]
    for day in result.days:
        lines += [
            "",
            (
                f"Day {day.index}  {day.date:%a %d %b %Y}  {day.city}  "
                f"(ends {day.ends_at:%H:%M}, walk {day.walk_km} km, "
                f"road {day.road_km} km, Rs {day.spend_inr})"
            ),
        ]
        for item in day.items:
            if isinstance(item, Move):
                tail = " (estimated)" if item.is_estimated else ""
                lines.append(
                    f"               ~ {item.minutes:>3} min {item.mode} "
                    f"{item.km} km to {item.to_name}{tail}"
                )
            else:
                lines.append(
                    f"  {item.arrive:%H:%M}-{item.depart:%H:%M}  {item.name}  "
                    f"[{item.leg_type}]  Rs {item.cost_inr}"
                )
                if item.name_kn:
                    lines.append(f"                 {item.name_kn}")
                lines.append(f"                 {item.why}")
    m = result.metrics
    lines += [
        "",
        (
            f"Total Rs {result.total_spend} - comfort: {result.comfort} - "
            f"plan B: {'yes' if result.has_plan_b else 'no'}"
        ),
        (
            f"metrics: before {m.route_km_before} km | after {m.route_km_after} km "
            f"| improvement {m.improvement_pct}% | repairs {m.repair_iterations} "
            f"| candidates {m.candidates_considered} | build {m.build_ms} ms "
            f"| checks {m.constraint_checks_passed}/{m.constraint_checks_total}"
        ),
    ]
    return "\n".join(lines)


IST = timezone(timedelta(hours=5, minutes=30))


def demo_request() -> TripRequest:
    """Two days in Mysuru from Bengaluru, starting tomorrow."""
    return TripRequest(
        origin_city="Bengaluru",
        destination_cities=["Mysuru"],
        start_date=datetime.now(tz=IST).date() + timedelta(days=1),
        days=2,
        travellers=[
            Traveller(kind="adult", age_band="40-59"),
            Traveller(kind="adult", age_band="40-59"),
        ],
        trip_type="heritage",
        pace="comfortable",
        budget_inr=20000,
        budget_basis="total",
        transport="any",
        getting_around="cab",
        interest_tags=["heritage", "palace", "food", "photography"],
        notes="Review demo trip.",
    )


def demo() -> int:
    import psycopg
    from dotenv import load_dotenv

    load_dotenv()
    request = demo_request()
    with psycopg.connect(os.environ["SUPABASE_DB_URL"]) as conn:
        result = plan(request, conn)
    print(render(result, request))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="travel-yantra deterministic planner")
    parser.add_argument(
        "--demo", action="store_true", help="plan and print a sample Mysuru trip"
    )
    args = parser.parse_args()
    if args.demo:
        return demo()
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

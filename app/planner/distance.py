"""Great-circle distance and the road-time model.

Road time is a straight-line distance inflated by a detour factor and divided by
an average speed: slow inside a city, faster between cities. Anything derived
this way is estimated; a real `intercity_leg` row always wins over the formula.
"""

from __future__ import annotations

import math

from .models import Leg, Move, Poi

EARTH_KM = 6371.0088
DETOUR = 1.35  # straight line -> road
CITY_KMH = 22.0
INTERCITY_KMH = 45.0
WALK_LIMIT_KM = 1.0  # a road hop this short is walked rather than driven

Point = tuple[float, float]


def haversine(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance in kilometres."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_KM * math.asin(math.sqrt(a))


def road_minutes(straight_km: float, *, intercity: bool = False) -> int:
    """Driving minutes for a straight-line distance, rounded up."""
    speed = INTERCITY_KMH if intercity else CITY_KMH
    return math.ceil(straight_km * DETOUR / speed * 60)


def local_hop(a: Poi, b: Poi) -> tuple[int, float, str]:
    """(minutes, road km, mode) between two stops in the same city.

    Short hops are labelled walks so a day can report how much of it is on foot,
    but every hop is timed at the one city speed. A separate pedestrian speed
    would make minutes non-monotone in kilometres, and 2-opt minimises minutes
    while the map toggle compares kilometres - the two have to agree.
    """
    straight = haversine(a.lat, a.lng, b.lat, b.lng)
    km = round(straight * DETOUR, 2)
    return road_minutes(straight), km, "walk" if km <= WALK_LIMIT_KM else "drive"


def find_leg(legs: list[Leg], a: str, b: str, transport: str) -> Leg | None:
    """Fastest stored leg between two cities, either direction, honouring transport."""
    matches = [
        leg
        for leg in legs
        if {leg.from_city, leg.to_city} == {a, b}
        and (transport == "any" or leg.mode == transport)
    ]
    return (
        min(matches, key=lambda leg: (leg.duration_min, leg.mode)) if matches else None
    )


def intercity_move(
    a: str,
    b: str,
    transport: str,
    legs: list[Leg],
    centroids: dict[str, Point],
) -> Move:
    """A city-to-city Move. A stored leg wins; the formula is the fallback."""
    leg = find_leg(legs, a, b, transport)
    if leg is not None:
        km = float(leg.distance_km) if leg.distance_km else 0.0
        return Move(
            from_name=a,
            to_name=b,
            minutes=leg.duration_min,
            km=km,
            mode=leg.mode,
            is_estimated=leg.is_estimated,
        )
    missing = [c for c in (a, b) if c not in centroids]
    if missing:
        # A city nobody has seeded and nobody could place. The API turns this
        # sentence into a 422; a KeyError here used to be a 500.
        raise ValueError(f"unknown city: {missing[0]}")
    (lat1, lng1), (lat2, lng2) = centroids[a], centroids[b]
    straight = haversine(lat1, lng1, lat2, lng2)
    return Move(
        from_name=a,
        to_name=b,
        minutes=road_minutes(straight, intercity=True),
        km=round(straight * DETOUR, 1),
        mode="car" if transport == "any" else transport,
        is_estimated=True,
    )

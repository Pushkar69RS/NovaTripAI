"""Ordering the stops of one day: nearest neighbour, then 2-opt.

2-opt minimises total travel *minutes* (a short hop is walked, which is slower
per kilometre than driving), while kilometres are reported separately. Both the
pre-2-opt order and the improved one are returned — the map toggle in the UI
needs the before route, so it is never thrown away.
"""

from __future__ import annotations

from itertools import pairwise

from .distance import CITY_KMH, DETOUR, haversine
from .models import Poi

MAX_ITER = 200


def matrices(stops: list[Poi]) -> tuple[list[list[float]], list[list[float]]]:
    """(travel minutes, road km) between every pair of stops, both unrounded."""
    n = len(stops)
    minutes = [[0.0] * n for _ in range(n)]
    km = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            straight = haversine(stops[i].lat, stops[i].lng, stops[j].lat, stops[j].lng)
            km[i][j] = km[j][i] = straight * DETOUR
            minutes[i][j] = minutes[j][i] = straight * DETOUR / CITY_KMH * 60
    return minutes, km


def total(order: list[int], cost: list[list[float]]) -> float:
    return sum(cost[a][b] for a, b in pairwise(order))


def nearest_neighbour(stops: list[Poi], start: int = 0) -> list[int]:
    """Greedy order: from `start`, always hop to the closest unvisited stop."""
    remaining = [i for i in range(len(stops)) if i != start]
    order = [start]
    while remaining:
        last = stops[order[-1]]
        nxt = min(
            remaining,
            key=lambda i: (
                haversine(last.lat, last.lng, stops[i].lat, stops[i].lng),
                i,
            ),
        )
        remaining.remove(nxt)
        order.append(nxt)
    return order


def two_opt(
    order: list[int], cost: list[list[float]], max_iter: int = MAX_ITER
) -> list[int]:
    """Reverse the segment that saves the most, until nothing saves anything.

    Only strictly improving reversals are applied, so the result is never longer
    than the order that went in.
    """
    order = list(order)
    for _ in range(max_iter):
        best, swap = 0.0, None
        for i in range(len(order) - 2):
            for j in range(i + 2, len(order)):
                a, b, c = order[i], order[i + 1], order[j]
                d = order[j + 1] if j + 1 < len(order) else None
                gain = cost[a][b] - cost[a][c]
                if d is not None:
                    gain += cost[c][d] - cost[b][d]
                if gain > best:
                    best, swap = gain, (i, j)
        if swap is None:
            return order
        i, j = swap
        order[i + 1 : j + 1] = reversed(order[i + 1 : j + 1])
    return order


def optimise(
    stops: list[Poi], start: int = 0
) -> tuple[list[int], list[int], float, float]:
    """(order before 2-opt, order after, km before, km after)."""
    if len(stops) < 2:
        order = list(range(len(stops)))
        return order, order, 0.0, 0.0
    minutes, km = matrices(stops)
    before = nearest_neighbour(stops, start)
    after = two_opt(before, minutes)
    return before, after, round(total(before, km), 2), round(total(after, km), 2)

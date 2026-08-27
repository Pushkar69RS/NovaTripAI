"""k-means over (lat, lng), written out rather than imported.

k-means++ seeding with a fixed seed, so the same request always produces the
same clusters. Longitude is scaled by cos(latitude) before the planar distance
so a degree east is worth the same as a degree north at Karnataka's latitude.
"""

from __future__ import annotations

import math
import random

SEED = 20260828
MAX_ITER = 50

Point = tuple[float, float]


def _project(points: list[Point]) -> list[Point]:
    """(lat, lng) -> planar (y, x) in degrees, longitude scaled at the mean latitude."""
    scale = math.cos(math.radians(sum(p[0] for p in points) / len(points)))
    return [(lat, lng * scale) for lat, lng in points]


def _d2(a: Point, b: Point) -> float:
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2


def _kmeans_plus_plus(pts: list[Point], k: int, rng: random.Random) -> list[Point]:
    centres = [pts[rng.randrange(len(pts))]]
    while len(centres) < k:
        weights = [min(_d2(p, c) for c in centres) for p in pts]
        if sum(weights) == 0:  # every remaining point coincides with a centre
            centres.append(pts[rng.randrange(len(pts))])
        else:
            centres.append(rng.choices(pts, weights=weights, k=1)[0])
    return centres


def kmeans(points: list[Point], k: int, *, seed: int = SEED) -> list[list[int]]:
    """Partition point indices into exactly k non-empty clusters."""
    if k < 1:
        raise ValueError("k must be at least 1")
    k = min(k, len(points))
    pts = _project(points)
    rng = random.Random(seed)
    centres = _kmeans_plus_plus(pts, k, rng)

    clusters: list[list[int]] = [[] for _ in range(k)]
    for _ in range(MAX_ITER):
        clusters = [[] for _ in range(k)]
        for i, p in enumerate(pts):
            clusters[min(range(k), key=lambda c: _d2(p, centres[c]))].append(i)
        _refill(clusters, pts, centres)
        moved = [
            (
                sum(pts[i][0] for i in c) / len(c),
                sum(pts[i][1] for i in c) / len(c),
            )
            for c in clusters
        ]
        if moved == centres:
            break
        centres = moved
    return clusters


def _refill(clusters: list[list[int]], pts: list[Point], centres: list[Point]) -> None:
    """Give every empty cluster the point its own cluster fits worst."""
    for empty in clusters:
        if empty:
            continue
        d = max(range(len(clusters)), key=lambda c: len(clusters[c]))
        if len(clusters[d]) < 2:  # nothing to spare
            continue
        i = max(clusters[d], key=lambda i: _d2(pts[i], centres[d]))
        clusters[d].remove(i)
        empty.append(i)


def balance(
    clusters: list[list[int]],
    points: list[Point],
    capacity: int,
    score: list[float],
) -> tuple[list[list[int]], list[int]]:
    """Trim every cluster to `capacity`.

    Overflow moves to the nearest cluster that still has room, highest score
    first; whatever no longer fits is returned as a spill pool the engine keeps
    in reserve for backfill and repair.
    """
    pts = _project(points)
    kept = [sorted(c, key=lambda i: -score[i])[:capacity] for c in clusters]
    pending = sorted(
        (i for c, k in zip(clusters, kept, strict=True) for i in c if i not in k),
        key=lambda i: -score[i],
    )

    spill: list[int] = []
    for i in pending:
        room = [c for c in range(len(kept)) if len(kept[c]) < capacity]
        if not room:
            spill.append(i)
            continue
        nearest = min(
            room,
            key=lambda c: min(_d2(pts[i], pts[j]) for j in kept[c]) if kept[c] else 0.0,
        )
        kept[nearest].append(i)
    return kept, spill

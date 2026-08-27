"""Pydantic models for the deterministic planner.

Nothing here talks to a database or an LLM. `Poi` and `Advisory` are the input
side (rows as loaded from Postgres or from the offline seed file); everything
else is the output side that the API and the UI render.
"""

from __future__ import annotations

from datetime import date, time
from typing import Literal

from pydantic import BaseModel, Field

Pace = Literal["relaxed", "comfortable", "packed"]
Transport = Literal["train", "car", "bus", "any"]

#: Stops a single day can hold, by pace.
PACE_CAPACITY: dict[str, int] = {"relaxed": 3, "comfortable": 4, "packed": 6}


class TripRequest(BaseModel):
    origin_city: str
    destination_cities: list[str] = Field(min_length=1)
    start_date: date
    days: int = Field(ge=1)
    party_size: int = Field(ge=1)
    has_elderly: bool = False
    has_children: bool = False
    pace: Pace = "comfortable"
    budget_inr: int = Field(ge=0)
    transport: Transport = "any"
    interest_tags: list[str] = []
    notes: str | None = None

    @property
    def capacity(self) -> int:
        return PACE_CAPACITY[self.pace]


class Poi(BaseModel):
    """A candidate stop. `score` is internal ranking state and never reaches output."""

    id: int
    name: str
    name_kn: str | None = None
    city: str
    lat: float
    lng: float
    category: str
    tags: list[str] = []
    typical_dwell_min: int = Field(gt=0)
    entry_fee_inr: int = 0
    opens: time | None = None
    closes: time | None = None
    closed_on: list[int] = []  # ISO weekday: 1=Mon .. 7=Sun
    elderly_friendly: bool = True
    popularity: int = 3
    score: float = 0.0


class Advisory(BaseModel):
    poi_id: int | None = None
    city: str | None = None
    severity: Literal["info", "warning", "closed"]
    message: str


class Leg(BaseModel):
    """A known city-to-city connection from `intercity_leg`."""

    from_city: str
    to_city: str
    mode: Literal["car", "bus", "train"]
    distance_km: int | None = None
    duration_min: int = Field(gt=0)
    is_estimated: bool = True


class Stop(BaseModel):
    kind: Literal["stop"] = "stop"
    poi_id: int
    name: str
    name_kn: str | None = None
    lat: float
    lng: float
    arrive: time
    depart: time
    dwell_min: int
    cost_inr: int
    leg_type: Literal["hard", "soft"]
    tags: list[str] = []
    note: str | None = None
    why: str


class Move(BaseModel):
    kind: Literal["move"] = "move"
    from_name: str
    to_name: str
    minutes: int
    km: float
    mode: str
    is_estimated: bool


class Day(BaseModel):
    index: int
    date: date
    city: str
    items: list[Stop | Move] = []
    ends_at: time
    walk_km: float = 0.0
    road_km: float = 0.0
    spend_inr: int = 0

    @property
    def stops(self) -> list[Stop]:
        return [i for i in self.items if isinstance(i, Stop)]

    @property
    def moves(self) -> list[Move]:
        return [i for i in self.items if isinstance(i, Move)]


class PlanMetrics(BaseModel):
    route_km_before: float
    route_km_after: float
    improvement_pct: float
    repair_iterations: int
    candidates_considered: int
    build_ms: int
    constraint_checks_passed: int
    constraint_checks_total: int


class Plan(BaseModel):
    days: list[Day]
    total_spend: int
    comfort: Literal["comfortable", "tight"]
    has_plan_b: bool
    metrics: PlanMetrics


class Reason(BaseModel):
    """One row of the arithmetic the UI renders as a table."""

    label: str
    value: int | float | str
    unit: str


class Alternative(BaseModel):
    title: str
    description: str
    request_override: dict


class Verdict(BaseModel):
    status: Literal["ok", "strained", "impossible"]
    reasons: list[Reason] = []
    alternatives: list[Alternative] = []

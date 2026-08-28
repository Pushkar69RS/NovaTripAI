"""Pydantic models for the deterministic planner.

Nothing here talks to a database or an LLM. `Poi` and `Advisory` are the input
side (rows as loaded from Postgres or from the offline seed file); everything
else is the output side that the API and the UI render.
"""

from __future__ import annotations

from datetime import date, time
from typing import Literal

from pydantic import BaseModel, Field, model_validator

Pace = Literal["relaxed", "comfortable", "packed"]
Transport = Literal["train", "car", "bus", "any"]
TripType = Literal[
    "family",
    "pilgrimage",
    "heritage",
    "nature",
    "food",
    "adventure",
    "couple",
    "friends",
]
GettingAround = Literal["cab", "own_car", "auto_public", "suggest"]

ADULT_BANDS = ("18-39", "40-59", "60+")
CHILD_BANDS = ("under 3", "3-5", "6-12", "13-17")
TODDLER_BANDS = ("under 3", "3-5")  # a pram and a knee want the same day

#: What a trip type is usually about, used only when nothing was ticked.
TRIP_TYPE_TAGS: dict[str, list[str]] = {
    "pilgrimage": ["spiritual"],
    "heritage": ["heritage"],
    "nature": ["nature", "waterfall"],
    "food": ["food"],
    "family": ["heritage", "food"],
    "adventure": ["nature", "trek"],
    "couple": ["quiet", "nature"],
    "friends": ["food", "photography"],
}

#: Stops a single day can hold, by pace.
PACE_CAPACITY: dict[str, int] = {"relaxed": 3, "comfortable": 4, "packed": 6}

#: poi.city is the hub city (see data/pois.json _notes). A traveller types the
#: locality; the planner works in the hub whose rows hold it.
HUBS = ("Bengaluru", "Mysuru", "Hampi", "Chikmagalur", "Coorg")
LOCALITIES: dict[str, str] = {
    "bangalore": "Bengaluru",
    "mysore": "Mysuru",
    "srirangapatna": "Mysuru",
    "hospet": "Hampi",
    "hosapete": "Hampi",
    "belur": "Chikmagalur",
    "halebidu": "Chikmagalur",
    "chikkamagaluru": "Chikmagalur",
    "kodagu": "Coorg",
    "madikeri": "Coorg",
    "kushalnagar": "Coorg",
} | {h.lower(): h for h in HUBS}


def hub_city(name: str) -> str:
    """The hub city for a typed place. An unknown name is kept, title-cased, so
    Mangalore and mangalore are one city in poi and city_centre."""
    key = name.strip().lower()
    return LOCALITIES.get(key, " ".join(w.capitalize() for w in name.split()))


class Traveller(BaseModel):
    kind: Literal["adult", "child"]
    age_band: str

    @model_validator(mode="after")
    def _band_fits_kind(self) -> Traveller:
        bands = ADULT_BANDS if self.kind == "adult" else CHILD_BANDS
        if self.age_band not in bands:
            raise ValueError(f"{self.kind} age band must be one of {bands}")
        return self


class TripRequest(BaseModel):
    origin_city: str
    destination_cities: list[str] = Field(min_length=1)
    places: list[str] = []  # what the traveller typed, localities included
    start_date: date
    days: int = Field(ge=1)
    travellers: list[Traveller] = []  # when given, the party facts derive from it
    party_size: int = Field(default=1, ge=1)
    has_elderly: bool = False
    has_children: bool = False
    trip_type: TripType | None = None
    pace: Pace = "comfortable"
    budget_inr: int = Field(ge=0)  # always the total; the form converts per-head
    budget_basis: Literal["total", "per_person"] = "total"
    transport: Transport = "any"
    getting_around: GettingAround = "suggest"
    food: str | None = None  # veg | jain | None; the narrator reads it
    interest_tags: list[str] = []
    must_see: list[str] = []  # the narrator and the chat read these
    skip: list[str] = []  # a word in a place's name, tags or category
    notes: str | None = None
    day_end: time | None = None  # None: 20:00, or 19:00 with an elder or a toddler

    @model_validator(mode="before")
    @classmethod
    def _to_hubs(cls, data: object) -> object:
        if not isinstance(data, dict) or not data.get("destination_cities"):
            return data
        typed = [str(c).strip() for c in data["destination_cities"] if str(c).strip()]
        hubs = list(dict.fromkeys(hub_city(c) for c in typed))
        out = {
            **data,
            "destination_cities": hubs,
            "places": data.get("places") or typed,
        }
        if data.get("origin_city"):
            out["origin_city"] = hub_city(str(data["origin_city"]))
        return out

    @model_validator(mode="after")
    def _derive(self) -> TripRequest:
        # Explicit party_size / has_elderly still win when no travellers were
        # listed, so stored trips and the planner tests keep working.
        if self.travellers:
            self.party_size = len(self.travellers)
            self.has_elderly = any(
                t.kind == "adult" and t.age_band == "60+" for t in self.travellers
            )
            self.has_children = any(t.kind == "child" for t in self.travellers)
        if not self.interest_tags and self.trip_type:
            self.interest_tags = list(TRIP_TYPE_TAGS[self.trip_type])
        return self

    @property
    def has_toddler(self) -> bool:
        return any(
            t.kind == "child" and t.age_band in TODDLER_BANDS for t in self.travellers
        )

    @property
    def gentle(self) -> bool:
        """An elder or a child under six: earlier evenings, easier places."""
        return self.has_elderly or self.has_toddler

    @property
    def capacity(self) -> int:
        pace = (
            "comfortable" if self.has_toddler and self.pace == "packed" else self.pace
        )
        return PACE_CAPACITY[pace]

    @property
    def title(self) -> str:
        return " & ".join(self.places or self.destination_cities)


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
    trust: str = "draft"  # verified | draft | ai_generated
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
    trust: str = "draft"  # copied from the Poi, so the page can say AI-drafted


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
    naive_order: list[int] = []  # poi ids in candidate-score order: "as listed"
    naive_km: float = 0.0  # road km of visiting them in that order
    route_km: float = 0.0  # road km in the order built, measured the same way

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
    route_km_naive: float = 0.0  # every day visited in list order, no routing


class Plan(BaseModel):
    days: list[Day]
    total_spend: int
    comfort: Literal["comfortable", "tight"]
    has_plan_b: bool
    metrics: PlanMetrics
    variant: str = "steady"  # which scoring mix built it; see engine.VARIANTS


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

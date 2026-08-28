"""The traveller's own words, read into the intake form. Never a guess.

Every field is optional. Anything the text does not say stays unfilled, a date
is never invented, and any shape the model gets wrong empties the whole fill
rather than half-filling a form the traveller then trusts.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.llm.client import complete
from app.llm.models import MODELS
from app.planner.models import GettingAround, Traveller, TripType

NOTE = "Couldn't read that — fill it in by hand"

#: A date is only ever taken when the text itself names one.
DATE_HINT = re.compile(
    r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\b"
    r"|\b(mon|tue|wed|thu|fri|sat|sun)[a-z]*\b"
    r"|\b(today|tomorrow|tonight|weekend|next week|next month)\b"
    r"|\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}[/.-]\d{1,2}(?:[/.-]\d{2,4})?\b"
    r"|\b\d{1,2}(st|nd|rd|th)\b",
    re.IGNORECASE,
)


class ParsedIntake(BaseModel):
    model_config = ConfigDict(extra="forbid")

    origin_city: str | None = None
    destination_cities: list[str] | None = Field(default=None, max_length=3)
    start_date: date | None = None
    days: int | None = Field(default=None, ge=1, le=14)
    travellers: list[Traveller] | None = Field(default=None, max_length=12)
    trip_type: TripType | None = None
    budget_inr: int | None = Field(default=None, ge=0)
    budget_basis: Literal["total", "per_person"] | None = None
    transport: Literal["train", "bus", "flight", "car", "any"] | None = None
    getting_around: GettingAround | None = None
    interest_tags: list[str] | None = None
    must_see: list[str] | None = None
    skip: list[str] | None = None
    food: Literal["veg", "jain"] | None = None


SYSTEM = (
    "You read a traveller's own words into a trip form. Answer with one JSON "
    "object using only these keys, and only when the text states the value: "
    "origin_city, destination_cities (list, up to 3), start_date (YYYY-MM-DD "
    "ONLY when the text names a date or a day; never invent one), days (int), "
    "travellers (list of {kind: adult|child, age_band}; adult bands 18-39, 40-59, "
    "60+; child bands 'under 3', '3-5', '6-12', '13-17'; one entry per person "
    "including the writer; the writer's parents, amma, appa or grandparents are "
    "adults 60+; the writer and a partner are 40-59 unless told otherwise; a "
    "child's band from its age), trip_type (family|pilgrimage|heritage|nature|"
    "food|adventure|couple|friends), budget_inr (int, the figure as written), "
    "budget_basis (total|per_person), transport (train|bus|flight|car|any), "
    "getting_around (cab|own_car|auto_public|suggest), interest_tags (from: "
    "heritage, food, spiritual, nature, waterfall, wildlife, shopping, "
    "photography, quiet, trek), must_see (list of place names), skip (list), "
    "food (veg|jain). Omit every key the text does not settle. No other keys, "
    "no prose."
)


def _fill(text: str, data: Any, today: date) -> dict:
    if not isinstance(data, dict):
        raise TypeError("not an object")
    parsed = ParsedIntake.model_validate(
        {k: v for k, v in data.items() if v is not None}
    )
    if parsed.start_date is not None and (
        not DATE_HINT.search(text) or parsed.start_date < today
    ):
        parsed.start_date = None
    return parsed.model_dump(mode="json", exclude_none=True)


def parse_intake(text: str, *, llm: Any = complete, today: date | None = None) -> dict:
    """{"filled": {field: value}, "note": None} or an empty fill with a note."""
    today = today or datetime.now(tz=timezone(timedelta(hours=5, minutes=30))).date()
    try:
        raw = llm(
            [
                {"role": "system", "content": SYSTEM},
                {
                    "role": "user",
                    "content": f"TODAY: {today.isoformat()}\nTEXT: {text}",
                },
            ],
            model=MODELS["parse_intake"],
            temperature=0.0,
            json_mode=True,
        ).text
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip())
        filled = _fill(text, json.loads(cleaned), today)
    except (ValidationError, ValueError, TypeError, KeyError, RuntimeError, OSError):
        return {"filled": {}, "note": NOTE}
    return {"filled": filled, "note": None}

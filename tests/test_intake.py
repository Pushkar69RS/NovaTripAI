"""The intake parser: a fixed reply maps, a wrong one empties the fill."""

from __future__ import annotations

import json
from datetime import date

from app.llm.client import Completion
from app.llm.intake import NOTE, ParsedIntake, parse_intake

TEXT = (
    "3 days in Mysuru and Hampi with my parents and our 4-year-old, around "
    "20,000 total, we love temples and food, going by train"
)
REPLY = {
    "destination_cities": ["Mysuru", "Hampi"],
    "days": 3,
    "travellers": [
        {"kind": "adult", "age_band": "40-59"},
        {"kind": "adult", "age_band": "60+"},
        {"kind": "adult", "age_band": "60+"},
        {"kind": "child", "age_band": "3-5"},
    ],
    "budget_inr": 20000,
    "budget_basis": "total",
    "interest_tags": ["spiritual", "food"],
    "transport": "train",
    "start_date": None,
}
TODAY = date(2026, 8, 28)


class Fake:
    def __init__(self, text: str) -> None:
        self.text = text

    def __call__(self, messages, *, model, temperature, json_mode, **kw) -> Completion:
        assert temperature == 0.0 and json_mode
        return Completion(self.text, model, 50, 80, 0.0001, 300)


def test_a_fixed_reply_maps_to_the_form_fields() -> None:
    out = parse_intake(TEXT, llm=Fake(json.dumps(REPLY)), today=TODAY)
    assert out["note"] is None
    filled = out["filled"]
    assert filled["destination_cities"] == ["Mysuru", "Hampi"]
    assert filled["days"] == 3 and filled["transport"] == "train"
    assert len(filled["travellers"]) == 4 and filled["travellers"][3]["kind"] == "child"
    assert "start_date" not in filled and "origin_city" not in filled
    assert ParsedIntake.model_validate(filled)


def test_malformed_json_or_a_wrong_field_returns_an_empty_fill() -> None:
    assert parse_intake(TEXT, llm=Fake("not json {"), today=TODAY) == {
        "filled": {},
        "note": NOTE,
    }
    wrong = {**REPLY, "hotel": "five star"}
    assert parse_intake(TEXT, llm=Fake(json.dumps(wrong)), today=TODAY)["filled"] == {}
    bad_band = {**REPLY, "travellers": [{"kind": "child", "age_band": "60+"}]}
    assert (
        parse_intake(TEXT, llm=Fake(json.dumps(bad_band)), today=TODAY)["filled"] == {}
    )
    assert parse_intake(TEXT, llm=Fake("[1, 2]"), today=TODAY)["filled"] == {}


def test_a_date_is_never_invented() -> None:
    invented = {**REPLY, "start_date": "2026-09-14"}
    out = parse_intake(TEXT, llm=Fake(json.dumps(invented)), today=TODAY)
    assert "start_date" not in out["filled"]  # the text names no date
    named = "Mysuru from 14 September for 3 days"
    out = parse_intake(named, llm=Fake(json.dumps(invented)), today=TODAY)
    assert out["filled"]["start_date"] == "2026-09-14"
    past = parse_intake(
        named, llm=Fake(json.dumps({**REPLY, "start_date": "2020-01-01"})), today=TODAY
    )
    assert "start_date" not in past["filled"]


def test_a_failing_model_is_an_empty_fill_not_an_error() -> None:
    def boom(*a, **k):
        raise RuntimeError("no network")

    assert parse_intake(TEXT, llm=boom, today=TODAY)["note"] == NOTE

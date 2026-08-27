"""Chat classification and one-day repair, offline, on the planner fixtures."""

from __future__ import annotations

import json

import pytest

from app.chat.router import (
    Clarification,
    EditInstruction,
    Question,
    apply_edit,
    classify,
    parse_classification,
    resolve,
)
from app.llm.client import Completion
from app.planner.engine import scored_pool
from app.planner.models import Plan
from tests.test_planner import advisories, centroids, edges, legs, pois, run, trip


@pytest.fixture(scope="module")
def world():
    request = trip(days=3, pace="comfortable")
    plan = run(request)
    assert isinstance(plan, Plan)
    loaded = (pois(), edges(), legs(), advisories(), centroids())
    by_city: dict[str, list] = {}
    for p in scored_pool(pois(), request, edges(), advisories()).values():
        by_city.setdefault(p.city, []).append(p)
    return request, plan, loaded, by_city


def snapshot(plan: Plan) -> list[str]:
    return [d.model_dump_json() for d in plan.days]


def fake(reply: str):
    def llm(messages, *, model, temperature, **kw) -> Completion:
        return Completion(reply, model, 1, 1, 0.0, 1)

    return llm


def boom(messages, **kw):
    raise AssertionError("the model must not be called for a plain question")


# --------------------------------------------------------------------------- #
# classification
# --------------------------------------------------------------------------- #


def test_a_question_never_reaches_the_model(world) -> None:
    _, plan, _, _ = world
    out = classify("What is the story behind the palace?", plan, llm=boom)
    assert isinstance(out, Question)


def test_a_malformed_edit_becomes_a_clarifying_question(world) -> None:
    _, plan, _, by_city = world
    before = snapshot(plan)

    garbage = classify("remove the thing please", plan, llm=fake("not json at all {"))
    assert isinstance(garbage, Clarification)

    wrong_shape = classify(
        "remove the thing", plan, llm=fake('{"kind": "edit", "action": "teleport"}')
    )
    assert isinstance(wrong_shape, Clarification)

    unknown = parse_classification(
        '{"kind": "edit", "action": "remove", "target": "the moon", "day_index": 2}',
        "remove the moon from day 2",
    )
    assert isinstance(unknown, EditInstruction)
    asked = resolve(unknown, plan, by_city)
    assert isinstance(asked, Clarification)
    assert "day 2" in asked.question

    no_day = resolve(
        EditInstruction(action="remove", target="palace", day_index=None), plan, by_city
    )
    assert isinstance(no_day, Clarification) and "Which day" in no_day.question

    assert snapshot(plan) == before  # nothing was mangled on the way


def test_a_kind_of_place_resolves_to_the_best_unused_one_of_that_kind(world) -> None:
    _, plan, _, by_city = world
    edit = resolve(
        EditInstruction(action="add", target="one more food stop", day_index=2),
        plan,
        by_city,
    )
    assert isinstance(edit, EditInstruction)
    chosen = next(p for p in by_city["Mysuru"] if p.name == edit.target)
    assert chosen.category == "food"
    assert chosen.id not in {s.poi_id for d in plan.days for s in d.stops}

    still_unclear = resolve(
        EditInstruction(action="add", target="something nice", day_index=2),
        plan,
        by_city,
    )
    assert isinstance(still_unclear, Clarification)

    # the model may leave the target empty; the traveller's own words decide
    parsed = parse_classification(
        '{"kind": "edit", "action": "add", "target": null, "day_index": 2}',
        "Add one more food stop to day 2",
    )
    assert isinstance(parsed, EditInstruction) and parsed.message
    from_words = resolve(parsed, plan, by_city)
    assert isinstance(from_words, EditInstruction)
    assert (
        next(p for p in by_city["Mysuru"] if p.name == from_words.target).category
        == "food"
    )


def test_a_day_named_in_the_message_beats_the_model() -> None:
    edit = parse_classification(
        '{"kind": "edit", "action": "add", "target": "food stop", "day_index": 1}',
        "Add one more food stop to day 2",
    )
    assert isinstance(edit, EditInstruction) and edit.day_index == 2
    silent = parse_classification(
        '{"kind": "edit", "action": "remove", "target": "zoo", "day_index": 3}',
        "drop the zoo",
    )
    assert isinstance(silent, EditInstruction) and silent.day_index == 3


def test_the_quick_chip_words_read_as_edits(world) -> None:
    _, plan, _, _ = world
    lighter = classify(
        "Make Day 2 lighter",
        plan,
        llm=fake(
            '{"kind": "edit", "action": "change_pace", "day_index": 2, "value": "lighter"}'
        ),
    )
    assert isinstance(lighter, EditInstruction) and lighter.action == "change_pace"


def test_a_well_formed_edit_resolves_to_a_real_stop(world) -> None:
    _, plan, _, by_city = world
    stop = plan.days[2].stops[-1]
    raw = json.dumps(
        {
            "kind": "edit",
            "action": "remove",
            "target": stop.name.split()[0].lower(),
            "day_index": 3,
        }
    )
    edit = parse_classification(raw, "")
    assert isinstance(edit, EditInstruction)
    resolved = resolve(edit, plan, by_city)
    assert isinstance(resolved, EditInstruction)
    assert resolved.target == stop.name


# --------------------------------------------------------------------------- #
# repair
# --------------------------------------------------------------------------- #


def test_removing_a_stop_changes_exactly_one_day(world) -> None:
    request, plan, loaded, by_city = world
    before = snapshot(plan)
    day = plan.days[1]
    victim = next(s for s in day.stops if s.leg_type == "soft")
    edit = resolve(
        EditInstruction(action="remove", target=victim.name, day_index=2), plan, by_city
    )
    assert isinstance(edit, EditInstruction)

    result = apply_edit(edit, plan, request, loaded)
    after = snapshot(result.plan)

    assert result.changed_day == 2
    assert after[0] == before[0] and after[2] == before[2], "other days byte-identical"
    assert after[1] != before[1]
    assert victim.poi_id not in {s.poi_id for s in result.plan.days[1].stops}
    assert result.change_summary.removed == [victim.name]
    assert result.change_summary.added == []
    assert snapshot(plan) == before  # the original plan is untouched


def test_shifting_the_start_moves_only_that_day(world) -> None:
    request, plan, loaded, by_city = world
    before = snapshot(plan)
    edit = resolve(
        EditInstruction(action="shift_time", day_index=3, value="10:30"), plan, by_city
    )
    assert isinstance(edit, EditInstruction) and edit.value == "10:30"
    result = apply_edit(edit, plan, request, loaded)
    after = snapshot(result.plan)
    assert after[:2] == before[:2]
    first = result.plan.days[2].stops[0]
    assert (first.arrive.hour, first.arrive.minute) >= (10, 30)
    assert result.change_summary.times_shifted >= 1
    assert result.change_summary.removed == [] or result.violations


def test_the_hard_stop_survives_an_edit(world) -> None:
    request, plan, loaded, by_city = world
    anchor = next(s for s in plan.days[0].stops if s.leg_type == "hard")
    soft = next(s for s in plan.days[0].stops if s.leg_type == "soft")
    edit = resolve(
        EditInstruction(action="remove", target=soft.name, day_index=1), plan, by_city
    )
    result = apply_edit(edit, plan, request, loaded)
    assert anchor.poi_id in {s.poi_id for s in result.plan.days[0].stops}

"""The post-plan chat. A message is either a question or an edit.

A question goes to retrieval with the trip context and comes back as a grounded
answer with its sources, or as an honest refusal. An edit is parsed into a
strict EditInstruction, resolved against the actual plan, and applied by
rebuilding that one day only; every other day is left byte for byte as it was.
Anything that does not parse or resolve cleanly turns into one clarifying
question rather than a guess.

The model is only asked to do the parsing, and only when the message looks like
an edit. Everything after that is plain code.
"""

from __future__ import annotations

import difflib
import json
import re
from datetime import time
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

from app.llm.client import complete
from app.llm.models import MODELS
from app.llm.narrate import Llm, answer_question
from app.planner.engine import Loaded, rebuild_day, scored_pool
from app.planner.models import Day, Plan, Poi, TripRequest
from app.rag.retrieve import Filters, Hit, TripContext, search

EDIT_WORDS = re.compile(
    r"\b(remove|drop|skip|delete|cancel|take out|add|include|put in|replace|swap|"
    r"instead of|move|shift|later|earlier|start at|push|relaxed|comfortable|"
    r"packed|slower|faster|pace|less rushed|more time)\b",
    re.IGNORECASE,
)
PACE_WORDS = {
    "relaxed": "relaxed",
    "slow": "relaxed",
    "slower": "relaxed",
    "easy": "relaxed",
    "comfortable": "comfortable",
    "normal": "comfortable",
    "packed": "packed",
    "fast": "packed",
    "faster": "packed",
    "busy": "packed",
}
SHIFT_MINUTES = 60  # what "later" and "earlier" mean when no time is given


class Question(BaseModel):
    kind: Literal["question"] = "question"
    text: str


class EditInstruction(BaseModel):
    kind: Literal["edit"] = "edit"
    action: Literal["remove", "add", "replace", "shift_time", "change_pace"]
    target: str | None = None
    day_index: int | None = Field(default=None, ge=1)
    value: str | None = None


class Clarification(BaseModel):
    kind: Literal["clarify"] = "clarify"
    question: str


class ChangeSummary(BaseModel):
    removed: list[str] = []
    added: list[str] = []
    times_shifted: int = 0


class EditResult(BaseModel):
    plan: Plan
    changed_day: int
    change_summary: ChangeSummary
    violations: list[str] = []


class Answer(BaseModel):
    kind: Literal["answer"] = "answer"
    text: str
    sources: list[dict[str, Any]] = []
    refused: bool = False


REFUSAL = {
    "en": "I don't have anything reliable on that, so I'd rather not guess.",
    "kn": "ಇದರ ಬಗ್ಗೆ ನನ್ನ ಬಳಿ ನಂಬಲರ್ಹ ಮಾಹಿತಿ ಇಲ್ಲ, ಹಾಗಾಗಿ ಊಹಿಸಲು ಬಯಸುವುದಿಲ್ಲ.",
    "hi": "इस बारे में मेरे पास कोई भरोसेमंद जानकारी नहीं है, इसलिए मैं अंदाज़ा नहीं लगाऊँगा।",
}


# --------------------------------------------------------------------------- #
# classify
# --------------------------------------------------------------------------- #


def plan_outline(plan: Plan) -> str:
    return "\n".join(
        f"day {d.index} ({d.city}): " + "; ".join(s.name for s in d.stops)
        for d in plan.days
    )


CLASSIFY_SYSTEM = (
    "You turn a traveller's message about their itinerary into JSON and nothing "
    "else. Output exactly one JSON object.\n"
    'A question: {"kind": "question", "text": "<the message>"}\n'
    'An edit: {"kind": "edit", "action": "<remove|add|replace|shift_time|'
    'change_pace>", "target": "<stop or place name or null>", "day_index": '
    '<number or null>, "value": "<see below or null>"}\n'
    "remove: target is the stop to drop. add: target is the place to add. "
    "replace: target is the stop to drop and value is the place to add. "
    "shift_time: value is the new start time as HH:MM, or the word later or "
    "earlier. change_pace: value is relaxed, comfortable or packed.\n"
    "day_index is the day the message refers to. If the message names no day, "
    "use null. Copy names as the traveller wrote them; do not invent places."
)


def classify(
    message: str,
    plan: Plan,
    *,
    llm: Llm = complete,
) -> Question | EditInstruction | Clarification:
    """A Question, an EditInstruction, or a Clarification. Never a guess."""
    if not EDIT_WORDS.search(message):
        return Question(text=message)
    raw = llm(
        [
            {"role": "system", "content": CLASSIFY_SYSTEM},
            {
                "role": "user",
                "content": f"PLAN:\n{plan_outline(plan)}\n\nMESSAGE: {message}",
            },
        ],
        model=MODELS["classify"],
        temperature=0.0,
        json_mode=True,
    ).text
    return parse_classification(raw, message)


def parse_classification(
    raw: str, message: str
) -> Question | EditInstruction | Clarification:
    """Strict parse of the model's JSON. Anything off-shape asks, not guesses."""
    text = raw.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return Clarification(question=_unclear(message))
    if not isinstance(data, dict):
        return Clarification(question=_unclear(message))
    if data.get("kind") == "question":
        return Question(text=str(data.get("text") or message))
    try:
        return EditInstruction.model_validate({**data, "kind": "edit"})
    except ValidationError:
        return Clarification(question=_unclear(message))


def _unclear(message: str) -> str:
    return (
        "I couldn't work out the change you want. Tell me the day and the stop, "
        'for example "remove the zoo from day 2" or "start day 1 at 10:00".'
    )


# --------------------------------------------------------------------------- #
# resolve an edit against the real plan
# --------------------------------------------------------------------------- #


def _match(wanted: str, names: list[str]) -> list[str]:
    """Names that plausibly mean `wanted`: exact, then substring, then fuzzy."""
    w = wanted.lower().strip()
    if not w:
        return []
    low = {n.lower(): n for n in names}
    if w in low:
        return [low[w]]
    contains = [n for n in names if w in n.lower() or n.lower() in w]
    if contains:
        return contains
    words = [x for x in re.findall(r"[a-z]+", w) if len(x) > 3]
    by_word = [n for n in names if any(x in n.lower() for x in words)]
    if by_word:
        return by_word
    return [low[m] for m in difflib.get_close_matches(w, list(low), n=3, cutoff=0.6)]


def _parse_time(value: str, current: time | None) -> time | None:
    v = value.strip().lower()
    m = re.match(r"^(\d{1,2})(?::(\d{2}))?\s*(am|pm)?$", v)
    if m:
        hour, minute = int(m.group(1)), int(m.group(2) or 0)
        if m.group(3) == "pm" and hour < 12:
            hour += 12
        if 0 <= hour < 24 and 0 <= minute < 60:
            return time(hour, minute)
    if current is not None and v in {"later", "earlier"}:
        shift = SHIFT_MINUTES if v == "later" else -SHIFT_MINUTES
        total = max(0, min(23 * 60 + 59, current.hour * 60 + current.minute + shift))
        return time(total // 60, total % 60)
    return None


def resolve(
    edit: EditInstruction, plan: Plan, city_pois: dict[str, list[Poi]]
) -> EditInstruction | Clarification:
    """Pin the edit to a real day and real names, or ask one question."""
    if edit.day_index is None:
        if len(plan.days) == 1:
            edit = edit.model_copy(update={"day_index": 1})
        else:
            return Clarification(
                question=f"Which day? Your plan has days 1 to {len(plan.days)}."
            )
    if not 1 <= edit.day_index <= len(plan.days):
        return Clarification(
            question=f"There is no day {edit.day_index}; the plan runs days 1 to {len(plan.days)}."
        )
    day = plan.days[edit.day_index - 1]
    stop_names = [s.name for s in day.stops]
    place_names = [p.name for p in city_pois.get(day.city, [])]

    def one(wanted: str | None, names: list[str], what: str) -> str | Clarification:
        if not wanted:
            return Clarification(
                question=f"Which {what} do you mean on day {day.index}?"
            )
        found = _match(wanted, names)
        if len(found) == 1:
            return found[0]
        if not found:
            listed = ", ".join(names) or "nothing yet"
            return Clarification(
                question=f"I can't find '{wanted}' for day {day.index}. That day has: {listed}."
            )
        return Clarification(
            question=f"'{wanted}' could be {', or '.join(found[:3])}. Which one?"
        )

    if edit.action in {"remove", "replace"}:
        target = one(edit.target, stop_names, "stop")
        if isinstance(target, Clarification):
            return target
        edit = edit.model_copy(update={"target": target})
    if edit.action == "add":
        already = set(stop_names)
        target = one(edit.target, [n for n in place_names if n not in already], "place")
        if isinstance(target, Clarification):
            return target
        edit = edit.model_copy(update={"target": target})
    if edit.action == "replace":
        value = one(
            edit.value, [n for n in place_names if n not in stop_names], "place"
        )
        if isinstance(value, Clarification):
            return value
        edit = edit.model_copy(update={"value": value})
    if edit.action == "shift_time":
        first = day.stops[0].arrive if day.stops else None
        parsed = _parse_time(edit.value or "", first)
        if parsed is None:
            return Clarification(
                question=f"What time should day {day.index} start? Give me a time like 10:00."
            )
        edit = edit.model_copy(update={"value": parsed.strftime("%H:%M")})
    if edit.action == "change_pace":
        pace = PACE_WORDS.get((edit.value or "").strip().lower())
        if pace is None:
            return Clarification(question="Which pace: relaxed, comfortable or packed?")
        edit = edit.model_copy(update={"value": pace})
    return edit


# --------------------------------------------------------------------------- #
# apply an edit to one day
# --------------------------------------------------------------------------- #


def apply_edit(
    edit: EditInstruction, plan: Plan, request: TripRequest, loaded: Loaded
) -> EditResult:
    """Rebuild exactly one day. The other Day objects are reused untouched."""
    assert edit.day_index is not None
    pois, edges, _legs, advisories, _centroids = loaded
    scored = scored_pool(pois, request, edges, advisories)
    by_name = {p.name: p.id for p in scored.values()}
    old = plan.days[edit.day_index - 1]
    ids = [s.poi_id for s in old.stops]
    start = old.stops[0].arrive if old.stops else time(9, 0)
    pace: str | None = None

    if edit.action == "remove":
        ids = [i for i in ids if i != by_name.get(edit.target)]
    elif edit.action == "add":
        ids = ids + [by_name[edit.target]]
    elif edit.action == "replace":
        ids = [by_name[edit.value] if i == by_name.get(edit.target) else i for i in ids]
    elif edit.action == "shift_time":
        start = time.fromisoformat(edit.value)
    elif edit.action == "change_pace":
        pace = edit.value
        ids = _repace(ids, old, plan, request, scored, pace)

    new_day, violations, _ = rebuild_day(
        plan, request, loaded, edit.day_index, ids, start=start, pace=pace
    )
    days = [new_day if d.index == old.index else d for d in plan.days]
    new_plan = plan.model_copy(
        update={
            "days": days,
            "total_spend": sum(d.spend_inr for d in days),
            "comfort": "tight" if violations else plan.comfort,
        }
    )
    return EditResult(
        plan=new_plan,
        changed_day=old.index,
        change_summary=_summary(old, new_day),
        violations=[v.message for v in violations],
    )


def _repace(
    ids: list[int],
    old: Day,
    plan: Plan,
    request: TripRequest,
    scored: dict[int, Poi],
    pace: str,
) -> list[int]:
    from app.planner.models import PACE_CAPACITY

    capacity = PACE_CAPACITY[pace]
    if len(ids) > capacity:
        anchor = max(ids, key=lambda i: (scored[i].score, -i))
        soft = sorted((i for i in ids if i != anchor), key=lambda i: -scored[i].score)
        return [i for i in ids if i in {anchor, *soft[: capacity - 1]}]
    taken = {s.poi_id for d in plan.days for s in d.stops}
    weekday = old.date.isoweekday()
    spare = sorted(
        (
            p
            for p in scored.values()
            if p.city == old.city and p.id not in taken and weekday not in p.closed_on
        ),
        key=lambda p: (-p.score, p.id),
    )
    return ids + [p.id for p in spare[: capacity - len(ids)]]


def _summary(old: Day, new: Day) -> ChangeSummary:
    before = {s.poi_id: s for s in old.stops}
    after = {s.poi_id: s for s in new.stops}
    return ChangeSummary(
        removed=[s.name for i, s in before.items() if i not in after],
        added=[s.name for i, s in after.items() if i not in before],
        times_shifted=sum(
            1 for i in before if i in after and before[i].arrive != after[i].arrive
        ),
    )


# --------------------------------------------------------------------------- #
# answer a question
# --------------------------------------------------------------------------- #


def answer(
    question: str,
    db: Any,
    *,
    language: str = "en",
    trip_context: TripContext | None = None,
    llm: Llm = complete,
) -> Answer:
    """Grounded prose from retrieved paragraphs, or the honest refusal."""
    hits: list[Hit] = search(
        question, db, filters=Filters(), k=4, trip_context=trip_context
    )
    if not hits:
        return Answer(text=REFUSAL.get(language, REFUSAL["en"]), refused=True)
    narration = answer_question(question, hits, language, llm=llm)
    return Answer(
        text=narration.text,
        sources=[
            {"id": h.id, "title": h.title, "name": h.source_name, "url": h.source_url}
            for h in hits
        ],
    )

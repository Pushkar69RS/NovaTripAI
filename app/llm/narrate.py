"""The narrator. Two jobs, and a fact-check between the model and the listener.

1. narrate_plan     a validated Plan -> warm companion prose
2. narrate_segment  retrieved paragraphs -> one spoken Katha segment

The model may only use what is in its input. That is asked for in the prompt
and then checked: any year, number or (in English) capitalised name in the
output that is not in the input fails the check. On failure the same request
is retried once at temperature 0; if that fails too, the retrieved text is
emitted lightly joined, with no model prose at all. A legend segment must open
with the framing phrase for its language, and gets it prepended if the model
forgot. Percentages, scores and probabilities never pass.

Kannada and Hindi output cannot be checked for names, because the script has
no capitals and the name will be transliterated. Numbers and years are still
checked in every language, with Indic digits normalised first.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field

from app.planner.models import Plan, TripRequest

from .client import Completion, complete
from .models import MODELS

LANGUAGES = {"en": "English", "kn": "Kannada", "hi": "Hindi"}
FRAMING = {"en": "The story goes", "kn": "ಕಥೆಯ ಪ್ರಕಾರ", "hi": "कहते हैं"}
SCRIPT_NOTE = {
    "en": "Write in plain English.",
    "kn": "Write in Kannada, in Kannada script only, with names transliterated.",
    "hi": "Write in Hindi, in Devanagari script only, with names transliterated.",
}
BANNED = ("%", "percent", "probability", "score", "ಶೇಕಡಾ", "प्रतिशत")

INDIC_DIGITS = str.maketrans("೦೧೨೩೪೫೬೭೮೯०१२३४५६७८९", "01234567890123456789")
NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")
WORD = re.compile(r"[A-Za-z][A-Za-z'-]*")
#: Sentence-initial or otherwise capitalised words that are not names.
NOT_NAMES = {
    "the",
    "a",
    "an",
    "and",
    "but",
    "so",
    "then",
    "now",
    "here",
    "there",
    "this",
    "that",
    "these",
    "those",
    "it",
    "its",
    "you",
    "your",
    "we",
    "our",
    "they",
    "their",
    "he",
    "she",
    "his",
    "her",
    "if",
    "when",
    "where",
    "while",
    "look",
    "stand",
    "walk",
    "go",
    "come",
    "take",
    "notice",
    "think",
    "remember",
    "stop",
    "keep",
    "let",
    "do",
    "not",
    "no",
    "yes",
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
    "in",
    "on",
    "at",
    "by",
    "for",
    "from",
    "to",
    "of",
    "with",
    "into",
    "over",
    "under",
    "before",
    "after",
    "all",
    "most",
    "some",
    "every",
    "each",
    "what",
    "why",
    "how",
    "who",
    "which",
    "i",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "as",
    "or",
    "nor",
    "yet",
    "because",
    "once",
    "still",
    "just",
    "only",
    "even",
    "also",
    "very",
    "more",
    "less",
    "first",
    "last",
    "next",
    "today",
    "tonight",
    "tomorrow",
    "morning",
    "evening",
    "afternoon",
    "sunday",
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
    "day",
    "days",
    "welcome",
    "good",
    "well",
    "right",
    "left",
    "up",
    "down",
    "out",
    "back",
    "imagine",
    "picture",
    "listen",
    "hear",
    "see",
    "feel",
    "try",
    "ask",
    "say",
}


@dataclass
class Narration:
    text: str
    language: str
    grounded: bool  # passed the post-check on the attempt that produced it
    fell_back: bool  # the retrieved text lightly joined, no model prose
    attempts: int
    model: str | None = None
    cost_usd: float | None = None
    latency_ms: int = 0
    flagged: list[str] = field(default_factory=list)


Llm = Callable[..., Completion]


# --------------------------------------------------------------------------- #
# the post-check, pure
# --------------------------------------------------------------------------- #


def numbers(text: str) -> set[str]:
    """Every number in the text, Indic digits normalised, commas removed."""
    text = text.translate(INDIC_DIGITS)
    return {m.group().replace(",", "").rstrip(".") for m in NUMBER.finditer(text)}


def names(text: str) -> set[str]:
    """Capitalised words that are not sentence-initial filler, lowercased."""
    out: set[str] = set()
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        for position, word in enumerate(WORD.findall(sentence)):
            if not word[0].isupper():
                continue
            low = word.lower().rstrip("'s").replace("'", "")
            if low in NOT_NAMES or (position == 0 and len(low) < 4):
                continue
            out.add(low)
    return out


def check(
    output: str, source: str, language: str, allowed: tuple[str, ...] = ()
) -> list[str]:
    """What the output says that the source does not. Empty means grounded."""
    flagged: list[str] = []
    source_all = " ".join((source, *allowed))
    flagged += sorted(numbers(output) - numbers(source_all))
    low = output.lower()
    flagged += [b for b in BANNED if b in low]
    if language == "en":
        known = {w.lower().rstrip("'s") for w in WORD.findall(source_all)}
        # Wadiyar and Wadiyars are the same name; so are Hoysala and Hoysalas.
        flagged += sorted(
            n for n in names(output) if not ({n, n + "s", n.rstrip("s")} & known)
        )
    return flagged


def frame_legend(text: str, language: str) -> str:
    """Make sure a legend opens with its language's framing phrase."""
    framing = FRAMING[language]
    stripped = text.lstrip("\"'“‘ \n")
    if stripped.lower().startswith(framing.lower()):
        return stripped
    joiner = ", " if language == "en" else " "
    return f"{framing}{joiner}{stripped[0].lower() + stripped[1:] if language == 'en' else stripped}"


def fallback_text(bodies: list[str], is_legend: bool, language: str) -> str:
    """The retrieved text, lightly joined. Honest, and always in the corpus's words."""
    text = " ".join(b.strip() for b in bodies if b.strip())
    return frame_legend(text, language) if is_legend else text


# --------------------------------------------------------------------------- #
# prompts
# --------------------------------------------------------------------------- #


def _system(language: str, is_legend: bool, job: str) -> str:
    legend = (
        f'Open with the exact words "{FRAMING[language]}" because this is a legend, '
        "then tell it as a story people tell, not as fact."
        if is_legend
        else ""
    )
    return (
        "You are a warm, plain-spoken guide walking beside a traveller in "
        "Karnataka. You speak; you do not write. Short sentences. Second person. "
        "No marketing words. "
        f"{SCRIPT_NOTE[language]} "
        "Use ONLY the facts given below. Never add a date, number, name, place or "
        "claim that is not in them; if the facts are silent, stay silent. Never "
        "give a percentage, a score or a probability. "
        f"{legend} "
        f"Output the {job} only, with no heading, no preamble and no notes."
    )


def _narrate(
    system: str,
    user: str,
    *,
    source: str,
    language: str,
    allowed: tuple[str, ...],
    is_legend: bool,
    fallback: str,
    llm: Llm,
    model: str,
) -> Narration:
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    cost = 0.0
    latency = 0
    last: Completion | None = None
    flagged: list[str] = []
    for attempt, temperature in enumerate((0.5, 0.0), start=1):
        last = llm(messages, model=model, temperature=temperature)
        cost += last.cost_usd or 0.0
        latency += last.latency_ms
        text = frame_legend(last.text, language) if is_legend else last.text.strip()
        flagged = check(text, source, language, allowed)
        if last.finish_reason == "length":
            flagged.append("cut off mid-sentence")  # never speak half a thought
        if not flagged:
            return Narration(
                text=text,
                language=language,
                grounded=True,
                fell_back=False,
                attempts=attempt,
                model=last.model,
                cost_usd=cost,
                latency_ms=latency,
            )
    return Narration(
        text=fallback,
        language=language,
        grounded=True,  # the corpus's own words
        fell_back=True,
        attempts=2,
        model=last.model if last else None,
        cost_usd=cost,
        latency_ms=latency,
        flagged=flagged,
    )


def narrate_segment(
    segment: dict,
    language: str,
    *,
    place: str = "",
    allowed: tuple[str, ...] = (),
    llm: Llm = complete,
    model: str | None = None,
) -> Narration:
    """One Katha segment, spoken. `segment` is a Katha Segment as a dict."""
    bodies = [c["body"] for c in segment["body_source_chunks"]]
    is_legend = bool(segment.get("is_legend"))
    source = "\n\n".join(
        f"{c.get('title') or ''}\n{c['body']}" for c in segment["body_source_chunks"]
    )
    words = sum(len(b.split()) for b in bodies)
    user = (
        f"PLACE: {place or segment.get('spine_item', '')}\n"
        f"SEGMENT TYPE: {segment['chunk_type']}\n"
        f"TARGET LENGTH: about {words} words\n\n"
        f"FACTS:\n{source}"
    )
    return _narrate(
        _system(language, is_legend, "spoken segment"),
        user,
        source=source,
        language=language,
        allowed=(place, *allowed),
        is_legend=is_legend,
        fallback=fallback_text(bodies, is_legend, language),
        llm=llm,
        model=model or MODELS["narrate_katha"],
    )


def plan_as_text(plan: Plan, request: TripRequest) -> str:
    who = ", ".join(f"{t.kind} {t.age_band}" for t in request.travellers)
    lines = [
        (
            f"Trip: {request.days} days from {request.origin_city} to "
            f"{', '.join(request.destination_cities)}, party of {request.party_size}"
            f"{f' ({who})' if who else ''}, {request.pace} pace, comfort {plan.comfort}."
        )
    ]
    if request.trip_type:
        lines.append(f"Trip type: {request.trip_type}.")
    if request.food:
        lines.append(f"Food: {request.food} only.")
    if request.must_see:
        lines.append(f"Must see: {', '.join(request.must_see)}.")
    if request.skip:
        lines.append(f"Skip: {', '.join(request.skip)}.")
    if request.notes:
        lines.append(f"The traveller wrote: {request.notes}")
    for day in plan.days:
        lines.append(f"Day {day.index}, {day.date:%A %d %B}, {day.city}:")
        if day.getting_around:
            g = day.getting_around
            lines.append(
                f"  getting around by {g.mode.replace('_', ' ')}, about {g.est_cost_inr} "
                "rupees, estimated"
            )
        for item in day.items:
            if item.kind == "move":
                lines.append(
                    f"  travel {item.minutes} minutes by {item.mode} to {item.to_name}"
                )
            else:
                lines.append(
                    f"  {item.arrive:%H:%M} to {item.depart:%H:%M} {item.name}, "
                    f"{item.dwell_min} minutes, {item.cost_inr} rupees. {item.why}"
                )
        lines.append(f"  day ends {day.ends_at:%H:%M}")
    lines.append(f"Total entry fees {plan.total_spend} rupees.")
    return "\n".join(lines)


def narrate_plan(
    plan: Plan,
    request: TripRequest,
    language: str,
    *,
    llm: Llm = complete,
    model: str | None = None,
) -> Narration:
    """The whole plan as a companion would say it, day by day."""
    source = plan_as_text(plan, request)
    user = (
        "Tell the traveller their plan as a companion would, day by day, in the "
        "order given. Keep every time, place and rupee amount exactly as given. "
        "Say why each stop sits where it does using the reasons given. When what "
        "the traveller wrote bears on a day, say how the day answers it."
        f"\n\nPLAN:\n{source}"
    )
    return _narrate(
        _system(language, False, "companion narration"),
        user,
        source=source,
        language=language,
        allowed=tuple(request.destination_cities) + (request.origin_city,),
        is_legend=False,
        fallback=source,
        llm=llm,
        model=model or MODELS["narrate_plan"],
    )


def answer_question(
    question: str,
    hits: list,
    language: str,
    *,
    llm: Llm = complete,
    model: str | None = None,
) -> Narration:
    """A chat answer built only from retrieved paragraphs, checked the same way."""
    source = "\n\n".join(f"{h.title or ''}\n{h.body}" for h in hits)
    user = (
        f"QUESTION: {question}\n\nFACTS:\n{source}\n\n"
        "Answer in two to five short spoken sentences using only the facts. "
        "If the facts do not answer the question, say so plainly."
    )
    return _narrate(
        _system(language, False, "answer"),
        user,
        source=source,
        language=language,
        allowed=(),
        is_legend=False,
        fallback=hits[0].body,
        llm=llm,
        model=model or MODELS["narrate_katha"],
    )

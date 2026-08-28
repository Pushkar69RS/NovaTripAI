"""The shape of a city Katha: a fixed portrait, told the same way every time.

More minutes means more of the portrait, never more of one monument's inside.
Each theme sits at a tier, the shortest Katha length that includes it, so a
2-minute Katha is a subset of the 5-minute one, which is a subset of the 10.
"""

from __future__ import annotations

THEME_ORDER = (
    "identity",
    "origins",
    "rulers",
    "character",
    "food",
    "festivals",
    "worth_seeing",
    "practical",
)

#: Segment side label and title, by theme. "{city}" is filled in.
THEME_LABELS: dict[str, str] = {
    "identity": "What {city} is",
    "origins": "How it began",
    "rulers": "Who ruled here",
    "character": "The city today",
    "food": "What it eats",
    "festivals": "Festivals",
    "worth_seeing": "Worth your time",
    "practical": "Before you come",
}

#: What the lede says a Katha covers, by theme, in order.
THEME_LEDE: dict[str, str] = {
    "identity": "what it is",
    "rulers": "who made it",
    "food": "what it eats",
    "worth_seeing": "what is worth your time",
}

#: The full corpus shape per city: (theme, tier). Fourteen paragraphs.
CITY_SHAPE: tuple[tuple[str, int], ...] = (
    ("identity", 2),
    ("origins", 2),
    ("rulers", 2),
    ("rulers", 5),
    ("rulers", 10),
    ("character", 5),
    ("character", 10),
    ("food", 5),
    ("food", 10),
    ("festivals", 5),
    ("worth_seeing", 2),
    ("worth_seeing", 5),
    ("worth_seeing", 10),
    ("practical", 10),
)

#: What the cold-start drafter asks a model for: twelve of the fourteen.
DRAFT_SHAPE: tuple[tuple[str, int], ...] = tuple(
    s for s in CITY_SHAPE if s not in {("rulers", 10), ("worth_seeing", 10)}
)

#: The chunk_type a drafted paragraph is filed under, by theme.
THEME_CHUNK_TYPE: dict[str, str] = {
    "identity": "hook",
    "origins": "story",
    "rulers": "fact",
    "character": "sensory",
    "food": "taste",
    "festivals": "fact",
    "worth_seeing": "fact",
    "practical": "practical",
}


def theme_rank(theme: str | None) -> int:
    return THEME_ORDER.index(theme) if theme in THEME_ORDER else len(THEME_ORDER)


def label_for(theme: str, city: str) -> str:
    return THEME_LABELS.get(theme, theme).format(city=city)

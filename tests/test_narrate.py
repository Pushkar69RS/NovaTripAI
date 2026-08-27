"""The narrator's fact-check, retry and fallback, with a fake model."""

from __future__ import annotations

from app.llm.client import Completion
from app.llm.narrate import (
    FRAMING,
    check,
    fallback_text,
    frame_legend,
    narrate_segment,
    numbers,
)

SOURCE = (
    "The palace in front of you is the fourth one to stand on this ground. "
    "In 1897 it caught fire in the middle of a royal wedding. Henry Irwin "
    "designed the stone one. It took fifteen years."
)
SEGMENT = {
    "title": "Three palaces burned before this one",
    "chunk_type": "hook",
    "is_legend": False,
    "spine_item": "Mysore Palace",
    "body_source_chunks": [{"id": 1, "title": "Three palaces", "body": SOURCE}],
}


class Fake:
    """Returns scripted replies and records how it was called."""

    def __init__(self, *replies: str) -> None:
        self.replies = list(replies)
        self.calls: list[dict] = []

    def __call__(self, messages, *, model, temperature, **kw) -> Completion:
        self.calls.append({"model": model, "temperature": temperature})
        text = self.replies.pop(0) if self.replies else ""
        return Completion(text, model, 10, 10, 0.0001, 5)


def test_the_post_check_catches_an_invented_date() -> None:
    out = "The palace burned in 1897 and Irwin finished the new one in 1912."
    assert check(out, SOURCE, "en") == ["1912"]
    assert check("The palace burned in 1897.", SOURCE, "en") == []


def test_the_post_check_catches_names_and_percentages() -> None:
    assert "wadiyar" in check("Wadiyar rebuilt it after 1897.", SOURCE, "en")
    assert "%" in check("About 90% of it burned in 1897.", SOURCE, "en")
    assert check("Henry Irwin designed it.", SOURCE, "en") == []
    # the place name and the city are always allowed
    assert check("Mysuru loved it.", SOURCE, "en", allowed=("Mysuru",)) == []


def test_indic_digits_count_as_the_same_number() -> None:
    assert numbers("೧೮೯೭ರಲ್ಲಿ") == {"1897"}
    assert check("ಅರಮನೆ ೧೮೯೭ರಲ್ಲಿ ಸುಟ್ಟುಹೋಯಿತು.", SOURCE, "kn") == []
    assert check("ಅರಮನೆ ೧೯೧೨ರಲ್ಲಿ ಮುಗಿಯಿತು.", SOURCE, "kn") == ["1912"]


def test_grounded_output_passes_first_time() -> None:
    fake = Fake(
        "Look up. The palace in front of you burned in 1897. Henry Irwin built it in stone."
    )
    n = narrate_segment(SEGMENT, "en", place="Mysore Palace", llm=fake, model="m")
    assert n.grounded and not n.fell_back and n.attempts == 1
    assert fake.calls[0]["temperature"] == 0.5


def test_invented_facts_retry_at_zero_then_fall_back_to_the_retrieved_text() -> None:
    fake = Fake(
        "It burned in 1897 and was finished in 1912 by Henry Irwin.",  # 1912 invented
        "Krishnaraja Wadiyar rebuilt it after the fire of 1897.",  # name invented
    )
    n = narrate_segment(SEGMENT, "en", place="Mysore Palace", llm=fake, model="m")
    assert n.fell_back
    assert n.attempts == 2
    assert [c["temperature"] for c in fake.calls] == [0.5, 0.0]
    assert n.text == SOURCE  # the corpus's own words, lightly joined
    assert n.flagged  # what the last attempt got wrong is kept for the log


def test_legends_open_with_the_framing_in_every_language() -> None:
    legend = {**SEGMENT, "is_legend": True}
    fake = Fake("A queen cursed the kings at the river in 1897.")
    n = narrate_segment(legend, "en", llm=fake, model="m")
    assert n.text.startswith("The story goes, a queen")

    assert frame_legend("ರಾಣಿ ಶಾಪ ಹಾಕಿದಳು.", "kn").startswith(FRAMING["kn"])
    assert frame_legend("रानी ने श्राप दिया।", "hi").startswith(FRAMING["hi"])
    assert frame_legend("The story goes that she cursed them.", "en").startswith(
        "The story goes"
    )
    assert (
        fallback_text(["She cursed them."], True, "en")
        == "The story goes, she cursed them."
    )

"""Which OpenRouter model does which job. Swapping one is a one-line change.

classify        turns a chat message into a Question or an EditInstruction
narrate_plan    turns a validated Plan into companion prose
narrate_katha   turns retrieved paragraphs into a spoken Katha segment
draft_places    drafts the places and the Katha city layer of an unseeded city
parse_intake    reads the traveller's own words into the intake form

narrate_katha is the one that matters for Kannada. scripts/pick_model.py ran
the same Mysore Palace segment through three current models side by side and
Rohan picked Gemini 3.1 Flash Lite for both narration jobs on 2026-08-28. The
id was checked against the live OpenRouter /models list that day, and again on
2026-08-28 when draft_places and parse_intake were added. classify stays on the
model scripts/check_env.py verifies.
"""

MODELS: dict[str, str] = {
    "classify": "deepseek/deepseek-chat",
    "narrate_plan": "google/gemini-3.1-flash-lite",
    "narrate_katha": "google/gemini-3.1-flash-lite",
    "draft_places": "google/gemini-3.1-flash-lite",
    "parse_intake": "google/gemini-3.1-flash-lite",
}

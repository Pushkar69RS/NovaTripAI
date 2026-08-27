"""Which OpenRouter model does which job. Swapping one is a one-line change.

classify        turns a chat message into a Question or an EditInstruction
narrate_plan    turns a validated Plan into companion prose
narrate_katha   turns retrieved paragraphs into a spoken Katha segment

narrate_katha is the one that matters for Kannada. scripts/pick_model.py ran
the same Mysore Palace segment through three current models side by side and
Rohan picked Gemini 3.1 Flash Lite for both narration jobs on 2026-08-28. The
id was checked against the live OpenRouter /models list that day. classify
stays on the model scripts/check_env.py verifies.
"""

MODELS: dict[str, str] = {
    "classify": "deepseek/deepseek-chat",
    "narrate_plan": "google/gemini-3.1-flash-lite",
    "narrate_katha": "google/gemini-3.1-flash-lite",
}

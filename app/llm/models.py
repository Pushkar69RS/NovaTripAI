"""Which OpenRouter model does which job. Swapping one is a one-line change.

classify        turns a chat message into a Question or an EditInstruction
narrate_plan    turns a validated Plan into companion prose
narrate_katha   turns retrieved paragraphs into a spoken Katha segment

narrate_katha is the one that matters for Kannada. scripts/pick_model.py runs
the same Mysore Palace segment through three current models and prints them
side by side; Rohan reads the Kannada and picks. Until then it points at the
model scripts/check_env.py already verifies, so nothing here is unproven.
"""

MODELS: dict[str, str] = {
    "classify": "deepseek/deepseek-chat",
    "narrate_plan": "deepseek/deepseek-chat",
    "narrate_katha": "deepseek/deepseek-chat",  # pending the bake-off pick
}

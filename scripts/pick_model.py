"""The bake-off. One Mysore Palace segment, narrated in Kannada by three models.

    uv run python scripts/pick_model.py

Prints the three outputs one after another with cost, latency and whether each
passed the fact-check, then stops. It chooses nothing. Rohan reads the Kannada
and writes the pick into app/llm/models.py.

The candidates are checked against what OpenRouter lists right now, with the
price it lists, so nothing here rests on memory.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.llm.client import OPENROUTER, complete
from app.llm.narrate import narrate_segment

ROOT = Path(__file__).resolve().parent.parent

#: Current, cheap-to-mid, and known to handle Indic scripts. Verified against
#: the live /models list at run time; a candidate that is not listed is skipped
#: and said so.
CANDIDATES = [
    "google/gemini-3.1-flash-lite",
    "openai/gpt-4.1-mini",
    "deepseek/deepseek-v4-flash",
]
SEGMENT_TITLE = "Three palaces burned before this one"  # curated, Mysore Palace


def fixed_segment() -> dict:
    data = json.loads(
        (ROOT / "data" / "chunks_curated.json").read_text(encoding="utf-8")
    )
    chunk = next(c for c in data["chunks"] if c["title"] == SEGMENT_TITLE)
    return {
        "title": chunk["title"],
        "chunk_type": chunk["chunk_type"],
        "is_legend": bool(chunk["is_legend"]),
        "spine_item": "Mysore Palace",
        "body_source_chunks": [
            {"id": 0, "title": chunk["title"], "body": chunk["body"]}
        ],
    }


def listed_models() -> dict[str, dict]:
    key = os.environ["OPENROUTER_API_KEY"]
    with httpx.Client(base_url=OPENROUTER, timeout=30) as c:
        r = c.get("/models", headers={"Authorization": f"Bearer {key}"})
        r.raise_for_status()
    return {m["id"]: m for m in r.json()["data"]}


def main() -> int:
    load_dotenv(ROOT / ".env")
    models = listed_models()
    segment = fixed_segment()
    print(
        f"SEGMENT (English source, {len(segment['body_source_chunks'][0]['body'].split())} words):"
    )
    print(f"  {segment['title']}")
    print(f"  {segment['body_source_chunks'][0]['body']}")
    print()

    results = []
    for model_id in CANDIDATES:
        if model_id not in models:
            print(f"-- {model_id}: NOT LISTED on OpenRouter today, skipped\n")
            continue
        pricing = models[model_id].get("pricing", {})
        price = (
            f"${float(pricing.get('prompt', 0)) * 1e6:.3f}/M in, "
            f"${float(pricing.get('completion', 0)) * 1e6:.3f}/M out"
        )
        try:
            narration = narrate_segment(
                segment, "kn", place="Mysore Palace", llm=complete, model=model_id
            )
        except httpx.HTTPError as exc:
            print(f"-- {model_id}: request failed ({type(exc).__name__}: {exc})\n")
            continue
        results.append((model_id, price, narration))

    print("=" * 78)
    print(
        f"{'model':<32}{'cost $':>10}{'ms':>8}{'tries':>7}{'grounded':>10}{'fallback':>10}"
    )
    print("-" * 78)
    for model_id, _price, n in results:
        cost = f"{n.cost_usd:.5f}" if n.cost_usd is not None else "n/a"
        print(
            f"{model_id:<32}{cost:>10}{n.latency_ms:>8}{n.attempts:>7}"
            f"{'yes' if n.grounded and not n.fell_back else 'no':>10}"
            f"{'yes' if n.fell_back else 'no':>10}"
        )
    print("=" * 78)
    for model_id, price, n in results:
        print()
        print(f"### {model_id}   ({price})")
        if n.flagged:
            print(f"    flagged by the fact-check: {n.flagged}")
        print()
        print(n.text)
    print()
    print("No model chosen. Read the Kannada, pick one, and set narrate_katha in")
    print("app/llm/models.py.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

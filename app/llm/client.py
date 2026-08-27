"""One call to OpenRouter. No framework, no retries hidden in here.

Every completion comes back with what it cost and how long it took, because
the bake-off prints both and the API should be able to say what it spent.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from time import perf_counter
from typing import Any

import httpx

OPENROUTER = "https://openrouter.ai/api/v1"
TIMEOUT = 90.0


@dataclass
class Completion:
    text: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float | None
    latency_ms: int
    finish_reason: str | None = None


def complete(
    messages: list[dict[str, str]],
    *,
    model: str,
    temperature: float = 0.4,
    max_tokens: int = 2000,  # Kannada and Hindi spend three to four tokens a word
    json_mode: bool = False,
) -> Completion:
    """POST /chat/completions and return the first choice."""
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY is not set")
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "usage": {"include": True},  # OpenRouter then reports usage.cost
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    headers = {
        "Authorization": f"Bearer {key}",
        "HTTP-Referer": "https://github.com/rohanbalu05/travel-yantra",
        "X-Title": "travel-yantra",
    }
    started = perf_counter()
    with httpx.Client(base_url=OPENROUTER, headers=headers, timeout=TIMEOUT) as c:
        r = c.post("/chat/completions", json=payload)
        r.raise_for_status()
        body = r.json()
    usage = body.get("usage") or {}
    cost = usage.get("cost")
    choice = body["choices"][0]
    return Completion(
        text=(choice["message"]["content"] or "").strip(),
        model=body.get("model", model),
        prompt_tokens=int(usage.get("prompt_tokens") or 0),
        completion_tokens=int(usage.get("completion_tokens") or 0),
        cost_usd=float(cost) if cost is not None else None,
        latency_ms=int((perf_counter() - started) * 1000),
        finish_reason=choice.get("finish_reason"),
    )

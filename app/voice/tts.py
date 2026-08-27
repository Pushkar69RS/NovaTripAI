"""Kannada, Hindi and English speech through Sarvam's bulbul model.

Shape checked against docs.sarvam.ai on 2026-08-28:
    POST https://api.sarvam.ai/text-to-speech
    header  api-subscription-key
    body    text (<= 2500 chars on bulbul:v3), language_code (kn-IN, hi-IN,
            en-IN), speaker (lowercase), model, pace, speech_sample_rate,
            output_audio_codec
    reply   {"request_id": ..., "audios": ["<base64 wav>", ...]}

speak() never raises. Anything that goes wrong returns None and the frontend
falls back to the browser's own speech synthesis. Every successful result is
cached on disk by the hash of (text, language, voice), so the review demo
plays from the cache and does not need the network.
"""

from __future__ import annotations

import base64
import hashlib
import io
import os
import re
import wave
from pathlib import Path

import httpx

SARVAM_TTS = "https://api.sarvam.ai/text-to-speech"
MODEL = "bulbul:v3"
VOICE = "roopa"  # one v3 speaker for every language, so the cache key is stable
LANGUAGE = {"en": "en-IN", "kn": "kn-IN", "hi": "hi-IN"}
SAMPLE_RATE = 22050
PIECE_CHARS = 2000  # under the 2500-char cap, with room for a long sentence
TIMEOUT = 60.0

CACHE_DIR = Path(__file__).resolve().parents[2] / "var" / "tts"


def cache_path(text: str, language: str, voice: str = VOICE) -> Path:
    digest = hashlib.sha256(f"{voice}\x1f{language}\x1f{text}".encode()).hexdigest()
    return CACHE_DIR / f"{digest}.wav"


def pieces(text: str, limit: int = PIECE_CHARS) -> list[str]:
    """Split on sentence ends so no request exceeds the character cap."""
    out: list[str] = []
    current = ""
    for sentence in re.split(r"(?<=[.!?।])\s+", text.strip()):
        if not sentence:
            continue
        if current and len(current) + 1 + len(sentence) > limit:
            out.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current:
        out.append(current)
    # a single sentence longer than the cap is cut on a space, not dropped
    final: list[str] = []
    for piece in out:
        while len(piece) > limit:
            cut = piece.rfind(" ", 0, limit)
            if cut <= 0:  # rfind says -1 for "no space", which is truthy
                cut = limit
            final.append(piece[:cut])
            piece = piece[cut:].lstrip()
        final.append(piece)
    return final


def join_wavs(parts: list[bytes]) -> bytes:
    """Concatenate WAV files that share their parameters."""
    if len(parts) == 1:
        return parts[0]
    frames = []
    params = None
    for part in parts:
        with wave.open(io.BytesIO(part), "rb") as w:
            if params is None:
                params = w.getparams()
            frames.append(w.readframes(w.getnframes()))
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as w:
        w.setparams(params)
        for chunk in frames:
            w.writeframes(chunk)
    return buffer.getvalue()


def _synthesise(text: str, language_code: str, voice: str, key: str) -> bytes:
    with httpx.Client(timeout=TIMEOUT) as client:
        r = client.post(
            SARVAM_TTS,
            headers={"api-subscription-key": key},
            json={
                "text": text,
                "language_code": language_code,
                "speaker": voice,
                "model": MODEL,
                "pace": 1.0,
                "speech_sample_rate": SAMPLE_RATE,
                "output_audio_codec": "wav",
            },
        )
        r.raise_for_status()
        audios = r.json()["audios"]
    return base64.b64decode("".join(audios))


def speak(text: str, language: str, *, voice: str = VOICE) -> bytes | None:
    """WAV bytes for the text, or None when it cannot be had right now."""
    try:
        if not text.strip() or language not in LANGUAGE:
            return None
        path = cache_path(text, language, voice)
        if path.exists():
            return path.read_bytes()
        key = os.environ.get("SARVAM_API_KEY", "").strip()
        if not key:
            return None
        parts = [
            _synthesise(piece, LANGUAGE[language], voice, key) for piece in pieces(text)
        ]
        audio = join_wavs(parts)
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path.write_bytes(audio)
        return audio
    except Exception:  # noqa: BLE001 - failing soft is the contract
        return None

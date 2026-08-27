"""speak() never raises and never needs the network twice for the same text."""

from __future__ import annotations

import io
import wave

import httpx
import pytest

from app.voice import tts


def tiny_wav(frames: int) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(22050)
        w.writeframes(b"\x00\x01" * frames)
    return buffer.getvalue()


@pytest.fixture
def cache(tmp_path, monkeypatch):
    monkeypatch.setattr(tts, "CACHE_DIR", tmp_path)
    monkeypatch.setenv("SARVAM_API_KEY", "test-key")
    return tmp_path


def test_tts_failure_returns_none_without_raising(cache, monkeypatch) -> None:
    def explode(self, *args, **kwargs):
        raise httpx.ConnectError("no network")

    monkeypatch.setattr(httpx.Client, "post", explode)
    assert tts.speak("ನಮಸ್ಕಾರ", "kn") is None
    assert tts.speak("hello", "en") is None
    assert not list(cache.iterdir())  # nothing half-written


def test_a_bad_status_or_bad_body_also_returns_none(cache, monkeypatch) -> None:
    class Bad:
        status_code = 500
        text = "boom"

        def raise_for_status(self):
            raise httpx.HTTPStatusError("boom", request=None, response=None)

    monkeypatch.setattr(httpx.Client, "post", lambda self, *a, **k: Bad())
    assert tts.speak("hello", "en") is None


def test_no_key_and_unknown_language_return_none(cache, monkeypatch) -> None:
    monkeypatch.delenv("SARVAM_API_KEY")
    assert tts.speak("hello", "en") is None
    monkeypatch.setenv("SARVAM_API_KEY", "k")
    assert tts.speak("hello", "fr") is None
    assert tts.speak("   ", "en") is None


def test_a_cached_result_is_served_without_the_network(cache, monkeypatch) -> None:
    audio = tiny_wav(100)
    path = tts.cache_path("Look up.", "en")
    path.write_bytes(audio)

    def explode(self, *args, **kwargs):
        raise AssertionError("the network must not be touched for a cached text")

    monkeypatch.setattr(httpx.Client, "post", explode)
    assert tts.speak("Look up.", "en") == audio
    assert tts.cache_path("Look up.", "kn") != path  # language is in the key


def test_pieces_stay_under_the_cap_and_lose_nothing() -> None:
    text = " ".join(f"Sentence number {i} ends here." for i in range(300))
    parts = tts.pieces(text, limit=500)
    assert all(len(p) <= 500 for p in parts)
    assert " ".join(parts).split() == text.split()
    assert tts.pieces("x" * 1200, limit=500) == ["x" * 500, "x" * 500, "x" * 200]


def test_join_wavs_adds_up_the_frames() -> None:
    joined = tts.join_wavs([tiny_wav(100), tiny_wav(50)])
    with wave.open(io.BytesIO(joined), "rb") as w:
        assert w.getnframes() == 150
        assert w.getframerate() == 22050

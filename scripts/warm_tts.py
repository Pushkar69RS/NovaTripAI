"""Pre-generate the two demo Kathas so the review never touches the network.

    uv run python scripts/warm_tts.py

Builds the 5-minute Mysuru Katha once, narrates it in English and in Kannada,
sends each narration to Sarvam, and leaves the audio in var/tts/ under its
content hash, where app.voice.tts.speak() will find it again. Alongside each
WAV it writes var/tts/demo_<lang>.json with the segments, the narration text
and the audio path, so a demo page can play the whole thing from disk.
"""

from __future__ import annotations

import json
import os
import sys
import wave
from pathlib import Path

import psycopg
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.katha.build import DbCatalogue, build, db_retriever
from app.katha.models import Scope
from app.llm.narrate import narrate_segment
from app.voice.tts import CACHE_DIR, cache_path, speak

ROOT = Path(__file__).resolve().parent.parent
LANGUAGES = ("en", "kn")


def seconds(wav: bytes) -> float:
    import io

    with wave.open(io.BytesIO(wav), "rb") as w:
        return w.getnframes() / float(w.getframerate())


def main() -> int:
    load_dotenv(ROOT / ".env")
    with psycopg.connect(os.environ["SUPABASE_DB_URL"]) as conn:
        katha = build(
            Scope(kind="city", id="Mysuru"),
            5,
            "quick",
            "en",
            catalogue=DbCatalogue(conn),
            retriever=db_retriever(conn),
        )
    print(f"katha: {katha.total_words} words, types {' -> '.join(katha.type_sequence)}")

    ok = True
    for language in LANGUAGES:
        narrations = []
        for segment in katha.segments:
            n = narrate_segment(
                segment.model_dump(),
                language,
                place="Mysuru" if segment.theme else segment.spine_item,
            )
            narrations.append(n)
            flag = "fallback" if n.fell_back else f"ok x{n.attempts}"
            print(
                f"  [{language}] {segment.chunk_type:9s} {flag:10s} {segment.title[:48]}"
            )
        text = "\n\n".join(n.text for n in narrations)
        audio = speak(text, language)
        path = cache_path(text, language)
        record = {
            "language": language,
            "katha": katha.model_dump(mode="json"),
            "narrations": [n.text for n in narrations],
            "audio": str(path) if audio else None,
        }
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        (CACHE_DIR / f"demo_{language}.json").write_text(
            json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        if audio is None:
            ok = False
            print(
                f"  [{language}] Sarvam returned nothing; the frontend will use browser speech"
            )
        else:
            print(
                f"  [{language}] audio {len(audio) / 1024:.0f} KB, "
                f"{seconds(audio):.0f} s -> {path}"
            )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

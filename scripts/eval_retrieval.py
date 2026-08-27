"""Measure dense, lexical and hybrid retrieval against thirty hand-written questions.

    uv run python scripts/eval_retrieval.py

Questions name their expected chunks by title rather than by id, because ids are
assigned by the database and would go stale the moment anything is reseeded.
Titles are unique across the corpus and are checked before the run starts.

The three methods are compared on raw retrieval, with the refusal gate off, so
the numbers say something about retrieval rather than about the threshold. The
refusal gate is then checked separately on questions the corpus cannot answer.

Read-only apart from one row written to eval_run.
"""

from __future__ import annotations

import json
import os
import statistics
import sys
from pathlib import Path
from time import perf_counter

import psycopg
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.rag.retrieve import Filters, dense, lexical, rank, search

ROOT = Path(__file__).resolve().parent.parent
AT = 5

# (language, question, titles that answer it)
QUESTIONS: list[tuple[str, str, list[str]]] = [
    (
        "en",
        "Who designed the Mysore Palace after the fire?",
        [
            "What kind of building is this, exactly",
            "Three palaces burned before this one",
        ],
    ),
    (
        "en",
        "What time does the Mysore Palace illumination start on Sunday?",
        ["Fees, shoes, and the light switch"],
    ),
    (
        "en",
        "Why is the Nandi statue on Chamundi hill black and shiny?",
        ["The oil, and why the stone is black"],
    ),
    (
        "en",
        "Who invented Mysore pak and where is it sold now?",
        ["The sweet invented in this kitchen"],
    ),
    (
        "en",
        "What was the curse Alamelamma laid on the Mysore kings?",
        ["The queen who went into the river"],
    ),
    (
        "en",
        "Where is Tipu Sultan's mechanical tiger kept today?",
        ["The tiger that eats a soldier"],
    ),
    (
        "en",
        "How did Tipu Sultan die at Srirangapatna?",
        [
            "An island with a short temper",
            "Why the river did not save the fort",
        ],
    ),
    (
        "en",
        "Who founded the Vijayanagara empire and in what year?",
        ["Two brothers and a river"],
    ),
    (
        "en",
        "What happened to Hampi after the battle of Talikota?",
        ["Six months of burning"],
    ),
    (
        "en",
        "Which temple at Hampi has pillars that make musical notes?",
        ["The pillars that play"],
    ),
    (
        "en",
        "Which temple in Hampi is still used for worship?",
        ["The temple that never stopped"],
    ),
    (
        "en",
        "What did the Portuguese traveller Domingo Paes say about the city?",
        [
            "Gems on the ground like grain",
        ],
    ),
    (
        "en",
        "Which hill near Hampi is said to be the birthplace of Hanuman?",
        ["The monkey kingdom across the river"],
    ),
    ("en", "Why is the Hoysala dynasty called Hoysala?", ["Strike, Sala"]),
    (
        "en",
        "Who was the model for the lady with the mirror at Belur?",
        ["Find the lady with the mirror"],
    ),
    (
        "en",
        "What kind of stone lets Hoysala carvers cut such fine detail?",
        ["Soft stone, hard stone"],
    ),
    (
        "en",
        "Why does the Halebidu temple have no tower?",
        ["The city they renamed Old Ruins"],
    ),
    ("en", "How did Bangalore get its name?", ["The town of boiled beans"]),
    (
        "en",
        "Who laid out the old town of Bangalore and when?",
        ["Kempegowda laid out four roads and a mud fort"],
    ),
    (
        "en",
        "How did coffee first reach India?",
        ["Seven beans in a robe"],
    ),
    (
        "en",
        "Where does the river Kaveri rise?",
        ["Where the Kaveri begins", "Climb the steps behind the tank"],
    ),
    # Kannada
    (
        "kn",
        "ಮೈಸೂರು ಅರಮನೆಯನ್ನು ಯಾರು ಕಟ್ಟಿಸಿದರು?",
        [
            "What kind of building is this, exactly",
            "Three palaces burned before this one",
        ],
    ),
    (
        "kn",
        "ಚಾಮುಂಡಿ ಬೆಟ್ಟದ ನಂದಿ ವಿಗ್ರಹ ಯಾವಾಗ ಕೆತ್ತಲಾಯಿತು?",
        ["A bull carved from one stone", "The oil, and why the stone is black"],
    ),
    (
        "kn",
        "ಮೈಸೂರು ಪಾಕ್ ಯಾರು ಕಂಡುಹಿಡಿದರು?",
        ["The sweet invented in this kitchen"],
    ),
    (
        "kn",
        "ಹಂಪಿಯ ಕಲ್ಲಿನ ರಥ ಎಲ್ಲಿದೆ?",
        ["The chariot on the fifty rupee note"],
    ),
    (
        "kn",
        "ಬಾಬಾ ಬುಡನ್ ಕಾಫಿ ಬೀಜಗಳನ್ನು ಹೇಗೆ ತಂದರು?",
        ["Seven beans in a robe"],
    ),
    (
        "kn",
        "ಕಾವೇರಿ ನದಿ ಎಲ್ಲಿ ಹುಟ್ಟುತ್ತದೆ?",
        ["Where the Kaveri begins", "Climb the steps behind the tank"],
    ),
    # Hinglish
    (
        "hi",
        "Hampi mein stone chariot kahan par hai?",
        ["The chariot on the fifty rupee note"],
    ),
    (
        "hi",
        "Mysore palace ke andar camera le ja sakte hain kya?",
        ["Fees, shoes, and the light switch"],
    ),
    (
        "hi",
        "Coorg mein pandi curry kaise banate hain?",
        ["Pandi curry and the sour secret"],
    ),
]


# The thirty above are all well-formed questions, which is the half of the query
# distribution dense retrieval is best at. People also type names and fragments
# into a search box, which is the half lexical is best at. This second block is
# reported separately rather than mixed in, so neither table is quietly shaped by
# the other. Nothing was removed from the thirty to make room for it.
KEYWORD_QUERIES: list[tuple[str, str, list[str]]] = [
    (
        "kw",
        "Talikota 1565",
        ["Six months of burning"],
    ),
    (
        "kw",
        "Kadalekai Parishe",
        [
            "The groundnut fair, on the last Monday of Karthika",
            "The bull and the groundnuts",
        ],
    ),
    ("kw", "Darpana Sundari", ["Find the lady with the mirror"]),
    ("kw", "Rashk-e-Jannat", ["Two storeys of teak in the middle of a market"]),
    ("kw", "kachampuli", ["Pandi curry and the sour secret"]),
    ("kw", "Gandaberunda", ["The double-headed bird over the gate"]),
    ("kw", "Dasoja Chavana Balligavi", ["The men who signed the stone"]),
    (
        "kw",
        "Brahmakundike Tula Sankramana",
        ["Where the Kaveri begins", "Climb the steps behind the tank"],
    ),
    (
        "kw",
        "Kakasura Madappa",
        ["The sweet invented in this kitchen"],
    ),
    ("kw", "chloritic schist soapstone", ["Soft stone, hard stone"]),
]

# Questions the corpus cannot answer. The refusal gate has to return nothing.
NONSENSE: list[str] = [
    "quarterly earnings of a Norwegian shipping company",
    "how to reset a Cisco router password",
    "best ski resorts in Hokkaido in February",
    "asdkjfh qwerty zxcvbnm blorp",
    "the offside rule in association football",
    "kubernetes ingress controller tls termination",
]


def rank_of(expected: set[int], ordered: list[int]) -> int | None:
    for position, chunk_id in enumerate(ordered, start=1):
        if chunk_id in expected:
            return position
    return None


def run_method(db, name: str, query: str) -> tuple[list[int], float]:
    started = perf_counter()
    if name == "dense":
        ordered = [r["id"] for r in dense(db, query, Filters())]
    elif name == "lexical":
        ordered = [r["id"] for r in lexical(db, query, Filters())]
    else:
        found = {
            "dense": dense(db, query, Filters()),
            "lexical": lexical(db, query, Filters()),
        }
        scores, _ = rank(found)
        ordered = sorted(scores, key=lambda i: (-scores[i], i))
    return ordered, (perf_counter() - started) * 1000


def measure(
    db, titles: dict[str, int], questions: list, methods: list[str]
) -> tuple[dict[str, dict], dict[str, dict[str, list[float]]]]:
    """Recall@5, MRR and latency for each method over one question set."""
    results: dict[str, dict] = {}
    per_lang: dict[str, dict[str, list[float]]] = {}
    for method in methods:
        hits, rr, ms = [], [], []
        for lang, query, expect in questions:
            want = {titles[t] for t in expect}
            ordered, elapsed = run_method(db, method, query)
            position = rank_of(want, ordered)
            hits.append(1.0 if position is not None and position <= AT else 0.0)
            rr.append(1.0 / position if position else 0.0)
            ms.append(elapsed)
            per_lang.setdefault(lang, {}).setdefault(method, []).append(hits[-1])
        results[method] = {
            "recall_at_5": round(statistics.fmean(hits), 3),
            "mrr": round(statistics.fmean(rr), 3),
            "p50_ms": round(statistics.median(ms), 1),
            "p95_ms": round(sorted(ms)[max(0, int(len(ms) * 0.95) - 1)], 1),
        }
    return results, per_lang


def table(title: str, results: dict[str, dict], methods: list[str]) -> None:
    label = {"dense": "dense only", "lexical": "lexical only", "hybrid": "hybrid + RRF"}
    print()
    print(title)
    print(bar())
    print(f"{'method':<16}{'Recall@5':>10}{'MRR':>9}{'p50 ms':>13}{'p95 ms':>14}")
    print(bar())
    for method in methods:
        r = results[method]
        print(
            f"{label[method]:<16}{r['recall_at_5']:>10.3f}{r['mrr']:>9.3f}"
            f"{r['p50_ms']:>13.1f}{r['p95_ms']:>14.1f}"
        )
    print(bar())


def bar(width: int = 62) -> str:
    return "-" * width


def main() -> int:
    load_dotenv(ROOT / ".env")
    methods = ["dense", "lexical", "hybrid"]

    with psycopg.connect(os.environ["SUPABASE_DB_URL"]) as conn:
        titles = {
            title: chunk_id
            for chunk_id, title in conn.execute("SELECT id, title FROM doc_chunk")
        }
        unknown = {t for _, _, expect in QUESTIONS for t in expect if t not in titles}
        if unknown:
            print("questions expect chunks that are not in the corpus:")
            for t in sorted(unknown):
                print(f"  {t!r}")
            return 1

        results, per_lang = measure(conn, titles, QUESTIONS, methods)
        keyword, _ = measure(conn, titles, KEYWORD_QUERIES, methods)

        print()
        print(f"RETRIEVAL EVAL   {len(titles)} chunks, top {AT}")
        table(
            f"A. {len(QUESTIONS)} written questions "
            f"(21 English, 6 Kannada, 3 Hinglish)",
            results,
            methods,
        )
        table(
            f"B. {len(KEYWORD_QUERIES)} name and keyword lookups "
            f"(what people type into a box)",
            keyword,
            methods,
        )

        print()
        print(f"{'Recall@5 by language':<16}{'dense':>10}{'lexical':>9}{'hybrid':>13}")
        print(bar())
        names = {"en": "English (21)", "kn": "Kannada (6)", "hi": "Hinglish (3)"}
        for lang in ("en", "kn", "hi"):
            row = per_lang[lang]
            print(
                f"{names[lang]:<16}{statistics.fmean(row['dense']):>10.3f}"
                f"{statistics.fmean(row['lexical']):>9.3f}"
                f"{statistics.fmean(row['hybrid']):>13.3f}"
            )
        print(bar())

        refused = 0
        for query in NONSENSE:
            if not search(query, conn):
                refused += 1
        print()
        print(
            f"refusal gate: {refused}/{len(NONSENSE)} unanswerable queries returned nothing"
        )

        for name, block in (("A", results), ("B", keyword)):
            best_single = max(
                block["dense"]["recall_at_5"], block["lexical"]["recall_at_5"]
            )
            beats = block["hybrid"]["recall_at_5"] > best_single
            print(
                f"{name}: hybrid {'beats' if beats else 'does NOT beat'} "
                f"both single methods on Recall@5 "
                f"({block['hybrid']['recall_at_5']:.3f} vs {best_single:.3f})"
            )

        metrics = {
            "kind": "retrieval",
            "questions": len(QUESTIONS),
            "keyword_queries": len(KEYWORD_QUERIES),
            "chunks": len(titles),
            "at": AT,
            "methods": results,
            "keyword_methods": keyword,
            "refused": f"{refused}/{len(NONSENSE)}",
            "recall_at_5_by_lang": {
                lang: {m: round(statistics.fmean(v), 3) for m, v in row.items()}
                for lang, row in per_lang.items()
            },
        }
        conn.execute(
            "INSERT INTO eval_run (metrics) VALUES (%s)", (json.dumps(metrics),)
        )
        (run_id,) = conn.execute("SELECT max(id) FROM eval_run").fetchone()
        print(f"written to eval_run id={run_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

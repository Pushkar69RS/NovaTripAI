"""Embedding and retrieval.

The pure tests run anywhere. The ones that need real rows are skipped when
SUPABASE_DB_URL is not set, so the suite still runs without a database.
"""

from __future__ import annotations

import os

# Tests must not reach the network. The model is in the local cache.
os.environ.setdefault("HF_HUB_OFFLINE", "1")

import numpy as np
import pytest
from dotenv import load_dotenv

from app.rag import embed
from app.rag.retrieve import (
    MIN_SIMILARITY,
    Filters,
    TripContext,
    fuse,
    rank,
    search,
)

load_dotenv()

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


@pytest.fixture(scope="module")
def db():
    url = os.environ.get("SUPABASE_DB_URL")
    if not url:
        pytest.skip("SUPABASE_DB_URL is not set")
    import psycopg

    with psycopg.connect(url) as conn:
        (rows,) = conn.execute(
            "SELECT count(*) FROM doc_chunk WHERE embedding IS NOT NULL"
        ).fetchone()
        if not rows:
            pytest.skip("doc_chunk is not seeded")
        yield conn


class Recorder:
    """Stands in for the sentence-transformers model and keeps what it was given."""

    def __init__(self) -> None:
        self.seen: list[str] = []

    def encode(self, texts, **kwargs):
        self.seen.extend(texts)
        return np.ones((len(texts), embed.DIM), dtype=np.float32)


# --------------------------------------------------------------------------- #
# embedding
# --------------------------------------------------------------------------- #


def test_e5_prefixes_are_actually_applied(monkeypatch) -> None:
    recorder = Recorder()
    monkeypatch.setattr(embed, "model", lambda: recorder)

    embed.embed_passages(["Mysore Palace burned in 1897."])
    embed.embed_query("when did the palace burn")

    assert recorder.seen[0].startswith("passage: ")
    assert recorder.seen[1].startswith("query: ")
    assert "Mysore Palace burned" in recorder.seen[0]
    assert "when did the palace burn" in recorder.seen[1]


def test_chunk_text_carries_the_title_and_the_names() -> None:
    text = embed.chunk_text("The oil", "The stone is black.", ("Nandi Statue", "ನಂದಿ"))
    assert text.startswith("The oil. The stone is black.")
    assert "Nandi Statue" in text and "ನಂದಿ" in text
    # blanks and repeats are dropped rather than padding the vector
    assert embed.chunk_text("T", "B", ("x", "", "x")) == "T. B x"


def test_embeddings_are_384_dimensional_and_normalised() -> None:
    vectors = embed.embed_passages(["Hampi was sacked in 1565.", "ಹಂಪಿ"])
    assert vectors.shape == (2, embed.DIM) == (2, 384)
    for vector in vectors:
        assert float(np.linalg.norm(vector)) == pytest.approx(1.0, abs=1e-4)

    query = embed.embed_query("what happened at Talikota")
    assert query.shape == (384,)
    assert float(np.linalg.norm(query)) == pytest.approx(1.0, abs=1e-4)


# --------------------------------------------------------------------------- #
# fusion
# --------------------------------------------------------------------------- #


def test_rrf_puts_a_doc_both_retrievers_found_above_a_single_retriever_doc() -> None:
    # 1 is second on both lists, 2 is first on dense only, 3 is first on lexical only.
    found = {
        "dense": [{"id": 2, "strict": True}, {"id": 1, "strict": True}],
        "lexical": [{"id": 3, "strict": True}, {"id": 1, "strict": True}],
    }
    scores, ranks = fuse(found)
    assert scores[1] > scores[2]
    assert scores[1] > scores[3]
    assert sorted(ranks[1]) == ["dense", "lexical"]
    assert sorted(ranks[2]) == ["dense"]


def test_the_loose_lexical_fallback_does_not_get_a_vote() -> None:
    found = {
        "dense": [{"id": 1}, {"id": 2}],
        "lexical": [{"id": 9, "strict": False}, {"id": 8, "strict": False}],
    }
    scores, _ = rank(found)
    assert set(scores) == {1, 2}, "a fallback match is not a second opinion"

    found["lexical"] = [{"id": 9, "strict": True}]
    scores, _ = rank(found)
    assert 9 in scores


# --------------------------------------------------------------------------- #
# retrieval against the seeded corpus
# --------------------------------------------------------------------------- #


def test_a_kannada_query_retrieves_the_right_english_chunk(db) -> None:
    hits = search("ಮೈಸೂರು ಅರಮನೆಯನ್ನು ಯಾರು ಕಟ್ಟಿಸಿದರು?", db, k=5)
    assert hits, "a real Kannada question must not be refused"
    titles = [h.title for h in hits]
    assert {
        "What kind of building is this, exactly",
        "Three palaces burned before this one",
    } & set(titles)
    assert all(h.city == "Mysuru" for h in hits[:3])
    assert hits[0].body.isascii(), "the corpus is English, the query was not"


def test_the_refusal_path_triggers_on_nonsense(db) -> None:
    assert search("kubernetes ingress controller tls termination", db) == []
    assert search("asdkjfh qwerty zxcvbnm blorp", db) == []
    # and does not fire on a question the corpus can answer
    assert search("who invented Mysore pak", db)


def test_filters_actually_filter(db) -> None:
    hampi = search("temple", db, filters=Filters(city="Hampi"), k=8)
    assert hampi and all(h.city == "Hampi" for h in hampi)

    stories = search(
        "temple", db, filters=Filters(city="Hampi", chunk_type="story"), k=8
    )
    assert stories and all(h.chunk_type == "story" for h in stories)

    dropped = hampi[0].id
    again = search("temple", db, filters=Filters(city="Hampi", exclude_ids=[dropped]))
    assert dropped not in {h.id for h in again}


def test_hits_say_which_retriever_found_them(db) -> None:
    hits = search("what happened at the battle of Talikota", db, k=8)
    assert hits
    for hit in hits:
        assert hit.retrievers, "the UI shows where a paragraph came from"
        assert set(hit.retrievers) <= {"dense", "lexical"}
        assert (hit.dense_rank is not None) == ("dense" in hit.retrievers)
        # a row both retrievers found must not lose the cosine on the way out
        assert (hit.similarity is not None) == ("dense" in hit.retrievers)
    assert any(h.similarity and h.similarity >= MIN_SIMILARITY for h in hits)


def test_trip_context_lifts_the_stop_you_are_standing_at(db) -> None:
    (poi_id,) = db.execute(
        "SELECT id FROM poi WHERE name = 'Chamundeshwari Temple'"
    ).fetchone()
    plain = search("what should I know before I go", db, k=5)
    aware = search(
        "what should I know before I go",
        db,
        k=5,
        trip_context=TripContext(current_poi=poi_id, has_elderly=True),
    )
    assert aware, "context must not make the search refuse"
    assert aware[0].poi_id == poi_id
    assert aware[0].id != plain[0].id or plain[0].poi_id == poi_id

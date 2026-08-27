"""Local embeddings for the Katha corpus.

The e5 family is trained with prefixes and it is not optional. A document has to
be encoded as "passage: ..." and a query as "query: ...". Get it wrong and
nothing breaks loudly, retrieval just gets worse, so the prefixes live here and
are applied in one place.

The model is loaded once per process, on first use rather than on import, so
that importing the retrieval layer does not drag torch into a process that only
wants the SQL.
"""

from __future__ import annotations

from collections.abc import Sequence
from functools import lru_cache
from typing import Any

import numpy as np

MODEL_NAME = "intfloat/multilingual-e5-small"
DIM = 384
BATCH = 32
PASSAGE_PREFIX = "passage: "
QUERY_PREFIX = "query: "


@lru_cache(maxsize=1)
def model() -> Any:
    """The sentence-transformers model, loaded once and kept."""
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(MODEL_NAME)


def _encode(texts: Sequence[str], prefix: str) -> np.ndarray:
    vectors = model().encode(
        [prefix + t for t in texts],
        batch_size=BATCH,
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    return np.asarray(vectors, dtype=np.float32)


def embed_passages(texts: Sequence[str]) -> np.ndarray:
    """(n, 384) unit vectors for corpus text."""
    return _encode(list(texts), PASSAGE_PREFIX)


def embed_query(text: str) -> np.ndarray:
    """A single (384,) unit vector for a search query."""
    return _encode([text], QUERY_PREFIX)[0]


#: Kannada names for the hub cities. A Kannada query has to find an English
#: paragraph, and e5-small only manages that reliably when the passage carries
#: the place name in both scripts. Every chunk has a city, only a third of the
#: POIs have a Kannada name, so the city map is what makes the coverage general.
CITY_KN = {
    "Mysuru": "ಮೈಸೂರು",
    "Hampi": "ಹಂಪಿ",
    "Bengaluru": "ಬೆಂಗಳೂರು",
    "Chikmagalur": "ಚಿಕ್ಕಮಗಳೂರು",
    "Coorg": "ಕೊಡಗು",
}


def chunk_text(title: str | None, body: str, aliases: Sequence[str] = ()) -> str:
    """What actually gets embedded.

    The title carries real signal, so it goes in. So do the names of the place
    and the city, in English and Kannada, because a paragraph rarely repeats the
    full official name of what it is describing and a Kannada query has nothing
    else to hold on to.
    """
    text = f"{title}. {body}" if title else body
    named = " ".join(dict.fromkeys(a for a in aliases if a))
    return f"{text} {named}".strip() if named else text

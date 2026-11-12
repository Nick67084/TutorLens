"""Turn text into vectors with BAAI/bge-m3 (via sentence-transformers).

The model is downloaded the first time (about 2 GB) and then kept in memory.
Vectors are normalised, which the vector store relies on.
"""
from __future__ import annotations

from typing import Callable

from core import config

_model = None


def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        _model = SentenceTransformer(config.EMBEDDING_MODEL)
        _model.max_seq_length = 512  # keeps CPU speed reasonable; chunks are short anyway
    return _model


def embed_texts(
    texts: list[str],
    batch_size: int = 16,
    progress: Callable[[int, int], None] | None = None,
) -> list[list[float]]:
    model = _get_model()
    vectors: list[list[float]] = []
    for start in range(0, len(texts), batch_size):
        batch = texts[start:start + batch_size]
        out = model.encode(batch, normalize_embeddings=True, show_progress_bar=False)
        vectors.extend(out.tolist())
        if progress:
            progress(min(start + batch_size, len(texts)), len(texts))
    return vectors


def embed_query(text: str) -> list[float]:
    return embed_texts([text])[0]
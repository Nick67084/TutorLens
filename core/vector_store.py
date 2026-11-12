"""ChromaDB wrapper: store PDF chunks as vectors and search them by meaning.

One Chroma collection per uploaded document ("doc_<id>").
"""
from __future__ import annotations

from core import config
from core.chunker import Chunk

_client = None


def _get_client():
    global _client
    if _client is None:
        import chromadb

        _client = chromadb.PersistentClient(path=str(config.CHROMA_DIR))
    return _client


def _name(doc_id: int) -> str:
    return f"doc_{doc_id}"


def similarity_from_distance(distance: float) -> float:
    """Convert Chroma's distance to a cosine similarity.

    Chroma's default distance is the squared L2 distance. Our vectors are
    normalised, so squared L2 = 2 - 2 * cosine, which means
    cosine = 1 - distance / 2.
    """
    return 1.0 - distance / 2.0


def add_document_chunks(doc_id: int, chunks: list[Chunk], vectors: list[list[float]]) -> None:
    delete_document(doc_id)  # start clean if this id was used before
    collection = _get_client().create_collection(_name(doc_id))
    for start in range(0, len(chunks), 100):
        part = chunks[start:start + 100]
        collection.add(
            ids=[f"{doc_id}-{c.index}" for c in part],
            documents=[c.text for c in part],
            embeddings=vectors[start:start + 100],
            metadatas=[
                {"page": c.page, "section": c.section, "chunk_index": c.index} for c in part
            ],
        )


def search(doc_id: int, query_vector: list[float], k: int) -> list[dict]:
    """Return the k most similar chunks, best first."""
    collection = _get_client().get_collection(_name(doc_id))
    n_results = min(k, collection.count())
    if n_results == 0:
        return []
    result = collection.query(
        query_embeddings=[query_vector],
        n_results=n_results,
        include=["documents", "metadatas", "distances"],
    )
    hits = []
    for text, meta, distance in zip(
        result["documents"][0], result["metadatas"][0], result["distances"][0]
    ):
        hits.append(
            {
                "text": text,
                "page": int(meta["page"]),
                "section": str(meta["section"]),
                "chunk_index": int(meta["chunk_index"]),
                "similarity": similarity_from_distance(float(distance)),
            }
        )
    return hits


def get_all_chunks(doc_id: int) -> list[dict]:
    """All chunks of a document in reading order."""
    collection = _get_client().get_collection(_name(doc_id))
    data = collection.get(include=["documents", "metadatas"])
    chunks = [
        {
            "text": text,
            "page": int(meta["page"]),
            "section": str(meta["section"]),
            "chunk_index": int(meta["chunk_index"]),
        }
        for text, meta in zip(data["documents"], data["metadatas"])
    ]
    return sorted(chunks, key=lambda c: c["chunk_index"])


def get_sections(doc_id: int) -> list[str]:
    """Unique section titles in reading order."""
    seen: list[str] = []
    for chunk in get_all_chunks(doc_id):
        if chunk["section"] not in seen:
            seen.append(chunk["section"])
    return seen


def get_section_chunks(doc_id: int, section: str) -> list[dict]:
    return [c for c in get_all_chunks(doc_id) if c["section"] == section]


def delete_document(doc_id: int) -> None:
    try:
        _get_client().delete_collection(_name(doc_id))
    except Exception:  # the collection did not exist
        pass
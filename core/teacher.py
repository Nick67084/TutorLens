"""Teacher mode: retrieve the right part of the PDF and build the prompts.

The Streamlit page does the streaming; this file prepares everything else.
"""
from __future__ import annotations

from dataclasses import dataclass

from core import config, embeddings, vector_store

NOT_FOUND_MESSAGE = (
    "I could not find this in the uploaded PDF, so I will not guess. "
    "Try rephrasing your question, or check that you selected the right PDF."
)


@dataclass
class Source:
    page: int
    section: str
    text: str
    similarity: float = 1.0


def retrieve(doc_id: int, question: str, history: list[dict] | None = None) -> list[Source]:
    """Find the chunks most similar to the question (empty list = nothing relevant)."""
    query = question
    if history and len(question) < 25:
        # a short follow-up like "why?" needs the previous question for context
        previous = next((m["content"] for m in reversed(history) if m["role"] == "user"), "")
        query = f"{previous} {question}".strip()
    hits = vector_store.search(doc_id, embeddings.embed_query(query), config.TOP_K)
    return [
        Source(page=h["page"], section=h["section"], text=h["text"], similarity=h["similarity"])
        for h in hits
        if h["similarity"] >= config.MIN_SIMILARITY
    ]


def format_context(sources: list[Source]) -> str:
    return "\n\n".join(f"[p.{s.page} | {s.section}]\n{s.text}" for s in sources)


def build_answer_messages(
    question: str, sources: list[Source], history: list[dict] | None = None
) -> list[dict]:
    system = config.render_prompt("teacher", context=format_context(sources))
    recent = [{"role": m["role"], "content": m["content"]} for m in (history or [])[-6:]]
    return [{"role": "system", "content": system}, *recent, {"role": "user", "content": question}]


def section_sources(doc_id: int, section: str) -> list[Source]:
    """All text of one section (up to SECTION_CONTEXT_CHARS)."""
    sources: list[Source] = []
    total = 0
    for chunk in vector_store.get_section_chunks(doc_id, section):
        if total + len(chunk["text"]) > config.SECTION_CONTEXT_CHARS and sources:
            break
        sources.append(Source(page=chunk["page"], section=chunk["section"], text=chunk["text"]))
        total += len(chunk["text"])
    return sources


def build_section_messages(section: str, sources: list[Source]) -> list[dict]:
    system = config.render_prompt("explain_section", section=section, context=format_context(sources))
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": f"Please teach me the section: {section}"},
    ]


def clean_answer(answer: str) -> str:
    """Replace the NOT_IN_PDF signal with a friendly message."""
    if answer.strip().upper().startswith("NOT_IN_PDF"):
        return NOT_FOUND_MESSAGE
    return answer.strip()
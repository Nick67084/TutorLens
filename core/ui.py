"""Small Streamlit helpers shared by every page."""
from __future__ import annotations

import streamlit as st

from db import database, queries


def init() -> None:
    """Make sure the database tables exist."""
    database.init_db()


def sidebar_student() -> int | None:
    """Ask for the student's name in the sidebar and return the student id."""
    st.sidebar.header("Student")
    name = st.sidebar.text_input(
        "Your name",
        value=st.session_state.get("student_name", ""),
        placeholder="e.g. Somchai",
    ).strip()
    st.session_state["student_name"] = name
    if not name:
        return None
    return queries.get_or_create_student(name)


def sidebar_document() -> dict | None:
    """Let the student choose one of the uploaded PDFs."""
    documents = queries.list_documents()
    if not documents:
        return None
    ids = [d["id"] for d in documents]
    by_id = {d["id"]: d for d in documents}
    saved = st.session_state.get("doc_id")
    index = ids.index(saved) if saved in ids else 0
    chosen = st.sidebar.selectbox(
        "Course PDF",
        ids,
        index=index,
        format_func=lambda doc_id: f"{by_id[doc_id]['title']} ({by_id[doc_id]['n_pages']} pages)",
    )
    st.session_state["doc_id"] = chosen
    return by_id[chosen]


def format_sources(sources) -> str:
    """One line like: Sources: p.7 (Gradient descent) · p.8 (Learning rate)."""
    seen: dict[int, str] = {}
    for source in sources:
        seen.setdefault(source.page, source.section)
    parts = [f"p.{page} ({section[:40]})" for page, section in sorted(seen.items())]
    return "Sources: " + " · ".join(parts)
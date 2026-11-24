
"""TutorLens AI teacher with contextual retrieval and teaching modes."""

from __future__ import annotations

import re
from dataclasses import dataclass

from core import config, embeddings, vector_store


NOT_FOUND_MESSAGE = (
    "I could not find this in the uploaded PDF, so I will not guess. "
    "Try rephrasing your question, or check that you selected the right PDF."
)


# ============================================================
# TEACHING MODES
# ============================================================

TEACHING_MODES = {
    "General AI Tutor": (
        "Answer naturally and clearly. Adapt the explanation "
        "to the student's question."
    ),

    "Simple Explanation": (
        "Explain the concept using beginner-friendly language. "
        "Define technical terms and use simple illustrative examples."
    ),

    "Detailed Lesson": (
        "Provide a structured university-level lesson with definitions, "
        "detailed explanations, examples, and key takeaways."
    ),

    "Step-by-Step Solution": (
        "Explain the solution progressively. State relevant formulas, "
        "define variables, show calculations or implementation steps, "
        "and explain the final result."
    ),

    "Revision Summary": (
        "Create organized revision notes. Highlight key concepts, "
        "important definitions, formulas, and essential facts."
    ),

    "Code Explanation": (
        "Explain the relevant code line by line. Describe its purpose, "
        "functions, variables, execution flow, and expected behavior. "
        "Use properly formatted code blocks."
    ),

    "Socratic Tutor": (
        "Guide the student using hints and focused questions. "
        "Do not immediately reveal the complete solution. "
        "Encourage the student to reason independently."
    ),
}


ANSWER_LENGTHS = {
    "Short": (
        "Give a concise answer focusing on the essential information."
    ),

    "Balanced": (
        "Provide enough detail to explain the concept clearly "
        "without unnecessary repetition."
    ),

    "Detailed": (
        "Provide a comprehensive explanation with relevant examples "
        "and supporting details when the PDF context permits."
    ),
}


# ============================================================
# SOURCE MODEL
# ============================================================

@dataclass
class Source:
    page: int
    section: str
    text: str
    similarity: float = 1.0


# ============================================================
# CONVERSATION MEMORY
# ============================================================

def get_recent_history(
    history: list[dict] | None = None,
    max_messages: int = 10,
    max_chars: int = 6000,
) -> list[dict]:
    """Return recent conversation messages within a size limit."""

    recent = []
    total_chars = 0

    for message in reversed((history or [])[-max_messages:]):
        role = message.get("role", "")
        content = message.get("content", "")

        if role not in {"user", "assistant"}:
            continue

        if not isinstance(content, str) or not content.strip():
            continue

        remaining = max_chars - total_chars

        if remaining <= 0:
            break

        content = content[:remaining]

        recent.append({
            "role": role,
            "content": content,
        })

        total_chars += len(content)

    return list(reversed(recent))


def is_follow_up(question: str) -> bool:
    """Detect common conversational follow-up questions."""

    question = question.strip().lower()

    patterns = [
        r"\b(it|this|that|these|those|them)\b",
        r"\banother example\b",
        r"\bmore examples?\b",
        r"\bexplain again\b",
        r"\bexplain more\b",
        r"\bmore detail\b",
        r"\bmore simply\b",
        r"\bsimplify\b",
        r"\belaborate\b",
        r"\bprevious\b",
        r"\babove\b",
        r"\bcontinue\b",
        r"\bsummarize\b",
        r"\bwhat about\b",
        r"\bhow about\b",
        r"\bwe just discussed\b",
        r"\byour answer\b",
        r"^(why|how|what)\??$",
    ]

    return any(
        re.search(pattern, question)
        for pattern in patterns
    )


def build_retrieval_query(
    question: str,
    history: list[dict] | None = None,
) -> str:
    """Add previous student questions to contextual follow-ups."""

    if not history or not is_follow_up(question):
        return question

    previous_questions = [
        message["content"]
        for message in get_recent_history(history)
        if message["role"] == "user"
        and message["content"].strip() != question.strip()
    ]

    if not previous_questions:
        return question

    previous_context = " ".join(previous_questions[-2:])

    return f"{previous_context} {question}".strip()


# ============================================================
# RAG RETRIEVAL
# ============================================================

def retrieve(
    doc_id: int,
    question: str,
    history: list[dict] | None = None,
) -> list[Source]:
    """Retrieve relevant PDF chunks using contextual search."""

    question = question.strip()

    if not question:
        return []

    contextual_query = build_retrieval_query(
        question,
        history,
    )

    queries = [question]

    if contextual_query != question:
        queries.append(contextual_query)

    unique_sources: dict[tuple, Source] = {}

    for query in queries:

        query_embedding = embeddings.embed_query(query)

        hits = vector_store.search(
            doc_id,
            query_embedding,
            config.TOP_K,
        )

        for hit in hits:

            similarity = hit["similarity"]

            if similarity < config.MIN_SIMILARITY:
                continue

            source = Source(
                page=hit["page"],
                section=hit["section"],
                text=hit["text"],
                similarity=similarity,
            )

            key = (
                source.page,
                source.section,
                source.text.strip(),
            )

            existing = unique_sources.get(key)

            if existing is None or (
                source.similarity > existing.similarity
            ):
                unique_sources[key] = source

    ranked_sources = sorted(
        unique_sources.values(),
        key=lambda source: source.similarity,
        reverse=True,
    )

    return ranked_sources[:config.TOP_K]


# ============================================================
# CONTEXT FORMATTING
# ============================================================

def format_context(sources: list[Source]) -> str:
    """Format retrieved PDF content with page references."""

    return "\n\n".join(
        f"[p.{source.page} | {source.section}]\n"
        f"{source.text}"
        for source in sources
    )


# ============================================================
# AI ANSWER GENERATION
# ============================================================

def build_answer_messages(
    question: str,
    sources: list[Source],
    history: list[dict] | None = None,
    mode: str = "General AI Tutor",
    answer_length: str = "Balanced",
) -> list[dict]:
    """Build grounded AI messages with memory and teaching preferences."""

    system = config.render_prompt(
        "teacher",
        context=format_context(sources),
    )

    mode_instruction = TEACHING_MODES.get(
        mode,
        TEACHING_MODES["General AI Tutor"],
    )

    length_instruction = ANSWER_LENGTHS.get(
        answer_length,
        ANSWER_LENGTHS["Balanced"],
    )

    system += (
        "\n\n# ACTIVE TEACHING PREFERENCES\n"
        f"Teaching mode: {mode}\n"
        f"{mode_instruction}\n\n"
        f"Answer length: {answer_length}\n"
        f"{length_instruction}\n\n"
        "Use conversation history to understand follow-up questions. "
        "Conversation history is not independent factual evidence. "
        "Verify factual claims against the supplied PDF context. "
        "Do not invent page references or unsupported information. "
        "Teaching preferences must not override PDF grounding rules."
    )

    recent = get_recent_history(history)

    # Avoid repeating the current question if it is already in history.
    if recent and recent[-1]["role"] == "user":
        if recent[-1]["content"].strip() == question.strip():
            recent.pop()

    return [
        {"role": "system", "content": system},
        *recent,
        {"role": "user", "content": question},
    ]


# ============================================================
# SECTION-BASED LEARNING
# ============================================================

def section_sources(
    doc_id: int,
    section: str,
) -> list[Source]:
    """Retrieve the text of a selected PDF section."""

    sources: list[Source] = []
    total = 0

    for chunk in vector_store.get_section_chunks(
        doc_id,
        section,
    ):

        if (
            total + len(chunk["text"])
            > config.SECTION_CONTEXT_CHARS
            and sources
        ):
            break

        sources.append(
            Source(
                page=chunk["page"],
                section=chunk["section"],
                text=chunk["text"],
            )
        )

        total += len(chunk["text"])

    return sources


def build_section_messages(
    section: str,
    sources: list[Source],
    mode: str = "Detailed Lesson",
    answer_length: str = "Balanced",
) -> list[dict]:
    """Build a personalized lesson for a selected section."""

    system = config.render_prompt(
        "explain_section",
        section=section,
        context=format_context(sources),
    )

    mode_instruction = TEACHING_MODES.get(
        mode,
        TEACHING_MODES["Detailed Lesson"],
    )

    length_instruction = ANSWER_LENGTHS.get(
        answer_length,
        ANSWER_LENGTHS["Balanced"],
    )

    system += (
        "\n\n# ACTIVE TEACHING PREFERENCES\n"
        f"Teaching mode: {mode}\n"
        f"{mode_instruction}\n\n"
        f"Answer length: {answer_length}\n"
        f"{length_instruction}\n\n"
        "Adapt the lesson structure to the selected teaching mode "
        "while preserving PDF grounding."
    )

    return [
        {"role": "system", "content": system},
        {
            "role": "user",
            "content": f"Please teach me the section: {section}",
        },
    ]


# ============================================================
# RESPONSE CLEANING
# ============================================================

def clean_answer(answer: str) -> str:
    """Replace the NOT_IN_PDF signal with a friendly message."""

    if not answer or not answer.strip():
        return (
            "The AI returned an empty response. "
            "Please try asking your question again."
        )

    if answer.strip().upper().startswith("NOT_IN_PDF"):
        return NOT_FOUND_MESSAGE

    return answer.strip()

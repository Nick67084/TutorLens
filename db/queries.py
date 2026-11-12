"""All database reads and writes used by the app. Every function returns plain
Python values (ints, dicts, lists) so the pages never touch SQLAlchemy objects."""
from sqlalchemy import delete, func, select

from db.database import get_session
from db.tables import Attempt, Document, QuestionRow, Student
from models.schemas import GradeResult, Question


# ---- students ------------------------------------------------------------
def get_or_create_student(name: str) -> int:
    with get_session() as session:
        student = session.scalar(select(Student).where(Student.name == name))
        if student is None:
            student = Student(name=name)
            session.add(student)
            session.flush()
        return student.id


# ---- documents -----------------------------------------------------------
def _document_dict(doc: Document) -> dict:
    return {
        "id": doc.id,
        "title": doc.title,
        "filename": doc.filename,
        "file_hash": doc.file_hash,
        "n_pages": doc.n_pages,
        "uploaded_at": doc.uploaded_at,
    }


def add_document(title: str, filename: str, file_hash: str, n_pages: int) -> int:
    with get_session() as session:
        doc = Document(title=title, filename=filename, file_hash=file_hash, n_pages=n_pages)
        session.add(doc)
        session.flush()
        return doc.id


def get_document_by_hash(file_hash: str) -> dict | None:
    with get_session() as session:
        doc = session.scalar(select(Document).where(Document.file_hash == file_hash))
        return _document_dict(doc) if doc else None


def list_documents() -> list[dict]:
    with get_session() as session:
        docs = session.scalars(select(Document).order_by(Document.id)).all()
        return [_document_dict(d) for d in docs]


def delete_document(doc_id: int) -> None:
    """Delete a document together with its questions and attempts."""
    with get_session() as session:
        question_ids = select(QuestionRow.id).where(QuestionRow.document_id == doc_id)
        session.execute(delete(Attempt).where(Attempt.question_id.in_(question_ids)))
        session.execute(delete(QuestionRow).where(QuestionRow.document_id == doc_id))
        session.execute(delete(Document).where(Document.id == doc_id))


# ---- questions -----------------------------------------------------------
def next_quiz_no(doc_id: int) -> int:
    with get_session() as session:
        current = session.scalar(
            select(func.max(QuestionRow.quiz_no)).where(QuestionRow.document_id == doc_id)
        )
        return (current or 0) + 1


def save_questions(doc_id: int, quiz_no: int, questions: list[Question]) -> list[int]:
    with get_session() as session:
        rows = [
            QuestionRow(
                document_id=doc_id,
                quiz_no=quiz_no,
                topic=q.topic,
                difficulty=q.difficulty,
                type=q.type,
                question=q.question,
                options=q.options,
                answer=q.answer,
                rubric=q.rubric,
                source_page=q.source_page,
            )
            for q in questions
        ]
        session.add_all(rows)
        session.flush()
        return [row.id for row in rows]


# ---- attempts and marks --------------------------------------------------
def save_attempt(student_id: int, question_id: int, answer_text: str | None, grade: GradeResult) -> None:
    with get_session() as session:
        session.add(
            Attempt(
                student_id=student_id,
                question_id=question_id,
                answer_text=answer_text,
                points=grade.points,
                max_points=grade.max_points,
                score=grade.score,
                feedback=grade.feedback,
                checks=[check.model_dump() for check in grade.checks],
            )
        )


def get_attempts(student_id: int) -> list[dict]:
    """Every answer a student has given, newest first."""
    with get_session() as session:
        rows = session.execute(
            select(Attempt, QuestionRow, Document)
            .select_from(Attempt)
            .join(QuestionRow, Attempt.question_id == QuestionRow.id)
            .join(Document, QuestionRow.document_id == Document.id)
            .where(Attempt.student_id == student_id)
            .order_by(Attempt.created_at.desc(), Attempt.id.desc())
        ).all()
        return [
            {
                "created_at": attempt.created_at,
                "pdf": doc.title,
                "quiz_no": question.quiz_no,
                "type": question.type,
                "difficulty": question.difficulty,
                "question": question.question,
                "answer_text": attempt.answer_text or "",
                "points": attempt.points,
                "max_points": attempt.max_points,
                "feedback": attempt.feedback,
            }
            for attempt, question, doc in rows
        ]


def get_quiz_summary(student_id: int) -> list[dict]:
    """One row per quiz: total points and maximum points."""
    with get_session() as session:
        rows = session.execute(
            select(
                Document.title,
                QuestionRow.quiz_no,
                func.count(Attempt.id),
                func.sum(Attempt.points),
                func.sum(Attempt.max_points),
                func.max(Attempt.created_at),
            )
            .select_from(Attempt)
            .join(QuestionRow, Attempt.question_id == QuestionRow.id)
            .join(Document, QuestionRow.document_id == Document.id)
            .where(Attempt.student_id == student_id)
            .group_by(Document.id, QuestionRow.quiz_no)
            .order_by(func.max(Attempt.created_at).desc())
        ).all()
        return [
            {
                "pdf": title,
                "quiz_no": quiz_no,
                "questions": n_questions,
                "points": int(points or 0),
                "max_points": int(max_points or 0),
                "date": last,
            }
            for title, quiz_no, n_questions, points, max_points, last in rows
        ]
"""SQLite connection (SQLAlchemy)."""
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core import config
from db.tables import Base

engine = create_engine(
    f"sqlite:///{config.DB_PATH.as_posix()}",
    connect_args={"check_same_thread": False},  # Streamlit runs code in several threads
)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def init_db() -> None:
    """Create the tables if they do not exist yet (safe to call many times)."""
    Base.metadata.create_all(engine)


@contextmanager
def get_session():
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
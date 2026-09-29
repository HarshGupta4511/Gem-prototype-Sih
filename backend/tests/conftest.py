"""Shared pytest fixtures: an isolated sqlite DB file per test.

The suite never touches the real/dev database — each test gets a fresh file
in ``tmp_path`` with the full schema created via ``Base.metadata.create_all``.
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.base import Base


@pytest.fixture()
def db(tmp_path):
    """Yield a SQLAlchemy Session bound to a fresh per-test sqlite file."""
    db_file = tmp_path / "test.db"
    engine = create_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False,
                                   expire_on_commit=False)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()

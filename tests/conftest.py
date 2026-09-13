import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


# Importing main.py creates its configured tables. Force that import-time work to
# an in-memory database so the developer's cruises.db is never opened by tests.
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from models import Base  # noqa: E402


@pytest.fixture
def db_session(tmp_path):
    database_path = tmp_path / "test.db"
    engine = create_engine(
        f"sqlite:///{database_path}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    testing_session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = testing_session()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()

import os

# Must be set before importing the application, whose SQLAlchemy engine is
# configured at module import time.
os.environ["DATABASE_URL"] = "sqlite:///./test_cold_calling.db"
os.environ["CALLING_MODE"] = "mock"
os.environ["LLM_MODE"] = "test"

import pytest
from fastapi.testclient import TestClient

from app.database.base import Base
from app.database.connection import engine
from app.main import app


@pytest.fixture(autouse=True)
def clean_database(monkeypatch):
    from app.services import call_service

    monkeypatch.setattr(call_service, "enqueue_call", lambda call: False)
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client

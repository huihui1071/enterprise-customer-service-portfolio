import os
from pathlib import Path


TEST_DB = Path(__file__).parent / "test_customer_service.db"
os.environ["DATABASE_PATH"] = str(TEST_DB)
os.environ["JWT_SECRET"] = "test-secret"
os.environ["ENABLE_FAULT_INJECTION"] = "true"

import pytest
from fastapi.testclient import TestClient

from app.database import initialize_database
from app.main import app


@pytest.fixture(autouse=True)
def fresh_database():
    initialize_database(force=True)
    yield
    if TEST_DB.exists():
        TEST_DB.unlink()


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def token_for(client, user_id):
    response = client.post("/v1/auth/token", json={"user_id": user_id})
    assert response.status_code == 200
    return response.json()["access_token"]


@pytest.fixture
def auth_headers(client):
    def build(user_id):
        return {"Authorization": f"Bearer {token_for(client, user_id)}"}
    return build

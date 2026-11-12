import os
import tempfile

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["RATE_LIMIT_ENABLED"] = "false"
os.environ["JWT_SECRET"] = "test-secret-please-change-me-32bytes"
os.environ["STORAGE_BACKEND"] = "local"
os.environ["LOCAL_STORAGE_PATH"] = tempfile.mkdtemp(prefix="wms-test-")
os.environ["REDIS_URL"] = ""
os.environ["ENV"] = "test"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import Base, SessionLocal, engine
from app.core.security import hash_password
from app.main import app
from app.models.entities import User

PASSWORD = "Wms-demo-123"


@pytest.fixture(autouse=True)
def reset_db():
    with engine.begin() as connection:
        connection.execute(text("DROP VIEW IF EXISTS inventory_balances_by_sku"))
        connection.execute(text("DROP VIEW IF EXISTS inventory_balances"))
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def admin(client):
    db: Session = SessionLocal()
    db.add(
        User(
            email="admin@test.local",
            password_hash=hash_password(PASSWORD),
            full_name="Ada Admin",
            role="admin",
            active=True,
        )
    )
    db.commit()
    db.close()
    response = client.post("/api/v1/auth/login", json={"email": "admin@test.local", "password": PASSWORD})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def auth_header(client, email: str) -> dict[str, str]:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}

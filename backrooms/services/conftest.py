"""Shared pytest bootstrap for the Nexova Supply Directory API test suite.

This conftest is loaded before any test module so it can:

1. Make the ``services.Supply_directory_API`` package importable by adding the
   ``backrooms`` directory to ``sys.path``.
2. Set the environment variables that ``auth.security`` and ``auth.email`` read
   at import time (so they never depend on a local ``.env`` during a test run).
3. Expose fixtures that run each test against an isolated temporary TinyDB so
   the tracked ``suppliers_db.json`` and local ``password_resets_db.json`` are
   never touched, and stub the Resend sender so no real email is sent.
"""

import os
import sys
from pathlib import Path

import pytest

# The `backrooms` directory is the parent of `services`, which is the directory
# that contains this file. `services.Supply_directory_API.*` imports only work
# when `backrooms` is importable.
BACKROOMS_ROOT = Path(__file__).resolve().parent.parent
if str(BACKROOMS_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKROOMS_ROOT))

# Must be set before importing anything that reads the environment at import
# time (auth.security and auth.email both call load_dotenv and read env vars).
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-for-pytest")
os.environ.setdefault("JWT_EXPIRY_MINUTES", "30")
os.environ.setdefault("PASSWORD_RESET_EXPIRY_MINUTES", "30")
os.environ.setdefault("PASSWORD_RESET_URL", "http://localhost:3000/reset-password")
os.environ.setdefault("RESEND_API_KEY", "test-api-key-for-pytest")

from fastapi.testclient import TestClient  # noqa: E402

from services.Supply_directory_API import database  # noqa: E402
from services.Supply_directory_API.database import get_db  # noqa: E402
from services.Supply_directory_API.main import app  # noqa: E402
from services.Supply_directory_API.routes import auth as auth_routes  # noqa: E402


@pytest.fixture()
def db(tmp_path, monkeypatch):
    """Point TinyDB at an isolated temporary file for the duration of a test."""
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "suppliers_db.json")
    monkeypatch.setattr(
        database, "PASSWORD_RESETS_DB_PATH", tmp_path / "password_resets_db.json"
    )
    with get_db() as tiny_db:
        yield tiny_db


@pytest.fixture()
def client(db):
    """A TestClient whose database writes land in an isolated temp TinyDB."""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def registered_user(client):
    """Register a single user and return its credentials for login."""
    email = "user@nexova.com"
    password = "initial-password-123"
    response = client.post(
        "/users",
        json={"email": email, "password": password, "name": "Test User"},
    )
    assert response.status_code == 201
    return {"email": email, "password": password}


@pytest.fixture()
def auth_headers(client, registered_user):
    """Authorization headers for the user created by ``registered_user``."""
    response = client.post(
        "/auth/login",
        json={
            "email": registered_user["email"],
            "password": registered_user["password"],
        },
    )
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def email_sender(monkeypatch):
    """Stub the Resend sender and record every attempted send."""
    sent: list[dict] = []

    def fake_send(to_email: str, token: str, expires_in_minutes: int) -> None:
        sent.append(
            {
                "to": to_email,
                "token": token,
                "expires_in_minutes": expires_in_minutes,
            }
        )

    monkeypatch.setattr(auth_routes, "send_password_reset_email", fake_send)
    return sent

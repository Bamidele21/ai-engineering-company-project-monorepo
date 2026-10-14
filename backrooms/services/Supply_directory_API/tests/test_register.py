"""Endpoint tests for user registration (``POST /users``).

Registration is the entry point to the authentication flow: it must hash the
password, default the role, and create a linked profile — all verified here as
business outcomes rather than response serialisation.
"""

from services.Supply_directory_API.auth.services import (
	get_profile_by_user_id,
	get_user_by_id,
)
from services.Supply_directory_API.database import get_db, get_users_table


def _register(client, email, password="valid-password-123", **extra):
    payload = {"email": email, "password": password, **extra}
    return client.post("/users", json=payload)


# --- Happy path -------------------------------------------------------------


def test_register_creates_user_with_defaults(client):
    response = _register(client, "new@nexova.com")
    assert response.status_code == 201

    body = response.json()
    # The registration response is a safe projection: only the new id.
    assert set(body) == {"id"}
    assert "hashed_password" not in body
    assert "password" not in body
    assert "email" not in body

    # Defaults are applied in storage rather than echoed by the response.
    with get_db() as db:
        user = get_user_by_id(db, body["id"])
    assert user.role == "user"
    assert user.is_active is True


def test_register_lowercases_email(client):
    response = _register(client, "MixedCase@Nexova.com")
    assert response.status_code == 201

    with get_db() as db:
        user = get_user_by_id(db, response.json()["id"])
    assert user.email == "mixedcase@nexova.com"


def test_register_creates_linked_profile(client):
    response = _register(client, "profiled@nexova.com", name="Patricia Solis")
    user_id = response.json()["id"]

    with get_db() as db:
        profile_entry = get_profile_by_user_id(db, user_id)
    assert profile_entry is not None
    assert profile_entry[1].name == "Patricia Solis"


def test_register_stores_password_as_bcrypt_hash(client):
    _register(client, "hashed@nexova.com", password="super-secret-99")

    with get_db() as db:
        stored = get_users_table(db).all()[0]["hashed_password"]
    assert stored.startswith("$2")
    assert "super-secret-99" not in stored


# --- Edge cases -------------------------------------------------------------


def test_register_rejects_duplicate_email(client):
    assert _register(client, "dup@nexova.com").status_code == 201
    duplicate = _register(client, "dup@nexova.com")
    assert duplicate.status_code == 409


def test_register_rejects_duplicate_email_case_insensitively(client):
    assert _register(client, "dup@nexova.com").status_code == 201
    assert _register(client, "DUP@nexova.com").status_code == 409


def test_register_rejects_short_password(client):
    assert _register(client, "short@nexova.com", password="short").status_code == 422


# --- Failure modes ----------------------------------------------------------


def test_register_rejects_empty_password(client):
    assert _register(client, "empty@nexova.com", password="").status_code == 422


def test_register_rejects_missing_password(client):
    response = client.post("/users", json={"email": "nopass@nexova.com"})
    assert response.status_code == 422


def test_register_rejects_invalid_email(client):
    assert _register(client, "not-an-email").status_code == 422

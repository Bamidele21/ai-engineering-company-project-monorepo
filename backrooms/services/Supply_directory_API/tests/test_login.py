"""Endpoint tests for login (``POST /auth/login``).

Focuses on the credential decision: a valid email+password pair issues a token;
an inactive account, an unknown email, or a wrong password are all rejected
without revealing which one failed.
"""

from services.Supply_directory_API.auth.services import get_user_entry_by_email
from services.Supply_directory_API.database import get_db, get_users_table


def _login(client, email, password):
    return client.post("/auth/login", json={"email": email, "password": password})


# --- Happy path -------------------------------------------------------------


def test_login_returns_token_for_valid_credentials(client, registered_user):
    response = _login(
        client, registered_user["email"], registered_user["password"]
    )
    assert response.status_code == 200

    body = response.json()
    assert body["access_token"]
    assert body["token_type"] == "bearer"
    assert body["expires_in"] > 0


def test_login_accepts_email_case_insensitively(client, registered_user):
    response = _login(client, registered_user["email"].upper(), registered_user["password"])
    assert response.status_code == 200


# --- Edge cases -------------------------------------------------------------


def test_login_rejects_inactive_user(client, registered_user):
    with get_db() as db:
        user_id, _ = get_user_entry_by_email(db, registered_user["email"])
        get_users_table(db).update({"is_active": False}, doc_ids=[user_id])

    response = _login(client, registered_user["email"], registered_user["password"])
    assert response.status_code == 401


def test_login_rejects_empty_password(client, registered_user):
    assert _login(client, registered_user["email"], "").status_code == 401


# --- Failure modes ----------------------------------------------------------


def test_login_rejects_wrong_password(client, registered_user):
    response = _login(client, registered_user["email"], "totally-wrong-password")
    assert response.status_code == 401


def test_login_rejects_unknown_email(client):
    assert _login(client, "nobody@nexova.com", "whatever-123").status_code == 401


def test_login_rejects_invalid_email(client):
    assert _login(client, "not-an-email", "whatever-123").status_code == 422

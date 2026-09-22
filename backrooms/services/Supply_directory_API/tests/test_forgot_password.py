"""Endpoint tests for password reset requests (``POST /auth/forgot-password``).

The key business rule here is enumeration resistance: the endpoint always
returns 200 and only generates/sends a reset token for an active, registered
address. A misconfigured email service fails loudly with 503 before any lookup.
"""

from services.Supply_directory_API.auth import security
from services.Supply_directory_API.auth.services import get_user_entry_by_email
from services.Supply_directory_API.database import get_db, get_users_table
from services.Supply_directory_API.routes import auth as auth_routes


def _forgot(client, email):
    return client.post("/auth/forgot-password", json={"email": email})


# --- Happy path -------------------------------------------------------------


def test_forgot_password_sends_email_for_registered_user(
    client, registered_user, email_sender
):
    response = _forgot(client, registered_user["email"])
    assert response.status_code == 200

    assert len(email_sender) == 1
    assert email_sender[0]["to"] == registered_user["email"]
    assert 15 <= email_sender[0]["expires_in_minutes"] <= 60


def test_forgot_password_generates_decodable_reset_token(
    client, registered_user, email_sender
):
    _forgot(client, registered_user["email"])

    user_id, jti = security.decode_password_reset_token(email_sender[0]["token"])
    assert user_id == _registered_user_id(registered_user["email"])
    assert isinstance(jti, str) and jti


# --- Edge cases -------------------------------------------------------------


def test_forgot_password_returns_200_for_unknown_email(client, email_sender):
    response = _forgot(client, "nobody@nexova.com")
    assert response.status_code == 200
    assert len(email_sender) == 0


def test_forgot_password_sends_nothing_for_inactive_user(
    client, registered_user, email_sender
):
    with get_db() as db:
        user_id, _ = get_user_entry_by_email(db, registered_user["email"])
        get_users_table(db).update({"is_active": False}, doc_ids=[user_id])

    response = _forgot(client, registered_user["email"])
    assert response.status_code == 200
    assert len(email_sender) == 0


# --- Failure modes ----------------------------------------------------------


def test_forgot_password_returns_503_when_email_not_configured(
    client, registered_user, monkeypatch
):
    monkeypatch.setattr(auth_routes, "is_email_delivery_configured", lambda: False)
    response = _forgot(client, registered_user["email"])
    assert response.status_code == 503


def test_forgot_password_rejects_invalid_email(client):
    assert _forgot(client, "not-an-email").status_code == 422


def _registered_user_id(email: str) -> int:
    with get_db() as db:
        user_id, _ = get_user_entry_by_email(db, email)
    return user_id

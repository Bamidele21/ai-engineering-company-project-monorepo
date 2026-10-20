"""Endpoint tests for completing a password reset (``POST /auth/reset-password``).

Covers the token lifecycle the AUTH-088 regression was about: a valid token
resets the password exactly once, while expired, replayed, malformed, and
wrong-type tokens are all rejected with 400.
"""

from datetime import datetime, timedelta, timezone

from services.Supply_directory_API.auth import security
from services.Supply_directory_API.auth.services import get_password_reset_by_jti
from services.Supply_directory_API.database import (
    get_password_resets_db,
    get_password_resets_table,
)

NEW_PASSWORD = "brand-new-password-456"


def _request_token(client, email_sender, email):
    client.post("/auth/forgot-password", json={"email": email})
    return email_sender[0]["token"]


def _reset(client, token, new_password=NEW_PASSWORD):
    return client.post(
        "/auth/reset-password", json={"token": token, "new_password": new_password}
    )


def _login(client, email, password):
    return client.post("/auth/login", json={"email": email, "password": password})


# --- Happy path -------------------------------------------------------------


def test_reset_password_updates_password(client, registered_user, email_sender):
    token = _request_token(client, email_sender, registered_user["email"])

    response = _reset(client, token)
    assert response.status_code == 200

    assert _login(client, registered_user["email"], registered_user["password"]).status_code == 401
    assert _login(client, registered_user["email"], NEW_PASSWORD).status_code == 200


# --- Edge cases -------------------------------------------------------------


def test_reset_token_is_single_use(client, registered_user, email_sender):
    token = _request_token(client, email_sender, registered_user["email"])

    assert _reset(client, token).status_code == 200
    replay = _reset(client, token, new_password="another-password-789")
    assert replay.status_code == 400


def test_reset_token_rejected_after_expiry(client, registered_user, email_sender):
    token = _request_token(client, email_sender, registered_user["email"])
    _, jti = security.decode_password_reset_token(token)

    doc_id, _ = get_password_reset_by_jti(jti)
    with get_password_resets_db() as db:
        get_password_resets_table(db).update(
            {
                "expires_at": (
                    datetime.now(timezone.utc) - timedelta(minutes=5)
                ).isoformat()
            },
            doc_ids=[doc_id],
        )

    assert _reset(client, token).status_code == 400


# --- Failure modes ----------------------------------------------------------


def test_reset_password_rejects_malformed_token(client):
    assert _reset(client, "not-a-jwt").status_code == 400


def test_reset_password_rejects_access_token(client, registered_user):
    login_response = _login(client, registered_user["email"], registered_user["password"])
    access_token = login_response.json()["access_token"]
    assert _reset(client, access_token).status_code == 400


def test_reset_password_rejects_short_new_password(client, registered_user, email_sender):
    token = _request_token(client, email_sender, registered_user["email"])
    assert _reset(client, token, new_password="short").status_code == 422

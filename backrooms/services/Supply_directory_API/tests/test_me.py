"""Endpoint tests for the authenticated account view (``GET /auth/me``).

Verifies the identity resolution behind the protected endpoint: a valid bearer
token maps to the right user plus linked profile, while missing, malformed, or
expired tokens are rejected with 401.
"""

from datetime import datetime, timedelta, timezone

from jose import jwt

from services.Supply_directory_API.auth import security
from services.Supply_directory_API.auth.services import (
    get_profile_by_user_id,
    get_user_entry_by_email,
)
from services.Supply_directory_API.database import get_db, get_profiles_table


def _registered_user_id(email: str) -> int:
    with get_db() as db:
        user_id, _ = get_user_entry_by_email(db, email)
    return user_id


# --- Happy path -------------------------------------------------------------


def test_me_returns_email_and_profile(client, registered_user, auth_headers):
    response = client.get("/auth/me", headers=auth_headers)
    assert response.status_code == 200

    body = response.json()
    assert body["email"] == registered_user["email"]
    assert body["profile"]["name"] == "Test User"
    assert "hashed_password" not in body


# --- Edge cases -------------------------------------------------------------


def test_me_returns_404_when_profile_is_missing(client, registered_user, auth_headers):
    user_id = _registered_user_id(registered_user["email"])
    with get_db() as db:
        profile_id, _ = get_profile_by_user_id(db, user_id)
        get_profiles_table(db).remove(doc_ids=[profile_id])

    assert client.get("/auth/me", headers=auth_headers).status_code == 404


# --- Failure modes ----------------------------------------------------------


def test_me_requires_authentication(client):
    assert client.get("/auth/me").status_code == 401


def test_me_rejects_malformed_token(client):
    response = client.get(
        "/auth/me", headers={"Authorization": "Bearer not-a-jwt"}
    )
    assert response.status_code == 401


def test_me_rejects_expired_token(client, registered_user):
    secret = security._jwt_secret()
    expired = jwt.encode(
        {
            "sub": str(_registered_user_id(registered_user["email"])),
            "exp": datetime.now(timezone.utc) - timedelta(minutes=1),
        },
        secret,
        algorithm=security.JWT_ALGORITHM,
    )
    response = client.get("/auth/me", headers={"Authorization": f"Bearer {expired}"})
    assert response.status_code == 401

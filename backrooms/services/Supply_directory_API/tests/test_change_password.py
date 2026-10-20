"""Endpoint tests for changing a password while authenticated (``POST /auth/change-password``).

Verifies the authenticated password-change decision: the current password must
match and a session token must be present; otherwise the change is refused.
"""

NEW_PASSWORD = "updated-password-456"


def _change(client, current_password, new_password=NEW_PASSWORD, headers=None):
    return client.post(
        "/auth/change-password",
        headers=headers or {},
        json={"current_password": current_password, "new_password": new_password},
    )


def _login(client, email, password):
    return client.post("/auth/login", json={"email": email, "password": password})


# --- Happy path -------------------------------------------------------------


def test_change_password_succeeds_with_correct_current(
    client, registered_user, auth_headers
):
    response = _change(
        client, registered_user["password"], headers=auth_headers
    )
    assert response.status_code == 200

    assert _login(client, registered_user["email"], registered_user["password"]).status_code == 401
    assert _login(client, registered_user["email"], NEW_PASSWORD).status_code == 200


# --- Failure modes ----------------------------------------------------------


def test_change_password_rejects_wrong_current(client, auth_headers):
    response = _change(client, "definitely-wrong", headers=auth_headers)
    assert response.status_code == 400


def test_change_password_requires_authentication(client):
    response = _change(client, "whatever-password")
    assert response.status_code == 401


# --- Edge cases -------------------------------------------------------------


def test_change_password_rejects_short_new_password(client, auth_headers):
    response = _change(
        client, "current-password", new_password="short", headers=auth_headers
    )
    assert response.status_code == 422

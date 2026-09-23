"""Endpoint tests for user management (``/users``).

Registration (``POST /users``) is covered by ``test_register.py``; these tests
focus on the backoffice management endpoints — listing, reading, updating, and
deleting users — and the ownership/admin authorization rules behind them.
"""

from services.Supply_directory_API.auth.services import get_user_by_id
from services.Supply_directory_API.database import get_db


def _me_id(client, headers) -> int:
    return client.get("/auth/me", headers=headers).json()["id"]


def _register(client, email, password="some-password-123"):
    return client.post("/users", json={"email": email, "password": password})


# --- List -------------------------------------------------------------------


def test_list_users_returns_registered_users(client, registered_user, auth_headers):
    response = client.get("/users", headers=auth_headers)
    assert response.status_code == 200
    emails = [user["email"] for user in response.json()]
    assert registered_user["email"] in emails


def test_list_users_requires_authentication(client):
    assert client.get("/users").status_code == 401


# --- Get by id --------------------------------------------------------------


def test_get_user_returns_own_record(client, registered_user, auth_headers):
    user_id = _me_id(client, auth_headers)
    response = client.get(f"/users/{user_id}", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["email"] == registered_user["email"]


def test_get_user_allows_admin_for_any_record(client, admin_headers, auth_headers):
    user_id = _me_id(client, auth_headers)
    response = client.get(f"/users/{user_id}", headers=admin_headers)
    assert response.status_code == 200


def test_get_user_rejects_non_owner_non_admin(client, auth_headers):
    other = _register(client, "other@nexova.com")
    other_id = other.json()["id"]
    assert client.get(f"/users/{other_id}", headers=auth_headers).status_code == 403


def test_get_user_unknown_id_returns_404(client, admin_headers):
    # An admin passes the ownership check, so the unknown id surfaces as 404.
    assert client.get("/users/9999", headers=admin_headers).status_code == 404


# --- Update -----------------------------------------------------------------


def test_update_user_changes_own_email(client, auth_headers):
    user_id = _me_id(client, auth_headers)
    response = client.put(
        f"/users/{user_id}", headers=auth_headers, json={"email": "renamed@nexova.com"}
    )
    assert response.status_code == 200
    assert response.json()["email"] == "renamed@nexova.com"


def test_update_user_rejects_taken_email(client, auth_headers):
    _register(client, "taken@nexova.com")
    user_id = _me_id(client, auth_headers)
    response = client.put(
        f"/users/{user_id}", headers=auth_headers, json={"email": "taken@nexova.com"}
    )
    assert response.status_code == 409


def test_update_user_rejects_non_owner(client, auth_headers):
    other = _register(client, "other@nexova.com")
    other_id = other.json()["id"]
    response = client.put(
        f"/users/{other_id}", headers=auth_headers, json={"email": "x@nexova.com"}
    )
    assert response.status_code == 403


def test_update_role_requires_admin(client, auth_headers):
    # A regular user cannot promote themselves.
    user_id = _me_id(client, auth_headers)
    response = client.put(f"/users/{user_id}", headers=auth_headers, json={"role": "admin"})
    assert response.status_code == 403


def test_admin_can_update_role(client, auth_headers, admin_headers):
    other_id = _me_id(client, auth_headers)
    response = client.put(f"/users/{other_id}", headers=admin_headers, json={"role": "manager"})
    assert response.status_code == 200
    assert response.json()["role"] == "manager"


# --- Delete -----------------------------------------------------------------


def test_delete_user_removes_own_record(client, auth_headers):
    user_id = _me_id(client, auth_headers)
    assert client.delete(f"/users/{user_id}", headers=auth_headers).status_code == 200

    with get_db() as db:
        assert get_user_by_id(db, user_id) is None


def test_delete_user_rejects_non_owner(client, auth_headers):
    other = _register(client, "other@nexova.com")
    other_id = other.json()["id"]
    assert client.delete(f"/users/{other_id}", headers=auth_headers).status_code == 403


def test_delete_user_unknown_id_returns_404(client, admin_headers):
    assert client.delete("/users/9999", headers=admin_headers).status_code == 404

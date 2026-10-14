"""Serialization contract tests for the Supply Directory API.

These tests assert the *response shape* of every audited endpoint (see
``docs/serialization-audit.md``): each route must expose exactly the fields its
consumers need, and must never leak internal or sensitive fields. They complement
the behaviour suites by pinning the wire contract.
"""


def _me(client, headers) -> dict:
    return client.get("/auth/me", headers=headers).json()


def _create_supplier(client, headers):
    return client.post(
        "/suppliers",
        headers=headers,
        json={
            "name": "Serialization Check S.L.",
            "country": "Spain",
            "categories": ["job_boards"],
            "monthly_rate": 250.0,
            "currency": "EUR",
            "status": "active",
            "notes": "Internal note that must stay on the detail view only.",
        },
    )


# --- Health -----------------------------------------------------------------


def test_health_endpoint_is_serialized(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "supplier-directory"}


# --- Auth / users -----------------------------------------------------------


def test_auth_me_returns_expected_shape_and_no_internal_fields(client, auth_headers):
    body = _me(client, auth_headers)

    # The caller's own email is allowed here; internal fields are not.
    assert set(body) == {"id", "email", "role", "profile"}
    for internal in ("uuid", "is_active", "created_at", "hashed_password"):
        assert internal not in body

    # The nested profile drops the internal owning FK.
    assert set(body["profile"]) == {"id", "name", "phone", "address"}


def test_user_detail_hides_uuid_and_password(client, auth_headers):
    user_id = _me(client, auth_headers)["id"]
    body = client.get(f"/users/{user_id}", headers=auth_headers).json()

    assert set(body) == {"id", "email", "role", "is_active", "created_at"}
    assert "uuid" not in body
    assert "hashed_password" not in body


def test_user_list_projection_is_slim(client, auth_headers):
    body = client.get("/users", headers=auth_headers).json()

    assert body  # the registered_user fixture guarantees at least one row
    for item in body:
        assert set(item) == {"id", "role", "is_active"}
        assert "email" not in item
        assert "uuid" not in item


def test_registration_response_hides_credentials_and_email(client):
    response = client.post(
        "/users",
        json={"email": "shape@nexova.com", "password": "valid-password-123"},
    )
    assert response.status_code == 201

    body = response.json()
    assert set(body) == {"id"}
    assert "email" not in body
    assert "hashed_password" not in body
    assert "password" not in body


# --- Suppliers --------------------------------------------------------------


def test_supplier_list_projection_omits_internal_fields(client, admin_headers):
    created = _create_supplier(client, admin_headers).json()

    listed = client.get("/suppliers", headers=admin_headers).json()
    item = next(record for record in listed if record["id"] == created["id"])

    assert set(item) == {
        "id",
        "name",
        "country",
        "categories",
        "monthly_rate",
        "currency",
        "status",
        "contract_renewal_date",
        "contact_email",
    }
    assert "notes" not in item
    assert "updated_at" not in item


def test_supplier_detail_includes_notes_and_updated_at(client, admin_headers):
    created = _create_supplier(client, admin_headers).json()

    detail = client.get(
        f"/suppliers/{created['id']}", headers=admin_headers
    ).json()

    # Detail keeps the full projection the list deliberately drops.
    assert "notes" in detail
    assert "updated_at" in detail
    assert detail["notes"] == "Internal note that must stay on the detail view only."


def test_supplier_create_generates_updated_at_server_side(client, admin_headers):
    response = client.post(
        "/suppliers",
        headers=admin_headers,
        json={
            "name": "Timestamp Guard S.L.",
            "country": "Spain",
            "categories": ["job_boards"],
            "monthly_rate": 100.0,
            "currency": "EUR",
            "status": "active",
            "updated_at": "2000-01-01T00:00:00+00:00",
        },
    )
    assert response.status_code == 201

    # A client-supplied updated_at is ignored; the server stamps its own.
    assert not response.json()["updated_at"].startswith("2000")


def test_delete_supplier_returns_message_shape(client, admin_headers):
    created = _create_supplier(client, admin_headers).json()

    response = client.delete(f"/suppliers/{created['id']}", headers=admin_headers)
    assert response.status_code == 200
    assert response.json() == {"detail": "Supplier deleted"}


def test_delete_user_returns_message_shape(client, auth_headers):
    user_id = _me(client, auth_headers)["id"]

    response = client.delete(f"/users/{user_id}", headers=auth_headers)
    assert response.status_code == 200
    assert response.json() == {"detail": "User deleted"}


# --- Failure ----------------------------------------------------------------


def test_supplier_list_requires_authentication(client):
    assert client.get("/suppliers").status_code == 401

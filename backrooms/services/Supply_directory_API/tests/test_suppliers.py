"""Endpoint tests for the supplier directory (``/suppliers``).

This is the core Nexova domain exposed by the backoffice: supplier records are
created and edited by admins/managers only, and the business rules (currency
must match country, categories are required, rate updates refresh ``updated_at``)
are asserted as decisions, not serialisation.
"""

VALID_CATEGORY = "job_boards"


def _supplier_payload(**overrides):
    payload = {
        "name": "Test Supplier",
        "country": "Spain",
        "categories": [VALID_CATEGORY],
        "monthly_rate": 1000.0,
        "currency": "EUR",
        "status": "active",
    }
    payload.update(overrides)
    return payload


def _create_supplier(client, headers, **overrides):
    return client.post("/suppliers", headers=headers, json=_supplier_payload(**overrides))


# --- Create -----------------------------------------------------------------


def test_create_supplier_succeeds_for_admin(client, admin_headers):
    response = _create_supplier(client, admin_headers)
    assert response.status_code == 201
    body = response.json()
    assert body["id"] is not None
    assert body["name"] == "Test Supplier"
    assert body["status"] == "active"


def test_create_supplier_succeeds_for_manager(client, manager_headers):
    assert _create_supplier(client, manager_headers).status_code == 201


def test_create_supplier_rejects_currency_country_mismatch(client, admin_headers):
    # Spain must use EUR, never USD.
    response = _create_supplier(client, admin_headers, country="Spain", currency="USD")
    assert response.status_code == 422


def test_create_supplier_rejects_empty_categories(client, admin_headers):
    assert _create_supplier(client, admin_headers, categories=[]).status_code == 422


def test_create_supplier_rejects_non_writer_role(client, auth_headers):
    # A plain `user` cannot create supplier records.
    assert _create_supplier(client, auth_headers).status_code == 403


def test_create_supplier_requires_authentication(client):
    response = client.post("/suppliers", json=_supplier_payload())
    assert response.status_code == 401


# --- List -------------------------------------------------------------------


def test_list_suppliers_returns_records(client, admin_headers):
    _create_supplier(client, admin_headers, name="First")
    _create_supplier(client, admin_headers, name="Second")

    response = client.get("/suppliers", headers=admin_headers)
    assert response.status_code == 200
    assert len(response.json()) == 2


def test_list_suppliers_filters_by_country(client, admin_headers):
    _create_supplier(client, admin_headers, name="Spain Co", country="Spain", currency="EUR")
    _create_supplier(client, admin_headers, name="USA Co", country="USA", currency="USD")

    response = client.get("/suppliers", headers=admin_headers, params={"country": "Spain"})
    names = [record["name"] for record in response.json()]
    assert names == ["Spain Co"]


def test_list_suppliers_filters_by_category(client, admin_headers):
    _create_supplier(client, admin_headers, name="Board Co", categories=["job_boards"])
    _create_supplier(client, admin_headers, name="ATS Co", categories=["ats_software"])

    response = client.get(
        "/suppliers", headers=admin_headers, params={"category": "ats_software"}
    )
    names = [record["name"] for record in response.json()]
    assert names == ["ATS Co"]


def test_list_suppliers_requires_authentication(client):
    assert client.get("/suppliers").status_code == 401


# --- Get by id --------------------------------------------------------------


def test_get_supplier_returns_record(client, admin_headers):
    created = _create_supplier(client, admin_headers).json()

    response = client.get(f"/suppliers/{created['id']}", headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["name"] == "Test Supplier"


def test_get_supplier_unknown_id_returns_404(client, admin_headers):
    assert client.get("/suppliers/9999", headers=admin_headers).status_code == 404


# --- Rate update ------------------------------------------------------------


def test_update_rate_refreshes_record(client, admin_headers):
    created = _create_supplier(client, admin_headers).json()

    response = client.patch(
        f"/suppliers/{created['id']}/rate",
        headers=admin_headers,
        json={"monthly_rate": 1500.0},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["monthly_rate"] == 1500.0
    assert body["updated_at"] != created["updated_at"]


def test_update_rate_rejects_non_positive_rate(client, admin_headers):
    created = _create_supplier(client, admin_headers).json()

    response = client.patch(
        f"/suppliers/{created['id']}/rate",
        headers=admin_headers,
        json={"monthly_rate": 0},
    )
    assert response.status_code == 422


def test_update_rate_rejects_non_writer(client, auth_headers, admin_headers):
    created = _create_supplier(client, admin_headers).json()

    response = client.patch(
        f"/suppliers/{created['id']}/rate",
        headers=auth_headers,
        json={"monthly_rate": 1500.0},
    )
    assert response.status_code == 403


# --- Status update ----------------------------------------------------------


def test_update_status_toggles_record(client, admin_headers):
    created = _create_supplier(client, admin_headers).json()

    response = client.patch(
        f"/suppliers/{created['id']}/status",
        headers=admin_headers,
        json={"status": "suspended"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "suspended"


def test_update_status_rejects_invalid_status(client, admin_headers):
    created = _create_supplier(client, admin_headers).json()

    response = client.patch(
        f"/suppliers/{created['id']}/status",
        headers=admin_headers,
        json={"status": "bogus"},
    )
    assert response.status_code == 422


def test_update_status_rejects_non_writer(client, auth_headers, admin_headers):
    created = _create_supplier(client, admin_headers).json()

    response = client.patch(
        f"/suppliers/{created['id']}/status",
        headers=auth_headers,
        json={"status": "suspended"},
    )
    assert response.status_code == 403


# --- Delete -----------------------------------------------------------------


def test_delete_supplier_removes_record(client, admin_headers):
    created = _create_supplier(client, admin_headers).json()

    assert client.delete(f"/suppliers/{created['id']}", headers=admin_headers).status_code == 200
    assert client.get(f"/suppliers/{created['id']}", headers=admin_headers).status_code == 404


def test_delete_supplier_unknown_id_returns_404(client, admin_headers):
    assert client.delete("/suppliers/9999", headers=admin_headers).status_code == 404


def test_delete_supplier_rejects_non_writer(client, auth_headers, admin_headers):
    created = _create_supplier(client, admin_headers).json()
    assert client.delete(f"/suppliers/{created['id']}", headers=auth_headers).status_code == 403

"""Behaviour tests for the Nexova inventory endpoints.

Three tiers per behaviour: happy path, edge case, failure case. Assertions check
business decisions (computed stock, rejection before write, recorded user UUID)
rather than transport details alone.
"""

from services.Supply_directory_API.auth.services import get_user_entry_by_email
from services.Supply_directory_API.database import get_db


def _inbound(client, headers, asset_id, quantity, office="Valencia"):
	return client.post(
		"/inventory/orders/inbound",
		headers=headers,
		json={
			"asset_id": asset_id,
			"quantity": quantity,
			"supplier": "TechDistrib Valencia S.L.",
			"office": office,
		},
	)


def _outbound(client, headers, asset_id, quantity, exit_type, assigned_to=None, office="Valencia"):
	payload = {
		"asset_id": asset_id,
		"quantity": quantity,
		"exit_type": exit_type,
		"office": office,
	}
	if assigned_to is not None:
		payload["assigned_to"] = assigned_to
	return client.post("/inventory/orders/outbound", headers=headers, json=payload)


def test_new_asset_starts_at_zero_stock(inventory_client, auth_headers, make_asset):
	asset = make_asset()
	assert asset["current_stock"] == 0

	fetched = inventory_client.get(f"/inventory/products/{asset['id']}")
	assert fetched.status_code == 200
	assert fetched.json()["current_stock"] == 0


def test_inbound_increases_stock_and_records_authenticated_uuid(
	inventory_client, auth_headers, registered_user, make_asset
):
	asset = make_asset()
	response = _inbound(inventory_client, auth_headers, asset["id"], 10)
	assert response.status_code == 201

	# ``uuid`` is internal (never returned by the API), so read it from storage.
	with get_db() as db:
		_, user = get_user_entry_by_email(db, registered_user["email"])
	assert response.json()["user_uuid"] == user.uuid

	listed = inventory_client.get("/inventory/products").json()
	stock = {item["id"]: item["current_stock"] for item in listed}[asset["id"]]
	assert stock == 10


def test_outbound_allocation_decrements_stock(inventory_client, auth_headers, make_asset):
	asset = make_asset()
	_inbound(inventory_client, auth_headers, asset["id"], 10)

	response = _outbound(
		inventory_client, auth_headers, asset["id"], 3, "allocation", "Javier Almeida"
	)
	assert response.status_code == 201
	assert response.json()["assigned_to"] == "Javier Almeida"

	product = inventory_client.get(f"/inventory/products/{asset['id']}").json()
	assert product["current_stock"] == 7


def test_consumption_with_null_assigned_to_is_allowed(inventory_client, auth_headers, make_asset):
	asset = make_asset()
	_inbound(inventory_client, auth_headers, asset["id"], 50)

	response = _outbound(inventory_client, auth_headers, asset["id"], 12, "consumption")
	assert response.status_code == 201
	assert response.json()["assigned_to"] is None

	product = inventory_client.get(f"/inventory/products/{asset['id']}").json()
	assert product["current_stock"] == 38


def test_consumption_with_assigned_to_is_rejected(inventory_client, auth_headers, make_asset):
	asset = make_asset()
	_inbound(inventory_client, auth_headers, asset["id"], 10)

	response = _outbound(
		inventory_client, auth_headers, asset["id"], 1, "consumption", "Elena Vargas"
	)
	assert response.status_code == 422


def test_allocation_without_assigned_to_is_rejected(inventory_client, auth_headers, make_asset):
	asset = make_asset()
	_inbound(inventory_client, auth_headers, asset["id"], 10)

	response = _outbound(inventory_client, auth_headers, asset["id"], 1, "allocation")
	assert response.status_code == 422


def test_insufficient_stock_is_rejected_before_write(inventory_client, auth_headers, make_asset):
	asset = make_asset(name="Ergonomic mouse", category="peripherals")
	_inbound(inventory_client, auth_headers, asset["id"], 5)

	orders_before = len(inventory_client.get("/inventory/orders").json())

	response = _outbound(
		inventory_client, auth_headers, asset["id"], 6, "allocation", "Javier Almeida"
	)
	assert response.status_code == 400
	assert response.json()["detail"] == (
		"Insufficient stock for asset 'Ergonomic mouse'. Available: 5, requested: 6."
	)

	# No exit row may be persisted when the request is rejected.
	assert len(inventory_client.get("/inventory/orders").json()) == orders_before
	product = inventory_client.get(f"/inventory/products/{asset['id']}").json()
	assert product["current_stock"] == 5


def test_duplicate_sku_returns_conflict(inventory_client, auth_headers, make_asset):
	asset = make_asset(sku="NXV-IT-001")

	response = inventory_client.post(
		"/inventory/products",
		headers=auth_headers,
		json={
			"name": "Duplicate laptop",
			"sku": "NXV-IT-001",
			"category": "hardware",
			"office": "Miami",
		},
	)
	assert response.status_code == 409
	assert "NXV-IT-001" in response.json()["detail"]
	assert asset["id"]


def test_get_unknown_asset_returns_not_found(inventory_client):
	assert inventory_client.get("/inventory/products/999999").status_code == 404


def test_unknown_asset_on_inbound_returns_not_found(inventory_client, auth_headers):
	response = _inbound(inventory_client, auth_headers, 999999, 1)
	assert response.status_code == 404


def test_writes_require_authentication(inventory_client, make_asset, auth_headers):
	asset = make_asset()

	created = inventory_client.post(
		"/inventory/products",
		json={"name": "No auth", "sku": "NXV-NA-001", "category": "hardware", "office": "Miami"},
	)
	assert created.status_code == 401

	inbound = inventory_client.post(
		"/inventory/orders/inbound",
		json={
			"asset_id": asset["id"],
			"quantity": 1,
			"supplier": "X",
			"office": "Valencia",
		},
	)
	assert inbound.status_code == 401

	outbound = inventory_client.post(
		"/inventory/orders/outbound",
		json={
			"asset_id": asset["id"],
			"quantity": 1,
			"exit_type": "consumption",
			"office": "Valencia",
		},
	)
	assert outbound.status_code == 401


def test_both_offices_coexist_and_stock_is_per_asset(
	inventory_client, auth_headers, make_asset
):
	valencia = make_asset(name='Laptop 14" Business', office="Valencia")
	miami = make_asset(name='Laptop 14" Business', office="Miami")

	_inbound(inventory_client, auth_headers, valencia["id"], 15, office="Valencia")
	_inbound(inventory_client, auth_headers, miami["id"], 4, office="Miami")

	products = inventory_client.get("/inventory/products").json()
	by_id = {item["id"]: item for item in products}
	assert by_id[valencia["id"]]["current_stock"] == 15
	assert by_id[miami["id"]]["current_stock"] == 4
	assert by_id[valencia["id"]]["office"] == "Valencia"
	assert by_id[miami["id"]]["office"] == "Miami"


def test_orders_list_includes_asset_data(inventory_client, auth_headers, make_asset):
	asset = make_asset(name="USB-C Hub", category="peripherals", office="Miami")
	_inbound(inventory_client, auth_headers, asset["id"], 15, office="Miami")
	_outbound(
		inventory_client, auth_headers, asset["id"], 2, "allocation", "Roberto Díaz", office="Miami"
	)

	orders = inventory_client.get("/inventory/orders").json()
	kinds = {order["kind"] for order in orders}
	assert kinds == {"inbound", "outbound"}
	for order in orders:
		assert order["asset_name"] == "USB-C Hub"
		assert order["asset_sku"] == asset["sku"]
		assert order["user_uuid"]


def test_order_write_invalidates_products_cache(inventory_client, auth_headers, make_asset):
	asset = make_asset()
	_inbound(inventory_client, auth_headers, asset["id"], 10)

	# Populate the products cache with the current stock.
	first_list = inventory_client.get("/inventory/products").json()
	by_id = {item["id"]: item["current_stock"] for item in first_list}
	assert by_id[asset["id"]] == 10

	# A second inbound must be reflected on the next read (cache invalidated).
	_inbound(inventory_client, auth_headers, asset["id"], 5)

	second_list = inventory_client.get("/inventory/products").json()
	relisted_by_id = {item["id"]: item["current_stock"] for item in second_list}
	assert relisted_by_id[asset["id"]] == 15

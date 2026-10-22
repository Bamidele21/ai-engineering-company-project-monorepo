"""Business-event coverage for the mandatory Nexova inventory telemetry."""

import pytest

from routers import inventory as inventory_routes


@pytest.fixture()
def captured(monkeypatch):
	events = []

	def fake_emit(event_type, properties, *, request=None, user_id=None, queue=None):
		events.append({"event_type": event_type, "properties": properties})

	monkeypatch.setattr(inventory_routes, "emit_inventory_event", fake_emit)
	return events


def _inbound(
	client,
	headers,
	asset_id,
	quantity,
	*,
	office="Valencia",
	unit_cost=10.0,
	supplier="PrintWorks Valencia S.L.",
):
	return client.post(
		"/inventory/orders/inbound",
		headers=headers,
		json={
			"asset_id": asset_id,
			"quantity": quantity,
			"supplier": supplier,
			"office": office,
			"unit_cost": unit_cost,
			"currency": "EUR" if office == "Valencia" else "USD",
		},
	)


def _outbound(
	client,
	headers,
	asset_id,
	quantity,
	*,
	exit_type="allocation",
	assigned_to="Elena Vargas",
	office="Valencia",
):
	payload = {
		"asset_id": asset_id,
		"quantity": quantity,
		"exit_type": exit_type,
		"office": office,
	}
	if assigned_to is not None:
		payload["assigned_to"] = assigned_to
	return client.post("/inventory/orders/outbound", headers=headers, json=payload)


def test_inbound_emits_the_confirmed_order_fact(
	inventory_client, auth_headers, make_asset, captured
):
	asset = make_asset(
		name="Leadership training workbook",
		category="training_kit",
		office="Valencia",
		min_stock=10,
	)

	response = _inbound(
		inventory_client,
		auth_headers,
		asset["id"],
		40,
		unit_cost=12.5,
	)

	assert response.status_code == 201
	assert [event["event_type"] for event in captured] == ["inbound_order_created"]
	properties = captured[0]["properties"]
	assert properties["office"] == "valencia"
	assert properties["product_id"] == asset["id"]
	assert properties["product_category"] == "training_kit"
	assert properties["programme_id"] == "test-programme"
	assert properties["quantity"] == 40
	assert properties["currency"] == "EUR"
	assert properties["supplier"] == "PrintWorks Valencia S.L."
	assert properties["unit_cost"] == 12.5
	assert properties["order_id"] == response.json()["id"]


def test_first_purchase_has_no_cost_variance_comparison(
	inventory_client, auth_headers, make_asset, captured
):
	asset = make_asset()
	_inbound(inventory_client, auth_headers, asset["id"], 10, unit_cost=10.0)

	assert [event["event_type"] for event in captured] == ["inbound_order_created"]


def test_outbound_emits_created_and_threshold_on_crossing(
	inventory_client, auth_headers, make_asset, captured
):
	asset = make_asset(min_stock=5)
	_inbound(inventory_client, auth_headers, asset["id"], 10)
	captured.clear()

	response = _outbound(inventory_client, auth_headers, asset["id"], 6)

	assert response.status_code == 201
	types = [event["event_type"] for event in captured]
	assert types == ["outbound_order_created", "stock_threshold_triggered"]
	outbound = captured[0]["properties"]
	assert outbound["quantity"] == 6
	assert outbound["exit_type"] == "allocation"
	assert "assigned_to" not in outbound
	threshold = captured[1]["properties"]
	assert threshold["previous_stock"] == 10
	assert threshold["min_stock"] == 5
	assert threshold["quantity"] == 4
	assert threshold["currency"] == "EUR"


def test_threshold_is_edge_triggered_at_equality(
	inventory_client, auth_headers, make_asset, captured
):
	asset = make_asset(min_stock=5)
	_inbound(inventory_client, auth_headers, asset["id"], 5)
	captured.clear()

	_outbound(inventory_client, auth_headers, asset["id"], 1)

	threshold = [
		event for event in captured if event["event_type"] == "stock_threshold_triggered"
	]
	assert len(threshold) == 1
	assert threshold[0]["properties"]["previous_stock"] == 5
	assert threshold[0]["properties"]["quantity"] == 4


def test_threshold_does_not_fire_when_stock_was_already_below(
	inventory_client, auth_headers, make_asset, captured
):
	asset = make_asset(min_stock=5)
	_inbound(inventory_client, auth_headers, asset["id"], 4)
	captured.clear()

	_outbound(inventory_client, auth_headers, asset["id"], 1)

	types = [event["event_type"] for event in captured]
	assert "stock_threshold_triggered" not in types


def test_cost_variance_requires_more_than_ten_percent(
	inventory_client, auth_headers, make_asset, captured
):
	asset = make_asset()
	_inbound(inventory_client, auth_headers, asset["id"], 10, unit_cost=10.0)
	captured.clear()

	_inbound(inventory_client, auth_headers, asset["id"], 10, unit_cost=11.0)
	assert [event["event_type"] for event in captured] == ["inbound_order_created"]

	captured.clear()
	_inbound(inventory_client, auth_headers, asset["id"], 10, unit_cost=12.0)

	types = [event["event_type"] for event in captured]
	assert types == ["inbound_order_created", "kit_cost_variance_detected"]
	variance = captured[1]["properties"]
	assert variance["historical_avg_cost"] == 10.5
	assert variance["variance_percent"] == 14.29
	assert variance["unit_cost"] == 12.0


def test_outbound_rejection_emits_before_the_400(
	inventory_client, auth_headers, make_asset, captured
):
	asset = make_asset(min_stock=10)
	_inbound(inventory_client, auth_headers, asset["id"], 5)
	captured.clear()

	response = _outbound(inventory_client, auth_headers, asset["id"], 6)

	assert response.status_code == 400
	assert [event["event_type"] for event in captured] == ["outbound_order_rejected"]
	properties = captured[0]["properties"]
	assert properties["available_stock"] == 5
	assert properties["quantity"] == 6
	assert properties["exit_type"] == "allocation"
	assert "assigned_to" not in properties


def test_direct_item_edit_is_rejected_and_captured(
	inventory_client, auth_headers, make_asset, captured
):
	asset = make_asset()
	captured.clear()

	response = inventory_client.put(
		f"/inventory/products/{asset['id']}",
		headers=auth_headers,
		json={"current_stock": 999},
	)

	assert response.status_code == 405
	properties = captured[0]["properties"]
	assert captured[0]["event_type"] == "direct_stock_edit_rejected"
	assert properties["office"] == "valencia"
	assert properties["product_id"] == asset["id"]
	assert properties["product_category"] == "certification"
	assert properties["programme_id"] == "test-programme"
	assert properties["quantity"] is None
	assert properties["currency"] == "EUR"
	assert properties["method"] == "PUT"
	assert properties["path"] == "/inventory/products/{id}"


def test_direct_collection_edit_uses_nullable_dimensions(
	inventory_client, auth_headers, captured
):
	response = inventory_client.delete("/inventory/products", headers=auth_headers)

	assert response.status_code == 405
	properties = captured[0]["properties"]
	assert properties["product_id"] is None
	assert properties["office"] is None
	assert properties["quantity"] is None
	assert properties["path"] == "/inventory/products"
	assert properties["method"] == "DELETE"


def test_direct_edit_of_unknown_asset_keeps_the_numeric_target(
	inventory_client, auth_headers, captured
):
	response = inventory_client.patch(
		"/inventory/products/999999",
		headers=auth_headers,
		json={"current_stock": 1},
	)

	assert response.status_code == 405
	properties = captured[0]["properties"]
	assert properties["product_id"] == 999999
	assert properties["office"] is None
	assert properties["product_category"] is None
	assert properties["programme_id"] is None
	assert properties["path"] == "/inventory/products/{id}"


def test_one_inbound_action_emits_one_business_fact(
	inventory_client, auth_headers, make_asset, captured
):
	asset = make_asset()
	_inbound(inventory_client, auth_headers, asset["id"], 10)

	inbound_events = [
		event for event in captured if event["event_type"] == "inbound_order_created"
	]
	assert len(inbound_events) == 1


def test_currency_must_match_the_office(
	inventory_client, auth_headers, make_asset, captured
):
	asset = make_asset(office="Valencia")

	response = inventory_client.post(
		"/inventory/orders/inbound",
		headers=auth_headers,
		json={
			"asset_id": asset["id"],
			"quantity": 1,
			"supplier": "PrintWorks Valencia S.L.",
			"office": "Valencia",
			"unit_cost": 10.0,
			"currency": "USD",
		},
	)

	assert response.status_code == 422
	assert captured == []

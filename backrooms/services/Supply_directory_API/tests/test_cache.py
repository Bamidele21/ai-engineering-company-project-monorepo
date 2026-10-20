"""Tests for the in-memory TTL cache and its route-level invalidation.

Three tiers per behaviour (happy, edge, failure) for the ``TtlCache`` unit, plus
one integration test proving a supplier write clears the cached list so a later
read never returns stale data.
"""

from services.cache import TtlCache


def _supplier_payload(**overrides):
    payload = {
        "name": "Cache Test Supplier",
        "country": "Spain",
        "categories": ["job_boards"],
        "monthly_rate": 1000.0,
        "currency": "EUR",
        "status": "active",
    }
    payload.update(overrides)
    return payload


# --- TtlCache unit behaviour -------------------------------------------------


def test_set_then_get_returns_value():
    cache = TtlCache()
    cache.set("key", {"a": 1}, ttl=60)
    assert cache.get("key") == {"a": 1}


def test_missing_key_returns_none():
    cache = TtlCache()
    assert cache.get("missing") is None


def test_expired_entry_returns_none():
    # A zero TTL is already expired at the moment of lookup.
    cache = TtlCache()
    cache.set("key", "value", ttl=0)
    assert cache.get("key") is None
    assert cache.get("key") is None


def test_overwrite_replaces_value_and_refreshes_entry():
    cache = TtlCache()
    cache.set("key", "old", ttl=60)
    cache.set("key", "new", ttl=60)
    assert cache.get("key") == "new"


def test_invalidate_removes_matching_prefix_only():
    cache = TtlCache()
    cache.set("suppliers:Spain:", 1, ttl=60)
    cache.set("suppliers:USA:", 2, ttl=60)
    cache.set("inventory:products", 3, ttl=60)

    cache.invalidate("suppliers:")

    assert cache.get("suppliers:Spain:") is None
    assert cache.get("suppliers:USA:") is None
    assert cache.get("inventory:products") == 3


def test_clear_removes_every_entry():
    cache = TtlCache()
    cache.set("a", 1, ttl=60)
    cache.set("b", 2, ttl=60)
    cache.clear()
    assert cache.get("a") is None
    assert cache.get("b") is None


# --- Route-level invalidation -------------------------------------------------


def test_supplier_rate_update_invalidates_list_cache(client, admin_headers):
    created = client.post("/suppliers", headers=admin_headers, json=_supplier_payload())
    assert created.status_code == 201
    supplier_id = created.json()["id"]

    # Populate the list cache with the pre-update rate.
    first_list = client.get("/suppliers", headers=admin_headers)
    assert first_list.status_code == 200

    patched = client.patch(
        f"/suppliers/{supplier_id}/rate",
        headers=admin_headers,
        json={"monthly_rate": 1234.5},
    )
    assert patched.status_code == 200

    # The second read must reflect the write, proving the cache was invalidated.
    second_list = client.get("/suppliers", headers=admin_headers)
    by_id = {supplier["id"]: supplier for supplier in second_list.json()}
    assert by_id[supplier_id]["monthly_rate"] == 1234.5

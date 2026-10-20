"""Unit tests for the authentication service layer in ``auth/services.py``.

These exercise the business logic behind registration, password management,
and the reset-token lifecycle directly against TinyDB, complementing the
endpoint tests with finer-grained edge cases.
"""

from datetime import datetime, timedelta, timezone

import pytest

from services.Supply_directory_API.auth import security
from services.Supply_directory_API.auth.services import (
    change_password,
    consume_password_reset,
    create_password_reset,
    create_user,
    delete_user,
    get_password_reset_by_jti,
    get_profile_by_user_id,
    get_user_by_email,
    get_user_by_id,
    get_user_entry_by_email,
    set_password,
    update_profile,
    update_user,
)
from services.Supply_directory_API.database import (
    get_password_resets_db,
    get_password_resets_table,
    get_profiles_table,
)
from services.Supply_directory_API.models import ProfileUpdate, UserCreate, UserUpdate


def _create(db, email="svc@nexova.com", password="service-password-123"):
    return create_user(
        db, UserCreate(email=email, password=password, name="Service User")
    )


# --- create_user ------------------------------------------------------------


def test_create_user_returns_id_and_hashes_password(db):
    user_id = _create(db)
    user = get_user_by_id(db, user_id)
    assert user is not None
    assert user.email == "svc@nexova.com"
    assert security.verify_password("service-password-123", user.hashed_password)


def test_create_user_links_a_profile(db):
    user_id = _create(db)
    assert get_profile_by_user_id(db, user_id) is not None


def test_create_user_rejects_duplicate_email(db):
    _create(db)
    with pytest.raises(ValueError):
        _create(db)


# --- User lookups -----------------------------------------------------------


def test_get_user_by_email_matches_case_insensitively(db):
    _create(db)
    assert get_user_by_email(db, "SVC@nexova.com") is not None


def test_get_user_entry_by_email_returns_none_for_unknown(db):
    assert get_user_entry_by_email(db, "ghost@nexova.com") is None


def test_get_user_by_id_returns_none_for_unknown(db):
    assert get_user_by_id(db, 9999) is None


# --- Reset token lifecycle --------------------------------------------------


def test_create_password_reset_persists_unused_record(db):
    user_id = _create(db)
    token, expires_in = create_password_reset(user_id)
    _, jti = security.decode_password_reset_token(token)

    entry = get_password_reset_by_jti(jti)
    assert entry is not None
    assert entry[1].used is False
    assert expires_in > 0
    assert token


def test_consume_password_reset_marks_token_used(db):
    user_id = _create(db)
    token, _ = create_password_reset(user_id)
    _, jti = security.decode_password_reset_token(token)

    assert consume_password_reset(jti, user_id) is True
    assert get_password_reset_by_jti(jti)[1].used is True


def test_consume_password_reset_rejects_unknown_jti(db):
    assert consume_password_reset("does-not-exist", 1) is False


def test_consume_password_reset_rejects_wrong_user(db):
    user_id = _create(db)
    other_id = _create(db, email="other@nexova.com")
    token, _ = create_password_reset(user_id)
    _, jti = security.decode_password_reset_token(token)

    assert consume_password_reset(jti, other_id) is False


def test_consume_password_reset_rejects_expired_token(db):
    user_id = _create(db)
    token, _ = create_password_reset(user_id)
    _, jti = security.decode_password_reset_token(token)

    doc_id, _ = get_password_reset_by_jti(jti)
    with get_password_resets_db() as reset_db:
        get_password_resets_table(reset_db).update(
            {
                "expires_at": (
                    datetime.now(timezone.utc) - timedelta(minutes=5)
                ).isoformat()
            },
            doc_ids=[doc_id],
        )

    assert consume_password_reset(jti, user_id) is False


# --- Password management ----------------------------------------------------


def test_set_password_replaces_hash(db):
    user_id = _create(db)
    assert set_password(db, user_id, "new-password-456") is True

    user = get_user_by_id(db, user_id)
    assert security.verify_password("new-password-456", user.hashed_password)


def test_set_password_rejects_unknown_user(db):
    assert set_password(db, 9999, "new-password-456") is False


def test_change_password_verifies_current_password(db):
    user_id = _create(db)
    assert change_password(db, user_id, "service-password-123", "new-password-456") is True
    assert change_password(db, user_id, "wrong-current", "new-password-789") is False


def test_change_password_rejects_unknown_user(db):
    assert change_password(db, 9999, "whatever", "new-password-456") is False


# --- User / profile updates -------------------------------------------------


def test_update_user_changes_email(db):
    user_id = _create(db)
    updated = update_user(db, user_id, UserUpdate(email="renamed@nexova.com"))
    assert updated is not None
    assert updated.email == "renamed@nexova.com"


def test_update_user_rejects_taken_email(db):
    _create(db)
    other_id = _create(db, email="other@nexova.com")
    with pytest.raises(ValueError):
        update_user(db, other_id, UserUpdate(email="svc@nexova.com"))


def test_update_user_returns_none_for_unknown(db):
    assert update_user(db, 9999, UserUpdate(email="x@nexova.com")) is None


def test_update_profile_creates_when_missing(db):
    user_id = _create(db)
    profile_id, _ = get_profile_by_user_id(db, user_id)
    get_profiles_table(db).remove(doc_ids=[profile_id])

    new_profile_id, profile = update_profile(db, user_id, ProfileUpdate(name="Recreated"))
    assert profile.name == "Recreated"
    assert new_profile_id is not None


def test_update_profile_updates_existing(db):
    user_id = _create(db)
    _, profile = update_profile(db, user_id, ProfileUpdate(name="Updated Name"))
    assert profile.name == "Updated Name"


# --- delete_user ------------------------------------------------------------


def test_delete_user_removes_user_and_profile(db):
    user_id = _create(db)
    assert delete_user(db, user_id) is True
    assert get_user_by_id(db, user_id) is None
    assert get_profile_by_user_id(db, user_id) is None


def test_delete_user_returns_false_for_unknown(db):
    assert delete_user(db, 9999) is False

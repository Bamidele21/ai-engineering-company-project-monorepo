"""Unit tests for the authentication primitives in ``auth/security.py``.

These exercise the token and password business logic directly (the exact logic
that regressed in the incident behind AUTH-088), without going through HTTP.
"""

from datetime import datetime, timedelta, timezone

import pytest
from jose import jwt

from services.Supply_directory_API.auth import security


# --- Password hashing -------------------------------------------------------


def test_hash_password_produces_bcrypt_hash():
    hashed = security.hash_password("correct-horse-battery-staple")
    assert hashed.startswith("$2")
    assert "correct-horse-battery-staple" not in hashed


def test_verify_password_accepts_matching_password():
    hashed = security.hash_password("correct-horse-battery-staple")
    assert security.verify_password("correct-horse-battery-staple", hashed) is True


def test_verify_password_rejects_wrong_password():
    hashed = security.hash_password("correct-horse-battery-staple")
    assert security.verify_password("wrong-password", hashed) is False


def test_hash_password_is_salted():
    # Two hashes of the same password must differ (bcrypt salts each hash).
    first = security.hash_password("same-password")
    second = security.hash_password("same-password")
    assert first != second


# --- Access tokens ----------------------------------------------------------


def test_create_access_token_round_trips_user_id():
    token, expires_in = security.create_access_token(user_id=42)
    assert security.decode_access_token(token) == 42
    assert expires_in == security.token_expiry_minutes() * 60


def test_access_token_expires_after_window():
    secret = security._jwt_secret()
    expired = jwt.encode(
        {"sub": "42", "exp": datetime.now(timezone.utc) - timedelta(minutes=1)},
        secret,
        algorithm=security.JWT_ALGORITHM,
    )
    with pytest.raises(ValueError):
        security.decode_access_token(expired)


def test_decode_access_token_rejects_malformed_token():
    with pytest.raises(ValueError):
        security.decode_access_token("not-a-jwt")


def test_decode_access_token_rejects_missing_subject():
    secret = security._jwt_secret()
    token = jwt.encode(
        {"exp": datetime.now(timezone.utc) + timedelta(minutes=5)},
        secret,
        algorithm=security.JWT_ALGORITHM,
    )
    with pytest.raises(ValueError):
        security.decode_access_token(token)


# --- Password reset tokens --------------------------------------------------


def test_create_reset_token_round_trips_user_id_and_jti():
    token, jti, expires_in = security.create_password_reset_token(user_id=7)
    decoded_user_id, decoded_jti = security.decode_password_reset_token(token)
    assert decoded_user_id == 7
    assert decoded_jti == jti
    assert expires_in == security.password_reset_expiry_minutes() * 60


def test_reset_token_rejects_access_token_type():
    access_token, _ = security.create_access_token(user_id=7)
    with pytest.raises(ValueError):
        security.decode_password_reset_token(access_token)


def test_reset_token_rejects_missing_jti():
    secret = security._jwt_secret()
    token = jwt.encode(
        {
            "sub": "7",
            "type": security.PASSWORD_RESET_TOKEN_TYPE,
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
        },
        secret,
        algorithm=security.JWT_ALGORITHM,
    )
    with pytest.raises(ValueError):
        security.decode_password_reset_token(token)


def test_reset_token_rejects_malformed_token():
    with pytest.raises(ValueError):
        security.decode_password_reset_token("garbage")


# --- Expiry configuration ---------------------------------------------------


def test_expiry_defaults_are_read_from_environment():
    # conftest sets JWT_EXPIRY_MINUTES and PASSWORD_RESET_EXPIRY_MINUTES to 30.
    assert security.token_expiry_minutes() == 30
    assert security.password_reset_expiry_minutes() == 30

"""Automated coverage for AUTH-03 password recovery and change.

Runs against an isolated temporary TinyDB so the tracked ``suppliers_db.json``
and the local ``password_resets_db.json`` are never touched. The Resend call is
stubbed, so no real email is sent and no API key is required.

Run from ``backrooms/services``::

	uv run python Supply_directory_API/tests/test_password_recovery.py
"""

import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path


os.environ.setdefault("JWT_SECRET_KEY", "test-secret-for-password-recovery")
os.environ.setdefault("JWT_EXPIRY_MINUTES", "30")
os.environ.setdefault("PASSWORD_RESET_EXPIRY_MINUTES", "30")
os.environ.setdefault("PASSWORD_RESET_URL", "http://localhost:3000/reset-password")

BACKROOMS_ROOT = Path(__file__).resolve().parents[3]
if str(BACKROOMS_ROOT) not in sys.path:
	sys.path.insert(0, str(BACKROOMS_ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from services.Supply_directory_API import database  # noqa: E402
from services.Supply_directory_API.auth import security  # noqa: E402
from services.Supply_directory_API.auth.services import get_password_reset_by_jti  # noqa: E402
from services.Supply_directory_API.database import (  # noqa: E402
	get_db,
	get_password_resets_db,
	get_password_resets_table,
	get_users_table,
)
from services.Supply_directory_API.main import app  # noqa: E402
from services.Supply_directory_API.routes import auth as auth_routes  # noqa: E402


PASSWORD = "initial-password-123"
NEW_PASSWORD = "brand-new-password-456"
UPDATED_PASSWORD = "changed-again-789"

_results: list[tuple[str, bool, str]] = []


def check(name: str, condition: bool, detail: str = "") -> None:
	_results.append((name, bool(condition), detail))
	status = "PASS" if condition else "FAIL"
	print(f"[{status}] {name}{(' - ' + detail) if detail and not condition else ''}")


def _register(client: TestClient, email: str) -> None:
	response = client.post(
		"/users",
		json={"email": email, "password": PASSWORD, "name": "Reset Tester"},
	)
	check(f"register {email} returns 201", response.status_code == 201, str(response.text))


def _login(client: TestClient, email: str, password: str):
	return client.post("/auth/login", json={"email": email, "password": password})


def _extract_token(reset_url: str) -> str:
	return reset_url.split("token=", 1)[1]


def run() -> int:
	email = "recovery@nexova.com"
	sent_emails: list[dict] = []

	def fake_send(to_email: str, token: str, expires_in_minutes: int) -> None:
		sent_emails.append(
			{
				"to": to_email,
				"token": token,
				"expires_in_minutes": expires_in_minutes,
			}
		)

	with tempfile.TemporaryDirectory() as tmp:
		tmp_path = Path(tmp)
		database.DB_PATH = tmp_path / "suppliers_db.json"
		database.PASSWORD_RESETS_DB_PATH = tmp_path / "password_resets_db.json"

		original_sender = auth_routes.send_password_reset_email
		auth_routes.send_password_reset_email = (
			lambda to_email, token, expires_in_minutes: fake_send(
				to_email, token, expires_in_minutes
			)
		)

		try:
			with TestClient(app) as client:
				_register(client, email)

				# Enumeration resistance: unknown email still returns 200 and sends nothing.
				sent_emails.clear()
				unknown = client.post(
					"/auth/forgot-password", json={"email": "nobody@nexova.com"}
				)
				check(
					"forgot-password unknown email returns 200",
					unknown.status_code == 200,
					unknown.text,
				)
				check("no email sent for unknown address", len(sent_emails) == 0)

				# Registered email triggers exactly one send with a 15-60 minute expiry.
				known = client.post("/auth/forgot-password", json={"email": email})
				check(
					"forgot-password known email returns 200",
					known.status_code == 200,
					known.text,
				)
				check("reset email queued for registered address", len(sent_emails) == 1)
				check(
					"reset link expiry within 15-60 minutes",
					bool(sent_emails) and 15 <= sent_emails[0]["expires_in_minutes"] <= 60,
				)

				token = sent_emails[0]["token"]
				user_id, jti = security.decode_password_reset_token(token)
				check("reset token decodes with user id and jti", isinstance(jti, str) and bool(jti))

				# An access token must not be accepted as a reset token.
				access = _login(client, email, PASSWORD)
				access_token = access.json()["access_token"]
				type_confusion = client.post(
					"/auth/reset-password",
					json={"token": access_token, "new_password": NEW_PASSWORD},
				)
				check(
					"access token rejected as reset token (400)",
					type_confusion.status_code == 400,
					type_confusion.text,
				)

				# Happy path reset.
				reset = client.post(
					"/auth/reset-password",
					json={"token": token, "new_password": NEW_PASSWORD},
				)
				check("reset-password succeeds with valid token", reset.status_code == 200, reset.text)

				check("old password rejected after reset", _login(client, email, PASSWORD).status_code == 401)
				check(
					"new password accepted after reset",
					_login(client, email, NEW_PASSWORD).status_code == 200,
				)

				# Single use: same token cannot be replayed.
				replay = client.post(
					"/auth/reset-password",
					json={"token": token, "new_password": UPDATED_PASSWORD},
				)
				check("used reset token rejected (400)", replay.status_code == 400, replay.text)

				# Expiry: expire the persisted record, then attempt the reset.
				sent_emails.clear()
				client.post("/auth/forgot-password", json={"email": email})
				expiring_token = sent_emails[0]["token"]
				_, expiring_jti = security.decode_password_reset_token(expiring_token)
				entry = get_password_reset_by_jti(expiring_jti)
				doc_id = entry[0]
				with get_password_resets_db() as db:
					get_password_resets_table(db).update(
						{"expires_at": (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()},
						doc_ids=[doc_id],
					)
				expired = client.post(
					"/auth/reset-password",
					json={"token": expiring_token, "new_password": UPDATED_PASSWORD},
				)
				check("expired reset token rejected (400)", expired.status_code == 400, expired.text)

				# Malformed token.
				malformed = client.post(
					"/auth/reset-password",
					json={"token": "not-a-jwt", "new_password": UPDATED_PASSWORD},
				)
				check("malformed reset token rejected (400)", malformed.status_code == 400)

				# Change password requires a session.
				anonymous = client.post(
					"/auth/change-password",
					json={
						"current_password": NEW_PASSWORD,
						"new_password": UPDATED_PASSWORD,
					},
				)
				check("unauthenticated change-password returns 401", anonymous.status_code == 401)

				login_now = _login(client, email, NEW_PASSWORD)
				headers = {"Authorization": f"Bearer {login_now.json()['access_token']}"}

				wrong_current = client.post(
					"/auth/change-password",
					headers=headers,
					json={
						"current_password": "definitely-wrong",
						"new_password": UPDATED_PASSWORD,
					},
				)
				check(
					"wrong current password rejected (400)",
					wrong_current.status_code == 400,
					wrong_current.text,
				)

				changed = client.post(
					"/auth/change-password",
					headers=headers,
					json={
						"current_password": NEW_PASSWORD,
						"new_password": UPDATED_PASSWORD,
					},
				)
				check("change-password succeeds with correct current", changed.status_code == 200, changed.text)
				check(
					"updated password accepted at login",
					_login(client, email, UPDATED_PASSWORD).status_code == 200,
				)

				# Hash check: stored value is bcrypt, never plaintext.
				with get_db() as db:
					stored = get_users_table(db).all()[0]["hashed_password"]
				check(
					"password stored as bcrypt hash",
					stored.startswith("$2") and UPDATED_PASSWORD not in stored,
				)
		finally:
			auth_routes.send_password_reset_email = original_sender

	failures = [name for name, ok, _ in _results if not ok]
	print(f"\n{len(_results) - len(failures)}/{len(_results)} checks passed")
	if failures:
		print("FAILED:", ", ".join(failures))
		return 1
	return 0


if __name__ == "__main__":
	raise SystemExit(run())

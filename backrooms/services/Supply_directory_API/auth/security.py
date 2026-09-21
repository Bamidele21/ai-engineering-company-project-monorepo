import os
from  dotenv import load_dotenv
load_dotenv()
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from jose import JWTError, jwt
from passlib.hash import bcrypt


JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
DEFAULT_EXPIRY_MINUTES = int(os.getenv("JWT_EXPIRY_MINUTES", "30"))
DEFAULT_PASSWORD_RESET_EXPIRY_MINUTES = int(
	os.getenv("PASSWORD_RESET_EXPIRY_MINUTES", "30")
)
PASSWORD_RESET_TOKEN_TYPE = "password_reset"


def _jwt_secret() -> str:
	secret = os.getenv("JWT_SECRET_KEY")
	if not secret:
		raise RuntimeError("JWT_SECRET_KEY must be configured")
	return secret


def token_expiry_minutes() -> int:
	return int(os.getenv("JWT_EXPIRY_MINUTES", str(DEFAULT_EXPIRY_MINUTES)))


def hash_password(password: str) -> str:
	return bcrypt.using(rounds=12).hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
	return bcrypt.verify(password, hashed_password)


def create_access_token(user_id: int) -> tuple[str, int]:
	expires_in = token_expiry_minutes() * 60
	expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
	payload = {"sub": str(user_id), "exp": expires_at}
	return jwt.encode(payload, _jwt_secret(), algorithm=JWT_ALGORITHM ), expires_in


def decode_access_token(token: str) -> int:
	try:
		payload = jwt.decode(token, _jwt_secret(), algorithms=[JWT_ALGORITHM])
		user_id = payload.get("sub")
		if user_id is None:
			raise ValueError("Token subject is missing")
		return int(user_id)
	except (JWTError, TypeError, ValueError) as exc:
		raise ValueError("Invalid authentication token") from exc


def password_reset_expiry_minutes() -> int:
	value = int(
		os.getenv(
			"PASSWORD_RESET_EXPIRY_MINUTES",
			str(DEFAULT_PASSWORD_RESET_EXPIRY_MINUTES),
		)
	)
	if value < 15 or value > 60:
		raise RuntimeError("PASSWORD_RESET_EXPIRY_MINUTES must be between 15 and 60")
	return value


def create_password_reset_token(user_id: int) -> tuple[str, str, int]:
	expires_in = password_reset_expiry_minutes() * 60
	expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
	jti = str(uuid4())
	payload = {
		"sub": str(user_id),
		"exp": expires_at,
		"type": PASSWORD_RESET_TOKEN_TYPE,
		"jti": jti,
	}
	token = jwt.encode(payload, _jwt_secret(), algorithm=JWT_ALGORITHM)
	return token, jti, expires_in


def decode_password_reset_token(token: str) -> tuple[int, str]:
	try:
		payload = jwt.decode(token, _jwt_secret(), algorithms=[JWT_ALGORITHM])
		if payload.get("type") != PASSWORD_RESET_TOKEN_TYPE:
			raise ValueError("Token is not a password reset token")
		user_id = payload.get("sub")
		jti = payload.get("jti")
		if user_id is None or not jti:
			raise ValueError("Password reset token is missing required claims")
		return int(user_id), str(jti)
	except (JWTError, TypeError, ValueError) as exc:
		raise ValueError("Invalid password reset token") from exc

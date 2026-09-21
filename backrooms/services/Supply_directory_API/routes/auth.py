import logging

from fastapi import APIRouter, Depends, HTTPException, status

from services.Supply_directory_API.auth.dependencies import get_current_user
from services.Supply_directory_API.auth.email import (
	EmailConfigurationError,
	EmailDeliveryError,
	is_email_delivery_configured,
	send_password_reset_email,
)
from services.Supply_directory_API.auth.security import (
	create_access_token,
	decode_password_reset_token,
	verify_password,
)
from services.Supply_directory_API.auth.services import (
	change_password,
	consume_password_reset,
	create_password_reset,
	get_profile_by_user_id,
	get_user_entry_by_email,
	set_password,
)
from services.Supply_directory_API.database import get_db
from services.Supply_directory_API.models import (
	AuthenticatedUser,
	ChangePasswordRequest,
	ForgotPasswordRequest,
	LoginRequest,
	MessageResponse,
	ProfileResponse,
	ResetPasswordRequest,
	TokenResponse,
	UserResponse,
	UserWithProfile,
)


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

GENERIC_FORGOT_MESSAGE = (
	"If that address is registered, you'll receive a reset link shortly."
)
INVALID_RESET_TOKEN_MESSAGE = "Invalid or expired reset token."
EMAIL_UNAVAILABLE_MESSAGE = (
	"Password reset is temporarily unavailable. Please try again later."
)


def _user_response(user: AuthenticatedUser) -> UserResponse:
	return UserResponse(id=user.id, **user.model_dump(exclude={"id", "hashed_password"}))


def _profile_response(profile_entry) -> ProfileResponse:
	profile_id, profile = profile_entry
	return ProfileResponse(id=profile_id, **profile.model_dump())


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest) -> TokenResponse:
	with get_db() as db:
		user_entry = get_user_entry_by_email(db, str(payload.email))
	if user_entry is None:
		raise HTTPException(
			status_code=status.HTTP_401_UNAUTHORIZED,
			detail="Incorrect email or password",
			headers={"WWW-Authenticate": "Bearer"},
		)
	user_id, user = user_entry
	if not user.is_active or not verify_password(payload.password, user.hashed_password):
		raise HTTPException(
			status_code=status.HTTP_401_UNAUTHORIZED,
			detail="Incorrect email or password",
			headers={"WWW-Authenticate": "Bearer"},
		)

	token, expires_in = create_access_token(user_id=user_id)
	return TokenResponse(access_token=token, expires_in=expires_in)


@router.get("/me", response_model=UserWithProfile)
def get_me(current_user: AuthenticatedUser = Depends(get_current_user)) -> UserWithProfile:
	with get_db() as db:
		profile_entry = get_profile_by_user_id(db, current_user.id)
	if profile_entry is None:
		raise HTTPException(status_code=404, detail="Profile not found")
	return UserWithProfile(
		**_user_response(current_user).model_dump(),
		profile=_profile_response(profile_entry),
	)


@router.post("/forgot-password", response_model=MessageResponse)
def forgot_password(payload: ForgotPasswordRequest) -> MessageResponse:
	# Checked before the user lookup so a misconfigured service fails for every
	# address rather than only for registered ones, which would leak accounts.
	if not is_email_delivery_configured():
		logger.error("Password reset requested while email delivery is not configured")
		raise HTTPException(
			status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
			detail=EMAIL_UNAVAILABLE_MESSAGE,
		)

	token: str | None = None
	expires_in = 0
	with get_db() as db:
		user_entry = get_user_entry_by_email(db, str(payload.email))
	if user_entry is not None and user_entry[1].is_active:
		try:
			token, expires_in = create_password_reset(user_entry[0])
		except (RuntimeError, ValueError):
			logger.error(
				"Password reset token could not be created due to a configuration error"
			)
			raise HTTPException(
				status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
				detail=EMAIL_UNAVAILABLE_MESSAGE,
			)

	if token is not None:
		try:
			send_password_reset_email(
				to_email=str(payload.email),
				token=token,
				expires_in_minutes=max(1, expires_in // 60),
			)
		except EmailConfigurationError:
			logger.error("Password reset email delivery is not configured")
			raise HTTPException(
				status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
				detail=EMAIL_UNAVAILABLE_MESSAGE,
			)
		except EmailDeliveryError:
			# Sanitized: never log the recipient, reset URL, or token. Still
			# returns the generic 200 so delivery failures cannot be used to
			# enumerate registered addresses.
			logger.error("Password reset email delivery failed for an active account")

	return MessageResponse(detail=GENERIC_FORGOT_MESSAGE)


@router.post("/reset-password", response_model=MessageResponse)
def reset_password(payload: ResetPasswordRequest) -> MessageResponse:
	try:
		user_id, jti = decode_password_reset_token(payload.token)
	except (RuntimeError, ValueError) as exc:
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail=INVALID_RESET_TOKEN_MESSAGE,
		) from exc

	if not consume_password_reset(jti, user_id):
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail=INVALID_RESET_TOKEN_MESSAGE,
		)

	with get_db() as db:
		if not set_password(db, user_id, payload.new_password):
			raise HTTPException(
				status_code=status.HTTP_400_BAD_REQUEST,
				detail=INVALID_RESET_TOKEN_MESSAGE,
			)

	return MessageResponse(
		detail="Your password has been updated. You can now sign in."
	)


@router.post("/change-password", response_model=MessageResponse)
def change_my_password(
	payload: ChangePasswordRequest,
	current_user: AuthenticatedUser = Depends(get_current_user),
) -> MessageResponse:
	with get_db() as db:
		updated = change_password(
			db,
			current_user.id,
			payload.current_password,
			payload.new_password,
		)

	if not updated:
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail="Current password is incorrect.",
		)

	return MessageResponse(detail="Your password has been updated.")

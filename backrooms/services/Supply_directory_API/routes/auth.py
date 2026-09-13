from fastapi import APIRouter, Depends, HTTPException, status

from services.Supply_directory_API.auth.dependencies import get_current_user
from services.Supply_directory_API.auth.security import create_access_token, verify_password
from services.Supply_directory_API.auth.services import (
	get_profile_by_user_id,
	get_user_entry_by_email,
)
from services.Supply_directory_API.database import get_db
from services.Supply_directory_API.models import (
	AuthenticatedUser,
	LoginRequest,
	ProfileResponse,
	TokenResponse,
	UserResponse,
	UserWithProfile,
)


router = APIRouter(prefix="/auth", tags=["auth"])


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

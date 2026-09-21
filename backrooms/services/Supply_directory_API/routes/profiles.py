import logging

from fastapi import APIRouter, Depends, HTTPException

from services.Supply_directory_API.auth.dependencies import get_current_user
from services.Supply_directory_API.auth.services import get_profile_by_user_id, update_profile
from services.Supply_directory_API.database import get_db
from services.Supply_directory_API.models import AuthenticatedUser, ProfileResponse, ProfileUpdate


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/profiles", tags=["profiles"])


def _profile_response(profile_entry) -> ProfileResponse:
	profile_id, profile = profile_entry
	return ProfileResponse(id=profile_id, **profile.model_dump())


@router.get("/me", response_model=ProfileResponse)
def get_my_profile(current_user: AuthenticatedUser = Depends(get_current_user)):
	with get_db() as db:
		profile_entry = get_profile_by_user_id(db, current_user.id)
	if profile_entry is None:
		raise HTTPException(status_code=404, detail="Profile not found")
	return _profile_response(profile_entry)


@router.put("/me", response_model=ProfileResponse)
def update_my_profile(
	payload: ProfileUpdate,
	current_user: AuthenticatedUser = Depends(get_current_user),
):
	with get_db() as db:
		try:
			profile_entry = update_profile(db, current_user.id, payload)
		except RuntimeError:
			logger.error("Profile disappeared while updating user %s", current_user.id)
			raise HTTPException(
				status_code=500,
				detail="Unable to update your profile. Please try again.",
			)
	return _profile_response(profile_entry)

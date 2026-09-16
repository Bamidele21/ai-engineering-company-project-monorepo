from fastapi import APIRouter, Depends, HTTPException, status

from services.Supply_directory_API.auth.dependencies import get_current_user
from services.Supply_directory_API.auth.services import (
	create_user,
	delete_user,
	get_user_by_id,
	update_user,
)
from services.Supply_directory_API.database import get_db, get_users_table
from services.Supply_directory_API.models import (
	AuthenticatedUser,
	UserCreate,
	UserResponse,
	UserUpdate,
)


router = APIRouter(prefix="/users", tags=["users"])


def _user_response(user_id: int, user) -> UserResponse:
	return UserResponse(id=user_id, **user.model_dump(exclude={"hashed_password"}))


def _require_owner_or_admin(current_user: AuthenticatedUser, user_id: int) -> None:
	if current_user.id != user_id and current_user.role != "admin":
		raise HTTPException(status_code=403, detail="Insufficient permissions")


@router.post("", response_model=UserResponse, status_code=201)
def register(payload: UserCreate):
	try:
		with get_db() as db:
			user_id = create_user(db, payload)
			user = get_user_by_id(db, user_id)
	except ValueError as exc:
		raise HTTPException(status_code=409, detail=str(exc)) from exc
	return _user_response(user_id, user)


@router.get("", response_model=list[UserResponse])
def list_users(current_user: AuthenticatedUser = Depends(get_current_user)):
	with get_db() as db:
		return [
			_user_response(document.doc_id, get_user_by_id(db, document.doc_id))
			for document in get_users_table(db).all()
		]


@router.get("/{user_id}", response_model=UserResponse)
def get_user(user_id: int, current_user: AuthenticatedUser = Depends(get_current_user)):
	_require_owner_or_admin(current_user, user_id)
	user = _get_user_or_404(user_id)
	return _user_response(user_id, user)


@router.put("/{user_id}", response_model=UserResponse)
def update_user_record(
	user_id: int,
	payload: UserUpdate,
	current_user: AuthenticatedUser = Depends(get_current_user),
):
	_require_owner_or_admin(current_user, user_id)
	if payload.role is not None and current_user.role != "admin":
		raise HTTPException(status_code=403, detail="Only admins can update roles")
	try:
		with get_db() as db:
			user = update_user(db, user_id, payload)
	except ValueError as exc:
		raise HTTPException(status_code=409, detail=str(exc)) from exc
	if user is None:
		raise HTTPException(status_code=404, detail="User not found")
	return _user_response(user_id, user)


@router.delete("/{user_id}")
def remove_user(user_id: int, current_user: AuthenticatedUser = Depends(get_current_user)):
	_require_owner_or_admin(current_user, user_id)
	with get_db() as db:
		if not delete_user(db, user_id):
			raise HTTPException(status_code=404, detail="User not found")
	return {"detail": "User deleted"}


def _get_user_or_404(user_id: int):
	with get_db() as db:
		user = get_user_by_id(db, user_id)
	if user is None:
		raise HTTPException(status_code=404, detail="User not found")
	return user

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from services.Supply_directory_API.auth.security import decode_access_token
from services.Supply_directory_API.auth.services import get_user_by_id
from services.Supply_directory_API.database import get_db
from services.Supply_directory_API.models import AuthenticatedUser


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def get_current_user(token: str = Depends(oauth2_scheme)) -> AuthenticatedUser:
	try:
		user_id = decode_access_token(token)
	except (RuntimeError, ValueError):
		raise HTTPException(
			status_code=status.HTTP_401_UNAUTHORIZED,
			detail="Invalid authentication credentials",
			headers={"WWW-Authenticate": "Bearer"},
		)

	with get_db() as db:
		user = get_user_by_id(db, user_id)
	if user is None or not user.is_active:
		raise HTTPException(
			status_code=status.HTTP_401_UNAUTHORIZED,
			detail="Invalid authentication credentials",
			headers={"WWW-Authenticate": "Bearer"},
		)
	return AuthenticatedUser(id=user_id, **user.model_dump())

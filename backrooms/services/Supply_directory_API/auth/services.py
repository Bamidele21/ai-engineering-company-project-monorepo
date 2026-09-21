from datetime import datetime, timedelta, timezone

from tinydb import Query, TinyDB

from services.Supply_directory_API.auth.security import (
	create_password_reset_token,
	hash_password,
	verify_password,
)
from services.Supply_directory_API.database import (
	get_password_resets_db,
	get_password_resets_table,
	get_profiles_table,
	get_users_table,
)
from services.Supply_directory_API.models import (
	PasswordResetToken,
	Profile,
	ProfileUpdate,
	User,
	UserCreate,
	UserUpdate,
)


def _user_from_document(document) -> User:
	return User(**dict(document))


def _profile_from_document(document) -> Profile:
	return Profile(**dict(document))


def get_user_by_id(db: TinyDB, user_id: int) -> User | None:
	document = get_users_table(db).get(doc_id=user_id)
	return None if document is None else _user_from_document(document)


def get_user_by_email(db: TinyDB, email: str) -> User | None:
	query = Query()
	document = get_users_table(db).get(query.email == email.lower())
	return None if document is None else _user_from_document(document)


def get_user_entry_by_email(db: TinyDB, email: str) -> tuple[int, User] | None:
	query = Query()
	document = get_users_table(db).get(query.email == email.lower())
	return None if document is None else (document.doc_id, _user_from_document(document))


def create_user(db: TinyDB, payload: UserCreate) -> int:
	users_table = get_users_table(db)
	profiles_table = get_profiles_table(db)
	if get_user_by_email(db, str(payload.email)) is not None:
		raise ValueError("Email is already registered")

	user = User(
		email=str(payload.email).lower(),
		hashed_password=hash_password(payload.password),
	)
	user_id = users_table.insert(user.model_dump(mode="json"))
	try:
		profile = Profile(
			user_id=user_id,
			name=payload.name,
			phone=payload.phone,
			address=payload.address,
		)
		profiles_table.insert(profile.model_dump())
	except (OSError, ValueError):
		users_table.remove(doc_ids=[user_id])
		raise
	return user_id


def get_profile_by_user_id(db: TinyDB, user_id: int) -> tuple[int, Profile] | None:
	query = Query()
	document = get_profiles_table(db).get(query.user_id == user_id)
	return None if document is None else (document.doc_id, _profile_from_document(document))


def update_profile(db: TinyDB, user_id: int, payload: ProfileUpdate) -> tuple[int, Profile]:
	profile_entry = get_profile_by_user_id(db, user_id)
	if profile_entry is None:
		profile = Profile(user_id=user_id, **payload.model_dump())
		profile_id = get_profiles_table(db).insert(profile.model_dump())
		return profile_id, profile

	profile_id, _ = profile_entry
	get_profiles_table(db).update(payload.model_dump(), doc_ids=[profile_id])
	updated_entry = get_profile_by_user_id(db, user_id)
	if updated_entry is None:
		raise RuntimeError("Profile disappeared while updating")
	return updated_entry


def update_user(db: TinyDB, user_id: int, payload: UserUpdate) -> User | None:
	user = get_user_by_id(db, user_id)
	if user is None:
		return None

	changes = payload.model_dump(exclude_unset=True, exclude_none=True)
	if "email" in changes:
		changes["email"] = str(changes["email"]).lower()
		other_user = get_user_by_email(db, changes["email"])
		if other_user is not None and other_user != user:
			raise ValueError("Email is already registered")
	if "password" in changes:
		changes["hashed_password"] = hash_password(changes.pop("password"))

	if changes:
		get_users_table(db).update(changes, doc_ids=[user_id])
	return get_user_by_id(db, user_id)


def create_password_reset(user_id: int) -> tuple[str, int]:
	token, jti, expires_in = create_password_reset_token(user_id)
	record = PasswordResetToken(
		jti=jti,
		user_id=user_id,
		expires_at=datetime.now(timezone.utc) + timedelta(seconds=expires_in),
	)
	with get_password_resets_db() as db:
		get_password_resets_table(db).insert(record.model_dump(mode="json"))
	return token, expires_in


def get_password_reset_by_jti(jti: str) -> tuple[int, PasswordResetToken] | None:
	with get_password_resets_db() as db:
		query = Query()
		document = get_password_resets_table(db).get(query.jti == jti)
	if document is None:
		return None
	return document.doc_id, PasswordResetToken(**dict(document))


def consume_password_reset(jti: str, user_id: int) -> bool:
	with get_password_resets_db() as db:
		query = Query()
		document = get_password_resets_table(db).get(query.jti == jti)
		if document is None:
			return False
		record = PasswordResetToken(**dict(document))
		if record.used or record.user_id != user_id:
			return False
		if record.expires_at <= datetime.now(timezone.utc):
			return False
		get_password_resets_table(db).update({"used": True}, doc_ids=[document.doc_id])
		return True


def set_password(db: TinyDB, user_id: int, new_password: str) -> bool:
	if get_user_by_id(db, user_id) is None:
		return False
	get_users_table(db).update(
		{"hashed_password": hash_password(new_password)}, doc_ids=[user_id]
	)
	return True


def change_password(
	db: TinyDB, user_id: int, current_password: str, new_password: str
) -> bool:
	user = get_user_by_id(db, user_id)
	if user is None:
		return False
	if not verify_password(current_password, user.hashed_password):
		return False
	get_users_table(db).update(
		{"hashed_password": hash_password(new_password)}, doc_ids=[user_id]
	)
	return True


def delete_user(db: TinyDB, user_id: int) -> bool:
	users_table = get_users_table(db)
	if users_table.get(doc_id=user_id) is None:
		return False
	users_table.remove(doc_ids=[user_id])
	profile_entry = get_profile_by_user_id(db, user_id)
	if profile_entry is not None:
		get_profiles_table(db).remove(doc_ids=[profile_entry[0]])
	return True

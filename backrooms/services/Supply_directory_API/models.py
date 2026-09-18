from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, model_validator


SupplierCategory = Literal[
	"job_boards",
	"ats_software",
	"assessment_tools",
	"training_platforms",
	"payroll_and_hr_software",
	"video_interview",
	"background_check",
	"office_and_facilities",
	"it_and_software_licenses",
]
SupplierCountry = Literal["Spain", "USA"]
SupplierCurrency = Literal["EUR", "USD"]
SupplierStatus = Literal["active", "suspended"]
UserRole = Literal["admin", "manager", "user"]


class Supplier(BaseModel):
	name: str
	country: SupplierCountry
	categories: list[SupplierCategory] = Field(min_length=1)
	monthly_rate: float = Field(gt=0)
	currency: SupplierCurrency
	updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
	status: SupplierStatus
	contract_renewal_date: str | None = Field(
		default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"
	)
	contact_email: EmailStr | None = None
	notes: str | None = None

	@model_validator(mode="after")
	def validate_currency_matches_country(self) -> "Supplier":
		expected_currency = "EUR" if self.country == "Spain" else "USD"
		if self.currency != expected_currency:
			raise ValueError(
				f"Suppliers in {self.country} must use {expected_currency}"
			)
		return self


class User(BaseModel):
	email: EmailStr
	hashed_password: str
	is_active: bool = True
	role: UserRole = "user"
	created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class UserCreate(BaseModel):
	email: EmailStr
	password: str = Field(min_length=8)
	name: str = ""
	phone: str | None = None
	address: str | None = None


class UserUpdate(BaseModel):
	email: EmailStr | None = None
	password: str | None = Field(default=None, min_length=8)
	role: UserRole | None = None
	is_active: bool | None = None


class UserResponse(BaseModel):
	id: int
	email: EmailStr
	is_active: bool
	role: UserRole
	created_at: datetime


class AuthenticatedUser(User):
	id: int


class Profile(BaseModel):
	user_id: int
	name: str = ""
	phone: str | None = None
	address: str | None = None


class ProfileUpdate(BaseModel):
	name: str = ""
	phone: str | None = None
	address: str | None = None


class ProfileResponse(Profile):
	id: int


class UserWithProfile(UserResponse):
	profile: ProfileResponse


class LoginRequest(BaseModel):
	email: EmailStr
	password: str


class TokenResponse(BaseModel):
	access_token: str
	token_type: str = "bearer"
	expires_in: int


class ForgotPasswordRequest(BaseModel):
	email: EmailStr


class ResetPasswordRequest(BaseModel):
	token: str
	new_password: str = Field(min_length=8)


class ChangePasswordRequest(BaseModel):
	current_password: str
	new_password: str = Field(min_length=8)


class MessageResponse(BaseModel):
	detail: str


class PasswordResetToken(BaseModel):
	jti: str
	user_id: int
	issued_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
	expires_at: datetime
	used: bool = False

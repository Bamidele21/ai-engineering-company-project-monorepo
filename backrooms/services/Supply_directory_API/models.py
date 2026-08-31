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

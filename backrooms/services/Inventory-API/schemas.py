"""Pydantic request/response schemas for the Nexova Inventory API.

Kept in a separate file from the SQLModel ORM models. Endpoints return these
schemas, never raw ORM objects.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator


AssetCategory = Literal[
	"hardware",
	"peripherals",
	"office_supplies",
	"training_materials",
]
Office = Literal["Valencia", "Miami"]
ExitType = Literal["allocation", "consumption"]


class AssetCreate(BaseModel):
	name: str = Field(min_length=1)
	sku: str = Field(min_length=1)
	category: AssetCategory
	office: Office


class AssetRead(BaseModel):
	id: int
	name: str
	sku: str
	category: str
	office: str
	current_stock: int


class AssetEntryCreate(BaseModel):
	asset_id: int
	quantity: int = Field(gt=0)
	supplier: str = Field(min_length=1)
	office: Office


class AssetEntryRead(BaseModel):
	id: int
	asset_id: int
	quantity: int
	supplier: str
	office: str
	created_at: datetime
	user_uuid: str


class AssetExitCreate(BaseModel):
	asset_id: int
	quantity: int = Field(gt=0)
	exit_type: ExitType
	assigned_to: str | None = None
	office: Office

	@model_validator(mode="after")
	def validate_assigned_to(self) -> "AssetExitCreate":
		if self.exit_type == "allocation" and not self.assigned_to:
			raise ValueError(
				"assigned_to is required when exit_type is 'allocation'"
			)
		if self.exit_type == "consumption" and self.assigned_to is not None:
			raise ValueError(
				"assigned_to must be null when exit_type is 'consumption'"
			)
		return self


class AssetExitRead(BaseModel):
	id: int
	asset_id: int
	quantity: int
	exit_type: str
	assigned_to: str | None
	office: str
	created_at: datetime
	user_uuid: str


class OrderRead(BaseModel):
	id: int
	kind: Literal["inbound", "outbound"]
	asset_id: int
	asset_name: str
	asset_sku: str
	quantity: int
	office: str
	created_at: datetime
	user_uuid: str
	supplier: str | None = None
	exit_type: str | None = None
	assigned_to: str | None = None


class MessageResponse(BaseModel):
	detail: str

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from services.Supply_directory_API.auth.dependencies import get_current_user
from services.Supply_directory_API.database import get_db, get_suppliers_table
from services.Supply_directory_API.models import AuthenticatedUser, Supplier, SupplierCountry, SupplierStatus


router = APIRouter(prefix="/suppliers", tags=["suppliers"])


class SupplierRecord(Supplier):
	id: int


class RateUpdatePayload(BaseModel):
	monthly_rate: float = Field(gt=0)


class StatusUpdatePayload(BaseModel):
	status: SupplierStatus


def _as_storable(supplier: Supplier) -> dict:
	data = supplier.model_dump()
	data["updated_at"] = supplier.updated_at.isoformat()
	return data


def _attach_id(doc) -> dict:
	payload = dict(doc)
	payload["id"] = doc.doc_id
	return payload


def _find_supplier_or_404(table, supplier_id: int):
	supplier = table.get(doc_id=supplier_id)
	if supplier is None:
		raise HTTPException(status_code=404, detail="Supplier not found")
	return supplier


def _require_supplier_writer(current_user: AuthenticatedUser) -> None:
	if current_user.role not in {"admin", "manager"}:
		raise HTTPException(status_code=403, detail="Supplier write access requires admin or manager role")


@router.post("", response_model=SupplierRecord, status_code=201)
def create_supplier(
	payload: Supplier,
	current_user: AuthenticatedUser = Depends(get_current_user),
):
	_require_supplier_writer(current_user)
	with get_db() as db:
		table = get_suppliers_table(db)
		doc_id = table.insert(_as_storable(payload))
		created = table.get(doc_id=doc_id)
		return _attach_id(created)


@router.get("", response_model=list[SupplierRecord])
def list_suppliers(
	country: SupplierCountry | None = Query(default=None),
	category: str | None = Query(default=None),
	current_user: AuthenticatedUser = Depends(get_current_user),
):
	with get_db() as db:
		table = get_suppliers_table(db)
		docs = table.all()

	results = []
	for doc in docs:
		matches_country = country is None or doc.get("country") == country
		categories = doc.get("categories", [])
		matches_category = category is None or category in categories
		if matches_country and matches_category:
			results.append(_attach_id(doc))

	return results


@router.get("/{supplier_id}", response_model=SupplierRecord)
def get_supplier(
	supplier_id: int,
	current_user: AuthenticatedUser = Depends(get_current_user),
):
	with get_db() as db:
		table = get_suppliers_table(db)
		supplier = _find_supplier_or_404(table, supplier_id)
		return _attach_id(supplier)


@router.patch("/{supplier_id}/rate", response_model=SupplierRecord)
def update_supplier_rate(
	supplier_id: int,
	payload: RateUpdatePayload,
	current_user: AuthenticatedUser = Depends(get_current_user),
):
	_require_supplier_writer(current_user)
	with get_db() as db:
		table = get_suppliers_table(db)
		_find_supplier_or_404(table, supplier_id)

		table.update(
			{
				"monthly_rate": payload.monthly_rate,
				"updated_at": datetime.now(timezone.utc).isoformat(),
			},
			doc_ids=[supplier_id],
		)
		updated = table.get(doc_id=supplier_id)

	return _attach_id(updated)


@router.patch("/{supplier_id}/status", response_model=SupplierRecord)
def update_supplier_status(
	supplier_id: int,
	payload: StatusUpdatePayload,
	current_user: AuthenticatedUser = Depends(get_current_user),
):
	_require_supplier_writer(current_user)
	with get_db() as db:
		table = get_suppliers_table(db)
		_find_supplier_or_404(table, supplier_id)
		table.update({"status": payload.status}, doc_ids=[supplier_id])
		updated = table.get(doc_id=supplier_id)

	return _attach_id(updated)


@router.delete("/{supplier_id}", status_code=200)
def delete_supplier(
	supplier_id: int,
	current_user: AuthenticatedUser = Depends(get_current_user),
):
	_require_supplier_writer(current_user)
	with get_db() as db:
		table = get_suppliers_table(db)
		_find_supplier_or_404(table, supplier_id)
		table.remove(doc_ids=[supplier_id])

	return {"detail": "Supplier deleted"}

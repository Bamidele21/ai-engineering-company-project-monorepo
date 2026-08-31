from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from tinydb import TinyDB

from models import Supplier, SupplierCountry, SupplierStatus


router = APIRouter(prefix="/suppliers", tags=["suppliers"])

DB_PATH = Path(__file__).resolve().parent.parent / "suppliers_db.json"
SUPPLIERS_TABLE = "suppliers"


class SupplierRecord(Supplier):
	id: int


class RateUpdatePayload(BaseModel):
	monthly_rate: float = Field(gt=0)


class StatusUpdatePayload(BaseModel):
	status: SupplierStatus


def _db() -> TinyDB:
	return TinyDB(DB_PATH)


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


@router.post("", response_model=SupplierRecord, status_code=201)
def create_supplier(payload: Supplier):
	with _db() as db:
		table = db.table(SUPPLIERS_TABLE)
		doc_id = table.insert(_as_storable(payload))
		created = table.get(doc_id=doc_id)
		return _attach_id(created)


@router.get("", response_model=list[SupplierRecord])
def list_suppliers(
	country: SupplierCountry | None = Query(default=None),
	category: str | None = Query(default=None),
):
	with _db() as db:
		table = db.table(SUPPLIERS_TABLE)
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
def get_supplier(supplier_id: int):
	with _db() as db:
		table = db.table(SUPPLIERS_TABLE)
		supplier = _find_supplier_or_404(table, supplier_id)
		return _attach_id(supplier)


@router.patch("/{supplier_id}/rate", response_model=SupplierRecord)
def update_supplier_rate(supplier_id: int, payload: RateUpdatePayload):
	with _db() as db:
		table = db.table(SUPPLIERS_TABLE)
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
def update_supplier_status(supplier_id: int, payload: StatusUpdatePayload):
	with _db() as db:
		table = db.table(SUPPLIERS_TABLE)
		_find_supplier_or_404(table, supplier_id)
		table.update({"status": payload.status}, doc_ids=[supplier_id])
		updated = table.get(doc_id=supplier_id)

	return _attach_id(updated)


@router.delete("/{supplier_id}", status_code=200)
def delete_supplier(supplier_id: int):
	with _db() as db:
		table = db.table(SUPPLIERS_TABLE)
		_find_supplier_or_404(table, supplier_id)
		table.remove(doc_ids=[supplier_id])

	return {"detail": "Supplier deleted"}

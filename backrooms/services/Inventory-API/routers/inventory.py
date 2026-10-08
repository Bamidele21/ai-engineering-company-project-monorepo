"""Nexova inventory router — every route lives under the ``/inventory`` prefix."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, func, select

from services.Supply_directory_API.auth.dependencies import get_current_user
from services.Supply_directory_API.models import AuthenticatedUser

from database import get_sql_session
from models import Asset, AssetEntry, AssetExit
from schemas import (
	AssetCreate,
	AssetEntryCreate,
	AssetEntryRead,
	AssetExitCreate,
	AssetExitRead,
	AssetRead,
	OrderRead,
)


router = APIRouter(prefix="/inventory", tags=["inventory"])


def _sum_by_asset(session: Session, model) -> dict[int, int]:
	"""Single grouped aggregate per order table (avoids the N+1 problem)."""
	rows = session.exec(
		select(model.asset_id, func.coalesce(func.sum(model.quantity), 0)).group_by(
			model.asset_id
		)
	).all()
	return {asset_id: int(total) for asset_id, total in rows}


def _stock_map(session: Session) -> dict[int, int]:
	inbound = _sum_by_asset(session, AssetEntry)
	outbound = _sum_by_asset(session, AssetExit)
	return {
		asset_id: inbound.get(asset_id, 0) - outbound.get(asset_id, 0)
		for asset_id in set(inbound) | set(outbound)
	}


def _get_asset_or_404(session: Session, asset_id: int) -> Asset:
	asset = session.get(Asset, asset_id)
	if asset is None:
		raise HTTPException(status_code=404, detail="Asset not found")
	return asset


def _to_asset_read(asset: Asset, current_stock: int) -> AssetRead:
	return AssetRead(
		id=asset.id,
		name=asset.name,
		sku=asset.sku,
		category=asset.category,
		office=asset.office,
		current_stock=current_stock,
	)


@router.get("/products", response_model=list[AssetRead])
def list_products(session: Session = Depends(get_sql_session)) -> list[AssetRead]:
	assets = session.exec(select(Asset).order_by(Asset.id)).all()
	stock = _stock_map(session)
	return [_to_asset_read(asset, stock.get(asset.id, 0)) for asset in assets]


@router.post("/products", response_model=AssetRead, status_code=201)
def create_product(
	payload: AssetCreate,
	session: Session = Depends(get_sql_session),
	current_user: AuthenticatedUser = Depends(get_current_user),
) -> AssetRead:
	asset = Asset(**payload.model_dump())
	session.add(asset)
	try:
		session.commit()
	except IntegrityError:
		session.rollback()
		raise HTTPException(
			status_code=409,
			detail=f"An asset with SKU '{payload.sku}' already exists.",
		)
	session.refresh(asset)
	# A freshly created asset always starts at zero stock.
	return _to_asset_read(asset, 0)


@router.get("/products/{asset_id}", response_model=AssetRead)
def get_product(
	asset_id: int, session: Session = Depends(get_sql_session)
) -> AssetRead:
	asset = _get_asset_or_404(session, asset_id)
	stock = _stock_map(session)
	return _to_asset_read(asset, stock.get(asset_id, 0))


@router.post("/orders/inbound", response_model=AssetEntryRead, status_code=201)
def create_inbound_order(
	payload: AssetEntryCreate,
	session: Session = Depends(get_sql_session),
	current_user: AuthenticatedUser = Depends(get_current_user),
) -> AssetEntryRead:
	_get_asset_or_404(session, payload.asset_id)
	entry = AssetEntry(**payload.model_dump(), user_uuid=current_user.uuid)
	session.add(entry)
	session.commit()
	session.refresh(entry)
	return AssetEntryRead(**entry.model_dump())


@router.post("/orders/outbound", response_model=AssetExitRead, status_code=201)
def create_outbound_order(
	payload: AssetExitCreate,
	session: Session = Depends(get_sql_session),
	current_user: AuthenticatedUser = Depends(get_current_user),
) -> AssetExitRead:
	asset = _get_asset_or_404(session, payload.asset_id)
	available = _stock_map(session).get(asset.id, 0)
	if payload.quantity > available:
		# Rejected before any row is persisted.
		raise HTTPException(
			status_code=400,
			detail=(
				f"Insufficient stock for asset '{asset.name}'. "
				f"Available: {available}, requested: {payload.quantity}."
			),
		)

	exit_record = AssetExit(**payload.model_dump(), user_uuid=current_user.uuid)
	session.add(exit_record)
	session.commit()
	session.refresh(exit_record)
	return AssetExitRead(**exit_record.model_dump())


@router.get("/orders", response_model=list[OrderRead])
def list_orders(session: Session = Depends(get_sql_session)) -> list[OrderRead]:
	# Load every asset once, then attach order rows — three queries, no N+1.
	assets = {asset.id: asset for asset in session.exec(select(Asset)).all()}
	orders: list[OrderRead] = []

	for entry in session.exec(select(AssetEntry)).all():
		asset = assets.get(entry.asset_id)
		orders.append(
			OrderRead(
				id=entry.id,
				kind="inbound",
				asset_id=entry.asset_id,
				asset_name=asset.name if asset else "",
				asset_sku=asset.sku if asset else "",
				quantity=entry.quantity,
				office=entry.office,
				created_at=entry.created_at,
				user_uuid=entry.user_uuid,
				supplier=entry.supplier,
			)
		)

	for exit_record in session.exec(select(AssetExit)).all():
		asset = assets.get(exit_record.asset_id)
		orders.append(
			OrderRead(
				id=exit_record.id,
				kind="outbound",
				asset_id=exit_record.asset_id,
				asset_name=asset.name if asset else "",
				asset_sku=asset.sku if asset else "",
				quantity=exit_record.quantity,
				office=exit_record.office,
				created_at=exit_record.created_at,
				user_uuid=exit_record.user_uuid,
				exit_type=exit_record.exit_type,
				assigned_to=exit_record.assigned_to,
			)
		)

	orders.sort(key=lambda order: order.created_at)
	return orders

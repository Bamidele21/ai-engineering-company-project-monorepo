"""Nexova inventory router. Every route lives under the ``/inventory`` prefix."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, func, select

from services.Supply_directory_API.auth.dependencies import get_current_user
from services.Supply_directory_API.models import AuthenticatedUser
from services.cache import TtlCache
from services.telemetry.constants import (
	OFFICE_CURRENCY,
	currency_for_office,
	lower_office,
	normalize_category,
)
from services.telemetry.emitter import emit_inventory_event

from database import get_sql_session
from models import Asset, AssetEntry, AssetExit, Programme
from schemas import (
	AssetCreate,
	AssetEntryCreate,
	AssetEntryRead,
	AssetExitCreate,
	AssetExitRead,
	AssetRead,
	OrderRead,
)


logger = logging.getLogger("nexova.telemetry")

router = APIRouter(prefix="/inventory", tags=["inventory"])

PRODUCTS_CACHE_TTL = 15.0
PRODUCTS_CACHE_KEY = "inventory:products"
_inventory_cache = TtlCache()
_telemetry_throttle = TtlCache()

STOCK_THRESHOLD_THROTTLE_SECONDS = 60 * 60
COST_VARIANCE_THROTTLE_SECONDS = 24 * 60 * 60
DIRECT_EDIT_PATH_TEMPLATE = "/inventory/products/{id}"


def _sum_by_asset(session: Session, model) -> dict[int, int]:
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


def _get_programme_or_404(session: Session, programme_id: int) -> Programme:
	programme = session.get(Programme, programme_id)
	if programme is None:
		raise HTTPException(status_code=404, detail="Programme not found")
	return programme


def _to_asset_read(asset: Asset, current_stock: int) -> AssetRead:
	return AssetRead(
		id=asset.id,
		name=asset.name,
		sku=asset.sku,
		category=asset.category,
		office=asset.office,
		programme_id=asset.programme_id,
		min_stock=asset.min_stock,
		current_stock=current_stock,
	)


def _programme_slug(session: Session, asset: Asset) -> str | None:
	if asset.programme_id is None:
		return None
	programme = session.get(Programme, asset.programme_id)
	return programme.slug if programme else None


def _dimensions(
	asset: Asset,
	programme_slug: str | None,
	*,
	office: str,
	currency: str,
) -> dict:
	return {
		"office": lower_office(office),
		"product_id": asset.id,
		"product_category": normalize_category(asset.category),
		"programme_id": programme_slug,
		"currency": currency,
	}


def _safe_emit(
	event_type: str,
	properties: dict,
	*,
	request: Request,
	current_user: AuthenticatedUser,
) -> None:
	try:
		emit_inventory_event(
			event_type,
			properties,
			request=request,
			user_id=current_user.id,
		)
	except Exception as error:
		logger.warning("telemetry emission failed for %s: %s", event_type, error)


def _is_throttled(key: str, ttl: float) -> bool:
	if _telemetry_throttle.get(key) is not None:
		return True
	_telemetry_throttle.set(key, True, ttl)
	return False


@router.get("/products", response_model=list[AssetRead])
def list_products(session: Session = Depends(get_sql_session)) -> list[AssetRead]:
	cached = _inventory_cache.get(PRODUCTS_CACHE_KEY)
	if cached is not None:
		return cached

	assets = session.exec(select(Asset).order_by(Asset.id)).all()
	stock = _stock_map(session)
	products = [_to_asset_read(asset, stock.get(asset.id, 0)) for asset in assets]
	_inventory_cache.set(PRODUCTS_CACHE_KEY, products, PRODUCTS_CACHE_TTL)
	return products


@router.post("/products", response_model=AssetRead, status_code=201)
def create_product(
	payload: AssetCreate,
	session: Session = Depends(get_sql_session),
	current_user: AuthenticatedUser = Depends(get_current_user),
) -> AssetRead:
	_get_programme_or_404(session, payload.programme_id)
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
	_inventory_cache.invalidate("inventory:")
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
	request: Request,
	session: Session = Depends(get_sql_session),
	current_user: AuthenticatedUser = Depends(get_current_user),
) -> AssetEntryRead:
	asset = _get_asset_or_404(session, payload.asset_id)
	entry = AssetEntry(**payload.model_dump(), user_uuid=current_user.uuid)
	session.add(entry)
	session.commit()
	session.refresh(entry)
	_inventory_cache.invalidate("inventory:")

	programme_slug = _programme_slug(session, asset)
	if programme_slug:
		_safe_emit(
			"inbound_order_created",
			{
				**_dimensions(
					asset,
					programme_slug,
					office=entry.office,
					currency=entry.currency,
				),
				"quantity": entry.quantity,
				"supplier": entry.supplier,
				"unit_cost": float(entry.unit_cost),
				"order_id": entry.id,
			},
			request=request,
			current_user=current_user,
		)
		_emit_cost_variance(
			session,
			asset,
			entry,
			programme_slug,
			request=request,
			current_user=current_user,
		)

	return AssetEntryRead(**entry.model_dump())


@router.post("/orders/outbound", response_model=AssetExitRead, status_code=201)
def create_outbound_order(
	payload: AssetExitCreate,
	request: Request,
	session: Session = Depends(get_sql_session),
	current_user: AuthenticatedUser = Depends(get_current_user),
) -> AssetExitRead:
	asset = _get_asset_or_404(session, payload.asset_id)
	available = _stock_map(session).get(asset.id, 0)
	programme_slug = _programme_slug(session, asset)

	if payload.quantity > available:
		if programme_slug:
			_safe_emit(
				"outbound_order_rejected",
				{
					**_dimensions(
						asset,
						programme_slug,
						office=payload.office,
						currency=currency_for_office(payload.office),
					),
					"quantity": payload.quantity,
					"exit_type": payload.exit_type,
					"available_stock": available,
				},
				request=request,
				current_user=current_user,
			)
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
	_inventory_cache.invalidate("inventory:")

	if programme_slug:
		_safe_emit(
			"outbound_order_created",
			{
				**_dimensions(
					asset,
					programme_slug,
					office=exit_record.office,
					currency=currency_for_office(exit_record.office),
				),
				"quantity": exit_record.quantity,
				"exit_type": exit_record.exit_type,
				"order_id": exit_record.id,
			},
			request=request,
			current_user=current_user,
		)
		_emit_stock_threshold(
			asset,
			programme_slug,
			previous_stock=available,
			new_stock=available - exit_record.quantity,
			request=request,
			current_user=current_user,
		)

	return AssetExitRead(**exit_record.model_dump())


def _emit_cost_variance(
	session: Session,
	asset: Asset,
	entry: AssetEntry,
	programme_slug: str,
	*,
	request: Request,
	current_user: AuthenticatedUser,
) -> None:
	historical = session.exec(
		select(func.avg(AssetEntry.unit_cost)).where(
			AssetEntry.asset_id == asset.id,
			AssetEntry.supplier == entry.supplier,
			AssetEntry.id != entry.id,
		)
	).one()
	if historical is None:
		return

	mean = float(historical)
	if mean <= 0:
		return

	variance = (float(entry.unit_cost) - mean) / mean
	if abs(variance) <= 0.10:
		return

	throttle_key = f"cost_variance:{asset.id}:{entry.supplier}"
	if _is_throttled(throttle_key, COST_VARIANCE_THROTTLE_SECONDS):
		return

	_safe_emit(
		"kit_cost_variance_detected",
		{
			**_dimensions(
				asset,
				programme_slug,
				office=entry.office,
				currency=entry.currency,
			),
			"quantity": entry.quantity,
			"supplier": entry.supplier,
			"unit_cost": float(entry.unit_cost),
			"historical_avg_cost": round(mean, 2),
			"variance_percent": round(variance * 100, 2),
			"order_id": entry.id,
		},
		request=request,
		current_user=current_user,
	)


def _emit_stock_threshold(
	asset: Asset,
	programme_slug: str,
	*,
	previous_stock: int,
	new_stock: int,
	request: Request,
	current_user: AuthenticatedUser,
) -> None:
	if not (previous_stock >= asset.min_stock > new_stock):
		return

	throttle_key = f"stock_threshold:{asset.id}"
	if _is_throttled(throttle_key, STOCK_THRESHOLD_THROTTLE_SECONDS):
		return

	_safe_emit(
		"stock_threshold_triggered",
		{
			**_dimensions(
				asset,
				programme_slug,
				office=asset.office,
				currency=currency_for_office(asset.office),
			),
			"quantity": new_stock,
			"min_stock": asset.min_stock,
			"previous_stock": previous_stock,
		},
		request=request,
		current_user=current_user,
	)


def _reject_direct_stock_edit(
	*,
	request: Request,
	session: Session,
	current_user: AuthenticatedUser,
	method: str,
	asset_id: int | None = None,
) -> None:
	asset = session.get(Asset, asset_id) if asset_id is not None else None
	programme_slug = _programme_slug(session, asset) if asset else None
	office = lower_office(asset.office) if asset else None

	_safe_emit(
		"direct_stock_edit_rejected",
		{
			"office": office,
			"product_id": asset.id if asset else asset_id,
			"product_category": normalize_category(asset.category) if asset else None,
			"programme_id": programme_slug,
			"quantity": None,
			"currency": OFFICE_CURRENCY.get(office) if office else None,
			"method": method,
			"path": DIRECT_EDIT_PATH_TEMPLATE if asset_id is not None else "/inventory/products",
		},
		request=request,
		current_user=current_user,
	)
	raise HTTPException(
		status_code=405,
		detail="Direct stock edits are not allowed. Use inbound or outbound orders.",
	)


@router.put("/products")
def reject_direct_product_put(
	request: Request,
	session: Session = Depends(get_sql_session),
	current_user: AuthenticatedUser = Depends(get_current_user),
) -> None:
	_reject_direct_stock_edit(
		request=request,
		session=session,
		current_user=current_user,
		method="PUT",
	)


@router.patch("/products")
def reject_direct_product_patch(
	request: Request,
	session: Session = Depends(get_sql_session),
	current_user: AuthenticatedUser = Depends(get_current_user),
) -> None:
	_reject_direct_stock_edit(
		request=request,
		session=session,
		current_user=current_user,
		method="PATCH",
	)


@router.delete("/products")
def reject_direct_product_delete(
	request: Request,
	session: Session = Depends(get_sql_session),
	current_user: AuthenticatedUser = Depends(get_current_user),
) -> None:
	_reject_direct_stock_edit(
		request=request,
		session=session,
		current_user=current_user,
		method="DELETE",
	)


@router.put("/products/{asset_id}")
def reject_direct_product_item_put(
	asset_id: int,
	request: Request,
	session: Session = Depends(get_sql_session),
	current_user: AuthenticatedUser = Depends(get_current_user),
) -> None:
	_reject_direct_stock_edit(
		request=request,
		session=session,
		current_user=current_user,
		method="PUT",
		asset_id=asset_id,
	)


@router.patch("/products/{asset_id}")
def reject_direct_product_item_patch(
	asset_id: int,
	request: Request,
	session: Session = Depends(get_sql_session),
	current_user: AuthenticatedUser = Depends(get_current_user),
) -> None:
	_reject_direct_stock_edit(
		request=request,
		session=session,
		current_user=current_user,
		method="PATCH",
		asset_id=asset_id,
	)


@router.delete("/products/{asset_id}")
def reject_direct_product_item_delete(
	asset_id: int,
	request: Request,
	session: Session = Depends(get_sql_session),
	current_user: AuthenticatedUser = Depends(get_current_user),
) -> None:
	_reject_direct_stock_edit(
		request=request,
		session=session,
		current_user=current_user,
		method="DELETE",
		asset_id=asset_id,
	)


@router.get("/orders", response_model=list[OrderRead])
def list_orders(session: Session = Depends(get_sql_session)) -> list[OrderRead]:
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
				unit_cost=entry.unit_cost,
				currency=entry.currency,
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

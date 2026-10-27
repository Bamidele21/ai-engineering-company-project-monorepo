"""Envelope construction and batched delivery for server-origin events."""

import atexit
import logging
import os
import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable
from uuid import UUID, uuid4

import httpx

from .catalog import validate_event_payload
from .constants import EVENT_SCHEMA_VERSIONS, INVENTORY_SOURCE

logger = logging.getLogger("nexova.telemetry")

DEFAULT_BATCH_SIZE = 20
DEFAULT_FLUSH_INTERVAL = 10.0
DEFAULT_RETRY_DELAYS = (0.5, 1.0, 2.0)


def _uuid_or_new(value: str | None) -> str:
	if value:
		try:
			UUID(str(value))
			return str(value)
		except (TypeError, ValueError):
			pass
	return str(uuid4())


def _utc_timestamp(value: datetime | None = None) -> str:
	moment = value or datetime.now(timezone.utc)
	if moment.tzinfo is None:
		moment = moment.replace(tzinfo=timezone.utc)
	return moment.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace(
		"+00:00", "Z"
	)


def build_event(
	event_type: str,
	properties: dict[str, Any],
	*,
	user_id: str | int | None = None,
	request_id: str | None = None,
	session_id: str | None = None,
	source: str = INVENTORY_SOURCE,
	timestamp: datetime | None = None,
) -> dict[str, Any]:
	schema_version = EVENT_SCHEMA_VERSIONS.get(event_type, "1.0")
	validate_event_payload(event_type, source, schema_version, properties)
	return {
		"eventId": str(uuid4()),
		"timestamp": _utc_timestamp(timestamp),
		"sessionId": _uuid_or_new(session_id),
		"userId": str(user_id) if user_id is not None else None,
		"event_type": event_type,
		"schemaVersion": schema_version,
		"requestId": _uuid_or_new(request_id),
		"source": source,
		"properties": dict(properties),
	}


def correlation_from_request(request: Any) -> tuple[str | None, str | None]:
	if request is None:
		return None, None
	return (
		request.headers.get("X-Request-Id"),
		request.headers.get("X-Session-Id"),
	)


def _post_batch(events: list[dict[str, Any]]) -> None:
	endpoint = os.getenv("TELEMETRY_ENDPOINT", "").strip()
	if not endpoint:
		logger.debug("telemetry endpoint is not configured; dropping %d events", len(events))
		return

	with httpx.Client(timeout=5.0) as client:
		response = client.post(endpoint, json={"events": events})
		response.raise_for_status()


class TelemetryQueue:
	"""Process-local batching queue with in-flight separation and bounded retries."""

	def __init__(
		self,
		sink: Callable[[list[dict[str, Any]]], None] | None = None,
		*,
		batch_size: int = DEFAULT_BATCH_SIZE,
		flush_interval: float = DEFAULT_FLUSH_INTERVAL,
		retry_delays: tuple[float, ...] = DEFAULT_RETRY_DELAYS,
		run_in_background: bool = True,
	) -> None:
		self._sink = sink or _post_batch
		self._batch_size = batch_size
		self._flush_interval = flush_interval
		self._retry_delays = retry_delays
		self._run_in_background = run_in_background
		self._pending: list[dict[str, Any]] = []
		self._timer: threading.Timer | None = None
		self._lock = threading.Lock()

	def add(self, event: dict[str, Any]) -> None:
		batch: list[dict[str, Any]] | None = None
		with self._lock:
			self._pending.append(event)
			if len(self._pending) >= self._batch_size:
				batch = self._drain_locked()
			elif self._timer is None:
				self._timer = threading.Timer(self._flush_interval, self._on_timer)
				self._timer.daemon = True
				self._timer.start()
		if batch:
			self._dispatch(batch)

	def flush_now(self) -> None:
		with self._lock:
			batch = self._drain_locked()
		if batch:
			self._send(batch)

	def pending_count(self) -> int:
		with self._lock:
			return len(self._pending)

	def _drain_locked(self) -> list[dict[str, Any]]:
		batch = self._pending
		self._pending = []
		if self._timer is not None:
			self._timer.cancel()
			self._timer = None
		return batch

	def _on_timer(self) -> None:
		with self._lock:
			self._timer = None
			batch = self._drain_locked()
		if batch:
			self._dispatch(batch)

	def _dispatch(self, batch: list[dict[str, Any]]) -> None:
		if not self._run_in_background:
			self._send(batch)
			return
		thread = threading.Thread(target=self._send, args=(batch,), daemon=True)
		thread.start()

	def _send(self, batch: list[dict[str, Any]]) -> None:
		for attempt in range(len(self._retry_delays) + 1):
			try:
				self._sink(batch)
				return
			except Exception as error:
				if attempt >= len(self._retry_delays):
					logger.warning(
						"telemetry batch dropped after %d attempts: %s",
						attempt + 1,
						error,
					)
					return
				time.sleep(self._retry_delays[attempt])


_default_queue = TelemetryQueue()
atexit.register(_default_queue.flush_now)


def emit_inventory_event(
	event_type: str,
	properties: dict[str, Any],
	*,
	request: Any = None,
	user_id: str | int | None = None,
	queue: TelemetryQueue | None = None,
) -> dict[str, Any]:
	request_id, session_id = correlation_from_request(request)
	event = build_event(
		event_type,
		properties,
		user_id=user_id,
		request_id=request_id,
		session_id=session_id,
	)
	(queue or _default_queue).add(event)
	return event


def flush_telemetry_queue() -> None:
	_default_queue.flush_now()

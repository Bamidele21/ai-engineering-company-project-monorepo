"""Database engines and the dedicated advisory-lock connection."""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.pool import NullPool

from . import config

logger = logging.getLogger("nexova.reporting.pipeline")

_engine: Engine | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = create_engine(config.database_url(), pool_pre_ping=True)
    return _engine


def dispose_engine() -> None:
    global _engine
    if _engine is not None:
        _engine.dispose()
        _engine = None


def _lock_engine() -> Engine:
    url = config.session_mode_database_url()
    if not url:
        raise SQLAlchemyError("Session-mode database URL is unavailable")
    # NullPool guarantees the advisory lock stays on one physical session and
    # is released when the dedicated connection closes.
    return create_engine(url, poolclass=NullPool, pool_pre_ping=True)


@contextmanager
def advisory_lock(key: int | None = None) -> Iterator[bool]:
    """Try to acquire the pipeline advisory lock on a dedicated session.

    SQLite test engines have no advisory locks, so the lock is a no-op there.
    If the session-mode connection cannot be established (for example a project
    that only exposes the transaction pooler), the pipeline logs a warning and
    continues: the active-run unique index and the Prefect concurrency limit
    remain in force. This fallback is recorded in the design document.
    """
    lock_key = key if key is not None else config.advisory_lock_key()
    engine = get_engine()
    if engine.dialect.name != "postgresql":
        yield True
        return

    try:
        lock_engine = _lock_engine()
    except SQLAlchemyError:
        logger.warning(
            "advisory lock unavailable; relying on the active-run constraint"
        )
        yield True
        return

    connection = None
    acquired = False
    try:
        try:
            connection = lock_engine.connect()
            acquired = bool(
                connection.execute(
                    text("select pg_try_advisory_lock(:key)"), {"key": lock_key}
                ).scalar()
            )
        except SQLAlchemyError:
            logger.warning(
                "advisory lock connection failed; relying on the active-run constraint"
            )
            acquired = True
        if not acquired:
            yield False
            return
        yield True
    finally:
        if connection is not None:
            if acquired:
                try:
                    connection.execute(
                        text("select pg_advisory_unlock(:key)"), {"key": lock_key}
                    )
                    connection.commit()
                except SQLAlchemyError:
                    logger.warning("advisory lock release failed; connection will close")
            connection.close()
        lock_engine.dispose()

"""Async engine, sessions and migrations for Supabase Postgres or local SQLite."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, event, make_url, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

logger = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).parent / "migrations"
SUPAVISOR_TRANSACTION_PORT = 6543
MIGRATION_LOCK_ID = 7_424_660_001  # arbitrary, shared by every Gauntlet process


def create_engine(database_url: str) -> AsyncEngine:
    url = make_url(database_url)
    if url.get_backend_name() == "sqlite":
        if url.database and url.database != ":memory:":
            Path(url.database).parent.mkdir(parents=True, exist_ok=True)
        engine = create_async_engine(url, connect_args={"timeout": 30})
        _serialize_sqlite_writes(engine)
        return engine

    connect_args: dict[str, Any] = {}
    if url.port == SUPAVISOR_TRANSACTION_PORT:
        # Supabase's pooler in transaction mode can't keep prepared statements.
        connect_args = {"statement_cache_size": 0, "prepared_statement_cache_size": 0}
    return create_async_engine(url, connect_args=connect_args, pool_pre_ping=True)


def _serialize_sqlite_writes(engine: AsyncEngine) -> None:
    """Make every SQLite transaction BEGIN IMMEDIATE.

    Postgres serializes trades with SELECT ... FOR UPDATE, which SQLite ignores. Taking the
    write lock at BEGIN gives SQLite the same guarantee: concurrent trades queue up
    instead of reading stale balances.
    """

    @event.listens_for(engine.sync_engine, "connect")
    def _connect(dbapi_connection: Any, _record: Any) -> None:
        dbapi_connection.isolation_level = None  # let us issue BEGIN ourselves
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()

    @event.listens_for(engine.sync_engine, "begin")
    def _begin(conn: Connection) -> None:
        conn.exec_driver_sql("BEGIN IMMEDIATE")


class Database:
    def __init__(self, database_url: str):
        self.url = database_url
        self.engine = create_engine(database_url)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)

    @property
    def dialect(self) -> str:
        return self.engine.dialect.name

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[AsyncSession]:
        """A session inside one transaction, committed on success."""
        async with self.sessions() as session, session.begin():
            yield session

    async def migrate(self, revision: str = "head") -> None:
        """Bring the schema up to date. Safe to call from several processes at once."""
        async with self.engine.begin() as conn:
            if self.dialect == "postgresql":
                await conn.execute(text("SELECT pg_advisory_xact_lock(:id)"), {"id": MIGRATION_LOCK_ID})
            await conn.run_sync(_upgrade, revision)

    async def dispose(self) -> None:
        await self.engine.dispose()


def alembic_config(connection: Connection | None = None) -> Config:
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    config.attributes["connection"] = connection
    return config


def _upgrade(connection: Connection, revision: str) -> None:
    command.upgrade(alembic_config(connection), revision)

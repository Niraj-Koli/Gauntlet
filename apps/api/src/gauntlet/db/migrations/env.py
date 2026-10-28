"""Alembic environment. Database.migrate() passes a connection in; otherwise (e.g. when
autogenerating a revision) we connect with the configured DATABASE_URL."""

import asyncio

from alembic import context
from sqlalchemy import Connection

from gauntlet.db.engine import create_engine
from gauntlet.db.models import Base
from gauntlet.settings import get_settings

target_metadata = Base.metadata


def run_with(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=connection.dialect.name == "sqlite",
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_online() -> None:
    engine = create_engine(get_settings().database_url)
    async with engine.begin() as conn:
        await conn.run_sync(run_with)
    await engine.dispose()


connection = context.config.attributes.get("connection")
if connection is not None:
    run_with(connection)
else:
    asyncio.run(run_online())

"""Read-only access to the dashboard tables for Supabase clients, and Realtime on them.

Supabase Realtime only delivers changes a client may SELECT under row-level security, so
the public dashboard tables get a read-only policy for the anon and authenticated roles.
Writes stay closed: only the backend (the table owner) can change anything. The control
tables (commands, floor_state) get no policy and remain private.

Postgres without Supabase's roles and publication is left unchanged.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-22
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PUBLIC_TABLES = [
    "traders",
    "positions",
    "transactions",
    "runs",
    "events",
    "portfolio_snapshots",
    "strategy_versions",
]
POLICY = "dashboard read"


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    for table in PUBLIC_TABLES:
        op.execute(
            f"""
            DO $$ BEGIN
              IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
                CREATE POLICY "{POLICY}" ON {table} FOR SELECT TO anon, authenticated USING (true);
              END IF;
            END $$;
            """
        )
    tables = ", ".join(PUBLIC_TABLES)
    op.execute(
        f"""
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_publication WHERE pubname = 'supabase_realtime') THEN
            ALTER PUBLICATION supabase_realtime ADD TABLE {tables};
          END IF;
        END $$;
        """
    )


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    tables = ", ".join(PUBLIC_TABLES)
    op.execute(
        f"""
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_publication WHERE pubname = 'supabase_realtime') THEN
            ALTER PUBLICATION supabase_realtime DROP TABLE {tables};
          END IF;
        END $$;
        """
    )
    for table in PUBLIC_TABLES:
        op.execute(f'DROP POLICY IF EXISTS "{POLICY}" ON {table}')

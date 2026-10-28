"""Initial schema: traders, positions, transactions, runs, strategies, snapshots, events.

Revision ID: 0001
Revises:
Create Date: 2026-10-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from gauntlet.db.types import Money, UTCDateTime

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = [
    "traders",
    "positions",
    "runs",
    "transactions",
    "strategy_versions",
    "portfolio_snapshots",
    "events",
]


def upgrade() -> None:
    op.create_table(
        "traders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("slug", sa.String(64), nullable=False),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("tagline", sa.String(64), nullable=False),
        sa.Column("model_name", sa.String(128), nullable=False),
        sa.Column("strategy", sa.Text(), nullable=False),
        sa.Column("cash", Money(), nullable=False),
        sa.Column("starting_cash", Money(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at", UTCDateTime(), nullable=False),
        sa.Column("updated_at", UTCDateTime(), nullable=False),
        sa.CheckConstraint("status IN ('active', 'paused')", name="ck_traders_status"),
        sa.UniqueConstraint("slug", name="uq_traders_slug"),
    )
    op.create_table(
        "positions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "trader_id",
            sa.Integer(),
            sa.ForeignKey("traders.id", ondelete="CASCADE", name="fk_positions_trader_id_traders"),
            nullable=False,
        ),
        sa.Column("symbol", sa.String(16), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("avg_cost", Money(), nullable=False),
        sa.UniqueConstraint("trader_id", "symbol", name="uq_positions_trader_symbol"),
        sa.CheckConstraint("quantity > 0", name="ck_positions_quantity_positive"),
    )
    op.create_table(
        "runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "trader_id",
            sa.Integer(),
            sa.ForeignKey("traders.id", ondelete="CASCADE", name="fk_runs_trader_id_traders"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("started_at", UTCDateTime(), nullable=False),
        sa.Column("finished_at", UTCDateTime(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("cost_usd", Money(), nullable=True),
        sa.CheckConstraint("kind IN ('trade', 'rebalance')", name="ck_runs_kind"),
        sa.CheckConstraint("status IN ('running', 'succeeded', 'failed')", name="ck_runs_status"),
    )
    op.create_index("ix_runs_trader_id", "runs", ["trader_id"])
    op.create_table(
        "transactions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "trader_id",
            sa.Integer(),
            sa.ForeignKey("traders.id", ondelete="CASCADE", name="fk_transactions_trader_id_traders"),
            nullable=False,
        ),
        sa.Column(
            "run_id",
            sa.Integer(),
            sa.ForeignKey("runs.id", ondelete="SET NULL", name="fk_transactions_run_id_runs"),
            nullable=True,
        ),
        sa.Column("symbol", sa.String(16), nullable=False),
        sa.Column("side", sa.String(4), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("price", Money(), nullable=False),
        sa.Column("market_price", Money(), nullable=False),
        sa.Column("realized_pnl", Money(), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("created_at", UTCDateTime(), nullable=False),
        sa.CheckConstraint("side IN ('buy', 'sell')", name="ck_transactions_side"),
        sa.CheckConstraint("quantity > 0", name="ck_transactions_quantity_positive"),
    )
    op.create_index("ix_transactions_trader_created", "transactions", ["trader_id", "created_at"])
    op.create_table(
        "strategy_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "trader_id",
            sa.Integer(),
            sa.ForeignKey("traders.id", ondelete="CASCADE", name="fk_strategy_versions_trader_id_traders"),
            nullable=False,
        ),
        sa.Column(
            "run_id",
            sa.Integer(),
            sa.ForeignKey("runs.id", ondelete="SET NULL", name="fk_strategy_versions_run_id_runs"),
            nullable=True,
        ),
        sa.Column("strategy", sa.Text(), nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("created_at", UTCDateTime(), nullable=False),
    )
    op.create_index("ix_strategy_versions_trader_id", "strategy_versions", ["trader_id"])
    op.create_table(
        "portfolio_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "trader_id",
            sa.Integer(),
            sa.ForeignKey("traders.id", ondelete="CASCADE", name="fk_portfolio_snapshots_trader_id_traders"),
            nullable=False,
        ),
        sa.Column("taken_at", UTCDateTime(), nullable=False),
        sa.Column("cash", Money(), nullable=False),
        sa.Column("holdings_value", Money(), nullable=False),
        sa.Column("total_value", Money(), nullable=False),
    )
    op.create_index("ix_portfolio_snapshots_trader_taken", "portfolio_snapshots", ["trader_id", "taken_at"])
    op.create_table(
        "events",
        sa.Column(
            "id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), primary_key=True, autoincrement=True
        ),
        sa.Column(
            "trader_id",
            sa.Integer(),
            sa.ForeignKey("traders.id", ondelete="CASCADE", name="fk_events_trader_id_traders"),
            nullable=True,
        ),
        sa.Column(
            "run_id",
            sa.Integer(),
            sa.ForeignKey("runs.id", ondelete="SET NULL", name="fk_events_run_id_runs"),
            nullable=True,
        ),
        sa.Column("created_at", UTCDateTime(), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
    )
    op.create_index("ix_events_trader_id_id", "events", ["trader_id", "id"])

    if op.get_bind().dialect.name == "postgresql":
        # Supabase exposes the public schema through its REST and Realtime APIs. With RLS on
        # and no policies, anonymous and signed-in clients can't read or write anything;
        # the backend connects as the table owner, which bypasses RLS. Phase 3 adds the
        # read-only policies the dashboard needs.
        for table in [*TABLES, "alembic_version"]:
            op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    for table in reversed(TABLES):
        op.drop_table(table)

"""Indexes for looking things up by run: a run's trace (events) and its trades.

The trace viewer reads a run's events, and deleting a run nulls run_id in both tables;
without these, each of those scans the whole table.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-23
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index("ix_events_run_id_id", "events", ["run_id", "id"])
    op.create_index("ix_transactions_run_id", "transactions", ["run_id"])


def downgrade() -> None:
    op.drop_index("ix_transactions_run_id", table_name="transactions")
    op.drop_index("ix_events_run_id_id", table_name="events")

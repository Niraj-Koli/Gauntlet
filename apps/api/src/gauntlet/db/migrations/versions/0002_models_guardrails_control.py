"""Provider-prefixed model ids, guardrails, structured run results, span ids,
control commands and the scheduler's leader lease.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from gauntlet.db.types import UTCDateTime

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NEW_TABLES = ["commands", "floor_state"]


def _prefixed(model: str) -> str:
    """Old ids were bare ('gpt-5.4-mini', 'deepseek-v4-flash') or OpenRouter paths."""
    if model.startswith(("openai/", "anthropic/", "gemini/", "deepseek/", "xai/", "openrouter/", "demo/")):
        return model
    if "/" in model:
        return f"openrouter/{model}"
    for marker, provider in (
        ("deepseek", "deepseek"),
        ("gemini", "gemini"),
        ("grok", "xai"),
        ("claude", "anthropic"),
    ):
        if marker in model:
            return f"{provider}/{model}"
    return f"openai/{model}"


def upgrade() -> None:
    with op.batch_alter_table("traders") as batch:
        batch.add_column(sa.Column("guardrails", sa.JSON(), nullable=True))
    with op.batch_alter_table("runs") as batch:
        batch.add_column(sa.Column("outlook", sa.String(16), nullable=True))
        batch.add_column(sa.Column("confidence", sa.Float(), nullable=True))
    with op.batch_alter_table("events") as batch:
        batch.add_column(sa.Column("span_id", sa.String(64), nullable=True))
        batch.add_column(sa.Column("parent_id", sa.String(64), nullable=True))

    bind = op.get_bind()
    for trader_id, model in bind.execute(sa.text("SELECT id, model_name FROM traders")).all():
        bind.execute(
            sa.text("UPDATE traders SET model_name = :m WHERE id = :id"),
            {"m": _prefixed(model), "id": trader_id},
        )

    op.create_table(
        "commands",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column(
            "trader_id",
            sa.Integer(),
            sa.ForeignKey("traders.id", ondelete="CASCADE", name="fk_commands_trader_id_traders"),
            nullable=True,
        ),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at", UTCDateTime(), nullable=False),
        sa.Column("processed_at", UTCDateTime(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "kind IN ('run_now', 'pause_trader', 'resume_trader', 'pause_floor', 'resume_floor')",
            name="ck_commands_kind",
        ),
        sa.CheckConstraint("status IN ('pending', 'done', 'failed')", name="ck_commands_status"),
    )
    op.create_index("ix_commands_status_id", "commands", ["status", "id"])
    op.create_table(
        "floor_state",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("paused", sa.Boolean(), nullable=False),
        sa.Column("leader_id", sa.String(64), nullable=True),
        sa.Column("lease_expires_at", UTCDateTime(), nullable=True),
        sa.Column("last_cycle_at", UTCDateTime(), nullable=True),
    )
    bind.execute(sa.text("INSERT INTO floor_state (id, paused) VALUES (1, false)"))

    if bind.dialect.name == "postgresql":
        for table in NEW_TABLES:
            op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.drop_table("floor_state")
    op.drop_table("commands")
    with op.batch_alter_table("events") as batch:
        batch.drop_column("parent_id")
        batch.drop_column("span_id")
    with op.batch_alter_table("runs") as batch:
        batch.drop_column("confidence")
        batch.drop_column("outlook")
    with op.batch_alter_table("traders") as batch:
        batch.drop_column("guardrails")

"""Floor-wide control: pause and resume, queued commands, and the scheduler leader lease.

Only one scheduler process may run the traders at a time. Each process tries to hold a
lease on the floor_state row and renews it while alive; another takes over only once the
lease has expired, so a crashed scheduler is replaced within one lease period.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError

from ..db import Command, Database, FloorState
from ..db.models import COMMAND_KINDS
from ..db.types import utcnow
from .errors import InvalidOrder

FLOOR_ID = 1


@dataclass(frozen=True)
class FloorStatus:
    paused: bool
    leader_id: str | None
    leader_alive: bool
    last_cycle_at: datetime | None = None


class FloorControl:
    def __init__(self, db: Database):
        self.db = db

    async def ensure_state(self) -> None:
        """Create the floor_state row if it's missing (the migration normally adds it)."""
        async with self.db.sessions() as session:
            if await session.get(FloorState, FLOOR_ID) is not None:
                return
        try:
            async with self.db.transaction() as session:
                session.add(FloorState(id=FLOOR_ID, paused=False))
        except IntegrityError:
            pass  # another process created it first

    # --- leader lease ------------------------------------------------------------------

    async def acquire_lease(self, leader_id: str, seconds: int) -> bool:
        """Take or renew the lease. True if this process now leads the floor."""
        now = utcnow()
        async with self.db.transaction() as session:
            result = await session.execute(
                update(FloorState)
                .where(
                    FloorState.id == FLOOR_ID,
                    or_(
                        FloorState.leader_id.is_(None),
                        FloorState.leader_id == leader_id,
                        FloorState.lease_expires_at < now,
                    ),
                )
                .values(leader_id=leader_id, lease_expires_at=now + timedelta(seconds=seconds))
            )
            return result.rowcount == 1  # pyright: ignore[reportAttributeAccessIssue]

    async def release_lease(self, leader_id: str) -> None:
        async with self.db.transaction() as session:
            await session.execute(
                update(FloorState)
                .where(FloorState.id == FLOOR_ID, FloorState.leader_id == leader_id)
                .values(leader_id=None, lease_expires_at=None)
            )

    # --- pause and status --------------------------------------------------------------

    async def status(self) -> FloorStatus:
        async with self.db.sessions() as session:
            state = await session.get(FloorState, FLOOR_ID)
        if state is None:
            return FloorStatus(paused=False, leader_id=None, leader_alive=False)
        alive = state.lease_expires_at is not None and state.lease_expires_at > utcnow()
        return FloorStatus(
            paused=state.paused,
            leader_id=state.leader_id,
            leader_alive=alive,
            last_cycle_at=state.last_cycle_at,
        )

    async def set_paused(self, paused: bool) -> None:
        async with self.db.transaction() as session:
            await session.execute(update(FloorState).where(FloorState.id == FLOOR_ID).values(paused=paused))

    async def mark_cycle(self) -> None:
        async with self.db.transaction() as session:
            await session.execute(
                update(FloorState).where(FloorState.id == FLOOR_ID).values(last_cycle_at=utcnow())
            )

    # --- commands ----------------------------------------------------------------------

    async def enqueue(self, kind: str, trader_id: int | None = None) -> Command:
        if kind not in COMMAND_KINDS:
            raise InvalidOrder(f"Unknown command {kind!r}")
        if kind in ("run_now", "pause_trader", "resume_trader") and trader_id is None:
            raise InvalidOrder(f"{kind} needs a trader")
        async with self.db.transaction() as session:
            command = Command(kind=kind, trader_id=trader_id, status="pending")
            session.add(command)
        return command

    async def pending(self, limit: int = 50) -> list[Command]:
        async with self.db.sessions() as session:
            return list(
                await session.scalars(
                    select(Command).where(Command.status == "pending").order_by(Command.id).limit(limit)
                )
            )

    async def complete(self, command_id: int, error: str | None = None) -> None:
        async with self.db.transaction() as session:
            command = await session.get(Command, command_id)
            if command is not None:
                command.status = "failed" if error else "done"
                command.error = error
                command.processed_at = utcnow()

    async def recent(self, limit: int = 20) -> list[Command]:
        """Most recent first, whatever their status."""
        async with self.db.sessions() as session:
            return list(await session.scalars(select(Command).order_by(Command.id.desc()).limit(limit)))

    async def get(self, command_id: int) -> Command | None:
        async with self.db.sessions() as session:
            return await session.get(Command, command_id)

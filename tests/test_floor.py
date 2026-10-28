"""Floor control (pause, commands, the leader lease) and the scheduler that acts on it."""

import asyncio
from contextlib import suppress
from datetime import timedelta

import pytest
from sqlalchemy import text, update

from gauntlet.db import FloorState
from gauntlet.db.types import utcnow
from gauntlet.domain import InvalidOrder
from gauntlet.domain.accounts import INTERRUPTED
from gauntlet.trading_floor import Scheduler


class StubRunner:
    def __init__(self) -> None:
        self.ran: list[str] = []
        self.running: set[int] = set()

    async def run(self, trader):
        await asyncio.sleep(0)
        self.ran.append(trader.slug)


@pytest.fixture
def scheduler(container) -> Scheduler:
    return Scheduler(container, StubRunner(), leader_id="test-leader")  # pyright: ignore[reportArgumentType]


async def test_only_one_scheduler_leads(container):
    floor = container.floor
    assert await floor.acquire_lease("a", 60)
    assert not await floor.acquire_lease("b", 60)
    assert await floor.acquire_lease("a", 60)  # renewing
    status = await floor.status()
    assert (status.leader_id, status.leader_alive) == ("a", True)
    await floor.release_lease("a")
    assert await floor.acquire_lease("b", 60)


async def test_an_expired_lease_is_taken_over(container):
    floor = container.floor
    assert await floor.acquire_lease("a", 60)
    async with container.db.transaction() as session:
        await session.execute(update(FloorState).values(lease_expires_at=utcnow() - timedelta(seconds=1)))
    assert await floor.acquire_lease("b", 60)


async def test_commands_are_validated_and_queued_in_order(container):
    floor = container.floor
    warren = await container.accounts.get_trader("warren")
    with pytest.raises(InvalidOrder):
        await floor.enqueue("run_now")
    with pytest.raises(InvalidOrder):
        await floor.enqueue("explode")
    first = await floor.enqueue("run_now", warren.id)
    second = await floor.enqueue("pause_floor")
    assert [c.id for c in await floor.pending()] == [first.id, second.id]
    await floor.complete(first.id)
    await floor.complete(second.id, error="boom")
    assert await floor.pending() == []
    done = await floor.get(second.id)
    assert done is not None and (done.status, done.error) == ("failed", "boom")


async def test_the_scheduler_applies_commands(container, scheduler):
    floor, accounts = container.floor, container.accounts
    warren = await accounts.get_trader("warren")
    ray = await accounts.get_trader("ray")
    await floor.enqueue("run_now", warren.id)
    await floor.enqueue("pause_trader", ray.id)
    await floor.enqueue("pause_floor")
    await scheduler.process_commands()
    await scheduler.drain()

    assert scheduler.runner.ran == ["warren"]  # pyright: ignore[reportAttributeAccessIssue]
    assert (await accounts.get_trader("ray")).status == "paused"
    assert (await floor.status()).paused
    assert await floor.pending() == []

    await floor.enqueue("resume_trader", ray.id)
    await floor.enqueue("resume_floor")
    await scheduler.process_commands()
    assert (await accounts.get_trader("ray")).status == "active"
    assert not (await floor.status()).paused


async def test_a_cycle_snapshots_and_runs_active_traders(container, scheduler, market):
    accounts = container.accounts
    ray = await accounts.get_trader("ray")
    await accounts.update_trader(ray.id, status="paused")
    await scheduler.run_cycle()
    assert sorted(scheduler.runner.ran) == ["cathie", "george", "warren"]  # pyright: ignore[reportAttributeAccessIssue]
    assert len(await accounts.snapshots((await accounts.get_trader("warren")).id)) == 1

    market.open = False
    scheduler.runner.ran.clear()  # pyright: ignore[reportAttributeAccessIssue]
    await scheduler.run_cycle()
    assert scheduler.runner.ran == []  # pyright: ignore[reportAttributeAccessIssue]


async def test_run_once_needs_the_lease_and_respects_pause(container, scheduler):
    await container.floor.acquire_lease("someone-else", 60)
    with pytest.raises(RuntimeError, match="Another scheduler"):
        await scheduler.run_once()
    await container.floor.release_lease("someone-else")

    await container.floor.set_paused(True)
    await scheduler.run_once()
    assert scheduler.runner.ran == []  # pyright: ignore[reportAttributeAccessIssue]
    await container.floor.set_paused(False)
    await scheduler.run_once()
    assert len(scheduler.runner.ran) == 4  # pyright: ignore[reportAttributeAccessIssue]


async def test_overlapping_cycles_are_skipped(scheduler):
    assert scheduler.start_cycle()
    assert not scheduler.start_cycle()
    await scheduler.drain()
    assert scheduler.start_cycle()
    await scheduler.drain()


async def test_migration_0002_prefixes_old_model_ids(tmp_path):
    from gauntlet.db import Database

    db = Database(f"sqlite+aiosqlite:///{(tmp_path / 'old.db').as_posix()}")
    await db.migrate("0001")
    async with db.engine.begin() as conn:
        for slug, model in [
            ("a", "gpt-5.4-mini"),
            ("b", "deepseek-v4-flash"),
            ("c", "grok-4.3"),
            ("d", "x/y"),
        ]:
            await conn.execute(
                text(
                    "INSERT INTO traders (slug, name, tagline, model_name, strategy, cash, starting_cash, "
                    "status, created_at, updated_at) VALUES (:s, :s, 't', :m, '', '1', '1', 'active', "
                    "'2026-01-01 00:00:00', '2026-01-01 00:00:00')"
                ),
                {"s": slug, "m": model},
            )
    await db.migrate()
    async with db.engine.connect() as conn:
        models = [row[0] for row in await conn.execute(text("SELECT model_name FROM traders ORDER BY slug"))]
    await db.dispose()
    assert models == ["openai/gpt-5.4-mini", "deepseek/deepseek-v4-flash", "xai/grok-4.3", "openrouter/x/y"]


async def test_a_new_leader_fails_runs_its_predecessor_left_running(container, scheduler):
    accounts = container.accounts
    warren = await accounts.get_trader("warren")
    ray = await accounts.get_trader("ray")
    orphan = await accounts.start_run(warren.id, "trade")
    ours = await accounts.start_run(ray.id, "trade")
    scheduler.runner.running.add(ray.id)  # pyright: ignore[reportAttributeAccessIssue]

    assert await scheduler.renew_lease()
    left = await accounts.get_run(orphan.id)
    assert left is not None and (left.status, left.error) == ("failed", INTERRUPTED)
    assert left.finished_at is not None
    still = await accounts.get_run(ours.id)
    assert still is not None and still.status == "running"

    # Only on taking the lease, not on every renewal.
    late = await accounts.start_run(warren.id, "rebalance")
    assert await scheduler.renew_lease()
    after = await accounts.get_run(late.id)
    assert after is not None and after.status == "running"


async def test_the_loop_beats_for_the_healthcheck(container, scheduler, tmp_path, monkeypatch, capsys):
    from gauntlet import health

    heartbeat = tmp_path / "run" / "heartbeat"
    container.settings.heartbeat_file = heartbeat
    container.settings.command_poll_seconds = 0.01
    monkeypatch.setattr(health, "get_settings", lambda: container.settings)
    with pytest.raises(SystemExit, match="No heartbeat yet"):
        health.main()

    task = asyncio.create_task(scheduler.run_forever())
    for _ in range(200):
        if heartbeat.exists():
            break
        await asyncio.sleep(0.01)
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task
    health.main()
    assert capsys.readouterr().out.startswith("ok")

    container.settings.heartbeat_max_age_seconds = -1  # any heartbeat is now too old
    with pytest.raises(SystemExit, match="Last heartbeat"):
        health.main()


def test_the_floor_process_exits_quietly_when_stopped(monkeypatch, caplog):
    """SIGTERM cancels the main task (see _serve); main() then exits cleanly."""
    import logging

    from gauntlet import trading_floor

    async def cancelled() -> None:
        raise asyncio.CancelledError

    monkeypatch.setattr(trading_floor, "run_floor", cancelled)
    with caplog.at_level(logging.INFO, logger="gauntlet.trading_floor"):
        trading_floor.main()
    assert "Scheduler stopped" in caplog.text


async def test_the_migrations_build_exactly_the_models_schema(container):
    """Alembic owns the schema; a model change without a migration (or the reverse) fails."""
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext

    from gauntlet.db.models import Base

    async with container.db.engine.connect() as conn:
        diff = await conn.run_sync(
            lambda sync: compare_metadata(MigrationContext.configure(sync), Base.metadata)
        )
    assert diff == []

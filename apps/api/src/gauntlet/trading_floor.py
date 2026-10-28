"""The scheduler: every cycle, snapshot every portfolio and run the active traders in
parallel; between cycles, act on queued commands (run now, pause, resume).

Needs the API running, since it hosts the traders' account and market MCP servers.
Several schedulers can be started safely: one holds the leader lease and the others
wait to take over if it stops.

    uv run -m gauntlet.trading_floor
"""

import asyncio
import logging
import os
import signal
import socket
import time
import uuid
from contextlib import suppress
from dataclasses import dataclass, field

import httpx
from agents import add_trace_processor, set_default_openai_key, set_trace_processors

from .container import Container, build_container
from .db import Command, Trader
from .settings import get_settings
from .tracers import EventWriter, LogTracer
from .traders import TraderRunner

logger = logging.getLogger(__name__)


async def check_api(container: Container) -> bool:
    url = f"{container.settings.api_base_url.rstrip('/')}/healthz"
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            (await client.get(url)).raise_for_status()
    except httpx.HTTPError as e:
        logger.warning("The API isn't reachable at %s (%s); traders can't trade until it is", url, e)
        return False
    return True


@dataclass
class Scheduler:
    container: Container
    runner: TraderRunner
    leader_id: str = field(
        default_factory=lambda: f"{socket.gethostname()}-{os.getpid()}-{uuid.uuid4().hex[:6]}"
    )
    is_leader: bool = False
    tasks: set[asyncio.Task] = field(default_factory=set)
    _cycle: asyncio.Task | None = None

    @property
    def settings(self):
        return self.container.settings

    async def renew_lease(self) -> bool:
        was_leader = self.is_leader
        self.is_leader = await self.container.floor.acquire_lease(
            self.leader_id, self.settings.leader_lease_seconds
        )
        if self.is_leader != was_leader:
            logger.info(
                "%s the floor (%s)", "Leading" if self.is_leader else "No longer leading", self.leader_id
            )
        if self.is_leader and not was_leader:
            # Runs a previous leader left behind (it crashed, or was killed mid-run) can't finish.
            if abandoned := await self.container.accounts.abandon_runs(keep=self.runner.running):
                logger.warning("Marked %d interrupted run(s) as failed", abandoned)
        return self.is_leader

    def beat(self) -> None:
        """Tell the health check (python -m gauntlet.health) the loop is alive."""
        if path := self.settings.heartbeat_file:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch()

    def _spawn(self, coroutine) -> asyncio.Task:
        task = asyncio.create_task(coroutine)
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        return task

    async def run_cycle(self) -> None:
        accounts = self.container.accounts
        traders = await accounts.list_traders(active_only=True)
        for trader in traders:
            await accounts.record_snapshot(trader.id)
        await self.container.floor.mark_cycle()
        if self.settings.run_even_when_market_is_closed or await self.container.market.is_market_open():
            await asyncio.gather(*(self.runner.run(trader) for trader in traders))
        else:
            logger.info("Market is closed, skipping run")

    def start_cycle(self) -> bool:
        """Start a cycle unless the last one is still going."""
        if self._cycle and not self._cycle.done():
            logger.info("The previous cycle is still running; skipping this one")
            return False
        self._cycle = self._spawn(self.run_cycle())
        return True

    async def process_commands(self) -> None:
        floor = self.container.floor
        for command in await floor.pending():
            try:
                await self._apply(command)
            except Exception as e:
                logger.exception("Command %s (%s) failed", command.id, command.kind)
                await floor.complete(command.id, error=f"{type(e).__name__}: {e}")
            else:
                await floor.complete(command.id)

    async def _apply(self, command: Command) -> None:
        accounts, floor = self.container.accounts, self.container.floor
        trader: Trader | None = None
        if command.trader_id is not None:
            trader = await accounts.get_trader_by_id(command.trader_id)
        match command.kind:
            case "run_now":
                assert trader is not None
                self._spawn(self.runner.run(trader))
            case "pause_trader":
                assert trader is not None
                await accounts.update_trader(trader.id, status="paused")
            case "resume_trader":
                assert trader is not None
                await accounts.update_trader(trader.id, status="active")
            case "pause_floor":
                await floor.set_paused(True)
            case "resume_floor":
                await floor.set_paused(False)

    async def run_forever(self) -> None:
        interval = self.settings.cycle_minutes * 60
        renew_every = self.settings.leader_lease_seconds / 3
        next_cycle = time.monotonic()
        last_renewal = -renew_every
        while True:
            now = time.monotonic()
            if now - last_renewal >= renew_every:
                await self.renew_lease()
                last_renewal = now
            if self.is_leader:
                await self.process_commands()
                if now >= next_cycle:
                    if not (await self.container.floor.status()).paused:
                        self.start_cycle()
                    else:
                        logger.info("The floor is paused")
                    # Keep to the original slots, so long cycles don't push the schedule later.
                    while next_cycle <= now:
                        next_cycle += interval
            self.beat()
            await asyncio.sleep(self.settings.command_poll_seconds)

    async def run_once(self) -> None:
        """One cycle and any queued commands, then wait for every run to finish."""
        if not await self.renew_lease():
            raise RuntimeError("Another scheduler holds the floor; stop it first")
        await self.process_commands()
        if not (await self.container.floor.status()).paused:
            await self.run_cycle()
        await self.drain()

    async def drain(self) -> None:
        while self.tasks:
            await asyncio.gather(*list(self.tasks), return_exceptions=True)

    async def shutdown(self) -> None:
        for task in list(self.tasks):
            task.cancel()
        with suppress(asyncio.CancelledError):
            await asyncio.gather(*list(self.tasks), return_exceptions=True)
        await self.container.floor.release_lease(self.leader_id)


async def run_floor(container: Container | None = None, once: bool = False) -> None:
    container = container or build_container()
    settings = container.settings
    await container.start()
    if openai_key := settings.secret("openai_api_key"):
        set_default_openai_key(openai_key)
    if settings.demo_mode:
        logger.info("Demo mode: every trader runs the scripted demo model, no API keys needed")
    writer = EventWriter(container.accounts)
    writer.start()
    tracer = LogTracer(writer)
    if settings.secret("openai_api_key") and not settings.demo_mode:
        add_trace_processor(tracer)  # alongside the SDK's export to the OpenAI traces dashboard
    else:
        set_trace_processors([tracer])  # nothing to export to without an OpenAI key
    scheduler = Scheduler(container, TraderRunner(container, tracer))
    await check_api(container)
    try:
        if once:
            await scheduler.run_once()
        else:
            await scheduler.run_forever()
    finally:
        await scheduler.shutdown()
        await writer.close()
        await container.close()


async def _serve() -> None:
    # Containers are stopped with SIGTERM: shut down the way Ctrl+C does, so in-flight runs
    # are recorded as interrupted and the leader lease is released for the next process.
    task = asyncio.current_task()
    assert task is not None
    with suppress(NotImplementedError):  # no signal handlers on Windows event loops
        asyncio.get_running_loop().add_signal_handler(signal.SIGTERM, task.cancel)
    await run_floor()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logger.info("Starting scheduler to run every %d minutes", get_settings().cycle_minutes)
    with suppress(asyncio.CancelledError, KeyboardInterrupt):
        asyncio.run(_serve())
    logger.info("Scheduler stopped")


if __name__ == "__main__":
    main()

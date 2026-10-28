"""End to end without an LLM: a real API server hosting the MCP servers, the real
TraderRunner, and a scripted model making the tool calls an agent would."""

import asyncio
import json
import socket
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack
from decimal import Decimal

import pytest
import uvicorn
from agents import set_trace_processors
from agents.mcp import MCPServerStreamableHttp
from fakes import ScriptedModel, ToolCall

from gauntlet.api import create_app
from gauntlet.container import build_container
from gauntlet.domain.accounts import INTERRUPTED
from gauntlet.mcp_servers import trader_mcp_servers
from gauntlet.security import TraderIdentity, issue_token
from gauntlet.tracers import EventWriter, LogTracer
from gauntlet.traders import TraderRunner


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
async def live(settings, market) -> AsyncIterator:
    """The API serving on a free port, in this test's event loop."""
    port = free_port()
    settings = settings.model_copy(update={"api_base_url": f"http://127.0.0.1:{port}"})
    container = build_container(settings, market=market)
    if container.db.dialect == "postgresql":
        from conftest import _empty_postgres

        await _empty_postgres(container.db)
    server = uvicorn.Server(uvicorn.Config(create_app(container), port=port, log_level="warning"))
    task = asyncio.create_task(server.serve())
    while not server.started:
        await asyncio.sleep(0.05)
    yield container
    server.should_exit = True
    await task


def token_for(container, trader_id: int, run_id: int | None = None) -> str:
    return issue_token(
        container.settings.gauntlet_secret_key.get_secret_value(), TraderIdentity(trader_id, run_id), 60
    )


async def connect(container, token: str) -> MCPServerStreamableHttp:
    server = MCPServerStreamableHttp(
        {"url": container.settings.mcp_accounts_url, "headers": {"Authorization": f"Bearer {token}"}},
        name="accounts",
    )
    await server.connect()
    return server


async def test_account_tools_act_only_on_the_tokens_trader(live):
    """Phase 0 bugs: tools took the account name from the caller, and every successful
    trade was reported back as a tool error."""
    container = live
    warren = await container.accounts.get_trader("warren")
    george = await container.accounts.get_trader("george")
    async with AsyncExitStack() as stack:
        server = await connect(container, token_for(container, warren.id))
        stack.push_async_callback(server.cleanup)

        tools = {t.name: t for t in await server.list_tools()}
        assert set(tools) == {
            "get_balance",
            "get_holdings",
            "get_account",
            "buy_shares",
            "sell_shares",
            "change_strategy",
        }
        for tool in tools.values():
            assert "name" not in tool.inputSchema.get("properties", {})

        result = await server.call_tool("buy_shares", {"symbol": "aapl", "quantity": 3, "rationale": "test"})
        assert not result.isError
        assert result.content[0].text.startswith("Completed. Bought 3 AAPL at $100.20")  # pyright: ignore

        bad = await server.call_tool("buy_shares", {"symbol": "AAPL", "quantity": -3, "rationale": "x"})
        assert bad.isError
        assert "at least 1 share" in bad.content[0].text  # pyright: ignore

    assert [p.quantity for p in (await container.accounts.portfolio(warren.id)).positions] == [3]
    assert (await container.accounts.portfolio(george.id)).positions == []


async def test_mcp_rejects_bad_tokens(live):
    with pytest.raises(Exception):  # noqa: B017 - the SDK wraps the 401 differently by version
        await connect(live, "not-a-token")


class RecordingNotifier:
    name = "test"

    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    async def send(self, title: str, message: str) -> None:
        self.sent.append((title, message))


async def no_sleep(_seconds: float) -> None:
    pass


def runner_for(container, model, tracer=None, **kwargs) -> TraderRunner:
    """A runner on a scripted model (or a model factory), without the researcher's servers."""
    model_for = model if not isinstance(model, ScriptedModel) else (lambda _: model)
    return TraderRunner(
        container,
        tracer or LogTracer(EventWriter(container.accounts)),
        notifier=kwargs.pop("notifier", RecordingNotifier()),
        model_for=model_for,
        researcher_servers=lambda s, name: [],
        sleep=no_sleep,
        **kwargs,
    )


async def stored_run(container, run):
    assert run is not None
    stored = await container.accounts.get_run(run.id)
    assert stored is not None
    return stored


def summary(appraisal: str, outlook: str = "neutral", confidence: float = 0.5) -> str:
    return json.dumps({"appraisal": appraisal, "outlook": outlook, "confidence": confidence})


async def test_a_full_trader_run(live):
    container = live
    accounts = container.accounts
    warren = await accounts.get_trader("warren")
    writer = EventWriter(accounts)
    writer.start()
    tracer = LogTracer(writer)
    set_trace_processors([tracer])
    notifier = RecordingNotifier()
    model = ScriptedModel(
        [
            ToolCall("lookup_share_price", {"symbol": "AAPL"}),
            ToolCall("buy_shares", {"symbol": "AAPL", "quantity": 5, "rationale": "Quality at a fair price"}),
            ToolCall("change_strategy", {"strategy": "Value, with a little more patience"}),
            ToolCall("push", {"message": "Bought 5 AAPL"}),
            # Warren's model is an OpenAI one, so the summary is native structured output.
            summary("Bought 5 AAPL. Portfolio is healthy.", "bullish", 0.7),
        ]
    )
    run = await runner_for(container, model, tracer, notifier=notifier).run(warren)
    await writer.close()

    first = model.requests[0]
    assert "Warren" in first["instructions"]
    assert {"lookup_share_price", "buy_shares", "push", "Researcher"} <= set(first["tools"])
    assert '"cash": 10000.0' in str(first["input"])  # the account report is in the prompt
    assert '"limits"' in str(first["input"])  # and so are its guardrails

    stored = await stored_run(container, run)
    assert (stored.status, stored.kind, stored.error) == ("succeeded", "trade", None)
    assert stored.summary == "Bought 5 AAPL. Portfolio is healthy."
    assert (stored.outlook, stored.confidence) == ("bullish", 0.7)
    assert notifier.sent == [("Gauntlet: Warren", "Bought 5 AAPL")]

    [trade] = await accounts.trades(warren.id)
    assert (trade.symbol, trade.quantity, trade.run_id) == ("AAPL", 5, stored.id)
    assert (await accounts.get_trader("warren")).strategy == "Value, with a little more patience"
    assert [s.total_value for s in await accounts.snapshots(warren.id)] == [Decimal("10000") - Decimal("1")]
    events = await accounts.events(warren.id, last_n=100)
    messages = [e.message for e in events]
    assert messages[0] == "Started: Warren-trading" and messages[-1] == "Ended: Warren-trading"
    assert "Bought 5 of AAPL" in messages
    # Spans form a tree under the trace.
    trace_id = events[0].span_id
    assert trace_id
    assert any(e.parent_id == trace_id for e in events)
    assert all(e.parent_id for e in events[1:-1] if e.kind != "account")
    assert await accounts.next_run_kind(warren.id) == "rebalance"


async def test_other_providers_summarize_in_json_text(live):
    container = live
    george = await container.accounts.get_trader("george")
    george = await container.accounts.update_trader(george.id, model_name="anthropic/claude-opus-5-5")
    model = ScriptedModel(["All in cash for now.\n\n" + summary("Holding cash.")])
    stored = await stored_run(container, await runner_for(container, model).run(george))
    assert "End your final reply with your appraisal as a JSON object" in str(model.requests[0]["input"])
    assert (stored.status, stored.summary, stored.outlook, stored.confidence) == (
        "succeeded",
        "Holding cash.",
        "neutral",
        0.5,
    )


async def test_a_rejected_order_reaches_the_agent_and_the_log(live):
    container = live
    warren = await container.accounts.get_trader("warren")
    await container.accounts.update_trader(warren.id, guardrails={"max_order_value": 500})
    model = ScriptedModel(
        [
            ToolCall("buy_shares", {"symbol": "AAPL", "quantity": 10, "rationale": "too big"}),
            summary("The order was too large."),
        ]
    )
    stored = await stored_run(container, await runner_for(container, model).run(warren))
    assert stored.status == "succeeded"
    assert "the most a single buy may cost is $500.00" in str(model.requests[1]["input"])
    assert await container.accounts.trades(warren.id) == []
    assert any(
        e.message.startswith("Rejected buy of 10 AAPL: This order costs $1,002.00")
        for e in await container.accounts.events(warren.id)
    )


async def test_a_failed_run_is_recorded(live):
    def broken_model(_name):
        raise RuntimeError("no model for you")

    container = live
    warren = await container.accounts.get_trader("warren")
    stored = await stored_run(container, await runner_for(container, broken_model).run(warren))
    assert stored.status == "failed"
    assert stored.error == "RuntimeError: no model for you"


async def test_missing_credentials_fail_clearly(live):
    container = live
    george = await container.accounts.get_trader("george")
    george = await container.accounts.update_trader(george.id, model_name="anthropic/claude-opus-5-5")
    runner = TraderRunner(container, LogTracer(EventWriter(container.accounts)), notifier=RecordingNotifier())
    stored = await stored_run(container, await runner.run(george))
    assert stored.status == "failed"
    assert stored.error is not None and "needs ANTHROPIC_API_KEY" in stored.error


async def test_transient_failures_are_retried(live):
    container = live
    warren = await container.accounts.get_trader("warren")
    attempts = []

    def flaky_servers(settings, token):
        attempts.append(token)
        if len(attempts) == 1:
            raise ConnectionError("API briefly unreachable")
        return trader_mcp_servers(settings, token)

    model = ScriptedModel([summary("Fine.")])
    runner = runner_for(container, model, trader_servers=flaky_servers)
    stored = await stored_run(container, await runner.run(warren))
    assert len(attempts) == 2
    assert stored.status == "succeeded"


async def test_a_run_that_already_traded_is_not_retried(live):
    container = live
    warren = await container.accounts.get_trader("warren")

    class RateLimitError(Exception):
        pass

    class FailsAfterTrading(ScriptedModel):
        async def get_response(self, *args, **kwargs):
            if self.requests:
                raise RateLimitError("slow down")
            return await super().get_response(*args, **kwargs)

    model = FailsAfterTrading([ToolCall("buy_shares", {"symbol": "AAPL", "quantity": 1, "rationale": "x"})])
    stored = await stored_run(container, await runner_for(container, model).run(warren))
    assert stored.status == "failed" and stored.error == "RateLimitError: slow down"
    assert len(await container.accounts.trades(warren.id)) == 1  # bought once, never again


async def test_runs_time_out(live):
    container = live
    container.settings.run_timeout_seconds = 1
    warren = await container.accounts.get_trader("warren")

    class Slow(ScriptedModel):
        async def get_response(self, *args, **kwargs):
            await asyncio.sleep(5)
            return await super().get_response(*args, **kwargs)

    stored = await stored_run(container, await runner_for(container, Slow(["never"])).run(warren))
    assert stored.status == "failed"
    assert stored.error is not None and stored.error.startswith("TimeoutError")


async def test_a_cancelled_run_is_recorded_as_interrupted(live):
    container = live
    warren = await container.accounts.get_trader("warren")
    started = asyncio.Event()

    class Hangs(ScriptedModel):
        async def get_response(self, *args, **kwargs):
            started.set()
            await asyncio.sleep(60)
            return await super().get_response(*args, **kwargs)

    task = asyncio.create_task(runner_for(container, Hangs(["never"])).run(warren))
    await asyncio.wait_for(started.wait(), 10)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    [run] = await container.accounts.runs(warren.id)
    assert (run.status, run.error) == ("failed", INTERRUPTED)


async def test_demo_mode_trades_without_any_api_key(live, market):
    container = live
    container.settings.demo_mode = True
    for symbol in ("IBIT", "ETHA", "ARKK", "COIN", "MSTR", "BITO"):
        market.prices[symbol] = Decimal("60")
    accounts = container.accounts
    cathie = await accounts.get_trader("cathie")
    writer = EventWriter(accounts)
    writer.start()
    tracer = LogTracer(writer)
    set_trace_processors([tracer])
    notifier = RecordingNotifier()
    runner = TraderRunner(container, tracer, notifier=notifier)  # the real model registry

    first = await stored_run(container, await runner.run(cathie))
    second = await stored_run(container, await runner.run(cathie))
    await writer.close()

    assert (first.status, first.kind) == ("succeeded", "trade")
    assert (second.status, second.kind) == ("succeeded", "rebalance")
    assert first.outlook in ("bullish", "neutral", "bearish") and first.summary
    assert first.cost_usd == Decimal(0)
    buys = [t for t in await accounts.trades(cathie.id) if t.side == "buy"]
    assert buys and buys[-1].run_id == first.id
    assert buys[-1].symbol in {"IBIT", "ETHA", "ARKK", "COIN", "MSTR", "BITO"}
    assert len(notifier.sent) == 2
    assert any(e.kind == "generation" for e in await accounts.events(cathie.id, last_n=200))


async def test_a_trader_with_a_run_in_progress_is_skipped(live):
    container = live
    warren = await container.accounts.get_trader("warren")
    runner = runner_for(container, ScriptedModel([]))
    runner.running.add(warren.id)
    assert await runner.run(warren) is None


async def test_a_whole_floor_cycle_in_demo_mode(live, market):
    """The trading floor's entrypoint, once: every trader runs on the demo model through the
    real API and MCP servers, and every run is recorded."""
    from gauntlet.demo import UNIVERSES
    from gauntlet.trading_floor import run_floor

    container = live
    container.settings.demo_mode = True
    for universe in UNIVERSES.values():
        for symbol in universe:
            market.prices.setdefault(symbol, Decimal("80"))
    await run_floor(container, once=True)

    accounts = container.accounts
    for trader in await accounts.list_traders():
        [run] = await accounts.runs(trader.id)
        assert (run.status, run.kind) == ("succeeded", "trade"), (trader.slug, run.error)
    status = await container.floor.status()
    assert status.last_cycle_at is not None and not status.leader_alive  # the lease was released

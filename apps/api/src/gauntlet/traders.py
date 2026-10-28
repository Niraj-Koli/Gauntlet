"""Running one trader: its agent, the researcher it uses as a tool, and their MCP servers."""

import asyncio
import json
import logging
import re
from collections.abc import Awaitable, Callable
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from typing import Literal

import httpx
from agents import Agent, Model, Runner, Tool, function_tool, gen_trace_id, trace
from agents.mcp import MCPServer
from pydantic import BaseModel, Field, ValidationError

from .container import Container
from .db import Run, Trader
from .domain.accounts import INTERRUPTED
from .llm import DEMO_MODEL, MissingCredentials, estimate_cost, resolve_model, uses_native_structured_output
from .mcp_servers import researcher_mcp_servers, trader_mcp_servers
from .notify import Notifier, create_notifier, notify
from .security import TraderIdentity, issue_token
from .settings import Settings
from .templates import (
    rebalance_message,
    research_tool,
    researcher_instructions,
    trade_message,
    trader_instructions,
)
from .tracers import LogTracer, TraceOwner

logger = logging.getLogger(__name__)

MAX_TURNS = 30
RETRY_BASE_SECONDS = 5.0


class RunSummary(BaseModel):
    """The agent's closing appraisal of its portfolio."""

    appraisal: str = Field(description="A brief 2-3 sentence appraisal of the portfolio and its outlook")
    outlook: Literal["bullish", "neutral", "bearish"]
    confidence: float = Field(ge=0, le=1, description="How confident you are in that outlook, 0 to 1")


JSON_SUMMARY_INSTRUCTION = """
End your final reply with your appraisal as a JSON object on its own line, exactly like:
{"appraisal": "<2-3 sentences>", "outlook": "bullish" | "neutral" | "bearish", "confidence": <0.0 to 1.0>}"""


def parse_summary(output: object) -> tuple[str, RunSummary | None]:
    """The run's final output as (summary text, structured summary if there is one).

    Native structured output arrives as a RunSummary. Otherwise the last JSON object in
    the text is used; if there isn't a valid one, the text itself is the summary.
    """
    if isinstance(output, RunSummary):
        return output.appraisal, output
    text = str(output or "").strip()
    for match in reversed(list(re.finditer(r"\{[^{}]*\}", text))):
        try:
            summary = RunSummary.model_validate(json.loads(match.group()))
        except (json.JSONDecodeError, ValidationError):
            continue
        return summary.appraisal, summary
    return text, None


# Errors worth another attempt: the network, rate limits and provider outages.
RETRYABLE_NAMES = {
    "APIConnectionError",
    "APITimeoutError",
    "RateLimitError",
    "InternalServerError",
    "ServiceUnavailableError",
    "Timeout",
}


def is_retryable(error: BaseException) -> bool:
    if isinstance(error, MissingCredentials | TimeoutError):
        return False
    if isinstance(error, ConnectionError | httpx.TransportError) or type(error).__name__ in RETRYABLE_NAMES:
        return True
    if isinstance(error, BaseExceptionGroup):
        return any(is_retryable(e) for e in error.exceptions)
    cause = error.__cause__ or error.__context__
    return cause is not None and is_retryable(cause)


def describe_error(error: BaseException) -> str:
    if isinstance(error, TimeoutError):
        return "TimeoutError: the run took longer than RUN_TIMEOUT_SECONDS"
    if isinstance(error, BaseExceptionGroup) and error.exceptions:
        return describe_error(error.exceptions[0])
    return f"{type(error).__name__}: {error}"


async def _connect(stack: AsyncExitStack, servers: list[MCPServer]) -> list[MCPServer]:
    for server in servers:
        await server.connect()
        stack.push_async_callback(server.cleanup)
    return servers


ServerFactory = Callable[[Settings, str], list[MCPServer]]


@dataclass
class TraderRunner:
    container: Container
    tracer: LogTracer
    notifier: Notifier | None = None
    model_for: Callable[[str], Model | str] | None = None
    """Model id -> model. Defaults to the registry, or the demo model in demo mode."""
    trader_servers: ServerFactory = trader_mcp_servers
    """Called with the settings and the run's MCP token."""
    researcher_servers: ServerFactory = researcher_mcp_servers
    """Called with the settings and the trader's name. Skipped in demo mode."""
    max_turns: int = MAX_TURNS
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep
    running: set[int] = field(default_factory=set)
    """Traders with a run in progress; a new run for one of them is skipped."""

    def __post_init__(self) -> None:
        self.notifier = self.notifier or create_notifier(self.container.settings)

    def model_id(self, trader: Trader) -> str:
        return DEMO_MODEL if self.container.settings.demo_mode else trader.model_name

    def _model(self, model_id: str) -> Model | str:
        if self.model_for:
            return self.model_for(model_id)
        return resolve_model(model_id, self.container.settings)

    async def run(self, trader: Trader) -> Run | None:
        """One trading or rebalancing run, recorded in the runs table. Never raises.

        Returns None if the trader already has a run in progress.
        """
        if trader.id in self.running:
            logger.info("%s is still running; skipping", trader.name)
            return None
        self.running.add(trader.id)
        try:
            return await self._run(trader)
        finally:
            self.running.discard(trader.id)

    async def _run(self, trader: Trader) -> Run:
        accounts = self.container.accounts
        settings = self.container.settings
        kind = await accounts.next_run_kind(trader.id)
        run = await accounts.start_run(trader.id, kind)
        token = issue_token(
            settings.gauntlet_secret_key.get_secret_value(),
            TraderIdentity(trader.id, run.id),
            settings.mcp_token_ttl_seconds,
        )
        owner = TraceOwner(trader.id, run.id)
        model_id = self.model_id(trader)
        name = f"{trader.name}-{'trading' if kind == 'trade' else 'rebalancing'}"
        error: str | None = None
        output: object = None
        try:
            for attempt in range(settings.run_retries + 1):
                trace_id = gen_trace_id()
                self.tracer.register(trace_id, owner)
                metadata = {"run_id": str(run.id), "model": model_id}
                try:
                    async with asyncio.timeout(settings.run_timeout_seconds):
                        with trace(name, trace_id=trace_id, metadata=metadata):
                            output = await self._run_agent(trader, model_id, kind, token)
                    error = None
                    break
                except Exception as e:
                    error = describe_error(e)
                    retry = attempt < settings.run_retries and is_retryable(e)
                    # Never repeat a run that has already traded: the retry could trade again.
                    if retry and not await accounts.run_has_trades(run.id):
                        delay = RETRY_BASE_SECONDS * 2**attempt
                        logger.warning(
                            "Run %s for %s failed (%s); retrying in %.0fs", run.id, trader.name, error, delay
                        )
                        await self.sleep(delay)
                        continue
                    logger.exception("Run %s for %s failed", run.id, trader.name)
                    break
        except asyncio.CancelledError:
            # The floor is shutting down (a deploy, say): record why rather than leave it "running".
            await asyncio.shield(accounts.finish_run(run.id, error=INTERRUPTED))
            raise

        text, summary = parse_summary(output) if error is None else (None, None)
        tokens = (owner.input_tokens, owner.output_tokens)
        await accounts.finish_run(
            run.id,
            error=error,
            summary=text,
            outlook=summary.outlook if summary else None,
            confidence=summary.confidence if summary else None,
            input_tokens=tokens[0] if any(tokens) else None,
            output_tokens=tokens[1] if any(tokens) else None,
            cost_usd=estimate_cost(model_id, *tokens) if any(tokens) or model_id == DEMO_MODEL else None,
        )
        await accounts.record_snapshot(trader.id)
        return run

    async def _run_agent(self, trader: Trader, model_id: str, kind: str, token: str) -> object:
        settings = self.container.settings
        model = self._model(model_id)
        native = uses_native_structured_output(model_id)
        async with AsyncExitStack() as stack:
            trader_servers = await _connect(stack, self.trader_servers(settings, token))
            researchers = [] if settings.demo_mode else self.researcher_servers(settings, trader.name)
            researcher_servers = await _connect(stack, researchers)
            agent = Agent(
                name=trader.name,
                instructions=trader_instructions(trader.name),
                model=model,
                tools=[self._researcher_tool(model, researcher_servers), self._push_tool(trader)],
                mcp_servers=trader_servers,
                output_type=RunSummary if native else None,
            )
            # Read fresh: the strategy may have changed since the trader list was loaded.
            current = await self.container.accounts.get_trader_by_id(trader.id)
            account = json.dumps(await self.container.accounts.report(trader.id))
            build = trade_message if kind == "trade" else rebalance_message
            message = build(trader.name, current.strategy, account)
            if not native:
                message += JSON_SUMMARY_INSTRUCTION
            result = await Runner.run(agent, message, max_turns=self.max_turns)
            return result.final_output

    def _researcher_tool(self, model: Model | str, servers: list[MCPServer]) -> Tool:
        researcher = Agent(
            name="Researcher",
            instructions=researcher_instructions(),
            model=model,
            mcp_servers=servers,
        )
        return researcher.as_tool(tool_name="Researcher", tool_description=research_tool())

    def _push_tool(self, trader: Trader) -> Tool:
        notifier = self.notifier
        assert notifier is not None

        @function_tool(name_override="push")
        async def push(message: str) -> str:
            """Send a push notification with this brief message.

            Args:
                message: A brief message to push
            """
            return await notify(notifier, f"Gauntlet: {trader.name}", message)

        return push

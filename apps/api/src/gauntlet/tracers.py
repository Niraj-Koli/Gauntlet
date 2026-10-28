"""Writes agent traces to the activity log.

Each run registers its trace id with the trader and run it belongs to, so spans are
attributed without parsing ids. Tracing callbacks are synchronous, so events go onto a
queue and a background task writes them to the database in order.
"""

import asyncio
import logging
from contextlib import suppress
from dataclasses import dataclass

from agents import Span, Trace, TracingProcessor

from .db import Event
from .db.types import utcnow
from .domain import AccountService

logger = logging.getLogger(__name__)


@dataclass
class TraceOwner:
    """Who a trace belongs to, and the tokens its model calls used (researcher included)."""

    trader_id: int
    run_id: int | None
    input_tokens: int = 0
    output_tokens: int = 0


class EventWriter:
    """Batches events from any thread onto the database, preserving their order."""

    def __init__(self, accounts: AccountService):
        self.accounts = accounts
        self._queue: asyncio.Queue[Event | None] = asyncio.Queue()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._task = asyncio.create_task(self._drain())

    def emit(self, event: Event) -> None:
        if self._loop is None:
            return
        self._loop.call_soon_threadsafe(self._queue.put_nowait, event)

    async def _drain(self) -> None:
        while True:
            batch = [await self._queue.get()]
            while not self._queue.empty():
                batch.append(self._queue.get_nowait())
            events = [e for e in batch if e is not None]
            if events:
                try:
                    await self.accounts.log_events(events)
                except Exception:
                    logger.exception("Failed to write %d trace events", len(events))
            if None in batch:
                return

    async def close(self) -> None:
        """Write everything queued so far, then stop."""
        if self._task is None:
            return
        self._queue.put_nowait(None)
        with suppress(asyncio.CancelledError):
            await self._task
        self._task = None


class LogTracer(TracingProcessor):
    def __init__(self, writer: EventWriter):
        self.writer = writer
        self.owners: dict[str, TraceOwner] = {}

    def register(self, trace_id: str, owner: TraceOwner) -> TraceOwner:
        """Attribute a trace to a trader's run. Pass the same owner for every retry of a
        run, so its token counts add up across attempts."""
        self.owners[trace_id] = owner
        return owner

    def _write(
        self, owner: TraceOwner, kind: str, message: str, span_id: str | None, parent_id: str | None
    ) -> None:
        self.writer.emit(
            Event(
                trader_id=owner.trader_id,
                run_id=owner.run_id,
                kind=kind,
                message=message,
                span_id=span_id,
                parent_id=parent_id,
                created_at=utcnow(),
            )
        )

    def on_trace_start(self, trace: Trace) -> None:
        if owner := self.owners.get(trace.trace_id):
            self._write(owner, "trace", f"Started: {trace.name}", trace.trace_id, None)

    def on_trace_end(self, trace: Trace) -> None:
        if owner := self.owners.pop(trace.trace_id, None):
            self._write(owner, "trace", f"Ended: {trace.name}", trace.trace_id, None)

    def _on_span(self, span: Span, verb: str) -> None:
        owner = self.owners.get(span.trace_id)
        if owner is None:
            return
        data = span.span_data
        kind = data.type if data else "span"
        message = verb
        if data:
            if data.type:
                message += f" {data.type}"
            if name := getattr(data, "name", None):
                message += f" {name}"
            if server := getattr(data, "server", None):
                message += f" {server}"
        if span.error:
            message += f" {span.error}"
        self._write(owner, kind, message, span.span_id, span.parent_id or span.trace_id)

    @staticmethod
    def _count_usage(owner: TraceOwner, span: Span) -> None:
        usage = getattr(span.span_data, "usage", None)
        if span.span_data and span.span_data.type in ("generation", "response") and isinstance(usage, dict):
            owner.input_tokens += int(usage.get("input_tokens") or 0)
            owner.output_tokens += int(usage.get("output_tokens") or 0)

    def on_span_start(self, span: Span) -> None:
        self._on_span(span, "Started")

    def on_span_end(self, span: Span) -> None:
        self._on_span(span, "Ended")
        if owner := self.owners.get(span.trace_id):
            self._count_usage(owner, span)

    def force_flush(self) -> None:
        pass

    def shutdown(self) -> None:
        pass

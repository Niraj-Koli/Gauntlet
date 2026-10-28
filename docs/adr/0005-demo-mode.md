# 0005: A scripted demo model, so the whole app runs without API keys

**Status:** accepted

## Context

Gauntlet's point is to watch agents trade, but a real run needs keys for one or more model providers and Tavily, and costs money each cycle. Someone looking at the project, a CI job or an end-to-end test shouldn't need any of that.

## Decision

`DEMO_MODE=true` runs every trader on `DemoModel` (`demo.py`), an implementation of the Agents SDK's model interface that makes plausible decisions from the trader's persona and portfolio. It calls the same tools a real model would, through the real MCP servers, guardrails and database:
- research;
- account and price lookups;
- orders sized within limits;
- an occasional strategy change;
- a structured summary of the run.

Prices come from the built-in simulator. Runs cost $0 and are recorded like any other. The dashboard labels demo mode, and the arena says when it compares models that aren't actually being used.

## Consequences

- **Zero setup:** `docker compose up` shows a live floor with no keys, and CI's end-to-end tests run against it.
- **Real code paths:** everything except the LLM itself is exercised, including the MCP token flow, guardrails, the scheduler, tracing and Realtime.
- **Not evidence about real models:** demo results say nothing about how a model would trade. The UI says so rather than presenting them as comparisons.
- **Kept in step with the run contract:** `DemoModel` is test code in production, so it must follow changes to the run contract. A test runs it end to end.

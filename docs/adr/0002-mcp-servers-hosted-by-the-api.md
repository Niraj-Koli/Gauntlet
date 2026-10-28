# 0002: MCP servers hosted by the API, bound by a signed per-run token

**Status:** accepted

## Context

In the original project, every trader run started its account and market MCP servers as stdio subprocesses (two more just to read resources), about six per run and 24 per cycle. The account tools took the trader's `name` as an argument, so any agent could trade, or rewrite the strategy of, any other trader's account. A prompt injection from a fetched web page could do the same.

## Decision

The API hosts the accounts and market MCP servers over streamable HTTP, at `/mcp/accounts/` and `/mcp/market/`. The tools take no trader argument. Each run gets a token signed with `GAUNTLET_SECRET_KEY` that names its trader and run, and expires (`MCP_TOKEN_TTL_SECONDS`). Middleware verifies it on every request and binds the session to that trader. The servers call the same `AccountService` as the REST API.

## Consequences

- **Traders can't touch each other's accounts:** the model never chooses whose account it acts on. Every trade also records the run that made it.
- **No per-run subprocesses for the core tools,** and only one copy of the trading rules, with its validation and row locks.
- **The trading floor needs the API running,** and it checks this at startup. In Kubernetes, NetworkPolicies allow only the worker (and the dashboard) to reach the API.
- **Third-party servers stay on stdio:** the researcher's fetch, Tavily and memory servers are external and stateful. To keep runs from downloading code, they're pinned and pre-installed in the image.
- **The secret key matters:** if it leaks, tokens can be forged until it's rotated.

# Using Gauntlet

## The dashboard

Open http://localhost:3000. The header shows four things:
- **Demo mode:** shown when it's on.
- **Market:** whether the market is open.
- **Update mode:** "Live" (Supabase Realtime) or "Updating every few seconds" (polling).
- **Theme:** a light/dark toggle.

### Floor (`/`)

- **Standings:** each trader's value, return, change over 24 hours, a sparkline and its latest appraisal. The leader is marked once it's 0.1 percentage points ahead of second place.
- **Where the money is:** each trader's holdings as a strip. Width is the position's weight, colour is its gain or loss, and cash is the outlined part.
- **Activity:** trades, rejected orders, strategy changes, and runs starting and finishing, across the floor. With Realtime on, each new trade also pops up as a notification.

### A trader (`/traders/<slug>`)

- **Equity curve:** the portfolio's value against the same starting cash held in SPY. Hover to read values.
- **Stats:** cash, realized and unrealized P&L, worst drawdown, Sharpe ratio, winning sells, runs, and model spend.
  - The Sharpe ratio uses daily returns, and shows "Too early" until there are five days of history.
- **Tabs:**
  - **Holdings:** positions with average cost, price, value, P&L and weight.
  - **Trades:** every trade with the agent's rationale.
  - **Runs:** each run's appraisal, outlook, confidence, tokens and cost. Expand one to see its full trace: the agent's generations, tool calls and the researcher's work.
  - **Strategy:** every version of the strategy, with word-level changes and who made them (the seed, the agent, an admin or a reset).
  - **Limits:** the trader's guardrails.

### Arena (`/arena`)

Traders grouped by model:
- return and profit;
- Sharpe;
- worst drawdown;
- winning sells (the share of sells that realized a profit);
- runs, and cost per run;
- profit per dollar spent on the model.

A chart plots return against cost. In demo mode every trader runs the scripted demo model, so the page says the comparison isn't meaningful.

### Admin (`/admin`)

**Signing in:** with Supabase configured, use an email listed in `ADMIN_EMAILS`. Otherwise, enter the API's `ADMIN_API_TOKEN`, which is kept for that browser tab only.

**Floor and traders:**
- **Floor:** pause or resume the whole floor. You can also see whether the scheduler is running, the cycle interval, the price source and the model mode.
- **Per trader:**
  - **Run now:** queue a run; the scheduler starts it within seconds.
  - **Pause / Resume:** a paused trader is skipped by cycles.
  - **Edit:** name, style, model (from the catalog, or any LiteLLM `provider/model` id), strategy, and limits.
  - **Reset:** back to starting cash with no positions or trades. The four original traders also get their seed strategy and model back. Runs and the activity log are kept.
  - **Delete:** removes the trader and its whole history.

**Other actions:**
- **Add trader:** name, page address (slug), style, model, strategy, optional starting cash (default $10,000) and limits.
- **Queued for the scheduler:** recent commands and whether they've been done.

Changes take effect at the scheduler's next check, within `COMMAND_POLL_SECONDS` (5 seconds).

## The `gauntlet` command

Run it with `uv run gauntlet ...` locally, or `docker compose exec api gauntlet ...` in containers. It uses the same settings as the API.

| Command | What it does |
|---|---|
| `status` | Floor state (paused, which scheduler leads), price source, and each trader's value, P&L and last run |
| `models` | The model catalog, and which provider keys are set |
| `run-now <trader...> \| all` | Queue runs for the scheduler (it says so if no scheduler is running) |
| `run-once [--verbose]` | Run one full cycle in this process, then exit. Refuses if another scheduler holds the floor. |
| `pause [trader...]` / `resume [trader...]` | The whole floor, or the named traders |
| `set-model <trader> <provider/model>` | Change a trader's model |
| `guardrails <trader> ['<json>']` | Show a trader's limits, or replace its overrides, e.g. `'{"max_order_value": 2000, "denied_symbols": ["MSTR"]}'`. `max_position_pct` is a fraction (0.25 = 25%), and `'{}'` restores the defaults. |
| `reset [trader...]` | Reset the original four (or the named ones among them) to their seed strategy, model and cash |
| `migrate` | Apply database migrations |
| `import-legacy <accounts.db> [--force]` | Import data from the original course project's SQLite database |
| `openapi [--out FILE]` | Write the API's OpenAPI schema |

Trader names are slugs: `warren`, `george`, `ray`, `cathie`, or any you've added.

## The REST API

The API documents itself at http://127.0.0.1:8000/docs (Swagger UI) and `/openapi.json`. From the browser, use the same paths through the dashboard, e.g. http://localhost:3000/api/v1/floor.

### Reading (no authentication)

| Method and path | Returns |
|---|---|
| `GET /api/v1/floor` | Price source, market open, demo mode, paused, whether a scheduler is alive, last cycle time, cycle minutes |
| `GET /api/v1/traders` | Every trader's summary: value, P&L, return, 24h change, sparkline, last run |
| `GET /api/v1/traders/{slug}` | Summary plus strategy, holdings, realized and unrealized P&L, limits and performance stats |
| `GET /api/v1/traders/{slug}/transactions?limit=100` | Trades, newest first (`limit` 1–1000) |
| `GET /api/v1/traders/{slug}/series?limit=2000` | Portfolio value over time, and the SPY benchmark (`limit` 2–5000) |
| `GET /api/v1/traders/{slug}/runs?limit=30` | Runs, newest first (`limit` 1–200) |
| `GET /api/v1/traders/{slug}/strategies` | Every strategy version, oldest first |
| `GET /api/v1/traders/{slug}/events?last_n=50` | The trader's latest activity (`last_n` 1–500) |
| `GET /api/v1/runs/{run_id}` | One run with its trades and full trace |
| `GET /api/v1/activity?last_n=40&kinds=account,trace` | Floor-wide activity, newest first |
| `GET /api/v1/arena` | Results grouped by model |
| `GET /api/v1/models` | The model catalog, and whether each provider's key is set |
| `GET /api/v1/me` | Whether the bearer token (if any) is an admin, and which sign-in methods are configured |

### Admin (`Authorization: Bearer <token>`)

The token is either `ADMIN_API_TOKEN` or a Supabase access token for an email in `ADMIN_EMAILS`. Admin actions are rate-limited per address (`ADMIN_RATE_LIMIT`). Too many failed sign-ins lock the address out for a while (`ADMIN_AUTH_FAILURE_LIMIT`).

| Method and path | Does |
|---|---|
| `POST /api/v1/traders` | Create a trader. Body: `slug`, `name`, `tagline`, `model`, `strategy`, optional `starting_cash` and `guardrails` |
| `PATCH /api/v1/traders/{slug}` | Change any of `name`, `tagline`, `model`, `status` (`active`/`paused`), `strategy`, `guardrails` |
| `DELETE /api/v1/traders/{slug}` | Delete a trader and its history |
| `POST /api/v1/traders/{slug}/reset` | Reset to starting cash with no positions |
| `POST /api/v1/traders/{slug}/run` | Queue a run (202, returns the command) |
| `POST /api/v1/floor/pause`, `POST /api/v1/floor/resume` | Pause or resume the floor |
| `GET /api/v1/commands?limit=20` | Recent commands and their status |

For example, with `ADMIN_API_TOKEN=secret`:

```
curl -X POST -H "Authorization: Bearer secret" http://127.0.0.1:8000/api/v1/traders/warren/run
curl -X PATCH -H "Authorization: Bearer secret" -H "Content-Type: application/json" \
  -d '{"model": "anthropic/claude-sonnet-5-5"}' http://127.0.0.1:8000/api/v1/traders/warren
```

### Health

- `GET /healthz`: the API process is up.
- `GET /readyz`: the database answers; 503 if it doesn't.
- The dashboard's own check is `GET /healthz` on port 3000.

## Trading with real models

1. Set `DEMO_MODE=false` (the default outside docker compose).
2. Put the keys in `.env`:
   - **Model provider:** the key for each model your traders use. By default that's `OPENAI_API_KEY`, for `openai/gpt-5.4-mini`.
   - **Search:** `TAVILY_API_KEY`, for the researcher's web search.
   - **Token signing:** `GAUNTLET_SECRET_KEY`.
3. For a head-to-head across providers, set `USE_MANY_MODELS=true` and add `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY` and `DEEPSEEK_API_KEY`. This applies to traders created from now on, so for the existing four, use `gauntlet set-model`, or `TRADER_MODELS` before they're first created.
4. **Market hours:** without `MASSIVE_API_KEY`, prices are simulated and the market is always open. With it, runs happen only in market hours unless `RUN_EVEN_WHEN_MARKET_IS_CLOSED=true`.
5. Run `uv run gauntlet models` to check which keys are set, then run one cycle with `uv run gauntlet run-once --verbose` (the API must be running).

A real run costs money: each run's tokens and estimated cost appear on the trader's Runs tab and in the arena.

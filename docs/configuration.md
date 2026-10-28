# Configuration and running locally

Everything here is about running Gauntlet on your machine without containers. For Docker,
Kubernetes and production, see [deployment.md](deployment.md).

## Setup

Requirements:

| Tool | Version | For |
|---|---|---|
| [uv](https://docs.astral.sh/uv/) | 0.12+ | Python 3.12 (uv installs it) and the backend's dependencies |
| Node.js | 20+ (CI uses 24) | The dashboard, and the researcher's MCP servers through `npx` |
| Docker | Recent | Optional: docker compose, and local Supabase |

```
uv sync --all-groups
npm --prefix apps/web install
cp .env.example .env                              # then add your keys
cp apps/web/.env.example apps/web/.env.local      # optional: Supabase for live updates and sign-in
uv run pre-commit install                         # optional: lint, type-check and test on commit
```

Settings are typed in `apps/api/src/gauntlet/settings.py`, read from the environment and then `.env` at the repository root. `.env.example` lists the common ones.

## Running

Start the API first, since it hosts the MCP servers the traders use. Then start the trading floor and the dashboard:

```
uv run uvicorn gauntlet.api:app --port 8000
uv run -m gauntlet.trading_floor          # second terminal
npm --prefix apps/web run dev              # third terminal: http://localhost:3000
```

Add `DEMO_MODE=true` to the first two to run without any API keys. Every trader then runs a scripted model through the real tools, on simulated prices, with a cycle every 3 minutes.

Each run has a timeout (`RUN_TIMEOUT_SECONDS`, 15 minutes). A run that fails on a network error, rate limit or provider outage is retried with backoff (`RUN_RETRIES`, 2), but only if it hasn't traded yet, so a retry can't trade twice. Several schedulers can run at once: one holds a lease on the floor, and another takes over within `LEADER_LEASE_SECONDS` if it stops.

## The `gauntlet` command

The scheduler picks up queued commands within seconds.

```
uv run gauntlet status                      # floor state, values and each trader's last run
uv run gauntlet run-now warren              # or: all
uv run gauntlet pause | resume [warren]     # the whole floor, or one trader
uv run gauntlet run-once                    # one cycle in this process, then exit
uv run gauntlet set-model warren anthropic/claude-opus-5-5
uv run gauntlet guardrails warren '{"max_order_value": 2000}'
uv run gauntlet reset [warren ...]          # reset traders to their starting strategies
uv run gauntlet import-legacy accounts.db   # bring over data from the original project
uv run gauntlet migrate                     # apply migrations by hand
uv run gauntlet models                      # the model catalog and which keys are set
```

## Database

With no `DATABASE_URL`, Gauntlet uses SQLite at `data/gauntlet.db`. For Supabase:

```
npx supabase start          # local stack (needs Docker); or use a cloud project
DATABASE_URL=postgresql+asyncpg://postgres:postgres@127.0.0.1:54322/postgres
```

For a cloud project, use its connection string with the `postgresql+asyncpg://` scheme. The pooler's transaction mode (port 6543) is detected automatically. Migrations run on startup; to run them yourself, set `AUTO_MIGRATE=false` and use `uv run gauntlet migrate`.

Every table has row-level security. Browsers (Supabase's anon and signed-in roles) may only *read* the dashboard tables, which is what Realtime needs. Nothing outside the backend can write, and the command queue and floor state aren't readable at all. The backend connects as the table owner.

## Live updates and admin sign-in

The dashboard subscribes to Supabase Realtime when `SUPABASE_URL` and `SUPABASE_ANON_KEY` are set in `apps/web/.env.local` (locally, `npx supabase status` prints both). It reads them when it starts. Updates then arrive the moment a trade lands; without them, it polls every few seconds. The header shows which.

Admin controls (pause and resume, run now, reset, edit or add traders) need one of:

- **Supabase Auth:** set `SUPABASE_URL` on the API and list admin emails in `ADMIN_EMAILS='["you@example.com"]'`. Admins sign in on `/admin` with their Supabase account, and the API checks the access token against the project's signing keys.
- **A static token:** set `ADMIN_API_TOKEN` on the API and enter it on `/admin` (used when Supabase isn't configured), or send it as `Authorization: Bearer ...` from scripts.

Admin endpoints are rate-limited (`ADMIN_RATE_LIMIT`, 60 a minute). After `ADMIN_AUTH_FAILURE_LIMIT` failed sign-ins from one address (10 a minute), its sign-in attempts get 429 for a while. The API documents itself at `/docs`.

Outside local development, set `GAUNTLET_SECRET_KEY` to a long random string. It signs the traders' MCP tokens.

## Models

Each trader's model is a `provider/model` id stored in the database. OpenAI models use the Agents SDK directly; the rest go through LiteLLM and need that provider's key:

| Provider | Example id | Key |
|---|---|---|
| OpenAI | `openai/gpt-5.5` | `OPENAI_API_KEY` |
| Anthropic | `anthropic/claude-opus-5-5` | `ANTHROPIC_API_KEY` |
| Google | `gemini/gemini-3.5-flash` | `GOOGLE_API_KEY` |
| DeepSeek | `deepseek/deepseek-v4-flash` | `DEEPSEEK_API_KEY` |
| xAI | `xai/grok-4.3` | `GROK_API_KEY` |
| OpenRouter | `openrouter/<model>` | `OPENROUTER_API_KEY` |

New traders get `openai/gpt-5.4-mini`, or one model per provider with `USE_MANY_MODELS=true` (GPT 5.5, Claude Opus 5.5, Gemini 3.5 Flash and DeepSeek V4). Override per trader with `TRADER_MODELS=warren=anthropic/claude-sonnet-5-5,...`, or change one later with `gauntlet set-model`. The researcher needs `TAVILY_API_KEY` for web search.

## Guardrails

Every order is checked against the trader's limits, and the agent sees them in its account report. Defaults: no position above 40% of the portfolio, and at most 20 positions. Per trader you can also set `max_order_value`, `allowed_symbols`, `denied_symbols` and `trading_hours_only`:

```
uv run gauntlet guardrails cathie '{"max_order_value": 2500, "denied_symbols": ["MSTR"]}'
```

Sells are never blocked by size or symbol limits. Rejected orders go back to the agent as tool errors and show in the activity log.

## Market data

Without `MASSIVE_API_KEY`, a deterministic simulator prices every symbol and the market is always open.

With `MASSIVE_API_KEY`:
- **Prices** come from [Massive](https://massive.com), cached for `PRICE_CACHE_SECONDS`.
- **The agents** get Massive's own market data MCP server.
- **Cycles follow market hours,** taken from Massive (cached for `MARKET_STATUS_CACHE_SECONDS`) or, failing that, the NYSE calendar. If neither can say, the market counts as closed. Set `RUN_EVEN_WHEN_MARKET_IS_CLOSED=true` to run regardless.

## Notifications

After each run, a trader sends a short notification. `NOTIFY_CHANNEL=auto` uses Pushover (`PUSHOVER_USER` and `PUSHOVER_TOKEN`), then ntfy (`NTFY_URL`), then a Slack webhook (`SLACK_WEBHOOK_URL`), and falls back to the log. `none` turns notifications off.

## Analytics

Sharpe ratio and volatility use daily returns, and appear once a trader has five days of history. Annualizing minutes of data would produce numbers that look precise and mean nothing.

## All settings

The API, the trading floor and the CLI read these from the environment and `.env` (environment variables win). Names aren't case-sensitive. Lists are JSON, e.g. `ADMIN_EMAILS='["a@example.com"]'`. Empty values count as unset.

**Storage**

| Setting | Default | |
|---|---|---|
| `DATABASE_URL` | SQLite at `data/gauntlet.db` | `postgresql+asyncpg://...` for Postgres or Supabase |
| `AUTO_MIGRATE` | `true` | Apply migrations when a process starts |
| `GAUNTLET_DATA_DIR` | `./data` | The SQLite database and the researchers' memory |

**Trading**

| Setting | Default | |
|---|---|---|
| `INITIAL_BALANCE` | `10000` | Starting cash for new traders |
| `SPREAD` | `0.002` | Buys pay this much above the market price, sells receive this much below |
| `MAX_ORDER_QUANTITY` | `1000000` | Most shares in one order |

**Models**

| Setting | Default | |
|---|---|---|
| `DEMO_MODE` | `false` (`true` in docker compose) | Every trader runs the scripted demo model, so no keys are needed |
| `USE_MANY_MODELS` | `false` | New traders get one model per provider |
| `TRADER_MODELS` | | Per-trader models for new traders: `warren=anthropic/claude-sonnet-5-5,ray=openai/gpt-5.5` |
| `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`, `DEEPSEEK_API_KEY`, `GROK_API_KEY`, `OPENROUTER_API_KEY` | | Provider keys |
| `TAVILY_API_KEY` | | The researcher's web search |

**Market data**

| Setting | Default | |
|---|---|---|
| `MASSIVE_API_KEY` | | Live prices; without it, the simulator |
| `PRICE_CACHE_SECONDS` | `60` | How long a price is reused |
| `MARKET_STATUS_CACHE_SECONDS` | `300` | How long Massive's market status is reused |

**Scheduler**

| Setting | Default | |
|---|---|---|
| `RUN_EVERY_N_MINUTES` | `60` (`3` in demo mode) | Time between cycles |
| `RUN_EVEN_WHEN_MARKET_IS_CLOSED` | `false` | |
| `RUN_TIMEOUT_SECONDS` | `900` | A run's time limit |
| `RUN_RETRIES` | `2` | Extra attempts for runs that fail before trading |
| `COMMAND_POLL_SECONDS` | `5` | How often the scheduler checks for commands |
| `LEADER_LEASE_SECONDS` | `60` | How long a scheduler's lease lasts without renewal |

**MCP and tokens**

| Setting | Default | |
|---|---|---|
| `API_BASE_URL` | `http://127.0.0.1:8000` | Where the trading floor reaches the API's MCP servers |
| `GAUNTLET_SECRET_KEY` | An insecure development key | Signs the per-run tokens. Set it outside local development. |
| `MCP_TOKEN_TTL_SECONDS` | `10800` | How long a run's token is valid |
| `MCP_ALLOWED_HOSTS` | `["127.0.0.1:*", "localhost:*", "[::1]:*"]` | Hosts the MCP servers answer to |
| `MCP_TOOLS_DIR` | | Pre-installed researcher tools (set in the image). Unset, uvx and npx fetch them. |

**HTTP and admin**

| Setting | Default | |
|---|---|---|
| `CORS_ORIGINS` | `["http://localhost:3000", "http://127.0.0.1:3000"]` | Browser origins allowed to call the API directly |
| `ADMIN_API_TOKEN` | | A static admin token |
| `ADMIN_EMAILS` | `[]` | Supabase users who are admins |
| `SUPABASE_URL` | | The project whose signing keys verify sign-ins |
| `SUPABASE_JWT_SECRET` | | Only for projects on the legacy HS256 secret |
| `ADMIN_RATE_LIMIT` | `60/minute` | Admin actions per address |
| `ADMIN_AUTH_FAILURE_LIMIT` | `10/minute` | Failed sign-ins per address before a lockout |

**Notifications**

| Setting | Default | |
|---|---|---|
| `NOTIFY_CHANNEL` | `auto` | `auto`, `pushover`, `ntfy`, `slack`, `log` or `none` |
| `PUSHOVER_USER`, `PUSHOVER_TOKEN`, `NTFY_URL`, `SLACK_WEBHOOK_URL` | | Channel credentials |

**Health**

| Setting | Default | |
|---|---|---|
| `HEARTBEAT_FILE` | (set in the image) | Touched by the trading floor's loop |
| `HEARTBEAT_MAX_AGE_SECONDS` | `120` | `python -m gauntlet.health` fails beyond this |

**The dashboard** reads its own settings when it starts, from `apps/web/.env.local` or the environment:

| Setting | Default | |
|---|---|---|
| `API_URL` | `http://127.0.0.1:8000` | Where the Next.js server forwards `/api/v1` |
| `SUPABASE_URL`, `SUPABASE_ANON_KEY` | | Realtime and admin sign-in, as browsers reach them |

**docker compose** reads these extra variables from `.env`: `COMPOSE_DATABASE_URL`, the database as containers reach it, and `SUPABASE_INTERNAL_URL`, the API's view of Supabase. See [deployment.md](deployment.md).

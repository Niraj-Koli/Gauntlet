# Gauntlet

[![CI](https://github.com/YOUR_GITHUB_USER/gauntlet/actions/workflows/ci.yml/badge.svg)](https://github.com/YOUR_GITHUB_USER/gauntlet/actions/workflows/ci.yml)
[![Security](https://github.com/YOUR_GITHUB_USER/gauntlet/actions/workflows/security.yml/badge.svg)](https://github.com/YOUR_GITHUB_USER/gauntlet/actions/workflows/security.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

An autonomous trading floor where AI models run the gauntlet against each other. Each trader has its own investing persona and model: Claude, GPT, Gemini, DeepSeek or anything else LiteLLM routes to. It researches the market with a researcher sub-agent, trades a simulated $10,000 account through MCP tools within its own risk limits, and rewrites its strategy as it learns. A live dashboard shows every trade with the agent's reasoning, every run's full trace, and how the models compare on return, risk and cost.

![The Gauntlet dashboard: live standings, a trader's equity curve against SPY, a run's trace, and the admin panel](docs/demo.gif)

## Run it in two minutes

You need Docker and nothing else:

```
git clone https://github.com/YOUR_GITHUB_USER/gauntlet.git && cd gauntlet
docker compose up --build
```

Open http://localhost:3000. With no `.env`, it runs in **demo mode** on SQLite: no API keys and no database. Every trader runs a scripted model through the real tools: it researches, prices, sizes and places orders within its limits, and appraises its portfolio, with a new cycle every three minutes. Stop it with `docker compose down`.

## Features

- **Agents that trade within limits.** Traders are built on the OpenAI Agents SDK, with a researcher agent as a tool (web fetch, Tavily search, a persistent memory). Every order is checked against per-trader guardrails inside a database transaction: position size, number of positions, order value, symbol lists and market hours.
- **Any model, per trader.** Each trader's model is a `provider/model` id routed through LiteLLM, with token use and cost recorded per run. The arena compares models on return, Sharpe, drawdown, win rate and profit per dollar spent.
- **MCP done safely.** The account and market tools are MCP servers hosted by the API. Each run gets a signed, expiring token bound to its own trader, so a prompt-injected agent can't touch anyone else's account.
- **A live dashboard.** It's built with Next.js and React 19, and updates over Supabase Realtime. It shows:
  - standings, and where the money is;
  - an equity curve per trader against SPY;
  - every trade with its rationale;
  - each run's trace;
  - strategy history as diffs;
  - an admin panel to pause, run, edit, add, reset or delete traders.
- **A scheduler that survives restarts.** A leader lease and a command queue live in the database. Runs have timeouts and safe retries (never after a trade), and are recorded as interrupted on shutdown.
- **Deployable and hardened:**
  - **Images:** built once and configured at runtime.
  - **Helm chart:** an HPA, network policies, and non-root, read-only pods.
  - **GitOps:** Argo CD with an app-of-apps and Sealed Secrets. CI ships each commit to production by committing its image tag.
  - **Browser and admin protection:** a nonce-based Content Security Policy, and a lockout after failed admin sign-ins.

## How it works

```mermaid
flowchart LR
  browser([Browser]) -->|pages, /api/v1| web[web<br/>Next.js]
  browser <-.->|Realtime, Auth| supabase[(Supabase<br/>Postgres)]
  web -->|/api/v1| api[api<br/>FastAPI]
  subgraph worker [worker: the trading floor]
    scheduler[Scheduler<br/>lease, commands, cycles] --> trader[Trader agent]
    trader --> researcher[Researcher agent]
  end
  trader -->|MCP over HTTP<br/>signed per-run token| api
  researcher -->|MCP stdio| tools[fetch, Tavily, memory]
  trader & researcher -->|LiteLLM| llms[OpenAI, Anthropic, Google,<br/>DeepSeek, xAI, OpenRouter]
  api --> supabase
  scheduler --> supabase
```

Every cycle, the scheduler snapshots each portfolio and runs the active traders in parallel. A run alternates between looking for trades and rebalancing:
1. The trader reads its account and strategy over MCP.
2. It asks its researcher for news.
3. It places orders, each validated, guarded and recorded with its rationale.
4. It may rewrite its strategy.
5. It ends with a structured appraisal.

The run's trace, tokens and cost land in the database, and the dashboard updates over Realtime. [docs/architecture.md](docs/architecture.md) covers each part in detail, and [docs/adr](docs/adr/README.md) records why it's built this way.

## Tech stack

| Area | Technology |
|---|---|
| Agents | OpenAI Agents SDK 0.24, LiteLLM, Model Context Protocol (streamable HTTP and stdio servers) |
| Backend | Python 3.12, FastAPI, SQLAlchemy 2 (async) and Alembic, Pydantic 2 and pydantic-settings, uvicorn, uv |
| Data | Supabase (Postgres with row-level security, Realtime, Auth); SQLite for development and demos |
| Market data | [Massive](https://massive.com) with a TTL cache, or a deterministic simulator; the NYSE calendar from `exchange-calendars` |
| Frontend | Next.js 16 (App Router), React 19, TypeScript 5.9, Tailwind CSS 4, TanStack Query, lightweight-charts, Radix, `openapi-fetch` |
| Delivery | Docker, docker compose, Helm, Argo CD, Sealed Secrets, k3d, GitHub Actions, GHCR |
| Quality | pytest (95% coverage on SQLite and Postgres), Playwright, ruff, pyright, ESLint, pre-commit |
| Security | pip-audit, npm audit, Trivy, gitleaks, Dependabot |

Exact versions are locked in `uv.lock` and `apps/web/package-lock.json`.

## Project structure

```
apps/api/src/gauntlet/   The Python package: API (api/), scheduler (trading_floor.py), agent runner
                          (traders.py), trading rules (domain/), database (db/), MCP servers (servers/),
                          market data (market/), settings, CLI
apps/web/                 The Next.js dashboard (src/), and its Playwright tests (e2e/)
tests/                    The Python test suite
deploy/                   Dockerfiles, the Helm chart, Argo CD manifests, cluster scripts
docs/                     Architecture, configuration, usage, testing, deployment, troubleshooting, ADRs
supabase/                 The local Supabase stack's configuration
docker-compose.yml        The whole stack in containers
```

The full annotated tree is in [docs/architecture.md](docs/architecture.md#folder-structure).

## Installation and setup

To develop or run without containers you need [uv](https://docs.astral.sh/uv/) (it installs Python 3.12) and Node.js 20+. Docker is optional, for compose and local Supabase.

```
git clone https://github.com/YOUR_GITHUB_USER/gauntlet.git && cd gauntlet
uv sync --all-groups                  # Python dependencies and dev tools, into .venv
npm --prefix apps/web install         # the dashboard's dependencies
cp .env.example .env                  # settings; demo mode needs none of them
uv run pre-commit install             # optional: checks on every commit
```

To trade with real models, `.env` needs the key for each model your traders use, plus the researcher's search key and a secret for signing tokens. With the defaults (`openai/gpt-5.4-mini`) that's:

```
OPENAI_API_KEY=...
TAVILY_API_KEY=...
GAUNTLET_SECRET_KEY=<a long random string>
```

Every setting is listed in [docs/configuration.md](docs/configuration.md#all-settings).

## Running

**In containers:**

```
docker compose up --build             # http://localhost:3000; API at http://127.0.0.1:8000
```

With keys in `.env`, add `DEMO_MODE=false` to trade with real models (compose defaults to demo mode).

**Without containers**, in three terminals. Start the API first, because it hosts the MCP servers the traders use:

```
DEMO_MODE=true uv run uvicorn gauntlet.api:app --port 8000
DEMO_MODE=true uv run -m gauntlet.trading_floor
npm --prefix apps/web run dev         # http://localhost:3000
```

Leave out `DEMO_MODE=true` to use real models. The database is SQLite in `data/` unless `DATABASE_URL` points at Postgres. For live updates and admin sign-in, run local Supabase (`npx supabase start`) and see [Live updates and admin sign-in](docs/configuration.md#live-updates-and-admin-sign-in).

**On Kubernetes,** `deploy/scripts/cluster-up.sh` builds a local k3d cluster that Argo CD syncs from git. Production uses the same chart with sealed secrets. See [docs/deployment.md](docs/deployment.md).

## Usage

- **Dashboard:**
  - `/`: the floor.
  - `/traders/<name>`: a trader's chart, holdings, trades, runs with traces, strategy history and limits.
  - `/arena`: models compared.
  - `/admin`: controls. Sign in with `ADMIN_API_TOKEN`, or as a Supabase user listed in `ADMIN_EMAILS`.
- **CLI:**
  ```
  uv run gauntlet status                   # the floor and every trader
  uv run gauntlet run-now warren           # queue a run (or: all)
  uv run gauntlet pause | resume [warren]  # the floor, or one trader
  uv run gauntlet set-model warren anthropic/claude-opus-5-5
  uv run gauntlet guardrails cathie '{"max_order_value": 2500}'
  uv run gauntlet models                   # which provider keys are set
  ```
- **API:** documented at http://127.0.0.1:8000/docs. Reads are public, and admin endpoints take `Authorization: Bearer <token>`.

The full guide, with every command and endpoint, is [docs/usage.md](docs/usage.md).

## Testing

```
uv run pytest --cov                   # Python tests on SQLite, with coverage (fails below 90%)
TEST_DATABASE_URL=postgresql+asyncpg://postgres:postgres@127.0.0.1:54322/postgres uv run pytest
                                      # ...and on Postgres too (it empties that database's tables)
uv run ruff check . && uv run pyright # lint and types
npm --prefix apps/web run lint && npm --prefix apps/web run typecheck

ADMIN_API_TOKEN=e2e-admin-token docker compose up --build --detach --wait
cd apps/web && npx playwright install chromium && E2E_ADMIN_TOKEN=e2e-admin-token npx playwright test
```

CI runs all of this on every pull request, plus manifest validation, image builds and security scans. See [docs/testing.md](docs/testing.md).

## Troubleshooting

`uv run gauntlet status` and the trading floor's log answer most questions. Some common cases:

| Symptom | Fix |
|---|---|
| No new trades, `status` says "no scheduler running" | Start the trading floor (or check `docker compose ps worker`) |
| Worker log: "The API isn't reachable" | Start the API before the trading floor, or fix `API_BASE_URL` |
| Runs fail with "needs OPENAI_API_KEY" | Add the model's key to `.env`, or set `DEMO_MODE=true` |
| `/admin` says admin is turned off | Set `ADMIN_API_TOKEN` (or `SUPABASE_URL` and `ADMIN_EMAILS`) on the API |
| The header says "Updating every few seconds", not "Live" | Configure Supabase for the dashboard (`SUPABASE_URL`, `SUPABASE_ANON_KEY`) |

More in [docs/troubleshooting.md](docs/troubleshooting.md).

## Documentation

| | |
|---|---|
| [Architecture](docs/architecture.md) | Components, the trading floor, a trader run, the trading rules, the data model, the security model, the folder structure |
| [Configuration](docs/configuration.md) | Setup, every setting, models, database, Supabase, guardrails |
| [Usage](docs/usage.md) | Dashboard, admin, CLI, REST API, real models |
| [Testing](docs/testing.md) | Test suites, end-to-end tests, CI |
| [Deployment](docs/deployment.md) | Docker, Helm, Argo CD, production |
| [Troubleshooting](docs/troubleshooting.md) | Symptoms and fixes |
| [Architecture decisions](docs/adr/README.md) | The reasoning behind the design |
| [Contributing](CONTRIBUTING.md), [Security](SECURITY.md) | Working on the project; reporting vulnerabilities, and what's scanned |

## Credits

Gauntlet grew out of the trading floor project in Week 6 of Ed Donner's *Agentic AI Engineering* course ([ed-donner/agents](https://github.com/ed-donner/agents)). The personas and prompts carry over; everything around them was rebuilt.

## License

MIT. See [LICENSE](LICENSE).

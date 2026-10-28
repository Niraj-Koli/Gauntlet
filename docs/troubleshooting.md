# Troubleshooting

Start with `uv run gauntlet status` (or `docker compose exec api gauntlet status`). It shows:
- whether the floor is paused;
- whether a scheduler is running;
- where prices come from;
- each trader's last run.

Then check the worker's log (`docker compose logs worker`, or the terminal running `gauntlet.trading_floor`).

## Traders aren't trading

| Symptom | Cause and fix |
|---|---|
| `status` says "no scheduler running"; the floor page's last cycle stays old | The trading floor isn't running. Start `uv run -m gauntlet.trading_floor`, or check `docker compose ps worker`. |
| Worker log: `The API isn't reachable at http://... ; traders can't trade until it is` | The worker reaches the API's MCP servers at `API_BASE_URL`. Start the API first, or fix `API_BASE_URL` (in compose it's `http://api:8000`). |
| Worker log: `Market is closed, skipping run` | With `MASSIVE_API_KEY`, runs follow market hours. Set `RUN_EVEN_WHEN_MARKET_IS_CLOSED=true` to run anyway. (The simulator's market is always open.) |
| Worker log: `The floor is paused`, or a trader shows "Paused" | Resume it on `/admin`, or with `gauntlet resume [trader]`. |
| Runs fail with `openai/gpt-5.4-mini needs OPENAI_API_KEY (or set DEMO_MODE=true to run without keys)` | The trader's model has no key. Add the provider's key to `.env` (`gauntlet models` shows which are set), or switch the model with `gauntlet set-model`. |
| Runs fail quickly with errors from the researcher's tools | It needs `TAVILY_API_KEY`, and locally it needs `uvx` (from uv) and `npx` (from Node.js 20+) on the `PATH`. The container image has the tools installed already. |
| Runs fail with `TimeoutError` | The run took longer than `RUN_TIMEOUT_SECONDS` (900). Raise it, or use a faster model. |
| A run shows `Interrupted: the trading floor stopped before the run finished` | The worker stopped (a deploy, Ctrl+C, a crash) during the run. This is expected, and the next cycle runs normally. |
| `gauntlet run-once` says `Another scheduler holds the floor; stop it first` | A trading floor process is already running and leading. Use `gauntlet run-now` to queue a run for it instead. |
| Docker compose runs in demo mode although `.env` has keys | Compose turns demo mode on unless `.env` says otherwise. Add `DEMO_MODE=false`. |

## The API

| Symptom | Cause and fix |
|---|---|
| `/readyz` returns 503 | The database isn't reachable. Check `DATABASE_URL` (`COMPOSE_DATABASE_URL` in compose). For local Supabase, run `npx supabase start`. |
| Worker's MCP calls fail with HTTP 421 `Invalid Host header`; the API logs `Invalid Host header` | The API only accepts MCP requests for the hosts in `MCP_ALLOWED_HOSTS`. Add the host from `API_BASE_URL`, e.g. `MCP_ALLOWED_HOSTS='["api:*", "127.0.0.1:*", "localhost:*"]'`. (Compose and the Helm chart set this for you.) |
| Startup warning: `GAUNTLET_SECRET_KEY is not set; MCP tokens use an insecure development key` | Set `GAUNTLET_SECRET_KEY` to a long random string. Locally on SQLite it's only a warning, but set it anywhere the API is reachable from other machines. |
| Postgres errors about prepared statements | You're on Supabase's transaction pooler: use its URL with port 6543, which Gauntlet detects automatically, or the session pooler or a direct connection. |

## Admin

| Symptom | Cause and fix |
|---|---|
| `/admin` says admin is turned off, or the API answers 403 `Admin access isn't configured` | Set `ADMIN_API_TOKEN`, or `SUPABASE_URL` plus `ADMIN_EMAILS`, on the API, and restart it. |
| 401 `Invalid admin token`, or `Invalid or expired sign-in` | The token is wrong, or the Supabase session expired. Sign in again. The API checks Supabase tokens against `SUPABASE_URL`'s signing keys; for compose, that's `SUPABASE_INTERNAL_URL`. |
| 403 `<email> isn't an admin` | Add the email to `ADMIN_EMAILS` (a JSON list, e.g. `'["you@example.com"]'`). |
| 429 `Too many failed sign-ins; try again in a few minutes` | More than `ADMIN_AUTH_FAILURE_LIMIT` (10 a minute) failed attempts came from your address. Wait, or restart the API to clear it. |
| 429 on admin actions | More than `ADMIN_RATE_LIMIT` (60 a minute) admin actions came from your address. |
| `Strategies are limited to 20,000 characters`, or `Starting cash must be positive and at most $1,000,000,000` | Inputs are bounded so they fit the database. |

## The dashboard

| Symptom | Cause and fix |
|---|---|
| Every page shows an error loading data | The dashboard can't reach the API at `API_URL` (default `http://127.0.0.1:8000`). Start the API, or set `API_URL` in `apps/web/.env.local`. |
| The header says "Updating every few seconds", not "Live" | Supabase Realtime isn't set up. Set `SUPABASE_URL` and `SUPABASE_ANON_KEY` for the dashboard (`npx supabase status` prints both locally), restart it, and use Postgres (Supabase) as the database: Realtime only covers that database. |
| It stays on "Connecting" | Realtime can't connect. Check the URL is the one browsers use (e.g. `http://127.0.0.1:54321`), and that the anon key is right. |
| Sharpe shows "Too early" | The Sharpe ratio uses daily returns, and needs five days of history. |
| The arena compares only one model | Every trader uses the same model by default. In demo mode, the page says the comparison isn't meaningful. |
| The browser console reports a Content Security Policy violation | Only the app's own scripts may run, and it may only connect to itself and `SUPABASE_URL`. A browser extension injecting scripts can trigger this, and is harmless. If Supabase is blocked, check `SUPABASE_URL` matches the address the browser uses. |
| `npm install` warns about install scripts for `unrs-resolver` | Expected. Its script is denied in `package.json` (`allowScripts`) because the optional native packages already provide what it would install. |

## Tests and tooling

| Symptom | Cause and fix |
|---|---|
| `test_the_web_apps_schema_is_current` fails | The API changed. Run `uv run gauntlet openapi --out apps/web/openapi.json && npm --prefix apps/web run gen:api`. |
| `test_the_migrations_build_exactly_the_models_schema` fails | A model changed without a migration, or the reverse. Add a migration in `apps/api/src/gauntlet/db/migrations/versions/`. |
| Local Supabase data disappeared after running tests | Tests with `TEST_DATABASE_URL` empty that database's tables. Starting the API reseeds the four traders. Point the tests at a scratch database if you need to keep data. |
| Playwright admin tests fail with 401 | The stack must run with `ADMIN_API_TOKEN` equal to `E2E_ADMIN_TOKEN` (both `e2e-admin-token` in the docs and CI). |
| `make` isn't found (Windows) | Run the commands in the `Makefile` directly, or the scripts in `deploy/scripts/` with Git Bash. |

## Containers and Kubernetes

| Symptom | Cause and fix |
|---|---|
| Containers can't reach local Supabase | Inside containers, the host is `host.docker.internal` (compose maps it on Linux too). Use it in `COMPOSE_DATABASE_URL` and `SUPABASE_INTERNAL_URL`. |
| The worker container is "unhealthy" | `python -m gauntlet.health` failed: the scheduler loop hasn't touched its heartbeat file within `HEARTBEAT_MAX_AGE_SECONDS` (120). Check the worker's log for what it's stuck on, e.g. an unreachable database. |
| k3d: the server never becomes ready; its log says `kubelet is configured to not run on a host using cgroup v1` | Docker Desktop (WSL2) is on cgroup v1. `cluster-up.sh` handles this; when creating a cluster by hand, add `--k3s-arg "--kubelet-arg=fail-cgroupv1=false@server:*;agent:*"`. |
| k3d on Windows: `kubectl` times out on `host.docker.internal:<port>` | Create the cluster with `--api-port 127.0.0.1:6550`, as `cluster-up.sh` does. |
| A pod is stuck in `CreateContainerConfigError` | Usually the `gauntlet` Secret is missing. Create it (`cluster-up.sh` does locally), or check the SealedSecret was decrypted: `kubectl -n gauntlet get sealedsecret,secret`. |
| Argo CD shows the app as `Degraded` right after a sync | The HPA reports Degraded until metrics arrive, about a minute. |
| Argo CD can't fetch the repository | It deploys from git, so push the repository and set `REPO_URL` (a private repository must be added to Argo CD first). |
| Pods can't pull images from GHCR | GHCR packages start private. Make them public, or add `imagePullSecrets` to the chart's values. |

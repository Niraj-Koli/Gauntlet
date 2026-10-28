# Testing

| Layer | Tool | Where | Runs on |
|---|---|---|---|
| Unit and integration | pytest | `tests/` | SQLite always; Postgres when `TEST_DATABASE_URL` is set |
| Coverage | pytest-cov | `pyproject.toml` (`[tool.coverage]`) | Fails below 90% (currently about 95%) |
| End to end | Playwright | `apps/web/e2e/` | The whole stack in demo mode, under docker compose |
| Static checks | ruff, pyright, ESLint, `tsc` | `pyproject.toml`, `apps/web/` | Every commit (pre-commit) and every pull request |
| Deployment | Helm lint, kubeconform, `docker compose config` | `deploy/` | Every pull request |
| Security | pip-audit, npm audit, Trivy, gitleaks | `.github/workflows/security.yml` | Pull requests, `main`, weekly |

No test calls a real LLM or a paid API. Agents are driven by a scripted model (`tests/fakes.py`), or by the demo model.

## Python tests

```
uv sync --all-groups
uv run pytest                     # SQLite, about a minute
uv run pytest --cov               # with coverage (fails below 90%)
uv run pytest tests/test_api_v1.py -k admin    # a subset
```

To run every test on Postgres as well, point `TEST_DATABASE_URL` at a database whose contents you don't need, since the tests empty its tables. Local Supabase works:

```
npx supabase start
TEST_DATABASE_URL=postgresql+asyncpg://postgres:postgres@127.0.0.1:54322/postgres uv run pytest
```

Each test that uses the database then runs twice, once per backend.

| File | Covers |
|---|---|
| `test_account_service.py` | Buying and selling: validation, cash, average cost, realized P&L, concurrent orders, bounds |
| `test_guardrails.py` | Every limit, and how rejections reach the agent |
| `test_trader_run.py` | Real API and MCP servers on a free port, driven by a scripted model. Covers the token binding, a full run, retries (never after a trade), timeouts, cancellation, demo mode, and a whole floor cycle |
| `test_api_v1.py` | Every endpoint, admin auth (static token, Supabase HS256 tokens, the lockout), validation, and that `apps/web/openapi.json` is current |
| `test_floor.py` | The leader lease, commands, cycles, recovering interrupted runs, the heartbeat health check, and that the migrations build exactly the models' schema |
| `test_cli.py` | Every `gauntlet` command, in-process |
| `test_market_*.py` | The simulator, the Massive provider (with a fake client), caching and NYSE hours |
| `test_analytics.py` | Sharpe ratio, volatility, drawdown and win rate |
| `test_llm_and_notify.py` | Model routing, costs, missing keys, notification channels |
| `test_security.py` | Signing and verifying per-run tokens |
| `test_mcp_tools.py` | The pinned third-party MCP servers, and installing them |
| `test_legacy_import.py` | Importing the original project's database |

## Static checks

```
uv run ruff check . && uv run ruff format --check .
uv run pyright
npm --prefix apps/web run lint
npm --prefix apps/web run typecheck
```

`uv run pre-commit install` runs them all, plus the Python tests, before each commit. `uv run pre-commit run --all-files` runs them once.

## End-to-end tests

These drive the dashboard in Chromium on a desktop screen, and the browsing tests also run at phone size:
- the floor, a trader's page with a run's trace, and the arena;
- the unknown-trader page;
- the Content Security Policy (no violations);
- a rejected admin token;
- pausing and resuming the floor;
- "run now";
- adding and then deleting a trader.

```
ADMIN_API_TOKEN=e2e-admin-token docker compose up --build --detach --wait
cd apps/web
npx playwright install chromium            # once
E2E_ADMIN_TOKEN=e2e-admin-token npx playwright test
npx playwright show-report                 # after a failure: traces and screenshots
docker compose down
```

`E2E_BASE_URL` points the tests at another address (the default is http://localhost:3000). The admin tests resume the floor before each test, so they don't depend on each other.

## Deployment manifests

```
helm lint --strict deploy/helm/gauntlet -f deploy/helm/gauntlet/values-prod.yaml
helm template gauntlet deploy/helm/gauntlet -f deploy/helm/gauntlet/values-prod.yaml | kubeconform -strict -summary
docker compose config --quiet
```

CI also renders the chart with a placeholder sealed secret, renders the Argo CD app-of-apps chart, and validates the CRDs against the [datreeio catalog](https://github.com/datreeio/CRDs-catalog).

## Continuous integration

| Workflow | When | Jobs |
|---|---|---|
| `ci.yml` | Pull requests; also before each release | Python (tests on SQLite and Postgres 17, with coverage), web (lint, types, build), manifests, image builds, end-to-end |
| `security.yml` | Pull requests, `main`, Mondays | pip-audit, npm audit, gitleaks over the full history, Trivy on the config and both images |
| `release.yml` | Push to `main` | CI, then push both images to GHCR, then commit the new tags to `values-prod.yaml` |

## After changing the API

The dashboard's types come from the API's schema, and `test_the_web_apps_schema_is_current` fails until you regenerate them:

```
uv run gauntlet openapi --out apps/web/openapi.json
npm --prefix apps/web run gen:api
```

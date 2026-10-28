"""/api/v1: the dashboard's reads and the admin controls."""

import time
from collections.abc import AsyncIterator

import httpx
import jwt
import pytest
from pydantic import SecretStr

from gauntlet.api import create_app

TOKEN = "test-admin-token"
JWT_SECRET = "test-jwt-secret-that-is-at-least-32-characters"
ADMIN = {"Authorization": f"Bearer {TOKEN}"}


def supabase_token(email: str, secret: str = JWT_SECRET, expires_in: int = 3600) -> str:
    claims = {"sub": "user-1", "email": email, "aud": "authenticated", "exp": int(time.time()) + expires_in}
    return jwt.encode(claims, secret, algorithm="HS256")


@pytest.fixture
async def api(container, settings) -> AsyncIterator[httpx.AsyncClient]:
    settings.admin_api_token = SecretStr(TOKEN)
    settings.supabase_jwt_secret = SecretStr(JWT_SECRET)
    settings.admin_emails = ["boss@example.com"]
    transport = httpx.ASGITransport(app=create_app(container))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def get(api, path: str, **kwargs):
    response = await api.get(path, **kwargs)
    assert response.status_code == 200, response.text
    return response.json()


# --- reading ----------------------------------------------------------------------------


async def test_floor(api):
    floor = await get(api, "/api/v1/floor")
    assert floor == {
        "market_source": "fake",
        "market_open": True,
        "demo_mode": False,
        "paused": False,
        "scheduler_alive": False,
        "last_cycle_at": None,
        "cycle_minutes": 60,
    }


async def test_trader_list_and_detail(api, accounts):
    warren = await accounts.get_trader("warren")
    await accounts.record_snapshot(warren.id)
    await accounts.buy(warren.id, "AAPL", 10, "cheap")
    await accounts.sell(warren.id, "AAPL", 4, "trim")

    traders = await get(api, "/api/v1/traders")
    assert [t["slug"] for t in traders] == ["warren", "george", "ray", "cathie"]
    first = traders[0]
    assert first["model"] == "openai/gpt-5.4-mini" and first["model_label"] == "GPT 5.4 mini"
    assert first["total_value"] == pytest.approx(first["cash"] + 600)
    assert first["return_pct"] == pytest.approx(first["pnl"] / 100)
    assert first["sparkline"][0] == 10000 and first["sparkline"][-1] == first["total_value"]
    assert first["positions"] == 1 and first["last_run"] is None and not first["running"]

    detail = await get(api, "/api/v1/traders/warren")
    assert "named in homage" in detail["strategy"]
    [holding] = detail["holdings"]
    assert holding["symbol"] == "AAPL" and holding["weight_pct"] == pytest.approx(
        600 / detail["total_value"] * 100
    )
    assert detail["guardrails"]["max_position_pct"] == "0.4" and detail["guardrail_overrides"] == {}
    assert (
        detail["stats"]["trades"] == 2 and detail["stats"]["sells"] == 1 and detail["stats"]["win_rate"] == 0
    )
    assert detail["realized_pnl"] == pytest.approx(4 * (99.8 - 100.2))

    trades = await get(api, "/api/v1/traders/warren/transactions?limit=1")
    assert [(t["side"], t["quantity"]) for t in trades] == [("sell", 4)]
    assert (await api.get("/api/v1/traders/nobody")).status_code == 404


async def test_series_includes_a_spy_benchmark(api, accounts):
    warren = await accounts.get_trader("warren")
    await accounts.record_snapshot(warren.id)
    await accounts.buy(warren.id, "AAPL", 10, "x")
    await accounts.record_snapshot(warren.id)
    series = await get(api, "/api/v1/traders/warren/series")
    assert [p["value"] for p in series["portfolio"]] == [10000, 9998]
    assert series["benchmark_symbol"] == "SPY"
    assert [p["value"] for p in series["benchmark"]] == [10000, 10000]  # the fake market's SPY is flat


async def test_runs_and_the_trace_viewer(api, accounts):
    warren = await accounts.get_trader("warren")
    run = await accounts.start_run(warren.id, "trade")
    await accounts.buy(warren.id, "AAPL", 1, "in the run", run_id=run.id)
    await accounts.finish_run(run.id, summary="Done.", outlook="bullish", confidence=0.6)

    [brief] = await get(api, "/api/v1/traders/warren/runs")
    assert (brief["id"], brief["status"], brief["outlook"]) == (run.id, "succeeded", "bullish")
    detail = await get(api, f"/api/v1/runs/{run.id}")
    assert detail["trader_slug"] == "warren"
    assert [t["symbol"] for t in detail["trades"]] == ["AAPL"]
    assert [e["message"] for e in detail["events"]] == ["Bought 1 of AAPL"]
    assert (await api.get("/api/v1/runs/999")).status_code == 404


async def test_strategies_events_arena_and_models(api, accounts):
    warren = await accounts.get_trader("warren")
    await accounts.change_strategy(warren.id, "New plan")
    strategies = await get(api, "/api/v1/traders/warren/strategies")
    assert [v["source"] for v in strategies] == ["seed", "agent"]
    events = await get(api, "/api/v1/traders/warren/events?last_n=1")
    assert events[0]["message"] == "Changed strategy"

    [row] = await get(api, "/api/v1/arena")
    assert row["model"] == "openai/gpt-5.4-mini" and row["traders"] == ["Warren", "George", "Ray", "Cathie"]
    models = {m["id"]: m for m in await get(api, "/api/v1/models")}
    assert models["demo/scripted"]["configured"] and not models["anthropic/claude-opus-5-5"]["configured"]


async def test_openapi_documents_v1(api):
    schema = await get(api, "/openapi.json")
    assert "/api/v1/traders/{slug}" in schema["paths"]
    assert all(path.startswith("/api/v1/") for path in schema["paths"])


# --- admin --------------------------------------------------------------------------------


async def test_me(api):
    assert (await get(api, "/api/v1/me"))["admin"] is False
    me = await get(api, "/api/v1/me", headers=ADMIN)
    assert (me["admin"], me["method"], me["auth_configured"]) == (True, "token", True)
    signed_in = await get(
        api, "/api/v1/me", headers={"Authorization": f"Bearer {supabase_token('Boss@Example.com')}"}
    )
    assert (signed_in["admin"], signed_in["email"], signed_in["method"]) == (
        True,
        "boss@example.com",
        "supabase",
    )


async def test_admin_endpoints_need_an_admin(api):
    assert (await api.post("/api/v1/floor/pause")).status_code == 401
    bad = {"Authorization": "Bearer nope"}
    assert (await api.post("/api/v1/floor/pause", headers=bad)).status_code == 401
    stranger = {"Authorization": f"Bearer {supabase_token('someone@example.com')}"}
    response = await api.post("/api/v1/floor/pause", headers=stranger)
    assert response.status_code == 403 and "isn't an admin" in response.json()["detail"]
    expired = {"Authorization": f"Bearer {supabase_token('boss@example.com', expires_in=-10)}"}
    assert (await api.post("/api/v1/floor/pause", headers=expired)).status_code == 401
    forged = {"Authorization": f"Bearer {supabase_token('boss@example.com', secret='x' * 40)}"}
    assert (await api.post("/api/v1/floor/pause", headers=forged)).status_code == 401
    boss = {"Authorization": f"Bearer {supabase_token('boss@example.com')}"}
    assert (await api.post("/api/v1/floor/pause", headers=boss)).status_code == 200


async def test_repeated_failed_sign_ins_lock_the_caller_out(container, settings):
    settings.admin_api_token = SecretStr(TOKEN)
    settings.admin_auth_failure_limit = "3/minute"
    transport = httpx.ASGITransport(app=create_app(container), client=("203.0.113.9", 1234))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        guesses = [{"Authorization": f"Bearer guess-{n}"} for n in range(3)]
        for guess in guesses:
            assert (await client.post("/api/v1/floor/pause", headers=guess)).status_code == 401
        # Locked out now, even with the right token, and /me is no way around it.
        assert (await client.post("/api/v1/floor/pause", headers=ADMIN)).status_code == 429
        assert (await client.get("/api/v1/me", headers=guesses[0])).status_code == 429
        # Reading the dashboard doesn't need a token, so it isn't affected.
        assert (await client.get("/api/v1/floor")).status_code == 200
    other = httpx.ASGITransport(app=create_app(container), client=("198.51.100.7", 1234))
    async with httpx.AsyncClient(transport=other, base_url="http://test") as client:
        assert (await client.get("/api/v1/me", headers=ADMIN)).json()["admin"] is True


async def test_admin_is_closed_when_not_configured(container, settings):
    transport = httpx.ASGITransport(app=create_app(container))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/v1/floor/pause", headers=ADMIN)
    assert response.status_code == 403 and "isn't configured" in response.json()["detail"]


async def test_floor_controls_and_commands(api):
    paused = await api.post("/api/v1/floor/pause", headers=ADMIN)
    assert paused.json()["paused"] is True
    assert (await api.post("/api/v1/floor/resume", headers=ADMIN)).json()["paused"] is False
    queued = await api.post("/api/v1/traders/ray/run", headers=ADMIN)
    assert queued.status_code == 202 and queued.json()["kind"] == "run_now"
    commands = (await api.get("/api/v1/commands", headers=ADMIN)).json()
    assert commands[0]["id"] == queued.json()["id"] and commands[0]["status"] == "pending"


async def test_create_update_reset_and_delete_a_trader(api, accounts):
    body = {
        "slug": "nancy",
        "name": "Nancy",
        "tagline": "Tech",
        "model": "claude-sonnet-5-5",
        "strategy": "Large-cap technology leaders.",
        "starting_cash": 25000,
        "guardrails": {"max_positions": 5},
    }
    created = await api.post("/api/v1/traders", json=body, headers=ADMIN)
    assert created.status_code == 201, created.text
    assert created.json()["model"] == "anthropic/claude-sonnet-5-5" and created.json()["total_value"] == 25000
    assert (await api.post("/api/v1/traders", json=body, headers=ADMIN)).status_code == 400
    bad = {**body, "slug": "Bad Slug"}
    assert (await api.post("/api/v1/traders", json=bad, headers=ADMIN)).status_code == 422

    patch = {"status": "paused", "strategy": "Only semiconductors.", "guardrails": {"max_order_value": 1000}}
    updated = await api.patch("/api/v1/traders/nancy", json=patch, headers=ADMIN)
    assert updated.status_code == 200 and updated.json()["status"] == "paused"
    detail = (await api.get("/api/v1/traders/nancy")).json()
    assert detail["strategy"] == "Only semiconductors."
    assert detail["guardrail_overrides"] == {"max_order_value": 1000}
    sources = [v["source"] for v in (await api.get("/api/v1/traders/nancy/strategies")).json()]
    assert sources == ["admin", "admin"]
    invalid = await api.patch(
        "/api/v1/traders/nancy", json={"guardrails": {"max_position_pct": 5}}, headers=ADMIN
    )
    assert invalid.status_code == 400

    nancy = await accounts.get_trader("nancy")
    await accounts.update_trader(nancy.id, guardrails={})
    await accounts.buy(nancy.id, "AAPL", 10, "x")
    reset = await api.post("/api/v1/traders/nancy/reset", headers=ADMIN)
    assert reset.json()["total_value"] == 25000 and reset.json()["positions"] == 0

    assert (await api.delete("/api/v1/traders/nancy", headers=ADMIN)).status_code == 204
    assert (await api.get("/api/v1/traders/nancy")).status_code == 404


async def test_admin_endpoints_are_rate_limited(container, settings):
    settings.admin_api_token = SecretStr(TOKEN)
    settings.admin_rate_limit = "2/minute"
    transport = httpx.ASGITransport(app=create_app(container))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        codes = [(await client.post("/api/v1/floor/pause", headers=ADMIN)).status_code for _ in range(3)]
    assert codes == [200, 200, 429]


async def test_cors_allows_the_dashboard(api):
    response = await api.options(
        "/api/v1/traders",
        headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "GET"},
    )
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
    other = await api.options(
        "/api/v1/traders", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"}
    )
    assert "access-control-allow-origin" not in other.headers


async def test_mcp_endpoints_require_a_trader_token(api):
    assert (await api.post("/mcp/accounts/", json={})).status_code == 401
    response = await api.post("/mcp/market/", json={}, headers={"Authorization": "Bearer nope"})
    assert response.status_code == 401
    # An admin token is not a trader token.
    assert (await api.post("/mcp/accounts/", json={}, headers=ADMIN)).status_code == 401


async def test_health_and_readiness(api):
    assert (await get(api, "/healthz")) == {"status": "ok"}
    assert (await get(api, "/readyz")) == {"status": "ready"}


def test_the_web_apps_schema_is_current(container):
    """apps/web/openapi.json generates the dashboard's TypeScript types; regenerate both with
    `uv run gauntlet openapi --out apps/web/openapi.json && npm --prefix apps/web run gen:api`."""
    import json
    from pathlib import Path

    committed = json.loads((Path(__file__).parents[1] / "apps/web/openapi.json").read_text(encoding="utf-8"))
    assert create_app(container).openapi() == committed

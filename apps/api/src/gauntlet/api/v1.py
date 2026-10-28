"""/api/v1: the dashboard's read endpoints and the admin control endpoints."""

from collections import defaultdict
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from slowapi import Limiter

from ..container import Container
from ..db import Trader
from ..db.types import utcnow
from ..domain import Guardrails, TraderSeed, TradingError, UnknownTrader
from ..domain.analytics import change_since, performance
from ..llm import CATALOG, PROVIDER_KEYS, model_label, normalize_model_id, provider_of
from ..personas import default_traders
from . import schemas as s
from .auth import AdminAuth, Principal

SPARKLINE_POINTS = 60
BENCHMARK = "SPY"


def build_router(container: Container, auth: AdminAuth, limiter: Limiter) -> APIRouter:
    accounts, floor, market, settings = (
        container.accounts,
        container.floor,
        container.market,
        container.settings,
    )
    router = APIRouter(prefix="/api/v1")
    admin_limit = limiter.limit(settings.admin_rate_limit)

    def require_admin(request: Request) -> Principal:
        return auth.require_admin(request)

    admin_only = [Depends(require_admin)]

    async def trader_or_404(slug: str) -> Trader:
        try:
            return await accounts.get_trader(slug)
        except UnknownTrader as e:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from e

    def bad_request(e: Exception) -> HTTPException:
        return HTTPException(status.HTTP_400_BAD_REQUEST, str(e))

    async def summary(trader: Trader, portfolio=None, snapshots=None) -> s.TraderSummary:
        """The trader's card; pass the portfolio and snapshots when the caller has them."""
        portfolio = portfolio or await accounts.portfolio(trader.id)
        snapshots = snapshots if snapshots is not None else await accounts.snapshots(trader.id)
        runs = await accounts.runs(trader.id, limit=1)
        last = runs[0] if runs else None
        values = [float(x.total_value) for x in snapshots[-(SPARKLINE_POINTS - 1) :]]
        change = change_since(snapshots, portfolio.total_value, utcnow())
        return s.TraderSummary(
            id=trader.id,
            slug=trader.slug,
            name=trader.name,
            tagline=trader.tagline,
            model=trader.model_name,
            model_label=model_label(trader.model_name),
            status=trader.status,  # pyright: ignore[reportArgumentType]
            cash=float(portfolio.cash),
            holdings_value=float(portfolio.holdings_value),
            total_value=float(portfolio.total_value),
            starting_cash=float(trader.starting_cash),
            pnl=float(portfolio.pnl),
            return_pct=float(portfolio.pnl / trader.starting_cash * 100) if trader.starting_cash else 0.0,
            change_24h=float(change) if change is not None else None,
            positions=len(portfolio.positions),
            sparkline=[*values, float(portfolio.total_value)],
            last_run=s.RunBrief.model_validate(last) if last else None,
            running=bool(last and last.status == "running"),
        )

    # --- reading ------------------------------------------------------------------------

    @router.get("/floor", response_model=s.FloorOut)
    async def get_floor():
        state = await floor.status()
        return s.FloorOut(
            market_source=market.name,
            market_open=await market.is_market_open(),
            demo_mode=settings.demo_mode,
            paused=state.paused,
            scheduler_alive=state.leader_alive,
            last_cycle_at=state.last_cycle_at,
            cycle_minutes=settings.cycle_minutes,
        )

    @router.get("/traders", response_model=list[s.TraderSummary])
    async def list_traders():
        """Every trader with its current value, profit and latest run."""
        return [await summary(t) for t in await accounts.list_traders()]

    @router.get("/traders/{slug}", response_model=s.TraderDetail)
    async def get_trader(slug: str):
        trader = await trader_or_404(slug)
        portfolio = await accounts.portfolio(trader.id)
        snapshots = await accounts.snapshots(trader.id)
        base = await summary(trader, portfolio, snapshots)
        total = portfolio.total_value or Decimal(1)
        stats = performance(
            snapshots,
            portfolio.total_value,
            trader.starting_cash,
            await accounts.trades(trader.id, limit=10_000),
            await accounts.runs(trader.id, limit=10_000),
        )
        return s.TraderDetail(
            **base.model_dump(),
            strategy=trader.strategy,
            realized_pnl=float(portfolio.realized_pnl),
            unrealized_pnl=float(portfolio.unrealized_pnl),
            holdings=[
                s.PositionOut(
                    symbol=p.symbol,
                    quantity=p.quantity,
                    avg_cost=float(p.avg_cost),
                    price=float(p.price),
                    market_value=float(p.market_value),
                    unrealized_pnl=float(p.unrealized_pnl),
                    weight_pct=float(p.market_value / total * 100),
                )
                for p in portfolio.positions
            ],
            guardrails=Guardrails.for_trader(trader.guardrails).model_dump(mode="json"),
            guardrail_overrides=trader.guardrails or {},
            stats=s.Stats(**stats.__dict__),
        )

    @router.get("/traders/{slug}/transactions", response_model=list[s.TradeOut])
    async def get_transactions(slug: str, limit: Annotated[int, Query(ge=1, le=1000)] = 100):
        """Most recent first."""
        trader = await trader_or_404(slug)
        return await accounts.trades(trader.id, limit=limit)

    @router.get("/traders/{slug}/series", response_model=s.SeriesOut)
    async def get_series(slug: str, limit: Annotated[int, Query(ge=2, le=5000)] = 2000):
        """Portfolio value over time, with the same starting cash held in SPY for comparison."""
        trader = await trader_or_404(slug)
        snapshots = await accounts.snapshots(trader.id, limit=limit)
        points = [s.PointOut(t=x.taken_at, value=float(x.total_value)) for x in snapshots]
        benchmark: list[s.PointOut] = []
        if snapshots:
            prices = await market.prices_at(BENCHMARK, [x.taken_at for x in snapshots])
            base = next((p for p in prices if p), None)
            if base:
                benchmark = [
                    s.PointOut(t=x.taken_at, value=float(trader.starting_cash * price / base))
                    for x, price in zip(snapshots, prices, strict=True)
                    if price
                ]
        return s.SeriesOut(portfolio=points, benchmark=benchmark, benchmark_symbol=BENCHMARK)

    @router.get("/traders/{slug}/runs", response_model=list[s.RunBrief])
    async def get_runs(slug: str, limit: Annotated[int, Query(ge=1, le=200)] = 30):
        trader = await trader_or_404(slug)
        return await accounts.runs(trader.id, limit=limit)

    @router.get("/runs/{run_id}", response_model=s.RunDetail)
    async def get_run(run_id: int):
        """A run with its trades and full trace, for the trace viewer."""
        run = await accounts.get_run(run_id)
        if run is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown run {run_id}")
        trader = await accounts.get_trader_by_id(run.trader_id)
        trades = await accounts.run_trades(run.id)
        events = await accounts.run_events(run.id)
        return s.RunDetail(
            **s.RunBrief.model_validate(run).model_dump(),
            trader_slug=trader.slug,
            model=trader.model_name,
            trades=[s.TradeOut.model_validate(t) for t in trades],
            events=[s.EventOut.model_validate(e) for e in events],
        )

    @router.get("/traders/{slug}/strategies", response_model=list[s.StrategyOut])
    async def get_strategies(slug: str):
        """Every version of the strategy, oldest first."""
        trader = await trader_or_404(slug)
        return await accounts.strategy_history(trader.id)

    @router.get("/traders/{slug}/events", response_model=list[s.EventOut])
    async def get_events(slug: str, last_n: Annotated[int, Query(ge=1, le=500)] = 50):
        """The latest activity, oldest first."""
        trader = await trader_or_404(slug)
        return await accounts.events(trader.id, last_n)

    @router.get("/activity", response_model=list[s.ActivityOut])
    async def get_activity(
        last_n: Annotated[int, Query(ge=1, le=500)] = 40,
        kinds: Annotated[str, Query(description="Comma-separated event kinds")] = "account,trace",
    ):
        """The latest activity across the whole floor, newest first: trades, rejections,
        strategy changes and runs starting and ending."""
        names = {t.id: t for t in await accounts.list_traders()}
        events = await accounts.recent_events([k.strip() for k in kinds.split(",") if k.strip()], last_n)
        return [
            s.ActivityOut(
                id=e.id,
                created_at=e.created_at,
                kind=e.kind,
                message=e.message,
                run_id=e.run_id,
                trader_slug=names[e.trader_id].slug,
                trader_name=names[e.trader_id].name,
            )
            for e in events
            if e.trader_id in names
        ]

    @router.get("/arena", response_model=list[s.ArenaRow])
    async def get_arena():
        """Traders grouped by model: who's doing best, and at what cost."""
        groups: dict[str, list] = defaultdict(list)
        for trader in await accounts.list_traders():
            portfolio = await accounts.portfolio(trader.id)
            stats = performance(
                await accounts.snapshots(trader.id),
                portfolio.total_value,
                trader.starting_cash,
                await accounts.trades(trader.id, limit=10_000),
                await accounts.runs(trader.id, limit=10_000),
            )
            groups[trader.model_name].append((trader, portfolio, stats))
        rows = []
        for model, members in groups.items():
            starting = sum(float(t.starting_cash) for t, _, _ in members)
            pnl = sum(float(p.pnl) for _, p, _ in members)
            cost = sum(st.total_cost_usd for _, _, st in members)
            runs = sum(st.runs for _, _, st in members)
            priced = sum(st.priced_runs for _, _, st in members)
            sharpes = [st.sharpe for _, _, st in members if st.sharpe is not None]
            wins = [st.win_rate for _, _, st in members if st.win_rate is not None]
            rows.append(
                s.ArenaRow(
                    model=model,
                    model_label=model_label(model),
                    traders=[t.name for t, _, _ in members],
                    return_pct=pnl / starting * 100 if starting else 0.0,
                    pnl=pnl,
                    sharpe=sum(sharpes) / len(sharpes) if sharpes else None,
                    max_drawdown_pct=max(st.max_drawdown_pct for _, _, st in members),
                    win_rate=sum(wins) / len(wins) if wins else None,
                    runs=runs,
                    total_cost_usd=cost,
                    cost_per_run_usd=cost / priced if priced else None,
                    pnl_per_dollar=pnl / cost if cost > 0 else None,
                )
            )
        return sorted(rows, key=lambda r: r.return_pct, reverse=True)

    @router.get("/models", response_model=list[s.ModelOut])
    async def get_models():
        """The model catalog. Any other LiteLLM provider/model id also works."""
        return [
            s.ModelOut(
                id=m.id,
                label=m.label,
                configured=(key := PROVIDER_KEYS.get(provider_of(m.id))) is None
                or bool(settings.secret(key)),
            )
            for m in CATALOG
        ]

    @router.get("/me", response_model=s.MeOut)
    async def get_me(request: Request):
        try:
            principal = auth.identify(request)
        except HTTPException as e:
            if e.status_code == status.HTTP_429_TOO_MANY_REQUESTS:
                raise
            principal = Principal(email=None, method="none", admin=False)
        return s.MeOut(
            admin=principal.admin,
            email=principal.email,
            method=principal.method,
            auth_configured=auth.configured,
        )

    # --- admin --------------------------------------------------------------------------

    @router.post(
        "/traders",
        response_model=s.TraderSummary,
        status_code=status.HTTP_201_CREATED,
        dependencies=admin_only,
    )
    @admin_limit
    async def create_trader(request: Request, body: s.TraderCreate):
        seed = TraderSeed(
            slug=body.slug,
            name=body.name,
            tagline=body.tagline,
            model_name=normalize_model_id(body.model),
            strategy=body.strategy.strip(),
        )
        try:
            starting = Decimal(str(body.starting_cash)) if body.starting_cash else None
            trader = await accounts.create_trader(seed, starting_cash=starting, guardrails=body.guardrails)
        except (TradingError, ValueError) as e:
            raise bad_request(e) from e
        await accounts.record_snapshot(trader.id)
        return await summary(trader)

    @router.patch("/traders/{slug}", response_model=s.TraderSummary, dependencies=admin_only)
    @admin_limit
    async def update_trader(request: Request, slug: str, body: s.TraderUpdate):
        trader = await trader_or_404(slug)
        try:
            trader = await accounts.update_trader(
                trader.id,
                model_name=normalize_model_id(body.model) if body.model else None,
                status=body.status,
                guardrails=body.guardrails,
                name=body.name,
                tagline=body.tagline,
            )
            if body.strategy is not None and body.strategy.strip() != trader.strategy:
                trader = await accounts.change_strategy(trader.id, body.strategy, source="admin")
        except (TradingError, ValueError) as e:
            raise bad_request(e) from e
        return await summary(await accounts.get_trader_by_id(trader.id))

    @router.delete("/traders/{slug}", status_code=status.HTTP_204_NO_CONTENT, dependencies=admin_only)
    @admin_limit
    async def delete_trader(request: Request, slug: str):
        trader = await trader_or_404(slug)
        await accounts.delete_trader(trader.id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @router.post("/traders/{slug}/reset", response_model=s.TraderSummary, dependencies=admin_only)
    @admin_limit
    async def reset_trader(request: Request, slug: str):
        """Back to starting cash with no positions. The four originals get their seed strategy
        and model back; other traders keep theirs."""
        trader = await trader_or_404(slug)
        seeds = {x.slug: x for x in default_traders(settings)}
        seed = seeds.get(trader.slug) or TraderSeed(
            slug=trader.slug,
            name=trader.name,
            tagline=trader.tagline,
            model_name=trader.model_name,
            strategy=trader.strategy,
        )
        trader = await accounts.reset(seed, starting_cash=trader.starting_cash)
        await accounts.record_snapshot(trader.id)
        return await summary(trader)

    @router.post(
        "/traders/{slug}/run",
        response_model=s.CommandOut,
        status_code=status.HTTP_202_ACCEPTED,
        dependencies=admin_only,
    )
    @admin_limit
    async def run_trader(request: Request, slug: str):
        """Queue a run; the scheduler starts it within a few seconds."""
        trader = await trader_or_404(slug)
        return await floor.enqueue("run_now", trader.id)

    @router.post("/floor/pause", response_model=s.FloorOut, dependencies=admin_only)
    @admin_limit
    async def pause_floor(request: Request):
        await floor.set_paused(True)
        return await get_floor()

    @router.post("/floor/resume", response_model=s.FloorOut, dependencies=admin_only)
    @admin_limit
    async def resume_floor(request: Request):
        await floor.set_paused(False)
        return await get_floor()

    @router.get("/commands", response_model=list[s.CommandOut], dependencies=admin_only)
    async def list_commands(limit: Annotated[int, Query(ge=1, le=200)] = 20):
        return await floor.recent(limit)

    return router

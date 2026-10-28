"""The `gauntlet` command: database, trader and floor administration.

uv run gauntlet migrate                    apply database migrations
uv run gauntlet reset [warren ...]         reset traders to their starting strategies
uv run gauntlet import-legacy accounts.db  import data from the original trading floor
uv run gauntlet status                     floor state, traders and their latest runs
uv run gauntlet models                     the model catalog and which API keys are set
uv run gauntlet set-model warren anthropic/claude-opus-5-5
uv run gauntlet guardrails warren '{"max_order_value": 2000}'
uv run gauntlet run-now warren             queue a run for the scheduler (or: all)
uv run gauntlet run-once                   run one cycle in this process and exit
uv run gauntlet pause | resume [warren]    the whole floor, or one trader
"""

import argparse
import asyncio
import json
import logging
from pathlib import Path

from .container import Container, build_container
from .db import Trader
from .domain import Guardrails
from .legacy_import import import_legacy
from .llm import CATALOG, PROVIDER_KEYS, model_label, normalize_model_id, provider_of
from .personas import default_traders


async def _started() -> Container:
    container = build_container()
    await container.start()
    return container


async def _traders(container: Container, names: list[str]) -> list[Trader]:
    if not names or names == ["all"]:
        return await container.accounts.list_traders()
    return [await container.accounts.get_trader(name) for name in names]


async def _migrate() -> None:
    container = build_container()
    await container.db.migrate()
    await container.close()
    print("Database is up to date")


async def _reset(slugs: list[str]) -> None:
    container = await _started()
    seeds = default_traders(container.settings)
    if unknown := {x.lower() for x in slugs} - {s.slug for s in seeds}:
        raise SystemExit(f"Unknown trader(s): {', '.join(sorted(unknown))}")
    for seed in [s for s in seeds if not slugs or s.slug in {x.lower() for x in slugs}]:
        await container.accounts.reset(seed)
        print(f"Reset {seed.name}")
    await container.close()


async def _import(path: Path, force: bool) -> None:
    if not path.exists():
        raise SystemExit(f"No such file: {path}")
    container = build_container()
    if container.settings.auto_migrate:
        await container.db.migrate()
    report = await import_legacy(
        path, container.db, container.settings, default_traders(container.settings), force=force
    )
    await container.accounts.ensure_traders(default_traders(container.settings))
    await container.close()
    print(
        f"Imported {', '.join(report.traders) or 'no traders'}: {report.trades} trades, "
        f"{report.snapshots} snapshots, {report.events} log lines"
    )
    if report.skipped:
        print(f"Skipped {', '.join(report.skipped)}: they already have trades (use --force to replace)")
    for warning in report.warnings:
        print(f"Warning: {warning}")


async def _status() -> None:
    container = await _started()
    floor = await container.floor.status()
    settings = container.settings
    leader = f"led by {floor.leader_id}" if floor.leader_alive else "no scheduler running"
    print(f"Floor: {'paused' if floor.paused else 'active'}, {leader}")
    print(f"Prices: {container.market.name}{', demo mode' if settings.demo_mode else ''}\n")
    for trader in await container.accounts.list_traders():
        portfolio = await container.accounts.portfolio(trader.id)
        runs = await container.accounts.runs(trader.id, limit=1)
        last = runs[0] if runs else None
        last_text = f"last run {last.kind} {last.status}" if last else "no runs yet"
        if last and last.cost_usd is not None:
            last_text += f", ${last.cost_usd:.4f}"
        label = "Demo" if settings.demo_mode else model_label(trader.model_name)
        print(
            f"{trader.name:<8} {trader.status:<7} {label:<18} "
            f"${portfolio.total_value:>11,.2f} ({portfolio.pnl:+,.2f})  {last_text}"
        )
    await container.close()


def _models() -> None:
    from .settings import get_settings

    settings = get_settings()
    for info in CATALOG:
        provider = provider_of(info.id)
        key = PROVIDER_KEYS.get(provider)
        ready = (
            "no key needed"
            if key is None
            else ("key set" if settings.secret(key) else f"needs {key.upper()}")
        )
        print(f"{info.id:<30} {info.label:<18} {ready}")
    print("\nAny other LiteLLM id (provider/model) works too.")


async def _set_model(name: str, model: str) -> None:
    container = await _started()
    trader = await container.accounts.get_trader(name)
    model = normalize_model_id(model)
    await container.accounts.update_trader(trader.id, model_name=model)
    print(f"{trader.name} now trades with {model_label(model)} ({model})")
    await container.close()


async def _guardrails(name: str, overrides: str | None) -> None:
    container = await _started()
    trader = await container.accounts.get_trader(name)
    if overrides is not None:
        values = json.loads(overrides)
        if not isinstance(values, dict):
            raise SystemExit("Guardrails must be a JSON object")
        await container.accounts.update_trader(trader.id, guardrails=values)
        trader = await container.accounts.get_trader(name)
    print(json.dumps(Guardrails.for_trader(trader.guardrails).describe(), indent=2))
    await container.close()


async def _run_now(names: list[str]) -> None:
    container = await _started()
    for trader in await _traders(container, names):
        await container.floor.enqueue("run_now", trader.id)
        print(f"Queued a run for {trader.name}")
    if not (await container.floor.status()).leader_alive:
        print("No scheduler is running: start `uv run -m gauntlet.trading_floor`, or use `gauntlet run-once`")
    await container.close()


async def _pause(names: list[str], paused: bool) -> None:
    container = await _started()
    if not names:
        await container.floor.set_paused(paused)
        print(f"Floor {'paused' if paused else 'resumed'}")
    for trader in [] if not names else await _traders(container, names):
        await container.accounts.update_trader(trader.id, status="paused" if paused else "active")
        print(f"{trader.name} {'paused' if paused else 'resumed'}")
    await container.close()


def _openapi(out: Path | None) -> None:
    from .api import create_app

    schema = json.dumps(create_app(build_container()).openapi(), indent=2, sort_keys=True) + "\n"
    if out:
        out.write_text(schema, encoding="utf-8", newline="\n")  # same bytes on every OS
        print(f"Wrote {out}")
    else:
        print(schema, end="")


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(prog="gauntlet", description=(__doc__ or "").splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("migrate", help="apply database migrations")
    reset = commands.add_parser("reset", help="reset traders to their starting strategies")
    reset.add_argument("traders", nargs="*", help="trader names (default: all)")
    legacy = commands.add_parser("import-legacy", help="import an accounts.db from the original project")
    legacy.add_argument("path", type=Path)
    legacy.add_argument("--force", action="store_true", help="replace traders that already have trades")
    commands.add_parser("status", help="floor state, traders and their latest runs")
    commands.add_parser("models", help="the model catalog and which API keys are set")
    set_model = commands.add_parser("set-model", help="change the model a trader uses")
    set_model.add_argument("trader")
    set_model.add_argument("model", help="a provider/model id, e.g. anthropic/claude-opus-5-5")
    guardrails = commands.add_parser("guardrails", help="show or set a trader's trading limits")
    guardrails.add_argument("trader")
    guardrails.add_argument("overrides", nargs="?", help="JSON overrides, e.g. '{\"max_order_value\": 2000}'")
    run_now = commands.add_parser("run-now", help="queue a run for the scheduler to start")
    run_now.add_argument("traders", nargs="+", help="trader names, or 'all'")
    openapi = commands.add_parser("openapi", help="write the API's OpenAPI schema (for the web app's types)")
    openapi.add_argument("--out", type=Path, help="file to write (default: stdout)")
    once = commands.add_parser("run-once", help="run one cycle in this process, then exit")
    once.add_argument("--verbose", action="store_true")
    for name, help_text in (("pause", "pause the floor or some traders"), ("resume", "resume them")):
        command = commands.add_parser(name, help=help_text)
        command.add_argument("traders", nargs="*", help="trader names (default: the whole floor)")
    args = parser.parse_args(argv)

    match args.command:
        case "migrate":
            asyncio.run(_migrate())
        case "reset":
            asyncio.run(_reset(args.traders))
        case "import-legacy":
            asyncio.run(_import(args.path, args.force))
        case "status":
            asyncio.run(_status())
        case "models":
            _models()
        case "set-model":
            asyncio.run(_set_model(args.trader, args.model))
        case "guardrails":
            asyncio.run(_guardrails(args.trader, args.overrides))
        case "run-now":
            asyncio.run(_run_now(args.traders))
        case "run-once":
            from .trading_floor import run_floor

            logging.getLogger().setLevel(logging.INFO if args.verbose else logging.WARNING)
            asyncio.run(run_floor(once=True))
        case "openapi":
            _openapi(args.out)
        case "pause" | "resume":
            asyncio.run(_pause(args.traders, args.command == "pause"))


if __name__ == "__main__":
    main()

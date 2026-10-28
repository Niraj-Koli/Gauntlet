"""Demo mode: a scripted stand-in for an LLM, so the whole floor runs with no API keys.

It follows the same loop a real agent does, through the real tools: ask the researcher,
look up a price, size and place an order within its cash, sometimes record a lesson in
its strategy, send a notification, then appraise the portfolio. Choices are seeded by
trader and time, so runs vary but are reproducible. It reports no token usage.
"""

import asyncio
import json
import random
import re
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

from agents import Model, ModelResponse, Usage
from agents.items import TResponseStreamEvent
from agents.tracing import generation_span
from openai.types.responses import ResponseFunctionToolCall, ResponseOutputMessage, ResponseOutputText

UNIVERSES = {
    "warren": ["KO", "AAPL", "BRK.B", "JNJ", "PG", "V"],
    "george": ["SPY", "TLT", "GLD", "EWJ", "FXI", "UUP"],
    "ray": ["VTI", "TLT", "IEF", "GLD", "DBC", "VWO"],
    "cathie": ["IBIT", "ETHA", "ARKK", "COIN", "MSTR", "BITO"],
}
DEFAULT_UNIVERSE = ["SPY", "QQQ", "AAPL", "MSFT"]

LESSONS = [
    "Size new positions smaller until a thesis has proven itself.",
    "Trim winners that grow past a fifth of the portfolio.",
    "Keep some cash in reserve for sharp pullbacks.",
    "Favour names where research and price action agree.",
]
LESSON_MARKER = "Lesson learned:"


def _text(item: Any) -> str:
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        content = item.get("content") or item.get("output") or ""
        if isinstance(content, list):
            return " ".join(str(c.get("text", "")) for c in content if isinstance(c, dict))
        return str(content)
    return ""


def _account_from(prompt: str) -> dict[str, Any]:
    match = re.search(
        r"Here is your current account:\s*(\{.*?\})\s*Here is the current datetime", prompt, re.S
    )
    if not match:
        return {}
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return {}


def _number(text: str) -> float | None:
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    return float(match.group()) if match else None


class DemoModel(Model):
    def __init__(self, step_delay: float = 0.4):
        self.step_delay = step_delay

    async def get_response(self, system_instructions, input, model_settings, tools, *args, **kwargs):
        if self.step_delay:
            await asyncio.sleep(self.step_delay)
        items = [input] if isinstance(input, str) else list(input)
        instructions = system_instructions or ""
        with generation_span(model="demo/scripted", input=[{"role": "system", "content": instructions}]):
            if "financial researcher" in instructions:
                return self._reply(self._research(_text(items[-1])))
            return self._trader_turn(instructions, items, {t.name for t in tools})

    def stream_response(self, *args, **kwargs) -> AsyncIterator[TResponseStreamEvent]:
        raise NotImplementedError("Demo mode doesn't stream")

    # --- the researcher ---------------------------------------------------------------

    def _research(self, request: str) -> str:
        rng = random.Random(request)
        mood = rng.choice(["constructive", "mixed", "cautious"])
        return (
            f"(Demo research) Market tone is {mood}. Large caps are holding up, rates are steady, "
            "and flows into the names you follow look orderly. No single headline stands out; "
            "position sizing matters more than timing today."
        )

    # --- the trader -------------------------------------------------------------------

    def _trader_turn(self, instructions: str, items: list[Any], tools: set[str]) -> ModelResponse:
        prompt = _text(items[0])
        found = re.search(r"You are (\w+),", instructions)
        name = found.group(1) if found else "Trader"
        account = _account_from(prompt)
        rebalancing = "decide if you need to rebalance" in prompt
        hour = datetime.now(UTC).strftime("%Y%m%d%H%M")
        rng = random.Random(f"{name}:{hour}:{rebalancing}")

        calls = [i for i in items if isinstance(i, dict) and i.get("type") == "function_call"]
        outputs = {
            i.get("call_id"): _text(i)
            for i in items
            if isinstance(i, dict) and i.get("type") == "function_call_output"
        }
        done = [c.get("name") for c in calls]

        universe = UNIVERSES.get(name.lower(), DEFAULT_UNIVERSE)
        positions = account.get("positions", [])
        selling = rebalancing and positions and rng.random() < 0.6
        target = rng.choice(positions)["symbol"] if selling else rng.choice(universe)

        if "Researcher" in tools and "Researcher" not in done:
            query = f"Latest news and risks for {target}" if not rebalancing else "How are my holdings doing?"
            return self._call("Researcher", {"input": query}, len(calls))
        if "lookup_share_price" in tools and "lookup_share_price" not in done:
            return self._call("lookup_share_price", {"symbol": target}, len(calls))
        if not {"buy_shares", "sell_shares"} & set(done) and {"buy_shares", "sell_shares"} <= tools:
            order = self._order(rng, account, target, selling, calls, outputs)
            if order:
                return self._call(*order, len(calls))
        if (
            rebalancing
            and "change_strategy" in tools
            and "change_strategy" not in done
            and rng.random() < 0.3
        ):
            strategy = account.get("strategy", "").split(LESSON_MARKER)[0].rstrip()
            lesson = rng.choice(LESSONS)
            return self._call(
                "change_strategy", {"strategy": f"{strategy}\n\n{LESSON_MARKER} {lesson}"}, len(calls)
            )
        if "push" in tools and "push" not in done:
            return self._call("push", {"message": f"{name}: {self._activity(done, target)}"}, len(calls))
        return self._reply(self._appraisal(rng, account, done, target))

    def _order(
        self,
        rng: random.Random,
        account: dict[str, Any],
        symbol: str,
        selling: bool,
        calls: list[dict[str, Any]],
        outputs: dict[Any, str],
    ) -> tuple[str, dict[str, Any]] | None:
        if selling:
            held = next((p for p in account.get("positions", []) if p["symbol"] == symbol), None)
            if not held:
                return None
            quantity = max(1, held["quantity"] // rng.choice([2, 3, 4]))
            return "sell_shares", {
                "symbol": symbol,
                "quantity": quantity,
                "rationale": "Trimming to rebalance",
            }
        lookup = next((c for c in calls if c.get("name") == "lookup_share_price"), None)
        price = _number(outputs.get(lookup.get("call_id"), "")) if lookup else None
        cash = float(account.get("cash", 0))
        total = float(account.get("total_portfolio_value", cash)) or cash
        if not price or price <= 0:
            return None
        budget = min(cash * 0.95, total * rng.uniform(0.10, 0.25))
        quantity = int(budget // (price * 1.01))
        if quantity < 1:
            return None
        rationale = rng.choice(
            [
                "Fits the strategy at a reasonable price",
                "Research supports adding exposure here",
                "Building the position gradually",
            ]
        )
        return "buy_shares", {"symbol": symbol, "quantity": quantity, "rationale": rationale}

    @staticmethod
    def _activity(done: list[Any], symbol: str) -> str:
        if "buy_shares" in done:
            return f"added to {symbol}."
        if "sell_shares" in done:
            return f"trimmed {symbol}."
        return "reviewed the portfolio; no trades this time."

    def _appraisal(self, rng: random.Random, account: dict[str, Any], done: list[Any], symbol: str) -> str:
        pnl = float(account.get("total_profit_loss", 0))
        outlook = "bullish" if pnl > 0 else rng.choice(["neutral", "bullish", "bearish"])
        summary = {
            "appraisal": (
                f"This run I {self._activity(done, symbol)} The portfolio is "
                f"{'ahead' if pnl >= 0 else 'behind'} by ${abs(pnl):,.0f} overall, and sizing stays "
                "within my limits."
            ),
            "outlook": outlook,
            "confidence": round(rng.uniform(0.4, 0.8), 2),
        }
        return f"{summary['appraisal']}\n\n{json.dumps(summary)}"

    # --- responses --------------------------------------------------------------------

    @staticmethod
    def _call(name: str, arguments: dict[str, Any], n: int) -> ModelResponse:
        call = ResponseFunctionToolCall(
            id=f"fc_demo_{n}",
            call_id=f"call_demo_{n}_{random.getrandbits(32):08x}",
            name=name,
            arguments=json.dumps(arguments),
            type="function_call",
            status="completed",
        )
        return ModelResponse(output=[call], usage=Usage(), response_id=None)

    @staticmethod
    def _reply(text: str) -> ModelResponse:
        message = ResponseOutputMessage(
            id="msg_demo",
            type="message",
            role="assistant",
            status="completed",
            content=[ResponseOutputText(type="output_text", text=text, annotations=[])],
        )
        return ModelResponse(output=[message], usage=Usage(), response_id=None)

"""The model registry, run summaries, retry decisions and notification channels."""

from decimal import Decimal

import httpx
import pytest
from agents.extensions.models.litellm_model import LitellmModel
from pydantic import SecretStr

from gauntlet.demo import DemoModel
from gauntlet.llm import (
    MissingCredentials,
    estimate_cost,
    model_label,
    normalize_model_id,
    resolve_model,
    uses_native_structured_output,
)
from gauntlet.notify import (
    LogNotifier,
    NtfyNotifier,
    PushoverNotifier,
    SlackNotifier,
    create_notifier,
    notify,
)
from gauntlet.personas import default_traders, parse_trader_models
from gauntlet.traders import RunSummary, is_retryable, parse_summary


def with_settings(settings, **values):
    return settings.model_copy(update=values)


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        ("gpt-5.5", "openai/gpt-5.5"),
        ("claude-opus-5-5", "anthropic/claude-opus-5-5"),
        ("deepseek-v4-flash", "deepseek/deepseek-v4-flash"),
        ("grok-4.3", "xai/grok-4.3"),
        ("meta/llama-5", "openrouter/meta/llama-5"),
        ("anthropic/claude-haiku-5-5", "anthropic/claude-haiku-5-5"),
        ("demo/scripted", "demo/scripted"),
    ],
)
def test_model_ids_are_normalized(given, expected):
    assert normalize_model_id(given) == expected


def test_labels():
    assert model_label("anthropic/claude-opus-5-5") == "Claude Opus 5.5"
    assert model_label("openrouter/meta/llama-5") == "meta/llama-5"


def test_models_resolve_by_provider(settings):
    keyed = with_settings(settings, openai_api_key=SecretStr("o"), anthropic_api_key=SecretStr("a"))
    assert resolve_model("openai/gpt-5.5", keyed) == "gpt-5.5"
    claude = resolve_model("anthropic/claude-opus-5-5", keyed)
    assert isinstance(claude, LitellmModel) and claude.model == "anthropic/claude-opus-5-5"
    assert isinstance(resolve_model("demo/scripted", settings), DemoModel)
    with pytest.raises(MissingCredentials, match="GOOGLE_API_KEY"):
        resolve_model("gemini/gemini-3.5-flash", keyed)
    with pytest.raises(ValueError):
        resolve_model("nowhere/model", keyed)


def test_only_openai_uses_native_structured_output():
    assert uses_native_structured_output("openai/gpt-5.5")
    assert not uses_native_structured_output("anthropic/claude-opus-5-5")


def test_costs_come_from_litellm_prices():
    assert estimate_cost("anthropic/claude-opus-5-5", 1_000_000, 1_000_000) == Decimal("24.0")
    assert estimate_cost("demo/scripted", 5, 5) == 0
    assert estimate_cost("openrouter/not/a-model", 5, 5) is None


def test_seeding_follows_settings(settings):
    assert {t.model_name for t in default_traders(settings)} == {"openai/gpt-5.4-mini"}
    many = default_traders(with_settings(settings, use_many_models=True))
    assert [t.model_name for t in many][1] == "anthropic/claude-opus-5-5"
    custom = default_traders(with_settings(settings, trader_models="ray=claude-sonnet-5-5"))
    assert {t.slug: t.model_name for t in custom}["ray"] == "anthropic/claude-sonnet-5-5"
    with pytest.raises(ValueError):
        parse_trader_models("ray")


def test_demo_mode_shortens_the_cycle(settings):
    assert settings.cycle_minutes == 60
    assert with_settings(settings, demo_mode=True).cycle_minutes == 3
    assert with_settings(settings, demo_mode=True, run_every_n_minutes=10).cycle_minutes == 10


# --- summaries and retries ------------------------------------------------------------


def test_summaries_are_parsed_from_structured_output_or_text():
    native = RunSummary(appraisal="Good.", outlook="bullish", confidence=0.9)
    assert parse_summary(native) == ("Good.", native)
    text, summary = parse_summary('Done.\n{"appraisal": "Fine.", "outlook": "bearish", "confidence": 0.2}')
    assert text == "Fine." and summary is not None and summary.outlook == "bearish"
    assert parse_summary("No JSON here.") == ("No JSON here.", None)
    assert parse_summary('{"appraisal": "x", "outlook": "sideways", "confidence": 3}') == (
        '{"appraisal": "x", "outlook": "sideways", "confidence": 3}',
        None,
    )


def test_retry_decisions():
    class RateLimitError(Exception):
        pass

    assert is_retryable(ConnectionError())
    assert is_retryable(RateLimitError())
    assert is_retryable(ExceptionGroup("mcp", [httpx.ConnectError("refused")]))
    wrapped = RuntimeError("wrapped")
    wrapped.__cause__ = httpx.ReadTimeout("slow")
    assert is_retryable(wrapped)
    assert not is_retryable(MissingCredentials("no key"))
    assert not is_retryable(TimeoutError())
    assert not is_retryable(ValueError("bad"))


# --- notifications --------------------------------------------------------------------


def test_the_channel_follows_configuration(settings):
    assert isinstance(create_notifier(settings), LogNotifier)
    pushover = with_settings(settings, pushover_user=SecretStr("u"), pushover_token=SecretStr("t"))
    assert isinstance(create_notifier(pushover), PushoverNotifier)
    assert isinstance(create_notifier(with_settings(settings, ntfy_url="https://ntfy.sh/x")), NtfyNotifier)
    slack = with_settings(settings, slack_webhook_url=SecretStr("https://hooks.slack.com/x"))
    assert isinstance(create_notifier(slack), SlackNotifier)
    assert create_notifier(with_settings(settings, notify_channel="none")).name == "none"
    # Asking for a channel that isn't configured falls back to the log.
    assert isinstance(create_notifier(with_settings(settings, notify_channel="slack")), LogNotifier)


async def test_delivery_failures_are_reported_not_raised():
    class Down:
        name = "ntfy"

        async def send(self, title, message):
            raise httpx.ConnectError("down")

    assert await notify(Down(), "t", "m") == "The push notification could not be sent"
    assert await notify(LogNotifier(), "t", "m") == "Notification recorded (no push channel is configured)"

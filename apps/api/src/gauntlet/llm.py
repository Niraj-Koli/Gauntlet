"""Which language models traders can use, and how each one is reached.

Model ids are LiteLLM-style "provider/model" strings, stored per trader. OpenAI models
go through the Agents SDK's native OpenAI client; everything else goes through LiteLLM.
"demo/..." is the scripted model that needs no API key.
"""

import logging
from dataclasses import dataclass
from decimal import Decimal

from agents import Model
from agents.extensions.models.litellm_model import LitellmModel

from .settings import Settings

logger = logging.getLogger(__name__)

DEMO_MODEL = "demo/scripted"


@dataclass(frozen=True)
class ModelInfo:
    id: str
    label: str


CATALOG = [
    ModelInfo("openai/gpt-5.4-mini", "GPT 5.4 mini"),
    ModelInfo("openai/gpt-5.5", "GPT 5.5"),
    ModelInfo("anthropic/claude-opus-5-5", "Claude Opus 5.5"),
    ModelInfo("anthropic/claude-sonnet-5-5", "Claude Sonnet 5.5"),
    ModelInfo("anthropic/claude-haiku-5-5", "Claude Haiku 5.5"),
    ModelInfo("anthropic/claude-fable-5-1", "Claude Fable 5.1"),
    ModelInfo("gemini/gemini-3.5-flash", "Gemini 3.5 Flash"),
    ModelInfo("deepseek/deepseek-v4-flash", "DeepSeek V4"),
    ModelInfo("xai/grok-4.3", "Grok 4.3"),
    ModelInfo(DEMO_MODEL, "Demo"),
]
CATALOG_BY_ID = {m.id: m for m in CATALOG}

# The settings field holding each provider's API key.
PROVIDER_KEYS = {
    "openai": "openai_api_key",
    "anthropic": "anthropic_api_key",
    "gemini": "google_api_key",
    "deepseek": "deepseek_api_key",
    "xai": "grok_api_key",
    "openrouter": "openrouter_api_key",
}


# For bare names from older configs: a substring of the name, and its provider.
BARE_NAME_PROVIDERS = [
    ("deepseek", "deepseek"),
    ("gemini", "gemini"),
    ("grok", "xai"),
    ("claude", "anthropic"),
]


class MissingCredentials(RuntimeError):
    pass


def provider_of(model_id: str) -> str:
    return model_id.split("/", 1)[0]


def model_label(model_id: str) -> str:
    """A short display name, e.g. 'anthropic/claude-opus-5-5' -> 'Claude Opus 5.5'."""
    if info := CATALOG_BY_ID.get(model_id):
        return info.label
    return model_id.split("/", 1)[-1]


def normalize_model_id(model: str) -> str:
    """Accept bare names from older configs: 'gpt-5.5' -> 'openai/gpt-5.5'."""
    model = model.strip()
    if provider_of(model) in PROVIDER_KEYS or model.startswith("demo/"):
        return model
    if "/" in model:
        return f"openrouter/{model}"
    for marker, provider in BARE_NAME_PROVIDERS:
        if marker in model:
            return f"{provider}/{model}"
    return f"openai/{model}"


def uses_native_structured_output(model_id: str) -> bool:
    """Whether the run summary can use the SDK's output_type.

    Only for OpenAI. Through LiteLLM, some providers implement JSON schema output by
    forcing a tool call, which current Claude models reject, so other models are asked
    for JSON in their final message instead.
    """
    return provider_of(model_id) == "openai"


def resolve_model(model_id: str, settings: Settings) -> Model | str:
    """The Agents SDK model for an id. Raises MissingCredentials without an API key."""
    provider = provider_of(model_id)
    if provider == "demo":
        from .demo import DemoModel

        return DemoModel()
    key_field = PROVIDER_KEYS.get(provider)
    if key_field is None:
        raise ValueError(f"Unknown model provider in {model_id!r}")
    api_key = settings.secret(key_field)
    if not api_key:
        raise MissingCredentials(
            f"{model_id} needs {key_field.upper()} (or set DEMO_MODE=true to run without keys)"
        )
    if provider == "openai":
        return model_id.split("/", 1)[1]  # the SDK's default client, keyed at startup
    return LitellmModel(model=model_id, api_key=api_key)


def estimate_cost(model_id: str, input_tokens: int, output_tokens: int) -> Decimal | None:
    """Dollar cost from LiteLLM's price list, or None for a model it doesn't price."""
    if provider_of(model_id) == "demo":
        return Decimal(0)
    try:
        import litellm

        prompt, completion = litellm.cost_per_token(
            model=model_id, prompt_tokens=input_tokens, completion_tokens=output_tokens
        )
    except Exception:
        logger.debug("No price for %s", model_id)
        return None
    return Decimal(str(prompt + completion))

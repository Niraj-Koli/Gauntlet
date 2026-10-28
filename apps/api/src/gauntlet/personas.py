"""The four starting traders: their personas, strategies and models."""

from .domain import TraderSeed
from .llm import normalize_model_id
from .settings import Settings

warren_strategy = """
You are Warren, and you are named in homage to your role model, Warren Buffett.
You are a value-oriented investor who prioritizes long-term wealth creation.
You identify high-quality companies trading below their intrinsic value.
You invest patiently and hold positions through market fluctuations,
relying on meticulous fundamental analysis, steady cash flows, strong management teams,
and competitive advantages. You rarely react to short-term market movements,
trusting your deep research and value-driven strategy.
"""

george_strategy = """
You are George, and you are named in homage to your role model, George Soros.
You are an aggressive macro trader who actively seeks significant market
mispricings. You look for large-scale economic and
geopolitical events that create investment opportunities. Your approach is contrarian,
willing to bet boldly against prevailing market sentiment when your macroeconomic analysis
suggests a significant imbalance. You leverage careful timing and decisive action to
capitalize on rapid market shifts.
"""

ray_strategy = """
You are Ray, and you are named in homage to your role model, Ray Dalio.
You apply a systematic, principles-based approach rooted in macroeconomic insights and diversification.
You invest broadly across asset classes, utilizing risk parity strategies to achieve balanced returns
in varying market environments. You pay close attention to macroeconomic indicators, central bank policies,
and economic cycles, adjusting your portfolio strategically to manage risk and preserve capital across diverse market conditions.
"""

cathie_strategy = """
You are Cathie, and you are named in homage to your role model, Cathie Wood.
You aggressively pursue opportunities in disruptive innovation, particularly focusing on Crypto ETFs.
Your strategy is to identify and invest boldly in sectors poised to revolutionize the economy,
accepting higher volatility for potentially exceptional returns. You closely monitor technological breakthroughs,
regulatory changes, and market sentiment in crypto ETFs, ready to take bold positions
and actively manage your portfolio to capitalize on rapid growth trends.
You focus your trading on crypto ETFs.
"""


PERSONAS = [
    ("warren", "Warren", "Patience", warren_strategy),
    ("george", "George", "Bold", george_strategy),
    ("ray", "Ray", "Systematic", ray_strategy),
    ("cathie", "Cathie", "Crypto", cathie_strategy),
]

SINGLE_MODEL = "openai/gpt-5.4-mini"
# One model per trader when USE_MANY_MODELS is on: a head-to-head across providers.
MANY_MODELS = [
    "openai/gpt-5.5",
    "anthropic/claude-opus-5-5",
    "gemini/gemini-3.5-flash",
    "deepseek/deepseek-v4-flash",
]


def parse_trader_models(value: str) -> dict[str, str]:
    """TRADER_MODELS, e.g. 'warren=anthropic/claude-sonnet-5-5,ray=openai/gpt-5.5'."""
    models = {}
    for pair in filter(None, (p.strip() for p in value.split(","))):
        slug, sep, model = pair.partition("=")
        if not sep or not model.strip():
            raise ValueError(f"TRADER_MODELS entry {pair!r} should look like name=provider/model")
        models[slug.strip().lower()] = normalize_model_id(model)
    return models


def default_traders(settings: Settings) -> list[TraderSeed]:
    """The starting traders. (Demo mode swaps in the demo model at run time, not here.)"""
    models = MANY_MODELS if settings.use_many_models else [SINGLE_MODEL] * len(PERSONAS)
    overrides = parse_trader_models(settings.trader_models)
    return [
        TraderSeed(
            slug=slug,
            name=name,
            tagline=tagline,
            model_name=overrides.get(slug, model),
            strategy=strategy.strip(),
        )
        for (slug, name, tagline, strategy), model in zip(PERSONAS, models, strict=True)
    ]

"""Typed configuration for every Gauntlet process, read from the environment and .env.

Real environment variables win over .env. The .env file is found at the repository
root, so processes behave the same whichever directory they start in.
"""

import logging
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# apps/api/src/gauntlet/settings.py -> repository root
REPO_ROOT = Path(__file__).resolve().parents[4]
DEV_SECRET_KEY = "dev-only-insecure-secret-change-me"

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
    )

    # Storage
    gauntlet_data_dir: Path = REPO_ROOT / "data"
    database_url: str = ""
    """SQLAlchemy async URL. Empty means SQLite in the data directory; for Supabase use
    postgresql+asyncpg://... (the pooler's transaction mode on port 6543 is detected)."""
    auto_migrate: bool = True
    """Apply database migrations when the API or trading floor starts."""

    # Trading rules
    initial_balance: Decimal = Decimal("10000")
    spread: Decimal = Decimal("0.002")
    max_order_quantity: int = 1_000_000

    # Market data
    massive_api_key: SecretStr | None = None
    price_cache_seconds: float = 60.0
    market_status_cache_seconds: float = 300.0

    # Scheduler
    run_every_n_minutes: int | None = None
    """Minutes between cycles; defaults to 60, or 3 in demo mode."""
    run_even_when_market_is_closed: bool = False
    run_timeout_seconds: int = 15 * 60
    run_retries: int = 2
    """Extra attempts for a run that fails before making any trade."""
    command_poll_seconds: float = 5.0
    leader_lease_seconds: int = 60

    # Models
    demo_mode: bool = False
    """Run every trader on the scripted demo model: no API keys needed."""
    use_many_models: bool = False
    trader_models: str = ""
    """Per-trader model overrides used when seeding, e.g. 'warren=anthropic/claude-sonnet-5-5'."""

    # Notifications: auto picks Pushover, then ntfy, then Slack, from what's configured
    notify_channel: str = "auto"
    """auto, pushover, ntfy, slack, log or none."""
    ntfy_url: str | None = None
    """A full topic URL, e.g. https://ntfy.sh/my-gauntlet-topic."""
    slack_webhook_url: SecretStr | None = None

    # MCP: the API hosts the accounts and market servers that the traders connect to
    api_base_url: str = "http://127.0.0.1:8000"
    gauntlet_secret_key: SecretStr = SecretStr(DEV_SECRET_KEY)
    mcp_allowed_hosts: list[str] = Field(default=["127.0.0.1:*", "localhost:*", "[::1]:*"])
    mcp_token_ttl_seconds: int = 3 * 60 * 60
    mcp_tools_dir: Path | None = None
    """Where `python mcp_tools.py DIR` installed the researcher's MCP servers (container images
    do). Unset, they run through uvx and npx."""

    # Process health: the trading floor touches this file on every loop, and
    # `python -m gauntlet.health` fails once it goes stale.
    heartbeat_file: Path | None = None
    heartbeat_max_age_seconds: float = 120.0

    # HTTP API and admin access
    cors_origins: list[str] = Field(default=["http://localhost:3000", "http://127.0.0.1:3000"])
    admin_api_token: SecretStr | None = None
    """A static bearer token for admin endpoints, for scripts and local development."""
    admin_emails: list[str] = Field(default_factory=list)
    """Supabase users who may use admin endpoints (JSON list, e.g. '["me@example.com"]')."""
    supabase_url: str | None = None
    """e.g. http://127.0.0.1:54321; its JWKS verifies the dashboard's sign-in tokens."""
    supabase_jwt_secret: SecretStr | None = None
    """Only for projects still on the legacy shared HS256 JWT secret."""
    admin_rate_limit: str = "60/minute"
    admin_auth_failure_limit: str = "10/minute"
    """Failed admin sign-ins allowed per client address; beyond it, sign-ins are refused."""

    # Model providers and tools
    openai_api_key: SecretStr | None = None
    anthropic_api_key: SecretStr | None = None
    openrouter_api_key: SecretStr | None = None
    deepseek_api_key: SecretStr | None = None
    google_api_key: SecretStr | None = None
    grok_api_key: SecretStr | None = None
    tavily_api_key: SecretStr | None = None
    pushover_user: SecretStr | None = None
    pushover_token: SecretStr | None = None

    @model_validator(mode="after")
    def _resolve_paths(self) -> "Settings":
        self.gauntlet_data_dir = self.gauntlet_data_dir.resolve()
        if not self.database_url:
            self.database_url = f"sqlite+aiosqlite:///{(self.data_dir / 'gauntlet.db').as_posix()}"
        return self

    @property
    def cycle_minutes(self) -> int:
        if self.run_every_n_minutes is not None:
            return self.run_every_n_minutes
        return 3 if self.demo_mode else 60

    @property
    def data_dir(self) -> Path:
        return self.gauntlet_data_dir

    @property
    def memory_dir(self) -> Path:
        return self.data_dir / "memory"

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def mcp_accounts_url(self) -> str:
        return f"{self.api_base_url.rstrip('/')}/mcp/accounts/"

    @property
    def mcp_market_url(self) -> str:
        return f"{self.api_base_url.rstrip('/')}/mcp/market/"

    def secret(self, name: str) -> str | None:
        """The plain value of an optional secret field, or None when unset."""
        value = getattr(self, name)
        return value.get_secret_value() if value else None


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    if settings.gauntlet_secret_key.get_secret_value() == DEV_SECRET_KEY and not settings.is_sqlite:
        logger.warning("GAUNTLET_SECRET_KEY is not set; MCP tokens use an insecure development key")
    return settings

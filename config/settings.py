"""
Application settings loaded from environment variables and .env file.
Uses pydantic-settings for validation and type coercion.

SAFETY DEFAULTS — all dangerous flags default to False.
Live trading and auto-live trading are LOCKED unless explicitly enabled.
"""

from pydantic_settings import BaseSettings
from pydantic import Field, field_validator
from functools import lru_cache
import re


class Settings(BaseSettings):
    """Central configuration for the AI Trading Assistant.

    Safety contract
    ---------------
    * ``ENABLE_LIVE_TRADING`` defaults to ``False`` — paper/mock mode only.
    * ``ENABLE_AUTO_LIVE_TRADING`` defaults to ``False`` — live auto locked.
    * Live auto-trading requires BOTH flags set to ``True``.
    * Auto paper trading only requires ``ENABLE_AUTO_MODE=True``.
    """

    # ── Alpaca API ────────────────────────────────────────────────────
    ALPACA_API_KEY: str = Field(default="", description="Alpaca API Key")
    ALPACA_SECRET_KEY: str = Field(default="", description="Alpaca Secret Key")
    ALPACA_BASE_URL: str = Field(
        default="https://paper-api.alpaca.markets",
        description="Alpaca Base URL (default: paper trading)",
    )

    # ── Safety Locks (all off by default) ────────────────────────────
    ENABLE_LIVE_TRADING: bool = Field(
        default=False,
        description="[DANGER] Enable live trading with real money. Must be explicit.",
    )
    ENABLE_AUTO_LIVE_TRADING: bool = Field(
        default=False,
        description="[DANGER] Enable fully-automated live trading. Requires ENABLE_LIVE_TRADING=True too.",
    )
    ENABLE_AUTO_MODE: bool = Field(
        default=False,
        description="Enable auto paper trading (paper/mock only).",
    )

    # ── Risk Limits ───────────────────────────────────────────────────
    MAX_DAILY_LOSS: float = Field(
        default=100.0, description="Max daily loss in USD before all trading halts"
    )
    MAX_POSITION_SIZE: float = Field(
        default=500.0, description="Max single position size in USD"
    )
    MAX_TRADES_PER_DAY: int = Field(
        default=5, description="Max number of trades executed per calendar day"
    )
    STOP_LOSS_PCT: float = Field(
        default=2.0, description="Stop-loss trigger in percent below entry price"
    )
    TAKE_PROFIT_PCT: float = Field(
        default=5.0, description="Take-profit trigger in percent above entry price"
    )
    COOLDOWN_SECONDS: int = Field(
        default=300,
        description="Mandatory cooldown in seconds after a losing trade closes",
    )

    # ── Order Safety ─────────────────────────────────────────────────
    REJECT_DUPLICATE_ORDERS: bool = Field(
        default=True,
        description="Reject duplicate orders (same ticker + side) within 60 seconds",
    )
    DUPLICATE_ORDER_WINDOW_SECONDS: int = Field(
        default=60,
        description="Window in seconds for duplicate-order detection",
    )
    REJECT_MARKET_CLOSED: bool = Field(
        default=True,
        description="Reject orders when the market is closed (live mode only)",
    )

    # ── Approval Workflow ─────────────────────────────────────────────
    ENABLE_APPROVAL_REQUIRED_LIVE_MODE: bool = Field(
        default=False,
        description="[SAFETY] Require explicit user approval before each live order.",
    )
    APPROVAL_EXPIRY_MINUTES: int = Field(
        default=5,
        description="Trade proposals auto-expire after this many minutes.",
    )
    MAX_PRICE_DRIFT_AFTER_APPROVAL_PERCENT: float = Field(
        default=0.5,
        description="Re-approval required if price moves more than this % after approval.",
    )

    # ── Portfolio Risk ────────────────────────────────────────────────
    MAX_PORTFOLIO_ALLOCATION_PER_TICKER_PERCENT: float = Field(
        default=20.0,
        description="Max % of portfolio value in a single ticker.",
    )
    MAX_RISK_PER_TRADE_PERCENT: float = Field(
        default=1.0,
        description="Max % of account equity risked per trade (used by position sizer).",
    )

    # ── Order Safety (Live) ───────────────────────────────────────────
    MAX_SPREAD_PERCENT: float = Field(
        default=0.5,
        description="Block live order if bid/ask spread exceeds this %.",
    )
    BLOCK_TRADES_NEAR_MARKET_CLOSE_MINUTES: int = Field(
        default=15,
        description="Block new orders this many minutes before market close (live mode).",
    )
    ALLOW_MARKET_ORDERS_LIVE: bool = Field(
        default=False,
        description="If false, live orders use limit orders only. Market orders require explicit opt-in.",
    )

    # ── Day Trading Agent (scales with account equity) ────────────────────
    DAY_TRADE_DAILY_TARGET_PCT: float = Field(
        default=0.75,
        description="Daily profit target as % of equity (0.75%% on $25k = $187.50)",
    )
    DAY_TRADE_DAILY_TARGET_USD: float = Field(
        default=0.0,
        description="Optional USD floor for daily target (0 = pct only). E.g. 100 on small accounts.",
    )
    DAY_TRADE_MAX_LOSS_PCT: float = Field(
        default=1.5,
        description="Stop trading for the day if loss exceeds this %% of equity",
    )
    DAY_TRADE_RISK_PER_TRADE_PCT: float = Field(
        default=0.75,
        description="Max risk per day trade as %% of equity",
    )
    DAY_TRADE_MAX_OPEN_POSITIONS: int = Field(
        default=3,
        description="Max simultaneous day-trade positions",
    )
    DAY_TRADE_MIN_SCORE: float = Field(
        default=68.0,
        description="Minimum scanner score to enter a day trade",
    )
    DAY_TRADE_RISK_REWARD: float = Field(
        default=2.0,
        description="Minimum reward:risk ratio for take-profit placement",
    )
    DAY_TRADE_FLAT_BEFORE_CLOSE_MIN: int = Field(
        default=15,
        description="Flatten all day-trade positions N minutes before close",
    )

    # ── AI / LLM ──────────────────────────────────────────────────────────────
    OPENAI_API_KEY: str = Field(default="", description="OpenAI API key for per-stock ChatGPT analysis")
    OPENAI_MODEL: str = Field(default="gpt-4o-mini", description="OpenAI model name")
    GEMINI_API_KEY: str = Field(default="", description="Google Gemini API key — default across the app")
    AI_PROVIDER: str = Field(
        default="gemini",
        description="Default AI everywhere: gemini | openai | auto (gemini first)",
    )
    AI_SCAN_PROVIDER: str = Field(
        default="gemini",
        description="Bulk scan table notes: gemini | openai | off",
    )
    AI_DEEP_PROVIDER: str = Field(
        default="openai",
        description="Per-stock analysis: openai (ChatGPT) | gemini",
    )
    AI_STOCK_PROVIDER: str = Field(
        default="openai",
        description="Same as AI_DEEP_PROVIDER — ChatGPT for each-stock deep dive",
    )
    AI_SCAN_TOP_N: int = Field(
        default=20,
        description="Max ranked picks to enrich with one Gemini batch call per scan",
    )

    # ── Database ──────────────────────────────────────────────────────────
    DATABASE_URL: str = Field(
        default="sqlite:///trading.db", description="SQLAlchemy database URL"
    )

    # ── Scan cache (Strategy Signals + US Market) ─────────────────────────
    SCAN_CACHE_REFRESH_MINUTES: int = Field(
        default=5,
        description="Full background re-scan interval; overwrites cached scan JSON in Postgres",
    )
    SCAN_UI_POLL_SECONDS: int = Field(
        default=30,
        description="How often the UI reloads to pick up new cached scan results",
    )

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }

    # ── Computed Properties ───────────────────────────────────────────

    @property
    def has_alpaca_keys(self) -> bool:
        """True if real Alpaca credentials are present."""
        placeholder = "your_alpaca_api_key_here"
        return bool(
            self.ALPACA_API_KEY
            and self.ALPACA_SECRET_KEY
            and self.ALPACA_API_KEY != placeholder
            and self.ALPACA_SECRET_KEY != placeholder
        )

    @property
    def is_paper_trading(self) -> bool:
        """True when the configured base URL is the Alpaca paper endpoint."""
        return "paper" in self.ALPACA_BASE_URL.lower()

    @property
    def is_live_trading(self) -> bool:
        """True ONLY when ENABLE_LIVE_TRADING is explicitly True AND a live URL is set."""
        return self.ENABLE_LIVE_TRADING and not self.is_paper_trading

    @property
    def is_live_auto_trading_allowed(self) -> bool:
        """Live auto-trading requires BOTH live and auto-live flags set."""
        return self.is_live_trading and self.ENABLE_AUTO_LIVE_TRADING

    @property
    def use_mock_broker(self) -> bool:
        """Use MockBroker when no real credentials are configured."""
        return not self.has_alpaca_keys

    @property
    def is_approval_mode_allowed(self) -> bool:
        """Approval-required live mode needs both live trading enabled AND the approval flag set."""
        return self.ENABLE_LIVE_TRADING and self.ENABLE_APPROVAL_REQUIRED_LIVE_MODE

    @property
    def approval_expiry_seconds(self) -> int:
        """Approval expiry in seconds (derived from APPROVAL_EXPIRY_MINUTES)."""
        return self.APPROVAL_EXPIRY_MINUTES * 60


@lru_cache()
def get_settings() -> Settings:
    """Return a cached Settings instance (loaded once per process)."""
    return Settings()

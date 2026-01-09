"""Configuration management using pydantic-settings v2."""

from pathlib import Path
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Alpaca API credentials
    ALPACA_API_KEY: str = Field(default="", description="Alpaca API key")
    ALPACA_SECRET_KEY: str = Field(default="", description="Alpaca secret key")
    ALPACA_PAPER: bool = Field(default=True, description="Use paper trading (default True)")
    ALLOW_LIVE: bool = Field(default=False, description="Allow live trading (must be explicitly True)")

    # Data and caching
    TIMEFRAME: str = Field(default="1Min", description="Default timeframe for bars")
    HIST_LOOKBACK_DAYS: int = Field(default=30, ge=1, description="Historical data lookback in days")
    CACHE_DIR: str = Field(default="./cache", description="Directory for cached data")

    # Universe behavior
    USE_ALL_ALPACA_CRYPTO: bool = Field(default=True, description="Use all tradable crypto pairs")
    SYMBOLS: str = Field(default="", description="Optional override: comma-separated symbols (e.g., BTC/USD,ETH/USD)")
    UNIVERSE_TOP_N: str = Field(default="ALL", description="Top N symbols by volume, or ALL")
    MIN_AVG_DOLLAR_VOL: float = Field(default=0.0, ge=0.0, description="Minimum average dollar volume filter")
    QUOTE_FILTER: str = Field(default="", description="Optional quote currency filter (e.g., USD,USDC,USDT)")
    EXCLUDE_SYMBOLS: str = Field(default="", description="Comma-separated symbols to exclude")

    # Risk controls
    MAX_POSITION_NOTIONAL_PER_SYMBOL: float = Field(default=500.0, gt=0, description="Max position size per symbol (USD)")
    TOTAL_MAX_NOTIONAL: float = Field(default=5000.0, gt=0, description="Max total exposure (USD)")
    MAX_ORDER_NOTIONAL: float = Field(default=200.0, gt=0, description="Max order size (USD)")
    MAX_ORDER_QTY: float = Field(default=10000000.0, gt=0, description="Max order quantity to prevent overflow (e.g., 10M shares)")
    MAX_POSITION_QTY: float = Field(default=100000000.0, gt=0, description="Max position quantity to prevent overflow (e.g., 100M shares)")
    MAX_OPEN_ORDERS_PER_SYMBOL: int = Field(default=2, ge=1, description="Max open orders per symbol")
    MAX_DAILY_LOSS: float = Field(default=100.0, gt=0, description="Max daily loss before halt (USD)")
    STALE_DATA_SECONDS: int = Field(default=5, ge=1, description="Max seconds before data considered stale")
    PRICE_BAND_BPS: int = Field(default=150, ge=0, description="Reject limit orders this many bps from mid price")
    KILL_SWITCH_FILE: str = Field(default="./KILL", description="Path to kill switch file")

    # Execution
    ORDER_REFRESH_MS: int = Field(default=2000, ge=100, description="Order refresh interval in milliseconds")
    MIN_SECONDS_BETWEEN_REPLACES: float = Field(default=1.5, gt=0, description="Min seconds between order replacements")
    DEFAULT_TIME_IN_FORCE: str = Field(default="gtc", description="Default time in force (gtc or ioc)")
    DEFAULT_ORDER_TYPE: str = Field(default="limit", description="Default order type (limit or market)")

    @field_validator("DEFAULT_TIME_IN_FORCE")
    @classmethod
    def validate_time_in_force(cls, v: str) -> str:
        """Validate time in force is allowed."""
        allowed = {"gtc", "ioc"}
        if v.lower() not in allowed:
            raise ValueError(f"Time in force must be one of {allowed}")
        return v.lower()

    @field_validator("DEFAULT_ORDER_TYPE")
    @classmethod
    def validate_order_type(cls, v: str) -> str:
        """Validate order type is allowed."""
        allowed = {"limit", "market"}
        if v.lower() not in allowed:
            raise ValueError(f"Order type must be one of {allowed}")
        return v.lower()

    @field_validator("ALPACA_PAPER", "ALLOW_LIVE", mode="before")
    @classmethod
    def parse_bool(cls, v) -> bool:
        """Parse boolean from string."""
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            return v.lower() in ("true", "1", "yes", "on")
        return False

    def get_cache_dir(self) -> Path:
        """Get cache directory as Path, creating if needed."""
        cache_path = Path(self.CACHE_DIR)
        cache_path.mkdir(parents=True, exist_ok=True)
        return cache_path

    def get_symbol_list(self) -> list[str]:
        """Parse SYMBOLS override into a list."""
        if not self.SYMBOLS:
            return []
        return [s.strip() for s in self.SYMBOLS.split(",") if s.strip()]

    def get_quote_filter_list(self) -> list[str]:
        """Parse QUOTE_FILTER into a list."""
        if not self.QUOTE_FILTER:
            return []
        return [q.strip() for q in self.QUOTE_FILTER.split(",") if q.strip()]

    def get_exclude_symbols_list(self) -> list[str]:
        """Parse EXCLUDE_SYMBOLS into a list."""
        if not self.EXCLUDE_SYMBOLS:
            return []
        return [s.strip() for s in self.EXCLUDE_SYMBOLS.split(",") if s.strip()]

    def get_universe_top_n(self) -> int | None:
        """Parse UNIVERSE_TOP_N as int or None for ALL."""
        if self.UNIVERSE_TOP_N.upper() == "ALL":
            return None
        try:
            return int(self.UNIVERSE_TOP_N)
        except ValueError:
            raise ValueError(f"UNIVERSE_TOP_N must be 'ALL' or an integer, got {self.UNIVERSE_TOP_N}")


# Global settings instance
settings = Settings()




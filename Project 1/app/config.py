"""
Configuration module using dataclasses and environment variables.

All settings are centralized here for easy modification and environment-based overrides.
"""

from dataclasses import dataclass, field
from typing import Optional, List
import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file - check both app/ and parent Project 1/ directories
load_dotenv()  # Current directory (app/.env)
load_dotenv(Path(__file__).parent.parent / ".env")  # Parent directory (Project 1/.env)


def _get_bool_env(key: str, default: bool = False) -> bool:
    """Parse boolean environment variable."""
    val = os.getenv(key, str(default)).lower()
    return val in ("true", "1", "yes", "on")


def _get_float_env(key: str, default: float) -> float:
    """Parse float environment variable."""
    return float(os.getenv(key, str(default)))


def _get_int_env(key: str, default: int) -> int:
    """Parse integer environment variable."""
    return int(os.getenv(key, str(default)))


@dataclass
class AlpacaConfig:
    """Alpaca API configuration."""
    api_key: str = field(default_factory=lambda: os.getenv("ALPACA_API_KEY", ""))
    secret_key: str = field(default_factory=lambda: os.getenv("ALPACA_SECRET_KEY", ""))
    paper: bool = field(default_factory=lambda: _get_bool_env("ALPACA_PAPER", True))
    data_feed: str = field(default_factory=lambda: os.getenv("ALPACA_DATA_FEED", "iex"))
    base_url_trading: Optional[str] = field(
        default_factory=lambda: os.getenv("BASE_URL_TRADING")
    )
    base_url_data: Optional[str] = field(
        default_factory=lambda: os.getenv("BASE_URL_DATA")
    )
    
    def __post_init__(self) -> None:
        """Validate configuration."""
        if not self.api_key or not self.secret_key:
            raise ValueError(
                "ALPACA_API_KEY and ALPACA_SECRET_KEY environment variables must be set"
            )
        if self.data_feed not in ("iex", "sip"):
            raise ValueError("ALPACA_DATA_FEED must be 'iex' or 'sip'")


@dataclass
class HMMConfig:
    """Hidden Markov Model configuration."""
    n_states: int = 3
    lookback_years: int = field(default_factory=lambda: _get_int_env("HMM_LOOKBACK_YEARS", 5))
    refit_days: int = field(default_factory=lambda: _get_int_env("HMM_REFIT_DAYS", 21))
    use_rolling_window: bool = field(default_factory=lambda: _get_bool_env("HMM_ROLLING_WINDOW", False))
    rolling_window_days: int = field(default_factory=lambda: _get_int_env("HMM_ROLLING_WINDOW_DAYS", 504))
    market_proxy: str = "SPY"
    # Probability thresholds for regime confirmation
    bull_prob_threshold: float = field(default_factory=lambda: _get_float_env("BULL_PROB_THRESHOLD", 0.60))
    bear_prob_threshold: float = field(default_factory=lambda: _get_float_env("BEAR_PROB_THRESHOLD", 0.60))


@dataclass
class IndicatorConfig:
    """Technical indicator configuration."""
    rsi_period: int = 14
    rsi_oversold: float = field(default_factory=lambda: _get_float_env("RSI_OVERSOLD", 35.0))
    rsi_overbought: float = field(default_factory=lambda: _get_float_env("RSI_OVERBOUGHT", 65.0))
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    atr_period: int = 14
    # Trend filter SMAs
    trend_filter_enabled: bool = field(default_factory=lambda: _get_bool_env("TREND_FILTER_ENABLED", True))
    trend_sma_fast: int = field(default_factory=lambda: _get_int_env("TREND_SMA_FAST", 50))
    trend_sma_slow: int = field(default_factory=lambda: _get_int_env("TREND_SMA_SLOW", 200))


@dataclass
class SentimentConfig:
    """Sentiment analysis configuration."""
    model_name: str = "ProsusAI/finbert"
    aggregation_method: str = field(default_factory=lambda: os.getenv("SENTIMENT_AGG_METHOD", "mean"))
    cache_file: str = "sentiment_cache.csv"
    
    # Sentiment mode: "soft" | "strict" | "off"
    mode: str = field(default_factory=lambda: os.getenv("SENTIMENT_MODE", "soft"))
    lookback_days: int = field(default_factory=lambda: _get_int_env("SENTIMENT_LOOKBACK_DAYS", 3))
    min_articles: int = field(default_factory=lambda: _get_int_env("SENTIMENT_MIN_ARTICLES", 1))
    
    # Strict mode thresholds
    strict_long_pos: float = field(default_factory=lambda: _get_float_env("SENTIMENT_STRICT_LONG_POS", 0.60))
    strict_short_neg: float = field(default_factory=lambda: _get_float_env("SENTIMENT_STRICT_SHORT_NEG", 0.60))
    
    # Soft mode thresholds
    soft_min_confirm: float = field(default_factory=lambda: _get_float_env("SENTIMENT_SOFT_MIN_CONFIRM", 0.45))
    soft_max_opposite: float = field(default_factory=lambda: _get_float_env("SENTIMENT_SOFT_MAX_OPPOSITE", 0.60))
    
    # Timeout for fetching (RSS)
    timeout_sec: int = field(default_factory=lambda: _get_int_env("SENTIMENT_TIMEOUT_SEC", 10))


@dataclass
class RiskConfig:
    """Risk management configuration."""
    risk_per_trade_pct: float = field(default_factory=lambda: _get_float_env("RISK_PER_TRADE_PCT", 1.0))
    atr_multiplier: float = field(default_factory=lambda: _get_float_env("ATR_MULTIPLIER", 1.5))
    max_position_pct: float = field(default_factory=lambda: _get_float_env("MAX_POSITION_PCT", 10.0))
    max_gross_exposure_pct: float = field(default_factory=lambda: _get_float_env("MAX_GROSS_EXPOSURE_PCT", 100.0))
    
    # Stop loss configuration
    hard_stop_pct: float = field(default_factory=lambda: _get_float_env("HARD_STOP_PCT", 0.02))  # 2%
    stop_atr_mult: float = field(default_factory=lambda: _get_float_env("STOP_ATR_MULT", 1.5))
    
    # Trailing stop
    trailing_activation_pct: float = field(default_factory=lambda: _get_float_env("TRAILING_ACTIVATION_PCT", 5.0))
    trailing_stop_pct: float = field(default_factory=lambda: _get_float_env("TRAILING_STOP_PCT", 2.0))
    
    # Time stop
    time_stop_enabled: bool = field(default_factory=lambda: _get_bool_env("TIME_STOP_ENABLED", True))
    max_hold_days: int = field(default_factory=lambda: _get_int_env("MAX_HOLD_DAYS", 10))
    
    # Cooldown after hard stop
    cooldown_days_after_hard_stop: int = field(default_factory=lambda: _get_int_env("COOLDOWN_DAYS_AFTER_HARD_STOP", 3))
    
    # Regime exit
    regime_flip_exit: bool = field(default_factory=lambda: _get_bool_env("REGIME_FLIP_EXIT", False))


@dataclass
class BacktestConfig:
    """Backtesting configuration."""
    initial_capital: float = field(default_factory=lambda: _get_float_env("INITIAL_CAPITAL", 100000.0))
    fee_rate: float = field(default_factory=lambda: _get_float_env("FEE_RATE", 0.001))  # 0.1% per side
    min_symbol_bars: int = field(default_factory=lambda: _get_int_env("MIN_SYMBOL_BARS", 400))


@dataclass
class APIConfig:
    """FastAPI server configuration."""
    host: str = field(default_factory=lambda: os.getenv("API_HOST", "0.0.0.0"))
    port: int = field(default_factory=lambda: _get_int_env("API_PORT", 8000))
    cors_origins: List[str] = field(
        default_factory=lambda: os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:5173").split(",")
    )
    reload: bool = field(default_factory=lambda: _get_bool_env("API_RELOAD", False))


@dataclass
class PathConfig:
    """File path configuration."""
    base_dir: Path = field(default_factory=lambda: Path(__file__).parent)
    data_dir: Path = field(init=False)
    reports_dir: Path = field(init=False)
    bars_cache_dir: Path = field(init=False)
    news_cache_dir: Path = field(init=False)
    
    def __post_init__(self) -> None:
        """Initialize derived paths."""
        self.data_dir = self.base_dir / "data"
        self.reports_dir = self.base_dir / "reports"
        self.bars_cache_dir = self.data_dir / "bars"
        self.news_cache_dir = self.data_dir / "news"
        
        # Create directories if they don't exist
        self.data_dir.mkdir(exist_ok=True)
        self.reports_dir.mkdir(exist_ok=True)
        self.bars_cache_dir.mkdir(exist_ok=True)
        self.news_cache_dir.mkdir(exist_ok=True)


@dataclass
class RSSConfig:
    """RSS feed fallback configuration."""
    enabled: bool = field(default_factory=lambda: _get_bool_env("RSS_FALLBACK_ENABLED", True))
    feeds: List[str] = field(default_factory=lambda: [
        "https://feeds.finance.yahoo.com/rss/2.0/headline?s={symbol}&region=US&lang=en-US",
        "https://www.investing.com/rss/news.rss",
        "https://feeds.marketwatch.com/marketwatch/topstories/",
        "https://seekingalpha.com/feed.xml",
    ])
    lookback_days: int = field(default_factory=lambda: _get_int_env("RSS_LOOKBACK_DAYS", 3))
    timeout_sec: int = field(default_factory=lambda: _get_int_env("RSS_TIMEOUT_SEC", 10))
    historical_notice: bool = field(default_factory=lambda: _get_bool_env("RSS_HISTORICAL_NOTICE", True))


@dataclass
class LiveConfig:
    """Live trading configuration."""
    scan_interval_minutes: int = field(default_factory=lambda: _get_int_env("LIVE_SCAN_INTERVAL", 60))
    scan_interval_seconds: int = field(default_factory=lambda: _get_int_env("LIVE_INTERVAL_SEC", 300))
    daily_run_time: str = field(default_factory=lambda: os.getenv("LIVE_RUN_TIME", "09:35"))
    mode: str = field(default_factory=lambda: os.getenv("LIVE_MODE", "interval"))  # "scheduled" or "interval"
    run_once_default: bool = field(default_factory=lambda: _get_bool_env("LIVE_RUN_ONCE_DEFAULT", False))


@dataclass
class Config:
    """Master configuration container."""
    alpaca: AlpacaConfig = field(default_factory=AlpacaConfig)
    hmm: HMMConfig = field(default_factory=HMMConfig)
    indicators: IndicatorConfig = field(default_factory=IndicatorConfig)
    sentiment: SentimentConfig = field(default_factory=SentimentConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    backtest: BacktestConfig = field(default_factory=BacktestConfig)
    api: APIConfig = field(default_factory=APIConfig)
    paths: PathConfig = field(default_factory=PathConfig)
    rss: RSSConfig = field(default_factory=RSSConfig)
    live: LiveConfig = field(default_factory=LiveConfig)


def load_config() -> Config:
    """
    Load configuration from environment variables.
    
    Returns:
        Config: Fully initialized configuration object.
    
    Raises:
        ValueError: If required environment variables are missing.
    """
    return Config()


# Global config instance (lazy loaded)
_config: Optional[Config] = None


def get_config() -> Config:
    """
    Get or create the global configuration instance.
    
    Returns:
        Config: Global configuration object.
    """
    global _config
    if _config is None:
        _config = load_config()
    return _config

"""
Utility functions for the trading bot.

Contains helpers for time handling, formatting, safe math, and logging setup.
"""

import logging
import math
from datetime import datetime, timezone, timedelta
from typing import Optional, Union
import pandas as pd
import numpy as np


def setup_logging(
    level: int = logging.INFO,
    format_string: Optional[str] = None
) -> logging.Logger:
    """
    Configure and return the root logger.
    
    Args:
        level: Logging level (default INFO).
        format_string: Custom format string.
    
    Returns:
        logging.Logger: Configured logger.
    """
    if format_string is None:
        format_string = "%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s"
    
    logging.basicConfig(
        level=level,
        format=format_string,
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    # Reduce noise from third-party libraries
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("alpaca").setLevel(logging.WARNING)
    logging.getLogger("transformers").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    
    return logging.getLogger("tradingbot")


def get_logger(name: str) -> logging.Logger:
    """
    Get a named logger.
    
    Args:
        name: Logger name.
    
    Returns:
        logging.Logger: Named logger instance.
    """
    return logging.getLogger(f"tradingbot.{name}")


def utc_now() -> datetime:
    """
    Get current UTC datetime.
    
    Returns:
        datetime: Current UTC time with timezone info.
    """
    return datetime.now(timezone.utc)


def to_utc(dt: datetime) -> datetime:
    """
    Convert datetime to UTC.
    
    Args:
        dt: Datetime object (may or may not have timezone).
    
    Returns:
        datetime: Datetime in UTC.
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def ensure_utc(dt: datetime) -> datetime:
    """
    Ensure datetime is timezone-aware UTC.
    
    Args:
        dt: Datetime object.
    
    Returns:
        datetime: UTC-aware datetime.
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def market_date(dt: Optional[datetime] = None) -> datetime:
    """
    Get market date (date portion in US Eastern time logic).
    
    Args:
        dt: Datetime to convert (default: now).
    
    Returns:
        datetime: Market date as datetime at midnight UTC.
    """
    if dt is None:
        dt = utc_now()
    # Simple approach: use the date portion
    return datetime(dt.year, dt.month, dt.day, tzinfo=timezone.utc)


def trading_days_ago(days: int, from_date: Optional[datetime] = None) -> datetime:
    """
    Calculate approximate date N trading days ago.
    
    Args:
        days: Number of trading days.
        from_date: Starting date (default: now).
    
    Returns:
        datetime: Approximate date N trading days ago.
    """
    if from_date is None:
        from_date = utc_now()
    # Approximate: 252 trading days per year, ~1.4 calendar days per trading day
    calendar_days = int(days * 1.45)
    return from_date - timedelta(days=calendar_days)


def years_ago(years: int, from_date: Optional[datetime] = None) -> datetime:
    """
    Calculate date N years ago.
    
    Args:
        years: Number of years.
        from_date: Starting date (default: now).
    
    Returns:
        datetime: Date N years ago.
    """
    if from_date is None:
        from_date = utc_now()
    try:
        return from_date.replace(year=from_date.year - years)
    except ValueError:
        # Handle Feb 29
        return from_date.replace(year=from_date.year - years, day=28)


def safe_divide(
    numerator: Union[float, int],
    denominator: Union[float, int],
    default: float = 0.0
) -> float:
    """
    Safely divide two numbers, returning default if division fails.
    
    Args:
        numerator: The numerator.
        denominator: The denominator.
        default: Value to return on division error.
    
    Returns:
        float: Result of division or default.
    """
    if denominator == 0 or math.isnan(denominator) or math.isnan(numerator):
        return default
    result = numerator / denominator
    if math.isnan(result) or math.isinf(result):
        return default
    return result


def safe_log(value: float, default: float = float("-inf")) -> float:
    """
    Safely compute natural logarithm.
    
    Args:
        value: Value to take log of.
        default: Value to return if log fails.
    
    Returns:
        float: Natural log or default.
    """
    if value <= 0 or math.isnan(value):
        return default
    return math.log(value)


def safe_sqrt(value: float, default: float = 0.0) -> float:
    """
    Safely compute square root.
    
    Args:
        value: Value to take sqrt of.
        default: Value to return if sqrt fails.
    
    Returns:
        float: Square root or default.
    """
    if value < 0 or math.isnan(value):
        return default
    return math.sqrt(value)


def round_to_cents(value: float) -> float:
    """
    Round to 2 decimal places (cents).
    
    Args:
        value: Dollar amount.
    
    Returns:
        float: Rounded amount.
    """
    return round(value, 2)


def round_shares(shares: float) -> int:
    """
    Round shares down to nearest whole number.
    
    Args:
        shares: Fractional share count.
    
    Returns:
        int: Whole shares.
    """
    return int(math.floor(shares))


def pct_change(old_value: float, new_value: float) -> float:
    """
    Calculate percentage change.
    
    Args:
        old_value: Original value.
        new_value: New value.
    
    Returns:
        float: Percentage change (e.g., 0.05 for 5%).
    """
    return safe_divide(new_value - old_value, old_value)


def annualize_return(total_return: float, days: int) -> float:
    """
    Annualize a total return.
    
    Args:
        total_return: Total return (e.g., 0.25 for 25%).
        days: Number of trading days.
    
    Returns:
        float: Annualized return.
    """
    if days <= 0:
        return 0.0
    return (1 + total_return) ** (252 / days) - 1


def format_pct(value: float, decimals: int = 2) -> str:
    """
    Format a decimal as percentage string.
    
    Args:
        value: Decimal value (e.g., 0.05).
        decimals: Number of decimal places.
    
    Returns:
        str: Formatted percentage (e.g., "5.00%").
    """
    return f"{value * 100:.{decimals}f}%"


def format_currency(value: float, symbol: str = "$") -> str:
    """
    Format a value as currency.
    
    Args:
        value: Dollar amount.
        symbol: Currency symbol.
    
    Returns:
        str: Formatted currency string.
    """
    return f"{symbol}{value:,.2f}"


def timestamp_to_str(dt: datetime, fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    """
    Format datetime as string.
    
    Args:
        dt: Datetime object.
        fmt: Format string.
    
    Returns:
        str: Formatted datetime string.
    """
    return dt.strftime(fmt)


def str_to_timestamp(s: str, fmt: str = "%Y-%m-%d") -> datetime:
    """
    Parse string to datetime.
    
    Args:
        s: Date string.
        fmt: Format string.
    
    Returns:
        datetime: Parsed datetime with UTC timezone.
    """
    dt = datetime.strptime(s, fmt)
    return dt.replace(tzinfo=timezone.utc)


def ensure_tz_aware(
    df: pd.DataFrame,
    datetime_col: str = "timestamp"
) -> pd.DataFrame:
    """
    Ensure datetime column is timezone-aware (UTC).
    
    Args:
        df: DataFrame with datetime column.
        datetime_col: Name of datetime column.
    
    Returns:
        pd.DataFrame: DataFrame with UTC-aware timestamps.
    """
    if datetime_col in df.columns:
        if df[datetime_col].dt.tz is None:
            df[datetime_col] = df[datetime_col].dt.tz_localize("UTC")
        else:
            df[datetime_col] = df[datetime_col].dt.tz_convert("UTC")
    return df


def hash_text(text: str) -> str:
    """
    Create a hash of text for caching purposes.
    
    Args:
        text: Text to hash.
    
    Returns:
        str: SHA256 hash hex string.
    """
    import hashlib
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def chunk_list(lst: list, chunk_size: int) -> list:
    """
    Split list into chunks.
    
    Args:
        lst: List to split.
        chunk_size: Maximum chunk size.
    
    Returns:
        list: List of chunks.
    """
    return [lst[i:i + chunk_size] for i in range(0, len(lst), chunk_size)]


def clamp(value: float, min_val: float, max_val: float) -> float:
    """
    Clamp a value between min and max.
    
    Args:
        value: Value to clamp.
        min_val: Minimum allowed.
        max_val: Maximum allowed.
    
    Returns:
        float: Clamped value.
    """
    return max(min_val, min(value, max_val))


def is_market_open(dt: Optional[datetime] = None) -> bool:
    """
    Simple check if within typical US market hours (9:30 AM - 4:00 PM ET).
    
    Note: This is approximate and doesn't account for holidays.
    For production, use Alpaca's market calendar.
    
    Args:
        dt: Datetime to check (default: now).
    
    Returns:
        bool: True if likely market hours.
    """
    if dt is None:
        dt = utc_now()
    
    # Convert to approximate ET (UTC-5 or UTC-4 depending on DST)
    # This is simplified; production should use proper timezone
    et_hour = (dt.hour - 5) % 24  # Approximate EST
    et_minute = dt.minute
    
    # Weekday check (0=Monday, 6=Sunday)
    if dt.weekday() >= 5:
        return False
    
    # Time check: 9:30 AM - 4:00 PM ET
    if et_hour < 9 or et_hour > 16:
        return False
    if et_hour == 9 and et_minute < 30:
        return False
    if et_hour == 16 and et_minute > 0:
        return False
    
    return True


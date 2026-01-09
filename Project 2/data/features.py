"""Simple and stable feature engineering from bars."""

import pandas as pd
import numpy as np


def rolling_mean(series: pd.Series, window: int) -> pd.Series:
    """Calculate rolling mean."""
    return series.rolling(window=window, min_periods=1).mean()


def rolling_std(series: pd.Series, window: int) -> pd.Series:
    """Calculate rolling standard deviation."""
    return series.rolling(window=window, min_periods=1).std()


def rolling_min(series: pd.Series, window: int) -> pd.Series:
    """Calculate rolling minimum."""
    return series.rolling(window=window, min_periods=1).min()


def rolling_max(series: pd.Series, window: int) -> pd.Series:
    """Calculate rolling maximum."""
    return series.rolling(window=window, min_periods=1).max()


def returns(series: pd.Series) -> pd.Series:
    """Calculate returns (pct_change)."""
    return series.pct_change()


def log_returns(series: pd.Series) -> pd.Series:
    """Calculate log returns."""
    return np.log(series / series.shift(1))


def rsi(series: pd.Series, window: int = 14) -> pd.Series:
    """
    Calculate RSI (Relative Strength Index).

    Args:
        series: Price series
        window: Window size (default 14)

    Returns:
        RSI series (0-100)
    """
    delta = series.diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)

    avg_gain = gain.rolling(window=window, min_periods=1).mean()
    avg_loss = loss.rolling(window=window, min_periods=1).mean()

    rs = avg_gain / (avg_loss + 1e-10)  # Avoid division by zero
    rsi = 100 - (100 / (1 + rs))

    return rsi


def bollinger_bands(series: pd.Series, window: int = 20, num_std: float = 2.0) -> tuple[pd.Series, pd.Series, pd.Series]:
    """
    Calculate Bollinger Bands.

    Args:
        series: Price series
        window: Window size
        num_std: Number of standard deviations

    Returns:
        Tuple of (upper_band, middle_band, lower_band)
    """
    middle = rolling_mean(series, window)
    std = rolling_std(series, window)
    upper = middle + (std * num_std)
    lower = middle - (std * num_std)

    return upper, middle, lower


def volatility(returns: pd.Series, window: int = 20) -> pd.Series:
    """
    Calculate rolling volatility (annualized).

    Args:
        returns: Returns series
        window: Window size
        annualization_factor: Factor to annualize (e.g., 252 for daily, sqrt(252) for daily to annual)

    Returns:
        Volatility series (annualized)
    """
    # Assuming returns are daily
    vol = rolling_std(returns, window) * np.sqrt(252)
    return vol









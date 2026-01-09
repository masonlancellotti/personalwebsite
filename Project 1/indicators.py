"""Technical indicator calculations."""
import pandas as pd
import numpy as np
import pandas_ta as ta


def calculate_rsi(prices: pd.Series, period: int = 14) -> pd.Series:
    """
    Calculate Relative Strength Index (RSI).
    
    Args:
        prices: Series of closing prices
        period: RSI period (default 14)
        
    Returns:
        Series of RSI values
    """
    return ta.rsi(prices, length=period)


def calculate_macd(
    prices: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9
) -> pd.DataFrame:
    """
    Calculate MACD (Moving Average Convergence Divergence).
    
    Args:
        prices: Series of closing prices
        fast: Fast EMA period (default 12)
        slow: Slow EMA period (default 26)
        signal: Signal line EMA period (default 9)
        
    Returns:
        DataFrame with columns: MACD, MACD_signal, MACD_hist
    """
    macd = ta.macd(prices, fast=fast, slow=slow, signal=signal)
    return macd


def calculate_sma(prices: pd.Series, period: int) -> pd.Series:
    """
    Calculate Simple Moving Average (SMA).
    
    Args:
        prices: Series of prices
        period: SMA period
        
    Returns:
        Series of SMA values
    """
    return ta.sma(prices, length=period)


def calculate_ema(prices: pd.Series, period: int) -> pd.Series:
    """
    Calculate Exponential Moving Average (EMA).
    
    Args:
        prices: Series of prices
        period: EMA period
        
    Returns:
        Series of EMA values
    """
    return ta.ema(prices, length=period)


def calculate_bollinger_bands(
    prices: pd.Series,
    period: int = 20,
    std_dev: int = 2
) -> pd.DataFrame:
    """
    Calculate Bollinger Bands.
    
    Args:
        prices: Series of closing prices
        period: Moving average period (default 20)
        std_dev: Number of standard deviations (default 2)
        
    Returns:
        DataFrame with columns: BBU (upper), BBM (middle), BBL (lower)
    """
    bb = ta.bbands(prices, length=period, std=std_dev)
    return bb


def calculate_volume_sma(volume: pd.Series, period: int = 20) -> pd.Series:
    """
    Calculate Simple Moving Average of volume.
    
    Args:
        volume: Series of volume values
        period: SMA period (default 20)
        
    Returns:
        Series of volume SMA values
    """
    return ta.sma(volume, length=period)


def calculate_atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """
    Calculate Average True Range (ATR).
    
    Args:
        high: Series of high prices
        low: Series of low prices
        close: Series of close prices
        period: ATR period (default 14)
        
    Returns:
        Series of ATR values
    """
    return ta.atr(high=high, low=low, close=close, length=period)


def calculate_stochastic(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    k_period: int = 14,
    d_period: int = 3
) -> pd.DataFrame:
    """
    Calculate Stochastic Oscillator.
    
    Args:
        high: Series of high prices
        low: Series of low prices
        close: Series of close prices
        k_period: %K period (default 14)
        d_period: %D period (default 3)
        
    Returns:
        DataFrame with columns: STOCHk, STOCHd
    """
    stoch = ta.stoch(high=high, low=low, close=close, k=k_period, d=d_period)
    return stoch


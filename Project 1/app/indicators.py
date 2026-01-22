"""
Technical indicators module.

Manual implementations of RSI, MACD, ATR, and SMA using Wilder smoothing.
No external TA library dependencies.
"""

import logging
from typing import Optional, Tuple, List, Sequence
import numpy as np
import pandas as pd

from config import get_config, IndicatorConfig

logger = logging.getLogger("tradingbot.indicators")


def sma(values: Sequence[float], period: int) -> List[Optional[float]]:
    """
    Simple Moving Average.
    
    Args:
        values: Sequence of values.
        period: SMA period.
    
    Returns:
        List of SMA values (None until enough bars exist).
    """
    result: List[Optional[float]] = []
    values_list = list(values)
    
    for i in range(len(values_list)):
        if i < period - 1:
            result.append(None)
        else:
            window = values_list[i - period + 1:i + 1]
            result.append(sum(window) / period)
    
    return result


def last_sma(values: Sequence[float], period: int) -> Optional[float]:
    """
    Get the last SMA value.
    
    Args:
        values: Sequence of values.
        period: SMA period.
    
    Returns:
        Last SMA value, or None if not enough bars.
    """
    values_list = list(values)
    if len(values_list) < period:
        return None
    return sum(values_list[-period:]) / period


def calculate_sma(close: pd.Series, period: int) -> pd.Series:
    """
    Calculate Simple Moving Average for a pandas Series.
    
    Args:
        close: Series of closing prices.
        period: SMA period.
    
    Returns:
        pd.Series: SMA values (NaN until enough bars exist).
    """
    return close.rolling(window=period, min_periods=period).mean()


def wilder_smoothing(values: pd.Series, period: int) -> pd.Series:
    """
    Wilder's smoothing method (exponential moving average variant).
    
    Used for RSI and ATR calculations.
    
    Args:
        values: Series of values to smooth.
        period: Smoothing period.
    
    Returns:
        pd.Series: Smoothed values.
    """
    alpha = 1.0 / period
    return values.ewm(alpha=alpha, adjust=False).mean()


def ema(values: pd.Series, period: int) -> pd.Series:
    """
    Exponential Moving Average.
    
    Args:
        values: Series of values.
        period: EMA period.
    
    Returns:
        pd.Series: EMA values.
    """
    return values.ewm(span=period, adjust=False).mean()


def calculate_rsi(
    close: pd.Series,
    period: int = 14
) -> pd.Series:
    """
    Calculate Relative Strength Index using Wilder smoothing.
    
    RSI = 100 - (100 / (1 + RS))
    where RS = Average Gain / Average Loss
    
    Args:
        close: Series of closing prices.
        period: RSI period (default 14).
    
    Returns:
        pd.Series: RSI values (0-100 scale).
    """
    # Calculate price changes
    delta = close.diff()
    
    # Separate gains and losses
    gains = delta.where(delta > 0, 0.0)
    losses = (-delta).where(delta < 0, 0.0)
    
    # Apply Wilder smoothing
    avg_gain = wilder_smoothing(gains, period)
    avg_loss = wilder_smoothing(losses, period)
    
    # Calculate RS and RSI
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    
    # Handle edge cases
    rsi = rsi.fillna(50)  # Neutral when undefined
    
    return rsi


def calculate_macd(
    close: pd.Series,
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9
) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """
    Calculate MACD (Moving Average Convergence Divergence).
    
    MACD Line = EMA(fast) - EMA(slow)
    Signal Line = EMA(signal) of MACD Line
    Histogram = MACD Line - Signal Line
    
    Args:
        close: Series of closing prices.
        fast_period: Fast EMA period (default 12).
        slow_period: Slow EMA period (default 26).
        signal_period: Signal line period (default 9).
    
    Returns:
        Tuple of (macd_line, signal_line, histogram).
    """
    # Calculate EMAs
    ema_fast = ema(close, fast_period)
    ema_slow = ema(close, slow_period)
    
    # MACD line
    macd_line = ema_fast - ema_slow
    
    # Signal line
    signal_line = ema(macd_line, signal_period)
    
    # Histogram
    histogram = macd_line - signal_line
    
    return macd_line, signal_line, histogram


def calculate_atr(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 14
) -> pd.Series:
    """
    Calculate Average True Range using Wilder smoothing.
    
    True Range = max(high-low, abs(high-prev_close), abs(low-prev_close))
    ATR = Wilder smoothed TR
    
    Args:
        high: Series of high prices.
        low: Series of low prices.
        close: Series of closing prices.
        period: ATR period (default 14).
    
    Returns:
        pd.Series: ATR values.
    """
    # Previous close
    prev_close = close.shift(1)
    
    # True Range components
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    
    # True Range is the maximum
    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    
    # Apply Wilder smoothing
    atr = wilder_smoothing(true_range, period)
    
    return atr


def macd_crossover(
    macd_line: pd.Series,
    signal_line: pd.Series
) -> Tuple[pd.Series, pd.Series]:
    """
    Detect MACD crossovers.
    
    Bullish crossover: MACD crosses above signal line
    Bearish crossover: MACD crosses below signal line
    
    Args:
        macd_line: MACD line values.
        signal_line: Signal line values.
    
    Returns:
        Tuple of (bullish_crossover, bearish_crossover) boolean Series.
    """
    # Previous values
    prev_macd = macd_line.shift(1)
    prev_signal = signal_line.shift(1)
    
    # Bullish: MACD was <= signal, now > signal
    bullish = (prev_macd <= prev_signal) & (macd_line > signal_line)
    
    # Bearish: MACD was >= signal, now < signal
    bearish = (prev_macd >= prev_signal) & (macd_line < signal_line)
    
    return bullish, bearish


class TechnicalIndicators:
    """
    Technical indicator calculator for a single symbol.
    
    Computes and stores RSI, MACD, and ATR values.
    """
    
    def __init__(self, config: Optional[IndicatorConfig] = None):
        """
        Initialize indicator calculator.
        
        Args:
            config: Indicator configuration.
        """
        self._config = config or get_config().indicators
        self._indicators: Optional[pd.DataFrame] = None
        
    def calculate(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate all technical indicators for OHLCV data.
        
        Args:
            df: DataFrame with columns: timestamp, open, high, low, close, volume
        
        Returns:
            DataFrame with added indicator columns:
            rsi, macd, macd_signal, macd_hist, atr, macd_bullish_cross, macd_bearish_cross,
            sma_fast, sma_slow
        """
        result = df.copy()
        
        # RSI
        result['rsi'] = calculate_rsi(df['close'], self._config.rsi_period)
        
        # MACD
        macd_line, signal_line, histogram = calculate_macd(
            df['close'],
            self._config.macd_fast,
            self._config.macd_slow,
            self._config.macd_signal
        )
        result['macd'] = macd_line
        result['macd_signal'] = signal_line
        result['macd_hist'] = histogram
        
        # MACD crossovers
        bullish_cross, bearish_cross = macd_crossover(macd_line, signal_line)
        result['macd_bullish_cross'] = bullish_cross
        result['macd_bearish_cross'] = bearish_cross
        
        # ATR
        result['atr'] = calculate_atr(
            df['high'], df['low'], df['close'],
            self._config.atr_period
        )
        
        # SMAs for trend filter
        result['sma_fast'] = calculate_sma(df['close'], self._config.trend_sma_fast)
        result['sma_slow'] = calculate_sma(df['close'], self._config.trend_sma_slow)
        
        self._indicators = result
        return result
    
    def get_latest_signals(
        self,
        df: Optional[pd.DataFrame] = None
    ) -> dict:
        """
        Get the most recent indicator values and signals.
        
        Args:
            df: DataFrame to analyze (uses cached if not provided).
        
        Returns:
            dict with latest indicator values and signals.
        """
        if df is not None:
            self.calculate(df)
        
        if self._indicators is None or self._indicators.empty:
            return {
                'rsi': None,
                'macd': None,
                'macd_signal': None,
                'atr': None,
                'sma_fast': None,
                'sma_slow': None,
                'close': None,
                'bullish_cross': False,
                'bearish_cross': False,
                'long_technical': False,
                'short_technical': False
            }
        
        # Get last two rows for signal detection
        latest = self._indicators.iloc[-1]
        
        rsi = latest['rsi']
        bullish_cross = bool(latest['macd_bullish_cross'])
        bearish_cross = bool(latest['macd_bearish_cross'])
        
        # Technical entry conditions (using t-1 data for t entry)
        long_technical = rsi < self._config.rsi_oversold and bullish_cross
        short_technical = rsi > self._config.rsi_overbought and bearish_cross
        
        return {
            'rsi': float(rsi) if pd.notna(rsi) else None,
            'macd': float(latest['macd']) if pd.notna(latest['macd']) else None,
            'macd_signal': float(latest['macd_signal']) if pd.notna(latest['macd_signal']) else None,
            'atr': float(latest['atr']) if pd.notna(latest['atr']) else None,
            'sma_fast': float(latest['sma_fast']) if pd.notna(latest.get('sma_fast')) else None,
            'sma_slow': float(latest['sma_slow']) if pd.notna(latest.get('sma_slow')) else None,
            'close': float(latest['close']) if pd.notna(latest.get('close')) else None,
            'bullish_cross': bullish_cross,
            'bearish_cross': bearish_cross,
            'long_technical': long_technical,
            'short_technical': short_technical
        }


def compute_indicators_for_df(
    df: pd.DataFrame,
    config: Optional[IndicatorConfig] = None
) -> pd.DataFrame:
    """
    Convenience function to compute all indicators for a DataFrame.
    
    Args:
        df: OHLCV DataFrame.
        config: Indicator configuration.
    
    Returns:
        DataFrame with indicator columns added.
    """
    calculator = TechnicalIndicators(config)
    return calculator.calculate(df)


def get_entry_signals(
    df: pd.DataFrame,
    config: Optional[IndicatorConfig] = None
) -> Tuple[bool, bool]:
    """
    Get entry signals from the latest bar data.
    
    Uses data through the last complete bar (t-1) for trading at t.
    
    Args:
        df: OHLCV DataFrame with at least 2 bars.
        config: Indicator configuration.
    
    Returns:
        Tuple of (long_signal, short_signal) booleans.
    """
    if len(df) < 2:
        return False, False
    
    cfg = config or get_config().indicators
    calculator = TechnicalIndicators(cfg)
    indicators = calculator.calculate(df)
    signals = calculator.get_latest_signals()
    
    return signals['long_technical'], signals['short_technical']


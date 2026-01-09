"""Market data handler for fetching and processing historical data."""
import pandas as pd
from typing import Optional, Dict, Any
from datetime import datetime, timedelta, timezone
from alpaca_client import AlpacaClient
from indicators import (
    calculate_rsi,
    calculate_macd,
    calculate_sma,
    calculate_ema,
    calculate_bollinger_bands,
    calculate_volume_sma,
)
import logging

logger = logging.getLogger(__name__)


class DataHandler:
    """Handles market data fetching and indicator calculations."""
    
    def __init__(self, alpaca_client: AlpacaClient, timeframe: str = "1Day"):
        """
        Initialize data handler.
        
        Args:
            alpaca_client: AlpacaClient instance
            timeframe: Timeframe for bars (e.g., "1Day", "1Hour")
        """
        self.alpaca_client = alpaca_client
        self.timeframe = timeframe
        self._cache: Dict[str, pd.DataFrame] = {}
    
    def get_historical_data(
        self,
        symbol: str,
        days: int = 200,
        use_cache: bool = True
    ) -> pd.DataFrame:
        """
        Get historical price data for a symbol.
        
        Args:
            symbol: Stock symbol
            days: Number of days of historical data
            use_cache: Whether to use cached data if available
            
        Returns:
            DataFrame with OHLCV data
        """
        cache_key = f"{symbol}_{days}"
        
        if use_cache and cache_key in self._cache:
            logger.debug(f"Using cached data for {symbol}")
            return self._cache[cache_key].copy()
        
        # Calculate start date (Alpaca requires timezone-aware datetimes)
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=days)
        
        # Fetch bars from Alpaca
        bars = self.alpaca_client.get_bars(
            symbol=symbol,
            timeframe=self.timeframe,
            start=start,
            end=end,
            limit=days * 2  # Request more than needed to account for non-trading days
        )
        
        if not bars:
            # Not all stocks are available on IEX feed - this is expected for basic accounts
            # Only log if debug level enabled to reduce noise
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(f"No bars returned for {symbol} (not on IEX feed)")
            return pd.DataFrame()
        
        # Convert to DataFrame
        df = pd.DataFrame(bars)
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df.set_index('timestamp', inplace=True)
        df.sort_index(inplace=True)
        
        # Cache the result
        if use_cache:
            self._cache[cache_key] = df.copy()
        
        logger.info(f"Fetched {len(df)} bars for {symbol}")
        return df
    
    def calculate_indicators(
        self,
        df: pd.DataFrame,
        strategy_type: str,
        params: Dict[str, Any]
    ) -> pd.DataFrame:
        """
        Calculate technical indicators based on strategy type.
        
        Args:
            df: DataFrame with OHLCV data
            strategy_type: Strategy type ("momentum" or "mean_reversion")
            params: Strategy parameters
            
        Returns:
            DataFrame with added indicator columns
        """
        if df.empty:
            return df
        
        df = df.copy()
        
        if strategy_type == "momentum":
            # Calculate momentum indicators
            rsi_period = params.get('rsi_period', 14)
            df['rsi'] = calculate_rsi(df['close'], period=rsi_period)
            
            macd_params = {
                'fast': params.get('macd_fast', 12),
                'slow': params.get('macd_slow', 26),
                'signal': params.get('macd_signal', 9),
            }
            macd_df = calculate_macd(df['close'], **macd_params)
            df = pd.concat([df, macd_df], axis=1)
            
            # Moving averages
            sma_short = params.get('sma_short', 50)
            sma_long = params.get('sma_long', 200)
            df[f'sma_{sma_short}'] = calculate_sma(df['close'], period=sma_short)
            df[f'sma_{sma_long}'] = calculate_sma(df['close'], period=sma_long)
            
            # Volume SMA
            df['volume_sma'] = calculate_volume_sma(df['volume'], period=20)
            
        elif strategy_type == "mean_reversion":
            # Calculate mean reversion indicators
            rsi_period = params.get('rsi_period', 14)
            df['rsi'] = calculate_rsi(df['close'], period=rsi_period)
            
            bb_period = params.get('bb_period', 20)
            bb_std = params.get('bb_std', 2)
            bb_df = calculate_bollinger_bands(df['close'], period=bb_period, std_dev=bb_std)
            df = pd.concat([df, bb_df], axis=1)
            
        else:
            logger.warning(f"Unknown strategy type: {strategy_type}")
        
        return df
    
    def get_latest_data(
        self,
        symbol: str,
        strategy_type: str,
        params: Dict[str, Any],
        days: int = 200
    ) -> Optional[pd.Series]:
        """
        Get latest data point with all indicators calculated.
        
        Args:
            symbol: Stock symbol
            strategy_type: Strategy type
            params: Strategy parameters
            days: Number of days of historical data to fetch
            
        Returns:
            Series with latest data point (None if unavailable)
        """
        df = self.get_historical_data(symbol, days=days)
        if df.empty:
            return None
        
        df = self.calculate_indicators(df, strategy_type, params)
        
        # Return latest row as Series
        if not df.empty:
            return df.iloc[-1]
        return None
    
    def clear_cache(self):
        """Clear the data cache."""
        self._cache.clear()
        logger.debug("Data cache cleared")


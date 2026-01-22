"""
Data provider module for historical market data.

Fetches daily OHLCV bars from Alpaca and manages local caching.
"""

import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional
import pandas as pd

from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame

from config import get_config, PathConfig
from alpaca_clients import get_data_client, get_data_feed
from utils import utc_now, years_ago, ensure_tz_aware, ensure_utc

logger = logging.getLogger("tradingbot.data_provider")


class DataProvider:
    """
    Provider for historical stock bar data with local caching.
    
    Features:
    - Fetches daily OHLCV bars from Alpaca
    - Caches data locally as parquet files
    - Handles symbol batching for efficient API usage
    - Supports incremental updates
    """
    
    def __init__(
        self,
        cache_dir: Optional[Path] = None,
        data_feed: Optional[str] = None
    ):
        """
        Initialize the data provider.
        
        Args:
            cache_dir: Directory for cached data files.
            data_feed: Data feed to use ('iex' or 'sip').
        """
        self._config = get_config()
        self._cache_dir = cache_dir or self._config.paths.bars_cache_dir
        self._data_feed = data_feed or get_data_feed()
        self._cache: Dict[str, pd.DataFrame] = {}
        
        # Ensure cache directory exists
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        
    def _cache_path(self, symbol: str) -> Path:
        """
        Get cache file path for a symbol.
        
        Args:
            symbol: Stock ticker symbol.
        
        Returns:
            Path: Path to cache file.
        """
        # Sanitize symbol for filename (handle BRK-B etc)
        safe_symbol = symbol.replace("-", "_").replace("/", "_")
        return self._cache_dir / f"{safe_symbol}_daily.parquet"
    
    def _load_cached(self, symbol: str) -> Optional[pd.DataFrame]:
        """
        Load cached data for a symbol.
        
        Args:
            symbol: Stock ticker symbol.
        
        Returns:
            DataFrame or None if not cached.
        """
        cache_path = self._cache_path(symbol)
        if cache_path.exists():
            try:
                df = pd.read_parquet(cache_path)
                df = ensure_tz_aware(df, "timestamp")
                return df
            except Exception as e:
                logger.warning(f"Failed to load cache for {symbol}: {e}")
        return None
    
    def _save_to_cache(self, symbol: str, df: pd.DataFrame) -> None:
        """
        Save data to cache file.
        
        Args:
            symbol: Stock ticker symbol.
            df: DataFrame with bar data.
        """
        if df.empty:
            return
            
        cache_path = self._cache_path(symbol)
        try:
            df.to_parquet(cache_path, index=False)
            logger.debug(f"Cached {len(df)} bars for {symbol}")
        except Exception as e:
            logger.warning(f"Failed to cache data for {symbol}: {e}")
    
    def fetch_bars(
        self,
        symbols: List[str],
        start: datetime,
        end: Optional[datetime] = None,
        timeframe: TimeFrame = TimeFrame.Day,
        use_cache: bool = True
    ) -> Dict[str, pd.DataFrame]:
        """
        Fetch historical bars for multiple symbols.
        
        Args:
            symbols: List of stock ticker symbols.
            start: Start date for data.
            end: End date for data (default: yesterday).
            timeframe: Bar timeframe (default: daily).
            use_cache: Whether to use cached data.
        
        Returns:
            Dict mapping symbol to DataFrame with columns:
            timestamp, open, high, low, close, volume, vwap, trade_count
        """
        if end is None:
            end = utc_now() - timedelta(days=1)
        
        # Ensure timezone-aware datetimes for comparison
        start = ensure_utc(start)
        end = ensure_utc(end)
        
        result: Dict[str, pd.DataFrame] = {}
        symbols_to_fetch: List[str] = []
        
        # Check cache first
        for symbol in symbols:
            if use_cache:
                cached = self._load_cached(symbol)
                if cached is not None and not cached.empty:
                    # Filter to requested date range
                    mask = (cached["timestamp"] >= start) & (cached["timestamp"] <= end)
                    filtered = cached[mask].copy()
                    
                    # Check if we need to fetch more recent data
                    if not filtered.empty:
                        latest_cached = filtered["timestamp"].max()
                        if latest_cached >= end - timedelta(days=3):  # Allow 3-day buffer
                            result[symbol] = filtered
                            self._cache[symbol] = cached  # Keep full cache in memory
                            continue
            
            symbols_to_fetch.append(symbol)
        
        # Fetch missing data from Alpaca
        if symbols_to_fetch:
            cached_count = len(symbols) - len(symbols_to_fetch)
            logger.info(f"Fetching bars for {len(symbols_to_fetch)} symbols from Alpaca ({cached_count} already cached)")
            fetched = self._fetch_from_alpaca(symbols_to_fetch, start, end, timeframe)
            
            # Merge with cache and save
            for symbol, df in fetched.items():
                if not df.empty:
                    # Merge with existing cache if present
                    existing = self._load_cached(symbol)
                    if existing is not None and not existing.empty:
                        combined = pd.concat([existing, df]).drop_duplicates(
                            subset=["timestamp"], keep="last"
                        ).sort_values("timestamp").reset_index(drop=True)
                    else:
                        combined = df.sort_values("timestamp").reset_index(drop=True)
                    
                    self._save_to_cache(symbol, combined)
                    self._cache[symbol] = combined
                    
                    # Filter to requested range for result (start/end already UTC-aware)
                    mask = (combined["timestamp"] >= start) & (combined["timestamp"] <= end)
                    result[symbol] = combined[mask].copy()
                else:
                    result[symbol] = pd.DataFrame()
        
        return result
    
    def _fetch_from_alpaca(
        self,
        symbols: List[str],
        start: datetime,
        end: datetime,
        timeframe: TimeFrame
    ) -> Dict[str, pd.DataFrame]:
        """
        Fetch bars directly from Alpaca API.
        
        Args:
            symbols: List of symbols to fetch.
            start: Start datetime.
            end: End datetime.
            timeframe: Bar timeframe.
        
        Returns:
            Dict mapping symbol to DataFrame.
        """
        result: Dict[str, pd.DataFrame] = {}
        client = get_data_client()
        
        # Batch symbols for efficiency (Alpaca allows multiple symbols per request)
        batch_size = 100  # Alpaca limit
        for i in range(0, len(symbols), batch_size):
            batch = symbols[i:i + batch_size]
            
            try:
                request = StockBarsRequest(
                    symbol_or_symbols=batch,
                    start=start,
                    end=end,
                    timeframe=timeframe,
                    feed=self._data_feed
                )
                
                bars = client.get_stock_bars(request)
                
                # Convert to DataFrames
                for symbol in batch:
                    if symbol in bars.data and bars.data[symbol]:
                        records = []
                        for bar in bars.data[symbol]:
                            records.append({
                                "timestamp": bar.timestamp,
                                "open": float(bar.open),
                                "high": float(bar.high),
                                "low": float(bar.low),
                                "close": float(bar.close),
                                "volume": int(bar.volume),
                                "vwap": float(bar.vwap) if bar.vwap else None,
                                "trade_count": int(bar.trade_count) if bar.trade_count else None
                            })
                        
                        df = pd.DataFrame(records)
                        df = ensure_tz_aware(df, "timestamp")
                        result[symbol] = df
                        logger.debug(f"Fetched {len(df)} bars for {symbol}")
                    else:
                        logger.warning(f"No data returned for {symbol}")
                        result[symbol] = pd.DataFrame()
                        
            except Exception as e:
                logger.warning(f"Batch fetch failed: {e}. Trying individual symbols...")
                # Fall back to fetching symbols one by one
                for symbol in batch:
                    try:
                        single_request = StockBarsRequest(
                            symbol_or_symbols=symbol,
                            start=start,
                            end=end,
                            timeframe=timeframe,
                            feed=self._data_feed
                        )
                        single_bars = client.get_stock_bars(single_request)
                        
                        if symbol in single_bars.data and single_bars.data[symbol]:
                            records = []
                            for bar in single_bars.data[symbol]:
                                records.append({
                                    "timestamp": bar.timestamp,
                                    "open": float(bar.open),
                                    "high": float(bar.high),
                                    "low": float(bar.low),
                                    "close": float(bar.close),
                                    "volume": int(bar.volume),
                                    "vwap": float(bar.vwap) if bar.vwap else None,
                                    "trade_count": int(bar.trade_count) if bar.trade_count else None
                                })
                            df = pd.DataFrame(records)
                            df = ensure_tz_aware(df, "timestamp")
                            result[symbol] = df
                            logger.debug(f"Fetched {len(df)} bars for {symbol} (individual)")
                        else:
                            result[symbol] = pd.DataFrame()
                    except Exception as e2:
                        logger.debug(f"Failed to fetch {symbol}: {e2}")
                        result[symbol] = pd.DataFrame()
        
        return result
    
    def get_latest_bars(
        self,
        symbols: List[str],
        lookback_days: int = 500
    ) -> Dict[str, pd.DataFrame]:
        """
        Get the most recent bars for symbols.
        
        Args:
            symbols: List of stock ticker symbols.
            lookback_days: Number of days of history to fetch.
        
        Returns:
            Dict mapping symbol to DataFrame.
        """
        end = utc_now()
        start = end - timedelta(days=lookback_days)
        return self.fetch_bars(symbols, start, end)
    
    def get_market_proxy_history(
        self,
        proxy: str = "SPY",
        years: int = 5
    ) -> pd.DataFrame:
        """
        Get historical data for the market proxy (SPY by default).
        
        Args:
            proxy: Market proxy symbol.
            years: Years of history to fetch.
        
        Returns:
            DataFrame with proxy bar data.
        """
        end = utc_now()
        start = years_ago(years, end)
        
        data = self.fetch_bars([proxy], start, end)
        return data.get(proxy, pd.DataFrame())
    
    def get_symbol_data(
        self,
        symbol: str,
        min_bars: int = 400
    ) -> Optional[pd.DataFrame]:
        """
        Get data for a single symbol with minimum bar requirement.
        
        Args:
            symbol: Stock ticker symbol.
            min_bars: Minimum number of bars required.
        
        Returns:
            DataFrame or None if insufficient data.
        """
        # Fetch enough history to satisfy min_bars
        lookback_days = int(min_bars * 1.5)  # Account for weekends/holidays
        data = self.get_latest_bars([symbol], lookback_days)
        
        df = data.get(symbol)
        if df is None or df.empty or len(df) < min_bars:
            logger.warning(f"Insufficient data for {symbol}: got {len(df) if df is not None else 0}, need {min_bars}")
            return None
        
        return df
    
    def clear_cache(self, symbol: Optional[str] = None) -> None:
        """
        Clear cached data.
        
        Args:
            symbol: Symbol to clear (None = clear all).
        """
        if symbol:
            cache_path = self._cache_path(symbol)
            if cache_path.exists():
                cache_path.unlink()
            self._cache.pop(symbol, None)
            logger.info(f"Cleared cache for {symbol}")
        else:
            for path in self._cache_dir.glob("*.parquet"):
                path.unlink()
            self._cache.clear()
            logger.info("Cleared all bar data cache")


# Module-level convenience functions
_provider: Optional[DataProvider] = None


def get_data_provider() -> DataProvider:
    """
    Get or create the global data provider.
    
    Returns:
        DataProvider: Global data provider instance.
    """
    global _provider
    if _provider is None:
        _provider = DataProvider()
    return _provider


def fetch_universe_bars(
    symbols: List[str],
    lookback_days: int = 600
) -> Dict[str, pd.DataFrame]:
    """
    Fetch bar data for universe symbols.
    
    Args:
        symbols: List of symbols.
        lookback_days: Days of history.
    
    Returns:
        Dict mapping symbol to DataFrame.
    """
    provider = get_data_provider()
    end = utc_now()
    start = end - timedelta(days=lookback_days)
    return provider.fetch_bars(symbols, start, end)


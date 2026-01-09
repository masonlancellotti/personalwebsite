"""Historical data download and caching."""

import asyncio
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd
from alpaca.data.requests import CryptoBarsRequest
from alpaca.data.timeframe import TimeFrame
from loguru import logger

from config import settings
from alpaca_clients import get_clients


def _parse_timeframe(timeframe_str: str) -> TimeFrame:
    """Parse timeframe string to TimeFrame enum."""
    timeframe_map = {
        "1Min": TimeFrame.Minute,
        "5Min": TimeFrame(5, TimeFrame.Minute),
        "15Min": TimeFrame(15, TimeFrame.Minute),
        "30Min": TimeFrame(30, TimeFrame.Minute),
        "1Hour": TimeFrame.Hour,
        "1Day": TimeFrame.Day,
    }
    if timeframe_str in timeframe_map:
        return timeframe_map[timeframe_str]
    # Try to parse as number + unit
    try:
        if timeframe_str.endswith("Min"):
            minutes = int(timeframe_str[:-3])
            return TimeFrame(minutes, TimeFrame.Minute)
        elif timeframe_str.endswith("Hour"):
            hours = int(timeframe_str[:-4])
            return TimeFrame(hours, TimeFrame.Hour)
        elif timeframe_str.endswith("Day"):
            days = int(timeframe_str[:-3])
            return TimeFrame(days, TimeFrame.Day)
    except ValueError:
        pass
    raise ValueError(f"Unsupported timeframe: {timeframe_str}")


def _symbol_to_filename(symbol: str) -> str:
    """Convert symbol to safe filename."""
    return symbol.replace("/", "_") + ".parquet"


def download_bars(
    symbols: list[str],
    timeframe: str = "1Min",
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    lookback_days: Optional[int] = None,
    batch_size: int = 10,
    delay_ms: int = 100,
) -> dict[str, pd.DataFrame]:
    """
    Download historical bars for symbols.

    Args:
        symbols: List of symbols to download
        timeframe: Timeframe string (e.g., "1Min", "5Min", "1Hour")
        start_date: Start date (if None, uses lookback_days from end_date)
        end_date: End date (default: now)
        lookback_days: Days to look back if start_date not provided
        batch_size: Number of symbols per batch
        delay_ms: Delay between batches (milliseconds)

    Returns:
        Dictionary mapping symbol to DataFrame
    """
    clients = get_clients()
    data_client = clients.data_client

    if end_date is None:
        end_date = datetime.utcnow()

    if start_date is None:
        if lookback_days is None:
            lookback_days = settings.HIST_LOOKBACK_DAYS
        start_date = end_date - timedelta(days=lookback_days)

    timeframe_obj = _parse_timeframe(timeframe)

    logger.info(
        f"Downloading bars for {len(symbols)} symbols: "
        f"timeframe={timeframe}, start={start_date.date()}, end={end_date.date()}"
    )

    results: dict[str, pd.DataFrame] = {}
    failed: list[str] = []

    # Download in batches to respect rate limits
    for i in range(0, len(symbols), batch_size):
        batch = symbols[i : i + batch_size]
        logger.info(f"Downloading batch {i//batch_size + 1}/{(len(symbols) + batch_size - 1)//batch_size}: {batch}")

        for symbol in batch:
            try:
                request = CryptoBarsRequest(
                    symbol_or_symbols=symbol,
                    timeframe=timeframe_obj,
                    start=start_date,
                    end=end_date,
                )

                bars = data_client.get_crypto_bars(request_params=request)

                # Convert to DataFrame
                df = bars.df

                if df.empty:
                    logger.warning(f"No data for {symbol}")
                    failed.append(symbol)
                    continue

                # Reset index if MultiIndex (symbol in index)
                if isinstance(df.index, pd.MultiIndex):
                    df = df.reset_index(level=0, drop=True)

                # Ensure timestamp is the index
                if not isinstance(df.index, pd.DatetimeIndex):
                    if "timestamp" in df.columns:
                        df["timestamp"] = pd.to_datetime(df["timestamp"])
                        df = df.set_index("timestamp")

                results[symbol] = df
                logger.debug(f"Downloaded {len(df)} bars for {symbol}")

            except Exception as e:
                logger.error(f"Error downloading {symbol}: {e}")
                failed.append(symbol)

        # Rate limiting delay between batches
        if i + batch_size < len(symbols):
            time.sleep(delay_ms / 1000.0)

    if failed:
        logger.warning(f"Failed to download {len(failed)} symbols: {failed}")

    logger.info(f"Successfully downloaded {len(results)}/{len(symbols)} symbols")
    return results


def fetch_latest_bar(symbol: str, timeframe: str = "1Min") -> Optional[pd.Series]:
    """
    Fetch the latest bar for a symbol.
    
    Args:
        symbol: Symbol to fetch
        timeframe: Timeframe string (e.g., "1Min")
        
    Returns:
        Latest bar as Series, or None if no data
    """
    clients = get_clients()
    data_client = clients.data_client
    
    timeframe_obj = _parse_timeframe(timeframe)
    
    # Fetch last 2 bars to ensure we get the latest complete one
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(minutes=10)  # Small window
    
    try:
        request = CryptoBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=timeframe_obj,
            start=start_date,
            end=end_date,
        )
        
        bars = data_client.get_crypto_bars(request_params=request)
        df = bars.df
        
        if df.empty:
            return None
            
        # Reset index if MultiIndex
        if isinstance(df.index, pd.MultiIndex):
            df = df.reset_index(level=0, drop=True)
            
        # Get the latest bar
        if len(df) > 0:
            latest_bar = df.iloc[-1]
            return latest_bar
            
    except Exception as e:
        logger.error(f"Error fetching latest bar for {symbol}: {e}")
        
    return None


def cache_bars(data: dict[str, pd.DataFrame], cache_dir: Optional[Path] = None) -> dict[str, Path]:
    """
    Cache bars to parquet files.

    Args:
        data: Dictionary mapping symbol to DataFrame
        cache_dir: Cache directory (default: settings.CACHE_DIR)

    Returns:
        Dictionary mapping symbol to cache file path
    """
    if cache_dir is None:
        cache_dir = settings.get_cache_dir() / "bars"
    else:
        cache_dir = Path(cache_dir)

    cache_dir.mkdir(parents=True, exist_ok=True)

    cached_files: dict[str, Path] = {}

    for symbol, df in data.items():
        filename = _symbol_to_filename(symbol)
        filepath = cache_dir / filename

        try:
            df.to_parquet(filepath, compression="snappy")
            cached_files[symbol] = filepath
            logger.debug(f"Cached {symbol} to {filepath}")
        except Exception as e:
            logger.error(f"Error caching {symbol} to {filepath}: {e}")

    logger.info(f"Cached {len(cached_files)} symbols to {cache_dir}")
    return cached_files


def load_cached_bars(
    symbol: str,
    cache_dir: Optional[Path] = None,
    resample: Optional[str] = None,
) -> pd.DataFrame:
    """
    Load cached bars for a symbol.

    Args:
        symbol: Symbol to load
        cache_dir: Cache directory (default: settings.CACHE_DIR/bars)
        resample: Optional resample rule (e.g., "5T" for 5 minutes)

    Returns:
        DataFrame with bars

    Raises:
        FileNotFoundError: If cache file doesn't exist
    """
    if cache_dir is None:
        cache_dir = settings.get_cache_dir() / "bars"
    else:
        cache_dir = Path(cache_dir)

    filename = _symbol_to_filename(symbol)
    filepath = cache_dir / filename

    if not filepath.exists():
        raise FileNotFoundError(f"Cache file not found: {filepath}")

    df = pd.read_parquet(filepath)

    # Ensure timestamp index
    if not isinstance(df.index, pd.DatetimeIndex):
        if "timestamp" in df.columns:
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            df = df.set_index("timestamp")
        else:
            raise ValueError(f"DataFrame for {symbol} has no timestamp index or column")

    # Resample if requested
    if resample:
        df = df.resample(resample).agg({
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
            "trade_count": "sum",
            "vwap": "mean",
        }).dropna()

    return df


def load_all_cached_bars(
    symbols: list[str],
    cache_dir: Optional[Path] = None,
    resample: Optional[str] = None,
) -> dict[str, pd.DataFrame]:
    """
    Load cached bars for multiple symbols.

    Args:
        symbols: List of symbols to load
        cache_dir: Cache directory
        resample: Optional resample rule

    Returns:
        Dictionary mapping symbol to DataFrame
    """
    results: dict[str, pd.DataFrame] = {}
    for symbol in symbols:
        try:
            results[symbol] = load_cached_bars(symbol, cache_dir=cache_dir, resample=resample)
        except FileNotFoundError:
            logger.warning(f"Cache not found for {symbol}, skipping")
        except Exception as e:
            logger.error(f"Error loading {symbol}: {e}")

    return results


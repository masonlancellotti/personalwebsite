"""Universe discovery, validation, and caching."""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from alpaca.trading.requests import GetAssetsRequest
from alpaca.trading.enums import AssetClass
from loguru import logger

from config import settings
from alpaca_clients import get_clients


def fetch_crypto_universe() -> list[str]:
    """
    Fetch all tradable crypto assets from Alpaca.

    Returns:
        List of symbol strings (e.g., ["BTC/USD", "ETH/USD"])
    """
    clients = get_clients()
    trading_client = clients.trading_client

    logger.info("Fetching crypto assets from Alpaca...")

    try:
        # Fetch all crypto assets
        assets = trading_client.get_all_assets(
            filter=GetAssetsRequest(asset_class=AssetClass.CRYPTO)
        )

        # Filter to active and tradable
        tradable_symbols = [
            asset.symbol
            for asset in assets
            if asset.tradable and asset.status == "active"
        ]

        logger.info(f"Found {len(tradable_symbols)} tradable crypto assets")
        return sorted(tradable_symbols)

    except Exception as e:
        logger.error(f"Error fetching crypto universe: {e}")
        raise


def filter_universe(
    symbols: list[str],
    top_n: Optional[int] = None,
    min_avg_dollar_vol: float = 0.0,
    quote_filter: Optional[list[str]] = None,
    exclude_symbols: Optional[list[str]] = None,
) -> list[str]:
    """
    Filter universe based on criteria.

    Args:
        symbols: List of symbols to filter
        top_n: Top N symbols by volume (None for all)
        min_avg_dollar_vol: Minimum average dollar volume (not yet implemented)
        quote_filter: List of quote currencies to include (e.g., ["USD", "USDC"])
        exclude_symbols: List of symbols to exclude

    Returns:
        Filtered list of symbols
    """
    filtered = symbols.copy()

    # Apply quote filter
    if quote_filter:
        quote_filter_upper = [q.upper() for q in quote_filter]
        filtered = [
            s for s in filtered
            if any(s.endswith(f"/{q}") for q in quote_filter_upper)
        ]
        logger.info(f"After quote filter {quote_filter}: {len(filtered)} symbols")

    # Apply exclude symbols
    if exclude_symbols:
        exclude_set = {s.strip().upper() for s in exclude_symbols}
        filtered = [s for s in filtered if s.upper() not in exclude_set]
        logger.info(f"After excluding {exclude_symbols}: {len(filtered)} symbols")

    # Apply top_n filter (by volume - simplified: just take first N after sorting)
    # TODO: Implement proper volume-based filtering when historical data is available
    if top_n is not None and top_n > 0:
        filtered = filtered[:top_n]
        logger.info(f"After top_n={top_n} filter: {len(filtered)} symbols")

    # TODO: Apply min_avg_dollar_vol filter when historical data is available

    return filtered


def cache_universe(symbols: list[str], cache_file: Optional[Path] = None) -> Path:
    """
    Cache universe to JSON file.

    Args:
        symbols: List of symbols to cache
        cache_file: Optional path to cache file (default: cache_dir/universe.json)

    Returns:
        Path to cache file
    """
    if cache_file is None:
        cache_file = settings.get_cache_dir() / "universe.json"

    cache_file.parent.mkdir(parents=True, exist_ok=True)

    universe_data = {
        "timestamp": datetime.utcnow().isoformat(),
        "symbols": symbols,
        "count": len(symbols),
    }

    with open(cache_file, "w") as f:
        json.dump(universe_data, f, indent=2)

    logger.info(f"Cached {len(symbols)} symbols to {cache_file}")
    return cache_file


def load_universe(cache_file: Optional[Path] = None) -> list[str]:
    """
    Load cached universe from JSON file.

    Args:
        cache_file: Optional path to cache file (default: cache_dir/universe.json)

    Returns:
        List of symbols

    Raises:
        FileNotFoundError: If cache file doesn't exist
    """
    if cache_file is None:
        cache_file = settings.get_cache_dir() / "universe.json"

    if not cache_file.exists():
        raise FileNotFoundError(
            f"Universe cache not found at {cache_file}. Run 'build-universe' first."
        )

    with open(cache_file, "r") as f:
        universe_data = json.load(f)

    symbols = universe_data.get("symbols", [])
    timestamp = universe_data.get("timestamp", "unknown")
    logger.info(f"Loaded {len(symbols)} symbols from cache (timestamp: {timestamp})")
    return symbols


def build_universe(
    top_n: Optional[int] = None,
    min_avg_dollar_vol: float = 0.0,
    quote_filter: Optional[list[str]] = None,
    exclude_symbols: Optional[list[str]] = None,
    refresh: bool = True,
) -> list[str]:
    """
    Build and cache the crypto universe.

    Args:
        top_n: Top N symbols (None for all)
        min_avg_dollar_vol: Minimum average dollar volume
        quote_filter: Quote currency filter
        exclude_symbols: Symbols to exclude
        refresh: Force refresh from API (default True)

    Returns:
        List of symbols
    """
    # Fetch from API
    all_symbols = fetch_crypto_universe()

    # Apply filters
    filtered_symbols = filter_universe(
        all_symbols,
        top_n=top_n,
        min_avg_dollar_vol=min_avg_dollar_vol,
        quote_filter=quote_filter,
        exclude_symbols=exclude_symbols,
    )

    # Cache
    cache_universe(filtered_symbols)

    return filtered_symbols


def validate_symbols(symbols: list[str], universe: Optional[list[str]] = None) -> tuple[list[str], list[str]]:
    """
    Validate that symbols exist in the universe.

    Args:
        symbols: List of symbols to validate
        universe: Optional universe list (will load from cache if not provided)

    Returns:
        Tuple of (valid_symbols, invalid_symbols)
    """
    if universe is None:
        try:
            universe = load_universe()
        except FileNotFoundError:
            # Build universe if cache doesn't exist
            logger.warning("Universe cache not found, fetching from API...")
            universe = fetch_crypto_universe()

    universe_set = {s.upper() for s in universe}
    valid = []
    invalid = []

    for symbol in symbols:
        if symbol.upper() in universe_set:
            valid.append(symbol)
        else:
            invalid.append(symbol)

    return valid, invalid


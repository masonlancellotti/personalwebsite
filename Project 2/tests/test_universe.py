"""Tests for universe discovery."""

import json
from pathlib import Path

import pytest

from universe import (
    filter_universe,
    cache_universe,
    load_universe,
    validate_symbols,
)


def test_filter_universe():
    """Test universe filtering."""
    symbols = ["BTC/USD", "ETH/USD", "SOL/USD", "USDT/USD", "USDC/USD"]

    # Test quote filter
    filtered = filter_universe(symbols, quote_filter=["USD"])
    assert len(filtered) == len(symbols)  # All end with /USD

    # Test exclude
    filtered = filter_universe(symbols, exclude_symbols=["USDT/USD", "USDC/USD"])
    assert len(filtered) == 3
    assert "USDT/USD" not in filtered
    assert "USDC/USD" not in filtered

    # Test top_n
    filtered = filter_universe(symbols, top_n=2)
    assert len(filtered) == 2


def test_cache_and_load_universe(tmp_path):
    """Test caching and loading universe."""
    symbols = ["BTC/USD", "ETH/USD", "SOL/USD"]
    cache_file = tmp_path / "universe.json"

    # Cache
    cache_universe(symbols, cache_file=cache_file)

    # Load
    loaded = load_universe(cache_file=cache_file)
    assert loaded == symbols


def test_validate_symbols():
    """Test symbol validation."""
    universe = ["BTC/USD", "ETH/USD", "SOL/USD"]
    symbols_to_validate = ["BTC/USD", "ETH/USD", "INVALID/USD"]

    valid, invalid = validate_symbols(symbols_to_validate, universe=universe)

    assert len(valid) == 2
    assert "BTC/USD" in valid
    assert "ETH/USD" in valid
    assert len(invalid) == 1
    assert "INVALID/USD" in invalid









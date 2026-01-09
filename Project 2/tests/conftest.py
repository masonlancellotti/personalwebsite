"""Pytest configuration and fixtures."""

import pytest


@pytest.fixture
def sample_symbols():
    """Sample symbols for testing."""
    return ["BTC/USD", "ETH/USD", "SOL/USD"]


@pytest.fixture
def sample_bar():
    """Sample bar data for testing."""
    import pandas as pd
    return pd.Series({
        "open": 50000.0,
        "high": 51000.0,
        "low": 49000.0,
        "close": 50500.0,
        "volume": 100.0,
        "trade_count": 1000,
        "vwap": 50000.0,
    })









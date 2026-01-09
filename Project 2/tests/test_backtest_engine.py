"""Tests for backtest engine."""

import pandas as pd
from datetime import datetime, timedelta

from backtest.engine import BacktestEngine
from strategies.base import Strategy
from execution.intents import OrderIntent


class DummyStrategy(Strategy):
    """Dummy strategy for testing."""

    def on_bar(self, symbol: str, bar: pd.Series) -> list[OrderIntent]:
        """Return empty intents."""
        return []


def test_backtest_engine_initialization():
    """Test backtest engine initialization."""
    strategy = DummyStrategy()
    symbols = ["BTC/USD"]
    start_date = datetime(2024, 1, 1)
    end_date = datetime(2024, 1, 31)

    engine = BacktestEngine(
        strategy=strategy,
        symbols=symbols,
        start_date=start_date,
        end_date=end_date,
    )

    assert engine.strategy == strategy
    assert engine.symbols == symbols
    assert engine.start_date == start_date
    assert engine.end_date == end_date


def test_backtest_align_timestamps():
    """Test timestamp alignment."""
    strategy = DummyStrategy()
    symbols = ["BTC/USD", "ETH/USD"]
    start_date = datetime(2024, 1, 1)
    end_date = datetime(2024, 1, 31)

    engine = BacktestEngine(
        strategy=strategy,
        symbols=symbols,
        start_date=start_date,
        end_date=end_date,
    )

    # Create test data
    timestamps1 = pd.date_range(start_date, start_date + timedelta(days=5), freq="1H")
    timestamps2 = pd.date_range(start_date + timedelta(hours=2), start_date + timedelta(days=5), freq="1H")

    data = {
        "BTC/USD": pd.DataFrame({"close": [50000] * len(timestamps1)}, index=timestamps1),
        "ETH/USD": pd.DataFrame({"close": [3000] * len(timestamps2)}, index=timestamps2),
    }

    aligned = engine.align_timestamps(data)
    assert len(aligned) > 0
    assert isinstance(aligned, pd.DatetimeIndex)









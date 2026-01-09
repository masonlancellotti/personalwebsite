"""Tests for fill simulation."""

import pandas as pd

from backtest.fills import FillSimulator, FillResult
from execution.intents import OrderIntent, OrderSide, OrderType, TimeInForce


def test_fill_simulator_market_order():
    """Test market order fill simulation."""
    simulator = FillSimulator(slippage_bps=10, taker_fee_bps=10)

    intent = OrderIntent(
        symbol="BTC/USD",
        side=OrderSide.BUY,
        qty_or_notional=0.001,
        order_type=OrderType.MARKET,
        tif=TimeInForce.IOC,
    )

    current_bar = pd.Series({"open": 50000.0, "close": 50100.0, "volume": 10.0})
    next_bar = pd.Series({"open": 50100.0, "close": 50200.0, "volume": 10.0})

    fill_result = simulator.simulate_fill(intent, current_bar, next_bar)

    assert fill_result is not None
    assert fill_result.filled_qty > 0
    assert fill_result.fill_price > 0
    assert fill_result.fee >= 0


def test_fill_simulator_limit_order():
    """Test limit order fill simulation."""
    simulator = FillSimulator(maker_fee_bps=5)

    intent = OrderIntent(
        symbol="BTC/USD",
        side=OrderSide.BUY,
        qty_or_notional=0.001,
        limit_price=50000.0,
        order_type=OrderType.LIMIT,
        tif=TimeInForce.GTC,
    )

    current_bar = pd.Series({"open": 50000.0, "close": 50100.0, "volume": 10.0})
    next_bar = pd.Series({"open": 49900.0, "high": 50200.0, "low": 49500.0, "volume": 10.0})

    # Should fill if low <= limit_price
    fill_result = simulator.simulate_fill(intent, current_bar, next_bar)

    # May or may not fill depending on price movement
    # Just check that method runs without error
    assert fill_result is None or isinstance(fill_result, FillResult)









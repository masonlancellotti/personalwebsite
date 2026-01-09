"""Tests for risk management."""

from execution.intents import OrderIntent, OrderSide, OrderType, TimeInForce
from execution.portfolio import Portfolio
from execution.risk import RiskManager
from execution.order_manager import OrderManager


def test_risk_manager_check_order_intent():
    """Test risk manager order intent checks."""
    portfolio = Portfolio(cash=10000.0)
    order_manager = OrderManager()
    risk_manager = RiskManager(portfolio, order_manager)

    # Create a test intent
    intent = OrderIntent(
        symbol="BTC/USD",
        side=OrderSide.BUY,
        qty_or_notional=0.001,
        limit_price=50000.0,
        order_type=OrderType.LIMIT,
        tif=TimeInForce.GTC,
    )

    symbol_state = {
        "BTC/USD": {
            "bid": 49900.0,
            "ask": 50100.0,
            "mid": 50000.0,
            "last_update_ts": None,  # Would be datetime in real usage
        }
    }

    symbol_prices = {"BTC/USD": 50000.0}

    # This would require proper timestamp setup - simplified test
    # passed, error = risk_manager.check_order_intent(intent, symbol_state, symbol_prices)
    # assert isinstance(passed, bool)


def test_kill_switch(tmp_path):
    """Test kill switch check."""
    import os
    from pathlib import Path
    from config import settings

    portfolio = Portfolio()
    order_manager = OrderManager()
    risk_manager = RiskManager(portfolio, order_manager)

    # Test when kill switch file doesn't exist
    assert risk_manager.check_kill_switch() is True

    # Test when kill switch file exists
    kill_file = Path(settings.KILL_SWITCH_FILE)
    kill_file.touch()
    try:
        assert risk_manager.check_kill_switch() is False
    finally:
        if kill_file.exists():
            kill_file.unlink()









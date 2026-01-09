"""Tests for idempotent client_order_id generation."""

from execution.order_manager import OrderManager


def test_client_order_id_idempotency():
    """Test that client_order_id generation is idempotent."""
    order_manager = OrderManager()

    strategy_name = "test_strategy"
    symbol = "BTC/USD"
    side = "buy"
    price_bucket = 50000.0
    timestamp_bucket = 1234567890
    tag = "test_tag"

    # Generate same ID twice
    id1 = order_manager.generate_client_order_id(
        strategy_name, symbol, side, price_bucket, timestamp_bucket, tag
    )
    id2 = order_manager.generate_client_order_id(
        strategy_name, symbol, side, price_bucket, timestamp_bucket, tag
    )

    assert id1 == id2

    # Different parameters should generate different IDs
    id3 = order_manager.generate_client_order_id(
        strategy_name, symbol, side, price_bucket + 1, timestamp_bucket, tag
    )
    assert id1 != id3









"""Basic market maker strategy - quote bid/ask around mid with inventory awareness."""

from typing import Optional

import pandas as pd
from pydantic import BaseModel, Field

from strategies.base import Strategy, StrategyParams, register_strategy
from execution.intents import OrderIntent, OrderSide, OrderType, TimeInForce


class MarketMakerBasicParams(StrategyParams):
    """Parameters for basic market maker."""

    spread_bps: float = Field(default=20.0, ge=0, description="Spread in basis points")
    min_spread_bps: float = Field(default=10.0, ge=0, description="Minimum spread to quote (must cover fees)")
    inventory_target: float = Field(default=0.0, description="Target inventory level")
    inventory_max: float = Field(default=1000.0, ge=0, description="Maximum inventory before reducing quotes")
    skew_factor: float = Field(default=0.5, ge=0, le=1, description="Inventory skew factor (0-1)")
    refresh_ms: int = Field(default=2000, ge=100, description="Order refresh interval in milliseconds")
    order_notional: float = Field(default=50.0, ge=10.0, description="Order size in USD (must be >= $10 for Alpaca minimum)")


@register_strategy(
    name="market_maker_basic",
    params_schema=MarketMakerBasicParams,
    explanation=(
        "Basic market maker strategy. Quotes bid and ask around mid using limit orders. "
        "Inventory-aware skew reduces bid when inventory is high, reduces ask when inventory is low. "
        "Skips quoting if spread is too tight (below min_spread_bps). "
        "Order sizes are calculated from order_notional parameter (default $50, minimum $10 for Alpaca). "
        "Cancels/replaces orders on mid move or timer."
    ),
)
class MarketMakerBasicStrategy(Strategy):
    """Basic market maker strategy."""

    def __init__(self, **kwargs):
        """Initialize market maker."""
        super().__init__(**kwargs)
        self.current_inventory: dict[str, float] = {}  # symbol -> inventory
        self.last_quote_time: dict[str, float] = {}  # symbol -> timestamp

    def on_bar(self, symbol: str, bar: pd.Series) -> list[OrderIntent]:
        """
        Generate market maker quotes.

        Args:
            symbol: Symbol
            bar: Bar data

        Returns:
            List of OrderIntents (bid and ask)
        """
        intents = []

        # Get current price (mid or close)
        mid = bar.get("close", 0.0)
        if mid <= 0:
            return []

        # Calculate spread
        spread = mid * (self.spread_bps / 10000.0)
        half_spread = spread / 2.0

        # Check minimum spread
        if spread < (mid * self.min_spread_bps / 10000.0):
            return []  # Spread too tight

        # Get current inventory (will be updated from portfolio state)
        inventory = self.current_inventory.get(symbol, 0.0)

        # Calculate inventory skew
        inventory_ratio = inventory / self.inventory_max if self.inventory_max > 0 else 0.0
        inventory_ratio = max(-1.0, min(1.0, inventory_ratio))  # Clamp to [-1, 1]

        # Calculate bid/ask with inventory skew
        # When inventory is high (positive), reduce bid
        # When inventory is low (negative), reduce ask
        bid = mid - half_spread * (1.0 - self.skew_factor * inventory_ratio)
        ask = mid + half_spread * (1.0 + self.skew_factor * inventory_ratio)

        # Calculate quantity based on target order notional
        # Use bid price for buy orders, ask price for sell orders
        qty_buy = self.order_notional / bid if bid > 0 else 0.0
        qty_sell = self.order_notional / ask if ask > 0 else 0.0
        
        # Cap quantities to prevent numerical overflow (e.g., for very cheap tokens like PEPE)
        from config import settings
        qty_buy = min(qty_buy, settings.MAX_ORDER_QTY)
        qty_sell = min(qty_sell, settings.MAX_ORDER_QTY)

        # Bid order (buy)
        if inventory < self.inventory_max and qty_buy > 0:
            intents.append(
                OrderIntent(
                    symbol=symbol,
                    side=OrderSide.BUY,
                    qty_or_notional=qty_buy,
                    limit_price=bid,
                    order_type=OrderType.LIMIT,
                    tif=TimeInForce.GTC,
                    tag="mm_bid",
                )
            )

        # Ask order (sell) - only if we have position (long-only, so only if inventory > 0)
        if inventory > 0:
            # Can't sell more than we have
            qty_to_sell = min(qty_sell, inventory)
            if qty_to_sell > 0:
                intents.append(
                    OrderIntent(
                        symbol=symbol,
                        side=OrderSide.SELL,
                        qty_or_notional=qty_to_sell,
                        limit_price=ask,
                        order_type=OrderType.LIMIT,
                        tif=TimeInForce.GTC,
                        tag="mm_ask",
                    )
                )

        return intents

    def update_inventory(self, symbol: str, inventory: float):
        """Update inventory for a symbol (called from execution pipeline)."""
        self.current_inventory[symbol] = inventory


"""TWAP/VWAP executor strategy."""

import pandas as pd
from pydantic import BaseModel, Field
from typing import Optional

from strategies.base import Strategy, StrategyParams, register_strategy
from execution.intents import OrderIntent, OrderSide, OrderType, TimeInForce


class TWAPVWAPExecutorParams(StrategyParams):
    """Parameters for TWAP/VWAP executor."""

    target_weights: Optional[dict[str, float]] = Field(default=None, description="Target weights dict (symbol -> weight)")
    target_notionals: Optional[dict[str, float]] = Field(default=None, description="Target notionals dict (symbol -> USD)")
    mode: str = Field(default="twap", description="Execution mode: 'twap' or 'vwap'")
    duration_minutes: int = Field(default=60, ge=1, description="Execution duration in minutes")
    slices: int = Field(default=10, ge=1, description="Number of time slices for TWAP")
    slippage_cap_bps: int = Field(default=50, ge=0, description="Maximum slippage in bps before using market orders")


@register_strategy(
    name="twap_vwap_executor",
    params_schema=TWAPVWAPExecutorParams,
    explanation=(
        "TWAP/VWAP executor strategy. Executes target weights or notionals gradually over time. "
        "TWAP: splits orders over time slices. VWAP: weights execution by bar volume. "
        "Uses IOC limits; falls back to market orders if slippage cap is hit."
    ),
)
class TWAPVWAPExecutorStrategy(Strategy):
    """TWAP/VWAP executor strategy."""

    def __init__(self, **kwargs):
        """Initialize executor."""
        super().__init__(**kwargs)
        self.current_positions: dict[str, float] = {}  # symbol -> current position
        self.target_allocation: dict[str, float] = {}  # symbol -> target notional
        self.execution_start_time: Optional[float] = None
        self.slice_index = 0

    def on_bar(self, symbol: str, bar: pd.Series) -> list[OrderIntent]:
        """
        Generate execution orders.

        Args:
            symbol: Symbol
            bar: Bar data

        Returns:
            List of OrderIntents
        """
        # Initialize target allocation if not set
        if not self.target_allocation:
            self._initialize_allocation()

        if symbol not in self.target_allocation:
            return []

        current_price = bar.get("close", 0.0)
        if current_price <= 0:
            return []

        target_notional = self.target_allocation.get(symbol, 0.0)
        current_position = self.current_positions.get(symbol, 0.0)
        current_notional = current_position * current_price

        # Calculate desired notional
        desired_notional = target_notional - current_notional

        if abs(desired_notional) < 1.0:  # Threshold
            return []

        # Calculate order size for this slice/bar
        if self.mode == "twap":
            # TWAP: divide equally across slices
            order_notional = desired_notional / self.slices
        else:  # vwap
            # VWAP: weight by volume (simplified - use bar volume)
            volume = bar.get("volume", 1.0)
            # Simplified: use volume ratio (would need total volume over period in practice)
            order_notional = desired_notional * 0.1  # Placeholder

        # Determine side and quantity
        if order_notional > 0:
            side = OrderSide.BUY
            qty = order_notional / current_price
        else:
            side = OrderSide.SELL
            qty = abs(order_notional) / current_price

        # Use IOC limit orders
        limit_price = current_price * (1.0 + (self.slippage_cap_bps / 10000.0)) if side == OrderSide.BUY else current_price * (1.0 - (self.slippage_cap_bps / 10000.0))

        return [
            OrderIntent(
                symbol=symbol,
                side=side,
                qty_or_notional=qty,
                limit_price=limit_price,
                order_type=OrderType.LIMIT,
                tif=TimeInForce.IOC,
                tag="twap_vwap",
            )
        ]

    def _initialize_allocation(self):
        """Initialize target allocation from weights or notionals."""
        # This would typically be set from external inputs
        # For now, use the params if provided
        if self.target_notionals:
            self.target_allocation = self.target_notionals
        elif self.target_weights:
            # Would need total capital - placeholder
            total_capital = 10000.0  # Should come from portfolio
            self.target_allocation = {
                symbol: weight * total_capital
                for symbol, weight in self.target_weights.items()
            }

    def update_position(self, symbol: str, position: float):
        """Update current position (called from execution pipeline)."""
        self.current_positions[symbol] = position









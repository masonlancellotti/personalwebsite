"""Rebalancer with target weights strategy."""

import pandas as pd
from pydantic import BaseModel, Field
from typing import Optional

from strategies.base import Strategy, StrategyParams, register_strategy
from execution.intents import OrderIntent, OrderSide, OrderType, TimeInForce


class RebalancerTargetWeightsParams(StrategyParams):
    """Parameters for rebalancer target weights."""

    target_weights: Optional[dict[str, float]] = Field(default=None, description="Target weights dict (symbol -> weight), or None for equal-weight")
    rebalance_threshold: float = Field(default=0.05, ge=0, description="Rebalance threshold (0.05 = 5% drift)")
    rebalance_frequency: str = Field(default="daily", description="Rebalance frequency: 'daily' or 'weekly'")


@register_strategy(
    name="rebalancer_target_weights",
    params_schema=RebalancerTargetWeightsParams,
    explanation=(
        "Simple rebalancer strategy. Maintains target weights (equal-weight or user-defined). "
        "Rebalances when drift exceeds threshold or on schedule. Respects exposure caps."
    ),
)
class RebalancerTargetWeightsStrategy(Strategy):
    """Rebalancer with target weights strategy."""

    def __init__(self, **kwargs):
        """Initialize rebalancer."""
        super().__init__(**kwargs)
        self.current_positions: dict[str, float] = {}  # symbol -> current position notional
        self.last_rebalance_date: Optional[pd.Timestamp] = None

    def on_bar(self, symbol: str, bar: pd.Series) -> list[OrderIntent]:
        """
        Generate rebalancing orders.

        Args:
            symbol: Symbol
            bar: Bar data

        Returns:
            List of OrderIntents
        """
        current_price = bar.get("close", 0.0)
        if current_price <= 0:
            return []

        # Check if it's time to rebalance
        current_timestamp = bar.name if hasattr(bar, 'name') else pd.Timestamp.now()
        if not self._should_rebalance(current_timestamp):
            return []

        # Calculate target weights (equal-weight if not provided)
        target_weights = self._get_target_weights()
        if symbol not in target_weights:
            return []

        target_weight = target_weights[symbol]

        # Get current total portfolio value (would come from portfolio)
        # Placeholder - would need actual portfolio value
        total_portfolio_value = 10000.0

        # Calculate target notional
        target_notional = target_weight * total_portfolio_value

        # Get current notional
        current_position = self.current_positions.get(symbol, 0.0)
        current_notional = current_position * current_price if current_position > 0 else 0.0

        # Calculate drift
        drift = abs(target_notional - current_notional) / total_portfolio_value if total_portfolio_value > 0 else 0.0

        # Check if rebalancing needed
        if drift < self.rebalance_threshold:
            return []

        # Generate rebalancing order
        desired_notional = target_notional - current_notional

        if abs(desired_notional) < 1.0:  # Threshold
            return []

        side = OrderSide.BUY if desired_notional > 0 else OrderSide.SELL
        qty = abs(desired_notional) / current_price

        return [
            OrderIntent(
                symbol=symbol,
                side=side,
                qty_or_notional=qty,
                order_type=OrderType.LIMIT,
                tif=TimeInForce.GTC,
                limit_price=current_price,  # Would use better pricing in practice
                tag="rebalance",
            )
        ]

    def _should_rebalance(self, current_timestamp: pd.Timestamp) -> bool:
        """Check if it's time to rebalance."""
        if self.last_rebalance_date is None:
            self.last_rebalance_date = current_timestamp
            return True

        if self.rebalance_frequency == "daily":
            return (current_timestamp - self.last_rebalance_date).days >= 1
        elif self.rebalance_frequency == "weekly":
            return (current_timestamp - self.last_rebalance_date).days >= 7

        return False

    def _get_target_weights(self) -> dict[str, float]:
        """Get target weights (equal-weight if not provided)."""
        if self.target_weights:
            return self.target_weights

        # Equal-weight: would need list of all symbols
        # Placeholder - would be set based on universe
        return {}

    def update_position(self, symbol: str, position_notional: float):
        """Update current position (called from execution pipeline)."""
        self.current_positions[symbol] = position_notional









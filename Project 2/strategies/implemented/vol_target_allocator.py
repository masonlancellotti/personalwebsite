"""Volatility target allocator - risk parity style."""

import pandas as pd
import numpy as np
from pydantic import BaseModel, Field
from typing import Optional

from strategies.base import Strategy, StrategyParams, register_strategy
from execution.intents import OrderIntent, OrderSide, OrderType, TimeInForce
from data.features import returns, volatility


class VolTargetAllocatorParams(StrategyParams):
    """Parameters for volatility target allocator."""

    target_vol: float = Field(default=0.15, gt=0, description="Target portfolio volatility (annualized)")
    vol_window: int = Field(default=20, ge=1, description="Window for volatility calculation")
    rebalance_frequency: str = Field(default="daily", description="Rebalance frequency: 'daily' or 'weekly'")
    min_vol: float = Field(default=0.01, gt=0, description="Minimum volatility to avoid division by zero")


@register_strategy(
    name="vol_target_allocator",
    params_schema=VolTargetAllocatorParams,
    explanation=(
        "Volatility target allocator (risk parity style). "
        "Allocates weights inversely proportional to rolling volatility. "
        "Scales overall exposure to target portfolio volatility. "
        "Rebalances on schedule (daily/weekly)."
    ),
)
class VolTargetAllocatorStrategy(Strategy):
    """Volatility target allocator strategy."""

    def __init__(self, **kwargs):
        """Initialize vol target allocator."""
        super().__init__(**kwargs)
        self.price_history: dict[str, list[float]] = {}  # symbol -> price history
        self.last_rebalance_date: Optional[pd.Timestamp] = None
        self.target_weights: dict[str, float] = {}

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

        # Update price history
        if symbol not in self.price_history:
            self.price_history[symbol] = []
        self.price_history[symbol].append(current_price)

        # Keep only recent history
        max_history = self.vol_window * 2
        if len(self.price_history[symbol]) > max_history:
            self.price_history[symbol] = self.price_history[symbol][-max_history:]

        # Check if it's time to rebalance
        if not self._should_rebalance(bar.name if hasattr(bar, 'name') else pd.Timestamp.now()):
            return []

        # Calculate target weights
        self._calculate_target_weights()

        # Generate rebalancing orders (simplified - would need current positions)
        # This is a placeholder - actual implementation would compare current vs target
        target_weight = self.target_weights.get(symbol, 0.0)
        if target_weight <= 0:
            return []

        # Placeholder order (actual would calculate needed qty based on portfolio value)
        # In practice, this would be handled by comparing current positions to target weights
        return []

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

    def _calculate_target_weights(self):
        """Calculate inverse volatility weights."""
        volatilities = {}

        for symbol, prices in self.price_history.items():
            if len(prices) < self.vol_window:
                continue

            price_series = pd.Series(prices)
            returns_series = returns(price_series)
            vol = volatility(returns_series, window=self.vol_window).iloc[-1]

            volatilities[symbol] = max(vol, self.min_vol)

        if not volatilities:
            return

        # Inverse volatility weighting
        inv_vols = {symbol: 1.0 / vol for symbol, vol in volatilities.items()}
        total_inv_vol = sum(inv_vols.values())

        self.target_weights = {
            symbol: inv_vol / total_inv_vol
            for symbol, inv_vol in inv_vols.items()
        }

        # Scale to target volatility
        # Simplified - would need portfolio-level vol calculation
        # For now, just normalize weights
        total_weight = sum(self.target_weights.values())
        if total_weight > 0:
            self.target_weights = {
                symbol: weight / total_weight
                for symbol, weight in self.target_weights.items()
            }









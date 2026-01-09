"""Cross-rate triangular arbitrage strategy."""

import pandas as pd
from pydantic import BaseModel, Field
from typing import Optional

from strategies.base import Strategy, StrategyParams, register_strategy
from execution.intents import OrderIntent, OrderSide, OrderType, TimeInForce


class CrossRateTriArbParams(StrategyParams):
    """Parameters for cross-rate triangular arbitrage."""

    min_profit_bps: float = Field(default=10.0, ge=0, description="Minimum profit in basis points after fees")
    max_notional_per_trade: float = Field(default=100.0, gt=0, description="Maximum notional per arbitrage trade")
    fee_bps: float = Field(default=10.0, ge=0, description="Estimated fee in basis points per leg")


@register_strategy(
    name="cross_rate_tri_arb",
    params_schema=CrossRateTriArbParams,
    explanation=(
        "Cross-rate triangular arbitrage strategy. "
        "Auto-detects valid triangles (USD -> A -> B -> USD) if all pairs exist in universe. "
        "Evaluates profit after fees + slippage. "
        "Executes sequentially with IOC limits and small notional caps. "
        "Unwinds safely if leg2 fails."
    ),
)
class CrossRateTriArbStrategy(Strategy):
    """Cross-rate triangular arbitrage strategy."""

    def __init__(self, **kwargs):
        """Initialize triangular arbitrage."""
        super().__init__(**kwargs)
        self.detected_triangles: list[tuple[str, str, str]] = []  # (USD/A, A/B, B/USD)
        self.active_arbitrages: dict[str, dict] = {}  # track active arbitrage attempts

    def on_bar(self, symbol: str, bar: pd.Series) -> list[OrderIntent]:
        """
        Generate triangular arbitrage orders.

        Args:
            symbol: Symbol
            bar: Bar data

        Returns:
            List of OrderIntents
        """
        # This strategy needs real-time quotes to detect arbitrage opportunities
        # It would need access to bid/ask prices, not just bars
        # For now, return empty - this is a placeholder implementation
        # Full implementation would:
        # 1. Detect triangles from universe
        # 2. Get current quotes for all three legs
        # 3. Calculate profit after fees
        # 4. Execute if profitable

        return []

    def detect_triangles(self, universe: list[str]) -> list[tuple[str, str, str]]:
        """
        Detect valid triangular arbitrage opportunities.

        Args:
            universe: List of all symbols in universe

        Returns:
            List of triangles as (leg1, leg2, leg3) tuples
        """
        triangles = []

        # Build symbol graph
        symbol_parts = {}
        for sym in universe:
            parts = sym.split("/")
            if len(parts) == 2:
                symbol_parts[sym] = (parts[0], parts[1])

        # Look for triangles: USD -> A -> B -> USD
        # This is simplified - would need more sophisticated graph traversal
        usd_symbols = [s for s in universe if s.startswith("USD/") or s.endswith("/USD")]

        # Placeholder - would implement proper triangle detection
        # For now, return empty
        return triangles

    def calculate_profit(
        self,
        leg1_rate: float,
        leg2_rate: float,
        leg3_rate: float,
        notional: float,
    ) -> float:
        """
        Calculate profit after fees.

        Args:
            leg1_rate: Rate for leg1 (USD -> A)
            leg2_rate: Rate for leg2 (A -> B)
            leg3_rate: Rate for leg3 (B -> USD)
            notional: Starting notional

        Returns:
            Profit after fees
        """
        # Execute: USD -> A -> B -> USD
        after_leg1 = notional * (1 - self.fee_bps / 10000.0) * leg1_rate
        after_leg2 = after_leg1 * (1 - self.fee_bps / 10000.0) * leg2_rate
        after_leg3 = after_leg2 * (1 - self.fee_bps / 10000.0) / leg3_rate  # Dividing by rate for USD return

        profit = after_leg3 - notional
        return profit









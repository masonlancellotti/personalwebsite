"""Liquidity guardrails - always-on filter strategy."""

from typing import Optional

import pandas as pd
from pydantic import BaseModel, Field

from strategies.base import Strategy, StrategyParams, register_strategy
from execution.intents import OrderIntent


class LiquidityGuardrailsParams(StrategyParams):
    """Parameters for liquidity guardrails."""

    min_spread_bps: float = Field(default=10.0, ge=0, description="Minimum spread in basis points")
    min_recent_trades: int = Field(default=1, ge=0, description="Minimum recent trades count")
    exclude_stable_stable: bool = Field(default=False, description="Exclude stable-stable pairs")


@register_strategy(
    name="liquidity_guardrails",
    params_schema=LiquidityGuardrailsParams,
    explanation=(
        "Liquidity guardrails filter strategy (always-on). "
        "Filters symbols based on minimum spread and recent trade activity. "
        "Returns empty intents - this is a filter strategy, not a trading strategy."
    ),
)
class LiquidityGuardrailsStrategy(Strategy):
    """Filter strategy that checks liquidity requirements."""

    def __init__(self, **kwargs):
        """Initialize liquidity guardrails."""
        super().__init__(**kwargs)
        # This strategy doesn't trade, it just filters
        # It will be applied separately in the execution pipeline

    def on_bar(self, symbol: str, bar: pd.Series) -> list[OrderIntent]:
        """
        This strategy doesn't emit orders - it's a filter.

        Returns:
            Empty list
        """
        return []

    def check_symbol(self, symbol: str, spread_bps: float, recent_trades: int) -> bool:
        """
        Check if symbol passes liquidity guardrails.

        Args:
            symbol: Symbol to check
            spread_bps: Current spread in basis points
            recent_trades: Recent trades count

        Returns:
            True if symbol passes, False otherwise
        """
        # Check spread
        if spread_bps < self.min_spread_bps:
            return False

        # Check recent trades
        if recent_trades < self.min_recent_trades:
            return False

        # Check stable-stable exclusion
        if self.exclude_stable_stable:
            stable_coins = {"USDT", "USDC", "DAI", "BUSD", "TUSD", "USD"}
            parts = symbol.split("/")
            if len(parts) == 2:
                base, quote = parts
                if base in stable_coins and quote in stable_coins:
                    return False

        return True









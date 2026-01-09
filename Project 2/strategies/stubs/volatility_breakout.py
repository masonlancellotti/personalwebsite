"""Volatility breakout strategy - stub."""

import pandas as pd
from pydantic import BaseModel, Field

from strategies.base import Strategy, StrategyParams, register_strategy
from execution.intents import OrderIntent


class VolatilityBreakoutParams(StrategyParams):
    """Parameters for volatility breakout."""

    vol_threshold: float = Field(default=0.02, gt=0, description="Volatility threshold for breakout")


@register_strategy(
    name="volatility_breakout",
    params_schema=VolatilityBreakoutParams,
    explanation="Volatility breakout strategy - enters when volatility exceeds threshold. Stub implementation.",
)
class VolatilityBreakoutStrategy(Strategy):
    """Volatility breakout strategy - stub."""

    def on_bar(self, symbol: str, bar: pd.Series) -> list[OrderIntent]:
        """Stub - not implemented."""
        return []









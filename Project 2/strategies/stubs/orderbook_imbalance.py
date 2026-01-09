"""Orderbook imbalance strategy - stub (requires L2 data)."""

import pandas as pd
from pydantic import BaseModel, Field

from strategies.base import Strategy, StrategyParams, register_strategy
from execution.intents import OrderIntent


class OrderbookImbalanceParams(StrategyParams):
    """Parameters for orderbook imbalance."""

    imbalance_threshold: float = Field(default=0.6, ge=0, le=1, description="Orderbook imbalance threshold")


@register_strategy(
    name="orderbook_imbalance",
    params_schema=OrderbookImbalanceParams,
    explanation="Orderbook imbalance strategy - trades based on bid/ask imbalance. Requires L2 data if available. Stub implementation.",
)
class OrderbookImbalanceStrategy(Strategy):
    """Orderbook imbalance strategy - stub."""

    def on_bar(self, symbol: str, bar: pd.Series) -> list[OrderIntent]:
        """Stub - not implemented."""
        return []









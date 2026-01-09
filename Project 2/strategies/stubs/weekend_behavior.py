"""Weekend behavior strategy - stub."""

import pandas as pd
from pydantic import BaseModel, Field

from strategies.base import Strategy, StrategyParams, register_strategy
from execution.intents import OrderIntent


class WeekendBehaviorParams(StrategyParams):
    """Parameters for weekend behavior."""

    weekend_exit: bool = Field(default=True, description="Exit positions before weekend")


@register_strategy(
    name="weekend_behavior",
    params_schema=WeekendBehaviorParams,
    explanation="Weekend behavior strategy - adjusts positions based on weekend patterns. Stub implementation.",
)
class WeekendBehaviorStrategy(Strategy):
    """Weekend behavior strategy - stub."""

    def on_bar(self, symbol: str, bar: pd.Series) -> list[OrderIntent]:
        """Stub - not implemented."""
        return []









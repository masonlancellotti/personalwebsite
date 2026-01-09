"""Mean reversion using Bollinger Bands."""

import pandas as pd
from pydantic import BaseModel, Field

from strategies.base import Strategy, StrategyParams, register_strategy
from execution.intents import OrderIntent


class MeanReversionBBParams(StrategyParams):
    """Parameters for mean reversion BB."""

    bb_period: int = Field(default=20, ge=1, description="Bollinger Band period")
    bb_std: float = Field(default=2.0, gt=0, description="Bollinger Band standard deviations")


@register_strategy(
    name="mean_reversion_bb",
    params_schema=MeanReversionBBParams,
    explanation=(
        "Mean reversion strategy using Bollinger Bands. "
        "Buys when price touches lower band, sells when price touches upper band. "
        "Baseline MR strategy. Disabled by default."
    ),
)
class MeanReversionBBStrategy(Strategy):
    """Mean reversion using Bollinger Bands."""

    def on_bar(self, symbol: str, bar: pd.Series) -> list[OrderIntent]:
        """Generate mean reversion orders."""
        # Disabled by default - placeholder implementation
        return []









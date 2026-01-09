"""Time of day seasonality strategy - stub."""

import pandas as pd
from pydantic import BaseModel, Field

from strategies.base import Strategy, StrategyParams, register_strategy
from execution.intents import OrderIntent


class TimeOfDaySeasonalityParams(StrategyParams):
    """Parameters for time of day seasonality."""

    buy_hour: int = Field(default=9, ge=0, le=23, description="Preferred buy hour (UTC)")
    sell_hour: int = Field(default=17, ge=0, le=23, description="Preferred sell hour (UTC)")


@register_strategy(
    name="time_of_day_seasonality",
    params_schema=TimeOfDaySeasonalityParams,
    explanation="Time of day seasonality strategy - trades based on time-of-day patterns. Stub implementation.",
)
class TimeOfDaySeasonalityStrategy(Strategy):
    """Time of day seasonality strategy - stub."""

    def on_bar(self, symbol: str, bar: pd.Series) -> list[OrderIntent]:
        """Stub - not implemented."""
        return []









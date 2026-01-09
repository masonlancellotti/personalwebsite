"""Grid trading strategy - range harvesting (risky in trends)."""

import pandas as pd
from pydantic import BaseModel, Field

from strategies.base import Strategy, StrategyParams, register_strategy
from execution.intents import OrderIntent, OrderSide, OrderType, TimeInForce


class GridTraderParams(StrategyParams):
    """Parameters for grid trader."""

    grid_spacing_bps: float = Field(default=50.0, ge=0, description="Grid spacing in basis points")
    num_levels: int = Field(default=10, ge=1, description="Number of grid levels")
    position_size: float = Field(default=100.0, gt=0, description="Position size per level")


@register_strategy(
    name="grid_trader",
    params_schema=GridTraderParams,
    explanation=(
        "Grid trading strategy - range harvesting. "
        "Places buy orders below current price and sell orders above. "
        "Risky in trending markets. Disabled by default."
    ),
)
class GridTraderStrategy(Strategy):
    """Grid trading strategy."""

    def on_bar(self, symbol: str, bar: pd.Series) -> list[OrderIntent]:
        """Generate grid orders."""
        # Disabled by default - placeholder implementation
        return []









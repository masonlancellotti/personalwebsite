"""Order intent dataclasses and enums."""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class OrderSide(str, Enum):
    """Order side."""

    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    """Order type."""

    LIMIT = "limit"
    MARKET = "market"


class TimeInForce(str, Enum):
    """Time in force."""

    GTC = "gtc"  # Good till cancel
    IOC = "ioc"  # Immediate or cancel


@dataclass
class OrderIntent:
    """Order intent emitted by strategies."""

    symbol: str
    side: OrderSide
    qty_or_notional: float  # Positive quantity or notional value
    limit_price: Optional[float] = None  # Required for limit orders
    tif: TimeInForce = TimeInForce.GTC
    order_type: OrderType = OrderType.LIMIT
    tag: Optional[str] = None  # Strategy identifier/tag

    def __post_init__(self):
        """Validate order intent."""
        if self.order_type == OrderType.LIMIT and self.limit_price is None:
            raise ValueError("Limit orders require limit_price")
        if self.qty_or_notional <= 0:
            raise ValueError("qty_or_notional must be positive")









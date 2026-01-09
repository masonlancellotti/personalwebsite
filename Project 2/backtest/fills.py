"""Conservative fill simulation for backtesting."""

from dataclasses import dataclass
from typing import Optional

import pandas as pd

from execution.intents import OrderIntent, OrderType


@dataclass
class FillResult:
    """Result of a fill simulation."""

    filled_qty: float
    fill_price: float
    fee: float
    is_partial: bool


class FillSimulator:
    """Conservative fill simulator."""

    def __init__(
        self,
        slippage_bps: int = 5,
        maker_fee_bps: int = 10,
        taker_fee_bps: int = 10,
        participation_rate: float = 0.1,
    ):
        """
        Initialize fill simulator.

        Args:
            slippage_bps: Slippage in basis points for market orders
            maker_fee_bps: Maker fee in basis points
            taker_fee_bps: Taker fee in basis points
            participation_rate: Max participation rate for partial fills (0.0 to 1.0)
        """
        self.slippage_bps = slippage_bps
        self.maker_fee_bps = maker_fee_bps
        self.taker_fee_bps = taker_fee_bps
        self.participation_rate = participation_rate

    def simulate_fill(
        self,
        intent: OrderIntent,
        current_bar: pd.Series,
        next_bar: Optional[pd.Series] = None,
    ) -> Optional[FillResult]:
        """
        Simulate order fill.

        Args:
            intent: Order intent
            current_bar: Current bar (for price reference)
            next_bar: Next bar (for limit order fills and market order execution)

        Returns:
            FillResult if filled, None otherwise
        """
        if next_bar is None:
            next_bar = current_bar

        if intent.order_type == OrderType.MARKET:
            return self._simulate_market_fill(intent, next_bar)
        else:  # LIMIT
            return self._simulate_limit_fill(intent, current_bar, next_bar)

    def _simulate_market_fill(
        self,
        intent: OrderIntent,
        next_bar: pd.Series,
    ) -> FillResult:
        """Simulate market order fill."""
        # Market orders fill at next bar open with slippage
        base_price = next_bar["open"]

        # Apply slippage
        slippage_mult = 1 + (self.slippage_bps / 10000.0)
        if intent.side.value == "buy":
            fill_price = base_price * slippage_mult  # Buy at worse price
        else:  # sell
            fill_price = base_price / slippage_mult  # Sell at worse price

        # Use full quantity (or cap by volume)
        filled_qty = intent.qty_or_notional

        # Cap by volume participation
        if "volume" in next_bar:
            max_qty = next_bar["volume"] * self.participation_rate
            if filled_qty > max_qty:
                filled_qty = max_qty

        # Calculate fee (taker fee for market orders)
        notional = filled_qty * fill_price
        fee = notional * (self.taker_fee_bps / 10000.0)

        return FillResult(
            filled_qty=filled_qty,
            fill_price=fill_price,
            fee=fee,
            is_partial=filled_qty < intent.qty_or_notional,
        )

    def _simulate_limit_fill(
        self,
        intent: OrderIntent,
        current_bar: pd.Series,
        next_bar: pd.Series,
    ) -> Optional[FillResult]:
        """Simulate limit order fill."""
        if intent.limit_price is None:
            return None

        limit_price = intent.limit_price
        buy_order = intent.side.value == "buy"

        # Check if price was crossed in next bar
        if buy_order:
            # Buy limit: fill if low <= limit_price
            if next_bar["low"] > limit_price:
                return None  # Not filled
            # Fill at limit or better (use limit_price conservatively)
            fill_price = limit_price
        else:  # sell
            # Sell limit: fill if high >= limit_price
            if next_bar["high"] < limit_price:
                return None  # Not filled
            # Fill at limit or better
            fill_price = limit_price

        # Calculate fill quantity
        filled_qty = intent.qty_or_notional

        # Cap by volume participation
        if "volume" in next_bar:
            max_qty = next_bar["volume"] * self.participation_rate
            if filled_qty > max_qty:
                filled_qty = max_qty

        # Calculate fee (maker fee for limit orders)
        notional = filled_qty * fill_price
        fee = notional * (self.maker_fee_bps / 10000.0)

        return FillResult(
            filled_qty=filled_qty,
            fill_price=fill_price,
            fee=fee,
            is_partial=filled_qty < intent.qty_or_notional,
        )









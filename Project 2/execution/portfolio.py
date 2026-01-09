"""Portfolio state tracking."""

from dataclasses import dataclass, field
from typing import Optional

from loguru import logger


@dataclass
class Position:
    """Position for a single symbol."""

    qty: float = 0.0
    avg_entry: float = 0.0
    unrealized_pnl: float = 0.0

    def notional(self, current_price: float) -> float:
        """Calculate current notional value."""
        return abs(self.qty * current_price)

    def cost_basis(self) -> float:
        """Calculate cost basis."""
        return abs(self.qty * self.avg_entry)


@dataclass
class Portfolio:
    """Portfolio state tracker."""

    cash: float = 0.0
    positions: dict[str, Position] = field(default_factory=dict)
    realized_pnl: float = 0.0

    def get_position(self, symbol: str) -> Position:
        """Get or create position for symbol."""
        if symbol not in self.positions:
            self.positions[symbol] = Position()
        return self.positions[symbol]

    def update_on_fill(
        self,
        symbol: str,
        side: str,
        qty: float,
        price: float,
        fee: float = 0.0,
    ):
        """
        Update portfolio on fill.

        Args:
            symbol: Symbol
            side: "buy" or "sell"
            qty: Quantity filled (always positive)
            price: Fill price
            fee: Fee paid (always positive)
        """
        position = self.get_position(symbol)
        cost = qty * price + fee

        if side.lower() == "buy":
            # Buying: increase position
            if position.qty == 0:
                # New position
                position.qty = qty
                position.avg_entry = price + (fee / qty)
            else:
                # Add to existing position
                total_cost = (position.qty * position.avg_entry) + cost
                position.qty += qty
                position.avg_entry = total_cost / position.qty

            self.cash -= cost

        else:  # sell
            # Selling: decrease position (long-only, so must have existing position)
            if position.qty <= 0:
                raise ValueError(f"Cannot sell {symbol}: no position (long-only)")

            if qty >= position.qty:
                # Closing entire position (or more)
                realized = (position.qty * price) - (position.qty * position.avg_entry) - fee
                self.realized_pnl += realized
                self.cash += (position.qty * price) - fee
                position.qty = 0
                position.avg_entry = 0.0
            else:
                # Partial close
                realized = (qty * price) - (qty * position.avg_entry) - fee
                self.realized_pnl += realized
                self.cash += (qty * price) - fee
                position.qty -= qty

    def get_total_exposure(self, symbol_prices: dict[str, float]) -> float:
        """Get total notional exposure."""
        total = 0.0
        for symbol, position in self.positions.items():
            if position.qty > 0:
                price = symbol_prices.get(symbol, position.avg_entry)
                total += position.notional(price)
        return total

    def get_unrealized_pnl(self, symbol_prices: dict[str, float]) -> float:
        """Calculate total unrealized PnL."""
        total = 0.0
        for symbol, position in self.positions.items():
            if position.qty > 0:
                current_price = symbol_prices.get(symbol, position.avg_entry)
                position.unrealized_pnl = (current_price - position.avg_entry) * position.qty
                total += position.unrealized_pnl
        return total

    def get_total_pnl(self, symbol_prices: dict[str, float]) -> float:
        """Get total PnL (realized + unrealized)."""
        return self.realized_pnl + self.get_unrealized_pnl(symbol_prices)

    def get_equity(self, symbol_prices: dict[str, float]) -> float:
        """Get total equity (cash + positions)."""
        return self.cash + self.get_total_exposure(symbol_prices)









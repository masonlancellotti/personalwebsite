"""Risk management and checks."""

from pathlib import Path
from typing import Optional

from loguru import logger

from config import settings
from execution.intents import OrderIntent
from execution.portfolio import Portfolio
from execution.order_manager import OrderManager


class RiskManager:
    """Risk management and order validation."""

    def __init__(self, portfolio: Portfolio, order_manager: OrderManager):
        """
        Initialize risk manager.

        Args:
            portfolio: Portfolio instance
            order_manager: OrderManager instance
        """
        self.portfolio = portfolio
        self.order_manager = order_manager
        self.daily_start_equity: Optional[float] = None

    def _check_quote_currency_balance(self, symbol: str, order_notional: float) -> tuple[bool, Optional[str]]:
        """Check if we have enough balance of the quote currency."""
        # Extract quote currency from symbol (e.g., "BTC/USD" -> "USD")
        if "/" not in symbol:
            return True, None  # Can't determine quote currency
        
        quote_currency = symbol.split("/")[1]
        
        # For USD pairs, check portfolio cash (more accurate than account balance)
        if quote_currency == "USD":
            available_cash = self.portfolio.cash
            if order_notional > available_cash:
                return False, f"Insufficient {quote_currency} balance: ${order_notional:.2f} required, ${available_cash:.2f} available"
        
        # For other quote currencies (USDC, USDT, BTC, ETH), we don't track balances
        # The broker will reject the order if we don't have enough, which is fine
        # We filter to USD-only pairs anyway to prevent these errors
        
        return True, None

    def check_order_intent(
        self,
        intent: OrderIntent,
        symbol_state: dict[str, dict],
        symbol_prices: dict[str, float],
    ) -> tuple[bool, Optional[str]]:
        """
        Check if order intent passes risk checks.

        Args:
            intent: Order intent to check
            symbol_state: Dict mapping symbol to state {bid, ask, mid, last_update_ts}
            symbol_prices: Dict mapping symbol to current price

        Returns:
            Tuple of (passed, error_message)
        """
        symbol = intent.symbol

        # Check kill switch
        if not self.check_kill_switch():
            return False, "Kill switch activated"

        # Check daily loss limit
        if not self.check_daily_loss(symbol_prices):
            return False, "Daily loss limit exceeded"

        # Get symbol state
        state = symbol_state.get(symbol, {})

        # Check stale data
        if not self._check_stale_data(state):
            return False, f"Data stale for {symbol}"

        # Calculate order notional
        current_price = symbol_prices.get(symbol)
        if current_price is None:
            current_price = state.get("mid")
        if current_price is None:
            return False, f"No price data for {symbol}"

        # For notional-based orders, calculate quantity
        # Note: intent.qty_or_notional is the quantity, not notional
        # Calculate notional value for checks
        order_notional = intent.qty_or_notional * current_price
        order_qty = intent.qty_or_notional
        
        # Check for numerical overflow - reject extremely large quantities
        if order_qty > settings.MAX_ORDER_QTY:
            return False, f"Order quantity {order_qty:.2f} exceeds MAX_ORDER_QTY {settings.MAX_ORDER_QTY:.2f} (overflow protection)"
        
        # Check quote currency balance (for buy orders)
        if intent.side.value == "buy":
            passed, error_msg = self._check_quote_currency_balance(symbol, order_notional)
            if not passed:
                return False, error_msg

        # Check MAX_ORDER_NOTIONAL
        if order_notional > settings.MAX_ORDER_NOTIONAL:
            return False, f"Order notional ${order_notional:.2f} exceeds MAX_ORDER_NOTIONAL ${settings.MAX_ORDER_NOTIONAL:.2f}"

        # Check MAX_POSITION_NOTIONAL_PER_SYMBOL (long-only)
        if intent.side.value == "buy":
            position = self.portfolio.get_position(symbol)
            current_position_notional = position.notional(current_price)
            new_position_notional = current_position_notional + order_notional
            new_position_qty = position.qty + order_qty

            if new_position_notional > settings.MAX_POSITION_NOTIONAL_PER_SYMBOL:
                return False, (
                    f"Position notional ${new_position_notional:.2f} would exceed "
                    f"MAX_POSITION_NOTIONAL_PER_SYMBOL ${settings.MAX_POSITION_NOTIONAL_PER_SYMBOL:.2f}"
                )
            
            # Check for position quantity overflow
            if new_position_qty > settings.MAX_POSITION_QTY:
                return False, (
                    f"Position quantity {new_position_qty:.2f} would exceed "
                    f"MAX_POSITION_QTY {settings.MAX_POSITION_QTY:.2f} (overflow protection)"
                )

        # Check TOTAL_MAX_NOTIONAL
        total_exposure = self.portfolio.get_total_exposure(symbol_prices)
        if intent.side.value == "buy":
            new_total_exposure = total_exposure + order_notional
            if new_total_exposure > settings.TOTAL_MAX_NOTIONAL:
                return False, (
                    f"Total exposure ${new_total_exposure:.2f} would exceed "
                    f"TOTAL_MAX_NOTIONAL ${settings.TOTAL_MAX_NOTIONAL:.2f}"
                )

        # Check MAX_OPEN_ORDERS_PER_SYMBOL
        open_orders = self.order_manager.get_open_orders_for_symbol(symbol)
        if len(open_orders) >= settings.MAX_OPEN_ORDERS_PER_SYMBOL:
            return False, (
                f"Open orders ({len(open_orders)}) for {symbol} exceeds "
                f"MAX_OPEN_ORDERS_PER_SYMBOL ({settings.MAX_OPEN_ORDERS_PER_SYMBOL})"
            )

        # Check PRICE_BAND_BPS for limit orders
        if intent.order_type.value == "limit" and intent.limit_price:
            mid = state.get("mid", current_price)
            if mid:
                price_diff_bps = abs(intent.limit_price - mid) / mid * 10000
                if price_diff_bps > settings.PRICE_BAND_BPS:
                    return False, (
                        f"Limit price ${intent.limit_price:.2f} is {price_diff_bps:.1f} bps from mid ${mid:.2f}, "
                        f"exceeds PRICE_BAND_BPS {settings.PRICE_BAND_BPS} bps"
                    )

        return True, None

    def _check_stale_data(self, state: dict) -> bool:
        """Check if symbol state data is fresh."""
        from datetime import datetime, timezone

        last_update_ts = state.get("last_update_ts")
        if last_update_ts is None:
            return False

        # Calculate age
        if isinstance(last_update_ts, datetime):
            age_seconds = (datetime.now(timezone.utc) - last_update_ts).total_seconds()
        else:
            # Assume timestamp
            age_seconds = (datetime.now(timezone.utc).timestamp() - last_update_ts)

        return age_seconds <= settings.STALE_DATA_SECONDS

    def check_kill_switch(self) -> bool:
        """Check if kill switch file exists."""
        kill_switch_path = Path(settings.KILL_SWITCH_FILE)
        if kill_switch_path.exists():
            logger.warning(f"Kill switch file found: {kill_switch_path}")
            return False
        return True

    def check_daily_loss(self, symbol_prices: dict[str, float]) -> bool:
        """Check if daily loss limit exceeded."""
        # Initialize daily start equity if needed
        # This should be called AFTER reconciliation to capture the starting state
        if self.daily_start_equity is None:
            self.daily_start_equity = self.portfolio.get_equity(symbol_prices)
            return True  # First call, can't have lost anything yet

        # Calculate current equity
        current_equity = self.portfolio.get_equity(symbol_prices)
        
        # Calculate loss (if current equity is less than start equity)
        equity_change = current_equity - self.daily_start_equity
        loss = -equity_change  # Loss is negative equity change
        
        if loss > settings.MAX_DAILY_LOSS:
            logger.warning(
                f"Daily loss limit exceeded: ${loss:.2f} > ${settings.MAX_DAILY_LOSS:.2f} "
                f"(equity: ${current_equity:.2f}, start: ${self.daily_start_equity:.2f})"
            )
            return False

        return True

    def initialize_daily_loss(self, symbol_prices: dict[str, float]):
        """Initialize daily loss tracking with current equity (call after reconciliation)."""
        if self.daily_start_equity is None:
            self.daily_start_equity = self.portfolio.get_equity(symbol_prices)
            logger.info(f"Initialized daily loss tracking: start equity = ${self.daily_start_equity:.2f}")

    def reset_daily_loss(self):
        """Reset daily loss tracking (call at start of new day)."""
        self.daily_start_equity = None



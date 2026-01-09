"""Periodic reconciliation with broker state."""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional

from alpaca.trading.requests import GetOrdersRequest
from alpaca.trading.enums import QueryOrderStatus
from loguru import logger

from alpaca_clients import get_clients
from execution.portfolio import Portfolio
from execution.order_manager import OrderManager
from storage import get_storage


def _normalize_symbol(symbol: str) -> str:
    """
    Normalize symbol format between Alpaca format (AAVEUSD) and our format (AAVE/USD).
    
    Args:
        symbol: Symbol in either format
        
    Returns:
        Symbol in our format (AAVE/USD)
    """
    # If it already has a slash, return as-is
    if "/" in symbol:
        return symbol
    
    # Try to detect quote currency (common ones: USD, USDC, USDT, BTC, ETH)
    # Check longer quotes first (USDT, USDC, USDP) before shorter ones (USD)
    quote_currencies = ["USDT", "USDC", "USDP", "BTC", "ETH", "USD"]
    
    for quote in quote_currencies:
        if symbol.endswith(quote):
            base = symbol[:-len(quote)]
            if base:  # Make sure we have a base symbol
                return f"{base}/{quote}"
    
    # If no match and symbol is long enough, try splitting at common patterns
    # This handles edge cases where the symbol format is unusual
    if len(symbol) >= 6:
        # Try last 3 chars as USD
        return f"{symbol[:-3]}/USD"
    
    # Return as-is if we can't normalize
    return symbol


class ReconcileManager:
    """Reconciliation manager for broker state."""

    def __init__(
        self,
        portfolio: Portfolio,
        order_manager: OrderManager,
        reconcile_interval_seconds: int = 60,
    ):
        """
        Initialize reconciliation manager.

        Args:
            portfolio: Portfolio instance
            order_manager: OrderManager instance
            reconcile_interval_seconds: Reconciliation interval
        """
        self.portfolio = portfolio
        self.order_manager = order_manager
        self.reconcile_interval_seconds = reconcile_interval_seconds
        self.clients = get_clients()
        self.trading_client = self.clients.trading_client
        self.storage = get_storage()
        self.last_reconcile: Optional[datetime] = None

    def reconcile(self):
        """Reconcile local state with broker state."""
        try:
            logger.info("Starting reconciliation...")

            # Reconcile positions
            self._reconcile_positions()

            # Reconcile orders
            self._reconcile_orders()

            self.last_reconcile = datetime.now(timezone.utc)
            logger.info("Reconciliation complete")

        except Exception as e:
            logger.error(f"Error during reconciliation: {e}")

    def _reconcile_positions(self):
        """Reconcile positions with broker."""
        try:
            # Fetch positions from broker
            broker_positions = self.trading_client.get_all_positions()

            broker_pos_dict = {}
            for pos in broker_positions:
                broker_symbol = pos.symbol
                # Normalize symbol format (AAVEUSD -> AAVE/USD)
                normalized_symbol = _normalize_symbol(broker_symbol)
                broker_pos_dict[normalized_symbol] = {
                    "qty": float(pos.qty),
                    "avg_entry": float(pos.avg_entry_price),
                }

            # Compare with local portfolio
            for symbol, broker_pos in broker_pos_dict.items():
                local_pos = self.portfolio.get_position(symbol)

                qty_diff = abs(broker_pos["qty"] - local_pos.qty)
                entry_diff = abs(broker_pos["avg_entry"] - local_pos.avg_entry) if local_pos.qty != 0 else 0

                if qty_diff > 0.01 or entry_diff > 0.01:  # Tolerance
                    logger.warning(
                        f"Position mismatch for {symbol}: "
                        f"local qty={local_pos.qty}, broker qty={broker_pos['qty']}, "
                        f"local entry={local_pos.avg_entry}, broker entry={broker_pos['avg_entry']}"
                    )
                    # Update local position to match broker
                    local_pos.qty = broker_pos["qty"]
                    local_pos.avg_entry = broker_pos["avg_entry"]
                    logger.info(f"Updated local position for {symbol} to match broker: qty={broker_pos['qty']}, entry={broker_pos['avg_entry']}")

            # Check for positions in broker but not locally
            for symbol in broker_pos_dict:
                if symbol not in self.portfolio.positions or self.portfolio.positions[symbol].qty == 0.0:
                    if symbol not in self.portfolio.positions:
                        logger.info(f"Found position in broker but not locally: {symbol}, adding to portfolio")
                    pos = self.portfolio.get_position(symbol)
                    broker_pos = broker_pos_dict[symbol]
                    pos.qty = broker_pos["qty"]
                    pos.avg_entry = broker_pos["avg_entry"]
                    logger.info(f"Added/updated position for {symbol}: qty={broker_pos['qty']}, entry={broker_pos['avg_entry']}")

        except Exception as e:
            logger.error(f"Error reconciling positions: {e}")

    def _reconcile_orders(self):
        """Reconcile orders with broker."""
        try:
            # Fetch open orders from broker
            orders_filter = GetOrdersRequest(status=QueryOrderStatus.OPEN)
            broker_orders = list(self.trading_client.get_orders(filter=orders_filter))

            broker_order_ids = set()
            broker_orders_dict = {}  # order_id -> order object
            for order in broker_orders:
                order_id_str = str(order.id)
                broker_order_ids.add(order_id_str)
                broker_orders_dict[order_id_str] = order

            # Compare with local open orders
            local_order_ids = set(
                order_data.get("alpaca_order_id")
                for order_data in self.order_manager.open_orders.values()
                if order_data.get("alpaca_order_id")
            )

            # Orders in broker but not locally - these are orphaned orders
            # We should cancel them as they're not being managed by this bot instance
            missing_locally = broker_order_ids - local_order_ids
            if missing_locally:
                logger.warning(f"Found {len(missing_locally)} orphaned orders in broker (not tracked locally): {missing_locally}")
                # Cancel orphaned orders - they're likely from a previous bot instance or manual trades
                for order_id_str in missing_locally:
                    order = broker_orders_dict.get(order_id_str)
                    if order:
                        try:
                            self.trading_client.cancel_order_by_id(order.id)
                            logger.info(f"Canceled orphaned order: {order.id} for {order.symbol}")
                        except Exception as e:
                            logger.debug(f"Could not cancel orphaned order {order.id} (may already be filled/canceled): {e}")

            # Orders locally but not in broker (should be canceled)
            missing_in_broker = local_order_ids - broker_order_ids
            if missing_in_broker:
                logger.warning(f"Orders locally but not in broker (likely filled/canceled): {missing_in_broker}")
                # Remove from local tracking
                for client_order_id, order_data in list(self.order_manager.open_orders.items()):
                    if order_data.get("alpaca_order_id") in missing_in_broker:
                        del self.order_manager.open_orders[client_order_id]
                        # Update storage
                        self.storage.update_order_status(client_order_id, "filled")  # Assume filled

        except Exception as e:
            logger.error(f"Error reconciling orders: {e}")

    def should_reconcile(self) -> bool:
        """Check if it's time to reconcile."""
        if self.last_reconcile is None:
            return True

        elapsed = (datetime.now(timezone.utc) - self.last_reconcile).total_seconds()
        return elapsed >= self.reconcile_interval_seconds


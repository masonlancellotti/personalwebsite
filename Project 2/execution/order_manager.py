"""Order management: submit, cancel, replace with idempotent client_order_id."""

import hashlib
import time
from datetime import datetime
from typing import Any, Optional

from alpaca.trading.requests import LimitOrderRequest, MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce
from loguru import logger

from alpaca_clients import get_clients
from config import settings
from execution.intents import OrderIntent, OrderSide as IntentOrderSide, OrderType, TimeInForce as IntentTimeInForce
from storage import get_storage


class OrderManager:
    """Order manager with idempotent client_order_id generation."""

    def __init__(self):
        """Initialize order manager."""
        self.clients = get_clients()
        self.trading_client = self.clients.trading_client
        self.storage = get_storage()
        self.open_orders: dict[str, dict[str, Any]] = {}  # client_order_id -> order data
        self.last_replace_time: dict[str, float] = {}  # symbol -> timestamp
        self.processed_fill_qty: dict[str, float] = {}  # client_order_id -> last processed filled quantity

    def generate_client_order_id(
        self,
        strategy_name: str,
        symbol: str,
        side: str,
        price_bucket: float,
        timestamp_bucket: int,
        tag: Optional[str] = None,
    ) -> str:
        """
        Generate deterministic, idempotent client_order_id.

        Args:
            strategy_name: Strategy name
            symbol: Symbol
            side: Order side ("buy" or "sell")
            price_bucket: Price rounded to bucket (e.g., price rounded to 0.01)
            timestamp_bucket: Timestamp rounded to bucket (e.g., seconds // 60 for 1-minute bucket)
            tag: Optional tag

        Returns:
            Deterministic client_order_id
        """
        # Create deterministic string
        parts = [
            strategy_name,
            symbol,
            side,
            f"{price_bucket:.8f}",  # Fixed precision
            str(timestamp_bucket),
        ]
        if tag:
            parts.append(tag)

        combined = "|".join(parts)

        # Hash to get consistent length (first 16 chars of hex)
        order_id_hash = hashlib.md5(combined.encode()).hexdigest()[:16]

        return f"{strategy_name[:8]}_{symbol[:6]}_{order_id_hash}"

    def submit_order(
        self,
        intent: OrderIntent,
        strategy_name: str,
        current_price: float,
    ) -> Optional[dict[str, Any]]:
        """
        Submit order to Alpaca.

        Args:
            intent: Order intent
            strategy_name: Strategy name
            current_price: Current price for idempotency

        Returns:
            Order dict if successful, None otherwise
        """
        try:
            # Generate idempotent client_order_id
            price_bucket = round(intent.limit_price if intent.limit_price else current_price, 2)
            timestamp_bucket = int(datetime.utcnow().timestamp()) // 60  # 1-minute bucket

            client_order_id = self.generate_client_order_id(
                strategy_name=strategy_name,
                symbol=intent.symbol,
                side=intent.side.value,
                price_bucket=price_bucket,
                timestamp_bucket=timestamp_bucket,
                tag=intent.tag,
            )

            # Check if order already exists (idempotency)
            if client_order_id in self.open_orders:
                logger.debug(f"Order {client_order_id} already exists, skipping")
                return self.open_orders[client_order_id]

            # Convert to Alpaca order request
            side = OrderSide.BUY if intent.side == IntentOrderSide.BUY else OrderSide.SELL
            tif = TimeInForce.GTC if intent.tif == IntentTimeInForce.GTC else TimeInForce.IOC

            if intent.order_type == OrderType.MARKET:
                order_request = MarketOrderRequest(
                    symbol=intent.symbol,
                    qty=intent.qty_or_notional,
                    side=side,
                    time_in_force=tif,
                    client_order_id=client_order_id,
                )
            else:  # LIMIT
                if intent.limit_price is None:
                    logger.error(f"Limit order requires limit_price for {intent.symbol}")
                    return None

                order_request = LimitOrderRequest(
                    symbol=intent.symbol,
                    qty=intent.qty_or_notional,
                    side=side,
                    time_in_force=tif,
                    limit_price=intent.limit_price,
                    client_order_id=client_order_id,
                )

            # Submit order
            order = self.trading_client.submit_order(order_request)

            # Store in open orders
            order_dict = {
                "client_order_id": client_order_id,
                "alpaca_order_id": str(order.id),
                "symbol": intent.symbol,
                "status": order.status.value if hasattr(order.status, "value") else str(order.status),
            }
            self.open_orders[client_order_id] = order_dict
            # Initialize processed fill quantity tracking
            self.processed_fill_qty[client_order_id] = 0.0

            # Write to storage
            self.storage.write_order(
                client_order_id=client_order_id,
                symbol=intent.symbol,
                side=intent.side.value,
                qty=intent.qty_or_notional,
                order_type=intent.order_type.value,
                time_in_force=intent.tif.value,
                strategy_tag=strategy_name,
                price=intent.limit_price,
                status="submitted",
                alpaca_order_id=str(order.id),
            )

            logger.info(f"Submitted order {client_order_id} for {intent.symbol}")

            return order_dict

        except Exception as e:
            logger.error(f"Error submitting order for {intent.symbol}: {e}")
            return None

    def cancel_order(self, client_order_id: str) -> bool:
        """Cancel order by client_order_id."""
        try:
            if client_order_id not in self.open_orders:
                logger.warning(f"Order {client_order_id} not found in open orders")
                return False

            order_dict = self.open_orders[client_order_id]
            alpaca_order_id = order_dict.get("alpaca_order_id")

            if alpaca_order_id:
                self.trading_client.cancel_order_by_id(alpaca_order_id)
                logger.info(f"Canceled order {client_order_id}")

            # Remove from open orders
            del self.open_orders[client_order_id]
            # Remove from processed fill tracking
            self.processed_fill_qty.pop(client_order_id, None)

            # Update storage
            self.storage.update_order_status(client_order_id, "canceled")

            return True

        except Exception as e:
            logger.error(f"Error canceling order {client_order_id}: {e}")
            return False

    def cancel_all_orders(self, symbol: Optional[str] = None) -> int:
        """Cancel all open orders, optionally filtered by symbol."""
        canceled_count = 0

        orders_to_cancel = list(self.open_orders.keys())
        if symbol:
            orders_to_cancel = [
                oid for oid, order_data in self.open_orders.items()
                if order_data.get("symbol") == symbol
            ]

        for client_order_id in orders_to_cancel:
            if self.cancel_order(client_order_id):
                canceled_count += 1

        logger.info(f"Canceled {canceled_count} orders")
        return canceled_count

    def get_open_orders_for_symbol(self, symbol: str) -> list[dict[str, Any]]:
        """Get open orders for a symbol."""
        return [
            order_data for order_data in self.open_orders.values()
            if order_data.get("symbol") == symbol
        ]

    def can_replace_order(self, symbol: str) -> bool:
        """Check if enough time has passed since last replace for this symbol."""
        last_replace = self.last_replace_time.get(symbol, 0)
        elapsed = time.time() - last_replace
        return elapsed >= settings.MIN_SECONDS_BETWEEN_REPLACES

    def mark_replace_time(self, symbol: str):
        """Mark that an order was replaced for this symbol."""
        self.last_replace_time[symbol] = time.time()
    
    def poll_for_fills(self) -> list[dict[str, Any]]:
        """
        Poll broker for filled orders and return fill information.
        Checks our tracked open orders to see if any have been filled.
        
        Returns:
            List of fill dicts with {client_order_id, symbol, side, qty, price, fee}
        """
        from alpaca.trading.requests import GetOrdersRequest
        from alpaca.trading.enums import QueryOrderStatus
        
        fills = []
        
        try:
            # Check each of our open orders
            for client_order_id, order_data in list(self.open_orders.items()):
                alpaca_order_id = order_data.get("alpaca_order_id")
                if not alpaca_order_id:
                    continue
                    
                try:
                    # Fetch the order from broker to check status
                    order = self.trading_client.get_order_by_id(alpaca_order_id)
                    
                    # Check if filled
                    if order.status.value.lower() in ("filled", "partially_filled"):
                        total_filled_qty = float(order.filled_qty) if order.filled_qty else 0.0
                        fill_price = float(order.filled_avg_price) if order.filled_avg_price else 0.0
                        
                        # Get last processed fill quantity for this order
                        last_processed_qty = self.processed_fill_qty.get(client_order_id, 0.0)
                        
                        # Calculate incremental fill (only report new fills)
                        incremental_fill_qty = total_filled_qty - last_processed_qty
                        
                        if incremental_fill_qty > 0:
                            fills.append({
                                "client_order_id": client_order_id,
                                "symbol": order_data.get("symbol", order.symbol),
                                "side": order.side.value.lower(),
                                "qty": incremental_fill_qty,  # Only the new fill amount
                                "price": fill_price,
                                "fee": 0.0,  # Fee not available from order object directly
                            })
                            
                            # Update processed fill quantity
                            self.processed_fill_qty[client_order_id] = total_filled_qty
                            
                            # Remove from open orders if fully filled
                            if order.status.value.lower() == "filled":
                                del self.open_orders[client_order_id]
                                self.processed_fill_qty.pop(client_order_id, None)
                                # Update storage
                                self.storage.update_order_status(client_order_id, "filled")
                            else:
                                # Partially filled - update but keep in open_orders
                                order_data["status"] = "partially_filled"
                                
                except Exception as e:
                    # Order might not exist anymore (filled/canceled)
                    logger.debug(f"Error checking order {alpaca_order_id}: {e}")
                    # Try to remove it from tracking
                    try:
                        del self.open_orders[client_order_id]
                        self.processed_fill_qty.pop(client_order_id, None)
                        self.storage.update_order_status(client_order_id, "unknown")
                    except KeyError:
                        pass
                        
        except Exception as e:
            logger.error(f"Error polling for fills: {e}")
            
        return fills


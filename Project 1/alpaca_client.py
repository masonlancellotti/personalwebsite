"""Alpaca Trading API client wrapper."""
import os
import time
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta, timezone
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest, LimitOrderRequest, StopLossRequest
from alpaca.trading.enums import OrderSide, TimeInForce, OrderType
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.data.enums import DataFeed
from alpaca.common.exceptions import APIError
import logging

logger = logging.getLogger(__name__)


class AlpacaClient:
    """Wrapper for Alpaca Trading API."""
    
    def __init__(self, api_key: str, secret_key: str, paper: bool = True):
        """
        Initialize Alpaca client.
        
        Args:
            api_key: Alpaca API key
            secret_key: Alpaca secret key
            paper: If True, use paper trading endpoint
        """
        self.api_key = api_key
        self.secret_key = secret_key
        self.paper = paper
        
        # Initialize trading client
        base_url = "https://paper-api.alpaca.markets" if paper else "https://api.alpaca.markets"
        self.trading_client = TradingClient(api_key, secret_key, paper=paper)
        
        # Initialize historical data client
        self.data_client = StockHistoricalDataClient(api_key, secret_key)
        
        logger.info(f"Alpaca client initialized in {'paper' if paper else 'live'} trading mode")
    
    def get_account(self) -> Dict[str, Any]:
        """
        Get account information.
        
        Returns:
            Account details dictionary
        """
        try:
            account = self.trading_client.get_account()
            return {
                'equity': float(account.equity),
                'cash': float(account.cash),
                'buying_power': float(account.buying_power),
                'portfolio_value': float(account.portfolio_value),
                'pattern_day_trader': account.pattern_day_trader,
                'trading_blocked': account.trading_blocked,
                'account_blocked': account.account_blocked,
            }
        except APIError as e:
            logger.error(f"Error fetching account: {e}")
            raise
    
    def get_positions(self) -> List[Dict[str, Any]]:
        """
        Get all open positions.
        
        Returns:
            List of position dictionaries
        """
        try:
            positions = self.trading_client.get_all_positions()
            return [
                {
                    'symbol': pos.symbol,
                    'qty': float(pos.qty),
                    'avg_entry_price': float(pos.avg_entry_price),
                    'current_price': float(pos.current_price),
                    'market_value': float(pos.market_value),
                    'cost_basis': float(pos.cost_basis),
                    'unrealized_pl': float(pos.unrealized_pl),
                    'unrealized_plpc': float(pos.unrealized_plpc),
                }
                for pos in positions
            ]
        except APIError as e:
            logger.error(f"Error fetching positions: {e}")
            return []
    
    def get_position(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get position for a specific symbol.
        
        Args:
            symbol: Stock symbol
            
        Returns:
            Position dictionary or None if no position exists
        """
        try:
            position = self.trading_client.get_open_position(symbol)
            return {
                'symbol': position.symbol,
                'qty': float(position.qty),
                'avg_entry_price': float(position.avg_entry_price),
                'current_price': float(position.current_price),
                'market_value': float(position.market_value),
                'cost_basis': float(position.cost_basis),
                'unrealized_pl': float(position.unrealized_pl),
                'unrealized_plpc': float(position.unrealized_plpc),
            }
        except APIError as e:
            # Position doesn't exist
            return None
    
    def get_open_orders(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get open/pending orders.
        
        Args:
            symbol: Optional symbol to filter by
            
        Returns:
            List of order dictionaries
        """
        try:
            # Try to get orders - newer Alpaca API doesn't accept status/limit parameters
            # Try calling with no parameters first
            try:
                all_orders = self.trading_client.get_orders()
            except TypeError as e:
                # If get_orders() doesn't work, try alternative approach
                logger.warning(f"get_orders() failed: {e}, trying alternative method")
                # Try using get_all_orders if available
                if hasattr(self.trading_client, 'get_all_orders'):
                    all_orders = self.trading_client.get_all_orders()
                else:
                    # Last resort: return empty list
                    logger.error("Unable to fetch orders - API method not available")
                    return []
            
            # Filter for open orders manually
            # Open order statuses: 'new', 'partially_filled', 'pending_new', 'accepted'
            open_statuses = ['new', 'partially_filled', 'pending_new', 'accepted']
            
            result = []
            for order in all_orders:
                try:
                    # Get order status
                    order_status = order.status.value if hasattr(order.status, 'value') else str(order.status)
                    
                    # Only include open orders
                    if order_status.lower() in [s.lower() for s in open_statuses]:
                        order_dict = {
                            'id': order.id,
                            'symbol': order.symbol,
                            'side': order.side.value if hasattr(order.side, 'value') else str(order.side),
                            'qty': float(order.qty),
                            'order_type': order.order_type.value if hasattr(order.order_type, 'value') else str(order.order_type),
                            'status': order_status,
                            'created_at': order.created_at.isoformat() if hasattr(order.created_at, 'isoformat') else str(order.created_at),
                        }
                        if symbol is None or order.symbol == symbol:
                            result.append(order_dict)
                except Exception as e:
                    logger.debug(f"Error processing order {getattr(order, 'id', 'unknown')}: {e}")
                    continue
            
            # Limit to 100 most recent if we have many orders
            if len(result) > 100:
                result = result[:100]
            
            return result
        except Exception as e:
            logger.error(f"Error fetching open orders: {e}")
            return []
    
    def submit_order(
        self,
        symbol: str,
        qty: float,
        side: str,
        order_type: str = "market",
        limit_price: Optional[float] = None,
        stop_loss: Optional[float] = None,
        time_in_force: str = "day"
    ) -> Optional[str]:
        """
        Submit an order.
        
        Args:
            symbol: Stock symbol
            qty: Quantity to trade
            side: "buy" or "sell"
            order_type: "market" or "limit"
            limit_price: Limit price (required for limit orders)
            stop_loss: Stop loss price
            time_in_force: "day", "gtc", "ioc", "fok"
            
        Returns:
            Order ID if successful, None otherwise
        """
        try:
            order_side = OrderSide.BUY if side.lower() == "buy" else OrderSide.SELL
            tif = TimeInForce.DAY if time_in_force.lower() == "day" else TimeInForce.GTC
            
            # Create stop loss request if provided
            stop_loss_request = None
            if stop_loss:
                stop_loss_request = StopLossRequest(stop_price=stop_loss)
            
            if order_type.lower() == "market":
                order_request = MarketOrderRequest(
                    symbol=symbol,
                    qty=qty,
                    side=order_side,
                    time_in_force=tif,
                    stop_loss=stop_loss_request
                )
            elif order_type.lower() == "limit":
                if not limit_price:
                    raise ValueError("limit_price is required for limit orders")
                order_request = LimitOrderRequest(
                    symbol=symbol,
                    qty=qty,
                    side=order_side,
                    limit_price=limit_price,
                    time_in_force=tif,
                    stop_loss=stop_loss_request
                )
            else:
                raise ValueError(f"Unsupported order type: {order_type}")
            
            order = self.trading_client.submit_order(order_request)
            logger.info(f"Order submitted: {order.id} - {side} {qty} {symbol}")
            return order.id
            
        except APIError as e:
            logger.error(f"Error submitting order for {symbol}: {e}")
            return None
    
    def cancel_order(self, order_id: str) -> bool:
        """
        Cancel an order.
        
        Args:
            order_id: Order ID to cancel
            
        Returns:
            True if successful, False otherwise
        """
        try:
            self.trading_client.cancel_order_by_id(order_id)
            logger.info(f"Order cancelled: {order_id}")
            return True
        except APIError as e:
            logger.error(f"Error cancelling order {order_id}: {e}")
            return False
    
    def get_bars(
        self,
        symbol: str,
        timeframe: str = "1Day",
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get historical bars for a symbol.
        
        Args:
            symbol: Stock symbol
            timeframe: Timeframe string (e.g., "1Day", "1Hour", "15Min")
            start: Start datetime
            end: End datetime
            limit: Maximum number of bars to return
            
        Returns:
            List of bar dictionaries
        """
        try:
            # Parse timeframe
            # For custom minute timeframes, use TimeFrame(amount, unit) syntax
            tf_map = {
                "1Day": TimeFrame.Day,
                "1Hour": TimeFrame.Hour,
                "30Min": TimeFrame(amount=30, unit=TimeFrame.Minute),
                "15Min": TimeFrame(amount=15, unit=TimeFrame.Minute),
                "5Min": TimeFrame(amount=5, unit=TimeFrame.Minute),
                "1Min": TimeFrame.Minute,
            }
            
            tf = tf_map.get(timeframe, TimeFrame.Day)
            
            # Default to last 100 days if start not provided
            # Alpaca requires timezone-aware datetime objects
            if not start:
                start = datetime.now(timezone.utc) - timedelta(days=limit)
            else:
                # Ensure timezone-aware
                if start.tzinfo is None:
                    start = start.replace(tzinfo=timezone.utc)
            if not end:
                end = datetime.now(timezone.utc)
            else:
                # Ensure timezone-aware
                if end.tzinfo is None:
                    end = end.replace(tzinfo=timezone.utc)
            
            request_params = StockBarsRequest(
                symbol_or_symbols=[symbol],
                timeframe=tf,
                start=start,
                end=end,
                limit=limit,
                feed=DataFeed.IEX  # Use IEX feed for basic accounts
            )
            
            bars = self.data_client.get_stock_bars(request_params)
            
            result = []
            # Handle BarSet response - use .df property for easier access
            if bars:
                try:
                    # Use the .df property (recommended approach)
                    df = bars.df
                    if not df.empty:
                        # DataFrame has multi-index (symbol, timestamp)
                        if symbol in df.index.get_level_values(0):
                            # Filter for this symbol
                            symbol_df = df.loc[symbol].reset_index()
                            for _, row in symbol_df.iterrows():
                                result.append({
                                    'timestamp': row['timestamp'],
                                    'open': float(row['open']),
                                    'high': float(row['high']),
                                    'low': float(row['low']),
                                    'close': float(row['close']),
                                    'volume': int(row['volume']),
                                })
                except (AttributeError, KeyError, IndexError) as e:
                    # BarSet might be empty or symbol not found - this is normal for some stocks
                    logger.debug(f"BarSet processing issue for {symbol}: {e} - may not have data on IEX feed")
                    # Fallback: try accessing as dict-like
                    try:
                        if hasattr(bars, symbol):
                            bar_list = getattr(bars, symbol)
                            for bar in bar_list:
                                result.append({
                                    'timestamp': bar.timestamp,
                                    'open': float(bar.open),
                                    'high': float(bar.high),
                                    'low': float(bar.low),
                                    'close': float(bar.close),
                                    'volume': int(bar.volume),
                                })
                    except Exception as e2:
                        logger.debug(f"Fallback also failed for {symbol}: {e2} - symbol may not be available")
            
            return result
            
        except APIError as e:
            logger.warning(f"API error fetching bars for {symbol}: {e}")
            return []
        except Exception as e:
            logger.warning(f"Unexpected error fetching bars for {symbol}: {e}")
            return []
    
    def get_current_price(self, symbol: str) -> Optional[float]:
        """
        Get current price for a symbol.
        
        Args:
            symbol: Stock symbol
            
        Returns:
            Current price or None if unavailable
        """
        try:
            # Get latest bar
            bars = self.get_bars(symbol, timeframe="1Min", limit=1)
            if bars:
                return bars[-1]['close']
            
            # Fallback: check position
            position = self.get_position(symbol)
            if position:
                return position['current_price']
                
            return None
        except Exception as e:
            logger.error(f"Error getting current price for {symbol}: {e}")
            return None


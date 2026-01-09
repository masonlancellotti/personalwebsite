"""Order management and position tracking."""
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime
from alpaca_client import AlpacaClient
from risk_manager import RiskManager
import logging

logger = logging.getLogger(__name__)


class OrderManager:
    """Manages order execution and position tracking."""
    
    def __init__(self, alpaca_client: AlpacaClient, risk_manager: RiskManager):
        """
        Initialize order manager.
        
        Args:
            alpaca_client: AlpacaClient instance
            risk_manager: RiskManager instance
        """
        self.alpaca_client = alpaca_client
        self.risk_manager = risk_manager
        self.open_orders: Dict[str, Dict[str, Any]] = {}
        logger.info("Order Manager initialized")
    
    def cleanup_filled_orders(self):
        """Remove filled/completed orders from open_orders tracking."""
        open_order_ids = set(self.open_orders.keys())
        api_orders = self.alpaca_client.get_open_orders()
        api_order_ids = {order['id'] for order in api_orders}
        
        # Remove orders that are no longer open in the API
        for order_id in list(open_order_ids):
            if order_id not in api_order_ids:
                symbol = self.open_orders[order_id].get('symbol', 'unknown')
                logger.debug(f"Removing filled order from tracking: {order_id} ({symbol})")
                self.open_orders.pop(order_id, None)
    
    def get_current_positions(self) -> List[Dict[str, Any]]:
        """
        Get all current positions.
        
        Returns:
            List of position dictionaries
        """
        return self.alpaca_client.get_positions()
    
    def get_position(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get position for a specific symbol.
        
        Args:
            symbol: Stock symbol
            
        Returns:
            Position dictionary or None
        """
        return self.alpaca_client.get_position(symbol)
    
    def has_pending_buy_order(self, symbol: str) -> bool:
        """
        Check if there's a pending buy order for a symbol.
        
        Args:
            symbol: Stock symbol
            
        Returns:
            True if there's a pending buy order, False otherwise
        """
        # Check Alpaca API for open orders
        open_orders = self.alpaca_client.get_open_orders(symbol=symbol)
        for order in open_orders:
            if order['side'].lower() == 'buy':
                return True
        
        # Also check our internal tracking
        for order_id, order_info in self.open_orders.items():
            if order_info.get('symbol') == symbol and order_info.get('side') == 'buy':
                return True
        
        return False
    
    def execute_buy_order(
        self,
        symbol: str,
        account_equity: float,
        buying_power: float,
        entry_price: Optional[float] = None,
        stop_loss_price: Optional[float] = None,
        max_position_size: Optional[float] = None
    ) -> Tuple[bool, Optional[str], int, str]:
        """
        Execute a buy order with risk management.
        
        Args:
            symbol: Stock symbol
            account_equity: Current account equity (for risk calculations)
            buying_power: Available cash/buying power (for position sizing)
            entry_price: Entry price (if None, uses market price)
            stop_loss_price: Stop loss price (optional)
            max_position_size: Override max position size (optional)
            
        Returns:
            Tuple of (success, order_id, shares, message)
        """
        # Get current price if not provided
        if entry_price is None:
            current_price = self.alpaca_client.get_current_price(symbol)
            if current_price is None:
                return False, None, 0, f"Could not get current price for {symbol}"
            entry_price = current_price
        
        # Check if already have position
        existing_position = self.get_position(symbol)
        if existing_position:
            logger.warning(f"Buy order blocked: Already have position in {symbol} ({existing_position['qty']} shares)")
            return False, None, 0, f"Already have position in {symbol}"
        
        # Check for pending buy orders
        if self.has_pending_buy_order(symbol):
            logger.warning(f"Buy order blocked: Pending buy order already exists for {symbol}")
            return False, None, 0, f"Pending buy order already exists for {symbol}"
        
        # Check if we have enough buying power
        if buying_power <= 0:
            return False, None, 0, f"Insufficient buying power: ${buying_power:.2f}"
        
        # Calculate position size
        shares = self.risk_manager.calculate_position_size(
            account_equity=account_equity,
            buying_power=buying_power,
            entry_price=entry_price,
            stop_loss_price=stop_loss_price,
            max_position_size=max_position_size
        )
        
        if shares <= 0:
            return False, None, 0, f"Invalid position size: {shares} shares"
        
        # Validate trade
        current_positions = self.get_current_positions()
        is_valid, reason = self.risk_manager.validate_trade(
            symbol=symbol,
            shares=shares,
            entry_price=entry_price,
            account_equity=account_equity,
            current_positions=current_positions,
            stop_loss_price=stop_loss_price
        )
        
        if not is_valid:
            return False, None, 0, reason
        
        # Submit order
        order_id = self.alpaca_client.submit_order(
            symbol=symbol,
            qty=shares,
            side="buy",
            order_type="market",
            stop_loss=stop_loss_price
        )
        
        if order_id:
            logger.info(
                f"Buy order submitted: {symbol} {shares} shares @ ${entry_price:.2f} "
                f"(order_id: {order_id})"
            )
            self.open_orders[order_id] = {
                'symbol': symbol,
                'side': 'buy',
                'shares': shares,
                'price': entry_price,
                'timestamp': datetime.now()
            }
            return True, order_id, shares, f"Buy order submitted: {shares} shares"
        else:
            return False, None, 0, "Failed to submit buy order"
    
    def execute_sell_order(
        self,
        symbol: str,
        qty: Optional[float] = None,
        order_type: str = "market",
        limit_price: Optional[float] = None
    ) -> Tuple[bool, Optional[str], str]:
        """
        Execute a sell order.
        
        Args:
            symbol: Stock symbol
            qty: Quantity to sell (if None, sells entire position)
            order_type: "market" or "limit"
            limit_price: Limit price (required for limit orders)
            
        Returns:
            Tuple of (success, order_id, message)
        """
        # Get current position
        position = self.get_position(symbol)
        if not position:
            return False, None, f"No position found for {symbol}"
        
        # Determine quantity
        if qty is None:
            qty = position['qty']
        else:
            qty = min(qty, position['qty'])  # Can't sell more than we have
        
        if qty <= 0:
            return False, None, f"Invalid quantity: {qty}"
        
        # Submit order
        order_id = self.alpaca_client.submit_order(
            symbol=symbol,
            qty=qty,
            side="sell",
            order_type=order_type,
            limit_price=limit_price
        )
        
        if order_id:
            logger.info(
                f"Sell order submitted: {symbol} {qty} shares "
                f"(order_id: {order_id})"
            )
            self.open_orders[order_id] = {
                'symbol': symbol,
                'side': 'sell',
                'shares': qty,
                'timestamp': datetime.now()
            }
            return True, order_id, f"Sell order submitted: {qty} shares"
        else:
            return False, None, "Failed to submit sell order"
    
    def close_position(self, symbol: str) -> Tuple[bool, Optional[str], str]:
        """
        Close entire position for a symbol.
        
        Args:
            symbol: Stock symbol
            
        Returns:
            Tuple of (success, order_id, message)
        """
        return self.execute_sell_order(symbol)
    
    def cancel_order(self, order_id: str) -> bool:
        """
        Cancel an open order.
        
        Args:
            order_id: Order ID to cancel
            
        Returns:
            True if successful, False otherwise
        """
        success = self.alpaca_client.cancel_order(order_id)
        if success:
            self.open_orders.pop(order_id, None)
        return success
    
    def get_portfolio_summary(self) -> Dict[str, Any]:
        """
        Get portfolio summary.
        
        Returns:
            Dictionary with portfolio information
        """
        positions = self.get_current_positions()
        account = self.alpaca_client.get_account()
        
        total_value = sum(p['market_value'] for p in positions)
        total_pl = sum(p['unrealized_pl'] for p in positions)
        
        return {
            'account_equity': account['equity'],
            'cash': account['cash'],
            'buying_power': account['buying_power'],
            'positions_count': len(positions),
            'total_positions_value': total_value,
            'total_unrealized_pl': total_pl,
            'positions': positions
        }


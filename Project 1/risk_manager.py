"""Risk management module."""
from typing import Dict, Any, Optional, Tuple
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class RiskManager:
    """Manages risk controls and position sizing."""
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize risk manager.
        
        Args:
            config: Risk configuration dictionary containing:
                - max_position_size: Maximum percentage of portfolio per position (default 0.1)
                - stop_loss_percent: Stop loss percentage (default 0.02)
                - max_daily_loss: Maximum daily loss percentage (default 0.05)
        """
        self.max_position_size = config.get('max_position_size', 0.1)
        self.stop_loss_percent = config.get('stop_loss_percent', 0.02)
        self.max_daily_loss = config.get('max_daily_loss', 0.05)
        
        # Track daily P&L
        self.daily_start_equity: Optional[float] = None
        self.daily_date: Optional[str] = None
        
        logger.info(
            f"Risk Manager initialized: max_position={self.max_position_size*100:.1f}%, "
            f"stop_loss={self.stop_loss_percent*100:.1f}%, "
            f"max_daily_loss={self.max_daily_loss*100:.1f}%"
        )
    
    def check_daily_loss_limit(
        self,
        account_equity: float,
        initial_equity: Optional[float] = None
    ) -> Tuple[bool, Optional[float]]:
        """
        Check if daily loss limit has been exceeded.
        
        Args:
            account_equity: Current account equity
            initial_equity: Starting equity for the day (if None, uses stored value)
            
        Returns:
            Tuple of (is_within_limit, daily_loss_percent)
        """
        today = datetime.now().strftime('%Y-%m-%d')
        
        # Reset if new day
        if self.daily_date != today:
            self.daily_start_equity = initial_equity or account_equity
            self.daily_date = today
            logger.info(f"New trading day: Starting equity = ${self.daily_start_equity:.2f}")
        
        # Calculate daily loss
        if self.daily_start_equity is None:
            self.daily_start_equity = account_equity
        
        daily_loss = self.daily_start_equity - account_equity
        daily_loss_percent = daily_loss / self.daily_start_equity if self.daily_start_equity > 0 else 0
        
        # Check limit
        within_limit = daily_loss_percent <= self.max_daily_loss
        
        if not within_limit:
            logger.warning(
                f"Daily loss limit exceeded: {daily_loss_percent*100:.2f}% "
                f"(limit: {self.max_daily_loss*100:.2f}%)"
            )
        else:
            logger.debug(f"Daily loss: {daily_loss_percent*100:.2f}% (limit: {self.max_daily_loss*100:.2f}%)")
        
        return within_limit, daily_loss_percent
    
    def calculate_position_size(
        self,
        account_equity: float,
        buying_power: float,
        entry_price: float,
        stop_loss_price: Optional[float] = None,
        max_position_size: Optional[float] = None
    ) -> int:
        """
        Calculate position size based on risk management rules.
        
        Args:
            account_equity: Total account equity (for risk calculations)
            buying_power: Available cash/buying power (for position sizing)
            entry_price: Entry price for the position
            stop_loss_price: Stop loss price (optional)
            max_position_size: Override max position size (optional)
            
        Returns:
            Number of shares (integer)
        """
        max_size = max_position_size or self.max_position_size
        
        # Maximum position value based on portfolio percentage of EQUITY
        # But capped by available BUYING POWER
        max_position_value_by_equity = account_equity * max_size
        max_position_value_by_cash = buying_power * max_size
        
        # Use the smaller of the two (can't exceed available cash)
        max_position_value = min(max_position_value_by_equity, buying_power)
        max_shares_by_size = max_position_value / entry_price
        
        # Calculate based on stop loss if provided (risk is % of equity)
        if stop_loss_price:
            risk_amount = account_equity * self.stop_loss_percent
            price_risk = abs(entry_price - stop_loss_price)
            
            if price_risk > 0:
                max_shares_by_risk = risk_amount / price_risk
                # Use the smaller (more conservative)
                shares = min(max_shares_by_size, max_shares_by_risk)
            else:
                shares = max_shares_by_size
        else:
            shares = max_shares_by_size
        
        # Round down to whole shares
        shares = int(max(0, shares))
        
        logger.debug(
            f"Position size: {shares} shares "
            f"(entry: ${entry_price:.2f}, max_value: ${max_position_value:.2f}, "
            f"equity: ${account_equity:.2f}, buying_power: ${buying_power:.2f})"
        )
        
        return shares
    
    def validate_trade(
        self,
        symbol: str,
        shares: int,
        entry_price: float,
        account_equity: float,
        current_positions: list,
        stop_loss_price: Optional[float] = None
    ) -> Tuple[bool, str]:
        """
        Validate if a trade should be executed based on risk rules.
        
        Args:
            symbol: Stock symbol
            shares: Number of shares to trade
            entry_price: Entry price
            account_equity: Current account equity
            current_positions: List of current positions
            stop_loss_price: Stop loss price (optional)
            
        Returns:
            Tuple of (is_valid, reason_message)
        """
        # Check daily loss limit
        within_limit, daily_loss = self.check_daily_loss_limit(account_equity)
        if not within_limit:
            return False, f"Daily loss limit exceeded: {daily_loss*100:.2f}%"
        
        # Check position size
        position_value = shares * entry_price
        position_percent = position_value / account_equity if account_equity > 0 else 0
        
        if position_percent > self.max_position_size:
            return False, f"Position size {position_percent*100:.2f}% exceeds max {self.max_position_size*100:.2f}%"
        
        # Check if already have position in this symbol
        existing_position = next(
            (p for p in current_positions if p.get('symbol') == symbol),
            None
        )
        if existing_position:
            return False, f"Already have position in {symbol}"
        
        # Check stop loss risk
        if stop_loss_price:
            risk_per_share = abs(entry_price - stop_loss_price)
            total_risk = risk_per_share * shares
            risk_percent = total_risk / account_equity if account_equity > 0 else 0
            
            if risk_percent > self.stop_loss_percent * 2:  # Allow up to 2x for volatility
                return False, f"Trade risk {risk_percent*100:.2f}% exceeds threshold"
        
        # Check minimum shares
        if shares <= 0:
            return False, "Invalid position size (shares <= 0)"
        
        return True, "Trade validated"
    
    def get_risk_summary(self, account_equity: float) -> Dict[str, Any]:
        """
        Get current risk summary.
        
        Args:
            account_equity: Current account equity
            
        Returns:
            Dictionary with risk metrics
        """
        within_limit, daily_loss = self.check_daily_loss_limit(account_equity)
        
        return {
            'daily_start_equity': self.daily_start_equity,
            'current_equity': account_equity,
            'daily_loss_percent': daily_loss * 100 if daily_loss else 0,
            'max_daily_loss_percent': self.max_daily_loss * 100,
            'within_daily_limit': within_limit,
            'max_position_size_percent': self.max_position_size * 100,
            'stop_loss_percent': self.stop_loss_percent * 100,
        }


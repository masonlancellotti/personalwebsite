"""Abstract base class for trading strategies."""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
import pandas as pd
import logging

logger = logging.getLogger(__name__)


class BaseStrategy(ABC):
    """Abstract base class for all trading strategies."""
    
    def __init__(self, params: Dict[str, Any]):
        """
        Initialize strategy.
        
        Args:
            params: Strategy parameters dictionary
        """
        self.params = params
        self.name = self.__class__.__name__
        logger.info(f"Initialized {self.name} strategy with params: {params}")
    
    @abstractmethod
    def generate_signal(
        self,
        data: pd.Series,
        current_position: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Generate trading signal based on current market data.
        
        Args:
            data: Series containing latest market data and indicators
            current_position: Current position for this symbol (if any)
            
        Returns:
            Signal string: "buy", "sell", or "hold"
        """
        pass
    
    @abstractmethod
    def calculate_stop_loss(
        self,
        entry_price: float,
        data: pd.Series,
        side: str = "buy"
    ) -> Optional[float]:
        """
        Calculate stop loss price.
        
        Args:
            entry_price: Entry price for the position
            data: Series containing latest market data and indicators
            side: "buy" or "sell"
            
        Returns:
            Stop loss price or None if not applicable
        """
        pass
    
    def calculate_position_size(
        self,
        account_equity: float,
        entry_price: float,
        max_position_size: float = 0.1,
        stop_loss_price: Optional[float] = None,
        risk_per_trade: float = 0.02
    ) -> float:
        """
        Calculate position size based on account equity and risk management.
        
        Args:
            account_equity: Total account equity
            entry_price: Entry price for the position
            max_position_size: Maximum percentage of portfolio per position (default 0.1 = 10%)
            stop_loss_price: Stop loss price for risk calculation
            risk_per_trade: Percentage of equity to risk per trade (default 0.02 = 2%)
            
        Returns:
            Number of shares to trade
        """
        # Maximum position value based on portfolio percentage
        max_position_value = account_equity * max_position_size
        
        # Calculate shares based on max position size
        max_shares_by_size = max_position_value / entry_price
        
        # If stop loss is provided, calculate shares based on risk
        if stop_loss_price:
            risk_amount = account_equity * risk_per_trade
            price_risk = abs(entry_price - stop_loss_price)
            if price_risk > 0:
                max_shares_by_risk = risk_amount / price_risk
                # Use the smaller of the two (most conservative)
                shares = min(max_shares_by_size, max_shares_by_risk)
            else:
                shares = max_shares_by_size
        else:
            shares = max_shares_by_size
        
        # Round down to whole shares
        shares = int(shares)
        
        logger.debug(
            f"Position size calculated: {shares} shares "
            f"(entry: ${entry_price:.2f}, equity: ${account_equity:.2f})"
        )
        
        return max(0, shares)
    
    def get_strategy_info(self) -> Dict[str, Any]:
        """
        Get strategy information.
        
        Returns:
            Dictionary with strategy information
        """
        return {
            'name': self.name,
            'params': self.params
        }


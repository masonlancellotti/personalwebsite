"""Mean reversion trading strategy."""
from typing import Dict, Any, Optional
import pandas as pd
import numpy as np
from .base_strategy import BaseStrategy
import logging

logger = logging.getLogger(__name__)


class MeanReversionStrategy(BaseStrategy):
    """
    Mean reversion trading strategy using Bollinger Bands and RSI.
    
    Buy signals:
    - Price touches or crosses below lower Bollinger Band
    - RSI is oversold (< oversold threshold)
    
    Sell signals:
    - Price touches or crosses above upper Bollinger Band
    - RSI is overbought (> overbought threshold)
    """
    
    def __init__(self, params: Dict[str, Any]):
        """
        Initialize mean reversion strategy.
        
        Args:
            params: Strategy parameters including:
                - rsi_period: RSI period (default 14)
                - rsi_oversold: RSI oversold threshold (default 30)
                - rsi_overbought: RSI overbought threshold (default 70)
                - bb_period: Bollinger Bands period (default 20)
                - bb_std: Bollinger Bands standard deviations (default 2)
        """
        super().__init__(params)
        self.rsi_period = params.get('rsi_period', 14)
        self.rsi_oversold = params.get('rsi_oversold', 30)
        self.rsi_overbought = params.get('rsi_overbought', 70)
        self.bb_period = params.get('bb_period', 20)
        self.bb_std = params.get('bb_std', 2)
    
    def generate_signal(
        self,
        data: pd.Series,
        current_position: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Generate trading signal based on mean reversion indicators.
        
        Args:
            data: Series with latest market data and indicators
            current_position: Current position (if any)
            
        Returns:
            "buy", "sell", or "hold"
        """
        # Extract values
        close = data.get('close', np.nan)
        rsi = data.get('rsi', np.nan)
        
        # Bollinger Bands columns from pandas-ta (try different naming patterns)
        # pandas-ta returns columns like: BBL_20_2.0, BBM_20_2.0, BBU_20_2.0
        # First try with .0 suffix
        bb_lower = data.get(f'BBL_{self.bb_period}_{self.bb_std}.0', None)
        bb_middle = data.get(f'BBM_{self.bb_period}_{self.bb_std}.0', None)
        bb_upper = data.get(f'BBU_{self.bb_period}_{self.bb_std}.0', None)
        
        # Try alternative format (without .0) if first attempt failed
        if bb_lower is None or pd.isna(bb_lower):
            bb_lower = data.get(f'BBL_{self.bb_period}_{self.bb_std}', np.nan)
            bb_middle = data.get(f'BBM_{self.bb_period}_{self.bb_std}', np.nan)
            bb_upper = data.get(f'BBU_{self.bb_period}_{self.bb_std}', np.nan)
        
        # Check for valid data
        if any(pd.isna([close, rsi, bb_lower, bb_upper])):
            logger.warning("Insufficient data for signal generation")
            return "hold"
        
        # Initialize signal score
        buy_signals = 0
        sell_signals = 0
        
        # Bollinger Band signals
        if close <= bb_lower:
            # Price at or below lower band - potential buy
            buy_signals += 1
        elif close >= bb_upper:
            # Price at or above upper band - potential sell
            sell_signals += 1
        
        # RSI signals
        if rsi < self.rsi_oversold:
            buy_signals += 1
        elif rsi > self.rsi_overbought:
            sell_signals += 1
        
        # Generate signal
        if current_position is None:
            # No position: look for buy signals
            # Require BOTH Bollinger Band AND RSI signals for stronger confirmation
            if buy_signals >= 2:
                logger.info(
                    f"BUY signal: Close=${close:.2f}, "
                    f"BB Lower=${bb_lower:.2f}, RSI={rsi:.2f} (signals: {buy_signals})"
                )
                return "buy"
            else:
                return "hold"
        else:
            # Have position: look for sell signals
            # Require BOTH Bollinger Band AND RSI signals, OR strong overbought with profit
            entry_price = current_position.get('avg_entry_price', close) if current_position else close
            profit_pct = (close - entry_price) / entry_price if entry_price and entry_price > 0 else 0
            
            if sell_signals >= 2:
                logger.info(
                    f"SELL signal: Close=${close:.2f}, "
                    f"BB Upper=${bb_upper:.2f}, RSI={rsi:.2f} (signals: {sell_signals}, profit: {profit_pct*100:.2f}%)"
                )
                return "sell"
            elif sell_signals >= 1 and (rsi > 75 or profit_pct > 0.03):  # Strong overbought OR 3%+ profit
                logger.info(
                    f"SELL signal (strong): Close=${close:.2f}, RSI={rsi:.2f}, "
                    f"profit: {profit_pct*100:.2f}%"
                )
                return "sell"
            elif close >= bb_middle and profit_pct > 0.02:  # Take profit at middle band if 2%+ profit
                logger.info(
                    f"SELL signal (take profit): Close=${close:.2f} >= BB Middle=${bb_middle:.2f}, "
                    f"profit: {profit_pct*100:.2f}%"
                )
                return "sell"
            else:
                return "hold"
    
    def calculate_stop_loss(
        self,
        entry_price: float,
        data: pd.Series,
        side: str = "buy"
    ) -> Optional[float]:
        """
        Calculate stop loss based on Bollinger Band width.
        
        Args:
            entry_price: Entry price
            data: Latest market data
            side: "buy" or "sell"
            
        Returns:
            Stop loss price
        """
        # Use Bollinger Band width for dynamic stop loss
        bb_lower = data.get(f'BBL_{self.bb_period}_{self.bb_std}.0', None)
        bb_upper = data.get(f'BBU_{self.bb_period}_{self.bb_std}.0', None)
        
        # Try alternative format if needed
        if bb_lower is None or pd.isna(bb_lower):
            bb_lower = data.get(f'BBL_{self.bb_period}_{self.bb_std}', np.nan)
            bb_upper = data.get(f'BBU_{self.bb_period}_{self.bb_std}', np.nan)
        
        if not pd.isna(bb_lower) and not pd.isna(bb_upper):
            # For buys, stop loss slightly below lower band
            if side == "buy":
                stop_loss = bb_lower * 0.98  # 2% below lower band
            else:  # sell (short)
                stop_loss = bb_upper * 1.02  # 2% above upper band
        else:
            # Fallback to percentage-based stop loss
            stop_loss_percent = 0.02  # 2%
            if side == "buy":
                stop_loss = entry_price * (1 - stop_loss_percent)
            else:
                stop_loss = entry_price * (1 + stop_loss_percent)
        
        logger.debug(f"Stop loss calculated: ${stop_loss:.2f} for entry at ${entry_price:.2f}")
        return stop_loss


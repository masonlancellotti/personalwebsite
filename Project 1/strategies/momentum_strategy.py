"""Momentum-based trading strategy."""
from typing import Dict, Any, Optional
import pandas as pd
import numpy as np
from .base_strategy import BaseStrategy
import logging

logger = logging.getLogger(__name__)


class MomentumStrategy(BaseStrategy):
    """
    Momentum-based trading strategy using RSI, MACD, and moving averages.
    
    Buy signals:
    - RSI oversold recovery (RSI < oversold then crosses above)
    - MACD bullish crossover (MACD crosses above signal)
    - Price above short-term moving average
    
    Sell signals:
    - RSI overbought (RSI > overbought)
    - MACD bearish crossover (MACD crosses below signal)
    - Price below short-term moving average
    """
    
    def __init__(self, params: Dict[str, Any]):
        """
        Initialize momentum strategy.
        
        Args:
            params: Strategy parameters including:
                - rsi_period: RSI period (default 14)
                - rsi_oversold: RSI oversold threshold (default 30)
                - rsi_overbought: RSI overbought threshold (default 70)
                - macd_fast: MACD fast period (default 12)
                - macd_slow: MACD slow period (default 26)
                - macd_signal: MACD signal period (default 9)
                - sma_short: Short-term SMA period (default 50)
                - sma_long: Long-term SMA period (default 200)
        """
        super().__init__(params)
        self.rsi_period = params.get('rsi_period', 14)
        self.rsi_oversold = params.get('rsi_oversold', 30)
        self.rsi_overbought = params.get('rsi_overbought', 70)
        self.macd_fast = params.get('macd_fast', 12)
        self.macd_slow = params.get('macd_slow', 26)
        self.macd_signal = params.get('macd_signal', 9)
        self.sma_short = params.get('sma_short', 50)
        self.sma_long = params.get('sma_long', 200)
    
    def generate_signal(
        self,
        data: pd.Series,
        current_position: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Generate trading signal based on momentum indicators.
        
        Args:
            data: Series with latest market data and indicators
            current_position: Current position (if any)
            
        Returns:
            "buy", "sell", or "hold"
        """
        # Extract values
        close = data.get('close', np.nan)
        rsi = data.get('rsi', np.nan)
        
        # MACD columns from pandas-ta: MACD_12_26_9, MACDs_12_26_9, MACDh_12_26_9
        macd_col = f'MACD_{self.macd_fast}_{self.macd_slow}_{self.macd_signal}'
        macd_signal_col = f'MACDs_{self.macd_fast}_{self.macd_slow}_{self.macd_signal}'
        macd_hist_col = f'MACDh_{self.macd_fast}_{self.macd_slow}_{self.macd_signal}'
        
        macd = data.get(macd_col, np.nan)
        macd_signal = data.get(macd_signal_col, np.nan)
        macd_hist = data.get(macd_hist_col, np.nan)
        sma_short = data.get(f'sma_{self.sma_short}', np.nan)
        sma_long = data.get(f'sma_{self.sma_long}', np.nan)
        
        # Check for valid data
        if any(pd.isna([close, rsi, macd, macd_signal, sma_short])):
            logger.warning("Insufficient data for signal generation")
            return "hold"
        
        # Initialize signal score
        buy_signals = 0
        sell_signals = 0
        
        # RSI signals
        if rsi < self.rsi_oversold:
            buy_signals += 1
        elif rsi > self.rsi_overbought:
            sell_signals += 1
        
        # MACD signals (loosened: only require crossover, not histogram sign)
        if not pd.isna(macd) and not pd.isna(macd_signal):
            if macd > macd_signal:  # MACD above signal (bullish crossover)
                buy_signals += 1
            elif macd < macd_signal:  # MACD below signal (bearish crossover)
                sell_signals += 1
        
        # Moving average signals
        if not pd.isna(sma_short) and not pd.isna(sma_long):
            if close > sma_short and sma_short > sma_long:  # Uptrend
                buy_signals += 1
            elif close < sma_short:  # Below short-term MA
                sell_signals += 1
        
        # Generate signal
        if current_position is None:
            # No position: look for buy signals
            # Require at least 2 buy signals for stronger confirmation
            if buy_signals >= 2:
                logger.info(f"BUY signal: RSI={rsi:.2f}, MACD_hist={macd_hist:.4f}, Close vs SMA={close:.2f} vs {sma_short:.2f} (signals: {buy_signals})")
                return "buy"
            else:
                return "hold"
        else:
            # Have position: look for sell signals
            # Require at least 2 sell signals OR strong overbought condition
            if sell_signals >= 2 or (rsi > 75 and sell_signals >= 1):
                logger.info(f"SELL signal: RSI={rsi:.2f}, MACD_hist={macd_hist:.4f}, Close vs SMA={close:.2f} vs {sma_short:.2f} (signals: {sell_signals})")
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
        Calculate stop loss based on ATR or percentage.
        
        Args:
            entry_price: Entry price
            data: Latest market data
            side: "buy" or "sell"
            
        Returns:
            Stop loss price
        """
        # Use a fixed percentage stop loss (can be enhanced with ATR)
        stop_loss_percent = 0.02  # 2% default
        
        if side == "buy":
            stop_loss = entry_price * (1 - stop_loss_percent)
        else:  # sell (short)
            stop_loss = entry_price * (1 + stop_loss_percent)
        
        logger.debug(f"Stop loss calculated: ${stop_loss:.2f} for entry at ${entry_price:.2f}")
        return stop_loss


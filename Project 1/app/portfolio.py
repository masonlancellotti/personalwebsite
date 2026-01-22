"""
Portfolio management module.

Handles position sizing, risk management, and trade execution.
"""

import logging
from datetime import datetime
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass, field
from enum import Enum
import math

from alpaca.trading.requests import MarketOrderRequest, LimitOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce

from config import get_config, RiskConfig
from alpaca_clients import get_client_manager, get_trading_client
from utils import get_logger, round_shares, safe_divide, clamp

logger = get_logger("portfolio")


class PositionSide(Enum):
    """Position side."""
    LONG = "long"
    SHORT = "short"


@dataclass
class Position:
    """
    Represents an open position with risk management state.
    """
    symbol: str
    side: PositionSide
    shares: int
    entry_price: float
    entry_date: datetime
    
    # Stop loss
    hard_stop: float
    
    # Trailing take profit
    trailing_active: bool = False
    peak_price: Optional[float] = None  # For longs
    trough_price: Optional[float] = None  # For shorts
    trailing_stop: Optional[float] = None
    
    # Metadata
    atr_at_entry: Optional[float] = None
    regime_at_entry: Optional[str] = None
    
    # Time tracking for time stop
    entry_day_index: int = 0  # Day index at entry (for backtest)
    
    @property
    def is_long(self) -> bool:
        return self.side == PositionSide.LONG
    
    @property
    def is_short(self) -> bool:
        return self.side == PositionSide.SHORT
    
    def current_pnl(self, current_price: float) -> float:
        """Calculate current P&L."""
        if self.is_long:
            return (current_price - self.entry_price) * self.shares
        else:
            return (self.entry_price - current_price) * self.shares
    
    def current_pnl_pct(self, current_price: float) -> float:
        """Calculate current P&L percentage."""
        if self.is_long:
            return (current_price - self.entry_price) / self.entry_price
        else:
            return (self.entry_price - current_price) / self.entry_price
    
    def holding_days(self, current_day_index: int) -> int:
        """Calculate number of days held."""
        return current_day_index - self.entry_day_index


@dataclass
class TradeRecord:
    """Record of a completed trade."""
    symbol: str
    side: str  # "long" or "short"
    action: str  # "entry" or "exit"
    shares: int
    price: float
    timestamp: datetime
    fee: float
    reason: str
    pnl: Optional[float] = None  # Only for exits


class PortfolioManager:
    """
    Manages portfolio positions, sizing, and risk.
    
    Features:
    - ATR-based position sizing
    - Hard stop loss
    - Trailing take-profit
    - Exposure limits
    """
    
    def __init__(
        self,
        initial_cash: float = 100000.0,
        config: Optional[RiskConfig] = None,
        fee_rate: float = 0.001
    ):
        """
        Initialize portfolio manager.
        
        Args:
            initial_cash: Starting cash balance.
            config: Risk configuration.
            fee_rate: Fee rate per side (e.g., 0.001 = 0.1%).
        """
        self._config = config or get_config().risk
        self._fee_rate = fee_rate
        
        # Portfolio state
        self.cash: float = initial_cash
        self.positions: Dict[str, Position] = {}
        self.trade_history: List[TradeRecord] = []
        self.equity_history: List[Tuple[datetime, float]] = []
        
        # Initial equity
        self._initial_equity = initial_cash
        
        # Hard stop cooldown tracking: symbol -> datetime of last hard stop
        self.last_hard_stop_dt: Dict[str, datetime] = {}
    
    @property
    def equity(self) -> float:
        """Calculate current equity at entry prices (placeholder for mark-to-market)."""
        # In backtest, prefer mark_to_market() with current prices
        position_value = 0.0
        for pos in self.positions.values():
            if pos.is_long:
                position_value += pos.shares * pos.entry_price
            else:
                # Short: liability at entry price
                position_value -= pos.shares * pos.entry_price
        return self.cash + position_value
    
    def mark_to_market(self, prices: Dict[str, float]) -> float:
        """
        Calculate equity with current prices.
        
        Args:
            prices: Dict mapping symbol to current price.
        
        Returns:
            Current equity value.
        """
        position_value = 0.0
        for symbol, pos in self.positions.items():
            price = prices.get(symbol, pos.entry_price)
            if pos.is_long:
                # Long: we own shares worth current price
                position_value += pos.shares * price
            else:
                # Short: we owe shares at current price (liability)
                # Cash already includes proceeds from short sale,
                # so we subtract the cost to cover
                position_value -= pos.shares * price
        
        return self.cash + position_value
    
    def gross_exposure(self, prices: Dict[str, float]) -> float:
        """
        Calculate gross exposure (sum of absolute position values).
        
        Args:
            prices: Dict mapping symbol to current price.
        
        Returns:
            Gross exposure as dollar amount.
        """
        return sum(
            pos.shares * prices.get(symbol, pos.entry_price)
            for symbol, pos in self.positions.items()
        )
    
    def gross_exposure_pct(self, prices: Dict[str, float]) -> float:
        """
        Calculate gross exposure as percentage of equity.
        
        Args:
            prices: Dict mapping symbol to current price.
        
        Returns:
            Gross exposure percentage.
        """
        equity = self.mark_to_market(prices)
        if equity <= 0:
            return 1.0
        return self.gross_exposure(prices) / equity
    
    def calculate_position_size(
        self,
        symbol: str,
        side: PositionSide,
        entry_price: float,
        atr: float,
        prices: Dict[str, float]
    ) -> int:
        """
        Calculate position size using ATR-based risk sizing.
        
        Args:
            symbol: Stock ticker symbol.
            side: Long or short.
            entry_price: Expected entry price.
            atr: Current ATR value.
            prices: Current prices for exposure calculation.
        
        Returns:
            Number of shares to trade.
        """
        equity = self.mark_to_market(prices)
        
        # Risk per trade
        risk_dollars = equity * (self._config.risk_per_trade_pct / 100)
        
        # Stop distance
        stop_distance = atr * self._config.atr_multiplier
        if stop_distance <= 0:
            logger.warning(f"Invalid stop distance for {symbol}: {stop_distance}")
            return 0
        
        # Raw share count based on risk
        raw_shares = risk_dollars / stop_distance
        
        # Cap by max position size
        max_position_value = equity * (self._config.max_position_pct / 100)
        max_shares_by_value = max_position_value / entry_price
        
        # Cap by remaining exposure
        current_exposure = self.gross_exposure(prices)
        max_total_exposure = equity * (self._config.max_gross_exposure_pct / 100)
        remaining_exposure = max_total_exposure - current_exposure
        max_shares_by_exposure = remaining_exposure / entry_price
        
        # Take minimum of all caps
        shares = min(raw_shares, max_shares_by_value, max_shares_by_exposure)
        shares = max(0, round_shares(shares))
        
        if shares == 0:
            logger.debug(f"Position size 0 for {symbol}: risk_shares={raw_shares:.0f}, "
                        f"value_cap={max_shares_by_value:.0f}, exposure_cap={max_shares_by_exposure:.0f}")
        
        return shares
    
    def calculate_hard_stop(
        self,
        entry_price: float,
        side: PositionSide,
        atr: Optional[float] = None
    ) -> float:
        """
        Calculate hard stop price using ATR-aware distance.
        
        Stop distance = max(pct_stop, atr_stop)
        
        Args:
            entry_price: Entry price.
            side: Long or short.
            atr: ATR value for ATR-based stop (optional).
        
        Returns:
            Hard stop price.
        """
        # Percentage-based stop distance
        pct_stop_distance = entry_price * self._config.hard_stop_pct
        
        # ATR-based stop distance
        atr_stop_distance = 0.0
        if atr is not None and atr > 0:
            atr_stop_distance = atr * self._config.stop_atr_mult
        
        # Use the larger of the two
        stop_distance = max(pct_stop_distance, atr_stop_distance)
        
        if side == PositionSide.LONG:
            return entry_price - stop_distance
        else:
            return entry_price + stop_distance
    
    def open_position(
        self,
        symbol: str,
        side: PositionSide,
        shares: int,
        price: float,
        timestamp: datetime,
        atr: Optional[float] = None,
        regime: Optional[str] = None,
        day_index: int = 0
    ) -> Tuple[bool, str]:
        """
        Open a new position.
        
        Args:
            symbol: Stock ticker symbol.
            side: Long or short.
            shares: Number of shares.
            price: Entry price.
            timestamp: Entry timestamp.
            atr: ATR at entry (for ATR-aware stop).
            regime: Market regime at entry.
            day_index: Current day index (for time stop tracking).
        
        Returns:
            Tuple of (success, message).
        """
        if shares <= 0:
            return False, "Invalid share count"
        
        if symbol in self.positions:
            return False, f"Position already exists for {symbol}"
        
        # Calculate costs
        trade_value = shares * price
        fee = trade_value * self._fee_rate
        
        if side == PositionSide.LONG:
            cost = trade_value + fee
            if cost > self.cash:
                return False, f"Insufficient cash: need {cost:.2f}, have {self.cash:.2f}"
            self.cash -= cost
        else:
            # Short: receive cash minus fees (simplified)
            self.cash += trade_value - fee
        
        # Create position with ATR-aware stop
        position = Position(
            symbol=symbol,
            side=side,
            shares=shares,
            entry_price=price,
            entry_date=timestamp,
            hard_stop=self.calculate_hard_stop(price, side, atr),
            atr_at_entry=atr,
            regime_at_entry=regime,
            entry_day_index=day_index
        )
        
        # Initialize peak/trough for trailing
        if side == PositionSide.LONG:
            position.peak_price = price
        else:
            position.trough_price = price
        
        self.positions[symbol] = position
        
        # Record trade
        self.trade_history.append(TradeRecord(
            symbol=symbol,
            side=side.value,
            action="entry",
            shares=shares,
            price=price,
            timestamp=timestamp,
            fee=fee,
            reason="signal"
        ))
        
        logger.info(f"OPEN {side.value.upper()} {symbol}: {shares} @ {price:.2f}, "
                   f"stop={position.hard_stop:.2f}, fee={fee:.2f}")
        
        return True, "Position opened"
    
    def close_position(
        self,
        symbol: str,
        price: float,
        timestamp: datetime,
        reason: str = "exit"
    ) -> Tuple[bool, str, Optional[float]]:
        """
        Close an existing position.
        
        Args:
            symbol: Stock ticker symbol.
            price: Exit price.
            timestamp: Exit timestamp.
            reason: Exit reason.
        
        Returns:
            Tuple of (success, message, pnl).
        """
        if symbol not in self.positions:
            return False, f"No position for {symbol}", None
        
        position = self.positions[symbol]
        shares = position.shares
        
        # Calculate trade value and fee
        trade_value = shares * price
        fee = trade_value * self._fee_rate
        
        # Calculate P&L
        if position.is_long:
            gross_pnl = (price - position.entry_price) * shares
            self.cash += trade_value - fee
        else:
            gross_pnl = (position.entry_price - price) * shares
            # Cover short: pay to buy back
            self.cash -= trade_value + fee
        
        net_pnl = gross_pnl - fee - (position.shares * position.entry_price * self._fee_rate)
        
        # Record trade
        self.trade_history.append(TradeRecord(
            symbol=symbol,
            side=position.side.value,
            action="exit",
            shares=shares,
            price=price,
            timestamp=timestamp,
            fee=fee,
            reason=reason,
            pnl=net_pnl
        ))
        
        # Track hard stop for cooldown
        if reason == "hard_stop":
            self.last_hard_stop_dt[symbol] = timestamp
        
        # Remove position
        del self.positions[symbol]
        
        logger.info(f"CLOSE {position.side.value.upper()} {symbol}: {shares} @ {price:.2f}, "
                   f"P&L={net_pnl:.2f} ({reason})")
        
        return True, f"Position closed: {reason}", net_pnl
    
    def update_trailing_stops(
        self,
        prices: Dict[str, float]
    ) -> List[str]:
        """
        Update trailing stop tracking.
        
        Args:
            prices: Current prices.
        
        Returns:
            List of symbols with triggered trailing stops.
        """
        triggers = []
        activation_pct = self._config.trailing_activation_pct / 100
        trail_pct = self._config.trailing_stop_pct / 100
        
        for symbol, pos in self.positions.items():
            price = prices.get(symbol, pos.entry_price)
            
            if pos.is_long:
                # Long: track peak, activate if +X% from entry
                current_gain = (price - pos.entry_price) / pos.entry_price
                
                if not pos.trailing_active and current_gain >= activation_pct:
                    pos.trailing_active = True
                    pos.peak_price = price
                    pos.trailing_stop = price * (1 - trail_pct)
                    logger.debug(f"Trailing activated for {symbol} LONG at {price:.2f}")
                
                elif pos.trailing_active:
                    if price > pos.peak_price:
                        pos.peak_price = price
                        pos.trailing_stop = price * (1 - trail_pct)
                    
                    if price <= pos.trailing_stop:
                        triggers.append(symbol)
            
            else:
                # Short: track trough, activate if -X% from entry (favorable)
                current_gain = (pos.entry_price - price) / pos.entry_price
                
                if not pos.trailing_active and current_gain >= activation_pct:
                    pos.trailing_active = True
                    pos.trough_price = price
                    pos.trailing_stop = price * (1 + trail_pct)
                    logger.debug(f"Trailing activated for {symbol} SHORT at {price:.2f}")
                
                elif pos.trailing_active:
                    if price < pos.trough_price:
                        pos.trough_price = price
                        pos.trailing_stop = price * (1 + trail_pct)
                    
                    if price >= pos.trailing_stop:
                        triggers.append(symbol)
        
        return triggers
    
    def check_hard_stops(
        self,
        prices: Dict[str, float]
    ) -> List[str]:
        """
        Check hard stop losses.
        
        Args:
            prices: Current prices.
        
        Returns:
            List of symbols with triggered hard stops.
        """
        triggers = []
        
        for symbol, pos in self.positions.items():
            price = prices.get(symbol, pos.entry_price)
            
            if pos.is_long and price <= pos.hard_stop:
                triggers.append(symbol)
            elif pos.is_short and price >= pos.hard_stop:
                triggers.append(symbol)
        
        return triggers
    
    def check_time_stops(
        self,
        current_day_index: int,
        prices: Dict[str, float]
    ) -> List[str]:
        """
        Check time-based stops (positions held too long without profit).
        
        Args:
            current_day_index: Current trading day index.
            prices: Current prices.
        
        Returns:
            List of symbols with triggered time stops.
        """
        if not self._config.time_stop_enabled:
            return []
        
        triggers = []
        max_hold = self._config.max_hold_days
        
        for symbol, pos in self.positions.items():
            hold_days = pos.holding_days(current_day_index)
            
            if hold_days >= max_hold:
                # Only trigger if not profitable
                price = prices.get(symbol, pos.entry_price)
                pnl = pos.current_pnl(price)
                
                if pnl <= 0:
                    triggers.append(symbol)
                    logger.debug(f"Time stop triggered for {symbol}: hold_days={hold_days}, pnl={pnl:.2f}")
        
        return triggers
    
    def record_equity(self, timestamp: datetime, prices: Dict[str, float]) -> float:
        """
        Record equity at a point in time.
        
        Args:
            timestamp: Current timestamp.
            prices: Current prices.
        
        Returns:
            Current equity value.
        """
        equity = self.mark_to_market(prices)
        self.equity_history.append((timestamp, equity))
        return equity
    
    def get_trade_df(self) -> "pd.DataFrame":
        """
        Get trade history as DataFrame.
        
        Returns:
            DataFrame of trade records.
        """
        import pandas as pd
        
        records = []
        for trade in self.trade_history:
            records.append({
                'timestamp': trade.timestamp,
                'symbol': trade.symbol,
                'side': trade.side,
                'action': trade.action,
                'shares': trade.shares,
                'price': trade.price,
                'fee': trade.fee,
                'reason': trade.reason,
                'pnl': trade.pnl
            })
        
        return pd.DataFrame(records)
    
    def get_equity_df(self) -> "pd.DataFrame":
        """
        Get equity history as DataFrame.
        
        Returns:
            DataFrame with timestamp and equity columns.
        """
        import pandas as pd
        
        return pd.DataFrame(self.equity_history, columns=['timestamp', 'equity'])


class LivePortfolioManager:
    """
    Portfolio manager for live/paper trading via Alpaca.
    """
    
    def __init__(self, config: Optional[RiskConfig] = None):
        """
        Initialize live portfolio manager.
        
        Args:
            config: Risk configuration.
        """
        self._config = config or get_config().risk
        self._client_manager = get_client_manager()
        
    def get_account_equity(self) -> float:
        """Get current account equity."""
        account = self._client_manager.get_account()
        return float(account.equity)
    
    def get_positions(self) -> Dict[str, dict]:
        """Get current positions."""
        positions = self._client_manager.get_positions()
        return {
            p.symbol: {
                'qty': int(p.qty),
                'side': 'long' if int(p.qty) > 0 else 'short',
                'market_value': float(p.market_value),
                'avg_entry_price': float(p.avg_entry_price),
                'unrealized_pl': float(p.unrealized_pl),
                'unrealized_plpc': float(p.unrealized_plpc)
            }
            for p in positions
        }
    
    def place_order(
        self,
        symbol: str,
        side: str,  # "buy" or "sell"
        qty: int,
        order_type: str = "market"
    ) -> Tuple[bool, str, Optional[str]]:
        """
        Place an order via Alpaca.
        
        Args:
            symbol: Stock ticker.
            side: "buy" or "sell".
            qty: Number of shares.
            order_type: "market" or "limit".
        
        Returns:
            Tuple of (success, message, order_id).
        """
        try:
            client = self._client_manager.trading_client
            
            # Check shortability for sells
            if side == "sell":
                positions = self.get_positions()
                if symbol not in positions:
                    # This is a new short
                    if not self._client_manager.is_shortable(symbol):
                        return False, f"{symbol} is not shortable", None
            
            order_side = OrderSide.BUY if side == "buy" else OrderSide.SELL
            
            order_request = MarketOrderRequest(
                symbol=symbol,
                qty=qty,
                side=order_side,
                time_in_force=TimeInForce.DAY
            )
            
            order = client.submit_order(order_request)
            
            logger.info(f"Order placed: {side.upper()} {qty} {symbol}, order_id={order.id}")
            return True, f"Order submitted: {order.id}", str(order.id)
            
        except Exception as e:
            logger.error(f"Order failed for {symbol}: {e}")
            return False, str(e), None
    
    def close_position(self, symbol: str) -> Tuple[bool, str]:
        """
        Close a position via Alpaca.
        
        Args:
            symbol: Stock ticker.
        
        Returns:
            Tuple of (success, message).
        """
        try:
            client = self._client_manager.trading_client
            client.close_position(symbol)
            logger.info(f"Closed position: {symbol}")
            return True, f"Position closed: {symbol}"
        except Exception as e:
            logger.error(f"Failed to close {symbol}: {e}")
            return False, str(e)


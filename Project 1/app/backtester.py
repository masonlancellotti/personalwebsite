"""
Backtesting engine with realistic cost modeling.

Simulates trading strategy performance on historical data.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple, Any
from dataclasses import dataclass

import pandas as pd
import numpy as np

from config import get_config, BacktestConfig
from data_provider import get_data_provider, fetch_universe_bars
from strategy import TradingStrategy, TradeSignal, SignalType
from portfolio import PortfolioManager, PositionSide
from indicators import compute_indicators_for_df
from regime_hmm import get_regime_detector, MarketRegime
from universe import get_universe_with_proxy
from utils import get_logger, utc_now, ensure_utc

logger = get_logger("backtester")


@dataclass
class BacktestResult:
    """Container for backtest results."""
    start_date: datetime
    end_date: datetime
    initial_capital: float
    final_equity: float
    total_return: float
    total_return_pct: float
    max_drawdown: float
    max_drawdown_pct: float
    sharpe_ratio: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    avg_win: float
    avg_loss: float
    profit_factor: float
    equity_curve: pd.DataFrame
    trades: pd.DataFrame
    
    def to_dict(self) -> dict:
        """Convert to dictionary (excludes DataFrames)."""
        return {
            'start_date': self.start_date.isoformat(),
            'end_date': self.end_date.isoformat(),
            'initial_capital': self.initial_capital,
            'final_equity': self.final_equity,
            'total_return': self.total_return,
            'total_return_pct': self.total_return_pct,
            'max_drawdown': self.max_drawdown,
            'max_drawdown_pct': self.max_drawdown_pct,
            'sharpe_ratio': self.sharpe_ratio,
            'total_trades': self.total_trades,
            'winning_trades': self.winning_trades,
            'losing_trades': self.losing_trades,
            'win_rate': self.win_rate,
            'avg_win': self.avg_win,
            'avg_loss': self.avg_loss,
            'profit_factor': self.profit_factor
        }


class Backtester:
    """
    Event-driven backtesting engine.
    
    Features:
    - Realistic fee/slippage modeling
    - No lookahead bias (signals from t-1, fills at t open)
    - Full position tracking and risk management
    - Detailed trade logging and metrics
    """
    
    def __init__(
        self,
        initial_capital: Optional[float] = None,
        fee_rate: Optional[float] = None,
        config: Optional[BacktestConfig] = None
    ):
        """
        Initialize backtester.
        
        Args:
            initial_capital: Starting capital.
            fee_rate: Fee rate per side.
            config: Backtest configuration.
        """
        self._config = config or get_config().backtest
        self._initial_capital = initial_capital or self._config.initial_capital
        self._fee_rate = fee_rate or self._config.fee_rate
        self._min_bars = self._config.min_symbol_bars
        
        self._portfolio: Optional[PortfolioManager] = None
        self._strategy: Optional[TradingStrategy] = None
        self._symbol_data: Dict[str, pd.DataFrame] = {}
        self._result: Optional[BacktestResult] = None
        
    def _prepare_data(
        self,
        symbols: List[str],
        start: datetime,
        end: datetime
    ) -> Dict[str, pd.DataFrame]:
        """
        Prepare data for backtesting.
        
        Args:
            symbols: List of symbols to include.
            start: Backtest start date.
            end: Backtest end date.
        
        Returns:
            Dict mapping symbol to OHLCV DataFrame with indicators.
        """
        logger.info(f"Preparing data for {len(symbols)} symbols")
        
        # Ensure UTC-aware datetimes
        start = ensure_utc(start)
        end = ensure_utc(end)
        
        # Fetch bars with extra history for indicator warmup
        lookback_days = int(self._min_bars * 1.5) + (end - start).days
        provider = get_data_provider()
        
        bars = provider.fetch_bars(
            symbols,
            start - timedelta(days=int(self._min_bars * 1.5)),
            end
        )
        
        result = {}
        for symbol, df in bars.items():
            if df.empty or len(df) < self._min_bars:
                logger.debug(f"Skipping {symbol}: insufficient data ({len(df)} bars)")
                continue
            
            # Compute indicators
            df = compute_indicators_for_df(df)
            result[symbol] = df.sort_values('timestamp').reset_index(drop=True)
        
        logger.info(f"Prepared {len(result)} symbols with sufficient data")
        return result
    
    def _get_prices_at_date(
        self,
        date: datetime,
        price_type: str = "close"
    ) -> Dict[str, float]:
        """
        Get prices for all symbols at a date.
        
        Args:
            date: Target date.
            price_type: 'open', 'close', 'high', 'low'.
        
        Returns:
            Dict mapping symbol to price.
        """
        prices = {}
        for symbol, df in self._symbol_data.items():
            mask = df['timestamp'].dt.date == date.date()
            if mask.any():
                prices[symbol] = float(df.loc[mask, price_type].iloc[0])
        return prices
    
    def _get_data_through_date(
        self,
        symbol: str,
        date: datetime
    ) -> pd.DataFrame:
        """
        Get data for a symbol through a date (no lookahead).
        
        Args:
            symbol: Stock ticker.
            date: Cutoff date.
        
        Returns:
            DataFrame with data through date (inclusive).
        """
        df = self._symbol_data.get(symbol)
        if df is None:
            return pd.DataFrame()
        
        mask = df['timestamp'].dt.date <= date.date()
        return df[mask].copy()
    
    def _process_exits(
        self,
        date: datetime,
        prices: Dict[str, float]
    ) -> None:
        """
        Process exit signals (stops).
        
        Args:
            date: Current date.
            prices: Current prices (close for stop checks).
        """
        # 1) Check hard stops
        hard_stop_triggers = self._portfolio.check_hard_stops(prices)
        for symbol in hard_stop_triggers:
            price = prices.get(symbol, 0)
            # Apply slippage (adverse for stops)
            pos = self._portfolio.positions.get(symbol)
            if pos:
                exit_price = price * (1 - self._fee_rate) if pos.is_long else price * (1 + self._fee_rate)
                self._portfolio.close_position(symbol, exit_price, date, "hard_stop")
        
        # 2) Check trailing stops
        trail_triggers = self._portfolio.update_trailing_stops(prices)
        for symbol in trail_triggers:
            if symbol in self._portfolio.positions:
                price = prices.get(symbol, 0)
                pos = self._portfolio.positions[symbol]
                exit_price = price * (1 - self._fee_rate) if pos.is_long else price * (1 + self._fee_rate)
                self._portfolio.close_position(symbol, exit_price, date, "trailing_stop")
    
    def _process_entries(
        self,
        signals: List[TradeSignal],
        date: datetime,
        open_prices: Dict[str, float],
        close_prices: Dict[str, float]
    ) -> None:
        """
        Process entry signals.
        
        Args:
            signals: List of trade signals.
            date: Trade date.
            open_prices: Open prices (for fills).
            close_prices: Close prices (for exposure calc).
        """
        for signal in signals:
            if not signal.should_trade:
                continue
            
            symbol = signal.symbol
            if symbol in self._portfolio.positions:
                logger.debug(f"Skipping {symbol}: already have position")
                continue
            
            if symbol not in open_prices:
                logger.debug(f"Skipping {symbol}: no price data")
                continue
            
            base_price = open_prices[symbol]
            atr = signal.atr or 1.0
            
            side = PositionSide.LONG if signal.signal_type == SignalType.LONG else PositionSide.SHORT
            
            # Apply slippage
            if side == PositionSide.LONG:
                entry_price = base_price * (1 + self._fee_rate)
            else:
                entry_price = base_price * (1 - self._fee_rate)
            
            # Calculate position size
            shares = self._portfolio.calculate_position_size(
                symbol, side, entry_price, atr, close_prices
            )
            
            if shares <= 0:
                logger.debug(f"Skipping {symbol}: zero position size")
                continue
            
            # Open position
            success, msg = self._portfolio.open_position(
                symbol=symbol,
                side=side,
                shares=shares,
                price=entry_price,
                timestamp=date,
                atr=atr,
                regime=signal.regime.value
            )
            
            if not success:
                logger.debug(f"Failed to open {symbol}: {msg}")
    
    def run(
        self,
        symbols: Optional[List[str]] = None,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None
    ) -> BacktestResult:
        """
        Run backtest.
        
        Args:
            symbols: List of symbols to trade (default: universe).
            start: Backtest start date.
            end: Backtest end date.
        
        Returns:
            BacktestResult with metrics and data.
        """
        # Defaults
        if symbols is None:
            symbols = get_universe_with_proxy()
        
        if end is None:
            end = utc_now() - timedelta(days=1)
        
        if start is None:
            start = end - timedelta(days=365)
        
        # Ensure SPY is in symbols for regime detection
        if "SPY" not in symbols:
            symbols = symbols + ["SPY"]
        
        logger.info(f"Starting backtest: {start.date()} to {end.date()}, {len(symbols)} symbols")
        
        # Initialize components
        self._portfolio = PortfolioManager(
            initial_cash=self._initial_capital,
            fee_rate=self._fee_rate
        )
        
        self._strategy = TradingStrategy()
        self._strategy.initialize()
        
        # Prepare data
        self._symbol_data = self._prepare_data(symbols, start, end)
        
        # Update regime detector with SPY data from backtest period
        if "SPY" in self._symbol_data:
            self._strategy._regime_detector.update_proxy_data(self._symbol_data["SPY"])
        
        if not self._symbol_data:
            raise ValueError("No valid data for backtest")
        
        # Get trading dates from SPY (or first available symbol)
        proxy_symbol = "SPY" if "SPY" in self._symbol_data else list(self._symbol_data.keys())[0]
        proxy_df = self._symbol_data[proxy_symbol]
        trading_dates = proxy_df[
            (proxy_df['timestamp'].dt.date >= start.date()) &
            (proxy_df['timestamp'].dt.date <= end.date())
        ]['timestamp'].dt.date.unique()
        
        trading_dates = sorted(trading_dates)
        logger.info(f"Processing {len(trading_dates)} trading days")
        
        # Main simulation loop
        for i, date in enumerate(trading_dates):
            date_dt = datetime.combine(date, datetime.min.time())
            
            # Get prices
            open_prices = self._get_prices_at_date(date_dt, "open")
            close_prices = self._get_prices_at_date(date_dt, "close")
            
            if not close_prices:
                continue
            
            # 1) Process exits at close (stops use close prices)
            self._process_exits(date_dt, close_prices)
            
            # 2) Record equity at close
            self._portfolio.record_equity(date_dt, close_prices)
            
            # 3) Generate signals for next day using today's close
            #    (In practice, signals computed end-of-day for next open)
            if i < len(trading_dates) - 1:
                # Prepare data through today for signal generation
                symbol_data_through_today = {
                    sym: self._get_data_through_date(sym, date_dt)
                    for sym in self._symbol_data.keys()
                }
                
                # Update regime detector with latest SPY data
                if "SPY" in symbol_data_through_today:
                    self._strategy._regime_detector.update_proxy_data(
                        symbol_data_through_today["SPY"]
                    )
                
                # Generate signals
                next_date = datetime.combine(trading_dates[i + 1], datetime.min.time())
                signals = self._strategy.get_actionable_signals(
                    symbol_data_through_today,
                    next_date
                )
                
                # Get next day's prices for entries
                next_open = self._get_prices_at_date(next_date, "open")
                next_close = self._get_prices_at_date(next_date, "close")
                
                # 4) Process entries at next open
                self._process_entries(signals, next_date, next_open, next_close)
            
            # Progress logging
            if (i + 1) % 50 == 0:
                equity = self._portfolio.mark_to_market(close_prices)
                logger.info(f"Day {i + 1}/{len(trading_dates)}: equity=${equity:,.2f}, "
                           f"positions={len(self._portfolio.positions)}")
        
        # Close remaining positions at final close
        final_prices = self._get_prices_at_date(
            datetime.combine(trading_dates[-1], datetime.min.time()),
            "close"
        )
        for symbol in list(self._portfolio.positions.keys()):
            price = final_prices.get(symbol, 0)
            self._portfolio.close_position(
                symbol, price,
                datetime.combine(trading_dates[-1], datetime.min.time()),
                "end_of_backtest"
            )
        
        # Calculate final metrics
        self._result = self._calculate_metrics(start, end)
        
        logger.info(f"Backtest complete: Return={self._result.total_return_pct:.2f}%, "
                   f"Sharpe={self._result.sharpe_ratio:.2f}, "
                   f"MaxDD={self._result.max_drawdown_pct:.2f}%")
        
        return self._result
    
    def _calculate_metrics(
        self,
        start: datetime,
        end: datetime
    ) -> BacktestResult:
        """
        Calculate performance metrics.
        
        Args:
            start: Backtest start.
            end: Backtest end.
        
        Returns:
            BacktestResult with all metrics.
        """
        equity_df = self._portfolio.get_equity_df()
        trades_df = self._portfolio.get_trade_df()
        
        # Basic returns
        initial = self._initial_capital
        final = equity_df['equity'].iloc[-1] if not equity_df.empty else initial
        total_return = final - initial
        total_return_pct = (total_return / initial) * 100
        
        # Drawdown
        equity_series = equity_df['equity']
        peak = equity_series.expanding().max()
        drawdown = (equity_series - peak) / peak
        max_dd_pct = abs(drawdown.min()) * 100 if not drawdown.empty else 0
        max_dd = peak.max() - equity_series.min() if not equity_series.empty else 0
        
        # Sharpe ratio (annualized)
        returns = equity_series.pct_change().dropna()
        if len(returns) > 1 and returns.std() > 0:
            sharpe = (returns.mean() / returns.std()) * np.sqrt(252)
        else:
            sharpe = 0.0
        
        # Trade statistics
        if trades_df.empty or 'action' not in trades_df.columns:
            exit_trades = pd.DataFrame()
            total_trades = 0
        else:
            exit_trades = trades_df[trades_df['action'] == 'exit']
            total_trades = len(exit_trades)
        
        if total_trades > 0:
            winning = exit_trades[exit_trades['pnl'] > 0]
            losing = exit_trades[exit_trades['pnl'] <= 0]
            
            winning_trades = len(winning)
            losing_trades = len(losing)
            win_rate = winning_trades / total_trades * 100
            
            avg_win = winning['pnl'].mean() if len(winning) > 0 else 0
            avg_loss = abs(losing['pnl'].mean()) if len(losing) > 0 else 0
            
            gross_profit = winning['pnl'].sum() if len(winning) > 0 else 0
            gross_loss = abs(losing['pnl'].sum()) if len(losing) > 0 else 1
            profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0
        else:
            winning_trades = losing_trades = 0
            win_rate = avg_win = avg_loss = profit_factor = 0
        
        return BacktestResult(
            start_date=start,
            end_date=end,
            initial_capital=initial,
            final_equity=final,
            total_return=total_return,
            total_return_pct=total_return_pct,
            max_drawdown=max_dd,
            max_drawdown_pct=max_dd_pct,
            sharpe_ratio=sharpe,
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate=win_rate,
            avg_win=avg_win,
            avg_loss=avg_loss,
            profit_factor=profit_factor,
            equity_curve=equity_df,
            trades=trades_df
        )


def run_backtest(
    symbols: Optional[List[str]] = None,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    initial_capital: float = 100000.0
) -> BacktestResult:
    """
    Convenience function to run a backtest.
    
    Args:
        symbols: Symbols to trade.
        start: Start date.
        end: End date.
        initial_capital: Starting capital.
    
    Returns:
        BacktestResult.
    """
    backtester = Backtester(initial_capital=initial_capital)
    return backtester.run(symbols, start, end)


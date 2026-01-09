"""Multi-asset event-driven backtest engine."""

from datetime import datetime
from typing import Any, Optional

import pandas as pd
from loguru import logger

from data.historical import load_all_cached_bars
from execution.portfolio import Portfolio
from execution.intents import OrderIntent
from storage import get_storage
from backtest.fills import FillSimulator
from backtest.metrics import calculate_metrics, calculate_per_symbol_metrics


class BacktestEngine:
    """Event-driven backtest engine."""

    def __init__(
        self,
        strategy: Any,  # Strategy instance (will be typed properly when strategies are defined)
        symbols: list[str],
        start_date: datetime,
        end_date: datetime,
        initial_capital: float = 10000.0,
        slippage_bps: int = 5,
        maker_fee_bps: int = 10,
        taker_fee_bps: int = 10,
    ):
        """
        Initialize backtest engine.

        Args:
            strategy: Strategy instance (must have on_bar method)
            symbols: List of symbols to backtest
            start_date: Start date
            end_date: End date
            initial_capital: Initial capital
            slippage_bps: Slippage in basis points
            maker_fee_bps: Maker fee in basis points
            taker_fee_bps: Taker fee in basis points
        """
        self.strategy = strategy
        self.symbols = symbols
        self.start_date = start_date
        self.end_date = end_date
        self.initial_capital = initial_capital
        self.fill_simulator = FillSimulator(
            slippage_bps=slippage_bps,
            maker_fee_bps=maker_fee_bps,
            taker_fee_bps=taker_fee_bps,
        )

        self.portfolio = Portfolio(cash=initial_capital)
        self.equity_curve: list[tuple[datetime, float]] = []
        self.trades: list[dict[str, Any]] = []
        self.pending_orders: dict[str, list[tuple[OrderIntent, datetime]]] = {
            symbol: [] for symbol in symbols
        }

    def load_data(self) -> dict[str, pd.DataFrame]:
        """Load historical data for all symbols."""
        logger.info(f"Loading data for {len(self.symbols)} symbols...")
        data = load_all_cached_bars(self.symbols)

        if not data:
            raise ValueError("No data loaded. Run 'download-data' first.")

        # Filter by date range and align
        filtered_data: dict[str, pd.DataFrame] = {}
        for symbol, df in data.items():
            # Filter by date range
            mask = (df.index >= self.start_date) & (df.index <= self.end_date)
            filtered = df[mask].copy()

            if len(filtered) == 0:
                logger.warning(f"No data in date range for {symbol}")
                continue

            filtered_data[symbol] = filtered

        logger.info(f"Loaded data for {len(filtered_data)} symbols")
        return filtered_data

    def align_timestamps(self, data: dict[str, pd.DataFrame]) -> pd.DatetimeIndex:
        """Get aligned timestamps across all symbols."""
        if not data:
            return pd.DatetimeIndex([])

        # Union of all timestamps
        all_timestamps = set()
        for df in data.values():
            all_timestamps.update(df.index)

        timestamps = sorted(all_timestamps)
        return pd.DatetimeIndex(timestamps)

    def run(self) -> dict[str, Any]:
        """
        Run backtest.

        Returns:
            Dictionary with results: equity_curve, trades, metrics
        """
        logger.info(f"Starting backtest: {self.start_date.date()} to {self.end_date.date()}")

        # Load data
        data = self.load_data()
        if not data:
            raise ValueError("No data available for backtest")

        # Get aligned timestamps
        timestamps = self.align_timestamps(data)

        if len(timestamps) == 0:
            raise ValueError("No timestamps in date range")

        # Initialize strategy
        if hasattr(self.strategy, "on_start"):
            self.strategy.on_start()

        # Event loop
        for i, timestamp in enumerate(timestamps):
            # Get current prices (forward-fill from previous bar)
            current_prices: dict[str, float] = {}
            current_bars: dict[str, pd.Series] = {}

            for symbol in self.symbols:
                if symbol in data:
                    # Find bar at or before this timestamp
                    symbol_data = data[symbol]
                    bars_before = symbol_data[symbol_data.index <= timestamp]

                    if len(bars_before) > 0:
                        current_bar = bars_before.iloc[-1]
                        current_bars[symbol] = current_bar
                        current_prices[symbol] = current_bar["close"]

            # Get next bar for fill simulation
            next_timestamp = timestamps[i + 1] if i + 1 < len(timestamps) else None
            next_bars: dict[str, pd.Series] = {}

            if next_timestamp:
                for symbol in self.symbols:
                    if symbol in data:
                        symbol_data = data[symbol]
                        bars_after = symbol_data[symbol_data.index > timestamp]
                        if len(bars_after) > 0:
                            next_bars[symbol] = bars_after.iloc[0]

            # Process pending orders (check for fills)
            self._process_pending_orders(timestamp, current_bars, next_bars)

            # Call strategy.on_bar for each symbol with current data
            for symbol in self.symbols:
                if symbol in current_bars:
                    try:
                        intents = self.strategy.on_bar(symbol, current_bars[symbol])
                        if intents:
                            for intent in intents:
                                if intent.symbol == symbol:
                                    self._submit_order(intent, timestamp, current_bars.get(symbol))
                    except Exception as e:
                        logger.error(f"Error in strategy.on_bar for {symbol} at {timestamp}: {e}")

            # Update portfolio unrealized PnL
            self.portfolio.get_unrealized_pnl(current_prices)

            # Record equity curve (daily snapshots - once per day)
            # Track the last recorded date to avoid duplicates
            if not hasattr(self, '_last_recorded_date'):
                self._last_recorded_date = None
            
            current_date = timestamp.date()
            should_record = (
                self._last_recorded_date is None or 
                current_date > self._last_recorded_date or 
                i == len(timestamps) - 1  # Always record at the end
            )
            
            if should_record:
                equity = self.portfolio.get_equity(current_prices)
                self.equity_curve.append((timestamp, equity))
                if i < len(timestamps) - 1:  # Don't update date on final record
                    self._last_recorded_date = current_date

        # Final equity snapshot
        final_prices = {symbol: data[symbol].iloc[-1]["close"] for symbol in self.symbols if symbol in data}
        final_equity = self.portfolio.get_equity(final_prices)
        self.equity_curve.append((self.end_date, final_equity))

        # Stop strategy
        if hasattr(self.strategy, "on_stop"):
            self.strategy.on_stop()

        # Build results
        equity_df = pd.DataFrame(self.equity_curve, columns=["timestamp", "equity"]).set_index("timestamp")
        trades_df = pd.DataFrame(self.trades) if self.trades else pd.DataFrame()

        # Calculate metrics
        metrics = calculate_metrics(equity_df["equity"], trades_df, self.initial_capital)
        per_symbol_metrics = calculate_per_symbol_metrics(trades_df, equity_df["equity"])

        logger.info(f"Backtest complete. Final equity: ${final_equity:.2f}, Total return: {metrics.get('total_return_pct', 0):.2f}%")

        return {
            "equity_curve": equity_df,
            "trades": trades_df,
            "metrics": metrics,
            "per_symbol_metrics": per_symbol_metrics,
            "final_equity": final_equity,
            "initial_capital": self.initial_capital,
        }

    def _submit_order(
        self,
        intent: OrderIntent,
        timestamp: datetime,
        current_bar: Optional[pd.Series],
    ):
        """Submit order (add to pending orders)."""
        if current_bar is None:
            return

        # Add to pending orders
        self.pending_orders[intent.symbol].append((intent, timestamp))

    def _process_pending_orders(
        self,
        timestamp: datetime,
        current_bars: dict[str, pd.Series],
        next_bars: dict[str, pd.Series],
    ):
        """Process pending orders and check for fills."""
        for symbol, orders in self.pending_orders.items():
            remaining_orders = []

            for intent, order_timestamp in orders:
                current_bar = current_bars.get(symbol)
                next_bar = next_bars.get(symbol)

                if current_bar is None:
                    # Keep order pending
                    remaining_orders.append((intent, order_timestamp))
                    continue

                # Try to fill
                fill_result = self.fill_simulator.simulate_fill(
                    intent,
                    current_bar,
                    next_bar,
                )

                if fill_result:
                    # Track realized PnL before update to calculate incremental PnL for sell orders
                    pnl_before = self.portfolio.realized_pnl
                    
                    # Fill occurred - update portfolio
                    self.portfolio.update_on_fill(
                        symbol,
                        intent.side.value,
                        fill_result.filled_qty,
                        fill_result.fill_price,
                        fill_result.fee,
                    )
                    
                    # Calculate incremental PnL for this trade
                    # For sell orders: realized PnL increases (incremental = change)
                    # For buy orders: no realized PnL yet (PnL = 0)
                    if intent.side.value == "sell":
                        trade_pnl = self.portfolio.realized_pnl - pnl_before
                    else:
                        trade_pnl = 0.0

                    # Record trade with PnL
                    self.trades.append({
                        "timestamp": timestamp,
                        "symbol": symbol,
                        "side": intent.side.value,
                        "qty": fill_result.filled_qty,
                        "price": fill_result.fill_price,
                        "fee": fill_result.fee,
                        "notional": fill_result.filled_qty * fill_result.fill_price,
                        "pnl": trade_pnl,
                    })

                    # If partial fill, keep remaining quantity pending
                    if fill_result.is_partial:
                        remaining_qty = intent.qty_or_notional - fill_result.filled_qty
                        if remaining_qty > 0:
                            # Create new intent with remaining quantity
                            new_intent = OrderIntent(
                                symbol=intent.symbol,
                                side=intent.side,
                                qty_or_notional=remaining_qty,
                                limit_price=intent.limit_price,
                                tif=intent.tif,
                                order_type=intent.order_type,
                                tag=intent.tag,
                            )
                            remaining_orders.append((new_intent, order_timestamp))
                else:
                    # Not filled, keep pending (or cancel if IOC and expired)
                    if intent.tif.value == "ioc" and timestamp > order_timestamp:
                        # IOC order expired
                        pass  # Drop it
                    else:
                        remaining_orders.append((intent, order_timestamp))

            self.pending_orders[symbol] = remaining_orders




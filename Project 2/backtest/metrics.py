"""Performance metrics calculation."""

from typing import Any

import numpy as np
import pandas as pd


def calculate_metrics(
    equity_curve: pd.Series,
    trades: pd.DataFrame,
    initial_capital: float,
) -> dict[str, Any]:
    """
    Calculate performance metrics.

    Args:
        equity_curve: Series of equity values over time (index is timestamp)
        trades: DataFrame with columns: timestamp, symbol, side, qty, price, pnl
        initial_capital: Initial capital

    Returns:
        Dictionary of metrics
    """
    if len(equity_curve) == 0:
        return {}

    # Returns
    returns = equity_curve.pct_change().dropna()

    # Total return
    total_return = (equity_curve.iloc[-1] / initial_capital) - 1.0

    # Sharpe ratio (annualized, assuming daily returns)
    if len(returns) > 1 and returns.std() > 0:
        sharpe = (returns.mean() / returns.std()) * np.sqrt(252)  # Annualized
    else:
        sharpe = 0.0

    # Maximum drawdown
    running_max = equity_curve.expanding().max()
    drawdown = (equity_curve - running_max) / running_max
    max_drawdown = drawdown.min()

    # Drawdown duration
    in_drawdown = drawdown < 0
    if in_drawdown.any():
        drawdown_periods = (equity_curve.index[-1] - equity_curve.index[0]).days
        # Simplified: max consecutive periods in drawdown
        max_dd_duration_days = drawdown_periods  # TODO: Calculate actual consecutive periods
    else:
        max_dd_duration_days = 0

    # Win rate (if trades have PnL)
    if "pnl" in trades.columns and len(trades) > 0:
        winning_trades = trades[trades["pnl"] > 0]
        win_rate = len(winning_trades) / len(trades) if len(trades) > 0 else 0.0

        avg_win = winning_trades["pnl"].mean() if len(winning_trades) > 0 else 0.0
        avg_loss = trades[trades["pnl"] < 0]["pnl"].mean() if len(trades[trades["pnl"] < 0]) > 0 else 0.0
        profit_factor = abs(avg_win / avg_loss) if avg_loss != 0 else 0.0
    else:
        win_rate = 0.0
        avg_win = 0.0
        avg_loss = 0.0
        profit_factor = 0.0

    # Turnover (simplified: sum of absolute trade values / average equity)
    if "notional" in trades.columns:
        turnover = trades["notional"].sum() / equity_curve.mean() if equity_curve.mean() > 0 else 0.0
    else:
        turnover = 0.0

    # Fee drag (if fees tracked)
    if "fee" in trades.columns:
        total_fees = trades["fee"].sum()
        fee_drag_bps = (total_fees / initial_capital) * 10000 if initial_capital > 0 else 0.0
    else:
        total_fees = 0.0
        fee_drag_bps = 0.0

    # Returns distribution
    return_std = returns.std()
    return_skew = returns.skew() if len(returns) > 2 else 0.0
    return_kurtosis = returns.kurtosis() if len(returns) > 2 else 0.0

    metrics = {
        "total_return": total_return,
        "total_return_pct": total_return * 100,
        "sharpe_ratio": sharpe,
        "max_drawdown": max_drawdown,
        "max_drawdown_pct": max_drawdown * 100,
        "max_drawdown_duration_days": max_dd_duration_days,
        "win_rate": win_rate,
        "win_rate_pct": win_rate * 100,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "profit_factor": profit_factor,
        "turnover": turnover,
        "total_fees": total_fees,
        "fee_drag_bps": fee_drag_bps,
        "num_trades": len(trades),
        "return_std": return_std,
        "return_skew": return_skew,
        "return_kurtosis": return_kurtosis,
        "final_equity": equity_curve.iloc[-1],
        "initial_capital": initial_capital,
    }

    return metrics


def calculate_per_symbol_metrics(
    trades: pd.DataFrame,
    equity_curve: pd.Series,
) -> pd.DataFrame:
    """
    Calculate per-symbol contribution metrics.

    Args:
        trades: DataFrame with columns: timestamp, symbol, side, qty, price, pnl
        equity_curve: Equity curve series

    Returns:
        DataFrame with per-symbol metrics
    """
    if len(trades) == 0 or "symbol" not in trades.columns:
        return pd.DataFrame()

    symbol_metrics = []

    for symbol in trades["symbol"].unique():
        symbol_trades = trades[trades["symbol"] == symbol]

        total_pnl = symbol_trades["pnl"].sum() if "pnl" in symbol_trades.columns else 0.0
        num_trades = len(symbol_trades)
        avg_trade_size = symbol_trades["qty"].mean() if "qty" in symbol_trades.columns else 0.0

        symbol_metrics.append({
            "symbol": symbol,
            "total_pnl": total_pnl,
            "num_trades": num_trades,
            "avg_trade_size": avg_trade_size,
            "pnl_pct_of_total": (total_pnl / equity_curve.iloc[-1] * 100) if len(equity_curve) > 0 and equity_curve.iloc[-1] > 0 else 0.0,
        })

    return pd.DataFrame(symbol_metrics)









"""
Reporting module for backtest results.

Generates metrics, CSVs, and visualizations.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd
import numpy as np

from config import get_config
from backtester import BacktestResult
from utils import get_logger, format_pct, format_currency

logger = get_logger("reporting")


class ReportGenerator:
    """
    Generates reports from backtest results.
    
    Outputs:
    - summary.csv: Key metrics
    - equity_curve.csv: Daily equity values
    - trades.csv: All trade records
    - equity_curve.png: Equity visualization
    """
    
    def __init__(self, output_dir: Optional[Path] = None):
        """
        Initialize report generator.
        
        Args:
            output_dir: Directory for output files.
        """
        self._output_dir = output_dir or get_config().paths.reports_dir
        self._output_dir.mkdir(parents=True, exist_ok=True)
        
    def generate(
        self,
        result: BacktestResult,
        prefix: str = ""
    ) -> dict:
        """
        Generate all reports from backtest result.
        
        Args:
            result: BacktestResult object.
            prefix: Optional filename prefix.
        
        Returns:
            Dict of generated file paths.
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if prefix:
            prefix = f"{prefix}_"
        
        files = {}
        
        # Summary CSV
        summary_path = self._output_dir / f"{prefix}summary_{timestamp}.csv"
        self._write_summary(result, summary_path)
        files['summary'] = summary_path
        
        # Equity curve CSV
        equity_path = self._output_dir / f"{prefix}equity_curve_{timestamp}.csv"
        self._write_equity_curve(result, equity_path)
        files['equity_curve'] = equity_path
        
        # Trades CSV
        trades_path = self._output_dir / f"{prefix}trades_{timestamp}.csv"
        self._write_trades(result, trades_path)
        files['trades'] = trades_path
        
        # Equity plot
        plot_path = self._output_dir / f"{prefix}equity_curve_{timestamp}.png"
        self._plot_equity_curve(result, plot_path)
        files['plot'] = plot_path
        
        logger.info(f"Reports generated in {self._output_dir}")
        return files
    
    def _write_summary(
        self,
        result: BacktestResult,
        path: Path
    ) -> None:
        """Write summary metrics to CSV."""
        metrics = {
            'Metric': [
                'Start Date',
                'End Date',
                'Initial Capital',
                'Final Equity',
                'Total Return ($)',
                'Total Return (%)',
                'Max Drawdown ($)',
                'Max Drawdown (%)',
                'Sharpe Ratio',
                'Total Trades',
                'Winning Trades',
                'Losing Trades',
                'Win Rate (%)',
                'Average Win ($)',
                'Average Loss ($)',
                'Profit Factor'
            ],
            'Value': [
                result.start_date.strftime('%Y-%m-%d'),
                result.end_date.strftime('%Y-%m-%d'),
                f"{result.initial_capital:,.2f}",
                f"{result.final_equity:,.2f}",
                f"{result.total_return:,.2f}",
                f"{result.total_return_pct:.2f}",
                f"{result.max_drawdown:,.2f}",
                f"{result.max_drawdown_pct:.2f}",
                f"{result.sharpe_ratio:.3f}",
                result.total_trades,
                result.winning_trades,
                result.losing_trades,
                f"{result.win_rate:.2f}",
                f"{result.avg_win:,.2f}",
                f"{result.avg_loss:,.2f}",
                f"{result.profit_factor:.3f}"
            ]
        }
        
        df = pd.DataFrame(metrics)
        df.to_csv(path, index=False)
        logger.debug(f"Wrote summary to {path}")
    
    def _write_equity_curve(
        self,
        result: BacktestResult,
        path: Path
    ) -> None:
        """Write equity curve to CSV."""
        df = result.equity_curve.copy()
        df['timestamp'] = df['timestamp'].dt.strftime('%Y-%m-%d')
        df.to_csv(path, index=False)
        logger.debug(f"Wrote equity curve to {path}")
    
    def _write_trades(
        self,
        result: BacktestResult,
        path: Path
    ) -> None:
        """Write trade history to CSV."""
        df = result.trades.copy()
        if not df.empty and 'timestamp' in df.columns:
            df['timestamp'] = df['timestamp'].dt.strftime('%Y-%m-%d %H:%M:%S')
        df.to_csv(path, index=False)
        logger.debug(f"Wrote trades to {path}")
    
    def _plot_equity_curve(
        self,
        result: BacktestResult,
        path: Path
    ) -> None:
        """Generate equity curve plot."""
        try:
            import matplotlib
            matplotlib.use('Agg')  # Non-interactive backend
            import matplotlib.pyplot as plt
            import matplotlib.dates as mdates
            
            fig, axes = plt.subplots(2, 1, figsize=(12, 8), height_ratios=[3, 1])
            
            # Equity curve
            ax1 = axes[0]
            df = result.equity_curve
            ax1.plot(df['timestamp'], df['equity'], color='#2E86AB', linewidth=1.5, label='Equity')
            ax1.fill_between(df['timestamp'], result.initial_capital, df['equity'],
                           alpha=0.3, color='#2E86AB')
            ax1.axhline(y=result.initial_capital, color='gray', linestyle='--', alpha=0.5, label='Initial')
            
            ax1.set_title(f'Backtest Equity Curve\n'
                         f'Return: {result.total_return_pct:.2f}% | '
                         f'Sharpe: {result.sharpe_ratio:.2f} | '
                         f'Max DD: {result.max_drawdown_pct:.2f}%',
                         fontsize=12, fontweight='bold')
            ax1.set_ylabel('Equity ($)')
            ax1.legend(loc='upper left')
            ax1.grid(True, alpha=0.3)
            ax1.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
            ax1.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
            
            # Drawdown
            ax2 = axes[1]
            equity = df['equity']
            peak = equity.expanding().max()
            drawdown = ((equity - peak) / peak) * 100
            
            ax2.fill_between(df['timestamp'], 0, drawdown, color='#E74C3C', alpha=0.5)
            ax2.plot(df['timestamp'], drawdown, color='#E74C3C', linewidth=1)
            ax2.set_ylabel('Drawdown (%)')
            ax2.set_xlabel('Date')
            ax2.grid(True, alpha=0.3)
            ax2.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
            ax2.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
            
            plt.tight_layout()
            plt.savefig(path, dpi=150, bbox_inches='tight')
            plt.close()
            
            logger.debug(f"Wrote plot to {path}")
            
        except ImportError as e:
            logger.warning(f"Could not generate plot (matplotlib not available): {e}")
        except Exception as e:
            logger.error(f"Failed to generate plot: {e}")


def print_summary(result: BacktestResult) -> None:
    """
    Print formatted backtest summary to console.
    
    Args:
        result: BacktestResult object.
    """
    print("\n" + "=" * 60)
    print("BACKTEST RESULTS")
    print("=" * 60)
    print(f"Period: {result.start_date.strftime('%Y-%m-%d')} to {result.end_date.strftime('%Y-%m-%d')}")
    print("-" * 60)
    print(f"Initial Capital:     {format_currency(result.initial_capital)}")
    print(f"Final Equity:        {format_currency(result.final_equity)}")
    print(f"Total Return:        {format_currency(result.total_return)} ({result.total_return_pct:.2f}%)")
    print("-" * 60)
    print(f"Max Drawdown:        {format_currency(result.max_drawdown)} ({result.max_drawdown_pct:.2f}%)")
    print(f"Sharpe Ratio:        {result.sharpe_ratio:.3f}")
    print(f"Profit Factor:       {result.profit_factor:.3f}")
    print("-" * 60)
    print(f"Total Trades:        {result.total_trades}")
    print(f"Winning Trades:      {result.winning_trades}")
    print(f"Losing Trades:       {result.losing_trades}")
    print(f"Win Rate:            {result.win_rate:.2f}%")
    print(f"Average Win:         {format_currency(result.avg_win)}")
    print(f"Average Loss:        {format_currency(result.avg_loss)}")
    print("=" * 60 + "\n")


def generate_reports(
    result: BacktestResult,
    output_dir: Optional[Path] = None,
    prefix: str = ""
) -> dict:
    """
    Convenience function to generate all reports.
    
    Args:
        result: BacktestResult object.
        output_dir: Output directory.
        prefix: Filename prefix.
    
    Returns:
        Dict of generated file paths.
    """
    generator = ReportGenerator(output_dir)
    return generator.generate(result, prefix)


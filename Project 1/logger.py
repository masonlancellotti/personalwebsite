"""Logging and trade journal module."""
import logging
import json
import os
from datetime import datetime
from typing import Dict, Any, Optional
from pathlib import Path


class TradeLogger:
    """Custom logger for trades and performance tracking."""
    
    def __init__(self, log_dir: str = "logs", trade_dir: str = "trades"):
        """
        Initialize trade logger.
        
        Args:
            log_dir: Directory for log files
            trade_dir: Directory for trade journal files
        """
        self.log_dir = Path(log_dir)
        self.trade_dir = Path(trade_dir)
        
        # Create directories
        self.log_dir.mkdir(exist_ok=True)
        self.trade_dir.mkdir(exist_ok=True)
        
        # Initialize trade journal
        self.trade_journal_file = self.trade_dir / f"trades_{datetime.now().strftime('%Y%m%d')}.json"
        self.trades = self._load_trade_journal()
        
        # Setup Python logger
        self._setup_logger()
        
        self.logger.info(f"Trade Logger initialized (log_dir: {log_dir}, trade_dir: {trade_dir})")
    
    def _setup_logger(self):
        """Setup Python logging configuration."""
        # Create logger
        self.logger = logging.getLogger('trading_agent')
        self.logger.setLevel(logging.INFO)
        
        # Remove existing handlers
        self.logger.handlers = []
        
        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_format = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        console_handler.setFormatter(console_format)
        self.logger.addHandler(console_handler)
        
        # File handler
        log_file = self.log_dir / f"trading_agent_{datetime.now().strftime('%Y%m%d')}.log"
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.DEBUG)
        file_format = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(file_format)
        self.logger.addHandler(file_handler)
    
    def _load_trade_journal(self) -> list:
        """Load existing trade journal."""
        if self.trade_journal_file.exists():
            try:
                with open(self.trade_journal_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                print(f"Error loading trade journal: {e}")
                return []
        return []
    
    def _save_trade_journal(self):
        """Save trade journal to file."""
        try:
            with open(self.trade_journal_file, 'w') as f:
                json.dump(self.trades, f, indent=2, default=str)
        except Exception as e:
            self.logger.error(f"Error saving trade journal: {e}")
    
    def log_trade_entry(
        self,
        symbol: str,
        side: str,
        shares: float,
        entry_price: float,
        order_id: str,
        stop_loss: Optional[float] = None,
        strategy: Optional[str] = None
    ):
        """
        Log trade entry.
        
        Args:
            symbol: Stock symbol
            side: "buy" or "sell"
            shares: Number of shares
            entry_price: Entry price
            order_id: Order ID
            stop_loss: Stop loss price (optional)
            strategy: Strategy name (optional)
        """
        trade = {
            'symbol': symbol,
            'side': side,
            'shares': shares,
            'entry_price': entry_price,
            'entry_time': datetime.now().isoformat(),
            'order_id': order_id,
            'stop_loss': stop_loss,
            'strategy': strategy,
            'status': 'open',
            'exit_price': None,
            'exit_time': None,
            'pnl': None,
            'pnl_percent': None,
        }
        
        self.trades.append(trade)
        self._save_trade_journal()
        
        self.logger.info(
            f"Trade entry logged: {side.upper()} {shares} {symbol} @ ${entry_price:.2f} "
            f"(order_id: {order_id})"
        )
    
    def log_trade_exit(
        self,
        symbol: str,
        exit_price: float,
        order_id: str,
        pnl: Optional[float] = None
    ):
        """
        Log trade exit.
        
        Args:
            symbol: Stock symbol
            exit_price: Exit price
            order_id: Order ID
            pnl: Profit/loss (optional, will be calculated if None)
        """
        # Find the open trade for this symbol
        open_trades = [t for t in self.trades if t['symbol'] == symbol and t['status'] == 'open']
        
        if not open_trades:
            self.logger.warning(f"No open trade found for {symbol}")
            return
        
        # Update the most recent open trade
        trade = open_trades[-1]
        trade['exit_price'] = exit_price
        trade['exit_time'] = datetime.now().isoformat()
        trade['status'] = 'closed'
        trade['exit_order_id'] = order_id
        
        # Calculate P&L if not provided
        if pnl is None:
            if trade['side'].lower() == 'buy':
                pnl = (exit_price - trade['entry_price']) * trade['shares']
                pnl_percent = ((exit_price - trade['entry_price']) / trade['entry_price']) * 100
            else:  # sell (short)
                pnl = (trade['entry_price'] - exit_price) * trade['shares']
                pnl_percent = ((trade['entry_price'] - exit_price) / trade['entry_price']) * 100
        else:
            pnl_percent = (pnl / (trade['entry_price'] * trade['shares'])) * 100
        
        trade['pnl'] = pnl
        trade['pnl_percent'] = pnl_percent
        
        self._save_trade_journal()
        
        self.logger.info(
            f"Trade exit logged: {symbol} @ ${exit_price:.2f} "
            f"(P&L: ${pnl:.2f}, {pnl_percent:.2f}%)"
        )
    
    def get_trade_statistics(self) -> Dict[str, Any]:
        """
        Calculate trade statistics.
        
        Returns:
            Dictionary with trade statistics
        """
        closed_trades = [t for t in self.trades if t['status'] == 'closed']
        open_trades = [t for t in self.trades if t['status'] == 'open']
        
        if not closed_trades:
            return {
                'total_trades': 0,
                'open_trades': len(open_trades),
                'winning_trades': 0,
                'losing_trades': 0,
                'win_rate': 0,
                'total_pnl': 0,
                'average_pnl': 0,
                'average_win': 0,
                'average_loss': 0,
            }
        
        winning_trades = [t for t in closed_trades if t.get('pnl', 0) > 0]
        losing_trades = [t for t in closed_trades if t.get('pnl', 0) <= 0]
        
        total_pnl = sum(t.get('pnl', 0) for t in closed_trades)
        average_pnl = total_pnl / len(closed_trades) if closed_trades else 0
        
        average_win = sum(t['pnl'] for t in winning_trades) / len(winning_trades) if winning_trades else 0
        average_loss = sum(t['pnl'] for t in losing_trades) / len(losing_trades) if losing_trades else 0
        
        win_rate = (len(winning_trades) / len(closed_trades)) * 100 if closed_trades else 0
        
        return {
            'total_trades': len(closed_trades),
            'open_trades': len(open_trades),
            'winning_trades': len(winning_trades),
            'losing_trades': len(losing_trades),
            'win_rate': win_rate,
            'total_pnl': total_pnl,
            'average_pnl': average_pnl,
            'average_win': average_win,
            'average_loss': average_loss,
        }
    
    def log_signal(self, symbol: str, signal: str, reason: str = ""):
        """
        Log trading signal.
        
        Args:
            symbol: Stock symbol
            signal: Signal type ("buy", "sell", "hold")
            reason: Reason for the signal
        """
        self.logger.info(f"Signal: {signal.upper()} {symbol} - {reason}")
    
    def log_performance(self, account_equity: float, positions_count: int):
        """
        Log performance metrics.
        
        Args:
            account_equity: Current account equity
            positions_count: Number of open positions
        """
        stats = self.get_trade_statistics()
        self.logger.info(
            f"Performance: Equity=${account_equity:.2f}, "
            f"Positions={positions_count}, "
            f"Total Trades={stats['total_trades']}, "
            f"Win Rate={stats['win_rate']:.1f}%, "
            f"Total P&L=${stats['total_pnl']:.2f}"
        )


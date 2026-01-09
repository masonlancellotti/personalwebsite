"""Main trading agent application."""
import os
import sys
import time
import signal
import yaml
import logging
from typing import Dict, Any, Optional
from dotenv import load_dotenv

from alpaca_client import AlpacaClient
from data_handler import DataHandler
from risk_manager import RiskManager
from order_manager import OrderManager
from logger import TradeLogger
from strategies import MomentumStrategy, MeanReversionStrategy, BaseStrategy

# Load environment variables
load_dotenv()


class TradingAgent:
    """Main trading agent class."""
    
    def __init__(self, config_path: str = "config.yaml"):
        """
        Initialize trading agent.
        
        Args:
            config_path: Path to configuration file
        """
        # Load configuration
        self.config = self._load_config(config_path)
        
        # Initialize logger
        self.trade_logger = TradeLogger()
        self.logger = self.trade_logger.logger
        
        # Initialize Alpaca client
        # API keys come from environment variables (loaded from .env file or system env)
        api_key = os.getenv('ALPACA_API_KEY')
        secret_key = os.getenv('ALPACA_SECRET_KEY')
        
        if not api_key or not secret_key:
            raise ValueError(
                "ALPACA_API_KEY and ALPACA_SECRET_KEY must be set in environment variables or .env file"
            )
        
        paper = self.config['alpaca'].get('paper', True)
        
        # Handle environment variable override
        if os.getenv('ALPACA_PAPER'):
            paper = os.getenv('ALPACA_PAPER').lower() == 'true'
        
        self.alpaca_client = AlpacaClient(api_key, secret_key, paper=paper)
        
        # Initialize components
        self.data_handler = DataHandler(
            self.alpaca_client,
            timeframe=self.config['trading']['timeframe']
        )
        self.risk_manager = RiskManager(self.config['risk'])
        self.order_manager = OrderManager(self.alpaca_client, self.risk_manager)
        
        # Initialize strategy
        self.strategy = self._initialize_strategy()
        
        # Trading parameters
        self.symbols = self.config['trading']['symbols']
        self.running = False
        
        self.logger.info("Trading Agent initialized")
        self.logger.info(f"Strategy: {self.strategy.name}")
        self.logger.info(f"Symbols: {self.symbols}")
        self.logger.info(f"Mode: {'Paper Trading' if paper else 'Live Trading'}")
    
    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """Load configuration from YAML file."""
        try:
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
            return config
        except Exception as e:
            print(f"Error loading config: {e}")
            sys.exit(1)
    
    def _initialize_strategy(self) -> BaseStrategy:
        """Initialize trading strategy based on config."""
        strategy_name = self.config['trading']['strategy']
        strategy_params = self.config['strategy_params'].get(strategy_name, {})
        
        if strategy_name == "momentum":
            return MomentumStrategy(strategy_params)
        elif strategy_name == "mean_reversion":
            return MeanReversionStrategy(strategy_params)
        else:
            raise ValueError(f"Unknown strategy: {strategy_name}")
    
    def check_positions(self):
        """Check existing positions and update stop losses if needed."""
        positions = self.order_manager.get_current_positions()
        
        for position in positions:
            symbol = position['symbol']
            avg_entry = position['avg_entry_price']
            current_price = position['current_price']
            
            self.logger.debug(
                f"Position: {symbol} {position['qty']} shares @ ${avg_entry:.2f} "
                f"(current: ${current_price:.2f}, P&L: ${position['unrealized_pl']:.2f})"
            )
    
    def process_symbol(self, symbol: str) -> bool:
        """
        Process a single symbol: fetch data, generate signal, execute trade.
        
        Args:
            symbol: Stock symbol to process
            
        Returns:
            True if a trade was executed, False otherwise
        """
        try:
            # Get latest data with indicators
            latest_data = self.data_handler.get_latest_data(
                symbol=symbol,
                strategy_type=self.config['trading']['strategy'],
                params=self.config['strategy_params'][self.config['trading']['strategy']],
                days=200
            )
            
            if latest_data is None or latest_data.empty:
                # Some stocks may not be available on IEX feed - this is normal for basic accounts
                # Suppress these warnings as they're expected behavior, not errors
                # (Some stocks trade on other exchanges not covered by free IEX feed)
                return False
            
            # Get current position
            current_position = self.order_manager.get_position(symbol)
            
            # Check for pending buy orders
            has_pending_buy = self.order_manager.has_pending_buy_order(symbol)
            
            # Generate signal
            signal = self.strategy.generate_signal(latest_data, current_position)
            current_price = latest_data.get('close', 0)
            
            self.trade_logger.log_signal(symbol, signal, f"Price: ${current_price:.2f}")
            
            # Get account info (refresh for each symbol to get updated buying_power)
            account = self.alpaca_client.get_account()
            account_equity = account['equity']
            buying_power = account['buying_power']
            
            # Execute based on signal
            # Only buy if: signal is buy, no current position, and no pending buy order
            if signal == "buy":
                if current_position is not None:
                    self.logger.debug(f"Buy signal for {symbol} ignored: Already have position ({current_position['qty']} shares)")
                elif has_pending_buy:
                    self.logger.debug(f"Buy signal for {symbol} ignored: Pending buy order exists")
                else:
                    # Calculate stop loss
                    stop_loss = self.strategy.calculate_stop_loss(
                        current_price,
                        latest_data,
                        side="buy"
                    )
                    
                    # Execute buy order
                    success, order_id, shares, message = self.order_manager.execute_buy_order(
                        symbol=symbol,
                        account_equity=account_equity,
                        buying_power=buying_power,
                        entry_price=current_price,
                        stop_loss_price=stop_loss
                    )
                    
                    if success and order_id:
                        self.trade_logger.log_trade_entry(
                            symbol=symbol,
                            side="buy",
                            shares=shares,
                            entry_price=current_price,
                            order_id=order_id,
                            stop_loss=stop_loss,
                            strategy=self.strategy.name
                        )
                        self.logger.info(f"Buy order executed: {symbol} {shares} shares @ ${current_price:.2f}")
                        return True
                    else:
                        self.logger.warning(f"Failed to execute buy order for {symbol}: {message}")
            
            elif signal == "sell" and current_position is not None:
                # Execute sell order
                success, order_id, message = self.order_manager.execute_sell_order(symbol=symbol)
                
                if success and order_id:
                    self.trade_logger.log_trade_exit(
                        symbol=symbol,
                        exit_price=current_price,
                        order_id=order_id
                    )
                    return True
                else:
                    self.logger.warning(f"Failed to execute sell order for {symbol}: {message}")
            
            return False
            
        except Exception as e:
            self.logger.error(f"Error processing {symbol}: {e}", exc_info=True)
            return False
    
    def run_once(self):
        """Run one iteration of the trading loop."""
        try:
            self.logger.info(f"Starting iteration - processing {len(self.symbols)} symbols")
            
            # Clean up filled orders from tracking
            try:
                self.order_manager.cleanup_filled_orders()
            except Exception as e:
                self.logger.error(f"Error cleaning up orders: {e}", exc_info=True)
            
            # Check existing positions
            try:
                self.check_positions()
            except Exception as e:
                self.logger.error(f"Error checking positions: {e}", exc_info=True)
            
            # Process each symbol - ensure ALL symbols are processed
            processed_count = 0
            skipped_count = 0
            for idx, symbol in enumerate(self.symbols, 1):
                # Check if shutdown was requested
                if not self.running:
                    self.logger.info(f"Shutdown requested, stopping after {processed_count} symbols")
                    break
                
                try:
                    self.logger.debug(f"Processing symbol {idx}/{len(self.symbols)}: {symbol}")
                    result = self.process_symbol(symbol)
                    processed_count += 1
                    
                    # Interruptible sleep - check running flag every 0.1 seconds
                    for _ in range(10):  # 10 * 0.1 = 1 second total
                        if not self.running:
                            break
                        time.sleep(0.1)
                except Exception as e:
                    self.logger.error(f"Error processing {symbol} ({idx}/{len(self.symbols)}): {e}", exc_info=True)
                    skipped_count += 1
                    # Continue with next symbol even if one fails
                    continue
            
            self.logger.info(f"Completed iteration - processed {processed_count}/{len(self.symbols)} symbols (skipped: {skipped_count})")
            
            # Log performance
            try:
                portfolio = self.order_manager.get_portfolio_summary()
                self.trade_logger.log_performance(
                    account_equity=portfolio['account_equity'],
                    positions_count=portfolio['positions_count']
                )
            except Exception as e:
                self.logger.error(f"Error logging performance: {e}", exc_info=True)
            
        except Exception as e:
            self.logger.error(f"Error in trading loop: {e}", exc_info=True)
            # Don't re-raise - let the run() method continue
    
    def run(self, interval: int = 300):
        """
        Run the trading agent continuously.
        
        Args:
            interval: Time in seconds between trading loop iterations (default 300 = 5 minutes)
        """
        self.running = True
        self.logger.info(f"Starting trading agent (interval: {interval}s)")
        
        # Setup signal handler for graceful shutdown
        def signal_handler(sig, frame):
            self.logger.info("Shutdown signal received - stopping immediately...")
            self.running = False
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        iteration_count = 0
        try:
            while self.running:
                iteration_count += 1
                try:
                    self.logger.info(f"=== Iteration #{iteration_count} ===")
                    self.run_once()
                    
                    if self.running:
                        self.logger.info(f"Waiting {interval} seconds until next iteration...")
                        # Interruptible sleep - check running flag every second
                        for _ in range(interval):
                            if not self.running:
                                break
                            time.sleep(1)
                except Exception as e:
                    # Log the error but continue running
                    self.logger.error(f"Unexpected error in trading loop iteration #{iteration_count}: {e}", exc_info=True)
                    self.logger.info(f"Continuing to next iteration in {interval} seconds...")
                    if self.running:
                        # Interruptible sleep - check running flag every second
                        for _ in range(interval):
                            if not self.running:
                                break
                            time.sleep(1)
        
        except KeyboardInterrupt:
            self.logger.info("Keyboard interrupt received")
        except Exception as e:
            self.logger.error(f"Fatal error in trading agent: {e}", exc_info=True)
        finally:
            self.shutdown()
    
    def shutdown(self):
        """Gracefully shutdown the trading agent."""
        self.logger.info("Shutting down trading agent...")
        
        # Log final statistics
        stats = self.trade_logger.get_trade_statistics()
        self.logger.info(f"Final statistics: {stats}")
        
        self.running = False


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Alpaca Swing Trading Agent')
    parser.add_argument(
        '--config',
        type=str,
        default='config.yaml',
        help='Path to configuration file (default: config.yaml)'
    )
    parser.add_argument(
        '--once',
        action='store_true',
        help='Run once instead of continuously'
    )
    parser.add_argument(
        '--interval',
        type=int,
        default=300,
        help='Interval between iterations in seconds (default: 300)'
    )
    
    args = parser.parse_args()
    
    # Check for API keys
    api_key = os.getenv('ALPACA_API_KEY')
    secret_key = os.getenv('ALPACA_SECRET_KEY')
    
    if not api_key or not secret_key:
        print("ERROR: ALPACA_API_KEY and ALPACA_SECRET_KEY must be set in environment or .env file")
        sys.exit(1)
    
    # Initialize and run agent
    agent = TradingAgent(config_path=args.config)
    
    if args.once:
        agent.run_once()
    else:
        agent.run(interval=args.interval)


if __name__ == "__main__":
    main()


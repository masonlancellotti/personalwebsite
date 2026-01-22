#!/usr/bin/env python3
"""
Trading Bot CLI Entrypoint.

Provides commands for:
- Running backtests
- Starting the API server
- Running the live trading bot
"""

import argparse
import logging
import sys
from datetime import datetime, timedelta
from typing import Optional

# Add app directory to path for imports
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils import setup_logging, utc_now, ensure_utc


def run_backtest(args) -> None:
    """
    Run backtest command.
    
    Args:
        args: Parsed command line arguments.
    """
    from backtester import Backtester
    from reporting import print_summary, generate_reports
    from universe import get_universe_with_proxy
    
    logger = logging.getLogger("tradingbot.main")
    
    # Parse dates (ensure UTC-aware)
    end_date = utc_now() - timedelta(days=1)
    if args.end:
        end_date = ensure_utc(datetime.strptime(args.end, "%Y-%m-%d"))
    
    start_date = end_date - timedelta(days=365)
    if args.start:
        start_date = ensure_utc(datetime.strptime(args.start, "%Y-%m-%d"))
    
    # Get symbols
    if args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(",")]
    else:
        symbols = get_universe_with_proxy()
    
    logger.info(f"Starting backtest: {start_date.date()} to {end_date.date()}")
    logger.info(f"Universe: {len(symbols)} symbols")
    logger.info(f"Initial capital: ${args.capital:,.2f}")
    
    # Run backtest
    backtester = Backtester(initial_capital=args.capital)
    result = backtester.run(symbols, start_date, end_date)
    
    # Print summary
    print_summary(result)
    
    # Generate reports
    if not args.no_reports:
        files = generate_reports(result, prefix=args.prefix or "backtest")
        logger.info(f"Reports saved to: {list(files.values())}")


def run_api(args) -> None:
    """
    Run API server command.
    
    Args:
        args: Parsed command line arguments.
    """
    from api_server import run_server
    
    logger = logging.getLogger("tradingbot.main")
    logger.info(f"Starting API server on {args.host}:{args.port}")
    
    run_server(host=args.host, port=args.port)


def run_live(args) -> None:
    """
    Run live trading bot command.
    
    Args:
        args: Parsed command line arguments.
    """
    import time
    from datetime import datetime
    
    from config import get_config
    from data_provider import get_data_provider
    from strategy import get_strategy
    from portfolio import LivePortfolioManager
    from alpaca_clients import get_client_manager
    from universe import get_universe_with_proxy
    from api_server import update_bot_state
    
    logger = logging.getLogger("tradingbot.main")
    config = get_config()
    
    # Validate account
    client_manager = get_client_manager()
    mode = "PAPER" if client_manager.is_paper else "LIVE"
    logger.info(f"Running in {mode} mode")
    
    valid, msg = client_manager.validate_account_for_shorting()
    if not valid:
        logger.warning(f"Account validation: {msg}")
    
    # Initialize components
    strategy = get_strategy()
    strategy.initialize()
    
    data_provider = get_data_provider()
    portfolio_manager = LivePortfolioManager()
    symbols = get_universe_with_proxy()
    
    logger.info(f"Bot initialized with {len(symbols)} symbols")
    
    def run_scan():
        """Execute one scan cycle."""
        logger.info("=" * 60)
        logger.info("Starting scan cycle")
        update_bot_state(scan_time=utc_now())
        
        try:
            # Fetch latest data
            symbol_data = data_provider.get_latest_bars(symbols)
            logger.info(f"Fetched data for {len(symbol_data)} symbols")
            
            # Generate signals
            signals = strategy.get_actionable_signals(symbol_data, utc_now())
            logger.info(f"Generated {len(signals)} actionable signals")
            
            update_bot_state(decision_time=utc_now())
            
            # Execute signals
            for signal in signals:
                logger.info(f"Signal: {signal.signal_type.value.upper()} {signal.symbol}")
                
                if not args.dry_run:
                    side = "buy" if signal.signal_type.value == "long" else "sell"
                    
                    # Calculate position size (simplified for live)
                    equity = portfolio_manager.get_account_equity()
                    position_value = equity * (config.risk.max_position_pct / 100) * 0.5
                    
                    # Get current price
                    df = symbol_data.get(signal.symbol)
                    if df is not None and not df.empty:
                        price = float(df['close'].iloc[-1])
                        qty = int(position_value / price)
                        
                        if qty > 0:
                            success, msg, order_id = portfolio_manager.place_order(
                                signal.symbol, side, qty
                            )
                            if success:
                                logger.info(f"Order placed: {side} {qty} {signal.symbol}")
                            else:
                                logger.error(f"Order failed: {msg}")
                else:
                    logger.info(f"DRY RUN: Would {signal.signal_type.value} {signal.symbol}")
            
            logger.info("Scan cycle complete")
            
        except Exception as e:
            logger.error(f"Error in scan cycle: {e}", exc_info=True)
    
    # Run mode
    if args.once:
        # Single run
        run_scan()
    else:
        # Continuous loop
        interval_seconds = config.live.scan_interval_minutes * 60
        logger.info(f"Starting continuous loop (interval: {config.live.scan_interval_minutes} min)")
        
        while True:
            try:
                run_scan()
                logger.info(f"Sleeping for {config.live.scan_interval_minutes} minutes")
                time.sleep(interval_seconds)
            except KeyboardInterrupt:
                logger.info("Interrupted by user")
                break
            except Exception as e:
                logger.error(f"Error in main loop: {e}", exc_info=True)
                time.sleep(60)  # Wait before retry


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Trading Bot CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run backtest
  python main.py backtest --start 2025-01-01 --end 2025-12-31
  
  # Run backtest with specific symbols
  python main.py backtest --symbols AAPL,MSFT,GOOGL --capital 50000
  
  # Start API server
  python main.py api --port 8000
  
  # Run live bot (paper trading, single scan)
  python main.py live --once --dry-run
  
  # Run live bot continuously
  python main.py live
        """
    )
    
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable debug logging"
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Backtest command
    bt_parser = subparsers.add_parser("backtest", help="Run backtest simulation")
    bt_parser.add_argument(
        "--start", "-s",
        type=str,
        help="Start date (YYYY-MM-DD)"
    )
    bt_parser.add_argument(
        "--end", "-e",
        type=str,
        help="End date (YYYY-MM-DD)"
    )
    bt_parser.add_argument(
        "--symbols",
        type=str,
        help="Comma-separated list of symbols (default: full universe)"
    )
    bt_parser.add_argument(
        "--capital", "-c",
        type=float,
        default=100000.0,
        help="Initial capital (default: 100000)"
    )
    bt_parser.add_argument(
        "--prefix",
        type=str,
        help="Report filename prefix"
    )
    bt_parser.add_argument(
        "--no-reports",
        action="store_true",
        help="Skip report generation"
    )
    bt_parser.set_defaults(func=run_backtest)
    
    # API command
    api_parser = subparsers.add_parser("api", help="Start API server")
    api_parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="Server host (default: 0.0.0.0)"
    )
    api_parser.add_argument(
        "--port", "-p",
        type=int,
        default=8000,
        help="Server port (default: 8000)"
    )
    api_parser.set_defaults(func=run_api)
    
    # Live command
    live_parser = subparsers.add_parser("live", help="Run live trading bot")
    live_parser.add_argument(
        "--once",
        action="store_true",
        help="Run single scan and exit"
    )
    live_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't place actual orders"
    )
    live_parser.set_defaults(func=run_live)
    
    # Parse args
    args = parser.parse_args()
    
    # Setup logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    setup_logging(level=log_level)
    
    logger = logging.getLogger("tradingbot.main")
    
    # Execute command
    if args.command is None:
        parser.print_help()
        sys.exit(1)
    
    try:
        args.func(args)
    except KeyboardInterrupt:
        logger.info("Interrupted")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()


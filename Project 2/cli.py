"""Command-line interface using Typer."""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Annotated, Optional

import typer
from loguru import logger

from config import settings
from alpaca_clients import get_clients

# Import strategies to register them (must be after config)
try:
    from strategies.implemented import *  # noqa: F401, F403
except ImportError:
    pass  # Strategies may not be available in all contexts
from universe import (
    build_universe as build_universe_func,
    load_universe,
    validate_symbols as validate_universe_symbols,
)
from data.historical import download_bars, cache_bars, fetch_latest_bar
from strategies.base import list_strategies as list_strategies_func, explain_strategy as explain_strategy_func, get_strategy
from backtest.engine import BacktestEngine
from execution.portfolio import Portfolio
from execution.order_manager import OrderManager
from execution.risk import RiskManager
from execution.reconcile import ReconcileManager

app = typer.Typer(help="Alpaca Crypto Trading Bot")


@app.command()
def list_universe():
    """List all tradable crypto pairs in the universe."""
    try:
        symbols = load_universe()
        typer.echo(f"\nFound {len(symbols)} symbols in universe:\n")
        for symbol in symbols:
            typer.echo(f"  {symbol}")
        typer.echo(f"\nTotal: {len(symbols)} symbols")
    except FileNotFoundError as e:
        typer.echo(f"Error: {e}", err=True)
        typer.echo("Run 'build-universe' first to create the universe cache.", err=True)
        raise typer.Exit(1)


@app.command()
def build_universe(
    top_n: Annotated[str, typer.Option("--top-n", "-n", help="Top N symbols or ALL")] = "ALL",
    lookback_days: Annotated[int, typer.Option("--lookback-days", "-d", help="Lookback days for volume")] = 30,
    min_avg_dollar_vol: Annotated[float, typer.Option("--min-avg-dollar-vol", "-v", help="Min avg dollar volume")] = 0.0,
    quote_filter: Annotated[str, typer.Option("--quote-filter", "-q", help="Quote currency filter")] = "",
    exclude: Annotated[str, typer.Option("--exclude", "-e", help="Symbols to exclude")] = "",
):
    """Build and cache the crypto universe."""
    typer.echo(f"Building universe with top_n={top_n}...")

    # Parse top_n
    top_n_int = None if top_n.upper() == "ALL" else int(top_n)

    # Parse filters
    quote_filter_list = [q.strip() for q in quote_filter.split(",") if q.strip()] if quote_filter else None
    exclude_list = [s.strip() for s in exclude.split(",") if s.strip()] if exclude else None

    try:
        symbols = build_universe_func(
            top_n=top_n_int,
            min_avg_dollar_vol=min_avg_dollar_vol,
            quote_filter=quote_filter_list,
            exclude_symbols=exclude_list,
        )
        typer.echo(f"\n[OK] Built universe with {len(symbols)} symbols")
        typer.echo(f"  Top {min(10, len(symbols))} symbols: {', '.join(symbols[:10])}")
        if len(symbols) > 10:
            typer.echo(f"  ... and {len(symbols) - 10} more")
    except Exception as e:
        typer.echo(f"Error building universe: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def validate_symbols(
    symbols: Annotated[str, typer.Option("--symbols", "-s", help="Comma-separated symbols")],
):
    """Validate that symbols exist in the universe."""
    symbol_list = [s.strip() for s in symbols.split(",") if s.strip()]
    if not symbol_list:
        typer.echo("Error: No symbols provided", err=True)
        raise typer.Exit(1)

    try:
        valid, invalid = validate_universe_symbols(symbol_list)
        if valid:
            typer.echo(f"\n[OK] Valid symbols ({len(valid)}): {', '.join(valid)}")
        if invalid:
            typer.echo(f"\n[ERROR] Invalid symbols ({len(invalid)}): {', '.join(invalid)}", err=True)
            typer.echo("These symbols are not in the tradable universe.", err=True)
            raise typer.Exit(1)
        typer.echo("\nAll symbols are valid!")
    except Exception as e:
        typer.echo(f"Error validating symbols: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def download_data(
    timeframe: Annotated[str, typer.Option("--timeframe", "-t", help="Timeframe (e.g., 1Min)")] = "1Min",
    lookback_days: Annotated[int, typer.Option("--lookback-days", "-d", help="Lookback days")] = 30,
):
    """Download and cache historical data for all symbols in universe."""
    typer.echo(f"Downloading data: timeframe={timeframe}, lookback_days={lookback_days}")

    try:
        # Load universe
        symbols = load_universe()
        typer.echo(f"Found {len(symbols)} symbols in universe")

        # Download bars
        typer.echo("Downloading bars (this may take a while)...")
        data = download_bars(symbols, timeframe=timeframe, lookback_days=lookback_days)

        if not data:
            typer.echo("No data downloaded", err=True)
            raise typer.Exit(1)

        # Cache bars
        typer.echo("Caching bars...")
        cached_files = cache_bars(data)

        typer.echo(f"\n[OK] Successfully downloaded and cached {len(cached_files)} symbols")
    except FileNotFoundError:
        typer.echo("Error: Universe cache not found. Run 'build-universe' first.", err=True)
        raise typer.Exit(1)
    except Exception as e:
        typer.echo(f"Error downloading data: {e}", err=True)
        logger.exception("Download data error")
        raise typer.Exit(1)


@app.command()
def list_strategies():
    """List all available strategies."""
    strategy_list = list_strategies_func()
    typer.echo(f"\nAvailable strategies ({len(strategy_list)}):\n")
    for name in strategy_list:
        typer.echo(f"  - {name}")
    typer.echo()


@app.command()
def explain_strategy(
    name: Annotated[str, typer.Option("--name", "-n", help="Strategy name")],
):
    """Explain a specific strategy and its parameters."""
    try:
        info = explain_strategy_func(name)
        typer.echo(f"\nStrategy: {info['name']}")
        typer.echo(f"Class: {info['class']}\n")
        typer.echo("Description:")
        typer.echo(f"  {info['explanation']}\n")

        if "params_schema" in info:
            typer.echo("Parameters:")
            schema = info["params_schema"]
            if "properties" in schema:
                for param_name, param_info in schema["properties"].items():
                    param_type = param_info.get("type", "unknown")
                    param_desc = param_info.get("description", "")
                    default = param_info.get("default", "")
                    default_str = f" (default: {default})" if default else ""
                    typer.echo(f"  - {param_name}: {param_type}{default_str}")
                    if param_desc:
                        typer.echo(f"    {param_desc}")
            typer.echo()
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def backtest(
    strategy: Annotated[str, typer.Option("--strategy", "-s", help="Strategy name")],
    start: Annotated[str, typer.Option("--start", help="Start date YYYY-MM-DD")],
    end: Annotated[str, typer.Option("--end", help="End date YYYY-MM-DD")],
    universe: Annotated[str, typer.Option("--universe", "-u", help="Universe (ALL or symbol list)")] = "ALL",
    params: Annotated[Optional[str], typer.Option("--params", "-p", help="Strategy params JSON (optional)")] = None,
):
    """Run a backtest."""
    # Parse params - default to empty dict if not provided
    if params is None or params.strip() == "":
        params_dict = {}
    else:
        params = params.strip()
        try:
            params_dict = json.loads(params)
        except json.JSONDecodeError:
            # Try to fix common PowerShell quote issues
            fixed_params = params
            if "'" in fixed_params and '"' not in fixed_params:
                fixed_params = fixed_params.replace("'", '"')
            if ':' in fixed_params and '"' not in fixed_params:
                fixed_params = re.sub(r'(\w+):', r'"\1":', fixed_params)
            try:
                params_dict = json.loads(fixed_params)
            except json.JSONDecodeError:
                typer.echo(f"Invalid JSON in --params: {params}", err=True)
                typer.echo("Expected JSON format. Examples:", err=True)
                typer.echo('  PowerShell: --params \'{"spread_bps": 20.0}\'', err=True)
                typer.echo('  Or omit --params to use default values', err=True)
                raise typer.Exit(1)

    try:
        # Parse dates
        start_date = datetime.strptime(start, "%Y-%m-%d")
        end_date = datetime.strptime(end, "%Y-%m-%d")

        # Get strategy class
        strategy_class = get_strategy(strategy)

        # Get universe
        if universe.upper() == "ALL":
            symbols = load_universe()
        else:
            symbols = [s.strip() for s in universe.split(",") if s.strip()]

        # Create strategy instance
        strategy_instance = strategy_class(**params_dict)

        # Run backtest
        engine = BacktestEngine(
            strategy=strategy_instance,
            symbols=symbols,
            start_date=start_date,
            end_date=end_date,
        )

        results = engine.run()

        # Display results
        typer.echo(f"\n[OK] Backtest complete")
        typer.echo(f"\nMetrics:")
        metrics = results["metrics"]
        for key, value in metrics.items():
            if isinstance(value, float):
                typer.echo(f"  {key}: {value:.4f}")
            else:
                typer.echo(f"  {key}: {value}")

    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    except Exception as e:
        typer.echo(f"Error running backtest: {e}", err=True)
        logger.exception("Backtest error")
        raise typer.Exit(1)


@app.command()
def optimize(
    strategy: Annotated[str, typer.Option("--strategy", "-s", help="Strategy name")],
    walkforward: Annotated[bool, typer.Option("--walkforward", "-w", help="Use walk-forward")] = False,
    params_grid: Annotated[str, typer.Option("--params-grid", "-g", help="Params grid JSON")] = "{}",
):
    """Optimize strategy parameters."""
    try:
        grid_dict = json.loads(params_grid)
    except json.JSONDecodeError:
        typer.echo(f"Invalid JSON in --params-grid: {params_grid}", err=True)
        raise typer.Exit(1)

    typer.echo(f"Optimizing strategy: {strategy}, walkforward={walkforward}")
    typer.echo(f"Params grid: {grid_dict}")
    # TODO: Implement in backtest/walkforward.py
    typer.echo("Not yet implemented")


@app.command()
def paper(
    strategy: Annotated[str, typer.Option("--strategy", "-s", help="Strategy name")],
    universe: Annotated[str, typer.Option("--universe", "-u", help="Universe (ALL or symbol list)")] = "ALL",
    params: Annotated[Optional[str], typer.Option("--params", "-p", help="Strategy params JSON (optional)")] = None,
):
    """Run in paper trading mode."""
    if not settings.ALPACA_PAPER:
        typer.echo("WARNING: ALPACA_PAPER is False. This will attempt live trading!", err=True)
        if not settings.ALLOW_LIVE:
            typer.echo("ERROR: ALLOW_LIVE is False. Aborting.", err=True)
            raise typer.Exit(1)

    # Parse params - default to empty dict if not provided
    if params is None or params.strip() == "":
        params_dict = {}
    else:
        params = params.strip()
        try:
            # Try to parse as JSON directly
            params_dict = json.loads(params)
        except json.JSONDecodeError:
            # If JSON parsing fails, try to fix common PowerShell quote issues
            # PowerShell often strips quotes, so we need to reconstruct valid JSON
            fixed_params = params
            
            # Replace single quotes with double quotes (common in PowerShell)
            if "'" in fixed_params and '"' not in fixed_params:
                fixed_params = fixed_params.replace("'", '"')
            
            # Try to fix missing quotes around keys (PowerShell strips them)
            # Pattern: {key: value} -> {"key": value}
            if ':' in fixed_params and '"' not in fixed_params:
                # Try to add quotes around keys
                fixed_params = re.sub(r'(\w+):', r'"\1":', fixed_params)
            
            try:
                params_dict = json.loads(fixed_params)
            except json.JSONDecodeError:
                typer.echo(f"Invalid JSON in --params: {params}", err=True)
                typer.echo("Expected JSON format. Examples:", err=True)
                typer.echo('  PowerShell: --params \'{"spread_bps": 20.0}\'', err=True)
                typer.echo('  Or use: --params "{\\"spread_bps\\": 20.0}"', err=True)
                typer.echo('  Or omit --params to use default values', err=True)
                raise typer.Exit(1)

    try:
        typer.echo(f"Starting paper trading: strategy={strategy}, universe={universe}")
        typer.echo(f"Params: {params_dict}")
        typer.echo("\n[WARNING] Paper trading mode (live trading requires ALLOW_LIVE=true)")
        typer.echo("Press Ctrl+C to stop\n")

        # Get strategy class
        strategy_class = get_strategy(strategy)
        strategy_instance = strategy_class(**params_dict)

        # Get universe
        if universe.upper() == "ALL":
            symbols = load_universe()
        else:
            symbols = [s.strip() for s in universe.split(",") if s.strip()]

        # Filter to only USD pairs (we only have USD balance, not USDC/USDT/BTC/etc)
        # This prevents "insufficient balance" errors for quote currencies we don't have
        original_count = len(symbols)
        symbols = [s for s in symbols if s.endswith("/USD")]
        if original_count != len(symbols):
            typer.echo(f"Filtered to {len(symbols)} USD pairs (removed {original_count - len(symbols)} non-USD pairs)")

        typer.echo(f"Trading {len(symbols)} symbols: {symbols[:5]}..." if len(symbols) > 5 else f"Trading {len(symbols)} symbols: {symbols}")

        # Initialize execution pipeline
        # Fetch account to get initial cash
        clients = get_clients()
        try:
            account = clients.trading_client.get_account()
            initial_cash = float(account.cash)
            typer.echo(f"Initial cash: ${initial_cash:.2f}")
        except Exception as e:
            logger.warning(f"Could not fetch account, using default cash: {e}")
            initial_cash = 10000.0
            
        portfolio = Portfolio(cash=initial_cash)
        order_manager = OrderManager()
        risk_manager = RiskManager(portfolio, order_manager)
        reconcile_manager = ReconcileManager(portfolio, order_manager)

        # Start strategy
        strategy_instance.on_start()

        typer.echo("\n[OK] Paper trading started")
        typer.echo("Fetching latest bars and processing orders...\n")
        typer.echo("Press Ctrl+C to stop...\n")

        # Trading loop
        import time
        import pandas as pd
        from datetime import datetime, timezone
        
        last_bar_fetch = 0
        bar_fetch_interval = 60  # Fetch bars every 60 seconds
        last_fill_poll = 0
        fill_poll_interval = 5  # Poll for fills every 5 seconds
        last_symbol_idx = 0  # Round-robin through symbols
        
        # Initialize symbol prices (will be updated as bars are fetched)
        symbol_prices = {symbol: 0.0 for symbol in symbols}
        
        # Do initial reconciliation to sync with broker state (positions, orders, cash)
        logger.info("Performing initial reconciliation...")
        reconcile_manager.reconcile()
        
        # Fetch initial prices for symbols with positions to calculate accurate starting equity
        # This ensures daily loss tracking starts from the correct baseline
        logger.info("Fetching initial prices for daily loss tracking...")
        symbols_with_positions = [s for s, p in portfolio.positions.items() if p.qty != 0]
        symbols_to_price = list(set(symbols_with_positions + symbols[:20]))  # Positions + first 20 universe symbols
        
        for symbol in symbols_to_price:
            try:
                latest_bar = fetch_latest_bar(symbol, settings.TIMEFRAME)
                if latest_bar is not None:
                    close_price = float(latest_bar.get("close", 0.0))
                    if close_price > 0:
                        symbol_prices[symbol] = close_price
            except Exception as e:
                logger.debug(f"Could not fetch initial price for {symbol}: {e}")
        
        # Initialize daily loss tracking AFTER reconciliation and with initial prices
        # This ensures we track equity changes from the session start, including pre-existing positions
        # Only track losses from this point forward, not from before the bot started
        risk_manager.initialize_daily_loss(symbol_prices)
        
        # Error tracking for robustness
        consecutive_errors = 0
        max_consecutive_errors = 10
        last_heartbeat = time.time()
        heartbeat_interval = 3600  # Log heartbeat every hour
        iteration_count = 0
        
        try:
            while True:
                iteration_count += 1
                current_time = time.time()
                
                # Heartbeat logging (every hour)
                if current_time - last_heartbeat >= heartbeat_interval:
                    logger.info(f"[HEARTBEAT] Bot still running - Iteration #{iteration_count}, {len(symbols)} symbols")
                    last_heartbeat = current_time
                
                try:
                    # Check kill switch
                    if not risk_manager.check_kill_switch():
                        typer.echo("\n[WARNING] Kill switch activated, stopping...")
                        break

                    # Fetch latest bars periodically and process strategy
                    if current_time - last_bar_fetch >= bar_fetch_interval:
                        # Process symbols in round-robin fashion to avoid rate limits
                        symbol = symbols[last_symbol_idx % len(symbols)]
                        last_symbol_idx += 1
                        
                        try:
                            latest_bar = fetch_latest_bar(symbol, settings.TIMEFRAME)
                            if latest_bar is not None:
                                # Update symbol price
                                close_price = float(latest_bar.get("close", 0.0))
                                if close_price > 0:
                                    symbol_prices[symbol] = close_price
                                    
                                    # Check daily loss after updating prices
                                    if not risk_manager.check_daily_loss(symbol_prices):
                                        typer.echo("\n[WARNING] Daily loss limit exceeded, stopping...")
                                        break
                                    
                                    # Update strategy inventory if method exists
                                    if hasattr(strategy_instance, "update_inventory"):
                                        position = portfolio.get_position(symbol)
                                        strategy_instance.update_inventory(symbol, position.qty)
                                    
                                    # Cancel existing orders for this symbol before placing new ones
                                    # This prevents order accumulation and implements cancel-and-replace logic
                                    existing_orders = order_manager.get_open_orders_for_symbol(symbol)
                                    if existing_orders:
                                        logger.debug(f"Canceling {len(existing_orders)} existing orders for {symbol} before placing new ones")
                                        order_manager.cancel_all_orders(symbol=symbol)
                                    
                                    # Call strategy to get order intents
                                    try:
                                        # #region agent log
                                        import json, traceback, sys
                                        with open('.cursor/debug.log', 'a') as f: f.write(json.dumps({"sessionId":"debug-session","runId":"run2","hypothesisId":"FIX_BROKEN","location":"cli.py:471","message":"About to call on_bar","data":{"symbol":symbol,"strategy_type":str(type(strategy_instance))},"timestamp":int(__import__('time').time()*1000)})+'\n')
                                        # #endregion
                                        order_intents = strategy_instance.on_bar(symbol, latest_bar)
                                        # #region agent log
                                        with open('.cursor/debug.log', 'a') as f: f.write(json.dumps({"sessionId":"debug-session","runId":"run2","hypothesisId":"FIX_BROKEN","location":"cli.py:474","message":"on_bar returned","data":{"symbol":symbol,"intents_count":len(order_intents) if order_intents else 0,"intents_type":str(type(order_intents))},"timestamp":int(__import__('time').time()*1000)})+'\n')
                                        # #endregion
                                        
                                        # Process each order intent
                                        for intent in order_intents:
                                            # Build symbol state for risk check (simplified)
                                            symbol_state = {
                                                symbol: {
                                                    "mid": close_price,
                                                    "bid": close_price * 0.999,  # Approximate
                                                    "ask": close_price * 1.001,  # Approximate
                                                    "last_update_ts": datetime.now(timezone.utc),
                                                }
                                            }
                                            
                                            # Risk check
                                            passed, error_msg = risk_manager.check_order_intent(
                                                intent, symbol_state, symbol_prices
                                            )
                                            
                                            if passed:
                                                # Submit order
                                                order_result = order_manager.submit_order(
                                                    intent, strategy, close_price
                                                )
                                                if order_result:
                                                    logger.info(f"Submitted order for {symbol}: {intent.side.value} {intent.qty_or_notional} @ {intent.limit_price or 'market'}")
                                            else:
                                                logger.debug(f"Order rejected for {symbol}: {error_msg}")
                                                
                                    except Exception as e:
                                        # #region agent log
                                        import json, traceback, sys
                                        exc_type, exc_value, exc_tb = sys.exc_info()
                                        tb_str = ''.join(traceback.format_exception(exc_type, exc_value, exc_tb))
                                        with open('.cursor/debug.log', 'a') as f: f.write(json.dumps({"sessionId":"debug-session","runId":"run2","hypothesisId":"FIX_BROKEN","location":"cli.py:505","message":"Exception caught","data":{"symbol":symbol,"exception_type":str(type(e).__name__),"exception_message":str(e),"traceback":tb_str},"timestamp":int(__import__('time').time()*1000)})+'\n')
                                        # #endregion
                                        logger.error(f"Error processing strategy for {symbol}: {e}")
                                        
                        except Exception as e:
                            logger.error(f"Error fetching bar for {symbol}: {e}")
                        
                        last_bar_fetch = current_time
                    
                    # Poll for fills periodically
                    if current_time - last_fill_poll >= fill_poll_interval:
                        try:
                            fills = order_manager.poll_for_fills()
                            for fill in fills:
                                try:
                                    # Update portfolio
                                    portfolio.update_on_fill(
                                        symbol=fill["symbol"],
                                        side=fill["side"],
                                        qty=fill["qty"],
                                        price=fill["price"],
                                        fee=fill.get("fee", 0.0),
                                    )
                                    
                                    # Notify strategy
                                    strategy_instance.on_order_fill(
                                        symbol=fill["symbol"],
                                        side=fill["side"],
                                        qty=fill["qty"],
                                        price=fill["price"],
                                    )
                                    
                                    logger.info(f"Fill: {fill['symbol']} {fill['side']} {fill['qty']} @ ${fill['price']:.2f}")
                                    
                                except Exception as e:
                                    logger.error(f"Error processing fill: {e}")
                        except Exception as e:
                            logger.error(f"Error polling for fills: {e}")
                        
                        last_fill_poll = current_time
                
                    # Reconciliation
                    if reconcile_manager.should_reconcile():
                        try:
                            reconcile_manager.reconcile()
                        except Exception as e:
                            logger.error(f"Error during reconciliation: {e}", exc_info=True)
                            # Continue even if reconciliation fails

                    # Reset error counter on successful iteration
                    consecutive_errors = 0
                    
                except Exception as e:
                    consecutive_errors += 1
                    logger.error(
                        f"Error in main trading loop (iteration #{iteration_count}, "
                        f"consecutive errors: {consecutive_errors}): {e}",
                        exc_info=True
                    )
                    
                    # If too many consecutive errors, wait longer before retrying
                    if consecutive_errors >= max_consecutive_errors:
                        logger.warning(
                            f"Too many consecutive errors ({consecutive_errors}), "
                            f"waiting 30 seconds before retrying..."
                        )
                        time.sleep(30)
                        consecutive_errors = 0  # Reset after backoff
                    else:
                        # Short wait before retrying
                        time.sleep(5)
                    
                    # Continue loop even after errors
                    continue

                time.sleep(1)  # Main loop sleep

        except KeyboardInterrupt:
            typer.echo("\n\nStopping paper trading...")
        except Exception as e:
            # Catch any unexpected errors that break out of the loop
            logger.critical(f"Fatal error in trading loop: {e}", exc_info=True)
            logger.info("Attempting to continue after fatal error...")
            # Could add restart logic here, but for now just log and continue
            typer.echo(f"\n[ERROR] Unexpected error occurred: {e}")
            typer.echo("Check logs for details. Bot will attempt to continue...")

        # Stop strategy
        strategy_instance.on_stop()

        # Cancel all orders
        canceled_count = order_manager.cancel_all_orders()
        typer.echo(f"Canceled {canceled_count} open orders")

        # Final portfolio summary
        final_equity = portfolio.get_equity(symbol_prices)
        total_pnl = portfolio.get_total_pnl(symbol_prices)
        typer.echo(f"\nFinal equity: ${final_equity:.2f}")
        typer.echo(f"Total PnL: ${total_pnl:.2f}")
        typer.echo(f"Cash: ${portfolio.cash:.2f}")
        typer.echo(f"Open positions: {len([p for p in portfolio.positions.values() if p.qty != 0])}")

        typer.echo("\n[OK] Paper trading stopped")

    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    except KeyboardInterrupt:
        typer.echo("\n\nStopping paper trading (interrupted)...")
        # Try to clean up gracefully
        try:
            if 'strategy_instance' in locals():
                strategy_instance.on_stop()
            if 'order_manager' in locals():
                canceled_count = order_manager.cancel_all_orders()
                typer.echo(f"Canceled {canceled_count} open orders")
        except Exception as cleanup_error:
            logger.error(f"Error during cleanup: {cleanup_error}")
        raise typer.Exit(0)
    except Exception as e:
        typer.echo(f"Error in paper trading: {e}", err=True)
        logger.exception("Paper trading error")
        # Try to clean up before exiting
        try:
            if 'strategy_instance' in locals():
                strategy_instance.on_stop()
            if 'order_manager' in locals():
                order_manager.cancel_all_orders()
        except Exception as cleanup_error:
            logger.error(f"Error during cleanup: {cleanup_error}")
        raise typer.Exit(1)


@app.command()
def status():
    """Show current trading status."""
    typer.echo("Status:")
    typer.echo(f"  Paper mode: {settings.ALPACA_PAPER}")
    typer.echo(f"  Allow live: {settings.ALLOW_LIVE}")
    # TODO: Show positions, orders, PnL
    typer.echo("Not yet implemented")


@app.command()
def cancel_all():
    """Cancel all open orders."""
    try:
        order_manager = OrderManager()
        count = order_manager.cancel_all_orders()
        typer.echo(f"[OK] Canceled {count} orders")
    except Exception as e:
        typer.echo(f"Error canceling orders: {e}", err=True)
        logger.exception("Cancel all error")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()


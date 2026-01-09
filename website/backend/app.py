"""Backend API server for trading algorithms portfolio website."""
import os
import json
import requests
from datetime import datetime, timedelta, timezone
try:
    from zoneinfo import ZoneInfo
except ImportError:
    # Fallback for Python < 3.9
    try:
        from backports.zoneinfo import ZoneInfo
    except ImportError:
        ZoneInfo = None
from flask import Flask, jsonify, request
from flask_cors import CORS
from dotenv import load_dotenv
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import GetOrdersRequest
from alpaca.trading.enums import QueryOrderStatus, OrderSide
from alpaca.data.historical import StockHistoricalDataClient, CryptoHistoricalDataClient
from pathlib import Path
from agent_baselines import get_baseline, get_baseline_start_datetime

# Load .env from the backend directory, not current working directory
env_path = Path(__file__).parent / '.env'
load_dotenv(dotenv_path=env_path)

app = Flask(__name__)
CORS(app)

# Alpaca API credentials from environment variables (Project 1 - Stocks)
ALPACA_API_KEY = os.getenv('ALPACA_API_KEY')
ALPACA_SECRET_KEY = os.getenv('ALPACA_SECRET_KEY')
ALPACA_BASE_URL = os.getenv('ALPACA_BASE_URL', 'https://paper-api.alpaca.markets')

# Alpaca API credentials for Project 2 (Crypto)
ALPACA_API_KEY_2 = os.getenv('ALPACA_API_KEY_2')
ALPACA_SECRET_KEY_2 = os.getenv('ALPACA_SECRET_KEY_2')
ALPACA_BASE_URL_2 = os.getenv('ALPACA_BASE_URL_2', 'https://paper-api.alpaca.markets')

# Determine if paper trading (better logic)
IS_PAPER = 'paper' in ALPACA_BASE_URL.lower()
IS_PAPER_2 = 'paper' in ALPACA_BASE_URL_2.lower()

# Initialize Alpaca clients (Project 1 - Stocks)
trading_client = None
data_client = None

# Initialize Alpaca clients (Project 2 - Crypto)
trading_client_2 = None
data_client_2 = None

try:
    if ALPACA_API_KEY and ALPACA_SECRET_KEY:
        trading_client = TradingClient(ALPACA_API_KEY, ALPACA_SECRET_KEY, paper=IS_PAPER)
        data_client = StockHistoricalDataClient(ALPACA_API_KEY, ALPACA_SECRET_KEY)
        print(f"Alpaca API (Project 1 - Stocks) initialized successfully (Paper: {IS_PAPER})")
    else:
        print("Warning: Alpaca API credentials not found. Set ALPACA_API_KEY and ALPACA_SECRET_KEY environment variables.")
except Exception as e:
    print(f"Error initializing Alpaca API (Project 1): {e}")
    import traceback
    traceback.print_exc()

try:
    if ALPACA_API_KEY_2 and ALPACA_SECRET_KEY_2:
        trading_client_2 = TradingClient(ALPACA_API_KEY_2, ALPACA_SECRET_KEY_2, paper=IS_PAPER_2)
        data_client_2 = CryptoHistoricalDataClient(ALPACA_API_KEY_2, ALPACA_SECRET_KEY_2)
        print(f"Alpaca API (Project 2 - Crypto) initialized successfully (Paper: {IS_PAPER_2})")
    else:
        print("Warning: Alpaca API credentials for Project 2 not found. Set ALPACA_API_KEY_2 and ALPACA_SECRET_KEY_2 environment variables.")
except Exception as e:
    print(f"Error initializing Alpaca API (Project 2): {e}")
    import traceback
    traceback.print_exc()


def get_alpaca_orders(limit=100, project=1):
    """Fetch filled orders (trades) from Alpaca and combine with positions.
    
    Args:
        limit: Maximum number of orders to fetch
        project: Project number (1 or 2) for baseline filtering
    """
    if not trading_client:
        print("No trading client available")
        return []
    
    try:
        # Get baseline start datetime for filtering
        baseline_start = get_baseline_start_datetime(project)
        
        # Get all orders and positions
        request_params = GetOrdersRequest(
            status=QueryOrderStatus.ALL,
            limit=limit,
            nested=True
        )
        orders = trading_client.get_orders(request_params)
        positions = get_alpaca_positions()
        
        # Filter orders to only include those after baseline
        filtered_orders = []
        for order in orders:
            if order.filled_qty and float(order.filled_qty) > 0:
                order_time = order.filled_at if hasattr(order, 'filled_at') and order.filled_at else order.created_at
                if order_time and order_time >= baseline_start:
                    filtered_orders.append(order)
        
        orders = filtered_orders
        print(f"Fetched {len(orders)} orders after baseline ({baseline_start.isoformat()}) and {len(positions)} positions from Alpaca")
        
        # Create a map of current positions by symbol
        position_map = {pos['symbol']: pos for pos in positions}
        
        # Count buy orders for total trades calculation
        buy_orders_count = 0
        
        # Group orders by symbol to match buys and sells
        orders_by_symbol = {}
        for order in orders:
            if order.filled_qty and float(order.filled_qty) > 0:
                symbol = order.symbol
                if symbol not in orders_by_symbol:
                    orders_by_symbol[symbol] = []
                orders_by_symbol[symbol].append(order)
        
        # Convert to trades - match buy/sell pairs or use positions for open trades
        trades = []
        
        # Helper function to get the best available time from an order (filled_at > created_at)
        # Also handles timezone conversion - Alpaca returns UTC, we need to ensure proper handling
        def get_order_time(order):
            if hasattr(order, 'filled_at') and order.filled_at:
                return order.filled_at
            return order.created_at
        
        # Helper function to convert datetime to ISO string, handling timezones properly
        def datetime_to_iso(dt):
            if dt is None:
                return None
            # If it's timezone-aware, convert to UTC explicitly, then format
            if hasattr(dt, 'tzinfo') and dt.tzinfo is not None:
                # Convert to UTC if not already
                utc_dt = dt.astimezone(timezone.utc) if dt.tzinfo != timezone.utc else dt
                # Return ISO format with UTC timezone (e.g., "2024-12-19T14:00:00+00:00")
                return utc_dt.isoformat()
            # If it's naive (no timezone), assume UTC and add 'Z' suffix
            if hasattr(dt, 'isoformat'):
                return dt.isoformat() + 'Z'
            return str(dt)
        
        # First, add open positions as trades
        for symbol, position in position_map.items():
            # Default to yesterday midnight (fixed time, not current time) if we can't find order
            entry_time_fallback = (datetime.now() - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            entry_time = None
            found_order = False
            fallback_used = False
            
            # Try to find the most recent buy order for this position
            if symbol in orders_by_symbol:
                all_orders = orders_by_symbol[symbol]
                print(f"DEBUG OPEN POSITION: symbol={symbol}")
                print(f"  Found {len(all_orders)} order(s) for this symbol")
                
                # Log all orders to see what we have
                for idx, order in enumerate(all_orders):
                    order_side = str(order.side).lower()
                    if hasattr(order.side, 'value'):
                        order_side = order.side.value.lower()
                    order_side_raw = order.side
                    filled_at_val = order.filled_at if hasattr(order, 'filled_at') and order.filled_at else None
                    created_at_val = order.created_at if hasattr(order, 'created_at') else None
                    print(f"  Order {idx + 1}: side={order_side} (raw: {order_side_raw}), filled_at={filled_at_val}, created_at={created_at_val}")
                
                # Try multiple ways to match buy orders
                buy_orders = []
                for o in all_orders:
                    side = str(o.side).lower()
                    if hasattr(o.side, 'value'):
                        side = o.side.value.lower()
                    # Also check if it's an enum or object
                    if side == 'buy' or side == 'buy_order' or (hasattr(o.side, 'value') and o.side.value.lower() == 'buy'):
                        buy_orders.append(o)
                
                if buy_orders:
                    latest_buy = max(buy_orders, key=lambda x: get_order_time(x))
                    entry_time = get_order_time(latest_buy)
                    found_order = True
                    
                    # Debug logging for all open positions
                    filled_at_val = latest_buy.filled_at if hasattr(latest_buy, 'filled_at') and latest_buy.filled_at else None
                    created_at_val = latest_buy.created_at if hasattr(latest_buy, 'created_at') else None
                    print(f"  ✓ Found {len(buy_orders)} buy order(s) - using latest")
                    print(f"    latest_buy.filled_at={filled_at_val} (type: {type(filled_at_val)})")
                    if filled_at_val:
                        print(f"      filled_at raw value: {filled_at_val}, hour={filled_at_val.hour if hasattr(filled_at_val, 'hour') else 'N/A'}, minute={filled_at_val.minute if hasattr(filled_at_val, 'minute') else 'N/A'}")
                    print(f"    latest_buy.created_at={created_at_val} (type: {type(created_at_val)})")
                    if created_at_val and not filled_at_val:
                        print(f"      created_at raw value: {created_at_val}, hour={created_at_val.hour if hasattr(created_at_val, 'hour') else 'N/A'}, minute={created_at_val.minute if hasattr(created_at_val, 'minute') else 'N/A'}")
                    print(f"    get_order_time returned: {entry_time} (type: {type(entry_time)})")
                    if entry_time:
                        print(f"      entry_time hour={entry_time.hour if hasattr(entry_time, 'hour') else 'N/A'}, minute={entry_time.minute if hasattr(entry_time, 'minute') else 'N/A'}, tzinfo={entry_time.tzinfo if hasattr(entry_time, 'tzinfo') else 'N/A'}")
                else:
                    # If no buy orders detected but we have orders and an open position, 
                    # use the most recent order anyway (open position means there was a buy)
                    print(f"  ⚠ No buy orders detected by side matching, but we have {len(all_orders)} order(s) for open position")
                    print(f"  Using most recent order (open position indicates this is from a buy)...")
                    latest_order = max(all_orders, key=lambda x: get_order_time(x))
                    entry_time = get_order_time(latest_order)
                    
                    if entry_time:
                        found_order = True
                        filled_at_val = latest_order.filled_at if hasattr(latest_order, 'filled_at') and latest_order.filled_at else None
                        created_at_val = latest_order.created_at if hasattr(latest_order, 'created_at') else None
                        order_side = str(latest_order.side)
                        if hasattr(latest_order.side, 'value'):
                            order_side = latest_order.side.value
                        print(f"  ✓ Using latest order: side={order_side}, filled_at={filled_at_val}, created_at={created_at_val}")
                        if filled_at_val:
                            print(f"    filled_at hour={filled_at_val.hour if hasattr(filled_at_val, 'hour') else 'N/A'}, minute={filled_at_val.minute if hasattr(filled_at_val, 'minute') else 'N/A'}")
                        elif created_at_val:
                            print(f"    created_at hour={created_at_val.hour if hasattr(created_at_val, 'hour') else 'N/A'}, minute={created_at_val.minute if hasattr(created_at_val, 'minute') else 'N/A'}")
                        print(f"    entry_time: {entry_time}, hour={entry_time.hour if hasattr(entry_time, 'hour') else 'N/A'}, minute={entry_time.minute if hasattr(entry_time, 'minute') else 'N/A'}, tzinfo={entry_time.tzinfo if hasattr(entry_time, 'tzinfo') else 'N/A'}")
                    else:
                        entry_time = entry_time_fallback
                        fallback_used = True
                        print(f"  ⚠ No valid time found in order, using fallback")
            else:
                entry_time = entry_time_fallback
                fallback_used = True
                print(f"DEBUG OPEN POSITION: symbol={symbol} - ⚠ Not in orders_by_symbol, using fallback")
            
            entry_time_str = datetime_to_iso(entry_time)
            if found_order:
                print(f"  final_entry_time_str={entry_time_str}")
            else:
                print(f"  fallback_entry_time_str={entry_time_str} (FIXED MIDNIGHT - will not update)")
            
            trade = {
                'symbol': symbol,
                'side': 'buy',
                'entry_price': position['avg_entry_price'],
                'exit_price': None,  # No exit price for open positions
                'shares': position['qty'],
                'pnl': position['unrealized_pl'],
                'pnl_percent': position['unrealized_plpc'] * 100,
                'entry_time': entry_time_str,
                'exit_time': None,
                'status': 'open',
                'current_price': position['current_price']
            }
            trades.append(trade)
        
        # Count buy orders from all symbols (including those with open positions)
        # #region agent log
        buy_order_details = []
        # #endregion
        for symbol, symbol_orders in orders_by_symbol.items():
            for order in symbol_orders:
                side = str(order.side).lower()
                if hasattr(order.side, 'value'):
                    side = order.side.value.lower()
                
                # Count buy orders
                if side == 'buy' or side == 'buy_order':
                    buy_orders_count += 1
                    # #region agent log
                    buy_order_details.append({'symbol': order.symbol, 'side': side, 'qty': float(order.filled_qty) if order.filled_qty else 0})
                    # #endregion
        # #region agent log
        with open(r'c:\Users\mason\OneDrive\Desktop\Cursor\website\.cursor\debug.log', 'a') as f:
            f.write(json.dumps({'sessionId': 'debug-session', 'runId': 'run1', 'hypothesisId': 'A', 'location': 'app.py:287', 'message': 'Project 1 buy orders counted', 'data': {'buy_orders_count': buy_orders_count, 'total_orders': len(orders), 'buy_order_details': buy_order_details}, 'timestamp': int(datetime.now().timestamp() * 1000)}) + '\n')
        # #endregion
        
        # Then, process closed trades by matching buy/sell orders
        for symbol, symbol_orders in orders_by_symbol.items():
            # Skip if we already added this as an open position
            if symbol in position_map:
                continue
            
            # Sort orders by time (use filled_at if available, otherwise created_at)
            symbol_orders.sort(key=lambda x: get_order_time(x))
            
            # Match buy and sell orders
            buy_stack = []
            for order in symbol_orders:
                side = str(order.side).lower()
                if hasattr(order.side, 'value'):
                    side = order.side.value.lower()
                
                filled_qty = float(order.filled_qty)
                avg_fill_price = float(order.filled_avg_price) if order.filled_avg_price else 0
                
                if side == 'buy':
                    buy_stack.append({
                        'qty': filled_qty,
                        'price': avg_fill_price,
                        'time': get_order_time(order)
                    })
                elif side == 'sell' and buy_stack:
                    # Match sell with buy orders
                    remaining_sell_qty = filled_qty
                    while remaining_sell_qty > 0 and buy_stack:
                        buy_order = buy_stack[0]
                        matched_qty = min(remaining_sell_qty, buy_order['qty'])
                        
                        # Calculate P&L
                        pnl = (avg_fill_price - buy_order['price']) * matched_qty
                        pnl_percent = ((avg_fill_price - buy_order['price']) / buy_order['price']) * 100
                        
                        entry_time = buy_order['time']
                        # Use filled_at if available, otherwise created_at (get_order_time handles this)
                        exit_time = get_order_time(order)
                        
                        entry_time_str = datetime_to_iso(entry_time)
                        exit_time_str = datetime_to_iso(exit_time)
                        
                        # Debug logging for all closed trades
                        filled_at_val = order.filled_at if hasattr(order, 'filled_at') and order.filled_at else None
                        created_at_val = order.created_at if hasattr(order, 'created_at') else None
                        buy_filled_at_val = None
                        buy_created_at_val = None
                        if hasattr(buy_order, 'get') or isinstance(buy_order.get('time') if isinstance(buy_order, dict) else None, datetime):
                            # Extract from buy_order dict if we stored the original order
                            pass
                        
                        print(f"DEBUG CLOSED TRADE: symbol={symbol}, side={side}, matched_qty={matched_qty}")
                        print(f"  SELL order.filled_at={filled_at_val} (type: {type(filled_at_val)})")
                        if filled_at_val:
                            print(f"    SELL filled_at hour={filled_at_val.hour if hasattr(filled_at_val, 'hour') else 'N/A'}, minute={filled_at_val.minute if hasattr(filled_at_val, 'minute') else 'N/A'}")
                        print(f"  SELL order.created_at={created_at_val} (type: {type(created_at_val)})")
                        print(f"  get_order_time(exit) returned: {exit_time} (type: {type(exit_time)})")
                        if exit_time:
                            print(f"    exit_time hour={exit_time.hour if hasattr(exit_time, 'hour') else 'N/A'}, minute={exit_time.minute if hasattr(exit_time, 'minute') else 'N/A'}, tzinfo={exit_time.tzinfo if hasattr(exit_time, 'tzinfo') else 'N/A'}")
                        print(f"  final_exit_time_str={exit_time_str}")
                        print(f"  BUY entry_time from buy_order: {entry_time} (type: {type(entry_time)})")
                        if entry_time:
                            print(f"    entry_time hour={entry_time.hour if hasattr(entry_time, 'hour') else 'N/A'}, minute={entry_time.minute if hasattr(entry_time, 'minute') else 'N/A'}, tzinfo={entry_time.tzinfo if hasattr(entry_time, 'tzinfo') else 'N/A'}")
                        print(f"  final_entry_time_str={entry_time_str}")
                        
                        trade = {
                            'symbol': symbol,
                            'side': 'sell',
                            'entry_price': buy_order['price'],
                            'exit_price': avg_fill_price,
                            'shares': matched_qty,
                            'pnl': round(pnl, 2),
                            'pnl_percent': round(pnl_percent, 2),
                            'entry_time': entry_time_str,
                            'exit_time': exit_time_str,
                            'status': 'closed'
                        }
                        trades.append(trade)
                        
                        # Update buy stack
                        buy_order['qty'] -= matched_qty
                        if buy_order['qty'] <= 0:
                            buy_stack.pop(0)
                        remaining_sell_qty -= matched_qty
        
        # Sort by exit_time or entry_time (most recent first)
        trades.sort(key=lambda x: x.get('exit_time') or x.get('entry_time', ''), reverse=True)
        print(f"Converted to {len(trades)} trades ({len([t for t in trades if t['status'] == 'open'])} open, {len([t for t in trades if t['status'] == 'closed'])} closed), {buy_orders_count} buy orders")
        # #region agent log
        with open(r'c:\Users\mason\OneDrive\Desktop\Cursor\website\.cursor\debug.log', 'a') as f:
            f.write(json.dumps({'sessionId': 'debug-session', 'runId': 'run1', 'hypothesisId': 'A', 'location': 'app.py:388', 'message': 'Project 1 final buy_orders_count', 'data': {'buy_orders_count': buy_orders_count, 'total_trades': len(trades), 'open_trades': len([t for t in trades if t['status'] == 'open']), 'closed_trades': len([t for t in trades if t['status'] == 'closed'])}, 'timestamp': int(datetime.now().timestamp() * 1000)}) + '\n')
        # #endregion
        return trades, buy_orders_count
    except Exception as e:
        print(f"Error fetching Alpaca orders: {e}")
        import traceback
        traceback.print_exc()
        return [], 0


def get_alpaca_account():
    """Get account information from Alpaca."""
    if not trading_client:
        return None
    
    try:
        account = trading_client.get_account()
        return {
            'equity': float(account.equity) if account.equity else 0,
            'cash': float(account.cash) if account.cash else 0,
            'buying_power': float(account.buying_power) if account.buying_power else 0,
            'portfolio_value': float(account.portfolio_value) if account.portfolio_value else 0
        }
    except Exception as e:
        print(f"Error fetching Alpaca account: {e}")
        import traceback
        traceback.print_exc()
        return None


def get_alpaca_positions():
    """Get current positions from Alpaca."""
    if not trading_client:
        return []
    
    try:
        positions = trading_client.get_all_positions()
        return [
            {
                'symbol': pos.symbol,
                'qty': float(pos.qty),
                'avg_entry_price': float(pos.avg_entry_price),
                'current_price': float(pos.current_price),
                'market_value': float(pos.market_value),
                'unrealized_pl': float(pos.unrealized_pl),
                'unrealized_plpc': float(pos.unrealized_plpc)
            }
            for pos in positions
        ]
    except Exception as e:
        print(f"Error fetching Alpaca positions: {e}")
        return []


# ============================================================================
# PROJECT 2 (CRYPTO) FUNCTIONS
# ============================================================================

def get_alpaca_orders_2(limit=100):
    """Fetch filled orders (trades) from Alpaca Project 2 (Crypto) and combine with positions.
    
    Returns:
        tuple: (trades_list, buy_orders_count) where buy_orders_count is the number of buy orders
    """
    if not trading_client_2:
        print("No trading client available for Project 2")
        return [], 0
    
    try:
        # Get baseline start datetime for filtering
        baseline_start = get_baseline_start_datetime(2)
        
        # Get all orders and positions
        request_params = GetOrdersRequest(
            status=QueryOrderStatus.ALL,
            limit=limit,
            nested=True
        )
        orders = trading_client_2.get_orders(request_params)
        positions = get_alpaca_positions_2()
        
        # Filter orders to only include those after baseline
        filtered_orders = []
        for order in orders:
            if order.filled_qty and float(order.filled_qty) > 0:
                order_time = order.filled_at if hasattr(order, 'filled_at') and order.filled_at else order.created_at
                if order_time and order_time >= baseline_start:
                    filtered_orders.append(order)
        
        orders = filtered_orders
        
        # Create a map of current positions by symbol
        position_map = {pos['symbol']: pos for pos in positions}
        
        print(f"Project 2: Fetched {len(orders)} total orders and {len(positions)} positions from Alpaca")
        
        # Count buy orders for total trades calculation
        buy_orders_count = 0
        
        # Helper function to get the best available time from an order (created_at for sorting)
        def get_order_created_time(order):
            if hasattr(order, 'created_at') and order.created_at:
                return order.created_at
            # Fallback to filled_at if created_at not available
            if hasattr(order, 'filled_at') and order.filled_at:
                return order.filled_at
            return datetime.now(timezone.utc)
        
        # Helper function to convert datetime to ISO string, handling timezones properly
        def datetime_to_iso(dt):
            if dt is None:
                return None
            # If datetime is timezone-aware, convert to UTC
            if hasattr(dt, 'tzinfo') and dt.tzinfo is not None:
                utc_dt = dt.astimezone(timezone.utc)
                # Return ISO format with Z suffix for UTC
                iso_str = utc_dt.strftime('%Y-%m-%dT%H:%M:%S')
                # Add microseconds if present
                if utc_dt.microsecond:
                    iso_str += f'.{utc_dt.microsecond:06d}'[:4]  # First 3 digits of microseconds
                return iso_str + 'Z'
            # If datetime is naive, assume it's UTC and add Z
            if hasattr(dt, 'isoformat'):
                return dt.isoformat() + 'Z'
            return str(dt)
        
        # Helper function to get order time for sorting (filled_at > created_at)
        def get_order_time(order):
            if hasattr(order, 'filled_at') and order.filled_at:
                return order.filled_at
            return order.created_at if hasattr(order, 'created_at') and order.created_at else datetime.now(timezone.utc)
        
        # For Recent Transactions: show ALL individual orders (both buys and sells)
        trades = []
        
        for order in orders:
            if not order.filled_qty or float(order.filled_qty) <= 0:
                continue
            
            side = str(order.side).lower()
            if hasattr(order.side, 'value'):
                side = order.side.value.lower()
            
            filled_qty = float(order.filled_qty)
            avg_fill_price = float(order.filled_avg_price) if order.filled_avg_price else 0
            order_time = get_order_time(order)
            order_time_str = datetime_to_iso(order_time)
            
            # Count buy orders
            if side == 'buy' or side == 'buy_order':
                buy_orders_count += 1
                # #region agent log
                with open(r'c:\Users\mason\OneDrive\Desktop\Cursor\website\.cursor\debug.log', 'a') as f:
                    f.write(json.dumps({'sessionId': 'debug-session', 'runId': 'run1', 'hypothesisId': 'B', 'location': 'app.py:536', 'message': 'Project 2 buy order counted', 'data': {'symbol': order.symbol, 'side': side, 'qty': filled_qty, 'buy_orders_count': buy_orders_count}, 'timestamp': int(datetime.now().timestamp() * 1000)}) + '\n')
                # #endregion
            
            # Check if this symbol has an open position
            symbol = order.symbol
            is_open = symbol in position_map
            
            trade = {
                'symbol': symbol,
                'side': side if side in ['buy', 'sell'] else ('buy' if 'buy' in side else 'sell'),
                'qty': filled_qty,
                'entry_price': avg_fill_price,
                'exit_price': avg_fill_price,  # Same as entry for individual orders
                'pnl': 0,  # P&L calculated separately for stats
                'pnl_percent': 0,
                'entry_time': order_time_str,
                'exit_time': order_time_str,
                'status': 'open' if is_open else 'closed'
            }
            trades.append(trade)
        
        # Sort trades by time (most recent first) for display
        def get_sort_time(trade):
            time_str = trade.get('entry_time', '') or trade.get('exit_time', '')
            if not time_str:
                return datetime.min
            try:
                # Parse ISO format datetime
                if 'T' in time_str:
                    time_str_clean = time_str.replace('Z', '+00:00')
                    try:
                        dt = datetime.fromisoformat(time_str_clean)
                    except:
                        dt = datetime.fromisoformat(time_str_clean.replace('+00:00', ''))
                        if time_str.endswith('Z'):
                            dt = dt.replace(tzinfo=timezone.utc)
                    return dt
                else:
                    return datetime.fromisoformat(time_str)
            except:
                return datetime.min
        
        trades.sort(key=get_sort_time, reverse=True)
        print(f"Project 2: Showing {len(trades)} individual orders, {buy_orders_count} buy orders")
        # #region agent log
        with open(r'c:\Users\mason\OneDrive\Desktop\Cursor\website\.cursor\debug.log', 'a') as f:
            f.write(json.dumps({'sessionId': 'debug-session', 'runId': 'run1', 'hypothesisId': 'A', 'location': 'app.py:578', 'message': 'Project 2 final buy_orders_count', 'data': {'buy_orders_count': buy_orders_count, 'total_trades': len(trades), 'buy_trades': len([t for t in trades if t.get('side', '').lower() == 'buy']), 'sell_trades': len([t for t in trades if t.get('side', '').lower() == 'sell'])}, 'timestamp': int(datetime.now().timestamp() * 1000)}) + '\n')
        # #endregion
        return trades, buy_orders_count
    except Exception as e:
        print(f"Error fetching Alpaca orders (Project 2): {e}")
        import traceback
        traceback.print_exc()
        return [], 0
    

def get_alpaca_account_2():
    """Get account information from Alpaca Project 2."""
    if not trading_client_2:
        return None
    
    try:
        account = trading_client_2.get_account()
        return {
            'equity': float(account.equity) if account.equity else 0,
            'cash': float(account.cash) if account.cash else 0,
            'buying_power': float(account.buying_power) if account.buying_power else 0,
            'portfolio_value': float(account.portfolio_value) if account.portfolio_value else 0
        }
    except Exception as e:
        print(f"Error fetching Alpaca account (Project 2): {e}")
        import traceback
        traceback.print_exc()
        return None


def get_alpaca_positions_2():
    """Get current positions from Alpaca Project 2."""
    if not trading_client_2:
        return []
    
    try:
        positions = trading_client_2.get_all_positions()
        return [
            {
                'symbol': pos.symbol,
                'qty': float(pos.qty),
                'avg_entry_price': float(pos.avg_entry_price),
                'current_price': float(pos.current_price),
                'market_value': float(pos.market_value),
                'unrealized_pl': float(pos.unrealized_pl),
                'unrealized_plpc': float(pos.unrealized_plpc)
            }
            for pos in positions
        ]
    except Exception as e:
        print(f"Error fetching Alpaca positions (Project 2): {e}")
        import traceback
        traceback.print_exc()
        return []


def get_live_portfolio_equity_2():
    """Compute live portfolio equity for Project 2 (Crypto) using extended-hours prices.
    
    Returns:
        dict: {
            'live_equity': float,
            'as_of_timestamp': int (milliseconds),
            'prices_used': dict mapping symbol to latest_price
        }
    """
    if not trading_client_2:
        print("LIVE_EQUITY (Project 2): Missing trading_client_2")
        return None
    
    try:
        # PRIMARY: Use Alpaca's account equity directly - this is the official source that includes extended-hours
        account = get_alpaca_account_2()
        if account and account.get('equity') is not None:
            account_equity = float(account['equity'])
            print(f"LIVE_EQUITY (Project 2): Using account equity directly: ${account_equity} (includes extended-hours)")
            
            # Still get positions for prices_used logging
            positions = get_alpaca_positions_2()
            prices_used = {}
            if data_client_2:
                from alpaca.data.requests import CryptoLatestTradeRequest
                for position in positions:
                    symbol = position['symbol']
                    try:
                        # Try to get latest extended-hours price for logging
                        latest_trade_req = CryptoLatestTradeRequest(symbol_or_symbols=[symbol])
                        latest_trades = data_client_2.get_crypto_latest_trade(latest_trade_req)
                        if symbol in latest_trades and latest_trades[symbol]:
                            prices_used[symbol] = float(latest_trades[symbol].price)
                        else:
                            prices_used[symbol] = float(position['current_price'])
                    except:
                        prices_used[symbol] = float(position['current_price'])
            else:
                for position in positions:
                    prices_used[position['symbol']] = float(position['current_price'])
            
            # Get the actual timestamp from account or use current time
            as_of_timestamp = int(datetime.now().timestamp() * 1000)
            
            return {
                'live_equity': round(account_equity, 2),
                'as_of_timestamp': as_of_timestamp,
                'prices_used': prices_used
            }
        
        # FALLBACK: Calculate from positions + cash (if account equity not available)
        account = get_alpaca_account_2()
        if not account:
            print("LIVE_EQUITY (Project 2): Could not get account")
            return None
        
        cash = account.get('cash', 0)
        positions = get_alpaca_positions_2()
        total_market_value = 0
        prices_used = {}
        latest_timestamp = 0
        
        if data_client_2:
            from alpaca.data.requests import CryptoLatestTradeRequest
            for position in positions:
                symbol = position['symbol']
                qty = position['qty']
                latest_price = None
                trade_timestamp = 0
                
                try:
                    # Get latest trade (crypto is 24/7)
                    latest_trade_req = CryptoLatestTradeRequest(symbol_or_symbols=[symbol])
                    latest_trades = data_client_2.get_crypto_latest_trade(latest_trade_req)
                    
                    if symbol in latest_trades and latest_trades[symbol]:
                        latest_trade = latest_trades[symbol]
                        latest_price = float(latest_trade.price)
                        # Handle timestamp
                        if hasattr(latest_trade.timestamp, 'timestamp'):
                            trade_timestamp = int(latest_trade.timestamp.timestamp() * 1000)
                        elif isinstance(latest_trade.timestamp, (int, float)):
                            trade_timestamp = int(latest_trade.timestamp * 1000) if latest_trade.timestamp < 10000000000 else int(latest_trade.timestamp)
                        else:
                            trade_timestamp = int(datetime.now().timestamp() * 1000)
                        print(f"LIVE_EQUITY (Project 2): {symbol} - Latest trade price: ${latest_price} (timestamp: {trade_timestamp})")
                except Exception as e:
                    print(f"LIVE_EQUITY (Project 2): Error fetching latest trade for {symbol}: {e}")
                
                # Fallback to position's current_price
                if latest_price is None:
                    latest_price = float(position['current_price'])
                    print(f"LIVE_EQUITY (Project 2): {symbol} - Using position current_price: ${latest_price} (fallback)")
                
                market_value = qty * latest_price
                total_market_value += market_value
                prices_used[symbol] = latest_price
                print(f"LIVE_EQUITY (Project 2): {symbol} - qty={qty}, price=${latest_price}, market_value=${market_value}")
                
                if trade_timestamp > latest_timestamp:
                    latest_timestamp = trade_timestamp
        
        live_equity = cash + total_market_value
        
        # Use the latest trade timestamp, or current time if no trades
        as_of_timestamp = latest_timestamp if latest_timestamp > 0 else int(datetime.now().timestamp() * 1000)
        
        print(f"LIVE_EQUITY (Project 2): cash=${cash}, total_market_value=${total_market_value}, live_equity=${live_equity}")
        print(f"LIVE_EQUITY (Project 2): prices_used={prices_used}")
        
        return {
            'live_equity': round(live_equity, 2),
            'as_of_timestamp': as_of_timestamp,
            'prices_used': prices_used
        }
    except Exception as e:
        print(f"Error computing live portfolio equity (Project 2): {e}")
        import traceback
        traceback.print_exc()
        return None


def get_alpaca_portfolio_history_2(timeframe='all'):
    """Fetch portfolio history (equity curve) from Alpaca API for Project 2 (Crypto)."""
    if not trading_client_2 or not ALPACA_API_KEY_2 or not ALPACA_SECRET_KEY_2:
        print("No trading client or API credentials available for Project 2")
        return []
    
    try:
        now = datetime.now()
        
        # Map our timeframe to Alpaca's period and timeframe parameters
        # Crypto trades 24/7, so no weekend handling needed
        if timeframe == 'day':
            date_end = now.strftime('%Y-%m-%d')
            period = '1D'
            alpaca_timeframe = '1Min'  # 1-minute intervals for intraday
            extended_hours = 'true'
        elif timeframe == 'week':
            period = '1W'
            alpaca_timeframe = '15Min'  # 15-minute intervals for intraday
            date_end = now.strftime('%Y-%m-%d')
            extended_hours = 'true'
        elif timeframe == 'month':
            period = '29D'  # 29 days (approximately 1 month)
            alpaca_timeframe = '1D'  # Daily points
            date_end = now.strftime('%Y-%m-%d')
            extended_hours = 'false'  # No effect for daily
        elif timeframe == '3m':
            period = '3M'
            alpaca_timeframe = '1D'  # Daily points
            date_end = now.strftime('%Y-%m-%d')
            extended_hours = 'false'  # No effect for daily
        elif timeframe == 'year':
            period = '1A'  # 1 year
            alpaca_timeframe = '1D'  # Daily points
            date_end = now.strftime('%Y-%m-%d')
            extended_hours = 'false'  # No effect for daily
        elif timeframe == 'ytd':
            # For YTD, calculate days since Jan 1
            year_start = datetime(now.year, 1, 1)
            days_since_start = (now - year_start).days
            if days_since_start <= 29:
                period = f'{days_since_start}D'
                alpaca_timeframe = '1H'
                extended_hours = 'true'
            else:
                period = '1A'
                alpaca_timeframe = '1D'
                extended_hours = 'false'
            date_end = now.strftime('%Y-%m-%d')
        else:  # 'all'
            period = '1A'  # Max 1 year for now
            alpaca_timeframe = '1D'  # Daily points
            date_end = now.strftime('%Y-%m-%d')
            extended_hours = 'false'  # No effect for daily
        
        # Make API request to Alpaca portfolio history endpoint
        url = f"{ALPACA_BASE_URL_2}/v2/account/portfolio/history"
        headers = {
            "APCA-API-KEY-ID": ALPACA_API_KEY_2,
            "APCA-API-SECRET-KEY": ALPACA_SECRET_KEY_2
        }
        params = {
            "period": period,
            "timeframe": alpaca_timeframe,
            "date_end": date_end,
            "extended_hours": extended_hours
        }
        
        print(f"Project 2: Fetching portfolio history: period={period}, timeframe={alpaca_timeframe}, date_end={date_end}, extended_hours={extended_hours}")
        response = requests.get(url, headers=headers, params=params)
        
        if response.status_code == 200:
            data = response.json()
            timestamps = data.get('timestamp', [])
            equity_values = data.get('equity', [])
            profit_loss = data.get('profit_loss', [])
            
            print(f"Project 2 DEBUG [{timeframe}]: timestamps.length={len(timestamps)}, equity.length={len(equity_values)}")
            
            if not timestamps or not equity_values:
                print("Project 2: No portfolio history data returned from Alpaca")
                return []
            
            if len(timestamps) != len(equity_values):
                print(f"Project 2 WARNING: Mismatch - {len(timestamps)} timestamps but {len(equity_values)} equity values")
            
            is_month_plus = timeframe in ['month', '3m', 'year', 'ytd', 'all']
            
            # Filter to only include points >= baseline
            baseline_start = get_baseline_start_datetime(2)
            baseline_ts_ms = int(baseline_start.timestamp() * 1000)
            
            performance_data = []
            equity_values_used = []
            
            for i in range(len(timestamps)):
                timestamp = timestamps[i]
                
                if isinstance(timestamp, (int, float)):
                    timestamp_ms = int(timestamp * 1000) if timestamp < 1e10 else int(timestamp)
                    dt = datetime.fromtimestamp(timestamp_ms / 1000)
                else:
                    try:
                        dt = datetime.fromisoformat(str(timestamp).replace('Z', '+00:00'))
                        if dt.tzinfo:
                            dt = dt.replace(tzinfo=None)
                        timestamp_ms = int(dt.timestamp() * 1000)
                    except Exception as e:
                        print(f"Project 2: Error parsing timestamp {timestamp}: {e}")
                        continue
                
                # Filter out points before baseline
                if timestamp_ms < baseline_ts_ms:
                    continue
                
                equity = float(equity_values[i]) if i < len(equity_values) else None
                if equity is None:
                    continue
                
                equity_values_used.append(equity)
                
                # For month+ timeframes: use raw equity, calculate returns relative to first equity value
                # For day/week: can use profit_loss if available, otherwise calculate from equity
                if is_month_plus:
                    # Use first equity value as baseline for returns calculation only
                    first_equity = float(equity_values[0]) if equity_values else equity
                    returns = equity - first_equity
                else:
                    # For day/week, use profit_loss if available
                    pnl = float(profit_loss[i]) if profit_loss and i < len(profit_loss) else None
                    if pnl is not None:
                        returns = pnl
                    else:
                        # Fallback: calculate from equity
                        first_equity = float(equity_values[0]) if equity_values else equity
                        returns = equity - first_equity
                
                # Format date based on timeframe
                if timeframe in ['day', 'week']:
                    # Include time for intraday
                    date_str = dt.strftime('%Y-%m-%dT%H:%M:%S')
                else:
                    # Date only for daily timeframes (month, 3m, year, ytd, all)
                    date_str = dt.strftime('%Y-%m-%d')
                
                performance_data.append({
                    'date': date_str,
                    'returns': round(returns, 2),
                    'equity': round(equity, 2),  # Use raw equity value, no normalization
                    'timestamp': timestamp_ms  # Already in milliseconds
                })
            
            # Part A: Log what Month+ data actually is (no guessing)
            if is_month_plus and equity_values_used:
                points_count = len(equity_values_used)
                min_value = min(equity_values_used)
                max_value = max(equity_values_used)
                unique_values_count = len(set(equity_values_used))
                first_value = equity_values_used[0]
                last_value = equity_values_used[-1]
                print(f"Project 2 MONTH_PLUS_DATA [{timeframe}]: points_count={points_count}, min_value={min_value}, max_value={max_value}, unique_values_count={unique_values_count}, first_value={first_value}, last_value={last_value}")
                if unique_values_count == 1:
                    print(f"Project 2 WARNING [{timeframe}]: All equity values are the same ({first_value}). This suggests we're plotting the wrong field or overwriting the series.")
            
            print(f"Project 2: Fetched {len(performance_data)} portfolio history points from Alpaca for {timeframe}")
            return performance_data
        else:
            print(f"Project 2: Error fetching portfolio history: {response.status_code} - {response.text}")
            return []
            
    except Exception as e:
        print(f"Project 2: Error fetching Alpaca portfolio history: {e}")
        import traceback
        traceback.print_exc()
        return []


def get_day_chart_live_value_2():
    """Get live value from Day chart's portfolio history for Project 2 (Crypto).
    
    Returns:
        tuple: (live_value: float, live_asof_timestamp_ms: int) or (None, None) if error
    """
    if not trading_client_2 or not ALPACA_API_KEY_2 or not ALPACA_SECRET_KEY_2:
        return None, None
    
    try:
        now = datetime.now()
        
        # Use same params as Day chart (crypto trades 24/7, no weekend handling)
        date_end = now.strftime('%Y-%m-%d')
        period = '1D'
        alpaca_timeframe = '1Min'
        extended_hours = 'true'
        
        # Make API request to Alpaca portfolio history endpoint
        url = f"{ALPACA_BASE_URL_2}/v2/account/portfolio/history"
        headers = {
            "APCA-API-KEY-ID": ALPACA_API_KEY_2,
            "APCA-API-SECRET-KEY": ALPACA_SECRET_KEY_2
        }
        params = {
            "period": period,
            "timeframe": alpaca_timeframe,
            "date_end": date_end,
            "extended_hours": extended_hours
        }
        
        response = requests.get(url, headers=headers, params=params)
        
        if response.status_code == 200:
            data = response.json()
            timestamps = data.get('timestamp', [])
            equity_values = data.get('equity', [])
            
            if not timestamps or not equity_values:
                return None, None
            
            live_value = float(equity_values[-1]) if equity_values else None
            last_timestamp = timestamps[-1] if timestamps else None
            
            if live_value is None or last_timestamp is None:
                return None, None
            
            # Convert timestamp to milliseconds
            if isinstance(last_timestamp, (int, float)):
                live_asof_timestamp_ms = int(last_timestamp * 1000)
            else:
                try:
                    dt = datetime.fromisoformat(str(last_timestamp).replace('Z', '+00:00'))
                    if dt.tzinfo:
                        dt = dt.replace(tzinfo=None)
                    live_asof_timestamp_ms = int(dt.timestamp() * 1000)
                except Exception as e:
                    print(f"Project 2: Error parsing timestamp {last_timestamp}: {e}")
                    return None, None
            
            return live_value, live_asof_timestamp_ms
        else:
            print(f"Project 2: Error fetching Day chart portfolio history: {response.status_code} - {response.text}")
            return None, None
            
    except Exception as e:
        print(f"Project 2: Error getting Day chart live value: {e}")
        import traceback
        traceback.print_exc()
        return None, None


# ============================================================================
# Removed Project 3 (Options) - all functions deleted

def get_last_trading_day(target_date):
    """Get the last trading day (weekday) on or before the target date."""
    current = target_date
    # Go back until we find a weekday (Monday=0, Sunday=6)
    while current.weekday() >= 5:  # Saturday=5, Sunday=6
        current = current - timedelta(days=1)
    return current


def get_live_portfolio_equity():
    """Compute live portfolio equity using extended-hours prices.
    
    Returns:
        dict: {
            'live_equity': float,
            'as_of_timestamp': int (milliseconds),
            'prices_used': dict mapping symbol to latest_price
        }
    """
    if not trading_client:
        print("LIVE_EQUITY: Missing trading_client")
        return None
    
    try:
        # PRIMARY: Use Alpaca's account equity directly - this is the official source that includes extended-hours
        account = get_alpaca_account()
        if account and account.get('equity') is not None:
            account_equity = float(account['equity'])
            print(f"LIVE_EQUITY: Using account equity directly: ${account_equity} (includes extended-hours)")
            
            # Still get positions for prices_used logging
            positions = get_alpaca_positions()
            prices_used = {}
            if data_client:
                from alpaca.data.requests import StockLatestTradeRequest
                for position in positions:
                    symbol = position['symbol']
                    try:
                        # Try to get latest extended-hours price for logging
                        latest_trade_req = StockLatestTradeRequest(symbol_or_symbols=[symbol], feed='iex')
                        latest_trades = data_client.get_stock_latest_trade(latest_trade_req)
                        if symbol in latest_trades and latest_trades[symbol]:
                            prices_used[symbol] = float(latest_trades[symbol].price)
                        else:
                            prices_used[symbol] = float(position['current_price'])
                    except:
                        prices_used[symbol] = float(position['current_price'])
            else:
                for position in positions:
                    prices_used[position['symbol']] = float(position['current_price'])
            
            # Get the actual timestamp from account or use current time
            # Alpaca account equity reflects the latest market snapshot (includes extended hours)
            # Use current time as the snapshot timestamp since account equity is live
            as_of_timestamp = int(datetime.now().timestamp() * 1000)
            
            # Try to get a more accurate timestamp from latest trades if available
            if data_client and positions:
                from alpaca.data.requests import StockLatestTradeRequest
                latest_timestamp = 0
                for position in positions:
                    symbol = position['symbol']
                    try:
                        latest_trade_req = StockLatestTradeRequest(symbol_or_symbols=[symbol], feed='iex')
                        latest_trades = data_client.get_stock_latest_trade(latest_trade_req)
                        if symbol in latest_trades and latest_trades[symbol]:
                            latest_trade = latest_trades[symbol]
                            if hasattr(latest_trade.timestamp, 'timestamp'):
                                trade_ts = int(latest_trade.timestamp.timestamp() * 1000)
                            elif isinstance(latest_trade.timestamp, (int, float)):
                                trade_ts = int(latest_trade.timestamp * 1000) if latest_trade.timestamp < 10000000000 else int(latest_trade.timestamp)
                            else:
                                trade_ts = 0
                            if trade_ts > latest_timestamp:
                                latest_timestamp = trade_ts
                    except:
                        pass
                
                if latest_timestamp > 0:
                    as_of_timestamp = latest_timestamp
            
            return {
                'live_equity': round(account_equity, 2),
                'as_of_timestamp': as_of_timestamp,
                'prices_used': prices_used
            }
        
        # FALLBACK: Manual calculation if account equity not available
        print("LIVE_EQUITY: Account equity not available, calculating manually...")
        cash = float(account['cash']) if account and account.get('cash') else 0.0
        print(f"LIVE_EQUITY: Cash = ${cash}")
        
        # Get all open positions
        positions = get_alpaca_positions()
        print(f"LIVE_EQUITY: Found {len(positions)} positions")
        
        # For each position, fetch latest trade price (extended-hours included)
        prices_used = {}
        total_market_value = 0.0
        latest_timestamp = 0
        
        if not data_client:
            print("LIVE_EQUITY: data_client not available, using position current_price")
            for position in positions:
                symbol = position['symbol']
                qty = float(position['qty'])
                latest_price = float(position['current_price'])
                market_value = qty * latest_price
                total_market_value += market_value
                prices_used[symbol] = latest_price
                print(f"LIVE_EQUITY: {symbol} - qty={qty}, price=${latest_price}, market_value=${market_value}")
        else:
            from alpaca.data.requests import StockLatestTradeRequest
            from alpaca.data.timeframe import TimeFrame
            
            for position in positions:
                symbol = position['symbol']
                qty = float(position['qty'])
                
                # Try to get latest trade price first (most accurate for extended hours)
                latest_price = None
                trade_timestamp = 0
                
                try:
                    # Get latest trade (includes extended hours) - IEX feed includes extended hours
                    latest_trade_req = StockLatestTradeRequest(symbol_or_symbols=[symbol], feed='iex')
                    latest_trades = data_client.get_stock_latest_trade(latest_trade_req)
                    
                    if symbol in latest_trades and latest_trades[symbol]:
                        latest_trade = latest_trades[symbol]
                        latest_price = float(latest_trade.price)
                        # Handle timestamp
                        if hasattr(latest_trade.timestamp, 'timestamp'):
                            trade_timestamp = int(latest_trade.timestamp.timestamp() * 1000)
                        elif isinstance(latest_trade.timestamp, (int, float)):
                            trade_timestamp = int(latest_trade.timestamp * 1000) if latest_trade.timestamp < 10000000000 else int(latest_trade.timestamp)
                        else:
                            trade_timestamp = int(datetime.now().timestamp() * 1000)
                        print(f"LIVE_EQUITY: {symbol} - Latest trade price: ${latest_price} (timestamp: {trade_timestamp})")
                except Exception as e:
                    print(f"LIVE_EQUITY: Error fetching latest trade for {symbol}: {e}")
                
                # Fallback to position's current_price
                if latest_price is None:
                    latest_price = float(position['current_price'])
                    print(f"LIVE_EQUITY: {symbol} - Using position current_price: ${latest_price} (fallback)")
                
                market_value = qty * latest_price
                total_market_value += market_value
                prices_used[symbol] = latest_price
                print(f"LIVE_EQUITY: {symbol} - qty={qty}, price=${latest_price}, market_value=${market_value}")
                
                if trade_timestamp > latest_timestamp:
                    latest_timestamp = trade_timestamp
        
        live_equity = cash + total_market_value
        
        # Use the latest trade timestamp, or current time if no trades
        as_of_timestamp = latest_timestamp if latest_timestamp > 0 else int(datetime.now().timestamp() * 1000)
        
        print(f"LIVE_EQUITY: cash=${cash}, total_market_value=${total_market_value}, live_equity=${live_equity}")
        print(f"LIVE_EQUITY: prices_used={prices_used}")
        
        return {
            'live_equity': round(live_equity, 2),
            'as_of_timestamp': as_of_timestamp,
            'prices_used': prices_used
        }
    except Exception as e:
        print(f"Error computing live portfolio equity: {e}")
        import traceback
        traceback.print_exc()
        return None


def get_alpaca_portfolio_history(timeframe='all'):
    """Fetch portfolio history (equity curve) from Alpaca API."""
    if not trading_client or not ALPACA_API_KEY or not ALPACA_SECRET_KEY:
        print("No trading client or API credentials available")
        return []
    
    try:
        now = datetime.now()
        
        # Map our timeframe to Alpaca's period and timeframe parameters
        # For day timeframe, if it's a weekend, use the last trading day
        if timeframe == 'day':
            if now.weekday() >= 5:  # Saturday or Sunday
                display_date = get_last_trading_day(now)
                date_end = display_date.strftime('%Y-%m-%d')
            else:
                date_end = now.strftime('%Y-%m-%d')
            period = '1D'
            alpaca_timeframe = '1Min'  # 1-minute intervals for intraday
            extended_hours = 'true'
        elif timeframe == 'week':
            period = '1W'
            alpaca_timeframe = '15Min'  # 15-minute intervals for intraday
            date_end = now.strftime('%Y-%m-%d')
            extended_hours = 'true'
        elif timeframe == 'month':
            period = '29D'  # 29 days (approximately 1 month)
            alpaca_timeframe = '1D'  # Daily points (same as other timeframes)
            date_end = now.strftime('%Y-%m-%d')
            extended_hours = 'false'  # No effect for daily
        elif timeframe == '3m':
            period = '3M'
            alpaca_timeframe = '1D'  # Daily points
            date_end = now.strftime('%Y-%m-%d')
            extended_hours = 'false'  # No effect for daily
        elif timeframe == 'year':
            period = '1A'  # 1 year
            alpaca_timeframe = '1D'  # Daily points
            date_end = now.strftime('%Y-%m-%d')
            extended_hours = 'false'  # No effect for daily
        elif timeframe == 'ytd':
            # For YTD, calculate days since Jan 1
            year_start = datetime(now.year, 1, 1)
            days_since_start = (now - year_start).days
            if days_since_start <= 29:
                period = f'{days_since_start}D'
                alpaca_timeframe = '1H'
                extended_hours = 'true'
            else:
                period = '1A'
                alpaca_timeframe = '1D'
                extended_hours = 'false'
            date_end = now.strftime('%Y-%m-%d')
        else:  # 'all'
            period = '1A'  # Max 1 year for now
            alpaca_timeframe = '1D'  # Daily points
            date_end = now.strftime('%Y-%m-%d')
            extended_hours = 'false'  # No effect for daily
        
        # Make API request to Alpaca portfolio history endpoint
        url = f"{ALPACA_BASE_URL}/v2/account/portfolio/history"
        headers = {
            "APCA-API-KEY-ID": ALPACA_API_KEY,
            "APCA-API-SECRET-KEY": ALPACA_SECRET_KEY
        }
        params = {
            "period": period,
            "timeframe": alpaca_timeframe,
            "date_end": date_end,
            "extended_hours": extended_hours
        }
        
        print(f"Fetching portfolio history: period={period}, timeframe={alpaca_timeframe}, date_end={date_end}, extended_hours={extended_hours}")
        response = requests.get(url, headers=headers, params=params)
        
        if response.status_code == 200:
            data = response.json()
            # Alpaca returns: { "timestamp": [...], "equity": [...], "profit_loss": [...], "profit_loss_pct": [...] }
            timestamps = data.get('timestamp', [])
            equity_values = data.get('equity', [])
            profit_loss = data.get('profit_loss', [])
            
            # Debug log: timestamps.length, equity.length, first/last timestamp
            print(f"DEBUG [{timeframe}]: timestamps.length={len(timestamps)}, equity.length={len(equity_values)}")
            if timestamps and equity_values:
                first_ts = timestamps[0] if timestamps else None
                last_ts = timestamps[-1] if timestamps else None
                print(f"DEBUG [{timeframe}]: first_timestamp={first_ts}, last_timestamp={last_ts}")
            
            # Log Month series values to identify outlier
            if timeframe == 'month' and equity_values:
                min_equity = min(equity_values) if equity_values else None
                max_equity = max(equity_values) if equity_values else None
                print(f"DEBUG [month]: First 10 equity values: {equity_values[:10]}")
                print(f"DEBUG [month]: Last 10 equity values: {equity_values[-10:]}")
                print(f"DEBUG [month]: MIN equity: {min_equity}, MAX equity: {max_equity}")
                # Check if Alpaca response has other fields that might be mixed in
                print(f"DEBUG [month]: Alpaca response keys: {list(data.keys())}")
                if 'profit_loss' in data:
                    print(f"DEBUG [month]: First 10 profit_loss: {data.get('profit_loss', [])[:10]}")
                if 'portfolio_value' in data:
                    print(f"DEBUG [month]: First 10 portfolio_value: {data.get('portfolio_value', [])[:10]}")
                if 'buying_power' in data:
                    print(f"DEBUG [month]: First 10 buying_power: {data.get('buying_power', [])[:10]}")
            
            if not timestamps or not equity_values:
                print("No portfolio history data returned from Alpaca")
                return []
            
            if len(timestamps) != len(equity_values):
                print(f"WARNING: Mismatch - {len(timestamps)} timestamps but {len(equity_values)} equity values")
            
            # For month/3m/year/ytd/all: build series ONLY from Alpaca portfolio_history equity[]
            # Do NOT normalize to baseline, do NOT use profit_loss for equity, use raw equity values
            is_month_plus = timeframe in ['month', '3m', 'year', 'ytd', 'all']
            
            # Map ALL returned points: series = timestamps.map((t,i)=>({t: timestamps[i]*1000, v: equity[i]}))
            # IMPORTANT: Use ONLY the 'equity' field from Alpaca - never buying_power, portfolio_value, or cash
            # Filter to only include points >= baseline
            baseline_start = get_baseline_start_datetime(1)
            baseline_ts_ms = int(baseline_start.timestamp() * 1000)
            
            performance_data = []
            equity_values_used = []
            
            for i in range(len(timestamps)):
                timestamp = timestamps[i]
                
                # Alpaca timestamps are in seconds (Unix timestamp), convert to milliseconds
                if isinstance(timestamp, (int, float)):
                    # Timestamp is in seconds, convert to ms
                    timestamp_ms = int(timestamp * 1000) if timestamp < 1e10 else int(timestamp)
                    dt = datetime.fromtimestamp(timestamp_ms / 1000)
                else:
                    # Try parsing as ISO string
                    try:
                        dt = datetime.fromisoformat(str(timestamp).replace('Z', '+00:00'))
                        if dt.tzinfo:
                            dt = dt.replace(tzinfo=None)
                        timestamp_ms = int(dt.timestamp() * 1000)
                    except Exception as e:
                        print(f"Error parsing timestamp {timestamp}: {e}")
                        continue
                
                # Filter out points before baseline
                if timestamp_ms < baseline_ts_ms:
                    continue
                
                # CRITICAL: Use ONLY equity_values[i] - this is the account equity, not buying_power
                equity = float(equity_values[i]) if i < len(equity_values) else None
                if equity is None:
                    continue
                
                equity_values_used.append(equity)
                
                # For month+ timeframes: use raw equity, calculate returns relative to first equity value
                # For day/week: can use profit_loss if available, otherwise calculate from equity
                if is_month_plus:
                    # Use first equity value as baseline for returns calculation only
                    first_equity = float(equity_values[0]) if equity_values else equity
                    returns = equity - first_equity
                else:
                    # For day/week, use profit_loss if available
                    pnl = float(profit_loss[i]) if i < len(profit_loss) else None
                    if pnl is not None:
                        returns = pnl
                    else:
                        # Fallback: calculate from equity
                        first_equity = float(equity_values[0]) if equity_values else equity
                        returns = equity - first_equity
                
                # Format date based on timeframe
                if timeframe in ['day', 'week']:
                    # Include time for intraday
                    date_str = dt.strftime('%Y-%m-%dT%H:%M:%S')
                else:
                    # Date only for daily timeframes (month, 3m, year, ytd, all)
                    date_str = dt.strftime('%Y-%m-%d')
                
                performance_data.append({
                    'date': date_str,
                    'returns': round(returns, 2),
                    'equity': round(equity, 2),  # Use raw equity value, no normalization
                    'timestamp': timestamp_ms  # Already in milliseconds
                })
            
            # Part A: Log what Month+ data actually is (no guessing)
            if is_month_plus and equity_values_used:
                points_count = len(equity_values_used)
                min_value = min(equity_values_used)
                max_value = max(equity_values_used)
                unique_values_count = len(set(equity_values_used))
                first_value = equity_values_used[0]
                last_value = equity_values_used[-1]
                print(f"MONTH_PLUS_DATA [{timeframe}]: points_count={points_count}, min_value={min_value}, max_value={max_value}, unique_values_count={unique_values_count}, first_value={first_value}, last_value={last_value}")
                if unique_values_count == 1:
                    print(f"WARNING [{timeframe}]: All equity values are the same ({first_value}). This suggests we're plotting the wrong field or overwriting the series.")
            
            print(f"Fetched {len(performance_data)} portfolio history points from Alpaca for {timeframe}")
            return performance_data
        else:
            print(f"Error fetching portfolio history: {response.status_code} - {response.text}")
            return []
            
    except Exception as e:
        print(f"Error fetching Alpaca portfolio history: {e}")
        import traceback
        traceback.print_exc()
        return []


def calculate_performance_data(trades, timeframe='all'):
    """Calculate performance data for a given timeframe."""
    # Filter trades by timeframe
    now = datetime.now()
    
    # For day timeframe, if it's a weekend, use the last trading day (like Robinhood)
    # For other timeframes, use current date
    if timeframe == 'day':
        if now.weekday() >= 5:  # Saturday or Sunday
            display_date = get_last_trading_day(now)
            print(f"Day timeframe: Weekend detected, using last trading day: {display_date.strftime('%Y-%m-%d')}")
        else:
            display_date = now
    else:
        display_date = now
    
    # For day timeframe, always generate data even if no trades
    # For other timeframes, return empty if no trades
    if not trades and timeframe != 'day':
        return []
    
    timeframe_map = {
        'day': timedelta(days=1),
        'week': timedelta(weeks=1),
        'month': timedelta(days=30),
        '3m': timedelta(days=90),
        'year': timedelta(days=365),
        'ytd': timedelta(days=(now - datetime(now.year, 1, 1)).days),
        'all': None
    }
    
    cutoff_date = None
    cutoff_end = None
    if timeframe != 'all':
        if timeframe == 'day':
            # Use the display_date (last trading day if weekend) for day timeframe
            # Set cutoff to start of that day, and also include trades up to end of that day
            cutoff_date = display_date.replace(hour=0, minute=0, second=0, microsecond=0)
            cutoff_end = display_date.replace(hour=23, minute=59, second=59, microsecond=999999)
        else:
            cutoff_date = now - timeframe_map.get(timeframe, timedelta(days=365))
            cutoff_end = now
    
    filtered_trades = []
    for trade in (trades or []):
        # Include both closed and open trades for performance calculation
        # For open trades, use entry_time; for closed, use exit_time
        time_to_check = trade.get('exit_time') if trade.get('status') == 'closed' else trade.get('entry_time')
        
        if time_to_check:
            try:
                if isinstance(time_to_check, str):
                    # Handle various ISO format variations
                    time_clean = time_to_check.replace('Z', '+00:00')
                    if '+' not in time_clean and 'T' in time_clean:
                        time_clean = time_clean + '+00:00'
                    trade_date = datetime.fromisoformat(time_clean)
                    # Make timezone-naive for comparison
                    if trade_date.tzinfo:
                        trade_date = trade_date.replace(tzinfo=None)
                else:
                    trade_date = time_to_check
                    if hasattr(trade_date, 'tzinfo') and trade_date.tzinfo:
                        trade_date = trade_date.replace(tzinfo=None)
                
                # Make cutoff_date timezone-naive too
                if cutoff_date and cutoff_date.tzinfo:
                    cutoff_date = cutoff_date.replace(tzinfo=None)
                if cutoff_end and cutoff_end.tzinfo:
                    cutoff_end = cutoff_end.replace(tzinfo=None)
                
                # For day timeframe, include trades on the display_date (last trading day)
                # For other timeframes, include trades from cutoff_date onwards
                if timeframe == 'day':
                    if cutoff_date and cutoff_end and cutoff_date <= trade_date <= cutoff_end:
                        filtered_trades.append(trade)
                elif cutoff_date is None or trade_date >= cutoff_date:
                    filtered_trades.append(trade)
            except Exception as e:
                print(f"Error parsing date {time_to_check}: {e}")
                import traceback
                traceback.print_exc()
    
    # Get initial equity from account or use default
    account = get_alpaca_account()
    initial_equity = account['equity'] if account else 10000
    
    # Sort by exit_time
    filtered_trades.sort(key=lambda x: x.get('exit_time', x.get('entry_time', '')))
    
    # Calculate cumulative returns
    cumulative_pnl = 0
    performance_data = []
    
    # Add starting point (baseline at initial equity) - Robinhood style
    start_date_str = None
    if filtered_trades:
        first_trade = filtered_trades[0]
        first_date = first_trade.get('exit_time', first_trade.get('entry_time', ''))
        if first_date:
            try:
                if isinstance(first_date, str):
                    start_date_str = first_date.split('T')[0] if 'T' in first_date else first_date
                else:
                    start_date_str = first_date.strftime('%Y-%m-%d')
                
                # Add baseline point at start
                performance_data.append({
                    'date': start_date_str,
                    'returns': 0,
                    'equity': round(initial_equity, 2)
                })
            except Exception as e:
                print(f"Error processing first trade date: {e}")
    elif timeframe == 'day':
        # For daily timeframe, show display_date's baseline (last trading day if weekend) even if no trades
        start_date_str = display_date.strftime('%Y-%m-%d')
        performance_data.append({
            'date': start_date_str,
            'returns': 0,
            'equity': round(initial_equity, 2)
        })
    
    for trade in filtered_trades:
        # Only count P&L from closed trades for cumulative returns
        if trade.get('status') == 'closed':
            pnl = trade.get('pnl', 0) or 0
            cumulative_pnl += pnl
        
        # Use exit_time for closed trades, entry_time for open trades
        time_to_use = trade.get('exit_time') if trade.get('status') == 'closed' else trade.get('entry_time', '')
        
        if time_to_use:
            try:
                if isinstance(time_to_use, str):
                    date_str = time_to_use.split('T')[0] if 'T' in time_to_use else time_to_use
                else:
                    date_str = time_to_use.strftime('%Y-%m-%d')
                
                # Skip if this is the same date as the baseline (avoid duplicate)
                if date_str == start_date_str:
                    continue
                
                # For open positions, add unrealized P&L to equity
                if trade.get('status') == 'open':
                    unrealized_pnl = trade.get('pnl', 0) or 0
                    current_equity = round(initial_equity + cumulative_pnl + unrealized_pnl, 2)
                else:
                    current_equity = round(initial_equity + cumulative_pnl, 2)
                
                performance_data.append({
                    'date': date_str,
                    'returns': round(cumulative_pnl, 2),
                    'equity': current_equity
                })
            except Exception as e:
                print(f"Error processing trade date: {e}")
    
    # Always ensure we have a start and end point for the timeframe
    # Start point: baseline at cutoff date or first trade date
    # End point: current equity at display_date (last trading day if weekend for day view)
    display_date_str = display_date.strftime('%Y-%m-%d')
    account = get_alpaca_account()
    current_equity = account['equity'] if account else initial_equity
    current_returns = round(current_equity - initial_equity, 2)
    
    # Determine the start date for the timeframe
    if timeframe != 'all':
        if timeframe == 'day':
            # For day, use the display_date (last trading day if weekend)
            timeframe_start = display_date.replace(hour=0, minute=0, second=0, microsecond=0)
        else:
            timeframe_start = cutoff_date.replace(hour=0, minute=0, second=0, microsecond=0) if cutoff_date else now
    else:
        # For 'all', use first trade date or a default
        if performance_data:
            timeframe_start = datetime.fromisoformat(performance_data[0]['date'])
        else:
            timeframe_start = (now - timedelta(days=365)).replace(hour=0, minute=0, second=0, microsecond=0)
    
    timeframe_start_str = timeframe_start.strftime('%Y-%m-%d')
    
    # Ensure we have a start point (baseline) - always at timeframe start
    if not performance_data:
        performance_data = [{
            'date': timeframe_start_str,
            'returns': 0,
            'equity': round(initial_equity, 2)
        }]
    elif performance_data[0]['date'] != timeframe_start_str:
        # Insert baseline at start if it doesn't exist
        performance_data.insert(0, {
            'date': timeframe_start_str,
            'returns': 0,
            'equity': round(initial_equity, 2)
        })
    
    # Ensure we have an end point (current) - use display_date for day, today for others
    end_date_str = display_date_str if timeframe == 'day' else now.strftime('%Y-%m-%d')
    if performance_data[-1]['date'] != end_date_str:
        performance_data.append({
            'date': end_date_str,
            'returns': current_returns,
            'equity': round(current_equity, 2)
        })
    
    # Generate interpolated data points for ALL ranges based on timeframe
    # Always generate points across the entire timeframe range
    # For day timeframe, ALWAYS generate hourly points even if we only have 1 point
    # For other timeframes, need at least 2 points to interpolate
    if timeframe == 'day' or len(performance_data) >= 2:
        # Use the timeframe start and end, not just data points
        start_date_str = performance_data[0]['date']
        end_date_str = performance_data[-1]['date']
        
        # Parse start date
        if 'T' in start_date_str or ' ' in start_date_str:
            start_date = datetime.fromisoformat(start_date_str.replace('T', ' '))
        else:
            start_date = datetime.fromisoformat(start_date_str)
        # For day timeframe, always use display_date start (last trading day if weekend)
        if timeframe == 'day':
            start_date = display_date.replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Parse end date - for day timeframe, use end of display_date (last trading day if weekend)
        if timeframe == 'day':
            # Use end of the display_date (last trading day), not current time
            end_date = display_date.replace(hour=23, minute=59, second=59)
        else:
            if 'T' in end_date_str or ' ' in end_date_str:
                end_date = datetime.fromisoformat(end_date_str.replace('T', ' '))
            else:
                end_date = datetime.fromisoformat(end_date_str)
                # For other timeframes, use end of day
                end_date = end_date.replace(hour=23, minute=59, second=59)
        
        # Determine sampling interval based on timeframe
        if timeframe == 'day':
            interval = timedelta(hours=1)  # Hourly for 1D (24 points)
        elif timeframe == 'week':
            interval = timedelta(hours=6)   # Every 6 hours for 1W (28 points)
        elif timeframe == 'month':
            interval = timedelta(days=1)    # Daily for 1M (30 points)
        elif timeframe == '3m':
            interval = timedelta(days=1)    # Daily for 3M (90 points)
        elif timeframe in ['year', 'ytd']:
            interval = timedelta(days=7)    # Weekly for 1Y/YTD (~52 points)
        else:  # 'all'
            interval = timedelta(days=30)   # Monthly for All
        
        interpolated_data = []
        # Create lookup map - for day/week, use date portion as key; for others, use full date string
        original_points = {}
        for point in performance_data:
            point_date_str = point['date']
            # Extract date portion for lookup
            if 'T' in point_date_str:
                date_key = point_date_str.split('T')[0]
            elif ' ' in point_date_str:
                date_key = point_date_str.split(' ')[0]
            else:
                date_key = point_date_str
            original_points[date_key] = point
        
        # Generate points from start_date to end_date using the interval
        current_date = start_date
        while current_date <= end_date:
            # For day/week timeframes, include time in stored date; for others, use date only
            if timeframe in ['day', 'week']:
                date_str = current_date.strftime('%Y-%m-%dT%H:%M:%S')
                date_key = current_date.strftime('%Y-%m-%d')  # For lookup
            else:
                date_str = current_date.strftime('%Y-%m-%d')
                date_key = date_str
            
            # If we have an exact point (by date), use it but keep the datetime if day/week
            if date_key in original_points:
                exact_point = original_points[date_key].copy()
                if timeframe in ['day', 'week']:
                    exact_point['date'] = date_str  # Update to include time
                interpolated_data.append(exact_point)
            else:
                # Find surrounding points for interpolation
                prev_point = None
                next_point = None
                
                for point in performance_data:
                    point_date_str = point['date']
                    # Parse point date - handle both date-only and datetime strings
                    if 'T' in point_date_str or ' ' in point_date_str:
                        point_date = datetime.fromisoformat(point_date_str.replace('T', ' '))
                    else:
                        point_date = datetime.fromisoformat(point_date_str)
                    if point_date < current_date:
                        prev_point = point
                    elif point_date >= current_date and next_point is None:
                        next_point = point
                        break
                
                if prev_point and next_point:
                    # Linear interpolation
                    prev_date_str = prev_point['date']
                    next_date_str = next_point['date']
                    # Parse dates - handle both date-only and datetime strings
                    if 'T' in prev_date_str or ' ' in prev_date_str:
                        prev_date = datetime.fromisoformat(prev_date_str.replace('T', ' '))
                    else:
                        prev_date = datetime.fromisoformat(prev_date_str)
                    if 'T' in next_date_str or ' ' in next_date_str:
                        next_date = datetime.fromisoformat(next_date_str.replace('T', ' '))
                    else:
                        next_date = datetime.fromisoformat(next_date_str)
                    total_diff = (next_date - prev_date).total_seconds()
                    current_diff = (current_date - prev_date).total_seconds()
                    
                    if total_diff > 0:
                        ratio = current_diff / total_diff
                        interp_equity = prev_point['equity'] + (next_point['equity'] - prev_point['equity']) * ratio
                        interp_returns = prev_point['returns'] + (next_point['returns'] - prev_point['returns']) * ratio
                        
                        interpolated_data.append({
                            'date': date_str if timeframe not in ['day', 'week'] else current_date.strftime('%Y-%m-%dT%H:%M:%S'),
                            'returns': round(interp_returns, 2),
                            'equity': round(interp_equity, 2)
                        })
                elif prev_point:
                    # Use previous point if no next point
                    interpolated_data.append({
                        'date': date_str if timeframe not in ['day', 'week'] else current_date.strftime('%Y-%m-%dT%H:%M:%S'),
                        'returns': prev_point['returns'],
                        'equity': prev_point['equity']
                    })
                elif next_point:
                    # Use next point if no previous point
                    interpolated_data.append({
                        'date': date_str if timeframe not in ['day', 'week'] else current_date.strftime('%Y-%m-%dT%H:%M:%S'),
                        'returns': next_point['returns'],
                        'equity': next_point['equity']
                    })
                elif len(performance_data) == 1:
                    # If we only have one point (baseline), use it for all interpolated points
                    single_point = performance_data[0]
                    interpolated_data.append({
                        'date': date_str if timeframe not in ['day', 'week'] else current_date.strftime('%Y-%m-%dT%H:%M:%S'),
                        'returns': single_point['returns'],
                        'equity': single_point['equity']
                    })
            
            # Move to next interval
            current_date += interval
        
        # Ensure we have the last point
        if performance_data and len(interpolated_data) > 0:
            last_original = performance_data[-1]
            last_interp = interpolated_data[-1]
            if last_original['date'] != last_interp['date']:
                interpolated_data.append(last_original)
        
        performance_data = interpolated_data if len(interpolated_data) > len(performance_data) else performance_data
    
    # Add timestamp (ms) to each point for frontend
    for point in performance_data:
        date_str = point['date']
        # Parse date - handle both date-only and datetime strings
        if 'T' in date_str or ' ' in date_str:
            date_obj = datetime.fromisoformat(date_str.replace('T', ' '))
        else:
            date_obj = datetime.fromisoformat(date_str)
        point['timestamp'] = int(date_obj.timestamp() * 1000)  # Convert to ms
    
    # Verify unique timestamps
    timestamps = [p['timestamp'] for p in performance_data]
    unique_timestamps = len(set(timestamps))
    
    print(f"Performance data points for {timeframe}: {len(performance_data)}")
    if performance_data:
        print(f"  First timestamp: {performance_data[0].get('timestamp')}, Last: {performance_data[-1].get('timestamp')}")
        unique_dates = len(set(p['date'] for p in performance_data))
        print(f"  Unique dates: {unique_dates}")
        print(f"  Unique timestamps: {unique_timestamps}")
        if unique_timestamps < len(performance_data):
            print(f"  WARNING: {len(performance_data) - unique_timestamps} duplicate timestamps detected!")
            if timeframe == 'day':
                print(f"  Sample timestamps: {timestamps[:10]}")
    else:
        print(f"  WARNING: No performance data generated for {timeframe}!")
        if timeframe == 'day':
            print(f"  Day timeframe should always have data. display_date: {display_date.strftime('%Y-%m-%d')}")
    
    # Ensure day timeframe always returns data (even if empty trades)
    if timeframe == 'day' and len(performance_data) == 0:
        print("  Generating fallback data for day timeframe")
        display_date_str = display_date.strftime('%Y-%m-%d')
        account = get_alpaca_account()
        current_equity = account['equity'] if account else 10000
        initial_equity = account['equity'] if account else 10000
        
        # Generate hourly points for the display_date
        start_date = display_date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = display_date.replace(hour=23, minute=59, second=59)
        
        performance_data = []
        current_date = start_date
        while current_date <= end_date:
            performance_data.append({
                'date': current_date.strftime('%Y-%m-%dT%H:%M:%S'),
                'returns': 0,
                'equity': round(current_equity, 2),
                'timestamp': int(current_date.timestamp() * 1000)
            })
            current_date += timedelta(hours=1)
        
        print(f"  Generated {len(performance_data)} fallback points for day timeframe")
    
    return performance_data


# Global cache to track maximum trade counts (never decreases)
# This ensures the trade counter on the website never goes down, even if:
# - Trades are filtered out by date/timeframe
# - API returns fewer trades due to pagination/limits
# - Trades are removed from Alpaca's history
# - Server restarts (persisted to file)
MAX_TRADE_COUNTS_FILE = Path(__file__).parent / 'max_trade_counts.json'

def load_max_trade_counts():
    """Load max trade counts from file, or return defaults if file doesn't exist."""
    try:
        if MAX_TRADE_COUNTS_FILE.exists():
            with open(MAX_TRADE_COUNTS_FILE, 'r') as f:
                data = json.load(f)
                # Ensure all projects are present
                counts = {1: data.get('1', 0), 2: data.get('2', 0), 3: data.get('3', 0)}
                print(f"Loaded max trade counts from file: {counts}")
                return counts
    except Exception as e:
        print(f"Error loading max trade counts: {e}")
    return {1: 0, 2: 0, 3: 0}

def save_max_trade_counts(counts):
    """Save max trade counts to file."""
    try:
        with open(MAX_TRADE_COUNTS_FILE, 'w') as f:
            json.dump({str(k): v for k, v in counts.items()}, f)
    except Exception as e:
        print(f"Error saving max trade counts: {e}")

_max_trade_counts = load_max_trade_counts()


def get_baseline_equity_from_api(project):
    """
    Fetch the actual baseline equity from the account's portfolio history at baselineStartIso.
    This is the REAL equity value from the account, not a config value.
    
    Returns the actual equity value from the account, or None if not available.
    """
    baseline = get_baseline(project)
    baseline_start = get_baseline_start_datetime(project)
    
    # Select appropriate client and credentials based on project
    if project == 2:
        base_url = ALPACA_BASE_URL_2
        api_key = ALPACA_API_KEY_2
        secret_key = ALPACA_SECRET_KEY_2
    else:
        base_url = ALPACA_BASE_URL
        api_key = ALPACA_API_KEY
        secret_key = ALPACA_SECRET_KEY
    
    if not api_key or not secret_key:
        return None
    
    headers = {
        "APCA-API-KEY-ID": api_key,
        "APCA-API-SECRET-KEY": secret_key
    }
    
    try:
        # Fetch portfolio history covering the baseline period
        # Try multiple periods to ensure we get data if baseline is older
        url_history = f"{base_url}/v2/account/portfolio/history"
        now = datetime.now(timezone.utc)
        date_end = now.strftime('%Y-%m-%d')
        
        # Try different periods: 29D (month), 1A (year)
        periods_to_try = [
            ("29D", "1D", "false"),  # 29 days, daily timeframe
            ("1A", "1D", "false"),   # 1 year, daily timeframe
        ]
        
        for period, timeframe, extended_hours in periods_to_try:
            params = {
                "period": period,
                "timeframe": timeframe,
                "date_end": date_end,
                "extended_hours": extended_hours
            }
            
            response = requests.get(url_history, headers=headers, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                equity_points = parse_portfolio_history(data, baseline_start)
                
                # Get the first equity point at or after baseline
                baseline_ts_ms = int(baseline_start.timestamp() * 1000)
                first_equity, first_ts = equity_at_or_after(equity_points, baseline_ts_ms)
                
                # If first equity is 0 or very small, try to find first non-zero point
                if first_equity is not None:
                    if first_equity <= 0.01:  # Account might have been empty at baseline
                        # Find first non-zero equity point
                        for point in equity_points:
                            if point['t'] >= baseline_ts_ms and point['equity'] > 0.01:
                                first_equity = point['equity']
                                first_ts = point['t']
                                print(f"Found first non-zero equity for project {project}: {first_equity} (at ts={first_ts})")
                                break
                    
                    if first_equity > 0.01:
                        print(f"Fetched baseline equity from API for project {project}: {first_equity} (at ts={first_ts}, using period={period})")
                        return first_equity
                    else:
                        print(f"Warning: Baseline equity for project {project} is {first_equity}, which seems incorrect. Using config fallback.")
                        return None
                else:
                    # Try next period if this one didn't have data
                    if period != periods_to_try[-1][0]:
                        continue
                    print(f"No equity point found after baseline for project {project} (tried periods: {[p[0] for p in periods_to_try]}), using config fallback")
                    return None
            else:
                error_text = response.text if hasattr(response, 'text') else ''
                print(f"Error fetching portfolio history for baseline equity (project {project}, period={period}): {response.status_code} - {error_text}")
                if period == periods_to_try[-1][0]:
                    return None
                # Try next period
                continue
        
        return None
    except Exception as e:
        print(f"Error fetching baseline equity from API for project {project}: {e}")
        import traceback
        traceback.print_exc()
        return None


def calculate_stats(trades, project=1, portfolio_value=None, buy_orders_count=None):
    """Calculate statistics from trades.
    
    Args:
        trades: List of trade dictionaries
        project: Project number (1 for stocks, 2 for crypto). Defaults to 1.
        portfolio_value: Optional portfolio value to use for P&L calculation. If None, will fetch it.
        buy_orders_count: Optional count of actual buy orders from Alpaca. If None, will count from trades.
    """
    global _max_trade_counts
    
    # For crypto (project 2), we need to match buy/sell pairs for stats calculation
    # because individual orders have pnl: 0
    if project == 2:
        # Match buy and sell orders into pairs for stats
        matched_trades = []
        orders_by_symbol = {}
        
        # Group orders by symbol
        for trade in trades:
            symbol = trade.get('symbol')
            if symbol not in orders_by_symbol:
                orders_by_symbol[symbol] = []
            orders_by_symbol[symbol].append(trade)
        
        # Match buys with sells for each symbol
        for symbol, symbol_trades in orders_by_symbol.items():
            buys = [t for t in symbol_trades if t.get('side', '').lower() == 'buy']
            sells = [t for t in symbol_trades if t.get('side', '').lower() == 'sell']
            
            # Sort by time (proper datetime parsing)
            def get_trade_time(t):
                time_str = t.get('entry_time', '') or t.get('exit_time', '')
                if not time_str:
                    return datetime.min
                try:
                    if 'T' in time_str:
                        time_str_clean = time_str.replace('Z', '+00:00')
                        try:
                            return datetime.fromisoformat(time_str_clean)
                        except:
                            return datetime.fromisoformat(time_str_clean.replace('+00:00', ''))
                    return datetime.fromisoformat(time_str)
                except:
                    return datetime.min
            
            buys.sort(key=get_trade_time)
            sells.sort(key=get_trade_time)
            
            # Match sells with buys (FIFO)
            buy_stack = []
            for sell in sells:
                # Find matching buy
                if buys:
                    buy = buys.pop(0)
                    buy_stack.append(buy)
                
                if buy_stack:
                    buy = buy_stack.pop(0)
                    # Calculate P&L
                    entry_price = buy.get('entry_price', 0)
                    exit_price = sell.get('entry_price', 0)  # sell's entry_price is actually exit price
                    qty = min(buy.get('qty', 0), sell.get('qty', 0))
                    pnl = (exit_price - entry_price) * qty
                    
                    matched_trades.append({
                        'symbol': symbol,
                        'side': 'sell',
                        'qty': qty,
                        'entry_price': entry_price,
                        'exit_price': exit_price,
                        'pnl': pnl,
                        'pnl_percent': ((exit_price - entry_price) / entry_price * 100) if entry_price > 0 else 0,
                        'entry_time': buy.get('entry_time'),
                        'exit_time': sell.get('entry_time'),
                        'status': 'closed'
                    })
            
            # Remaining buys become open trades
            for buy in buys + buy_stack:
                matched_trades.append({
                    'symbol': symbol,
                    'side': 'buy',
                    'qty': buy.get('qty', 0),
                    'entry_price': buy.get('entry_price', 0),
                    'exit_price': None,
                    'pnl': 0,  # Unrealized
                    'pnl_percent': 0,
                    'entry_time': buy.get('entry_time'),
                    'exit_time': None,
                    'status': 'open'
                })
        
        # Use matched trades for stats calculation
        closed_trades = [t for t in matched_trades if t.get('status') == 'closed']
        open_trades = [t for t in matched_trades if t.get('status') == 'open']
    else:
        closed_trades = [t for t in trades if t.get('status') == 'closed']
        open_trades = [t for t in trades if t.get('status') == 'open']
    
    # Count total trades: use buy_orders_count if provided, otherwise count buy trades
    # For crypto, closed trades have side='sell', so we need to count differently
    # #region agent log
    with open(r'c:\Users\mason\OneDrive\Desktop\Cursor\website\.cursor\debug.log', 'a') as f:
        f.write(json.dumps({'sessionId': 'debug-session', 'runId': 'run1', 'hypothesisId': 'E', 'location': 'app.py:2725', 'message': 'calculate_stats entry', 'data': {'project': project, 'buy_orders_count': buy_orders_count, 'total_trades_input': len(trades), 'closed_trades': len([t for t in trades if t.get('status') == 'closed']), 'open_trades': len([t for t in trades if t.get('status') == 'open'])}, 'timestamp': int(datetime.now().timestamp() * 1000)}) + '\n')
    # #endregion
    if buy_orders_count is not None:
        calculated_count = buy_orders_count
        # #region agent log
        with open(r'c:\Users\mason\OneDrive\Desktop\Cursor\website\.cursor\debug.log', 'a') as f:
            f.write(json.dumps({'sessionId': 'debug-session', 'runId': 'run1', 'hypothesisId': 'E', 'location': 'app.py:2726', 'message': 'Using buy_orders_count path', 'data': {'project': project, 'buy_orders_count': buy_orders_count, 'calculated_count': calculated_count}, 'timestamp': int(datetime.now().timestamp() * 1000)}) + '\n')
        # #endregion
    elif project == 2:
        # For crypto: count open positions (side='buy') + count unique buy orders from closed trades
        # Since closed trades represent sells, we need to count the underlying buy orders
        open_buys = len([t for t in open_trades if t.get('side', '').lower() == 'buy'])
        # Each closed trade represents a sell, but was created from a buy order
        # So we count closed trades as buy orders (each sell came from a buy)
        closed_buys = len(closed_trades)
        calculated_count = open_buys + closed_buys
        # #region agent log
        with open(r'c:\Users\mason\OneDrive\Desktop\Cursor\website\.cursor\debug.log', 'a') as f:
            f.write(json.dumps({'sessionId': 'debug-session', 'runId': 'run1', 'hypothesisId': 'E', 'location': 'app.py:2734', 'message': 'Project 2 fallback counting', 'data': {'project': project, 'open_buys': open_buys, 'closed_buys': closed_buys, 'calculated_count': calculated_count}, 'timestamp': int(datetime.now().timestamp() * 1000)}) + '\n')
        # #endregion
    else:
        # For stocks: count trades with side='buy' or 'long'
        filled_buys = [t for t in trades if t.get('side', '').lower() in ['buy', 'long']]
        calculated_count = len(filled_buys)
        # #region agent log
        with open(r'c:\Users\mason\OneDrive\Desktop\Cursor\website\.cursor\debug.log', 'a') as f:
            f.write(json.dumps({'sessionId': 'debug-session', 'runId': 'run1', 'hypothesisId': 'E', 'location': 'app.py:2751', 'message': 'Project 1 fallback counting', 'data': {'project': project, 'filled_buys_count': len(filled_buys), 'calculated_count': calculated_count}, 'timestamp': int(datetime.now().timestamp() * 1000)}) + '\n')
        # #endregion
    
    # Update max trade count: if buy_orders_count was provided, trust it as authoritative
    # Otherwise, only increase (monotonicity) to handle cases where API might return partial data
    old_max = _max_trade_counts[project]
    # #region agent log
    with open(r'c:\Users\mason\OneDrive\Desktop\Cursor\website\.cursor\debug.log', 'a') as f:
        f.write(json.dumps({'sessionId': 'debug-session', 'runId': 'run1', 'hypothesisId': 'C', 'location': 'app.py:2793', 'message': 'Max trade count check', 'data': {'project': project, 'calculated_count': calculated_count, 'old_max': old_max, 'buy_orders_count_provided': buy_orders_count is not None}, 'timestamp': int(datetime.now().timestamp() * 1000)}) + '\n')
    # #endregion
    
    if buy_orders_count is not None:
        # When buy_orders_count is provided, it's authoritative from the API - always use it
        # This allows correction of previous incorrect counts
        if calculated_count != _max_trade_counts[project]:
            _max_trade_counts[project] = calculated_count
            print(f"Updated max trade count for project {project}: {old_max} -> {calculated_count} (using authoritative buy_orders_count)")
            save_max_trade_counts(_max_trade_counts)
            # #region agent log
            with open(r'c:\Users\mason\OneDrive\Desktop\Cursor\website\.cursor\debug.log', 'a') as f:
                f.write(json.dumps({'sessionId': 'debug-session', 'runId': 'run1', 'hypothesisId': 'C', 'location': 'app.py:2801', 'message': 'Max trade count updated (authoritative buy_orders_count)', 'data': {'project': project, 'old_max': old_max, 'new_max': calculated_count}, 'timestamp': int(datetime.now().timestamp() * 1000)}) + '\n')
            # #endregion
    elif calculated_count > _max_trade_counts[project]:
        # Only increase when buy_orders_count not provided (fallback counting)
        _max_trade_counts[project] = calculated_count
        print(f"Updated max trade count for project {project}: {old_max} -> {calculated_count}")
        save_max_trade_counts(_max_trade_counts)
        # #region agent log
        with open(r'c:\Users\mason\OneDrive\Desktop\Cursor\website\.cursor\debug.log', 'a') as f:
            f.write(json.dumps({'sessionId': 'debug-session', 'runId': 'run1', 'hypothesisId': 'C', 'location': 'app.py:2809', 'message': 'Max trade count updated (fallback counting)', 'data': {'project': project, 'old_max': old_max, 'new_max': calculated_count}, 'timestamp': int(datetime.now().timestamp() * 1000)}) + '\n')
        # #endregion
    elif calculated_count < _max_trade_counts[project]:
        # If calculated count is less than max and buy_orders_count not provided, keep using the max
        # This handles cases where API might return partial data
        print(f"WARNING: Calculated trade count ({calculated_count}) is less than max ({_max_trade_counts[project]}) for project {project}. Using max to maintain monotonicity.")
        # #region agent log
        with open(r'c:\Users\mason\OneDrive\Desktop\Cursor\website\.cursor\debug.log', 'a') as f:
            f.write(json.dumps({'sessionId': 'debug-session', 'runId': 'run1', 'hypothesisId': 'C', 'location': 'app.py:2815', 'message': 'Using old max (calculated < old_max, no buy_orders_count)', 'data': {'project': project, 'calculated_count': calculated_count, 'old_max': old_max}, 'timestamp': int(datetime.now().timestamp() * 1000)}) + '\n')
        # #endregion
    
    # Use the stored max count
    total_trades_count = _max_trade_counts[project]
    # #region agent log
    with open(r'c:\Users\mason\OneDrive\Desktop\Cursor\website\.cursor\debug.log', 'a') as f:
        f.write(json.dumps({'sessionId': 'debug-session', 'runId': 'run1', 'hypothesisId': 'C', 'location': 'app.py:2770', 'message': 'Final total_trades_count', 'data': {'project': project, 'calculated_count': calculated_count, 'total_trades_count': total_trades_count, 'old_max': old_max}, 'timestamp': int(datetime.now().timestamp() * 1000)}) + '\n')
    # #endregion
    
    # Final safety check: ensure we never return a count less than what we've seen before
    # BUT: Skip this check if buy_orders_count was provided, as it's authoritative and can legitimately be lower
    if buy_orders_count is None and total_trades_count < old_max:
        print(f"CRITICAL ERROR: total_trades_count ({total_trades_count}) is less than old_max ({old_max})! This should never happen!")
        total_trades_count = old_max
        _max_trade_counts[project] = old_max
        save_max_trade_counts(_max_trade_counts)
    
    # Calculate total P&L: current portfolio value - baseline equity
    # Use portfolio_value if provided, otherwise fetch it
    if portfolio_value is not None:
        current_equity = portfolio_value
    else:
        # Fallback: fetch live equity
        if project == 2:
            live_equity_data = get_live_portfolio_equity_2()
            current_equity = live_equity_data['live_equity'] if live_equity_data else 10000.0
        else:
            live_equity_data = get_live_portfolio_equity()
            current_equity = live_equity_data['live_equity'] if live_equity_data else 10000.0
    
    # Get baseline equity from API (actual account value) or fallback to config
    baseline = get_baseline(project)
    baseline_equity = get_baseline_equity_from_api(project)
    if baseline_equity is None:
        # Fallback to config value if API fetch fails
        baseline_equity = baseline['baselineEquity']
        print(f"Using config baseline equity for project {project}: {baseline_equity}")
    else:
        print(f"Using API baseline equity for project {project}: {baseline_equity}")
    
    # Also calculate from trades for comparison/debugging
    closed_pnl = sum(t.get('pnl', 0) or 0 for t in closed_trades)
    unrealized_pnl = sum(t.get('pnl', 0) or 0 for t in open_trades)
    trade_based_pnl = closed_pnl + unrealized_pnl
    
    # If there are no trades at all, P&L should be 0
    if total_trades_count == 0:
        total_pnl = 0
    else:
        total_pnl = current_equity - baseline_equity
    
    # Debug logging for P&L calculation
    print(f"P&L_DEBUG: total_trades={len(trades)}, closed={len(closed_trades)}, open={len(open_trades)}")
    print(f"P&L_DEBUG: baseline_equity={baseline_equity}, current_equity={current_equity}, total_pnl={total_pnl}")
    print(f"P&L_DEBUG: closed_pnl={closed_pnl}, unrealized_pnl={unrealized_pnl}, trade_based_pnl={trade_based_pnl}")
    
    if not closed_trades:
        return {
            'total_trades': total_trades_count,
            'winning_trades': 0,
            'losing_trades': 0,
            'win_rate': None,  # None when no closed trades (frontend will show N/A)
            'total_pnl': round(total_pnl, 2),  # Include unrealized P&L
            'average_pnl': 0,
            'average_win': 0,
            'average_loss': 0
        }
    
    winning_trades = [t for t in closed_trades if (t.get('pnl', 0) or 0) > 0]
    losing_trades = [t for t in closed_trades if (t.get('pnl', 0) or 0) <= 0]
    
    average_pnl = closed_pnl / len(closed_trades) if closed_trades else 0
    average_win = sum(t.get('pnl', 0) or 0 for t in winning_trades) / len(winning_trades) if winning_trades else 0
    average_loss = sum(t.get('pnl', 0) or 0 for t in losing_trades) / len(losing_trades) if losing_trades else 0
    win_rate = (len(winning_trades) / len(closed_trades)) * 100 if closed_trades else 0
    
    return {
        'total_trades': total_trades_count,
        'winning_trades': len(winning_trades),
        'losing_trades': len(losing_trades),
        'win_rate': round(win_rate, 2),
        'total_pnl': round(total_pnl, 2),  # Includes unrealized P&L from open positions
        'average_pnl': round(average_pnl, 2),
        'average_win': round(average_win, 2),
        'average_loss': round(average_loss, 2)
    }


def get_project_for_algorithm(algorithm_name):
    """Determine which project (1 or 2) an algorithm belongs to based on name."""
    algorithm_name_lower = algorithm_name.lower()
    if 'crypto' in algorithm_name_lower or 'coin' in algorithm_name_lower:
        return 2
    elif 'swing' in algorithm_name_lower:
        return 1
    # Default to Project 1 for backward compatibility
    return 1


@app.route('/api/algorithms', methods=['GET'])
def get_algorithms():
    """Get list of all trading algorithms."""
    # Prevent caching to ensure fresh data on each request
    response_headers = {
        'Cache-Control': 'no-cache, no-store, must-revalidate',
        'Pragma': 'no-cache',
        'Expires': '0'
    }
    algorithms = []
    
    # Project 1: Swing Trading Agent (Stocks)
    try:
        trades_1, buy_orders_count_1 = get_alpaca_orders(limit=1000, project=1)
        stats_1 = calculate_stats(trades_1, project=1, buy_orders_count=buy_orders_count_1)
        live_equity_data_1 = get_live_portfolio_equity()
        portfolio_value_1 = live_equity_data_1['live_equity'] if live_equity_data_1 else 0
        
        algorithms.append({
            'name': 'Swing Trading Agent',
            'description': 'Automated trading agent trained on historical data regarding momentum and mean reversion. Continuously monitors technical indicators for 200 stocks and exectues trades based on price action patterns and learned thresholds.',
            'strategy': 'Stocks',
            'stats': {
                'totalPnl': stats_1['total_pnl'],
                'winRate': stats_1['win_rate'],
                'totalTrades': stats_1['total_trades'],
                'averagePnl': stats_1['average_pnl'],
                'winningTrades': stats_1['winning_trades'],
                'losingTrades': stats_1['losing_trades']
            },
            'portfolioValue': portfolio_value_1
        })
    except Exception as e:
        print(f"Error fetching Project 1 data: {e}")
        # Add with default values if error
        algorithms.append({
            'name': 'Swing Trading Agent',
            'description': 'Automated trading agent trained on historical data regarding momentum and mean reversion. Continuously monitors technical indicators for 200 stocks and exectues trades based on price action patterns and learned thresholds.',
            'strategy': 'Stocks',
            'stats': {
                'totalPnl': 0,
                'winRate': None,
                'totalTrades': 0
            },
            'portfolioValue': 0
        })
    
    # Project 2: Crypto Trading Agent
    try:
        trades_2, buy_orders_count_2 = get_alpaca_orders_2(limit=1000)
        live_equity_data_2 = get_live_portfolio_equity_2()
        portfolio_value_2 = live_equity_data_2['live_equity'] if live_equity_data_2 else 0
        # Pass portfolio_value and buy_orders_count to calculate_stats to ensure P&L uses the same value
        stats_2 = calculate_stats(trades_2, project=2, portfolio_value=portfolio_value_2, buy_orders_count=buy_orders_count_2)
        
        algorithms.append({
            'name': 'Coin Trading Agent',
            'description': 'Automated trading agent trained on historical data for different cryptocurrency strategies, accounting for higher volatility and lower liquidity. Monitors indicators for 60 coins and exectues trades based on predefined, risk-managed signals.',
            'strategy': 'Crypto',
            'stats': {
                'totalPnl': stats_2['total_pnl'],
                'winRate': stats_2['win_rate'],
                'totalTrades': stats_2['total_trades'],
                'averagePnl': stats_2['average_pnl'],
                'winningTrades': stats_2['winning_trades'],
                'losingTrades': stats_2['losing_trades']
            },
            'portfolioValue': portfolio_value_2
        })
    except Exception as e:
        print(f"Error fetching Project 2 data: {e}")
        # Add with default values if error
        algorithms.append({
            'name': 'Coin Trading Agent',
            'description': 'Automated trading agent trained on historical data for different cryptocurrency strategies, accounting for higher volatility and lower liquidity. Monitors indicators for 60 coins and exectues trades based on predefined, risk-managed signals.',
            'strategy': 'Crypto',
            'stats': {
                'totalPnl': 0,
                'winRate': None,
                'totalTrades': 0
            },
            'portfolioValue': 0
        })
    
    response = jsonify(algorithms)
    # Add cache-control headers to prevent stale data
    for header, value in response_headers.items():
        response.headers[header] = value
    return response


@app.route('/api/algorithms/<algorithm_name>', methods=['GET'])
def get_algorithm(algorithm_name):
    """Get details for a specific algorithm."""
    algorithm_name_decoded = algorithm_name.replace('_', ' ')
    project = get_project_for_algorithm(algorithm_name_decoded)
    
    if project == 2:
        # Project 2: Crypto
        trades, buy_orders_count = get_alpaca_orders_2(limit=1000)
        live_equity_data = get_live_portfolio_equity_2()
        portfolio_value = live_equity_data['live_equity'] if live_equity_data else 0
        # Pass portfolio_value and buy_orders_count to calculate_stats to ensure P&L uses the same value
        stats = calculate_stats(trades, project=2, portfolio_value=portfolio_value, buy_orders_count=buy_orders_count)
        
        return jsonify({
            'name': algorithm_name_decoded,
            'description': 'Automated trading agent trained on historical data for different cryptocurrency strategies, accounting for higher volatility and lower liquidity. Monitors indicators for 60 coins and exectues trades based on predefined, risk-managed signals.',
            'strategy': 'Crypto',
            'stats': {
                'totalPnl': stats['total_pnl'],
                'winRate': stats['win_rate'],
                'totalTrades': stats['total_trades'],
                'averagePnl': stats['average_pnl'],
                'averageWin': stats['average_win'],
                'averageLoss': stats['average_loss']
            },
            'portfolioValue': portfolio_value
        })
    else:
        # Project 1: Stocks (default)
        trades, buy_orders_count = get_alpaca_orders(limit=1000)
        live_equity_data = get_live_portfolio_equity()
        portfolio_value = live_equity_data['live_equity'] if live_equity_data else 0
        # Pass portfolio_value and buy_orders_count to calculate_stats to ensure P&L uses the same value
        stats = calculate_stats(trades, project=1, portfolio_value=portfolio_value, buy_orders_count=buy_orders_count)
        
        return jsonify({
            'name': algorithm_name_decoded,
            'description': 'Automated trading agent trained on historical data regarding momentum and mean reversion. Continuously monitors technical indicators for 200 stocks and exectues trades based on price action patterns and learned thresholds.',
            'strategy': 'Stocks',
            'stats': {
                'totalPnl': stats['total_pnl'],
                'winRate': stats['win_rate'],
                'totalTrades': stats['total_trades'],
                'averagePnl': stats['average_pnl'],
                'averageWin': stats['average_win'],
                'averageLoss': stats['average_loss']
            },
            'portfolioValue': portfolio_value
        })


def get_day_chart_live_value():
    """Get live value from Day chart's portfolio history (period=1D, timeframe=1Min, extended_hours=true).
    
    Returns:
        tuple: (live_value: float, live_asof_timestamp_ms: int) or (None, None) if error
    """
    if not trading_client or not ALPACA_API_KEY or not ALPACA_SECRET_KEY:
        return None, None
    
    try:
        now = datetime.now()
        
        # Use same params as Day chart
        if now.weekday() >= 5:  # Saturday or Sunday
            display_date = get_last_trading_day(now)
            date_end = display_date.strftime('%Y-%m-%d')
        else:
            date_end = now.strftime('%Y-%m-%d')
        
        period = '1D'
        alpaca_timeframe = '1Min'
        extended_hours = 'true'
        
        # Make API request to Alpaca portfolio history endpoint (same as Day chart)
        url = f"{ALPACA_BASE_URL}/v2/account/portfolio/history"
        headers = {
            "APCA-API-KEY-ID": ALPACA_API_KEY,
            "APCA-API-SECRET-KEY": ALPACA_SECRET_KEY
        }
        params = {
            "period": period,
            "timeframe": alpaca_timeframe,
            "date_end": date_end,
            "extended_hours": extended_hours
        }
        
        response = requests.get(url, headers=headers, params=params)
        
        if response.status_code == 200:
            data = response.json()
            timestamps = data.get('timestamp', [])
            equity_values = data.get('equity', [])
            
            if not timestamps or not equity_values:
                return None, None
            
            # Get last equity value and timestamp
            live_value = float(equity_values[-1]) if equity_values else None
            last_timestamp = timestamps[-1] if timestamps else None
            
            if live_value is None or last_timestamp is None:
                return None, None
            
            # Convert timestamp to milliseconds
            if isinstance(last_timestamp, (int, float)):
                # Timestamp is in seconds, convert to ms
                live_asof_timestamp_ms = int(last_timestamp * 1000)
            else:
                # Try parsing as ISO string
                try:
                    dt = datetime.fromisoformat(str(last_timestamp).replace('Z', '+00:00'))
                    if dt.tzinfo:
                        dt = dt.replace(tzinfo=None)
                    live_asof_timestamp_ms = int(dt.timestamp() * 1000)
                except Exception as e:
                    print(f"Error parsing timestamp {last_timestamp}: {e}")
                    return None, None
            
            return live_value, live_asof_timestamp_ms
        else:
            print(f"Error fetching Day chart portfolio history: {response.status_code} - {response.text}")
            return None, None
            
    except Exception as e:
        print(f"Error getting Day chart live value: {e}")
        import traceback
        traceback.print_exc()
        return None, None


@app.route('/api/algorithms/<algorithm_name>/performance', methods=['GET'])
def get_performance(algorithm_name):
    """Get performance data for a specific timeframe using Alpaca portfolio history."""
    timeframe = request.args.get('timeframe', 'all')
    
    algorithm_name_decoded = algorithm_name.replace('_', ' ')
    project = get_project_for_algorithm(algorithm_name_decoded)
    
    # Use Alpaca portfolio history instead of calculating from trades
    if project == 2:
        performance_data = get_alpaca_portfolio_history_2(timeframe)
    else:
        performance_data = get_alpaca_portfolio_history(timeframe)
    
    # For month/3m/ytd/year/all: use Day chart's live value to update last point
    # For day/week: use existing logic (unchanged)
    is_month_plus = timeframe in ['month', '3m', 'ytd', 'year', 'all']
    as_of_timestamp = None
    
    if is_month_plus:
        # Get live value from Day chart's portfolio history
        if project == 2:
            live_value, live_asof_timestamp_ms = get_day_chart_live_value_2()
        else:
            live_value, live_asof_timestamp_ms = get_day_chart_live_value()
        
        if live_value is not None and performance_data and len(performance_data) > 0:
            # Get last point info BEFORE replacement
            last_point = performance_data[-1]
            first_value = performance_data[0].get('equity') if performance_data else None
            last_value_before = last_point.get('equity')
            last_timestamp = last_point.get('timestamp', 0)
            points_count = len(performance_data)
            
            # Replace the last point's VALUE and TIMESTAMP with live_value and current time
            # This ensures the far-right value equals the headline value and shows current date
            initial_equity = performance_data[0].get('equity', live_value)
            returns = live_value - initial_equity
            
            # Use current timestamp (always use current time, not Alpaca's timestamp which may be old)
            # This ensures the x-axis shows today's date, not an old date
            # For crypto, always use current time since it trades 24/7
            current_timestamp = int(datetime.now().timestamp() * 1000)
            current_date = datetime.fromtimestamp(current_timestamp / 1000).strftime('%Y-%m-%dT%H:%M:%S')
            
            # Force replacement of last point's equity value and timestamp
            performance_data[-1] = {
                'date': current_date,  # Update to current date
                'returns': round(returns, 2),
                'equity': round(live_value, 2),  # Update value to live_value (must equal headline)
                'timestamp': current_timestamp  # Update to current timestamp
            }
            
            last_value_after = performance_data[-1].get('equity')
            as_of_timestamp = live_asof_timestamp_ms
            
            # Verification logs for all month+ timeframes
            print(f"MONTH_PLUS_UPDATE [{timeframe}]: points_count={points_count}, first_value={first_value}, last_value_BEFORE={last_value_before}, live_value={live_value}, last_value_AFTER={last_value_after}")
            if abs(last_value_after - live_value) > 0.01:  # Allow small rounding differences
                print(f"ERROR [{timeframe}]: last_value_AFTER ({last_value_after}) != live_value ({live_value})")
            
            # Additional logs specifically for ytd/year/all
            if timeframe in ['ytd', 'year', 'all']:
                print(f"YTD_YEAR_ALL_UPDATE [{timeframe}]: last_value_before={last_value_before}, live_value={live_value}, last_value_after={last_value_after}, points_count={points_count}")
                if abs(last_value_after - live_value) > 0.01:
                    print(f"CRITICAL_ERROR [{timeframe}]: last_value_after ({last_value_after}) != live_value ({live_value}) - backend replacement failed!")
                # Log the actual last point being returned
                print(f"YTD_YEAR_ALL_RETURN [{timeframe}]: Returning last point: equity={performance_data[-1].get('equity')}, timestamp={performance_data[-1].get('timestamp')}, date={performance_data[-1].get('date')}")
                
                # For year/ytd/all: append one extra point to create visible end segment
                # This creates a horizontal line at the end showing the current value
                # Use current timestamp + 60 seconds for the extra point
                extra_timestamp_ms = current_timestamp + (60 * 1000)  # Add 60 seconds to current time
                extra_date = datetime.fromtimestamp(extra_timestamp_ms / 1000).strftime('%Y-%m-%dT%H:%M:%S')
                performance_data.append({
                    'date': extra_date,
                    'returns': round(returns, 2),
                    'equity': round(live_value, 2),  # Same value as last point
                    'timestamp': extra_timestamp_ms
                })
                # Ensure sorted by timestamp
                performance_data.sort(key=lambda x: x.get('timestamp', 0))
                print(f"YTD_YEAR_ALL_EXTRA_POINT [{timeframe}]: Added extra point at timestamp={extra_timestamp_ms}, value={live_value}")
        elif live_value is None:
            print(f"WARNING [{timeframe}]: live_value is None, cannot update last point")
        elif not performance_data or len(performance_data) == 0:
            print(f"WARNING [{timeframe}]: performance_data is empty, cannot update last point")
    else:
        # For day/week: use existing logic
        if project == 2:
            live_equity_data = get_live_portfolio_equity_2()
        else:
            live_equity_data = get_live_portfolio_equity()
        now_ms = int(datetime.now().timestamp() * 1000)
        
        if live_equity_data:
            live_equity_extended = live_equity_data['live_equity']
            live_snapshot_ts = live_equity_data.get('as_of_timestamp', now_ms)
            five_minutes_ms = 5 * 60 * 1000
            
            if not performance_data:
                performance_data = [{
                    'date': datetime.fromtimestamp(live_snapshot_ts / 1000).strftime('%Y-%m-%dT%H:%M:%S'),
                    'returns': 0,
                    'equity': live_equity_extended,
                    'timestamp': live_snapshot_ts
                }]
                as_of_timestamp = live_snapshot_ts
            else:
                last_point = performance_data[-1]
                last_history_time = last_point.get('timestamp', 0)
                
                if last_history_time > 0 and abs(live_snapshot_ts - last_history_time) <= five_minutes_ms:
                    # Replace last point
                    initial_equity = performance_data[0].get('equity', live_equity_extended)
                    returns = live_equity_extended - initial_equity
                    performance_data[-1] = {
                        'date': datetime.fromtimestamp(live_snapshot_ts / 1000).strftime('%Y-%m-%dT%H:%M:%S'),
                        'returns': round(returns, 2),
                        'equity': live_equity_extended,
                        'timestamp': live_snapshot_ts
                    }
                    as_of_timestamp = live_snapshot_ts
                else:
                    # Append new point
                    initial_equity = performance_data[0].get('equity', live_equity_extended)
                    returns = live_equity_extended - initial_equity
                    performance_data.append({
                        'date': datetime.fromtimestamp(live_snapshot_ts / 1000).strftime('%Y-%m-%dT%H:%M:%S'),
                        'returns': round(returns, 2),
                        'equity': live_equity_extended,
                        'timestamp': live_snapshot_ts
                    })
                    as_of_timestamp = live_snapshot_ts
                
                # Ensure sorted by timestamp
                performance_data.sort(key=lambda x: x.get('timestamp', 0))
    
    return jsonify({
        'algorithm': algorithm_name_decoded,
        'timeframe': timeframe,
        'data': performance_data,
        'as_of_timestamp': as_of_timestamp  # Return separately for display
    })


@app.route('/api/live-equity', methods=['GET'])
def get_live_equity():
    """Get live portfolio equity with extended-hours prices."""
    live_data = get_live_portfolio_equity()
    if live_data is None:
        return jsonify({'error': 'Failed to compute live equity'}), 500
    return jsonify(live_data)


@app.route('/api/portfolio/live_equity_extended', methods=['GET'])
def get_portfolio_live_equity_extended():
    """Get live portfolio equity extended using the same data source as Day chart.
    
    Uses Alpaca portfolio history with same params as Day chart:
    - period=1D, timeframe=1Min, extended_hours=true
    
    Returns:
        JSON: { value: equity[-1], as_of: timestamp_iso }
    """
    if not trading_client or not ALPACA_API_KEY or not ALPACA_SECRET_KEY:
        return jsonify({'error': 'Trading client or API credentials not available'}), 500
    
    try:
        now = datetime.now()
        
        # Use same params as Day chart
        if now.weekday() >= 5:  # Saturday or Sunday
            display_date = get_last_trading_day(now)
            date_end = display_date.strftime('%Y-%m-%d')
        else:
            date_end = now.strftime('%Y-%m-%d')
        
        period = '1D'
        alpaca_timeframe = '1Min'  # 1-minute intervals for intraday
        extended_hours = 'true'
        
        # Make API request to Alpaca portfolio history endpoint (same as Day chart)
        url = f"{ALPACA_BASE_URL}/v2/account/portfolio/history"
        headers = {
            "APCA-API-KEY-ID": ALPACA_API_KEY,
            "APCA-API-SECRET-KEY": ALPACA_SECRET_KEY
        }
        params = {
            "period": period,
            "timeframe": alpaca_timeframe,
            "date_end": date_end,
            "extended_hours": extended_hours
        }
        
        response = requests.get(url, headers=headers, params=params)
        
        if response.status_code == 200:
            data = response.json()
            timestamps = data.get('timestamp', [])
            equity_values = data.get('equity', [])
            
            if not timestamps or not equity_values:
                return jsonify({'error': 'No portfolio history data returned'}), 500
            
            # Get last equity value and timestamp (same as Day chart uses)
            headline_value = float(equity_values[-1]) if equity_values else None
            last_timestamp = timestamps[-1] if timestamps else None
            
            if headline_value is None or last_timestamp is None:
                return jsonify({'error': 'Invalid portfolio history data'}), 500
            
            # Convert timestamp to UTC datetime and format
            if isinstance(last_timestamp, (int, float)):
                # Timestamp is in seconds, convert to UTC datetime
                dt_utc = datetime.fromtimestamp(last_timestamp, tz=timezone.utc)
            else:
                # Try parsing as ISO string
                try:
                    dt_str = str(last_timestamp).replace('Z', '+00:00')
                    dt_utc = datetime.fromisoformat(dt_str)
                    if dt_utc.tzinfo is None:
                        # Assume UTC if no timezone info
                        dt_utc = dt_utc.replace(tzinfo=timezone.utc)
                    else:
                        # Convert to UTC
                        dt_utc = dt_utc.astimezone(timezone.utc)
                except Exception as e:
                    print(f"Error parsing timestamp {last_timestamp}: {e}")
                    return jsonify({'error': 'Invalid timestamp format'}), 500
            
            # Format as ISO UTC with Z
            as_of_utc = dt_utc.isoformat().replace('+00:00', 'Z')
            
            # Format as ET display string: "Dec 19, 2025 8:00 PM ET"
            # Convert UTC to ET
            try:
                from zoneinfo import ZoneInfo
                et_tz = ZoneInfo('America/New_York')
            except ImportError:
                # Fallback for Python < 3.9: use pytz
                import pytz
                et_tz = pytz.timezone('America/New_York')
            
            dt_et = dt_utc.astimezone(et_tz)
            as_of_et_display = dt_et.strftime('%b %d, %Y %I:%M %p ET')
            
            # Log headline_value and as_of
            print(f"LIVE_EQUITY_EXTENDED: headline_value={headline_value}, as_of_utc={as_of_utc}, as_of_et_display={as_of_et_display}")
            
            return jsonify({
                'value': round(headline_value, 2),
                'as_of_utc': as_of_utc,
                'as_of_et_display': as_of_et_display
            })
        else:
            print(f"Error fetching portfolio history: {response.status_code} - {response.text}")
            return jsonify({'error': 'Failed to fetch portfolio history'}), 500
            
    except Exception as e:
        print(f"Error computing live equity extended: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Failed to compute live equity extended'}), 500


@app.route('/api/algorithms/<algorithm_name>/trades', methods=['GET'])
def get_trades(algorithm_name):
    """Get recent trades for an algorithm."""
    limit = request.args.get('limit', 10, type=int)
    
    algorithm_name_decoded = algorithm_name.replace('_', ' ')
    project = get_project_for_algorithm(algorithm_name_decoded)
    
    if project == 2:
        trades, _ = get_alpaca_orders_2(limit=1000)
    else:
        trades, _ = get_alpaca_orders(limit=1000)
    
    # Return most recent trades
    recent_trades = trades[:limit]
    
    return jsonify({
        'algorithm': algorithm_name_decoded,
        'trades': recent_trades,
        'total': len(trades)
    })


@app.route('/api/algorithms/<algorithm_name>/stats', methods=['GET'])
def get_stats(algorithm_name):
    """Get statistics for an algorithm."""
    algorithm_name_decoded = algorithm_name.replace('_', ' ')
    project = get_project_for_algorithm(algorithm_name_decoded)
    
    if project == 2:
        trades, buy_orders_count = get_alpaca_orders_2(limit=1000)
        live_equity_data = get_live_portfolio_equity_2()
        portfolio_value = live_equity_data['live_equity'] if live_equity_data else 0
        stats = calculate_stats(trades, project=2, portfolio_value=portfolio_value, buy_orders_count=buy_orders_count)
    else:
        trades, buy_orders_count = get_alpaca_orders(limit=1000)
        live_equity_data = get_live_portfolio_equity()
        portfolio_value = live_equity_data['live_equity'] if live_equity_data else 0
        stats = calculate_stats(trades, project=1, portfolio_value=portfolio_value, buy_orders_count=buy_orders_count)
    
    return jsonify({
        'algorithm': algorithm_name_decoded,
        'stats': {
            'totalTrades': stats['total_trades'],
            'winningTrades': stats['winning_trades'],
            'losingTrades': stats['losing_trades'],
            'winRate': stats['win_rate'],
            'totalPnl': stats['total_pnl'],
            'averagePnl': stats['average_pnl'],
            'averageWin': stats['average_win'],
            'averageLoss': stats['average_loss']
        }
    })


@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    alpaca_status = 'connected' if trading_client else 'not_configured'
    return jsonify({
        'status': 'healthy',
        'alpaca': alpaca_status,
        'has_api_key': bool(ALPACA_API_KEY)
    })


def get_today_start_ny():
    """Get start of today in America/New_York timezone as ISO string."""
    try:
        if ZoneInfo:
            ny_tz = ZoneInfo('America/New_York')
            now_ny = datetime.now(ny_tz)
            today_start = now_ny.replace(hour=0, minute=0, second=0, microsecond=0)
            return today_start.isoformat()
        else:
            # Fallback: approximate NY timezone offset (EST/EDT)
            # EST is UTC-5, EDT is UTC-4
            # Simple approximation: use UTC-5 for now
            now_utc = datetime.now(timezone.utc)
            # Subtract 5 hours to get approximate EST
            est_offset = timedelta(hours=-5)
            now_est = now_utc + est_offset
            today_start = now_est.replace(hour=0, minute=0, second=0, microsecond=0)
            # Convert back to UTC for ISO string
            today_start_utc = today_start - est_offset
            return today_start_utc.isoformat()
    except Exception as e:
        # Fallback to UTC if zoneinfo fails
        print(f"Warning: Could not use ZoneInfo, falling back to UTC: {e}")
        now_utc = datetime.now(timezone.utc)
        today_start = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
        return today_start.isoformat()


def equity_at_or_after(points, t0_ms):
    """
    Find the equity at the first point with t >= t0_ms (or nearest after).
    Returns (equity, timestamp_ms) or (None, None) if no point found.
    """
    for point in points:
        if point['t'] >= t0_ms:
            return point['equity'], point['t']
    return None, None


def equity_at_or_before(points, t0_ms):
    """
    Find the equity at the last point with t <= t0_ms (nearest before or at).
    If no point exists before t0, return the first point.
    Returns (equity, timestamp_ms) or (None, None) if no points exist.
    """
    if not points:
        return None, None
    
    # Points should be sorted by timestamp
    last_before = None
    last_before_ts = None
    
    for point in points:
        point_ts = point['t']
        if point_ts <= t0_ms:
            if point.get('equity') is not None:
                last_before = point['equity']
                last_before_ts = point_ts
        else:
            # We've passed t0, stop searching
            break
    
    if last_before is not None:
        return last_before, last_before_ts
    
    # If no point before t0, return first point
    first_point = points[0]
    if first_point.get('equity') is not None:
        return first_point['equity'], first_point['t']
    
    return None, None


def equity_latest(points):
    """
    Get the latest equity point.
    Returns (equity, timestamp_ms) or (None, None) if no points.
    """
    if not points:
        return None, None
    last_point = points[-1]
    return last_point['equity'], last_point['t']


def parse_portfolio_history(data, baseline_start, account_equity_hint=None):
    """
    Parse Alpaca portfolio history response into canonical equity points.
    Returns list of {t: ms, equity: number} filtered to >= baseline.
    """
    timestamps = data.get('timestamp', [])
    equity_values = data.get('equity', [])
    base_value_raw = data.get('base_value', None)
    
    if not timestamps or not equity_values or len(timestamps) != len(equity_values):
        return []

    # Alpaca sometimes returns `equity` as a delta from `base_value` (especially around resets / some account types).
    # Detect this and normalize to absolute equity.
    base_value = None
    try:
        base_value = float(base_value_raw) if base_value_raw is not None else None
    except (ValueError, TypeError):
        base_value = None

    interpret_equity_as_delta = False
    if base_value is not None and equity_values:
        try:
            last_val = float(equity_values[-1])
            # Strong signal: if base_value + last_val matches the live account equity, `equity` is a delta.
            if account_equity_hint is not None:
                try:
                    acct_eq = float(account_equity_hint)
                    if acct_eq > 0 and abs((base_value + last_val) - acct_eq) <= max(1.0, acct_eq * 0.01):
                        interpret_equity_as_delta = True
                except (ValueError, TypeError):
                    pass
            # Heuristic fallback: if values are "small" compared to base_value, treat as delta.
            if not interpret_equity_as_delta:
                sample = []
                for v in equity_values[: min(50, len(equity_values))]:
                    try:
                        sample.append(abs(float(v)))
                    except (ValueError, TypeError):
                        continue
                if sample and max(sample) < base_value * 0.5:
                    interpret_equity_as_delta = True
        except (ValueError, TypeError):
            pass
    
    baseline_ts_ms = int(baseline_start.timestamp() * 1000)
    points = []
    
    for i, ts in enumerate(timestamps):
        # Convert timestamp to milliseconds
        if isinstance(ts, (int, float)):
            ts_val_ms = int(ts * 1000) if ts < 1e10 else int(ts)
        else:
            try:
                dt = datetime.fromisoformat(str(ts).replace('Z', '+00:00'))
                if dt.tzinfo:
                    dt = dt.replace(tzinfo=None)
                ts_val_ms = int(dt.timestamp() * 1000)
            except:
                continue
        
        # Only include points >= baseline
        if ts_val_ms < baseline_ts_ms:
            continue
        
        equity = equity_values[i]
        # Ensure numeric conversion (Alpaca may return strings)
        try:
            equity_float = float(equity) if equity is not None else None
            if equity_float is not None and interpret_equity_as_delta and base_value is not None:
                equity_float = base_value + equity_float
            if equity_float is not None:
                points.append({'t': ts_val_ms, 'equity': equity_float})
        except (ValueError, TypeError):
            continue
    
    # Sort by timestamp
    points.sort(key=lambda x: x['t'])
    return points


def compute_micro_metrics(project=1):
    """
    Compute micro-metrics for a given project using Alpaca API.
    Uses separate portfolio history windows for Day/Week/Month calculations.
    All metrics are computed ONLY from baselineStartIso forward.
    
    Returns:
        dict with keys: pnlWeek, pnlMonth, avgReturnPct, wins, losses, 
        tradesToday, lastTradeHoursAgo, dayChangePct, investedPct
        Returns None (never 0) when data is unavailable.
    """
    # Get baseline configuration
    baseline = get_baseline(project)
    baseline_start = get_baseline_start_datetime(project)
    baseline_start_iso = baseline['baselineStartIso']
    baseline_equity = baseline['baselineEquity']
    baseline_start_ms = int(baseline_start.timestamp() * 1000)
    
    # Select appropriate client and credentials based on project
    if project == 2:
        base_url = ALPACA_BASE_URL_2
        api_key = ALPACA_API_KEY_2
        secret_key = ALPACA_SECRET_KEY_2
        get_account_func = get_alpaca_account_2
    else:
        base_url = ALPACA_BASE_URL
        api_key = ALPACA_API_KEY
        secret_key = ALPACA_SECRET_KEY
        get_account_func = get_alpaca_account
    
    if not api_key or not secret_key:
        return {
            'pnlWeek': None, 'pnlMonth': None, 'avgReturnPct': None,
            'wins': None, 'losses': None, 'tradesToday': None,  # None when API keys missing (truly missing)
            'lastTradeHoursAgo': None, 'dayChangePct': None, 'investedPct': None
        }
    
    headers = {
        "APCA-API-KEY-ID": api_key,
        "APCA-API-SECRET-KEY": secret_key
    }
    
    result = {
        'pnlWeek': None,
        'pnlMonth': None,
        'avgReturnPct': None,
        'wins': None,
        'losses': None,
        'tradesToday': None,  # Use None as default, set to 0 only when we have data confirming 0 trades
        'lastTradeHoursAgo': None,
        'dayChangePct': None,
        'investedPct': None
    }
    
    try:
        from concurrent.futures import ThreadPoolExecutor, as_completed
        
        # Get today start - use NY timezone for stocks, UTC for crypto (24/7 trading)
        now_utc = datetime.now(timezone.utc)
        
        if project == 2:  # Crypto - use UTC for "today" since crypto trades 24/7
            today_start_utc = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
            today_start_ny = today_start_utc.isoformat()  # ISO format for API
            day_start_utc = today_start_utc
            day_start_ms = int(day_start_utc.timestamp() * 1000)
        else:  # Stocks/Options - use NY timezone
            today_start_ny_str = get_today_start_ny()
            today_start_ny = today_start_ny_str
            # Parse the ISO string to get UTC datetime
            try:
                today_start_utc = datetime.fromisoformat(today_start_ny_str.replace('Z', '+00:00'))
                if today_start_utc.tzinfo is None:
                    today_start_utc = today_start_utc.replace(tzinfo=timezone.utc)
            except:
                # Fallback to calculating NY timezone
                if ZoneInfo:
                    ny_tz = ZoneInfo('America/New_York')
                else:
                    import pytz
                    ny_tz = pytz.timezone('America/New_York')
                now_ny = datetime.now(ny_tz)
                day_start_ny_dt = now_ny.replace(hour=0, minute=0, second=0, microsecond=0)
                today_start_utc = day_start_ny_dt.astimezone(timezone.utc)
            
            # Calculate window starts in NY timezone, then convert to UTC
            if ZoneInfo:
                ny_tz = ZoneInfo('America/New_York')
            else:
                import pytz
                ny_tz = pytz.timezone('America/New_York')
            
            now_ny = datetime.now(ny_tz)
            day_start_ny_dt = now_ny.replace(hour=0, minute=0, second=0, microsecond=0)
            day_start_utc = day_start_ny_dt.astimezone(timezone.utc)
            day_start_ms = int(day_start_utc.timestamp() * 1000)
        
        # Calculate desired window starts (in UTC)
        desired_week_start = now_utc - timedelta(days=7)
        desired_month_start = now_utc - timedelta(days=30)
        desired_week_start_ms = int(desired_week_start.timestamp() * 1000)
        desired_month_start_ms = int(desired_month_start.timestamp() * 1000)
        
        # Check if reset happened inside windows (before clamping)
        reset_inside_week = baseline_start_ms > desired_week_start_ms
        reset_inside_month = baseline_start_ms > desired_month_start_ms
        
        # Clamp windows to baseline (cannot start before baseline)
        day_start_ms = max(day_start_ms, baseline_start_ms)
        week_start_ms = max(desired_week_start_ms, baseline_start_ms)
        month_start_ms = max(desired_month_start_ms, baseline_start_ms)
        
        # Fetch portfolio history using separate windows
        url_history = f"{base_url}/v2/account/portfolio/history"
        url_activities = f"{base_url}/v2/account/activities"
        url_account = f"{base_url}/v2/account"
        
        request_configs = {
            'history_1d': (url_history, {"period": "1D", "timeframe": "5Min", "extended_hours": "true"}),
            'history_7d': (url_history, {"period": "7D", "timeframe": "1H", "extended_hours": "true"}),
            'history_30d': (url_history, {"period": "30D", "timeframe": "1D", "extended_hours": "true"}),
            'account': (url_account, {}),
            'fills_today': (url_activities, {"activity_types": "FILL", "after": today_start_ny, "direction": "asc", "page_size": 200}),
            'latest_fill': (url_activities, {"activity_types": "FILL", "direction": "desc", "page_size": 1}),
            'fills_7d': (url_activities, {"activity_types": "FILL", "after": baseline_start_iso, "direction": "asc", "page_size": 500}),
        }
        
        def fetch_request(key, url, params):
            try:
                resp = requests.get(url, headers=headers, params=params, timeout=10)
                return key, resp
            except Exception as e:
                print(f"Error fetching {key}: {e}")
                return key, None
        
        # Fetch account and all HTTP requests in parallel
        responses = {}
        account = None
        
        with ThreadPoolExecutor(max_workers=7) as executor:
            # Submit account fetch (using function)
            account_future = executor.submit(get_account_func)
            
            # Submit all HTTP requests
            futures = {
                executor.submit(fetch_request, key, url, params): key 
                for key, (url, params) in request_configs.items()
            }
            
            # Collect results
            for future in as_completed(futures):
                key, resp = future.result()
                responses[key] = resp
            
            # Get account result
            try:
                account = account_future.result()
            except Exception as e:
                print(f"Error fetching account: {e}")
                account = None
        
        # Get account from API response if function didn't work
        response_account = responses.get('account')
        if response_account and response_account.status_code == 200:
            account_data = response_account.json()
            if account and not account.get('equity'):
                # Merge API response if function result is incomplete
                account = {**account, **account_data}
            elif not account:
                account = account_data
        
        # Get equityNow from account (most accurate "now" value)
        equity_now = None
        if account:
            try:
                equity_now = float(account.get('equity', 0))
                if equity_now <= 0:
                    equity_now = None
            except (ValueError, TypeError):
                pass
        
        if equity_now is None:
            # Cannot compute metrics without current equity
            print(f"DEBUG [compute_micro_metrics] project={project}: No equity available from account")
            return result
        
        # Parse separate history windows
        # Day: 1D history with 5Min timeframe
        day_points = []
        response_1d = responses.get('history_1d')
        if response_1d and response_1d.status_code == 200:
            data_1d = response_1d.json()
            day_points = parse_portfolio_history(data_1d, baseline_start, account_equity_hint=equity_now)
            # Filter to >= baseline
            day_points = [p for p in day_points if p['t'] >= baseline_start_ms]
        
        # Week: 7D history with 1H timeframe
        week_points = []
        response_7d = responses.get('history_7d')
        if response_7d and response_7d.status_code == 200:
            data_7d = response_7d.json()
            week_points = parse_portfolio_history(data_7d, baseline_start, account_equity_hint=equity_now)
            # Filter to >= baseline
            week_points = [p for p in week_points if p['t'] >= baseline_start_ms]
        
        # Month: 30D history with 1D timeframe
        month_points = []
        response_30d = responses.get('history_30d')
        if response_30d and response_30d.status_code == 200:
            data_30d = response_30d.json()
            month_points = parse_portfolio_history(data_30d, baseline_start, account_equity_hint=equity_now)
            # Filter to >= baseline
            month_points = [p for p in month_points if p['t'] >= baseline_start_ms]
        
        # ===== DAY CHANGE % =====
        # Preferred: Use account.last_equity if available AND reset not inside today window
        if account and baseline_start_ms <= day_start_ms:
            try:
                last_equity = float(account.get('last_equity', 0))
                if last_equity > 0:
                    result['dayChangePct'] = ((equity_now - last_equity) / last_equity) * 100
                    print(f"DEBUG [dayChangePct] project={project}: Using account last_equity: {last_equity} -> {equity_now} = {result['dayChangePct']:.2f}%")
            except (ValueError, TypeError, KeyError):
                pass
        
        # Fallback: Use 1D history with at-or-before lookup
        if result['dayChangePct'] is None and day_points:
            day_start_equity, _ = equity_at_or_before(day_points, day_start_ms)
            if day_start_equity is not None and day_start_equity > 0:
                result['dayChangePct'] = ((equity_now - day_start_equity) / day_start_equity) * 100
                print(f"DEBUG [dayChangePct] project={project}: Using 1D history at-or-before: {day_start_equity} -> {equity_now} = {result['dayChangePct']:.2f}%")
        
        # ===== WEEK P&L =====
        if week_points:
            # Check if reset happened inside week window (account opened/reset within last 7 days)
            if reset_inside_week:
                # Reset inside window - use baseline equity (show P&L since reset)
                result['pnlWeek'] = equity_now - baseline_equity
                print(f"DEBUG [pnlWeek] project={project}: Reset inside week window, using baseline: {baseline_equity} -> {equity_now}, pnl={result['pnlWeek']}")
            else:
                # Reset before window - use at-or-before lookup
                week_start_equity, week_start_ts = equity_at_or_before(week_points, week_start_ms)
                if week_start_equity is not None and week_start_equity > 0:
                    result['pnlWeek'] = equity_now - week_start_equity
                    print(f"DEBUG [pnlWeek] project={project}: week_start_equity={week_start_equity} (ts={week_start_ts}) -> {equity_now}, pnl={result['pnlWeek']}")
                else:
                    # Fallback: if no point found, use baseline equity (account hasn't been open for full week)
                    result['pnlWeek'] = equity_now - baseline_equity
                    print(f"DEBUG [pnlWeek] project={project}: No week point found, using baseline: {baseline_equity} -> {equity_now}, pnl={result['pnlWeek']}")
        
        # ===== MONTH P&L =====
        # Always show month P&L - if account hasn't been open for full month, show "since reset" (baseline to now)
        # This ensures month P&L is always displayed for crypto, options, and stocks
        if equity_now is not None and baseline_equity is not None:
            if month_points and len(month_points) > 0:
                # Check if reset happened inside month window (account opened/reset within last 30 days)
                if reset_inside_month:
                    # Reset inside window - use baseline equity (show P&L since reset)
                    result['pnlMonth'] = equity_now - baseline_equity
                    print(f"DEBUG [pnlMonth] project={project}: Reset inside month window, using baseline: {baseline_equity} -> {equity_now}, pnl={result['pnlMonth']}")
                else:
                    # Reset before window - use at-or-before lookup for 30-day window
                    month_start_equity, month_start_ts = equity_at_or_before(month_points, month_start_ms)
                    if month_start_equity is not None and month_start_equity > 0:
                        result['pnlMonth'] = equity_now - month_start_equity
                        print(f"DEBUG [pnlMonth] project={project}: month_start_equity={month_start_equity} (ts={month_start_ts}) -> {equity_now}, pnl={result['pnlMonth']}")
                    else:
                        # Fallback: if no point found, use baseline equity
                        # This handles accounts that haven't been open for 30 days
                        result['pnlMonth'] = equity_now - baseline_equity
                        print(f"DEBUG [pnlMonth] project={project}: No month point found, using baseline: {baseline_equity} -> {equity_now}, pnl={result['pnlMonth']}")
            else:
                # No month history points - show P&L since baseline (account hasn't been open for 30 days)
                result['pnlMonth'] = equity_now - baseline_equity
                print(f"DEBUG [pnlMonth] project={project}: No month history available, using baseline: {baseline_equity} -> {equity_now}, pnl={result['pnlMonth']}")
        
        
        # Process fills today (filter by baseline AND today's date)
        response_fills_today = responses.get('fills_today')
        if response_fills_today and response_fills_today.status_code == 200:
            fills_today = response_fills_today.json()
            if isinstance(fills_today, list):
                # Filter fills to only include those after baseline AND within today
                filtered_fills_today = []
                # Use today_start_utc (defined above) for filtering - ensures crypto uses UTC, stocks use NY->UTC
                
                for fill in fills_today:
                    transaction_time = fill.get('transaction_time')
                    if transaction_time:
                        try:
                            fill_time = datetime.fromisoformat(transaction_time.replace('Z', '+00:00'))
                            if fill_time.tzinfo is None:
                                fill_time = fill_time.replace(tzinfo=timezone.utc)
                            
                            # Must be after baseline AND within today (since midnight)
                            # For crypto: today_start_utc is UTC midnight; for stocks: NY midnight converted to UTC
                            if fill_time >= baseline_start and fill_time >= today_start_utc:
                                filtered_fills_today.append(fill)
                        except Exception as e:
                            print(f"Error parsing transaction_time: {e}")
                # Always set tradesToday - 0 if no trades, count if there are trades
                result['tradesToday'] = len(filtered_fills_today)
                print(f"DEBUG [tradesToday] project={project}: Found {result['tradesToday']} trades today (total fills={len(fills_today)}, after baseline and today start)")
            else:
                # Response was not a list - set to 0
                result['tradesToday'] = 0
                print(f"DEBUG [tradesToday] project={project}: Response was not a list, setting to 0")
        else:
            # No response or error - set to 0 (we have no data, so assume 0)
            result['tradesToday'] = 0
            print(f"DEBUG [tradesToday] project={project}: No valid response, setting to 0")
        
        # Process latest fill (must be after baseline)
        response_latest_fill = responses.get('latest_fill')
        if response_latest_fill and response_latest_fill.status_code == 200:
            latest_fills = response_latest_fill.json()
            if isinstance(latest_fills, list) and len(latest_fills) > 0:
                # Find the latest fill that's after baseline
                for fill in latest_fills:
                    transaction_time = fill.get('transaction_time')
                    if transaction_time:
                        try:
                            # Parse ISO timestamp
                            fill_time = datetime.fromisoformat(transaction_time.replace('Z', '+00:00'))
                            if fill_time.tzinfo is None:
                                fill_time = fill_time.replace(tzinfo=timezone.utc)
                            if fill_time >= baseline_start:
                                now_utc = datetime.now(timezone.utc)
                                hours_ago = (now_utc - fill_time).total_seconds() / 3600
                                result['lastTradeHoursAgo'] = round(hours_ago, 1)
                                break
                        except Exception as e:
                            print(f"Error parsing transaction_time: {e}")
        
        # Process account for invested %
        if account:
            try:
                portfolio_value = float(account.get('portfolio_value', 0))
                cash = float(account.get('cash', 0))
                if portfolio_value > 0:
                    invested_value = portfolio_value - cash
                    result['investedPct'] = max(0, min(100, (invested_value / portfolio_value) * 100))
            except (ValueError, TypeError):
                pass
        
        # Process fills 7D for W/L and avg return (already filtered by baseline via API)
        response_fills_7d = responses.get('fills_7d')
        matched_segments = []
        
        # #region agent log - Hypothesis A: Check if fills_7d response exists and is valid
        log_data = {'project': project, 'has_response': response_fills_7d is not None}
        if response_fills_7d:
            log_data['status_code'] = response_fills_7d.status_code if hasattr(response_fills_7d, 'status_code') else None
            log_data['status_code_is_200'] = (hasattr(response_fills_7d, 'status_code') and response_fills_7d.status_code == 200)
        try:
            with open(r'c:\Users\mason\OneDrive\Desktop\Cursor\website\.cursor\debug.log', 'a') as f:
                import json
                f.write(json.dumps({'location': 'app.py:3966', 'message': 'fills_7d response check', 'data': log_data, 'timestamp': int(datetime.now(timezone.utc).timestamp() * 1000), 'sessionId': 'debug-session', 'runId': 'run1', 'hypothesisId': 'A'}) + '\n')
        except: pass
        # #endregion
        
        if response_fills_7d and response_fills_7d.status_code == 200:
            # #region agent log - Entered 200 block
            try:
                with open(r'c:\Users\mason\OneDrive\Desktop\Cursor\website\.cursor\debug.log', 'a') as f:
                    import json
                    f.write(json.dumps({'location': 'app.py:3969', 'message': 'entered status 200 block', 'data': {'project': project}, 'timestamp': int(datetime.now(timezone.utc).timestamp() * 1000), 'sessionId': 'debug-session', 'runId': 'run1', 'hypothesisId': 'A'}) + '\n')
            except: pass
            # #endregion
            fills_7d = response_fills_7d.json()
            
            # #region agent log - Hypothesis B: Check fills structure for crypto
            log_data = {'project': project, 'is_list': isinstance(fills_7d, list), 'total_fills': len(fills_7d) if isinstance(fills_7d, list) else 0}
            if isinstance(fills_7d, list) and len(fills_7d) > 0:
                sample_fill = fills_7d[0]
                log_data['sample_fill_keys'] = list(sample_fill.keys()) if isinstance(sample_fill, dict) else []
                log_data['sample_fill_side'] = sample_fill.get('side') if isinstance(sample_fill, dict) else None
                log_data['sample_fill_symbol'] = sample_fill.get('symbol') if isinstance(sample_fill, dict) else None
            try:
                with open(r'c:\Users\mason\OneDrive\Desktop\Cursor\website\.cursor\debug.log', 'a') as f:
                    import json
                    f.write(json.dumps({'location': 'app.py:3970', 'message': 'fills_7d structure check', 'data': log_data, 'timestamp': int(datetime.now(timezone.utc).timestamp() * 1000), 'sessionId': 'debug-session', 'runId': 'run1', 'hypothesisId': 'B'}) + '\n')
            except: pass
            # #endregion
            
            # Additional client-side filtering to ensure all fills are after baseline
            if isinstance(fills_7d, list):
                filtered_fills_7d = []
                before_baseline_count = 0
                for fill in fills_7d:
                    transaction_time = fill.get('transaction_time')
                    if transaction_time:
                        try:
                            fill_time = datetime.fromisoformat(transaction_time.replace('Z', '+00:00'))
                            if fill_time.tzinfo is None:
                                fill_time = fill_time.replace(tzinfo=timezone.utc)
                            if fill_time >= baseline_start:
                                filtered_fills_7d.append(fill)
                            else:
                                before_baseline_count += 1
                        except Exception as e:
                            print(f"Error parsing transaction_time: {e}")
                fills_7d = filtered_fills_7d
                
                # #region agent log - Hypothesis C: Check baseline filtering
                try:
                    with open(r'c:\Users\mason\OneDrive\Desktop\Cursor\website\.cursor\debug.log', 'a') as f:
                        import json
                        f.write(json.dumps({'location': 'app.py:3985', 'message': 'baseline filtering results', 'data': {'project': project, 'filtered_count': len(fills_7d), 'before_baseline_count': before_baseline_count, 'baseline_start': baseline_start.isoformat()}, 'timestamp': int(datetime.now(timezone.utc).timestamp() * 1000), 'sessionId': 'debug-session', 'runId': 'run1', 'hypothesisId': 'C'}) + '\n')
                except: pass
                # #endregion
            
            if len(fills_7d) > 0:
                # FIFO matching per symbol
                open_lots = {}  # symbol -> list of {qty, price, timestamp}
                buy_count = 0
                sell_count = 0
                
                for fill in fills_7d:
                    symbol = fill.get('symbol')
                    side = fill.get('side', '').upper()
                    try:
                        qty = float(fill.get('qty', 0))
                        price = float(fill.get('price', 0))
                    except (ValueError, TypeError):
                        continue
                    
                    if not symbol or qty == 0 or price == 0:
                        continue
                    
                    # #region agent log - Hypothesis D: Count buy/sell fills
                    if side == 'BUY':
                        buy_count += 1
                    elif side == 'SELL':
                        sell_count += 1
                    # #endregion
                    
                    if side == 'BUY':
                        # Add to open lots
                        if symbol not in open_lots:
                            open_lots[symbol] = []
                        open_lots[symbol].append({'qty': qty, 'price': price})
                    elif side == 'SELL':
                        # Match against open lots (FIFO)
                        if symbol in open_lots and len(open_lots[symbol]) > 0:
                            remaining_qty = qty
                            while remaining_qty > 0 and len(open_lots[symbol]) > 0:
                                lot = open_lots[symbol][0]
                                matched_qty = min(remaining_qty, lot['qty'])
                                
                                # Calculate realized P&L
                                entry_price = lot['price']
                                exit_price = price
                                realized_pnl = (exit_price - entry_price) * matched_qty
                                
                                # Calculate return % and store P&L
                                cost_basis = matched_qty * entry_price
                                if cost_basis > 0:
                                    return_pct = (realized_pnl / cost_basis) * 100
                                    matched_segments.append({
                                        'return_pct': return_pct,
                                        'pnl': realized_pnl,  # Store dollar amount P&L
                                        'qty': matched_qty
                                    })
                                
                                # Update lot
                                lot['qty'] -= matched_qty
                                if lot['qty'] <= 0:
                                    open_lots[symbol].pop(0)
                                
                                remaining_qty -= matched_qty
                        else:
                            # #region agent log - Hypothesis E: No matching buy for sell
                            try:
                                with open(r'c:\Users\mason\OneDrive\Desktop\Cursor\website\.cursor\debug.log', 'a') as f:
                                    import json
                                    f.write(json.dumps({'location': 'app.py:4014', 'message': 'sell without matching buy', 'data': {'project': project, 'symbol': symbol, 'qty': qty, 'open_lots_has_symbol': symbol in open_lots, 'open_lots_count': len(open_lots.get(symbol, []))}, 'timestamp': int(datetime.now(timezone.utc).timestamp() * 1000), 'sessionId': 'debug-session', 'runId': 'run1', 'hypothesisId': 'E'}) + '\n')
                            except: pass
                            # #endregion
                
                # #region agent log - Hypothesis D: Final buy/sell counts and matching results
                try:
                    with open(r'c:\Users\mason\OneDrive\Desktop\Cursor\website\.cursor\debug.log', 'a') as f:
                        import json
                        f.write(json.dumps({'location': 'app.py:4036', 'message': 'buy/sell matching summary', 'data': {'project': project, 'buy_count': buy_count, 'sell_count': sell_count, 'matched_segments_count': len(matched_segments), 'open_lots_symbols': list(open_lots.keys()), 'open_lots_total_qty': {k: sum(lot['qty'] for lot in v) for k, v in open_lots.items()}}, 'timestamp': int(datetime.now(timezone.utc).timestamp() * 1000), 'sessionId': 'debug-session', 'runId': 'run1', 'hypothesisId': 'D'}) + '\n')
                except: pass
                # #endregion
        
        # #region agent log - Final matched segments check
        try:
            with open(r'c:\Users\mason\OneDrive\Desktop\Cursor\website\.cursor\debug.log', 'a') as f:
                import json
                f.write(json.dumps({'location': 'app.py:4037', 'message': 'final matched segments', 'data': {'project': project, 'matched_segments_count': len(matched_segments), 'matched_segments': matched_segments[:3] if len(matched_segments) > 0 else []}, 'timestamp': int(datetime.now(timezone.utc).timestamp() * 1000), 'sessionId': 'debug-session', 'runId': 'run1', 'hypothesisId': 'D'}) + '\n')
        except: pass
        # #endregion
        
        # #region agent log - Final summary before aggregation
        try:
            with open(r'c:\Users\mason\OneDrive\Desktop\Cursor\website\.cursor\debug.log', 'a') as f:
                import json
                summary = {
                    'project': project,
                    'response_exists': response_fills_7d is not None,
                    'response_status': response_fills_7d.status_code if (response_fills_7d and hasattr(response_fills_7d, 'status_code')) else None,
                    'matched_segments_count': len(matched_segments),
                    'result_wins': result.get('wins'),
                    'result_losses': result.get('losses')
                }
                f.write(json.dumps({'location': 'app.py:4079', 'message': 'final summary before wins/losses', 'data': summary, 'timestamp': int(datetime.now(timezone.utc).timestamp() * 1000), 'sessionId': 'debug-session', 'runId': 'run1', 'hypothesisId': 'ALL'}) + '\n')
        except Exception as e:
            # Write error to log too
            try:
                with open(r'c:\Users\mason\OneDrive\Desktop\Cursor\website\.cursor\debug.log', 'a') as f:
                    import json
                    f.write(json.dumps({'location': 'app.py:4079', 'message': 'error writing final summary', 'data': {'project': project, 'error': str(e)}, 'timestamp': int(datetime.now(timezone.utc).timestamp() * 1000), 'sessionId': 'debug-session', 'runId': 'run1', 'hypothesisId': 'ALL'}) + '\n')
            except: pass
        # #endregion
        
        # Aggregate matched segments - always set wins/losses (even if 0)
        # For crypto, use trades matching (same as calculate_stats) instead of fills matching
        # because fills can split orders into multiple segments, causing double-counting
        wins = 0
        losses = 0
        avg_return_dollar = None
        
        if project == 2:  # Crypto - use trades matching (same as calculate_stats) for accuracy
            # Use trades-based matching instead of fills to match entire orders, not partial fills
            try:
                trades, _ = get_alpaca_orders_2(limit=1000)
                if trades:
                    # Use the same matching logic as calculate_stats for consistency
                    matched_trades = []
                    orders_by_symbol = {}
                    
                    # Group orders by symbol
                    for trade in trades:
                        symbol = trade.get('symbol')
                        if symbol not in orders_by_symbol:
                            orders_by_symbol[symbol] = []
                        orders_by_symbol[symbol].append(trade)
                    
                    # Match buys with sells for each symbol (same as calculate_stats)
                    for symbol, symbol_trades in orders_by_symbol.items():
                        buys = [t for t in symbol_trades if t.get('side', '').lower() == 'buy']
                        sells = [t for t in symbol_trades if t.get('side', '').lower() == 'sell']
                        
                        # Sort by time
                        def get_trade_time(t):
                            time_str = t.get('entry_time', '') or t.get('exit_time', '')
                            if not time_str:
                                return datetime.min
                            try:
                                if 'T' in time_str:
                                    time_str_clean = time_str.replace('Z', '+00:00')
                                    try:
                                        return datetime.fromisoformat(time_str_clean)
                                    except:
                                        return datetime.fromisoformat(time_str_clean.replace('+00:00', ''))
                                return datetime.fromisoformat(time_str)
                            except:
                                return datetime.min
                        
                        buys.sort(key=get_trade_time)
                        sells.sort(key=get_trade_time)
                        
                        # Match sells with buys (FIFO) - same as calculate_stats
                        buy_stack = []
                        for sell in sells:
                            if buys:
                                buy = buys.pop(0)
                                buy_stack.append(buy)
                            
                            if buy_stack:
                                buy = buy_stack.pop(0)
                                entry_price = buy.get('entry_price', 0)
                                exit_price = sell.get('entry_price', 0)
                                qty = min(buy.get('qty', 0), sell.get('qty', 0))
                                pnl = (exit_price - entry_price) * qty
                                
                                # Calculate return % for this trade
                                cost_basis = qty * entry_price if entry_price > 0 and qty > 0 else 0
                                return_pct = (pnl / cost_basis * 100) if cost_basis > 0 else 0
                                
                                matched_trades.append({
                                    'pnl': pnl,
                                    'return_pct': return_pct,
                                    'status': 'closed'
                                })
                    
                    # Count wins/losses from matched closed trades (exclude break-even)
                    closed_trades = [t for t in matched_trades if t.get('status') == 'closed']
                    wins = len([t for t in closed_trades if (t.get('return_pct', 0) or 0) > 0])
                    losses = len([t for t in closed_trades if (t.get('return_pct', 0) or 0) < 0])
                    closed_trades_count = wins + losses
                    
                    # Calculate avg return as Total P&L / Total Trades
                    # Use total P&L (current_equity - baseline_equity) and total trades count
                    try:
                        # Get total trades count from max_trade_counts (same as calculate_stats)
                        total_trades_count = _max_trade_counts.get(project, 0)
                        
                        # Get total P&L = current_equity - baseline_equity (same as calculate_stats)
                        if project == 2:
                            live_equity_data = get_live_portfolio_equity_2()
                            current_equity = live_equity_data['live_equity'] if live_equity_data else 10000.0
                        else:
                            live_equity_data = get_live_portfolio_equity()
                            current_equity = live_equity_data['live_equity'] if live_equity_data else 10000.0
                        
                        baseline = get_baseline(project)
                        baseline_equity = get_baseline_equity_from_api(project)
                        if baseline_equity is None:
                            baseline_equity = baseline['baselineEquity']
                        
                        total_pnl = current_equity - baseline_equity if total_trades_count > 0 else 0
                        avg_return_dollar = total_pnl / total_trades_count if total_trades_count > 0 else None
                    except Exception as e:
                        print(f"ERROR calculating avg return for project {project}: {e}")
                        avg_return_dollar = None
                        total_pnl = 0
                        total_trades_count = 0
                    
                    result['wins'] = wins
                    result['losses'] = losses
                    result['avgReturnPct'] = round(avg_return_dollar, 2) if avg_return_dollar is not None else None
                    if total_trades_count > 0:
                        print(f"DEBUG [wins/losses] project={project} (crypto): Using trades matching - wins={wins}, losses={losses}, avgReturn=${avg_return_dollar:.2f} = Total P&L ${total_pnl:.2f} / Total Trades {total_trades_count}")
                    else:
                        print(f"DEBUG [wins/losses] project={project} (crypto): Using trades matching - wins={wins}, losses={losses}, avgReturn=None (no closed trades)")
                else:
                    # No trades available - set to 0/0
                    result['wins'] = 0
                    result['losses'] = 0
                    print(f"DEBUG [wins/losses] project={project}: No trades available, setting wins=0, losses=0")
            except Exception as e:
                print(f"DEBUG [wins/losses] project={project}: Error in trades matching: {e}, setting wins=0, losses=0")
                result['wins'] = 0
                result['losses'] = 0
        elif matched_segments:
            # Stocks/Options - use fills matching (they work correctly with fills)
            wins = sum(1 for seg in matched_segments if seg['return_pct'] > 0)
            losses = sum(1 for seg in matched_segments if seg['return_pct'] < 0)
            closed_trades_count = wins + losses
            
            # Calculate avg return as Total P&L / Total Trades
            # Use total P&L (current_equity - baseline_equity) and total trades count
            try:
                # Get total trades count from max_trade_counts (same as calculate_stats)
                total_trades_count = _max_trade_counts.get(project, 0)
                
                # Get total P&L = current_equity - baseline_equity (same as calculate_stats)
                if project == 1:
                    live_equity_data = get_live_portfolio_equity()
                    current_equity = live_equity_data['live_equity'] if live_equity_data else 10000.0
                else:
                    live_equity_data = get_live_portfolio_equity_2()
                    current_equity = live_equity_data['live_equity'] if live_equity_data else 10000.0
                
                baseline = get_baseline(project)
                baseline_equity = get_baseline_equity_from_api(project)
                if baseline_equity is None:
                    baseline_equity = baseline['baselineEquity']
                
                total_pnl = current_equity - baseline_equity if total_trades_count > 0 else 0
                avg_return_dollar = total_pnl / total_trades_count if total_trades_count > 0 else None
            except Exception as e:
                print(f"ERROR calculating avg return for project {project}: {e}")
                avg_return_dollar = None
                total_pnl = 0
                total_trades_count = 0
            
            result['wins'] = wins
            result['losses'] = losses
            result['avgReturnPct'] = round(avg_return_dollar, 2) if avg_return_dollar is not None else None
            if total_trades_count > 0:
                print(f"DEBUG [wins/losses] project={project}: wins={wins}, losses={losses}, avgReturn=${avg_return_dollar:.2f} = Total P&L ${total_pnl:.2f} / Total Trades {total_trades_count}")
            else:
                print(f"DEBUG [wins/losses] project={project}: wins={wins}, losses={losses}, avgReturn=None (no closed trades)")
        else:
            # No matched segments - for stocks/options, set to 0/0
            if project != 2:  # Stocks/Options - no matched segments
                result['wins'] = 0
                result['losses'] = 0
                result['avgReturnPct'] = None
                print(f"DEBUG [wins/losses] project={project}: No matched segments (no closed trades), setting wins=0, losses=0")
        
        # Final safety check - ensure wins/losses are ALWAYS set (never None)
        if result.get('wins') is None:
            result['wins'] = 0
        if result.get('losses') is None:
            result['losses'] = 0
        
    except Exception as e:
        print(f"Error computing micro-metrics for project {project}: {e}")
        import traceback
        traceback.print_exc()
        # Ensure wins/losses are always set even on error (set to 0/0 as fallback)
        if result.get('wins') is None:
            result['wins'] = 0
        if result.get('losses') is None:
            result['losses'] = 0
    
    # Final safety check before returning - ensure wins/losses are NEVER None
    # This prevents the flickering issue where values might briefly appear then disappear
    if result.get('wins') is None:
        result['wins'] = 0
    if result.get('losses') is None:
        result['losses'] = 0
    
    # Ensure numeric values (not strings or other types)
    try:
        result['wins'] = int(result.get('wins', 0))
        result['losses'] = int(result.get('losses', 0))
    except (ValueError, TypeError):
        result['wins'] = 0
        result['losses'] = 0
    
    return result


@app.route('/api/alpaca/metrics', methods=['GET'])
def get_alpaca_metrics():
    """Get micro-metrics for a trading algorithm."""
    project = request.args.get('project', '1', type=int)
    
    if project not in [1, 2]:
        return jsonify({'error': 'Invalid project. Must be 1 or 2'}), 400
    
    try:
        metrics = compute_micro_metrics(project)
        response = jsonify(metrics)
        # Prevent caching - always fetch fresh data
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response
    except Exception as e:
        print(f"Error fetching metrics: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=True, host='0.0.0.0', port=port)

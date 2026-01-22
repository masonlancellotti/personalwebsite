"""
FastAPI backend for the trading dashboard.

Provides endpoints for portfolio data, performance metrics, and transactions.
Uses Alpaca account data for live/paper trading dashboard.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
from enum import Enum

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from config import get_config, APIConfig
from alpaca_clients import get_client_manager
from utils import get_logger, utc_now

logger = get_logger("api_server")

# Initialize FastAPI app
app = FastAPI(
    title="Trading Bot API",
    description="Backend API for the trading dashboard",
    version="1.0.0"
)


# ============================================================
# Response Models
# ============================================================

class DashboardSummary(BaseModel):
    """Dashboard summary response model."""
    portfolioValue: float
    dayReturnPct: float
    totalPnL: float
    pnlWeek: float
    pnlMonth: float
    winRate: Optional[float]
    avgReturn: Optional[float]
    closedWL: Dict[str, int]
    totalTrades: int
    tradesToday: int
    lastTradeAt: Optional[str]
    lastTradeAgoSeconds: Optional[int]
    investedPct: float


class EquityPoint(BaseModel):
    """Single equity data point."""
    t: str
    equity: float


class PerformanceResponse(BaseModel):
    """Performance chart response model."""
    range: str
    points: List[EquityPoint]


class Transaction(BaseModel):
    """Transaction record model."""
    symbol: str
    action: str
    qty: int
    price: float
    t: str


class TransactionsResponse(BaseModel):
    """Transactions list response model."""
    transactions: List[Transaction]


class BotStatus(BaseModel):
    """Bot status response model."""
    mode: str
    universeSize: int
    lastScanAt: Optional[str]
    lastDecisionAt: Optional[str]
    openPositions: int


# ============================================================
# State tracking
# ============================================================

class BotState:
    """Track bot state for status endpoint."""
    last_scan_at: Optional[datetime] = None
    last_decision_at: Optional[datetime] = None


bot_state = BotState()


# ============================================================
# Helper Functions
# ============================================================

def get_portfolio_history(
    period: str = "1D",
    timeframe: str = "1D"
) -> List[Dict[str, Any]]:
    """
    Get portfolio history from Alpaca.
    
    Args:
        period: History period (e.g., "1D", "1W", "1M", "3M", "1A", "all").
        timeframe: Data resolution ("1D" for daily).
    
    Returns:
        List of equity data points.
    """
    try:
        client_manager = get_client_manager()
        client = client_manager.trading_client
        
        history = client.get_portfolio_history(
            period=period,
            timeframe=timeframe
        )
        
        points = []
        if history and history.timestamp:
            for i, ts in enumerate(history.timestamp):
                dt = datetime.fromtimestamp(ts, tz=timezone.utc)
                equity = float(history.equity[i]) if history.equity else 0
                points.append({
                    "timestamp": dt,
                    "equity": equity
                })
        
        return points
        
    except Exception as e:
        logger.error(f"Failed to get portfolio history: {e}")
        return []


def get_account_activities(
    activity_types: Optional[List[str]] = None,
    after: Optional[datetime] = None,
    limit: int = 100
) -> List[Dict[str, Any]]:
    """
    Get account activities (fills) from Alpaca.
    
    Args:
        activity_types: Filter by activity type (e.g., ["FILL"]).
        after: Only activities after this time.
        limit: Maximum activities to return.
    
    Returns:
        List of activity records.
    """
    try:
        client_manager = get_client_manager()
        client = client_manager.trading_client
        
        # Get account activities
        activities = client.get_account_activities(
            activity_types=activity_types or ["FILL"],
            after=after,
        )
        
        records = []
        for activity in activities[:limit]:
            records.append({
                "id": activity.id,
                "activity_type": activity.activity_type,
                "symbol": getattr(activity, 'symbol', None),
                "side": getattr(activity, 'side', None),
                "qty": float(getattr(activity, 'qty', 0) or 0),
                "price": float(getattr(activity, 'price', 0) or 0),
                "transaction_time": getattr(activity, 'transaction_time', None)
            })
        
        return records
        
    except Exception as e:
        logger.error(f"Failed to get account activities: {e}")
        return []


def period_to_alpaca_format(range_str: str) -> str:
    """Convert frontend range to Alpaca period format."""
    mapping = {
        "day": "1D",
        "week": "1W",
        "month": "1M",
        "3m": "3M",
        "year": "1A",
        "ytd": "1A",  # Approximation
        "all": "all"
    }
    return mapping.get(range_str.lower(), "1M")


# ============================================================
# API Endpoints
# ============================================================

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "timestamp": utc_now().isoformat()}


@app.get("/api/dashboard/summary", response_model=DashboardSummary)
async def get_dashboard_summary():
    """
    Get dashboard summary metrics.
    
    Returns portfolio value, P&L metrics, trade statistics,
    and invested percentage based on live/paper Alpaca account.
    """
    try:
        client_manager = get_client_manager()
        
        # Get account info
        account = client_manager.get_account()
        equity = float(account.equity)
        last_equity = float(account.last_equity)
        
        # Day return
        day_return = equity - last_equity
        day_return_pct = (day_return / last_equity * 100) if last_equity > 0 else 0
        
        # Get portfolio history for P&L calculations
        # Week P&L
        week_history = get_portfolio_history(period="1W", timeframe="1D")
        pnl_week = 0.0
        if week_history and len(week_history) > 1:
            pnl_week = equity - week_history[0]["equity"]
        
        # Month P&L
        month_history = get_portfolio_history(period="1M", timeframe="1D")
        pnl_month = 0.0
        if month_history and len(month_history) > 1:
            pnl_month = equity - month_history[0]["equity"]
        
        # Total P&L (using all-time or 3M as proxy)
        all_history = get_portfolio_history(period="3M", timeframe="1D")
        total_pnl = 0.0
        if all_history and len(all_history) > 1:
            total_pnl = equity - all_history[0]["equity"]
        
        # Get positions for invested percentage
        positions = client_manager.get_positions()
        total_position_value = sum(
            abs(float(p.market_value))
            for p in positions
        )
        invested_pct = total_position_value / equity if equity > 0 else 0
        
        # Get fills for trade statistics
        # Last 90 days of fills
        activities = get_account_activities(
            activity_types=["FILL"],
            after=utc_now() - timedelta(days=90),
            limit=500
        )
        
        total_trades = len(activities)
        
        # Trades today
        today_start = utc_now().replace(hour=0, minute=0, second=0, microsecond=0)
        trades_today = sum(
            1 for a in activities
            if a.get("transaction_time") and
            datetime.fromisoformat(str(a["transaction_time"]).replace("Z", "+00:00")) >= today_start
        )
        
        # Last trade info
        last_trade_at = None
        last_trade_ago_seconds = None
        if activities:
            last_activity = activities[0]
            if last_activity.get("transaction_time"):
                last_trade_time = datetime.fromisoformat(
                    str(last_activity["transaction_time"]).replace("Z", "+00:00")
                )
                last_trade_at = last_trade_time.isoformat()
                last_trade_ago_seconds = int((utc_now() - last_trade_time).total_seconds())
        
        # Win/loss calculation (simplified - would need closed position tracking for accuracy)
        # For now, return null as we can't easily compute this from fills alone
        win_rate = None
        avg_return = None
        closed_wl = {"wins": 0, "losses": 0}
        
        return DashboardSummary(
            portfolioValue=round(equity, 2),
            dayReturnPct=round(day_return_pct, 2),
            totalPnL=round(total_pnl, 2),
            pnlWeek=round(pnl_week, 2),
            pnlMonth=round(pnl_month, 2),
            winRate=win_rate,
            avgReturn=avg_return,
            closedWL=closed_wl,
            totalTrades=total_trades,
            tradesToday=trades_today,
            lastTradeAt=last_trade_at,
            lastTradeAgoSeconds=last_trade_ago_seconds,
            investedPct=round(invested_pct, 4)
        )
        
    except Exception as e:
        logger.error(f"Error in dashboard summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/dashboard/performance", response_model=PerformanceResponse)
async def get_performance(
    range: str = Query("week", description="Time range: day, week, month, 3m, year, ytd, all")
):
    """
    Get performance data for chart visualization.
    
    Returns equity time series for the specified range.
    """
    try:
        period = period_to_alpaca_format(range)
        history = get_portfolio_history(period=period, timeframe="1D")
        
        points = [
            EquityPoint(
                t=point["timestamp"].isoformat(),
                equity=round(point["equity"], 2)
            )
            for point in history
        ]
        
        return PerformanceResponse(range=range, points=points)
        
    except Exception as e:
        logger.error(f"Error in performance data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/dashboard/transactions", response_model=TransactionsResponse)
async def get_transactions(
    limit: int = Query(25, description="Maximum transactions to return")
):
    """
    Get recent transactions (fills).
    
    Returns most recent trades with symbol, action, quantity, price, and timestamp.
    """
    try:
        activities = get_account_activities(
            activity_types=["FILL"],
            limit=limit
        )
        
        transactions = []
        for activity in activities:
            if activity.get("symbol") and activity.get("side"):
                action = "BUY" if activity["side"].lower() == "buy" else "SELL"
                t_time = activity.get("transaction_time")
                if t_time:
                    t_str = datetime.fromisoformat(
                        str(t_time).replace("Z", "+00:00")
                    ).isoformat()
                else:
                    t_str = utc_now().isoformat()
                
                transactions.append(Transaction(
                    symbol=activity["symbol"],
                    action=action,
                    qty=int(activity.get("qty", 0)),
                    price=round(float(activity.get("price", 0)), 2),
                    t=t_str
                ))
        
        return TransactionsResponse(transactions=transactions)
        
    except Exception as e:
        logger.error(f"Error in transactions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/bot/status", response_model=BotStatus)
async def get_bot_status():
    """
    Get bot operational status.
    
    Returns mode, universe size, last scan time, and open positions count.
    """
    try:
        client_manager = get_client_manager()
        
        # Determine mode
        mode = "paper" if client_manager.is_paper else "live"
        
        # Get universe size
        from universe import get_universe
        universe_size = len(get_universe())
        
        # Get open positions count
        positions = client_manager.get_positions()
        open_positions = len(positions)
        
        # Format timestamps
        last_scan = None
        if bot_state.last_scan_at:
            last_scan = bot_state.last_scan_at.isoformat()
        
        last_decision = None
        if bot_state.last_decision_at:
            last_decision = bot_state.last_decision_at.isoformat()
        
        return BotStatus(
            mode=mode,
            universeSize=universe_size,
            lastScanAt=last_scan,
            lastDecisionAt=last_decision,
            openPositions=open_positions
        )
        
    except Exception as e:
        logger.error(f"Error in bot status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/positions")
async def get_positions():
    """
    Get current open positions.
    
    Returns list of positions with details.
    """
    try:
        client_manager = get_client_manager()
        positions = client_manager.get_positions()
        
        result = []
        for p in positions:
            result.append({
                "symbol": p.symbol,
                "qty": int(p.qty),
                "side": "long" if int(p.qty) > 0 else "short",
                "avgEntryPrice": float(p.avg_entry_price),
                "marketValue": float(p.market_value),
                "currentPrice": float(p.current_price),
                "unrealizedPL": float(p.unrealized_pl),
                "unrealizedPLPct": float(p.unrealized_plpc) * 100,
                "changeToday": float(p.change_today) * 100 if p.change_today else 0
            })
        
        return {"positions": result}
        
    except Exception as e:
        logger.error(f"Error getting positions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/account")
async def get_account():
    """
    Get account details.
    
    Returns account equity, cash, buying power, etc.
    """
    try:
        client_manager = get_client_manager()
        account = client_manager.get_account()
        
        return {
            "equity": float(account.equity),
            "cash": float(account.cash),
            "buyingPower": float(account.buying_power),
            "portfolioValue": float(account.portfolio_value),
            "daytradeCount": int(account.daytrade_count),
            "patternDayTrader": account.pattern_day_trader,
            "tradingBlocked": account.trading_blocked,
            "accountBlocked": account.account_blocked
        }
        
    except Exception as e:
        logger.error(f"Error getting account: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def configure_cors(app: FastAPI, config: Optional[APIConfig] = None) -> None:
    """
    Configure CORS middleware.
    
    Args:
        app: FastAPI application.
        config: API configuration.
    """
    cfg = config or get_config().api
    
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


def create_app() -> FastAPI:
    """
    Create and configure the FastAPI application.
    
    Returns:
        FastAPI: Configured application.
    """
    configure_cors(app)
    return app


def run_server(host: Optional[str] = None, port: Optional[int] = None) -> None:
    """
    Run the API server.
    
    Args:
        host: Server host.
        port: Server port.
    """
    import uvicorn
    
    config = get_config().api
    host = host or config.host
    port = port or config.port
    
    configure_cors(app)
    
    logger.info(f"Starting API server on {host}:{port}")
    
    # Use string path on Windows to avoid signal handling issues
    uvicorn.run(
        "api_server:app",
        host=host,
        port=port,
        reload=config.reload,
        log_level="info"
    )


# Update bot state (called from live runner)
def update_bot_state(scan_time: Optional[datetime] = None, decision_time: Optional[datetime] = None):
    """Update bot state for status endpoint."""
    if scan_time:
        bot_state.last_scan_at = scan_time
    if decision_time:
        bot_state.last_decision_at = decision_time


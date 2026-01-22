# HMM-Based Trading Bot with Sentiment Analysis

A professional-grade Python trading bot featuring Hidden Markov Model (HMM) market regime detection, technical indicators, FinBERT sentiment analysis, and a FastAPI backend for dashboard integration.

## 🎯 Features

- **HMM Market Regime Detection**: 3-state Gaussian HMM classifying Bull/Bear/Sideways regimes using SPY as market proxy
- **Technical Signals**: RSI (Wilder smoothing) + MACD crossovers for entry triggers
- **FinBERT Sentiment**: NLP-based sentiment confirmation using Alpaca News with RSS fallback
- **Risk Management**: ATR-based position sizing, hard stops, trailing take-profit
- **Realistic Backtesting**: Slippage/commission modeling, no lookahead bias
- **FastAPI Dashboard**: Real-time endpoints for your existing frontend
- **Long & Short**: Full support for shorting in Bear regimes

## 📁 Project Structure

```
/app
├── main.py              # CLI entrypoint
├── config.py            # Configuration via environment variables
├── universe.py          # 200 stock universe
├── alpaca_clients.py    # Alpaca SDK client management
├── data_provider.py     # Historical bars with caching
├── news_provider.py     # Alpaca News + RSS fallback
├── indicators.py        # RSI, MACD, ATR (manual implementation)
├── regime_hmm.py        # HMM market regime detection
├── sentiment.py         # FinBERT sentiment scoring
├── strategy.py          # Entry/exit signal logic
├── portfolio.py         # Position management & risk
├── backtester.py        # Simulation engine
├── reporting.py         # Metrics, CSVs, plots
├── api_server.py        # FastAPI backend
├── utils.py             # Helper functions
├── requirements.txt     # Dependencies
└── README.md            # This file
```

## ⚙️ Environment Variables

Create a `.env` file in the project root:

```bash
# Required - Alpaca API Keys
ALPACA_API_KEY=your_api_key
ALPACA_SECRET_KEY=your_secret_key
ALPACA_PAPER=true              # true for paper trading, false for live
ALPACA_DATA_FEED=iex           # iex (free) or sip (paid)

# Optional - API URL overrides
# BASE_URL_TRADING=https://paper-api.alpaca.markets
# BASE_URL_DATA=https://data.alpaca.markets

# HMM Configuration
HMM_LOOKBACK_YEARS=5           # Years of SPY data for training
HMM_REFIT_DAYS=21              # Refit interval (trading days)
BULL_PROB_THRESHOLD=0.60       # Minimum bull probability for longs
BEAR_PROB_THRESHOLD=0.60       # Minimum bear probability for shorts

# Technical Indicators
RSI_OVERSOLD=35                # RSI threshold for long entries
RSI_OVERBOUGHT=65              # RSI threshold for short entries

# Sentiment
SENTIMENT_POS_THRESHOLD=0.60   # Positive sentiment threshold
SENTIMENT_NEG_THRESHOLD=0.60   # Negative sentiment threshold
NEWS_LOOKBACK_DAYS=3           # Days of news for sentiment

# Risk Management
RISK_PER_TRADE_PCT=1.0         # Risk per trade (% of equity)
ATR_MULTIPLIER=1.5             # Stop distance = ATR * multiplier
MAX_POSITION_PCT=10.0          # Max position size (% of equity)
MAX_GROSS_EXPOSURE_PCT=100.0   # Max total exposure
HARD_STOP_PCT=2.0              # Hard stop loss percentage
TRAILING_ACTIVATION_PCT=5.0    # Profit level to activate trailing
TRAILING_STOP_PCT=2.0          # Trailing stop distance

# Backtest
INITIAL_CAPITAL=100000.0       # Starting capital
FEE_RATE=0.001                 # Fee rate per side (0.1%)
MIN_SYMBOL_BARS=400            # Min bars for indicator warmup

# API Server
API_HOST=0.0.0.0
API_PORT=8000
CORS_ORIGINS=http://localhost:3000,http://localhost:5173

# Live Trading
LIVE_SCAN_INTERVAL=60          # Minutes between scans
```

## 🚀 Quick Start

### 1. Install Dependencies

```bash
cd app
pip install -r requirements.txt
```

### 2. Set Environment Variables

```bash
# Windows PowerShell
$env:ALPACA_API_KEY="your_key"
$env:ALPACA_SECRET_KEY="your_secret"
$env:ALPACA_PAPER="true"

# Or use a .env file
```

### 3. Run Backtest

```bash
# Full universe, last year
python main.py backtest

# Custom date range
python main.py backtest --start 2024-01-01 --end 2024-12-31

# Specific symbols
python main.py backtest --symbols AAPL,MSFT,GOOGL --capital 50000

# Verbose output
python main.py -v backtest
```

### 4. Start API Server

```bash
python main.py api --port 8000
```

Then access endpoints:
- Health: `GET http://localhost:8000/health`
- Summary: `GET http://localhost:8000/api/dashboard/summary`
- Performance: `GET http://localhost:8000/api/dashboard/performance?range=week`
- Transactions: `GET http://localhost:8000/api/dashboard/transactions?limit=25`
- Bot Status: `GET http://localhost:8000/api/bot/status`

### 5. Run Live Bot

```bash
# Single scan (dry run)
python main.py live --once --dry-run

# Continuous operation
python main.py live
```

## 📊 API Endpoints

### `GET /api/dashboard/summary`

Returns dashboard metrics from your Alpaca account:

```json
{
  "portfolioValue": 10065.15,
  "dayReturnPct": -0.64,
  "totalPnL": 59.21,
  "pnlWeek": -96.05,
  "pnlMonth": 76.26,
  "winRate": null,
  "avgReturn": null,
  "closedWL": {"wins": 0, "losses": 0},
  "totalTrades": 19,
  "tradesToday": 0,
  "lastTradeAt": "2026-01-07T09:31:00Z",
  "lastTradeAgoSeconds": 1220000,
  "investedPct": 1.0
}
```

### `GET /api/dashboard/performance?range=week`

Returns equity time series:

```json
{
  "range": "week",
  "points": [
    {"t": "2026-01-15T00:00:00Z", "equity": 10230.12},
    {"t": "2026-01-16T00:00:00Z", "equity": 10110.44}
  ]
}
```

### `GET /api/dashboard/transactions?limit=25`

Returns recent fills:

```json
{
  "transactions": [
    {"symbol": "INTC", "action": "BUY", "qty": 29, "price": 40.69, "t": "2026-01-07T09:31:00Z"}
  ]
}
```

### `GET /api/bot/status`

Returns bot operational status:

```json
{
  "mode": "paper",
  "universeSize": 200,
  "lastScanAt": "2026-01-22T14:00:00Z",
  "lastDecisionAt": "2026-01-22T14:00:05Z",
  "openPositions": 5
}
```

## 📈 Trading Strategy

### Entry Rules

**LONG Entry** (Bull regime only):
1. HMM detects Bull regime with `bull_prob >= 0.60`
2. RSI(14) < 35 (oversold)
3. MACD bullish crossover (MACD crosses above signal)
4. Positive sentiment score >= 0.60 from recent news

**SHORT Entry** (Bear regime only):
1. HMM detects Bear regime with `bear_prob >= 0.60`
2. RSI(14) > 65 (overbought)
3. MACD bearish crossover (MACD crosses below signal)
4. Negative sentiment score >= 0.60 from recent news

**NO new entries** in Sideways regime.

### Exit Rules

1. **Hard Stop**: 2% adverse move from entry
2. **Trailing Take-Profit**: Activates at +5% favorable move, trails at 2%
3. **Regime Flip** (optional): Exit when regime changes

### Position Sizing

- Risk per trade: 1% of equity
- Stop distance: ATR(14) × 1.5
- Position size: `(equity × risk%) / stop_distance`
- Max position: 10% of equity
- Max total exposure: 100% of equity

## 🔬 HMM Regime Detection

The Hidden Markov Model uses 3 states trained on SPY data:

**Features:**
- Log returns: `log(close_t / close_{t-1})`
- 20-day rolling volatility
- 10-day rolling mean return

**State Labeling:**
- **Bull**: Highest mean return state
- **Bear**: Lowest mean return state
- **Sideways**: Middle state

**Bootstrap Training:**
- On first run, automatically downloads 5 years of SPY data
- Trains HMM immediately for day-1 trading capability
- Refits every 21 trading days (configurable)

## 📰 Sentiment Analysis

Uses FinBERT (ProsusAI/finbert) for financial sentiment:

**News Sources:**
1. **Primary**: Alpaca News API
2. **Fallback**: Public RSS feeds (Yahoo Finance, MarketWatch, etc.)

**Scoring:**
- Aggregates sentiment from headlines + summaries
- Default aggregation: mean (configurable to max)
- Caches scores by text hash to avoid reprocessing

**Fail-Safe:**
- No news = No trade (strict sentiment confirmation)
- Logs clearly when Alpaca News unavailable

## 📁 Data Caching

All data is cached locally in `/app/data/`:

- `/data/bars/` - Historical OHLCV bars (parquet)
- `/data/news/` - News articles (JSON)
- `/data/sentiment_cache.parquet` - Scored sentiment
- `/data/hmm_model.pkl` - Trained HMM model

Reports are saved to `/app/reports/`:

- `summary_YYYYMMDD_HHMMSS.csv`
- `equity_curve_YYYYMMDD_HHMMSS.csv`
- `trades_YYYYMMDD_HHMMSS.csv`
- `equity_curve_YYYYMMDD_HHMMSS.png`

## ⚠️ Important Notes

1. **No Lookahead Bias**: Signals computed from t-1 data, fills at t open
2. **Shorting**: Requires margin account; bot validates shortability per asset
3. **Alpaca Data Feed**: `iex` is free but delayed; `sip` requires subscription
4. **Sentiment Model**: FinBERT downloads ~400MB on first use
5. **totalTrades** in API = count of fills over last 90 days

## 🧪 Development

```bash
# Run with debug logging
python main.py -v backtest

# Test API locally
curl http://localhost:8000/health
curl http://localhost:8000/api/dashboard/summary
```

## 📜 License

For educational and personal use. Not financial advice.

---

Built with 🐍 Python, 🦙 Alpaca, and 🤗 Transformers


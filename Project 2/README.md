# Alpaca Crypto Trading Bot

A production-quality, crypto-only automated trading and research repository using Alpaca's API. Built with safety-by-design principles, comprehensive risk controls, and a modular strategy architecture.

## Installation

1. **Set up virtual environment** (recommended):
   ```bash
   python -m venv venv
   .\venv\Scripts\Activate.ps1  # Windows
   pip install -r requirements.txt
   ```

2. **Set up Alpaca API credentials**:
   
   Get your API keys from:
   - Paper Trading: https://app.alpaca.markets/paper/dashboard/overview
   - Live Trading: https://app.alpaca.markets/dashboard/overview
   
   Create a `.env` file in the project root:
   ```
   ALPACA_API_KEY=your_api_key_here
   ALPACA_SECRET_KEY=your_secret_key_here
   ALPACA_PAPER=true  # Set to false for live trading
   ALLOW_LIVE=false  # Must be explicitly true for live trading
   ```

## Quick Start

1. **Build universe**:
   ```bash
   python main.py build-universe
   ```

2. **Download historical data**:
   ```bash
   python main.py download-data --timeframe 1Min --lookback-days 30
   ```

3. **List available strategies**:
   ```bash
   python main.py list-strategies
   ```

4. **Run backtest**:
   ```bash
   python main.py backtest --strategy market_maker_basic --universe ALL --start 2024-01-01 --end 2024-01-31
   ```

5. **Paper trading**:
   ```bash
   python main.py paper --strategy market_maker_basic --universe ALL
   ```

## Configuration

Key configuration options in `.env`:

- `ALPACA_PAPER=true` - Use paper trading (default)
- `ALLOW_LIVE=false` - Must be explicitly `true` for live trading
- `MAX_POSITION_NOTIONAL_PER_SYMBOL=500` - Max position per symbol (USD)
- `TOTAL_MAX_NOTIONAL=5000` - Max total exposure (USD)
- `MAX_DAILY_LOSS=100` - Daily loss limit before halt (USD)
- `KILL_SWITCH_FILE=./KILL` - Path to kill switch file

## CLI Commands

```bash
# Universe Management
python main.py list-universe
python main.py build-universe
python main.py validate-symbols --symbols BTC/USD,ETH/USD

# Data Management
python main.py download-data --timeframe 1Min --lookback-days 30

# Strategy Management
python main.py list-strategies
python main.py explain-strategy --name market_maker_basic

# Backtesting
python main.py backtest --strategy vol_target_allocator --universe ALL --start 2024-01-01 --end 2024-01-31

# Trading
python main.py paper --strategy market_maker_basic --universe ALL
python main.py status
python main.py cancel-all
```

## Available Strategies

- `market_maker_basic` - Basic market maker with inventory-aware skew
- `vol_target_allocator` - Volatility target allocator (risk parity style)
- `rebalancer_target_weights` - Simple rebalancer with target weights
- `twap_vwap_executor` - TWAP/VWAP execution algorithm
- `liquidity_guardrails` - Always-on liquidity filter
- `cross_rate_tri_arb` - Triangular arbitrage detection
- `grid_trader` - Grid trading strategy
- `breakout_retest` - Breakout and retest strategy
- `mean_reversion_bb` - Mean reversion with Bollinger Bands

## Safety Features

- **Kill Switch**: Create `./KILL` file to halt trading immediately
- **Daily Loss Limit**: Automatic halt if daily loss exceeds limit
- **Position Caps**: Per-symbol and total exposure limits
- **Paper by Default**: Requires explicit flag for live trading
- **No Shorting/Leverage**: Long-only spot trading only

## Important Notes

- Always test with paper trading before using live trading
- Trading cryptocurrencies involves substantial risk
- Use appropriate risk management and only trade with capital you can afford to lose

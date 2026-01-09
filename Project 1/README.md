# Alpaca Swing Trading Agent

An automated swing trading agent built for the Alpaca Trading API. Supports momentum and mean reversion strategies with comprehensive risk management.

## Installation

**Requires Python 3.12** (for pandas-ta/numba compatibility). The setup script will automatically use Python 3.12 if available.

1. **Set up virtual environment** (recommended):
   ```powershell
   .\setup_venv.ps1
   .\venv\Scripts\Activate.ps1
   ```
   
   The setup script will:
   - Find and use Python 3.12 (checks `py -3.12`, `python3.12`, then `python`)
   - Create a fresh virtual environment
   - Install all dependencies including pandas-ta
   
   Or manually with Python 3.12:
   ```bash
   py -3.12 -m venv venv  # Use Python 3.12 specifically
   .\venv\Scripts\Activate.ps1
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
   ```

3. **Configure trading parameters**:
   
   Edit `config.yaml` to set symbols, strategy type, and risk parameters.

## Usage

### Run once (single iteration):
```bash
python main.py --once
```

### Run continuously (default: 5 minute intervals):
```bash
python main.py
```

### Run with custom interval:
```bash
python main.py --interval 600  # 10 minutes
```

## Configuration

Edit `config.yaml`:

```yaml
trading:
  symbols: ["AAPL", "MSFT", "GOOGL"]
  strategy: "momentum"  # or "mean_reversion"
  timeframe: "1Day"

risk:
  max_position_size: 0.1  # 10% of portfolio per position
  stop_loss_percent: 0.02  # 2% stop loss
  max_daily_loss: 0.05  # 5% max daily loss

strategy_params:
  momentum:
    rsi_period: 14
    rsi_oversold: 30
    rsi_overbought: 70
  mean_reversion:
    rsi_period: 14
    bb_period: 20
    bb_std: 2
```

## Trading Strategies

- **Momentum Strategy**: Uses RSI, MACD, and moving average crossovers to identify trends
- **Mean Reversion Strategy**: Uses Bollinger Bands and RSI to identify when prices deviate from the mean

## Important Notes

- Always test with paper trading before using live trading
- Ensure the agent runs during market hours for best results
- Trading involves risk. Use appropriate risk management and only trade with capital you can afford to lose

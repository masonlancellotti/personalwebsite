# Trading Algorithms API Backend

Backend API server for serving trading algorithm data from Alpaca API to the website frontend.

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Create a `.env` file in the `backend/` directory with your Alpaca API credentials:
```env
# Project 1 (Stocks)
ALPACA_API_KEY=your_api_key_here
ALPACA_SECRET_KEY=your_secret_key_here
ALPACA_BASE_URL=https://paper-api.alpaca.markets

# Project 2 (Crypto) - Optional
ALPACA_API_KEY_2=your_api_key_2_here
ALPACA_SECRET_KEY_2=your_secret_key_2_here
ALPACA_BASE_URL_2=https://paper-api.alpaca.markets

PORT=5000
```

   - For **paper trading** (recommended for testing): Use `https://paper-api.alpaca.markets`
   - For **live trading**: Use `https://api.alpaca.markets`
   - Get your API keys from: https://app.alpaca.markets/paper/dashboard/overview
   - Project 2 is optional - only include it if you have a separate Alpaca account for crypto trading

3. Run the server:
```bash
python app.py
```

The API will be available at `http://localhost:5000`

## API Endpoints

- `GET /api/algorithms` - List all trading algorithms
- `GET /api/algorithms/{name}` - Get algorithm details
- `GET /api/algorithms/{name}/performance?timeframe={timeframe}` - Get performance data
- `GET /api/algorithms/{name}/trades?limit={limit}` - Get recent trades
- `GET /api/algorithms/{name}/stats` - Get statistics
- `GET /api/health` - Health check (shows Alpaca connection status)

## Environment Variables

### Project 1 (Stocks) - Required
- `ALPACA_API_KEY` - Your Alpaca API key for Project 1 (required)
- `ALPACA_SECRET_KEY` - Your Alpaca secret key for Project 1 (required)
- `ALPACA_BASE_URL` - Alpaca API base URL for Project 1 (default: paper trading)

### Project 2 (Crypto) - Optional
- `ALPACA_API_KEY_2` - Your Alpaca API key for Project 2 (optional)
- `ALPACA_SECRET_KEY_2` - Your Alpaca secret key for Project 2 (optional)
- `ALPACA_BASE_URL_2` - Alpaca API base URL for Project 2 (default: paper trading)

### General
- `PORT` - Server port (default: 5000)

## Data Source

The backend now fetches trade data directly from the Alpaca API:
- **Trades**: Fetched from filled orders
- **Performance**: Calculated from trade history
- **Statistics**: Computed from closed trades

Make sure your Alpaca account has trading history for data to appear.


# Quick Start Guide

Get your personal website running locally in minutes!

## Prerequisites

1. **Node.js and npm** - Install from [nodejs.org](https://nodejs.org/)
2. **Python 3.8+** - Should already be installed

## Setup

### 1. Install Frontend Dependencies

```bash
cd website/frontend
npm install
```

### 2. Install Backend Dependencies

```bash
cd website/backend
pip install -r requirements.txt
```

## Running Locally

### Start Backend API (Terminal 1)

```bash
cd website/backend
python app.py
```

Backend will run on `http://localhost:5000`

### Start Frontend (Terminal 2)

```bash
cd website/frontend
npm run dev
```

Frontend will run on `http://localhost:3000`

Visit `http://localhost:3000` in your browser!

## What You'll See

- **Homepage**: Simple landing page (customize later)
- **Trading Algorithms** (`/tradingalgos`): 
  - Shows your trading bot performance
  - Interactive charts with timeframe selector
  - Recent trades table
  - Performance statistics

## Notes

- The backend automatically reads trade data from `../trades/` directory
- If no trades exist yet, the frontend will show sample/demo data
- Charts update based on the timeframe selected (Day, Week, Month, etc.)

## Next Steps

1. Customize the homepage content
2. Add more trading algorithms as you build them
3. Deploy to AWS (see `DEPLOYMENT.md`)


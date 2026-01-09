# How to Monitor Your Trading Bot

## Quick Start - Verify It's Running Every 5 Minutes

### Method 1: Watch Log File (Recommended)
Open a **new PowerShell window** and run:
```powershell
Get-Content logs\trading_agent_*.log -Wait -Tail 20
```

This will show you:
- Every 5 minutes: "Waiting 300 seconds until next iteration..."
- Performance updates after each cycle
- All buy/sell signals
- Trade executions

### Method 2: Use the Monitor Script
In a **new PowerShell window**, run:
```powershell
.\monitor_bot.ps1
```

This shows colored output for:
- 🔵 **Cyan**: Trading signals (BUY/SELL/HOLD)
- 🟢 **Green**: Trade executions
- 🟡 **Yellow**: Performance metrics
- 🟣 **Magenta**: Cycle completion messages

### Method 3: Check Log File Manually
```powershell
# View last 50 lines
Get-Content logs\trading_agent_*.log -Tail 50

# Search for cycle messages (every 5 min)
Select-String -Path logs\trading_agent_*.log -Pattern "Waiting.*seconds"

# Count how many cycles completed today
Select-String -Path logs\trading_agent_*.log -Pattern "Waiting.*seconds" | Measure-Object

# See all signals generated
Select-String -Path logs\trading_agent_*.log -Pattern "Signal:"
```

### Method 4: Check Trade Journal
```powershell
# View today's trades
Get-Content trades\trades_*.json | ConvertFrom-Json | Format-Table
```

## What You Should See

### If Bot is Working Correctly:
✅ Every 5 minutes, you'll see:
```
2025-12-19 XX:XX:XX - trading_agent - INFO - Waiting 300 seconds until next iteration...
```

✅ After each cycle, you'll see:
```
2025-12-19 XX:XX:XX - trading_agent - INFO - Performance: Equity=$10000.00, Positions=0, Total Trades=0, Win Rate=0.0%, Total P&L=$0.00
```

✅ For each stock, you'll see signals:
```
2025-12-19 XX:XX:XX - trading_agent - INFO - Signal: HOLD AAPL - Price: $150.00
```

### When Bot Finds Opportunities:
🟢 **BUY Signal**:
```
2025-12-19 XX:XX:XX - trading_agent - INFO - Signal: BUY MSFT - Price: $380.00
2025-12-19 XX:XX:XX - trading_agent - INFO - Trade entry logged: BUY 26 MSFT @ $380.00
```

🔴 **SELL Signal**:
```
2025-12-19 XX:XX:XX - trading_agent - INFO - Signal: SELL AAPL - Price: $155.00
2025-12-19 XX:XX:XX - trading_agent - INFO - Trade exit logged: AAPL @ $155.00 (P&L: $130.00, 2.60%)
```

## Timing Verification

To verify it's checking every 5 minutes, watch for these patterns:

1. **Look for timestamps** - Each "Waiting 300 seconds" message should be exactly 5 minutes apart
2. **Count cycles** - In 1 hour, you should see 12 "Waiting 300 seconds" messages (60 min / 5 min = 12)
3. **Check performance messages** - Should appear right before "Waiting" messages

## Troubleshooting

### Bot Not Running?
```powershell
# Check if Python process is running
Get-Process python -ErrorAction SilentlyContinue

# Restart the bot
python main.py
```

### No Log Messages?
- Check if `logs/` folder exists
- Verify bot started successfully (check for error messages)
- Make sure API keys are set correctly in `.env` file

### No Market Data?
- Market might be closed (9:30 AM - 4:00 PM ET, weekdays)
- Check "No bars returned" warnings in logs
- Verify Alpaca API keys are valid

## Stop the Bot

Press `Ctrl+C` in the terminal where the bot is running, or:
```powershell
Get-Process python | Where-Object {$_.MainWindowTitle -like "*main.py*"} | Stop-Process
```


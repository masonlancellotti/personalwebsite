# Monitor Trading Bot Script
# Run this in a separate PowerShell window to monitor the bot's activity

$logFile = Get-ChildItem -Path "logs" -Filter "trading_agent_*.log" | Sort-Object LastWriteTime -Descending | Select-Object -First 1

if ($null -eq $logFile) {
    Write-Host "No log file found. Make sure the bot is running." -ForegroundColor Red
    exit
}

Write-Host "Monitoring bot activity from: $($logFile.Name)" -ForegroundColor Green
Write-Host "Press Ctrl+C to stop monitoring`n" -ForegroundColor Yellow

# Track last position
$lastPos = 0

while ($true) {
    $content = Get-Content $logFile.FullName -Tail 100
    $newContent = $content[$lastPos..($content.Length-1)]
    
    foreach ($line in $newContent) {
        if ($line -match "Signal:") {
            Write-Host $line -ForegroundColor Cyan
        }
        elseif ($line -match "Trade entry logged|Trade exit logged") {
            Write-Host $line -ForegroundColor Green
        }
        elseif ($line -match "Performance:") {
            Write-Host $line -ForegroundColor Yellow
        }
        elseif ($line -match "Waiting.*seconds") {
            $timestamp = if ($line -match '(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})') { $matches[1] } else { "" }
            Write-Host "$timestamp - Bot completed cycle, waiting for next iteration..." -ForegroundColor Magenta
        }
        elseif ($line -match "ERROR") {
            Write-Host $line -ForegroundColor Red
        }
    }
    
    $lastPos = $content.Length
    Start-Sleep -Seconds 10
}


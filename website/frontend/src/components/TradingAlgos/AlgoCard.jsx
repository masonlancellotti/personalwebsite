import React from 'react'
import ReturnsChart from './ReturnsChart'
import RecentTrades from './RecentTrades'
import LoadingSpinner from './LoadingSpinner'
import './AlgoCard.css'

function AlgoCard({ algorithm, metricsMap = {}, metricsLoaded = false }) {
  // Map algorithm name to project number
  const getProjectNumber = (algorithmName) => {
    const nameLower = algorithmName.toLowerCase()
    if (nameLower.includes('crypto') || nameLower.includes('coin')) {
      return 2
    } else {
      return 1
    }
  }
  
  // Get micro-indicators from pre-fetched metricsMap
  const projectNumber = getProjectNumber(algorithm.name)
  const microIndicators = metricsMap[projectNumber] || {}
  // Check if metrics for this project are loaded
  const projectMetricsLoaded = metricsLoaded && metricsMap[projectNumber] !== undefined
  
  // Use portfolioValue from algorithm data instead of fetching separately
  const displayEquity = algorithm.portfolioValue !== undefined && algorithm.portfolioValue !== null 
    ? algorithm.portfolioValue 
    : '—'

  // Helper function to format micro-indicator chips
  const MetricChip = ({ label, value, isPositive, isNegative, isLoading = false }) => {
    const valueClass = isPositive ? 'metric-value-positive' : isNegative ? 'metric-value-negative' : ''
    return (
      <span className="metric-chip">
        <span className="metric-chip-label">{label}:</span>
        {isLoading ? (
          <span className="metric-chip-loading">
            <LoadingSpinner size="small" message="" />
          </span>
        ) : (
          <span className={`metric-chip-value ${valueClass}`}>{value}</span>
        )}
      </span>
    )
  }

  // Calculate micro-indicator values (using available data or placeholders)
  const stats = algorithm.stats || {}
  
  // P&L micro-indicators
  const pnlWeek = microIndicators.pnlWeek !== undefined ? microIndicators.pnlWeek : null
  const pnlMonth = microIndicators.pnlMonth !== undefined ? microIndicators.pnlMonth : null
  
  // Win Rate micro-indicators
  // Use avgReturnPct from microIndicators first (dollar amount), then fallback to stats.averagePnl (dollar amount)
  // Both are now dollar amounts (average P&L per closed trade)
  const avgReturnPct = microIndicators.avgReturnPct !== undefined 
    ? microIndicators.avgReturnPct 
    : (stats.averagePnl !== undefined 
      ? stats.averagePnl 
      : null)
  const wins = microIndicators.wins !== undefined ? microIndicators.wins : (stats.winningTrades !== undefined ? stats.winningTrades : null)
  const losses = microIndicators.losses !== undefined ? microIndicators.losses : (stats.losingTrades !== undefined ? stats.losingTrades : null)
  
  // Total Trades micro-indicators
  const tradesToday = microIndicators.tradesToday !== undefined ? microIndicators.tradesToday : null
  const lastTradeHoursAgo = microIndicators.lastTradeHoursAgo !== undefined ? microIndicators.lastTradeHoursAgo : null
  
  // Portfolio Value micro-indicators
  const dayChangePct = microIndicators.dayChangePct !== undefined ? microIndicators.dayChangePct : null
  const dayChangeUsd = microIndicators.dayChangeUsd !== undefined ? microIndicators.dayChangeUsd : null
  const investedPct = microIndicators.investedPct !== undefined ? microIndicators.investedPct : null

  // Shared helper for signed formatting with epsilon thresholds
  // Returns: { formatted: string, isPositive: boolean, isNegative: boolean }
  const formatSignedValue = (val, type) => {
    if (val === null || val === undefined) {
      return { formatted: '—', isPositive: false, isNegative: false }
    }
    
    // Epsilon thresholds: values below these will be treated as zero
    // For percent: 0.00005 = 0.005% (values that round to 0.00% after toFixed(2))
    // For currency: 0.005 = $0.005 (values that round to $0.00 after toFixed(2))
    const epsilon = type === 'percent' ? 0.00005 : 0.005
    
    // Check if value is effectively zero (including exact zero)
    if (val === 0 || Math.abs(val) < epsilon) {
      // Format as zero (no sign, neutral styling)
      const formatted = type === 'percent' ? '0.00%' : '$0.00'
      return { formatted, isPositive: false, isNegative: false }
    }
    
    // Format with sign
    const sign = val >= 0 ? '+' : '-'
    let formatted = type === 'percent' 
      ? `${sign}${Math.abs(val).toFixed(2)}%`
      : `${sign}$${Math.abs(val).toFixed(2)}`
    
    // Check if formatted value rounds to 0.00 - treat as neutral
    // This catches edge cases where rounding results in 0.00 despite being above epsilon
    const numericPart = formatted.replace(/[^0-9.]/g, '')
    if (numericPart === '0.00') {
      // Remove sign and return neutral styling
      formatted = formatted.replace(/^[+-]/, '')
      return { formatted, isPositive: false, isNegative: false }
    }
    
    // Determine styling based on epsilon threshold
    // But ensure that if the absolute value is very small (could round to 0), use neutral
    const absVal = Math.abs(val)
    const roundedVal = parseFloat(absVal.toFixed(2))
    if (roundedVal === 0) {
      // If rounded value is 0, treat as neutral
      formatted = formatted.replace(/^[+-]/, '')
      return { formatted, isPositive: false, isNegative: false }
    }
    
    const isPositive = val > epsilon
    const isNegative = val < -epsilon
    
    return { formatted, isPositive, isNegative }
  }

  // Format helpers (now using shared helper)
  const formatCurrency = (val) => {
    return formatSignedValue(val, 'currency').formatted
  }

  const formatPercent = (val) => {
    return formatSignedValue(val, 'percent').formatted
  }

  const formatHoursAgo = (val) => {
    if (val === null || val === undefined) return '—'
    if (val >= 24) {
      const days = Math.floor(val / 24)
      const hours = Math.floor(val % 24)
      if (hours > 0) {
        return `${days}d ${hours}h ago`
      }
      return `${days}d ago`
    }
    if (val < 1) {
      // Show minutes until it reaches 1 hour
      const minutes = Math.floor(val * 60)
      return `${minutes}m ago`
    }
    // Show hours only (no minutes, no decimal) once it reaches 1 hour
    const hours = Math.floor(val)
    return `${hours}h ago`
  }

  return (
    <div className="algo-card surface-card">
      <div className="algo-header">
        <div className="algo-title-group">
          <h2>
            {algorithm.name}
          </h2>
          <span className="algo-strategy">{algorithm.strategy || 'N/A'}</span>
        </div>
        <div className="last-updated meta-pill">
          <span className="status-indicator"></span>
          <span className="last-updated-text">Last updated: just now</span>
        </div>
      </div>
      
      <p className="algo-description">{algorithm.description}</p>
      
      <div className="algo-stats">
        {algorithm.stats && (
          <div className="stats-grid">
            <div className="stat-item stat-mini-card">
              <span className="stat-label">
                Total P&L
              </span>
              <span className={`stat-value ${(algorithm.stats.totalPnl || 0) >= 0 ? 'positive' : 'negative'}`}>
                ${(algorithm.stats.totalPnl ?? 0).toFixed(2)}
              </span>
              <div className="metric-micro-row">
                {(() => {
                  const weekFormat = formatSignedValue(pnlWeek, 'currency')
                  const monthFormat = formatSignedValue(pnlMonth, 'currency')
                  const isWeekLoading = !projectMetricsLoaded && pnlWeek === null
                  const isMonthLoading = !projectMetricsLoaded && pnlMonth === null
                  return (
                    <>
                      <MetricChip 
                        label="Week" 
                        value={weekFormat.formatted} 
                        isPositive={weekFormat.isPositive}
                        isNegative={weekFormat.isNegative}
                        isLoading={isWeekLoading}
                      />
                      <MetricChip 
                        label="Month" 
                        value={monthFormat.formatted} 
                        isPositive={monthFormat.isPositive}
                        isNegative={monthFormat.isNegative}
                        isLoading={isMonthLoading}
                      />
                    </>
                  )
                })()}
              </div>
            </div>
            {algorithm.stats.winRate !== undefined && (
              <div className="stat-item stat-mini-card">
                <span className="stat-label">
                  Win Rate
                </span>
                <span className="stat-value">
                  {algorithm.stats.winRate === null || algorithm.stats.winRate === undefined
                    ? 'N/A' 
                    : `${algorithm.stats.winRate.toFixed(1)}%`}
                </span>
                <div className="metric-micro-row">
                  {(() => {
                    const avgReturnFormat = formatSignedValue(avgReturnPct, 'currency')
                    const isAvgReturnLoading = !projectMetricsLoaded && avgReturnPct === null && (stats.averagePnl === undefined || stats.averagePnl === null)
                    const isWinsLossesLoading = !projectMetricsLoaded && wins === null && losses === null && (stats.winningTrades === undefined || stats.losingTrades === undefined)
                    return (
                      <>
                        <MetricChip 
                          label="Avg. return" 
                          value={avgReturnFormat.formatted}
                          isPositive={avgReturnFormat.isPositive}
                          isNegative={avgReturnFormat.isNegative}
                          isLoading={isAvgReturnLoading}
                        />
                        <MetricChip 
                          label="W/L (closed)" 
                          value={wins !== null && wins !== undefined && losses !== null && losses !== undefined 
                            ? (wins === 0 && losses === 0 ? '—' : `${wins}/${losses}`)
                            : '—'}
                          isLoading={isWinsLossesLoading}
                        />
                      </>
                    )
                  })()}
                </div>
              </div>
            )}
            {algorithm.stats.totalTrades !== undefined && (
              <div className="stat-item stat-mini-card">
                <span className="stat-label">
                  Total Trades
                </span>
                <span className="stat-value">{algorithm.stats.totalTrades || 0}</span>
                <div className="metric-micro-row">
                  {(() => {
                    const isTradesTodayLoading = !projectMetricsLoaded && tradesToday === null
                    const isLastTradeLoading = !projectMetricsLoaded && lastTradeHoursAgo === null
                    return (
                      <>
                        <MetricChip 
                          label="Today" 
                          value={tradesToday !== null && tradesToday !== undefined 
                            ? tradesToday.toString()
                            : '—'}
                          isLoading={isTradesTodayLoading}
                        />
                        <MetricChip 
                          label="Last trade" 
                          value={formatHoursAgo(lastTradeHoursAgo)}
                          isLoading={isLastTradeLoading}
                        />
                      </>
                    )
                  })()}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
      
      <div className="portfolio-value portfolio-mini-card">
        <span className="portfolio-label">Total Portfolio Value</span>
        <span className="portfolio-amount">
          {typeof displayEquity === 'number' 
            ? `$${displayEquity.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
            : displayEquity}
        </span>
        <div className="metric-micro-row">
          {(() => {
            const dayChangeFormat = formatSignedValue(dayChangePct, 'percent')
            const isDayChangeLoading = !projectMetricsLoaded && dayChangePct === null
            const isInvestedLoading = !projectMetricsLoaded && investedPct === null
            return (
              <>
                <MetricChip 
                  label="Day" 
                  value={dayChangeFormat.formatted} 
                  isPositive={dayChangeFormat.isPositive}
                  isNegative={dayChangeFormat.isNegative}
                  isLoading={isDayChangeLoading}
                />
                <MetricChip 
                  label="Total invested" 
                  value={investedPct !== null && investedPct !== undefined 
                    ? `${investedPct.toFixed(0)}%` 
                    : '—'}
                  isLoading={isInvestedLoading}
                />
              </>
            )
          })()}
        </div>
      </div>
      
      <div className="chart-trades-section">
        <ReturnsChart algorithmName={algorithm.name} />
        <RecentTrades algorithmName={algorithm.name} />
      </div>
    </div>
  )
}

export default AlgoCard


import React, { useState, useEffect } from 'react'
import { getTrades } from '../../services/api'
import LoadingSpinner from './LoadingSpinner'
import './RecentTrades.css'

function RecentTrades({ algorithmName }) {
  const [trades, setTrades] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  
  // Check if this is crypto algorithm
  const isCrypto = algorithmName.toLowerCase().includes('crypto')
  
  // Project 3 removed
  const isOptions = false

  useEffect(() => {
    fetchTrades()
  }, [algorithmName])

  const fetchTrades = async () => {
    try {
      setLoading(true)
      const tradesData = await getTrades(algorithmName, 5)
      const fetchedTrades = tradesData.trades || []
      
      // Log trade dates for debugging
      if (fetchedTrades.length > 0) {
        console.log('[RecentTrades] Fetched trades with dates:')
        fetchedTrades.forEach((trade, idx) => {
          const timeKey = trade.exit_time || trade.entry_time
          console.log(`  ${idx + 1}. ${trade.symbol} (${trade.status}): ${timeKey}`)
        })
      }
      
      // Sort by most recent first (use entry_time which is created_at for crypto orders)
      const sortedTrades = fetchedTrades.sort((a, b) => {
        const timeA = a.entry_time || a.exit_time || ''
        const timeB = b.entry_time || b.exit_time || ''
        return new Date(timeB) - new Date(timeA) // Most recent first
      })
      setTrades(sortedTrades)
      setError(null)
    } catch (err) {
      console.error('Error fetching trades:', err)
      setError('Failed to load trade history')
      // Generate sample trades for demo
      setTrades(generateSampleTrades())
    } finally {
      setLoading(false)
    }
  }

  const generateSampleTrades = () => {
    const symbols = ['AAPL', 'MSFT', 'GOOGL', 'NVDA', 'TSLA']
    const sampleTrades = []
    
    for (let i = 0; i < 5; i++) {
      const side = Math.random() > 0.5 ? 'buy' : 'sell'
      const entryPrice = 100 + Math.random() * 200
      const exitPrice = entryPrice + (Math.random() - 0.4) * 20
      const pnl = side === 'buy' 
        ? (exitPrice - entryPrice) * 10 
        : (entryPrice - exitPrice) * 10

      sampleTrades.push({
        symbol: symbols[Math.floor(Math.random() * symbols.length)],
        side,
        entry_price: parseFloat(entryPrice.toFixed(2)),
        exit_price: parseFloat(exitPrice.toFixed(2)),
        shares: 10,
        pnl: parseFloat(pnl.toFixed(2)),
        pnl_percent: parseFloat(((pnl / (entryPrice * 10)) * 100).toFixed(2)),
        entry_time: new Date(Date.now() - Math.random() * 7 * 24 * 60 * 60 * 1000).toISOString(),
        exit_time: new Date().toISOString(),
        status: 'closed'
      })
    }
    
    return sampleTrades.sort((a, b) => new Date(b.exit_time) - new Date(a.exit_time))
  }

  // Cache for formatted dates to prevent re-parsing - persists across renders
  const dateCacheRef = React.useRef(new Map())
  
  const formatDate = (dateString) => {
    if (!dateString) return '—'
    
    const cache = dateCacheRef.current
    
    // Return cached value if available
    if (cache.has(dateString)) {
      return cache.get(dateString)
    }
    
    try {
      // Parse the date string - handle ISO format with Z
      let date
      if (dateString.endsWith('Z')) {
        // UTC timezone
        date = new Date(dateString)
      } else if (dateString.includes('T') && !dateString.includes('+') && !dateString.includes('-', 10)) {
        // ISO format without timezone, assume UTC
        date = new Date(dateString + 'Z')
      } else {
        date = new Date(dateString)
      }
      
      // Validate date is valid
      if (isNaN(date.getTime())) {
        console.warn('[RecentTrades] Invalid date string:', dateString)
        return 'Invalid Date'
      }
      
      // For crypto, use ET timezone; for stocks, use local timezone
      const timeZone = isCrypto ? 'America/New_York' : Intl.DateTimeFormat().resolvedOptions().timeZone
      
      // Use toLocaleString to ensure time is displayed correctly
      const formatted = date.toLocaleString('en-US', { 
        month: 'short', 
        day: 'numeric',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        hour12: true,
        timeZone: timeZone
      })
      
      // Cache the formatted result
      cache.set(dateString, formatted)
      
      return formatted
    } catch (error) {
      console.error('[RecentTrades] Error formatting date:', dateString, error)
      return 'Invalid Date'
    }
  }

  const formatCurrency = (value) => {
    return `$${Math.abs(value).toFixed(2)}`
  }

  const formatQuantity = (qty) => {
    if (!qty && qty !== 0) return '—'
    
    const numQty = parseFloat(qty)
    if (isNaN(numQty)) return '—'
    
    // For very large numbers, use abbreviated format
    if (Math.abs(numQty) >= 1000000) {
      // Millions or more - use M notation
      const millions = numQty / 1000000
      if (Math.abs(millions) >= 1000) {
        // Billions
        const billions = numQty / 1000000000
        return `${billions.toFixed(2)}B`
      }
      // Show 2 decimal places for millions
      return `${millions.toFixed(2)}M`
    } else if (Math.abs(numQty) >= 1000) {
      // Thousands - use K notation
      const thousands = numQty / 1000
      // Show 2 decimal places for thousands
      return `${thousands.toFixed(2)}K`
    }
    
    // For smaller numbers, use comma separators and smart decimal places
    if (numQty % 1 === 0) {
      // Whole number - add commas
      return numQty.toLocaleString('en-US', { maximumFractionDigits: 0 })
    }
    
    // Fractional number - determine appropriate decimal places
    const absQty = Math.abs(numQty)
    let decimals = 4 // default
    
    if (absQty >= 100) {
      decimals = 2 // Large numbers: 2 decimals
    } else if (absQty >= 10) {
      decimals = 3 // Medium numbers: 3 decimals
    } else if (absQty >= 1) {
      decimals = 4 // Small numbers: 4 decimals
    } else {
      decimals = 6 // Very small numbers: 6 decimals
    }
    
    // Format with commas and remove trailing zeros
    const formatted = numQty.toLocaleString('en-US', { 
      maximumFractionDigits: decimals,
      minimumFractionDigits: 0
    })
    
    return formatted
  }

  const formatSymbol = (symbol) => {
    if (!symbol) return '—'
    
    // For options, extract just the base ticker
    // Options format: AAPL250117C00250000 -> AAPL
    // Pattern: letters at the start, followed by numbers/letters
    if (isOptions) {
      // Match only the leading letters (the stock ticker)
      const match = symbol.match(/^[A-Z]+/)
      return match ? match[0] : symbol
    }
    
    // For crypto, remove USD suffix (e.g., BTCUSD -> BTC)
    if (isCrypto && symbol.endsWith('USD')) {
      return symbol.slice(0, -3)
    }
    
    // For stocks, return as-is
    return symbol
  }

  // Always show only last 5 trades (or less if fewer than 5)
  const displayedTrades = trades.slice(0, 5)

  if (loading) {
    return (
      <div className="recent-trades">
        <h3>Recent Transactions</h3>
        <div className="trades-table surface-card">
          <div className="trades-loading-container">
            <LoadingSpinner message="Loading trades" size="medium" />
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="recent-trades">
      <h3>Recent Transactions</h3>
      
      {error ? (
        <div className="trades-table surface-card">
          <div className="trades-error-container">
            <div className="trades-error-message">{error}</div>
            <button className="trades-retry-btn" onClick={fetchTrades}>
              Retry
            </button>
          </div>
        </div>
      ) : displayedTrades.length > 0 ? (
        <div className="trades-table surface-card">
          <div className="trades-header">
            <div>Symbol</div>
            <div>Action</div>
            <div>Qty</div>
            <div>Price</div>
            <div>Date</div>
          </div>
          <div className="trades-body">
            {displayedTrades.map((trade, index) => (
              <div key={index} className="trade-row">
                <div className="trade-symbol">{formatSymbol(trade.symbol)}</div>
                <div className={`trade-side ${trade.side}`}>
                  {trade.side === 'buy' ? 'BUY' : trade.side === 'sell' ? 'SELL' : trade.side.toUpperCase()}
                </div>
                <div>{formatQuantity(trade.qty || trade.shares)}</div>
                <div>{formatCurrency(trade.entry_price)}</div>
                <div className="trade-date">{formatDate(trade.entry_time || trade.exit_time)}</div>
              </div>
            ))}
          </div>
        </div>
      ) : (
        <div className="trades-table surface-card">
          <div className="trades-empty">No trades available</div>
        </div>
      )}
    </div>
  )
}

export default RecentTrades


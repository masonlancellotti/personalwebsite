import React, { useState, useEffect, useRef, useCallback } from 'react'
import { LineChart, Line, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'
import { getPerformance } from '../../services/api'
import TimeframeSelector from './TimeframeSelector'
import LoadingSpinner from './LoadingSpinner'
import './ReturnsChart.css'

function ReturnsChart({ algorithmName }) {
  const [timeframe, setTimeframe] = useState('day')
  const [data, setData] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [chartDimensions, setChartDimensions] = useState({ width: 0, height: 0 })
  const [cursorX, setCursorX] = useState(null)
  const chartContainerRef = useRef(null)

  useEffect(() => {
    fetchPerformanceData()
  }, [algorithmName, timeframe])

  // ResizeObserver to track chart container dimensions
  useEffect(() => {
    if (!chartContainerRef.current) return

    const resizeObserver = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const { width, height } = entry.contentRect
        setChartDimensions({ width, height })
      }
    })

    resizeObserver.observe(chartContainerRef.current)

    return () => {
      resizeObserver.disconnect()
    }
  }, [data])

  // Calculate plot rectangle (excluding axis gutters)
  const getPlotRect = useCallback(() => {
    const margin = { 
      left: 0, 
      right: timeframe === 'day' || timeframe === 'week' ? 15 : 0, 
      top: 35, 
      bottom: 20 
    }
    const yAxisWidth = 60
    const xAxisHeight = 20 + 8 // bottom margin + tick margin
    
    return {
      plotLeft: margin.left + yAxisWidth,
      plotRight: chartDimensions.width - margin.right,
      plotTop: margin.top,
      plotBottom: chartDimensions.height - margin.bottom - xAxisHeight,
      width: chartDimensions.width,
      height: chartDimensions.height
    }
  }, [chartDimensions, timeframe])

  // Unified time domain function for all ranges
  const getTimeDomain = useCallback((range, dataPoints, timezone = 'America/New_York') => {
    const now = Date.now()
    let domainStart, domainEnd
    
    if (range === 'day') {
      // Day: start at today 4:00 AM NY, end at now (or end of day)
      const nowDate = new Date()
      const etParts = new Intl.DateTimeFormat('en-US', {
        timeZone: timezone,
        year: 'numeric',
        month: 'numeric',
        day: 'numeric'
      }).formatToParts(nowDate)
      
      const year = parseInt(etParts.find(p => p.type === 'year').value)
      const month = parseInt(etParts.find(p => p.type === 'month').value)
      const dayNum = parseInt(etParts.find(p => p.type === 'day').value)
      
      domainStart = etToUTC(year, month, dayNum, 4, 0)
      domainEnd = etToUTC(year, month, dayNum, 21, 0) // 9 PM ET
    } else if (range === 'week') {
      // Week: 7 days ago to now
      domainStart = now - (7 * 24 * 60 * 60 * 1000)
      domainEnd = now
    } else if (range === 'month') {
      // Month: 30 days ago to now
      domainStart = now - (30 * 24 * 60 * 60 * 1000)
      domainEnd = now
    } else if (range === '3m') {
      // 3M: 90 days ago to now
      domainStart = now - (90 * 24 * 60 * 60 * 1000)
      domainEnd = now
    } else if (range === 'year') {
      // Year: 365 days ago to now
      domainStart = now - (365 * 24 * 60 * 60 * 1000)
      domainEnd = now
    } else if (range === 'ytd') {
      // YTD: start of year to now
      const yearStart = new Date(new Date().getFullYear(), 0, 1).getTime()
      domainStart = yearStart
      domainEnd = now
    } else if (range === 'all') {
      // All: use data range or reasonable default
      if (dataPoints && dataPoints.length > 0) {
        const timestamps = dataPoints.map(d => d.t).filter(t => t != null && !isNaN(t))
        if (timestamps.length > 0) {
          domainStart = Math.min(...timestamps)
          domainEnd = now
        } else {
          domainStart = now - (365 * 24 * 60 * 60 * 1000)
          domainEnd = now
        }
      } else {
        domainStart = now - (365 * 24 * 60 * 60 * 1000)
        domainEnd = now
      }
    } else {
      // Default: use data range
      if (dataPoints && dataPoints.length > 0) {
        const timestamps = dataPoints.map(d => d.t).filter(t => t != null && !isNaN(t))
        if (timestamps.length > 0) {
          domainStart = Math.min(...timestamps)
          domainEnd = Math.max(...timestamps)
        } else {
          domainStart = now - (30 * 24 * 60 * 60 * 1000)
          domainEnd = now
        }
      } else {
        domainStart = now - (30 * 24 * 60 * 60 * 1000)
        domainEnd = now
      }
    }
    
    return { domainStart, domainEnd }
  }, [])

  // Handle cursor line positioning based on Recharts coordinate
  const handleTooltipActive = useCallback((coord, domainStart) => {
    if (!coord) {
      setCursorX(null)
      return
    }
    
    const plotRect = getPlotRect()
    if (plotRect.width === 0 || plotRect.height === 0) {
      setCursorX(null)
      return
    }
    
    // Clamp cursor to plot area bounds
    let cursorXPos = coord.x
    
    // If coordinate is before plot area (before domain start), pin it to the Y-axis
    if (coord.x < plotRect.plotLeft) {
      cursorXPos = plotRect.plotLeft
    }
    
    // Clamp to plot area right boundary
    if (cursorXPos > plotRect.plotRight) {
      cursorXPos = plotRect.plotRight
    }
    
    setCursorX(cursorXPos)
  }, [getPlotRect])

  const fetchPerformanceData = async () => {
    try {
      setLoading(true)
      const performanceData = await getPerformance(algorithmName, timeframe)
      
      // Step 1: Get raw data
      const raw = performanceData.data || []
      
      // Step 2: Convert to ms timestamps and normalize field names
      const toMs = (t) => {
        if (typeof t === 'number') {
          // If timestamp is in seconds (10 digits), convert to ms
          if (t < 10000000000) {
            return t * 1000
          }
          return t
        }
        // If it's a date string, convert to ms
        return new Date(t).getTime()
      }
      
      // Map raw data to normalized format with t (timestamp) and v (value/equity)
      let rawMapped = raw.map(p => {
        const t = toMs(p.timestamp || p.date)
        const v = p.equity || 0
        return { t, v, equity: v, returns: p.returns || 0 }
      })
      
      // Sort rawMapped by timestamp to ensure last point is truly the latest (create new array)
      rawMapped = [...rawMapped].sort((a, b) => a.t - b.t)
      
      // Step 3: Define lookback times in milliseconds
      const lookbackMs = (range) => {
        const now = Date.now()
        switch(range) {
          case 'day': return 24 * 60 * 60 * 1000  // 1 day
          case 'week': return 7 * 24 * 60 * 60 * 1000  // 7 days
          case 'month': return 30 * 24 * 60 * 60 * 1000  // 30 days
          case '3m': return 90 * 24 * 60 * 60 * 1000  // 90 days
          case 'year': return 365 * 24 * 60 * 60 * 1000  // 365 days
          case 'ytd': {
            const yearStart = new Date(new Date().getFullYear(), 0, 1).getTime()
            return now - yearStart
          }
          case 'all': return Infinity
          default: return 365 * 24 * 60 * 60 * 1000
        }
      }
      
      // Step 4: Filter by range
      // For year/ytd/all: trust backend series, no client-side filtering (daily points arrive at ~20:00 ET)
      // For other timeframes: apply time-based filtering
      let series
      if (timeframe === 'year' || timeframe === 'ytd' || timeframe === 'all') {
        // No filtering - trust backend series as returned (create new array)
        series = [...rawMapped].sort((a, b) => a.t - b.t)
      } else {
        // For 'day' timeframe, accept data from the last 3 days (to handle weekends showing Friday's data)
        // For other timeframes, use normal filtering
        const now = Date.now()
        let start, end
        if (timeframe === 'day') {
          // Accept data from last 3 days (to include Friday's data on weekends)
          start = now - (3 * 24 * 60 * 60 * 1000)
          end = now
        } else {
          start = now - lookbackMs(timeframe)
          end = now
        }
        
        // Filter by range with inclusive end (create new array)
        series = [...rawMapped]
          .filter(p => p.t >= start && p.t <= end)
          .sort((a, b) => a.t - b.t)
      }
      
      // For Day timeframe: sort, dedupe timestamps, and keep unique entries
      if (timeframe === 'day' && series.length > 0) {
        // Remove duplicates by timestamp (keep first occurrence)
        const seen = new Set()
        series = series.filter(p => {
          if (seen.has(p.t)) {
            return false
          }
          seen.add(p.t)
          return true
        })
        // Ensure sorted by timestamp (create new array)
        series = [...series].sort((a, b) => a.t - b.t)
      }
      
      // Step 1: Hard debug logs
      console.log("RANGE", timeframe)
      console.log("RAW", raw.length, raw[0], raw[raw.length - 1])
      console.log("SERIES_LEN", series.length)
      console.log("T_MINMAX", series[0]?.t, series[series.length - 1]?.t)
      console.log("UNIQUE_T", new Set(series.map(p => p.t)).size)
      console.log("SAMPLE_T", series.slice(0, 5).map(p => p.t))
      
      // For ytd/year/all: identify what's being plotted
      if (timeframe === 'ytd' || timeframe === 'year' || timeframe === 'all') {
        const lastPoint = series[series.length - 1]
        const lastPointValue = lastPoint?.v || lastPoint?.equity || 0
        const seriesKeyUsed = 'v' // Chart uses dataKey="v" which maps to equity
        const yAxisLabel = '$' // formatCurrency formats as currency
        
        // Single log as requested: timeframe + series_key_used + yAxisLabel + lastPointValue
        console.log(`PLOT_IDENTIFY [${timeframe}]: series_key_used=${seriesKeyUsed}, yAxisLabel=${yAxisLabel}, lastPointValue=${lastPointValue}`)
      }
      
      // Check if current time is before 4am ET, and if so, use current time for timestamps
      // This makes the graph show current time even though the price is from market close
      const checkIfBefore4amET = () => {
        const now = new Date()
        const etFormatter = new Intl.DateTimeFormat('en-US', {
          timeZone: 'America/New_York',
          hour: 'numeric',
          hour12: false
        })
        const currentHourET = parseInt(etFormatter.format(now))
        return currentHourET < 4
      }
      
      if (series.length > 0 && checkIfBefore4amET()) {
        // Before 4am ET: replace timestamps with current time
        const currentTime = Date.now()
        series = series.map((point, index) => {
          // For the last point (most recent data), use current time
          // For other points, keep their original timestamps
          if (index === series.length - 1) {
            return { ...point, t: currentTime }
          }
          return point
        })
      }
      
      // Check for collapsed time values
      if (series.length === 1 || new Set(series.map(p => p.t)).size === 1) {
        console.error("ERROR: Collapsed time values detected! All points have same timestamp.")
      }
      
      // Verify timestamps are in ms (13 digits)
      const invalidTimestamps = series.filter(p => p.t < 1000000000000 || p.t > 9999999999999)
      if (invalidTimestamps.length > 0) {
        console.error("ERROR: Invalid timestamps (not in ms):", invalidTimestamps.slice(0, 3))
      }
      
      // Right before rendering: log last point for year/ytd/all AFTER filtering
      if ((timeframe === 'year' || timeframe === 'ytd' || timeframe === 'all') && series.length > 0) {
        const lastPoint = series[series.length - 1]
        const lastPointDate = new Date(lastPoint.t).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
        const lastPointTimestamp = lastPoint.t
        console.log(`AFTER_FILTER [${timeframe}]: lastPointDate=${lastPointDate}, lastPointTimestamp=${lastPointTimestamp}`)
      }
      
      // Get time domain for clamping
      const { domainStart, domainEnd } = getTimeDomain(timeframe, series)
      
      // Transform data: add tsRaw (original) and tsPlot (clamped), and merge early points
      let transformedSeries = []
      
      if (series.length > 0) {
        // Separate points before domainStart and points after
        const pointsBeforeStart = series.filter(p => p.t < domainStart)
        const pointsAfterStart = series.filter(p => p.t >= domainStart)
        
        // If there are points before domainStart, merge them into one representative point
        if (pointsBeforeStart.length > 0) {
          // Use the last point before domainStart (closest to start) as representative
          const representativePoint = pointsBeforeStart[pointsBeforeStart.length - 1]
          transformedSeries.push({
            ...representativePoint,
            tsRaw: representativePoint.t, // Original timestamp
            tsPlot: domainStart, // Clamped to domain start
            t: domainStart // For backward compatibility
          })
        }
        
        // Add all points after domainStart (no clamping needed)
        transformedSeries.push(...pointsAfterStart.map(p => ({
          ...p,
          tsRaw: p.t, // Original timestamp
          tsPlot: p.t, // No clamping needed
          t: p.t // Keep original
        })))
        
        // Sort by tsPlot to ensure correct order
        transformedSeries.sort((a, b) => a.tsPlot - b.tsPlot)
      }
      
      // Verify data integrity before setting
      if (transformedSeries.length > 0) {
        const timestamps = transformedSeries.map(p => p.tsRaw).filter(t => t != null && !isNaN(t))
        const minTs = Math.min(...timestamps)
        const maxTs = Math.max(...timestamps)
        const uniqueCount = new Set(timestamps).size
        
        console.log(`XAXIS_VERIFY [${timeframe}]: points=${transformedSeries.length}, unique_timestamps=${uniqueCount}, min=${new Date(minTs).toLocaleDateString()}, max=${new Date(maxTs).toLocaleDateString()}`)
      }
      
      // Create new array reference to force React re-render
      setData(transformedSeries)
      setError(null)
    } catch (err) {
      console.error('Error fetching performance data:', err)
      setError('Failed to load performance data')
      setData([])
    } finally {
      setLoading(false)
    }
  }

  const generateSampleData = () => {
    // Generate sample data for demo purposes
    const data = []
    const startDate = new Date()
    startDate.setDate(startDate.getDate() - 30)
    let cumulativeReturn = 0

    for (let i = 0; i < 30; i++) {
      const date = new Date(startDate)
      date.setDate(date.getDate() + i)
      cumulativeReturn += (Math.random() - 0.48) * 100 // Slight positive bias
      data.push({
        date: date.toISOString().split('T')[0],
        returns: parseFloat(cumulativeReturn.toFixed(2)),
        equity: 10000 + cumulativeReturn
      })
    }
    return data
  }

  const formatCurrency = (value) => {
    if (value >= 1000) {
      const kValue = value / 1000
      // Compact format: $9.99k (2 decimals max)
      return `$${kValue.toFixed(2)}k`
    }
    // For values < 1000, show as whole number
    return `$${Math.round(value)}`
  }

  const formatDate = (timestamp) => {
    if (!timestamp || isNaN(timestamp)) {
      return ''
    }
    let date = new Date(Number(timestamp))
    // Check if date is valid
    if (isNaN(date.getTime())) {
      return ''
    }
    // For daily view, show time; for others, show date
    if (timeframe === 'day') {
      return date.toLocaleTimeString('en-US', { hour: 'numeric', hour12: true })
    }
    
    // For month+ timeframes: only show today's date for the RIGHTMOST tick
    if (timeframe === 'month' || timeframe === '3m' || timeframe === 'year' || timeframe === 'ytd' || timeframe === 'all') {
      // Compute max domain value on the fly
      let maxDomain = null
      if (data.length > 0) {
        const timestamps = data.map(d => d.t).filter(t => t != null && !isNaN(t))
        if (timestamps.length > 0) {
          let maxTimestamp = Math.max(...timestamps)
          const todayET = getTodayInET()
          const endOfTodayET = todayET + (24 * 60 * 60 * 1000) - 1 // End of today in ET
          maxDomain = Math.max(maxTimestamp, endOfTodayET)
        }
      }
      
      if (maxDomain !== null) {
        const tickMs = Number(timestamp)
        // Only show today for the rightmost tick (within 2 hours of max domain)
        // This ensures only the final tick shows today, not earlier ticks
        const threshold = 2 * 60 * 60 * 1000 // 2 hours threshold (much tighter)
        if (tickMs >= maxDomain - threshold && tickMs <= maxDomain + threshold) {
          // This is the rightmost tick - show today's date
          const todayDateFormatter = new Intl.DateTimeFormat('en-US', {
            timeZone: 'America/New_York',
            month: 'short',
            day: 'numeric'
          })
          return todayDateFormatter.format(new Date())
        }
      }
    }
    
    // Otherwise, format the actual date
    const dateFormatter = new Intl.DateTimeFormat('en-US', {
      timeZone: 'America/New_York',
      month: 'short',
      day: 'numeric'
    })
    return dateFormatter.format(date)
  }

  // Helper: Convert ET date/time to UTC timestamp (in milliseconds)
  // Uses binary search to find UTC time that represents the desired ET time
  const etToUTC = (year, month, day, hour, minute = 0) => {
    const etFormatter = new Intl.DateTimeFormat('en-US', {
      timeZone: 'America/New_York',
      year: 'numeric',
      month: 'numeric',
      day: 'numeric',
      hour: 'numeric',
      minute: 'numeric',
      hour12: false
    })
    
    // Start with approximate UTC (assume ET is UTC-5 or UTC-4)
    // EST = UTC-5, EDT = UTC-4
    let lowUTC = new Date(Date.UTC(year, month - 1, day, hour + 5, minute, 0)).getTime() // EST estimate
    let highUTC = new Date(Date.UTC(year, month - 1, day, hour + 4, minute, 0)).getTime() // EDT estimate
    
    // Binary search to find exact UTC
    let bestUTC = lowUTC
    let bestDiff = Infinity
    
    for (let attempt = 0; attempt < 20; attempt++) {
      const midUTC = Math.floor((lowUTC + highUTC) / 2)
      const candidateDate = new Date(midUTC)
      const etParts = etFormatter.formatToParts(candidateDate)
      
      const etY = parseInt(etParts.find(p => p.type === 'year').value)
      const etM = parseInt(etParts.find(p => p.type === 'month').value)
      const etD = parseInt(etParts.find(p => p.type === 'day').value)
      const etH = parseInt(etParts.find(p => p.type === 'hour').value)
      const etMin = parseInt(etParts.find(p => p.type === 'minute').value)
      
      // Check if we match
      if (etY === year && etM === month && etD === day && etH === hour && etMin === minute) {
        return midUTC
      }
      
      // Calculate difference
      const dayDiff = etD - day
      const hourDiff = etH - hour
      const totalDiff = Math.abs(dayDiff * 24 + hourDiff)
      
      if (totalDiff < bestDiff) {
        bestDiff = totalDiff
        bestUTC = midUTC
      }
      
      // Adjust search range
      if (dayDiff > 0 || (dayDiff === 0 && hourDiff > 0)) {
        highUTC = midUTC - 1
      } else {
        lowUTC = midUTC + 1
      }
      
      if (lowUTC >= highUTC) break
    }
    
    return bestUTC
  }

  // Get current date in ET timezone (today at midnight ET)
  const getTodayInET = () => {
    const now = new Date()
    const etFormatter = new Intl.DateTimeFormat('en-US', {
      timeZone: 'America/New_York',
      year: 'numeric',
      month: 'numeric',
      day: 'numeric'
    })
    const parts = etFormatter.formatToParts(now)
    const year = parseInt(parts.find(p => p.type === 'year').value)
    const month = parseInt(parts.find(p => p.type === 'month').value)
    const day = parseInt(parts.find(p => p.type === 'day').value)
    
    // Create a date at midnight ET for today
    return etToUTC(year, month, day, 0, 0)
  }

  // Compute XAxis domain using unified time domain function
  const computeXAxisDomain = () => {
    if (data.length === 0) {
      return ['dataMin', 'dataMax']
    }
    
    const { domainStart, domainEnd } = getTimeDomain(timeframe, data)
    
    // For the domain, use the first data point's tsPlot (which is clamped to domainStart)
    // This ensures the line starts exactly at the Y-axis
    const timestamps = data.map(d => d.tsPlot || d.t).filter(t => t != null && !isNaN(t))
    const firstDataPoint = timestamps.length > 0 ? Math.min(...timestamps) : domainStart
    
    return [firstDataPoint, domainEnd]
  }

  // Compute ticks for day view
  const computeDayTicks = () => {
    if (timeframe !== 'day') {
      return undefined
    }
    
    const now = new Date()
    const etParts = new Intl.DateTimeFormat('en-US', {
      timeZone: 'America/New_York',
      year: 'numeric',
      month: 'numeric',
      day: 'numeric'
    }).formatToParts(now)
    
    const year = parseInt(etParts.find(p => p.type === 'year').value)
    const month = parseInt(etParts.find(p => p.type === 'month').value)
    const dayNum = parseInt(etParts.find(p => p.type === 'day').value)
    
    // Ticks: 4 AM, 8 AM, 12 PM, 4 PM, 8 PM ET
    const hours = [4, 8, 12, 16, 20]
    return hours.map(hour => etToUTC(year, month, dayNum, hour, 0))
  }

  // Compute evenly spaced ticks for week timeframe
  const computeWeekTicks = () => {
    if (timeframe !== 'week' || data.length === 0) {
      return undefined
    }
    
    const { domainStart, domainEnd } = getTimeDomain(timeframe, data)
    const numTicks = 5
    const ticks = []
    const step = (domainEnd - domainStart) / (numTicks - 1)
    
    for (let i = 0; i < numTicks; i++) {
      ticks.push(domainStart + (i * step))
    }
    
    return ticks.length > 0 ? ticks : undefined
  }

  const dayTicks = computeDayTicks()
  const weekTicks = computeWeekTicks()
  const xAxisDomain = computeXAxisDomain()
  
  // Get domainStart for clamping (already computed in getTimeDomain)
  const { domainStart } = getTimeDomain(timeframe, data)

  // Data is already transformed in fetchPerformanceData with tsRaw and tsPlot
  // Use data directly (it already has tsRaw and tsPlot from transformation)
  const transformedData = data
  
  // Store max domain for formatDate to use (for month+ timeframes to identify rightmost tick)
  const maxDomainValue = (() => {
    if (timeframe === 'day' || data.length === 0) {
      return null
    }
    if (Array.isArray(xAxisDomain) && xAxisDomain.length === 2) {
      return xAxisDomain[1] // The max value of the domain
    }
    return null
  })()
  
  // Log domain for verification
  if (data.length > 0 && timeframe !== 'day') {
    const domainMin = Array.isArray(xAxisDomain) ? xAxisDomain[0] : 'dataMin'
    const domainMax = Array.isArray(xAxisDomain) ? xAxisDomain[1] : 'dataMax'
    console.log(`XAXIS_DOMAIN [${timeframe}]: domain=[${typeof domainMin === 'number' ? new Date(domainMin).toLocaleDateString() : domainMin}, ${typeof domainMax === 'number' ? new Date(domainMax).toLocaleDateString() : domainMax}], dataRange=[${new Date(Math.min(...data.map(d => d.t))).toLocaleDateString()}, ${new Date(Math.max(...data.map(d => d.t))).toLocaleDateString()}]`)
  }

  // Format tick label for Day: "4 AM", "8 AM", "12 PM", "4 PM", "8 PM"
  const formatDayTick = (timestamp) => {
    if (!dayTicks) return '4 AM'
    
    // Map timestamps to exact labels
    const labels = {
      [dayTicks[0]]: '4 AM',
      [dayTicks[1]]: '8 AM',
      [dayTicks[2]]: '12 PM',
      [dayTicks[3]]: '4 PM',
      [dayTicks[4]]: '8 PM'
    }
    return labels[timestamp] || '4 AM'
  }

  if (loading) {
    return (
      <div className="returns-chart">
        <h3>Performance</h3>
        <div className="chart-table surface-card">
          <div className="chart-timeframe-header">
            <TimeframeSelector timeframe={timeframe} onChange={setTimeframe} />
          </div>
          <div className="chart-loading-container">
            <LoadingSpinner message="Loading chart data" size="medium" />
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="returns-chart">
      <h3>Performance</h3>
      
      {error ? (
        <div className="chart-table surface-card">
          <div className="chart-timeframe-header">
            <TimeframeSelector timeframe={timeframe} onChange={setTimeframe} />
          </div>
          <div className="chart-error-container">
            <div className="chart-error-message">{error}</div>
            <button className="chart-retry-btn" onClick={fetchPerformanceData}>
              Retry
            </button>
          </div>
        </div>
      ) : data.length > 0 ? (
        <div className="chart-table surface-card">
          <div className="chart-timeframe-header">
            <TimeframeSelector timeframe={timeframe} onChange={setTimeframe} />
          </div>
          <div className="chart-container">
          <div className="chart-wrapper" ref={chartContainerRef}>
            {/* Custom cursor line overlay */}
            {cursorX !== null && (() => {
              const plotRect = getPlotRect()
              if (plotRect.width === 0 || plotRect.height === 0) return null
              return (
                <svg
                  className="custom-cursor-overlay"
                  style={{
                    position: 'absolute',
                    top: 0,
                    left: 0,
                    width: '100%',
                    height: '100%',
                    pointerEvents: 'none',
                    zIndex: 10
                  }}
                >
                  <line
                    x1={cursorX}
                    y1={plotRect.plotTop}
                    x2={cursorX}
                    y2={plotRect.plotBottom}
                    stroke="#d4a574"
                    strokeWidth={1}
                    strokeDasharray="4 4"
                    opacity={0.5}
                  />
                </svg>
              )
            })()}
            <ResponsiveContainer 
              width="100%" 
              height={218}
              key={`${timeframe}-${transformedData.length}-${transformedData[transformedData.length - 1]?.tsPlot}-${transformedData[transformedData.length - 1]?.v}`}
            >
            <LineChart data={transformedData} margin={{ left: 0, right: timeframe === 'day' || timeframe === 'week' ? 15 : 0, top: 35, bottom: 20 }}>
            <defs>
              <linearGradient id="equityGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#d4a574" stopOpacity={0.16} />
                <stop offset="100%" stopColor="#d4a574" stopOpacity={0} />
              </linearGradient>
            </defs>
            <XAxis 
              dataKey="tsPlot" 
              type="number"
              scale="time"
              domain={xAxisDomain}
              stroke="#d1d5db"
              tickFormatter={timeframe === 'day' ? formatDayTick : formatDate}
              tick={{ fill: '#888', fontSize: '0.85rem', fontWeight: 600 }}
              axisLine={true}
              ticks={timeframe === 'day' ? dayTicks : (timeframe === 'week' ? weekTicks : undefined)}
              interval={timeframe === 'day' ? 0 : (timeframe === 'week' ? 0 : 'preserveStartEnd')}
              allowDataOverflow={timeframe === 'day' ? true : false}
              tickMargin={8}
              minTickGap={timeframe === 'day' ? undefined : (timeframe === 'week' ? undefined : 40)}
            />
            <YAxis 
              width={60}
              tickMargin={4}
              stroke="#d1d5db"
              tickFormatter={formatCurrency}
              tick={{ fill: '#888', fontSize: '0.85rem', fontWeight: 600 }}
              axisLine={true}
              domain={(() => {
                // Alpaca-style dynamic Y-axis for all timeframes
                const values = data.map(d => d.v || d.equity).filter(v => v != null && !isNaN(v))
                if (values.length === 0) return ['auto', 'auto']
                
                const minValue = Math.min(...values)
                const maxValue = Math.max(...values)
                const dataRange = maxValue - minValue
                
                // Use the latest value as the center point
                const centerValue = values[values.length - 1] || (minValue + maxValue) / 2
                
                // Base range: small percentage of center value (0.2% on each side = 0.4% total)
                // This gives a tight scale like $9.99k to $10.01k for a $10k portfolio
                const baseRangePercent = 0.004 // 0.4% total (0.2% on each side)
                const baseRange = centerValue * baseRangePercent
                
                // For small movements, use tight scale centered on latest value
                // For large movements, center on the data range
                let domainMin, domainMax
                
                if (dataRange <= baseRange * 2) {
                  // Small movement: use tight scale centered on latest value
                  const minRange = Math.max(dataRange, baseRange)
                  const padding = minRange * 0.05
                  const totalRange = minRange + (padding * 2)
                  domainMin = centerValue - (totalRange / 2)
                  domainMax = centerValue + (totalRange / 2)
                } else {
                  // Large movement: center on the data range with padding
                  const padding = dataRange * 0.05
                  domainMin = minValue - padding
                  domainMax = maxValue + padding
                }
                
                // Round to pretty numbers based on the range size
                const totalRange = domainMax - domainMin
                let roundTo
                if (totalRange < 100) {
                  roundTo = 1
                } else if (totalRange < 1000) {
                  roundTo = 10
                } else if (totalRange < 10000) {
                  roundTo = 50
                } else {
                  roundTo = 100
                }
                
                domainMin = Math.floor(domainMin / roundTo) * roundTo
                domainMax = Math.ceil(domainMax / roundTo) * roundTo
                
                // Ensure we don't go below 0
                if (domainMin < 0) {
                  domainMin = 0
                }
                
                return [domainMin, domainMax]
              })()}
            />
            <Tooltip 
              content={(props) => {
                if (!props.active || !props.payload || props.payload.length === 0) {
                  handleTooltipActive(null)
                  return null
                }
                
                const plotRect = getPlotRect()
                if (plotRect.width === 0 || plotRect.height === 0) {
                  handleTooltipActive(null)
                  return null
                }
                
                // Get coordinate from Recharts (chart's calculated position in SVG coordinates)
                const chartCoord = props.coordinate || { x: 0, y: 0 }
                
                // Check if the hovered data point is before domainStart (using tsRaw)
                const hoveredPayload = props.payload[0]
                const hoveredTsRaw = hoveredPayload?.payload?.tsRaw
                const shouldClampToYAxis = (() => {
                  if (hoveredTsRaw !== undefined && domainStart !== null) {
                    return hoveredTsRaw < domainStart
                  }
                  return false
                })()
                
                // Update cursor line position - clamp to Y-axis if data point is before domainStart
                if (shouldClampToYAxis) {
                  const plotRect = getPlotRect()
                  handleTooltipActive({ ...chartCoord, x: plotRect.plotLeft }, domainStart)
                } else {
                  handleTooltipActive(chartCoord, domainStart)
                }
                
                // Clamp chart coordinate to plot area
                const tooltipWidth = 120
                const tooltipHeight = 60
                
                // Position tooltip to the right of cursor by default
                let tooltipX = chartCoord.x + 12
                let tooltipY = chartCoord.y
                
                // If tooltip would overflow right, flip it left
                if (tooltipX + tooltipWidth > plotRect.plotRight) {
                  tooltipX = chartCoord.x - tooltipWidth - 12
                }
                
                // Clamp tooltip position within plot area (never overlap Y-axis)
                const finalX = Math.max(plotRect.plotLeft, Math.min(tooltipX, plotRect.plotRight - tooltipWidth))
                const finalY = Math.max(plotRect.plotTop, Math.min(tooltipY, plotRect.plotBottom - tooltipHeight))
                
                const value = hoveredPayload?.value || 0
                const label = props.label || ''
                
                // Format label using tsRaw (original timestamp) for tooltip display
                let formattedLabel = label
                let timestampToFormat = null
                
                // Prefer tsRaw from payload (original timestamp), fallback to label
                if (hoveredPayload?.payload?.tsRaw !== undefined) {
                  timestampToFormat = hoveredPayload.payload.tsRaw
                } else if (hoveredPayload?.payload?.t !== undefined) {
                  timestampToFormat = hoveredPayload.payload.t
                } else {
                  timestampToFormat = Number(label)
                }
                
                if (timeframe === 'day' && timestampToFormat !== null) {
                  const date = new Date(timestampToFormat)
                  const etFormatter = new Intl.DateTimeFormat('en-US', {
                    timeZone: 'America/New_York',
                    hour: 'numeric',
                    minute: '2-digit',
                    hour12: true
                  })
                  formattedLabel = etFormatter.format(date)
                } else if (timestampToFormat !== null) {
                  formattedLabel = formatDate(timestampToFormat)
                }
                
                return (
                  <div
                    style={{
                      position: 'absolute',
                      left: `${finalX}px`,
                      top: `${finalY}px`,
                      backgroundColor: 'rgba(255, 255, 255, 0.95)',
                      border: '1px solid rgba(0, 0, 0, 0.1)',
                      borderRadius: '8px',
                      color: '#1a1a1a',
                      padding: '8px 12px',
                      boxShadow: '0 2px 8px rgba(0, 0, 0, 0.1)',
                      pointerEvents: 'none',
                      zIndex: 1000
                    }}
                  >
                    <div style={{ marginBottom: '4px', fontSize: '0.85rem', fontWeight: 600, color: '#888' }}>
                      {formattedLabel}
                    </div>
                    <div style={{ fontSize: '1rem', fontWeight: 700, color: '#1a1a1a' }}>
                      ${value.toFixed(2)}
                    </div>
                  </div>
                )
              }}
              cursor={false}
            />
            <Area
              type="monotone" 
              dataKey="v"
              stroke="none"
              fill="url(#equityGradient)"
            />
            <Line 
              type="monotone" 
              dataKey="v" 
              stroke="#d4a574" 
              strokeWidth={3}
              strokeOpacity={1}
              dot={false}
              activeDot={{ r: 4, fill: '#d4a574', stroke: '#fff', strokeWidth: 2 }}
              isAnimationActive={false}
              connectNulls={true}
            />
          </LineChart>
        </ResponsiveContainer>
          </div>
          </div>
        </div>
      ) : (
        <div className="chart-table surface-card">
          <div className="chart-empty">No performance data available</div>
        </div>
      )}
    </div>
  )
}

export default ReturnsChart


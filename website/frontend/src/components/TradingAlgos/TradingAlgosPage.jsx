import React, { useState, useEffect, useCallback, useRef } from 'react'
import { getAlgorithms, getAlpacaMetrics } from '../../services/api'
import AlgoCard from './AlgoCard'
import LoadingSpinner from './LoadingSpinner'
import './TradingAlgosPage.css'

const loadingMessages = [
  'Initializing...',
  'Fetching trading algorithms...',
  'Analyzing portfolio performance...',
  'Calculating metrics...',
  'Preparing data visualization...',
  'Almost ready...'
]

function TradingAlgosPage() {
  const [algorithms, setAlgorithms] = useState([])
  const [metricsMap, setMetricsMap] = useState({}) // { projectNumber: metrics }
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [loadingMessage, setLoadingMessage] = useState(loadingMessages[0])
  const fetchingRef = useRef(false) // Prevent concurrent fetches

  const fetchAlgorithms = useCallback(async () => {
    // Prevent concurrent fetches
    if (fetchingRef.current) {
      // #region agent log
      fetch('http://127.0.0.1:7245/ingest/9d64e218-9bd1-44d8-aab6-5e10b2f6ec39',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({location:'TradingAlgosPage.jsx:23',message:'fetchAlgorithms SKIPPED - already fetching',data:{timestamp:Date.now()},timestamp:Date.now(),sessionId:'debug-session',runId:'run1',hypothesisId:'D'})}).catch(()=>{});
      // #endregion
      return
    }
    
    fetchingRef.current = true
    try {
      // #region agent log
      fetch('http://127.0.0.1:7245/ingest/9d64e218-9bd1-44d8-aab6-5e10b2f6ec39',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({location:'TradingAlgosPage.jsx:24',message:'fetchAlgorithms START',data:{timestamp:Date.now()},timestamp:Date.now(),sessionId:'debug-session',runId:'run1',hypothesisId:'A,B,C,D'})}).catch(()=>{});
      // #endregion
      setLoading(true)
      setError(null)
      setLoadingMessage('Initializing...')
      
      // First, fetch main algorithm data (fast)
      setLoadingMessage('Fetching trading algorithms...')
      // #region agent log
      fetch('http://127.0.0.1:7245/ingest/9d64e218-9bd1-44d8-aab6-5e10b2f6ec39',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({location:'TradingAlgosPage.jsx:31',message:'BEFORE getAlgorithms',data:{timestamp:Date.now()},timestamp:Date.now(),sessionId:'debug-session',runId:'run1',hypothesisId:'A,B'})}).catch(()=>{});
      // #endregion
      const data = await getAlgorithms()
      // #region agent log
      fetch('http://127.0.0.1:7245/ingest/9d64e218-9bd1-44d8-aab6-5e10b2f6ec39',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({location:'TradingAlgosPage.jsx:32',message:'AFTER getAlgorithms',data:{dataType:Array.isArray(data)?'array':'other',dataLength:Array.isArray(data)?data.length:'N/A',hasData:!!data},timestamp:Date.now(),sessionId:'debug-session',runId:'run1',hypothesisId:'A,B'})}).catch(()=>{});
      // #endregion
      
      // Check if we got valid data
      if (!data) {
        throw new Error('No data received from API')
      }
      
      if (!Array.isArray(data)) {
        throw new Error(`Invalid data format: expected array, got ${typeof data}`)
      }
      
      // Allow empty array - backend should always return at least 2 algorithms, but handle gracefully
      if (data.length === 0) {
        console.warn('API returned empty algorithms array')
        // Still set it so the page can render (just won't show any cards)
        setAlgorithms([])
        setLoading(false)
        return
      }
      
      setLoadingMessage('Analyzing portfolio performance...')
      setAlgorithms(data)
      // #region agent log
      fetch('http://127.0.0.1:7245/ingest/9d64e218-9bd1-44d8-aab6-5e10b2f6ec39',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({location:'TradingAlgosPage.jsx:36',message:'BEFORE setLoading(false)',data:{algorithmsSet:data.length},timestamp:Date.now(),sessionId:'debug-session',runId:'run1',hypothesisId:'C'})}).catch(()=>{});
      // #endregion
      setLoading(false) // Show page immediately
      // #region agent log
      fetch('http://127.0.0.1:7245/ingest/9d64e218-9bd1-44d8-aab6-5e10b2f6ec39',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({location:'TradingAlgosPage.jsx:37',message:'AFTER setLoading(false)',data:{timestamp:Date.now()},timestamp:Date.now(),sessionId:'debug-session',runId:'run1',hypothesisId:'C'})}).catch(()=>{});
      // #endregion
      
      // Then fetch micro-metrics in background (slower, but non-blocking)
      Promise.all([
        getAlpacaMetrics(1).catch(() => ({})),
        getAlpacaMetrics(2).catch(() => ({})),
        getAlpacaMetrics(3).catch(() => ({}))
      ]).then(([metrics1, metrics2, metrics3]) => {
        setMetricsMap({
          1: metrics1,
          2: metrics2,
          3: metrics3
        })
      }).catch(err => {
        console.error('Error fetching micro-metrics:', err)
        // Silently fail - micro-metrics will show dashes
      })
    } catch (err) {
      // #region agent log
      fetch('http://127.0.0.1:7245/ingest/9d64e218-9bd1-44d8-aab6-5e10b2f6ec39',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({location:'TradingAlgosPage.jsx:57',message:'CATCH block',data:{errorMessage:err?.message,errorName:err?.name,errorStack:err?.stack?.substring(0,200),responseStatus:err?.response?.status,responseData:err?.response?.data},timestamp:Date.now(),sessionId:'debug-session',runId:'run1',hypothesisId:'A,D'})}).catch(()=>{});
      // #endregion
      console.error('Error fetching algorithms:', err)
      
      // Provide more helpful error messages
      let errorMessage = 'Failed to load trading algorithms. '
      if (err?.response) {
        // Server responded with error status
        errorMessage += `Server error (${err.response.status}). `
        if (err.response.status === 404) {
          errorMessage += 'API endpoint not found. Please check if the backend server is running.'
        } else if (err.response.status >= 500) {
          errorMessage += 'Server error. Please try again later.'
        }
      } else if (err?.request) {
        // Request was made but no response received
        errorMessage += 'Unable to connect to the server. Please check if the backend is running.'
      } else {
        // Something else happened
        errorMessage += err?.message || 'Unknown error occurred.'
      }
      errorMessage += ' Please refresh the page.'
      
      setError(errorMessage)
      // Don't set fallback data - keep algorithms empty to show error state
      setAlgorithms([])
      setLoading(false)
    } finally {
      fetchingRef.current = false
    }
  }, [])

  const messageIndexRef = useRef(0)
  
  useEffect(() => {
    // #region agent log
    fetch('http://127.0.0.1:7245/ingest/9d64e218-9bd1-44d8-aab6-5e10b2f6ec39',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({location:'TradingAlgosPage.jsx:66',message:'useEffect fetchAlgorithms CALLED',data:{fetchAlgorithmsType:typeof fetchAlgorithms,fetchingRef:fetchingRef.current},timestamp:Date.now(),sessionId:'debug-session',runId:'run1',hypothesisId:'D'})}).catch(()=>{});
    // #endregion
    fetchAlgorithms()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []) // Only run once on mount - fetchAlgorithms is stable with useCallback
  
  useEffect(() => {
    // #region agent log
    fetch('http://127.0.0.1:7245/ingest/9d64e218-9bd1-44d8-aab6-5e10b2f6ec39',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({location:'TradingAlgosPage.jsx:72',message:'useEffect loading MESSAGE',data:{loading},timestamp:Date.now(),sessionId:'debug-session',runId:'run1',hypothesisId:'C'})}).catch(()=>{});
    // #endregion
    if (loading) {
      messageIndexRef.current = 0
      setLoadingMessage(loadingMessages[0])
      const messageInterval = setInterval(() => {
        messageIndexRef.current = (messageIndexRef.current + 1) % loadingMessages.length
        setLoadingMessage(loadingMessages[messageIndexRef.current])
      }, 1200) // Change message every 1.2 seconds
      
      return () => clearInterval(messageInterval)
    } else {
      // Reset to first message when not loading
      messageIndexRef.current = 0
      setLoadingMessage(loadingMessages[0])
    }
  }, [loading])

  // #region agent log
  React.useEffect(() => {
    fetch('http://127.0.0.1:7245/ingest/9d64e218-9bd1-44d8-aab6-5e10b2f6ec39',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({location:'TradingAlgosPage.jsx:89',message:'RENDER check',data:{loading,error,algorithmsLength:algorithms.length},timestamp:Date.now(),sessionId:'debug-session',runId:'run1',hypothesisId:'A,B,C,D'})}).catch(()=>{});
  });
  // #endregion

  if (loading) {
    return (
      <div className="trading-algos-page">
        <div className="page-loading-container">
          <LoadingSpinner message={loadingMessage} size="large" />
        </div>
      </div>
    )
  }

  if (error && algorithms.length === 0) {
    return (
      <div className="trading-algos-page">
        <div className="error-container">
          <div className="error">{error}</div>
          <button onClick={fetchAlgorithms} className="retry-button">
Retry
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="trading-algos-page">
      <p className="page-description">
        Real-time performance indicators and transaction history for various trading algorithms I've created. A variety of strategies are included in each program, and all source code is available on GitHub.
      </p>
      <div className="algorithms-grid">
        {algorithms.map((algo) => (
          <AlgoCard key={algo.name} algorithm={algo} metricsMap={metricsMap} metricsLoaded={Object.keys(metricsMap).length > 0} />
        ))}
      </div>
    </div>
  )
}

export default TradingAlgosPage


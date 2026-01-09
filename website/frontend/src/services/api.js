import axios from 'axios'

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:5000/api'

const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000, // Increased to 30 seconds to handle multiple sequential Alpaca API calls
  headers: {
    'Content-Type': 'application/json'
  }
})

// Helper to encode algorithm names for URLs
const encodeAlgorithmName = (name) => {
  return encodeURIComponent(name.replace(/\s+/g, '_'))
}

export const getAlgorithms = async () => {
  try {
    const response = await api.get('/algorithms')
    return response.data
  } catch (error) {
    console.error('API Error:', error)
    throw error
  }
}

export const getAlgorithm = async (name) => {
  try {
    const encodedName = encodeAlgorithmName(name)
    const response = await api.get(`/algorithms/${encodedName}`)
    return response.data
  } catch (error) {
    console.error('API Error:', error)
    throw error
  }
}

export const getPerformance = async (algorithmName, timeframe = 'all') => {
  try {
    const encodedName = encodeAlgorithmName(algorithmName)
    const response = await api.get(`/algorithms/${encodedName}/performance`, {
      params: { timeframe }
    })
    return response.data
  } catch (error) {
    console.error('API Error:', error)
    throw error
  }
}

export const getTrades = async (algorithmName, limit = 10) => {
  try {
    const encodedName = encodeAlgorithmName(algorithmName)
    const response = await api.get(`/algorithms/${encodedName}/trades`, {
      params: { limit }
    })
    return response.data
  } catch (error) {
    console.error('API Error:', error)
    throw error
  }
}

export const getStats = async (algorithmName) => {
  try {
    const encodedName = encodeAlgorithmName(algorithmName)
    const response = await api.get(`/algorithms/${encodedName}/stats`)
    return response.data
  } catch (error) {
    console.error('API Error:', error)
    throw error
  }
}

export const getLiveEquity = async () => {
  try {
    const response = await api.get('/live-equity')
    return response.data
  } catch (error) {
    console.error('API Error:', error)
    throw error
  }
}

export const getPortfolioLiveEquityExtended = async () => {
  try {
    const response = await api.get('/portfolio/live_equity_extended')
    return response.data
  } catch (error) {
    console.error('API Error fetching live equity extended:', error)
    throw error
  }
}

export const getAlpacaMetrics = async (project) => {
  try {
    const response = await api.get('/alpaca/metrics', {
      params: { project }
    })
    return response.data
  } catch (error) {
    console.error('API Error fetching Alpaca metrics:', error)
    throw error
  }
}

export default api


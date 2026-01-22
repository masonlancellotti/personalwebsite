import React from 'react'
import { BrowserRouter as Router, Routes, Route, useLocation } from 'react-router-dom'
import Navigation from './components/Navigation'
import HomePage from './components/HomePage'
import TradingAlgosPage from './components/TradingAlgos/TradingAlgosPage'
import './App.css'

function MainContent() {
  const location = useLocation()
  const isTradingAlgos = location.pathname === '/tradingalgos'
  const isHomePage = location.pathname === '/'
  
  return (
    <main className={`main-content ${isTradingAlgos || isHomePage ? 'scene-bg' : ''}`}>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/tradingalgos" element={<TradingAlgosPage />} />
      </Routes>
    </main>
  )
}

function App() {
  return (
    <Router>
      <div className="App">
        <Navigation />
        <MainContent />
      </div>
    </Router>
  )
}

export default App


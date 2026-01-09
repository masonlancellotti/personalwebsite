import React from 'react'
import { Link, useLocation } from 'react-router-dom'
import './Navigation.css'

function Navigation() {
  const location = useLocation()

  return (
    <nav className="navigation">
      <div className="nav-container">
        <Link to="/" className="nav-logo">
          Mason Lancellotti
        </Link>
        <div className="nav-links">
          <Link 
            to="/" 
            className={location.pathname === '/' ? 'active' : ''}
          >
            Home
          </Link>
          <Link 
            to="/tradingalgos" 
            className={location.pathname === '/tradingalgos' ? 'active' : ''}
          >
            Trading Algorithms
          </Link>
        </div>
      </div>
    </nav>
  )
}

export default Navigation


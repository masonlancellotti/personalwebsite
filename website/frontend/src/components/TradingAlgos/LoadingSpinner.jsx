import React from 'react'
import './LoadingSpinner.css'

function LoadingSpinner({ message = 'Loading...', size = 'medium' }) {
  return (
    <div className={`loading-spinner-container ${size}`}>
      <div className="loading-spinner">
        <div className="spinner-ring"></div>
      </div>
      {message && message.trim() !== '' && <span className="loading-message">{message}</span>}
    </div>
  )
}

export default LoadingSpinner








import React from 'react'
import './TimeframeSelector.css'

const TIMEFRAMES = [
  { value: 'day', label: 'Day' },
  { value: 'week', label: 'Week' },
  { value: 'month', label: 'Month' },
  { value: '3m', label: '3M' },
  { value: 'year', label: 'Year' },
  { value: 'ytd', label: 'YTD' },
  { value: 'all', label: 'All Time' }
]

function TimeframeSelector({ timeframe, onChange }) {
  return (
    <div className="timeframe-selector">
      {TIMEFRAMES.map((tf) => (
        <button
          key={tf.value}
          className={`timeframe-btn ${timeframe === tf.value ? 'active' : ''}`}
          onClick={() => onChange(tf.value)}
        >
          {tf.label}
        </button>
      ))}
    </div>
  )
}

export default TimeframeSelector


"""
Hidden Markov Model for market regime identification.

Uses 3-state GaussianHMM to classify market conditions as Bull, Bear, or Sideways.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Tuple, Dict, List
from enum import Enum
import pickle
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler
from hmmlearn.hmm import GaussianHMM

from config import get_config, HMMConfig
from data_provider import get_data_provider
from utils import utc_now

logger = logging.getLogger("tradingbot.regime_hmm")


class MarketRegime(Enum):
    """Market regime classification."""
    BULL = "Bull"
    BEAR = "Bear"
    SIDEWAYS = "Sideways"


class RegimeModel:
    """
    Hidden Markov Model for market regime detection.
    
    Features used:
    - log_return: log(close_t / close_{t-1})
    - rolling_vol_20: 20-day rolling std of log returns
    - rolling_mean_10: 10-day rolling mean of log returns
    
    States are labeled post-training based on mean returns:
    - Bull: highest mean return state
    - Bear: lowest mean return state
    - Sideways: remaining state
    """
    
    def __init__(self, config: Optional[HMMConfig] = None):
        """
        Initialize the regime model.
        
        Args:
            config: HMM configuration.
        """
        self._config = config or get_config().hmm
        self._model: Optional[GaussianHMM] = None
        self._scaler: Optional[StandardScaler] = None
        self._state_labels: Dict[int, MarketRegime] = {}
        self._last_fit_date: Optional[datetime] = None
        self._fit_count: int = 0
        self._model_path = get_config().paths.data_dir / "hmm_model.pkl"
        
    def _compute_features(self, df: pd.DataFrame) -> np.ndarray:
        """
        Compute HMM features from price data.
        
        Args:
            df: DataFrame with 'close' column.
        
        Returns:
            numpy array of features (n_samples, 3).
        """
        close = df['close'].values
        
        # Log returns
        log_returns = np.diff(np.log(close))
        log_returns = np.insert(log_returns, 0, 0)  # Pad first value
        
        # Rolling volatility (20-day)
        rolling_vol = pd.Series(log_returns).rolling(20).std().fillna(0).values
        
        # Rolling mean (10-day)
        rolling_mean = pd.Series(log_returns).rolling(10).mean().fillna(0).values
        
        # Stack features
        features = np.column_stack([log_returns, rolling_vol, rolling_mean])
        
        # Remove initial NaN rows
        valid_start = max(20, 10)  # Start after warmup
        return features[valid_start:]
    
    def _label_states(self, features: np.ndarray, states: np.ndarray) -> None:
        """
        Label HMM states based on mean returns.
        
        Args:
            features: Feature matrix (log_return is first column).
            states: Hidden state sequence.
        """
        # Compute mean return for each state
        state_returns = {}
        for state in range(self._config.n_states):
            mask = states == state
            if mask.sum() > 0:
                state_returns[state] = features[mask, 0].mean()
            else:
                state_returns[state] = 0
        
        # Sort states by return
        sorted_states = sorted(state_returns.items(), key=lambda x: x[1])
        
        # Label states
        self._state_labels = {
            sorted_states[0][0]: MarketRegime.BEAR,      # Lowest return
            sorted_states[-1][0]: MarketRegime.BULL,     # Highest return
        }
        
        # Middle state(s) are sideways
        for state, _ in sorted_states[1:-1]:
            self._state_labels[state] = MarketRegime.SIDEWAYS
        
        # Handle 3-state case
        if self._config.n_states == 3:
            self._state_labels[sorted_states[1][0]] = MarketRegime.SIDEWAYS
        
        logger.info(f"State labels: {self._state_labels}")
        for state, regime in self._state_labels.items():
            logger.info(f"  State {state} ({regime.value}): mean_return={state_returns[state]:.6f}")
    
    def fit(self, df: pd.DataFrame) -> None:
        """
        Fit the HMM model on historical data.
        
        Args:
            df: DataFrame with 'close' column and sufficient history.
        """
        logger.info(f"Fitting HMM on {len(df)} bars")
        
        # Compute features
        features = self._compute_features(df)
        
        if len(features) < 100:
            raise ValueError(f"Insufficient data for HMM fitting: {len(features)} samples")
        
        # Scale features
        self._scaler = StandardScaler()
        features_scaled = self._scaler.fit_transform(features)
        
        # Initialize and fit HMM
        self._model = GaussianHMM(
            n_components=self._config.n_states,
            covariance_type="full",
            n_iter=200,
            random_state=42,
            verbose=False
        )
        
        self._model.fit(features_scaled)
        
        # Get hidden states and label them
        states = self._model.predict(features_scaled)
        self._label_states(features, states)
        
        self._last_fit_date = utc_now()
        self._fit_count += 1
        
        # Save model
        self._save_model()
        
        logger.info(f"HMM fitted successfully (fit #{self._fit_count})")
    
    def predict(self, df: pd.DataFrame) -> Tuple[MarketRegime, Dict[MarketRegime, float]]:
        """
        Predict current market regime.
        
        Uses data through the last bar (no lookahead).
        
        Args:
            df: DataFrame with 'close' column.
        
        Returns:
            Tuple of (regime, probabilities dict).
        """
        if self._model is None or self._scaler is None:
            raise ValueError("Model not fitted. Call fit() first.")
        
        # Compute features
        features = self._compute_features(df)
        
        if len(features) == 0:
            raise ValueError("Insufficient data for prediction")
        
        # Scale
        features_scaled = self._scaler.transform(features)
        
        # Get posterior probabilities for the last observation
        log_prob, posteriors = self._model.score_samples(features_scaled)
        
        # Last observation's posteriors
        last_posteriors = posteriors[-1]
        
        # Map to regime probabilities
        probs = {regime: 0.0 for regime in MarketRegime}
        for state, prob in enumerate(last_posteriors):
            regime = self._state_labels[state]
            probs[regime] = float(prob)
        
        # Predicted regime (highest probability)
        predicted_state = np.argmax(last_posteriors)
        regime = self._state_labels[predicted_state]
        
        return regime, probs
    
    def get_regime_with_confidence(
        self,
        df: pd.DataFrame
    ) -> Tuple[MarketRegime, float, float, float]:
        """
        Get regime with all probabilities.
        
        Args:
            df: DataFrame with 'close' column.
        
        Returns:
            Tuple of (regime, bull_prob, bear_prob, side_prob).
            Note: bull_prob + bear_prob + side_prob ≈ 1.0 (rounding allowed)
        """
        regime, probs = self.predict(df)
        bull_prob = probs[MarketRegime.BULL]
        bear_prob = probs[MarketRegime.BEAR]
        side_prob = probs[MarketRegime.SIDEWAYS]
        
        return regime, bull_prob, bear_prob, side_prob
    
    def needs_refit(self) -> bool:
        """
        Check if model needs refitting.
        
        Returns:
            bool: True if refit needed.
        """
        if self._model is None or self._last_fit_date is None:
            return True
        
        days_since_fit = (utc_now() - self._last_fit_date).days
        return days_since_fit >= self._config.refit_days
    
    def _save_model(self) -> None:
        """Save model to disk."""
        try:
            data = {
                'model': self._model,
                'scaler': self._scaler,
                'state_labels': self._state_labels,
                'last_fit_date': self._last_fit_date,
                'fit_count': self._fit_count
            }
            with open(self._model_path, 'wb') as f:
                pickle.dump(data, f)
            logger.debug("Saved HMM model to disk")
        except Exception as e:
            logger.warning(f"Failed to save HMM model: {e}")
    
    def load_model(self) -> bool:
        """
        Load model from disk.
        
        Returns:
            bool: True if loaded successfully.
        """
        if not self._model_path.exists():
            return False
        
        try:
            with open(self._model_path, 'rb') as f:
                data = pickle.load(f)
            
            self._model = data['model']
            self._scaler = data['scaler']
            self._state_labels = data['state_labels']
            self._last_fit_date = data['last_fit_date']
            self._fit_count = data['fit_count']
            
            logger.info(f"Loaded HMM model (fit #{self._fit_count}, last fit: {self._last_fit_date})")
            return True
            
        except Exception as e:
            logger.warning(f"Failed to load HMM model: {e}")
            return False


class RegimeDetector:
    """
    High-level regime detection with automatic bootstrap training.
    
    Ensures day-1 trading capability by training on historical data.
    """
    
    def __init__(self, config: Optional[HMMConfig] = None):
        """
        Initialize the regime detector.
        
        Args:
            config: HMM configuration.
        """
        self._config = config or get_config().hmm
        self._model = RegimeModel(self._config)
        self._initialized = False
        self._proxy_data: Optional[pd.DataFrame] = None
        
    def initialize(self) -> None:
        """
        Initialize regime detection (bootstrap training).
        
        Loads cached model or trains fresh on historical SPY data.
        Always fetches proxy data for regime inference.
        """
        if self._initialized:
            return
        
        logger.info("Initializing regime detector")
        
        # Always fetch proxy data (needed for regime inference)
        logger.info(f"Fetching {self._config.lookback_years} years of {self._config.market_proxy} data")
        provider = get_data_provider()
        self._proxy_data = provider.get_market_proxy_history(
            proxy=self._config.market_proxy,
            years=self._config.lookback_years
        )
        
        if self._proxy_data.empty or len(self._proxy_data) < 252:
            raise ValueError(f"Insufficient {self._config.market_proxy} data for HMM training")
        
        # Try to load cached model
        if self._model.load_model() and not self._model.needs_refit():
            logger.info("Using cached HMM model")
            self._initialized = True
            return
        
        # Train model (no cached model or needs refit)
        self._model.fit(self._proxy_data)
        self._initialized = True
    
    def get_current_regime(
        self,
        as_of_date: Optional[datetime] = None,
        proxy_data: Optional[pd.DataFrame] = None
    ) -> Tuple[MarketRegime, float, float, float]:
        """
        Get current market regime.
        
        Args:
            as_of_date: Date to evaluate regime as of (for backtesting).
                        Only data BEFORE this date will be used (no lookahead).
            proxy_data: Optional updated proxy data.
        
        Returns:
            Tuple of (regime, bull_prob, bear_prob, side_prob).
            Note: bull + bear + side ≈ 1.0 (rounding allowed)
        """
        if not self._initialized:
            self.initialize()
        
        if proxy_data is not None:
            self._proxy_data = proxy_data
        
        if self._proxy_data is None or self._proxy_data.empty:
            raise ValueError("No proxy data available")
        
        # Filter data to avoid lookahead bias
        if as_of_date is not None:
            # Ensure timezone-aware comparison
            if as_of_date.tzinfo is None:
                from datetime import timezone
                as_of_date = as_of_date.replace(tzinfo=timezone.utc)
            
            # Make sure proxy data timestamps are comparable
            proxy_ts = pd.to_datetime(self._proxy_data['timestamp'])
            if proxy_ts.dt.tz is None:
                proxy_ts = proxy_ts.dt.tz_localize('UTC')
            
            # Use only data up to (but not including) as_of_date
            # This ensures we're using t-1 close for day t decision
            mask = proxy_ts < as_of_date
            data_for_regime = self._proxy_data[mask].copy()
            
            if data_for_regime.empty or len(data_for_regime) < 50:
                # Fallback to sideways if insufficient data
                logger.warning(f"Insufficient data for regime detection as of {as_of_date}")
                return MarketRegime.SIDEWAYS, 0.33, 0.33, 0.34
        else:
            data_for_regime = self._proxy_data
        
        # Check if refit needed (only for live trading, not backtest)
        if as_of_date is None and self._model.needs_refit():
            logger.info("Refitting HMM model (periodic refit)")
            
            if self._config.use_rolling_window:
                # Use rolling window
                window_data = self._proxy_data.tail(self._config.rolling_window_days)
            else:
                # Use expanding window (all data)
                window_data = self._proxy_data
            
            self._model.fit(window_data)
        
        return self._model.get_regime_with_confidence(data_for_regime)
    
    def update_proxy_data(self, new_data: pd.DataFrame) -> None:
        """
        Update proxy data with new bars.
        
        Args:
            new_data: New proxy bar data.
        """
        if self._proxy_data is None:
            self._proxy_data = new_data
        else:
            # Merge and deduplicate
            combined = pd.concat([self._proxy_data, new_data])
            combined = combined.drop_duplicates(subset=['timestamp'], keep='last')
            combined = combined.sort_values('timestamp').reset_index(drop=True)
            self._proxy_data = combined
    
    def can_trade_long(self, bull_prob: Optional[float] = None) -> bool:
        """
        Check if long entries are allowed.
        
        Args:
            bull_prob: Bull probability (fetches if not provided).
        
        Returns:
            bool: True if long entries allowed.
        """
        if bull_prob is None:
            regime, bull_prob, _, _ = self.get_current_regime()
        return bull_prob >= self._config.bull_prob_threshold
    
    def can_trade_short(self, bear_prob: Optional[float] = None) -> bool:
        """
        Check if short entries are allowed.
        
        Args:
            bear_prob: Bear probability (fetches if not provided).
        
        Returns:
            bool: True if short entries allowed.
        """
        if bear_prob is None:
            regime, _, bear_prob, _ = self.get_current_regime()
        return bear_prob >= self._config.bear_prob_threshold


# Global detector instance
_detector: Optional[RegimeDetector] = None


def get_regime_detector() -> RegimeDetector:
    """
    Get or create the global regime detector.
    
    Returns:
        RegimeDetector: Global detector instance.
    """
    global _detector
    if _detector is None:
        _detector = RegimeDetector()
    return _detector


def get_current_regime() -> Tuple[MarketRegime, float, float, float]:
    """
    Convenience function to get current regime.
    
    Returns:
        Tuple of (regime, bull_prob, bear_prob, side_prob).
    """
    detector = get_regime_detector()
    detector.initialize()
    return detector.get_current_regime()


"""
Trading strategy module.

Combines regime detection, technical indicators, and sentiment for trade signals.
"""

import logging
from datetime import datetime
from typing import Optional, Dict, List, Tuple, Any
from dataclasses import dataclass
from enum import Enum

import pandas as pd

from config import get_config
from regime_hmm import get_regime_detector, MarketRegime
from indicators import TechnicalIndicators, get_entry_signals
from sentiment import get_sentiment_analyzer, confirm_sentiment
from utils import get_logger

logger = get_logger("strategy")


class SignalType(Enum):
    """Trading signal type."""
    LONG = "long"
    SHORT = "short"
    NONE = "none"


@dataclass
class TradeSignal:
    """
    Represents a trade signal with full context.
    """
    symbol: str
    signal_type: SignalType
    date: datetime
    
    # Regime info
    regime: MarketRegime
    bull_prob: float
    bear_prob: float
    regime_passed: bool
    
    # Technical info
    rsi: Optional[float]
    macd: Optional[float]
    atr: Optional[float]
    technical_passed: bool
    
    # Sentiment info
    sentiment_score: float
    sentiment_passed: bool
    sentiment_reason: str
    
    # Final decision
    should_trade: bool
    reject_reason: Optional[str] = None
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            'symbol': self.symbol,
            'signal_type': self.signal_type.value,
            'date': self.date.isoformat(),
            'regime': self.regime.value,
            'bull_prob': self.bull_prob,
            'bear_prob': self.bear_prob,
            'regime_passed': self.regime_passed,
            'rsi': self.rsi,
            'macd': self.macd,
            'atr': self.atr,
            'technical_passed': self.technical_passed,
            'sentiment_score': self.sentiment_score,
            'sentiment_passed': self.sentiment_passed,
            'sentiment_reason': self.sentiment_reason,
            'should_trade': self.should_trade,
            'reject_reason': self.reject_reason
        }


class TradingStrategy:
    """
    Main trading strategy combining all signal sources.
    
    Entry rules:
    - LONG: Bull regime (prob >= threshold) + RSI < oversold + bullish MACD cross + positive sentiment
    - SHORT: Bear regime (prob >= threshold) + RSI > overbought + bearish MACD cross + negative sentiment
    - SIDEWAYS: No new entries
    
    All signals are computed using data through t-1 close for trading at t open.
    """
    
    def __init__(self):
        """Initialize the trading strategy."""
        self._config = get_config()
        self._regime_detector = get_regime_detector()
        self._sentiment_analyzer = get_sentiment_analyzer()
        self._indicators = TechnicalIndicators()
        
    def initialize(self) -> None:
        """Initialize strategy components (HMM bootstrap, etc.)."""
        logger.info("Initializing trading strategy")
        self._regime_detector.initialize()
        logger.info("Strategy initialization complete")
    
    def _check_regime(
        self,
        signal_type: SignalType
    ) -> Tuple[bool, MarketRegime, float, float, str]:
        """
        Check if regime allows the trade.
        
        Args:
            signal_type: Proposed signal type.
        
        Returns:
            Tuple of (passed, regime, bull_prob, bear_prob, reason).
        """
        regime, bull_prob, bear_prob = self._regime_detector.get_current_regime()
        
        if signal_type == SignalType.LONG:
            if regime == MarketRegime.BULL and bull_prob >= self._config.hmm.bull_prob_threshold:
                return True, regime, bull_prob, bear_prob, "Bull regime confirmed"
            elif regime == MarketRegime.SIDEWAYS:
                return False, regime, bull_prob, bear_prob, "No entries in Sideways regime"
            else:
                return False, regime, bull_prob, bear_prob, f"Bull prob ({bull_prob:.2f}) below threshold"
        
        elif signal_type == SignalType.SHORT:
            if regime == MarketRegime.BEAR and bear_prob >= self._config.hmm.bear_prob_threshold:
                return True, regime, bull_prob, bear_prob, "Bear regime confirmed"
            elif regime == MarketRegime.SIDEWAYS:
                return False, regime, bull_prob, bear_prob, "No entries in Sideways regime"
            else:
                return False, regime, bull_prob, bear_prob, f"Bear prob ({bear_prob:.2f}) below threshold"
        
        return False, regime, bull_prob, bear_prob, "No signal"
    
    def _check_technical(
        self,
        df: pd.DataFrame
    ) -> Tuple[bool, bool, dict]:
        """
        Check technical signals.
        
        Args:
            df: OHLCV DataFrame.
        
        Returns:
            Tuple of (long_signal, short_signal, indicator_values).
        """
        indicators_df = self._indicators.calculate(df)
        signals = self._indicators.get_latest_signals()
        
        return signals['long_technical'], signals['short_technical'], signals
    
    def _check_sentiment(
        self,
        symbol: str,
        date: datetime,
        side: str
    ) -> Tuple[bool, float, str]:
        """
        Check sentiment confirmation.
        
        Args:
            symbol: Stock ticker.
            date: Trade date.
            side: "long" or "short".
        
        Returns:
            Tuple of (passed, score, reason).
        """
        # Skip sentiment entirely if configured (for faster backtesting)
        if self._config.sentiment.skip_sentiment:
            return True, 0.5, "Sentiment check skipped (SKIP_SENTIMENT=true)"
        
        # Check if news exists
        if not self._sentiment_analyzer.has_news_coverage(symbol, date):
            # If configured to skip sentiment when no news, allow the trade
            if self._config.sentiment.skip_when_no_news:
                return True, 0.5, "No news available - sentiment check skipped"
            return False, 0.0, "No news available for sentiment confirmation"
        
        return self._sentiment_analyzer.check_sentiment_confirmation(symbol, date, side)
    
    def generate_signal(
        self,
        symbol: str,
        df: pd.DataFrame,
        date: datetime
    ) -> TradeSignal:
        """
        Generate trade signal for a symbol.
        
        Args:
            symbol: Stock ticker symbol.
            df: OHLCV DataFrame (data through t-1 close).
            date: Trade date (day t).
        
        Returns:
            TradeSignal with full analysis.
        """
        # Get technical signals
        long_tech, short_tech, tech_values = self._check_technical(df)
        
        # Determine proposed signal type
        if long_tech:
            proposed = SignalType.LONG
        elif short_tech:
            proposed = SignalType.SHORT
        else:
            proposed = SignalType.NONE
        
        # No technical trigger
        if proposed == SignalType.NONE:
            regime, bull_prob, bear_prob = self._regime_detector.get_current_regime()
            return TradeSignal(
                symbol=symbol,
                signal_type=SignalType.NONE,
                date=date,
                regime=regime,
                bull_prob=bull_prob,
                bear_prob=bear_prob,
                regime_passed=False,
                rsi=tech_values['rsi'],
                macd=tech_values['macd'],
                atr=tech_values['atr'],
                technical_passed=False,
                sentiment_score=0.0,
                sentiment_passed=False,
                sentiment_reason="No technical trigger",
                should_trade=False,
                reject_reason="No technical signal"
            )
        
        # Check regime
        regime_passed, regime, bull_prob, bear_prob, regime_reason = self._check_regime(proposed)
        
        if not regime_passed:
            return TradeSignal(
                symbol=symbol,
                signal_type=proposed,
                date=date,
                regime=regime,
                bull_prob=bull_prob,
                bear_prob=bear_prob,
                regime_passed=False,
                rsi=tech_values['rsi'],
                macd=tech_values['macd'],
                atr=tech_values['atr'],
                technical_passed=True,
                sentiment_score=0.0,
                sentiment_passed=False,
                sentiment_reason="Regime check failed, sentiment not checked",
                should_trade=False,
                reject_reason=regime_reason
            )
        
        # Check sentiment
        side = "long" if proposed == SignalType.LONG else "short"
        sentiment_passed, sentiment_score, sentiment_reason = self._check_sentiment(symbol, date, side)
        
        if not sentiment_passed:
            return TradeSignal(
                symbol=symbol,
                signal_type=proposed,
                date=date,
                regime=regime,
                bull_prob=bull_prob,
                bear_prob=bear_prob,
                regime_passed=True,
                rsi=tech_values['rsi'],
                macd=tech_values['macd'],
                atr=tech_values['atr'],
                technical_passed=True,
                sentiment_score=sentiment_score,
                sentiment_passed=False,
                sentiment_reason=sentiment_reason,
                should_trade=False,
                reject_reason=sentiment_reason
            )
        
        # All checks passed
        return TradeSignal(
            symbol=symbol,
            signal_type=proposed,
            date=date,
            regime=regime,
            bull_prob=bull_prob,
            bear_prob=bear_prob,
            regime_passed=True,
            rsi=tech_values['rsi'],
            macd=tech_values['macd'],
            atr=tech_values['atr'],
            technical_passed=True,
            sentiment_score=sentiment_score,
            sentiment_passed=True,
            sentiment_reason=sentiment_reason,
            should_trade=True
        )
    
    def scan_universe(
        self,
        symbol_data: Dict[str, pd.DataFrame],
        date: datetime
    ) -> List[TradeSignal]:
        """
        Scan universe for trade signals.
        
        Args:
            symbol_data: Dict mapping symbol to OHLCV DataFrame.
            date: Trade date.
        
        Returns:
            List of TradeSignal for all symbols.
        """
        signals: List[TradeSignal] = []
        
        for symbol, df in symbol_data.items():
            if df is None or df.empty or len(df) < 30:
                logger.debug(f"Skipping {symbol}: insufficient data")
                continue
            
            try:
                signal = self.generate_signal(symbol, df, date)
                signals.append(signal)
                
                if signal.should_trade:
                    logger.info(
                        f"SIGNAL: {symbol} {signal.signal_type.value.upper()} | "
                        f"Regime={signal.regime.value} (bull={signal.bull_prob:.2f}, bear={signal.bear_prob:.2f}) | "
                        f"RSI={signal.rsi:.1f} | Sentiment={signal.sentiment_score:.2f}"
                    )
                    
            except Exception as e:
                logger.error(f"Error generating signal for {symbol}: {e}")
                continue
        
        return signals
    
    def get_actionable_signals(
        self,
        symbol_data: Dict[str, pd.DataFrame],
        date: datetime
    ) -> List[TradeSignal]:
        """
        Get only actionable (should_trade=True) signals.
        
        Args:
            symbol_data: Dict mapping symbol to OHLCV DataFrame.
            date: Trade date.
        
        Returns:
            List of actionable TradeSignal objects.
        """
        all_signals = self.scan_universe(symbol_data, date)
        return [s for s in all_signals if s.should_trade]


# Global strategy instance
_strategy: Optional[TradingStrategy] = None


def get_strategy() -> TradingStrategy:
    """
    Get or create the global trading strategy.
    
    Returns:
        TradingStrategy: Global strategy instance.
    """
    global _strategy
    if _strategy is None:
        _strategy = TradingStrategy()
    return _strategy


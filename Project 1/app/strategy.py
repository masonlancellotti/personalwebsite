"""
Trading strategy module.

Combines regime detection, technical indicators, trend filter, and sentiment for trade signals.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple, Any
from dataclasses import dataclass
from enum import Enum

import pandas as pd

from config import get_config
from regime_hmm import get_regime_detector, MarketRegime
from indicators import TechnicalIndicators, get_entry_signals
from sentiment import get_sentiment_analyzer, SentimentScore
from news_provider import get_news_provider
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
    side_prob: float
    regime_passed: bool
    
    # Technical info
    rsi: Optional[float]
    macd: Optional[float]
    atr: Optional[float]
    sma_fast: Optional[float]
    sma_slow: Optional[float]
    close: Optional[float]
    technical_passed: bool
    trend_passed: bool
    
    # Sentiment info
    sentiment: Optional[SentimentScore]
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
            'side_prob': self.side_prob,
            'regime_passed': self.regime_passed,
            'rsi': self.rsi,
            'macd': self.macd,
            'atr': self.atr,
            'sma_fast': self.sma_fast,
            'sma_slow': self.sma_slow,
            'close': self.close,
            'technical_passed': self.technical_passed,
            'trend_passed': self.trend_passed,
            'sentiment_pos': self.sentiment.positive if self.sentiment else None,
            'sentiment_neg': self.sentiment.negative if self.sentiment else None,
            'sentiment_n': self.sentiment.n if self.sentiment else 0,
            'sentiment_passed': self.sentiment_passed,
            'sentiment_reason': self.sentiment_reason,
            'should_trade': self.should_trade,
            'reject_reason': self.reject_reason
        }
    
    @property
    def sentiment_str(self) -> str:
        """Get sentiment as formatted string for logging."""
        if self.sentiment is None:
            return "None"
        return f"pos={self.sentiment.positive:.2f} neg={self.sentiment.negative:.2f} n={self.sentiment.n}"


class TradingStrategy:
    """
    Main trading strategy combining all signal sources.
    
    Entry rules:
    - LONG: Bull regime + RSI < oversold + bullish MACD cross + trend filter + sentiment
    - SHORT: Bear regime + RSI > overbought + bearish MACD cross + trend filter + sentiment
    - SIDEWAYS: No new entries
    
    Trend Filter (if enabled):
    - LONG: close > SMA200 AND SMA50 >= SMA200
    - SHORT: close < SMA200 AND SMA50 <= SMA200
    
    Sentiment Modes:
    - "off": Skip sentiment entirely
    - "strict": Require positive (long) or negative (short) above threshold
    - "soft": Allow trade if no news, but block on strong opposite sentiment
    
    All signals are computed using data through t-1 close for trading at t open.
    """
    
    def __init__(self):
        """Initialize the trading strategy."""
        self._config = get_config()
        self._regime_detector = get_regime_detector()
        self._sentiment_analyzer = get_sentiment_analyzer()
        self._news_provider = get_news_provider()
        self._indicators = TechnicalIndicators()
        
        # Cooldown tracking: symbol -> last hard stop date
        self._cooldown_map: Dict[str, datetime] = {}
        
    def initialize(self) -> None:
        """Initialize strategy components (HMM bootstrap, etc.)."""
        logger.info("Initializing trading strategy")
        self._regime_detector.initialize()
        logger.info("Strategy initialization complete")
    
    def set_hard_stop_cooldown(self, symbol: str, date: datetime) -> None:
        """
        Record a hard stop for cooldown tracking.
        
        Args:
            symbol: Stock ticker.
            date: Date of hard stop.
        """
        self._cooldown_map[symbol] = date
        logger.debug(f"Cooldown set for {symbol} until {date + timedelta(days=self._config.risk.cooldown_days_after_hard_stop)}")
    
    def _is_in_cooldown(self, symbol: str, date: datetime) -> bool:
        """
        Check if symbol is in cooldown period after hard stop.
        
        Args:
            symbol: Stock ticker.
            date: Current date.
        
        Returns:
            bool: True if in cooldown.
        """
        if symbol not in self._cooldown_map:
            return False
        
        last_stop = self._cooldown_map[symbol]
        cooldown_end = last_stop + timedelta(days=self._config.risk.cooldown_days_after_hard_stop)
        
        return date < cooldown_end
    
    def _check_regime(
        self,
        signal_type: SignalType,
        as_of_date: Optional[datetime] = None
    ) -> Tuple[bool, MarketRegime, float, float, float, str]:
        """
        Check if regime allows the trade.
        
        Args:
            signal_type: Proposed signal type.
            as_of_date: Date for regime evaluation (for backtesting).
        
        Returns:
            Tuple of (passed, regime, bull_prob, bear_prob, side_prob, reason).
        """
        regime, bull_prob, bear_prob, side_prob = self._regime_detector.get_current_regime(as_of_date=as_of_date)
        
        if signal_type == SignalType.LONG:
            if regime == MarketRegime.BULL and bull_prob >= self._config.hmm.bull_prob_threshold:
                return True, regime, bull_prob, bear_prob, side_prob, "Bull regime confirmed"
            elif regime == MarketRegime.SIDEWAYS:
                return False, regime, bull_prob, bear_prob, side_prob, "No entries in Sideways regime"
            else:
                return False, regime, bull_prob, bear_prob, side_prob, f"Bull prob ({bull_prob:.2f}) below threshold"
        
        elif signal_type == SignalType.SHORT:
            if regime == MarketRegime.BEAR and bear_prob >= self._config.hmm.bear_prob_threshold:
                return True, regime, bull_prob, bear_prob, side_prob, "Bear regime confirmed"
            elif regime == MarketRegime.SIDEWAYS:
                return False, regime, bull_prob, bear_prob, side_prob, "No entries in Sideways regime"
            else:
                return False, regime, bull_prob, bear_prob, side_prob, f"Bear prob ({bear_prob:.2f}) below threshold"
        
        return False, regime, bull_prob, bear_prob, side_prob, "No signal"
    
    def _check_trend_filter(
        self,
        signal_type: SignalType,
        close: Optional[float],
        sma_fast: Optional[float],
        sma_slow: Optional[float]
    ) -> Tuple[bool, str]:
        """
        Check trend filter.
        
        Args:
            signal_type: Proposed signal type.
            close: Last close price.
            sma_fast: Fast SMA (e.g., 50).
            sma_slow: Slow SMA (e.g., 200).
        
        Returns:
            Tuple of (passed, reason).
        """
        if not self._config.indicators.trend_filter_enabled:
            return True, "Trend filter disabled"
        
        if close is None or sma_fast is None or sma_slow is None:
            return False, "SMAs not available (insufficient data)"
        
        if signal_type == SignalType.LONG:
            # Long: close > SMA200 AND SMA50 >= SMA200
            if close > sma_slow and sma_fast >= sma_slow:
                return True, "Uptrend confirmed"
            else:
                return False, f"Trend filter failed: close={close:.2f}, SMA50={sma_fast:.2f}, SMA200={sma_slow:.2f}"
        
        elif signal_type == SignalType.SHORT:
            # Short: close < SMA200 AND SMA50 <= SMA200
            if close < sma_slow and sma_fast <= sma_slow:
                return True, "Downtrend confirmed"
            else:
                return False, f"Trend filter failed: close={close:.2f}, SMA50={sma_fast:.2f}, SMA200={sma_slow:.2f}"
        
        return True, "No filter applied"
    
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
    ) -> Tuple[bool, Optional[SentimentScore], str]:
        """
        Check sentiment confirmation using configured mode.
        
        Args:
            symbol: Stock ticker.
            date: Trade date.
            side: "long" or "short".
        
        Returns:
            Tuple of (passed, sentiment_score, reason).
        """
        mode = self._config.sentiment.mode
        
        # Mode: OFF - skip sentiment entirely
        if mode == "off":
            return True, None, "Sentiment=OFF"
        
        # Get news and sentiment
        lookback = self._config.sentiment.lookback_days
        end_dt = date
        start_dt = date - timedelta(days=lookback)
        
        articles = self._news_provider.get_news_window(symbol, start_dt, end_dt)
        
        if not articles:
            sentiment = None
        else:
            sentiment = self._sentiment_analyzer.score_articles(articles)
        
        # Mode: STRICT - require sentiment confirmation
        if mode == "strict":
            if sentiment is None or sentiment.n < self._config.sentiment.min_articles:
                return False, sentiment, "strict: sentiment missing or too few articles"
            
            if side == "long":
                if sentiment.positive >= self._config.sentiment.strict_long_pos:
                    return True, sentiment, f"strict: positive ({sentiment.positive:.2f}) confirmed"
                else:
                    return False, sentiment, f"strict: positive ({sentiment.positive:.2f}) below threshold ({self._config.sentiment.strict_long_pos})"
            else:
                if sentiment.negative >= self._config.sentiment.strict_short_neg:
                    return True, sentiment, f"strict: negative ({sentiment.negative:.2f}) confirmed"
                else:
                    return False, sentiment, f"strict: negative ({sentiment.negative:.2f}) below threshold ({self._config.sentiment.strict_short_neg})"
        
        # Mode: SOFT (default) - allow if no news, but check for opposite sentiment
        if mode == "soft":
            if sentiment is None or sentiment.n < self._config.sentiment.min_articles:
                return True, None, "Sentiment=None -> soft mode allows trade"
            
            if side == "long":
                # Long requires: positive >= soft_min_confirm AND negative <= soft_max_opposite
                if sentiment.positive >= self._config.sentiment.soft_min_confirm and \
                   sentiment.negative <= self._config.sentiment.soft_max_opposite:
                    return True, sentiment, f"soft: sentiment ok (pos={sentiment.positive:.2f}, neg={sentiment.negative:.2f})"
                else:
                    return False, sentiment, f"soft: opposite sentiment too high (pos={sentiment.positive:.2f}, neg={sentiment.negative:.2f})"
            else:
                # Short requires: negative >= soft_min_confirm AND positive <= soft_max_opposite
                if sentiment.negative >= self._config.sentiment.soft_min_confirm and \
                   sentiment.positive <= self._config.sentiment.soft_max_opposite:
                    return True, sentiment, f"soft: sentiment ok (pos={sentiment.positive:.2f}, neg={sentiment.negative:.2f})"
                else:
                    return False, sentiment, f"soft: opposite sentiment too high (pos={sentiment.positive:.2f}, neg={sentiment.negative:.2f})"
        
        # Unknown mode - default to allow
        return True, sentiment, f"Unknown sentiment mode: {mode}"
    
    def generate_signal(
        self,
        symbol: str,
        df: pd.DataFrame,
        date: datetime,
        check_sentiment: bool = True
    ) -> TradeSignal:
        """
        Generate trade signal for a symbol.
        
        Args:
            symbol: Stock ticker symbol.
            df: OHLCV DataFrame (data through t-1 close).
            date: Trade date (day t).
            check_sentiment: Whether to check sentiment (can skip for pre-filter).
        
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
        
        # Get regime info (always needed for reporting)
        regime, bull_prob, bear_prob, side_prob = self._regime_detector.get_current_regime(as_of_date=date)
        
        # Base signal for no technical trigger
        if proposed == SignalType.NONE:
            return TradeSignal(
                symbol=symbol,
                signal_type=SignalType.NONE,
                date=date,
                regime=regime,
                bull_prob=bull_prob,
                bear_prob=bear_prob,
                side_prob=side_prob,
                regime_passed=False,
                rsi=tech_values['rsi'],
                macd=tech_values['macd'],
                atr=tech_values['atr'],
                sma_fast=tech_values.get('sma_fast'),
                sma_slow=tech_values.get('sma_slow'),
                close=tech_values.get('close'),
                technical_passed=False,
                trend_passed=False,
                sentiment=None,
                sentiment_passed=False,
                sentiment_reason="No technical trigger",
                should_trade=False,
                reject_reason="No technical signal"
            )
        
        # Check cooldown
        if self._is_in_cooldown(symbol, date):
            return TradeSignal(
                symbol=symbol,
                signal_type=proposed,
                date=date,
                regime=regime,
                bull_prob=bull_prob,
                bear_prob=bear_prob,
                side_prob=side_prob,
                regime_passed=False,
                rsi=tech_values['rsi'],
                macd=tech_values['macd'],
                atr=tech_values['atr'],
                sma_fast=tech_values.get('sma_fast'),
                sma_slow=tech_values.get('sma_slow'),
                close=tech_values.get('close'),
                technical_passed=True,
                trend_passed=False,
                sentiment=None,
                sentiment_passed=False,
                sentiment_reason="Cooldown active",
                should_trade=False,
                reject_reason="SKIP: cooldown active after hard stop"
            )
        
        # Check regime
        regime_passed, regime, bull_prob, bear_prob, side_prob, regime_reason = self._check_regime(proposed, as_of_date=date)
        
        if not regime_passed:
            return TradeSignal(
                symbol=symbol,
                signal_type=proposed,
                date=date,
                regime=regime,
                bull_prob=bull_prob,
                bear_prob=bear_prob,
                side_prob=side_prob,
                regime_passed=False,
                rsi=tech_values['rsi'],
                macd=tech_values['macd'],
                atr=tech_values['atr'],
                sma_fast=tech_values.get('sma_fast'),
                sma_slow=tech_values.get('sma_slow'),
                close=tech_values.get('close'),
                technical_passed=True,
                trend_passed=False,
                sentiment=None,
                sentiment_passed=False,
                sentiment_reason="Regime check failed",
                should_trade=False,
                reject_reason=regime_reason
            )
        
        # Check trend filter
        trend_passed, trend_reason = self._check_trend_filter(
            proposed,
            tech_values.get('close'),
            tech_values.get('sma_fast'),
            tech_values.get('sma_slow')
        )
        
        if not trend_passed:
            return TradeSignal(
                symbol=symbol,
                signal_type=proposed,
                date=date,
                regime=regime,
                bull_prob=bull_prob,
                bear_prob=bear_prob,
                side_prob=side_prob,
                regime_passed=True,
                rsi=tech_values['rsi'],
                macd=tech_values['macd'],
                atr=tech_values['atr'],
                sma_fast=tech_values.get('sma_fast'),
                sma_slow=tech_values.get('sma_slow'),
                close=tech_values.get('close'),
                technical_passed=True,
                trend_passed=False,
                sentiment=None,
                sentiment_passed=False,
                sentiment_reason="Trend filter failed",
                should_trade=False,
                reject_reason=f"SKIP: {trend_reason}"
            )
        
        # Check sentiment (can be skipped for pre-filtering)
        if check_sentiment:
            side = "long" if proposed == SignalType.LONG else "short"
            sentiment_passed, sentiment, sentiment_reason = self._check_sentiment(symbol, date, side)
        else:
            sentiment_passed = True
            sentiment = None
            sentiment_reason = "Sentiment check skipped (pre-filter)"
        
        if not sentiment_passed:
            return TradeSignal(
                symbol=symbol,
                signal_type=proposed,
                date=date,
                regime=regime,
                bull_prob=bull_prob,
                bear_prob=bear_prob,
                side_prob=side_prob,
                regime_passed=True,
                rsi=tech_values['rsi'],
                macd=tech_values['macd'],
                atr=tech_values['atr'],
                sma_fast=tech_values.get('sma_fast'),
                sma_slow=tech_values.get('sma_slow'),
                close=tech_values.get('close'),
                technical_passed=True,
                trend_passed=True,
                sentiment=sentiment,
                sentiment_passed=False,
                sentiment_reason=sentiment_reason,
                should_trade=False,
                reject_reason=f"SKIP: {sentiment_reason}"
            )
        
        # All checks passed
        return TradeSignal(
            symbol=symbol,
            signal_type=proposed,
            date=date,
            regime=regime,
            bull_prob=bull_prob,
            bear_prob=bear_prob,
            side_prob=side_prob,
            regime_passed=True,
            rsi=tech_values['rsi'],
            macd=tech_values['macd'],
            atr=tech_values['atr'],
            sma_fast=tech_values.get('sma_fast'),
            sma_slow=tech_values.get('sma_slow'),
            close=tech_values.get('close'),
            technical_passed=True,
            trend_passed=True,
            sentiment=sentiment,
            sentiment_passed=True,
            sentiment_reason=sentiment_reason,
            should_trade=True
        )
    
    def scan_universe(
        self,
        symbol_data: Dict[str, pd.DataFrame],
        date: datetime,
        pre_filter_sentiment: bool = False
    ) -> List[TradeSignal]:
        """
        Scan universe for trade signals.
        
        Args:
            symbol_data: Dict mapping symbol to OHLCV DataFrame.
            date: Trade date.
            pre_filter_sentiment: If True, only fetch sentiment for candidates that pass
                                  regime + technical + trend filters (more efficient for backtest).
        
        Returns:
            List of TradeSignal for all symbols.
        """
        signals: List[TradeSignal] = []
        
        for symbol, df in symbol_data.items():
            if df is None or df.empty or len(df) < 30:
                logger.debug(f"Skipping {symbol}: insufficient data")
                continue
            
            try:
                # First pass: check everything except sentiment if pre_filter_sentiment
                signal = self.generate_signal(symbol, df, date, check_sentiment=not pre_filter_sentiment)
                
                # If pre-filtering and passed all non-sentiment checks, now check sentiment
                if pre_filter_sentiment and signal.should_trade:
                    signal = self.generate_signal(symbol, df, date, check_sentiment=True)
                
                signals.append(signal)
                
                if signal.should_trade:
                    logger.info(
                        f"SIGNAL: {symbol} {signal.signal_type.value.upper()} | "
                        f"Regime={signal.regime.value} (bull={signal.bull_prob:.2f}, bear={signal.bear_prob:.2f}, side={signal.side_prob:.2f}) | "
                        f"RSI={signal.rsi:.1f if signal.rsi else 0} | "
                        f"Sentiment={signal.sentiment_str}"
                    )
                    
            except Exception as e:
                logger.error(f"Error generating signal for {symbol}: {e}")
                continue
        
        return signals
    
    def get_actionable_signals(
        self,
        symbol_data: Dict[str, pd.DataFrame],
        date: datetime,
        pre_filter_sentiment: bool = False
    ) -> List[TradeSignal]:
        """
        Get only actionable (should_trade=True) signals.
        
        Args:
            symbol_data: Dict mapping symbol to OHLCV DataFrame.
            date: Trade date.
            pre_filter_sentiment: If True, optimize by checking sentiment only for candidates.
        
        Returns:
            List of actionable TradeSignal objects.
        """
        all_signals = self.scan_universe(symbol_data, date, pre_filter_sentiment)
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

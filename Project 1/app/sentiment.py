"""
Sentiment analysis module using FinBERT.

Scores news article sentiment and caches results for efficiency.
"""

import logging
from datetime import datetime
from typing import Optional, Dict, List, Tuple
from pathlib import Path

import pandas as pd
import numpy as np

from config import get_config, SentimentConfig
from news_provider import get_news_provider, NewsArticle
from utils import hash_text

logger = logging.getLogger("tradingbot.sentiment")


class SentimentAnalyzer:
    """
    FinBERT-based sentiment analyzer with caching.
    
    Uses HuggingFace transformers to score financial news sentiment.
    """
    
    def __init__(self, config: Optional[SentimentConfig] = None):
        """
        Initialize the sentiment analyzer.
        
        Args:
            config: Sentiment configuration.
        """
        self._config = config or get_config().sentiment
        self._pipeline = None
        self._cache: Dict[str, Dict[str, float]] = {}
        self._cache_path = get_config().paths.data_dir / self._config.cache_file
        self._load_cache()
        
    def _load_cache(self) -> None:
        """Load sentiment cache from disk."""
        if self._cache_path.exists():
            try:
                df = pd.read_parquet(self._cache_path)
                for _, row in df.iterrows():
                    self._cache[row['text_hash']] = {
                        'positive': row['positive'],
                        'negative': row['negative'],
                        'neutral': row['neutral']
                    }
                logger.info(f"Loaded {len(self._cache)} cached sentiment scores")
            except Exception as e:
                logger.warning(f"Failed to load sentiment cache: {e}")
    
    def _save_cache(self) -> None:
        """Save sentiment cache to disk."""
        try:
            records = [
                {'text_hash': k, **v}
                for k, v in self._cache.items()
            ]
            df = pd.DataFrame(records)
            df.to_parquet(self._cache_path, index=False)
            logger.debug(f"Saved {len(self._cache)} sentiment scores to cache")
        except Exception as e:
            logger.warning(f"Failed to save sentiment cache: {e}")
    
    def _get_pipeline(self):
        """Lazy-load the FinBERT pipeline."""
        if self._pipeline is None:
            logger.info(f"Loading FinBERT model: {self._config.model_name}")
            try:
                from transformers import pipeline
                self._pipeline = pipeline(
                    "sentiment-analysis",
                    model=self._config.model_name,
                    tokenizer=self._config.model_name,
                    truncation=True,
                    max_length=512
                )
                logger.info("FinBERT model loaded successfully")
            except Exception as e:
                logger.error(f"Failed to load FinBERT model: {e}")
                raise
        return self._pipeline
    
    def _score_text(self, text: str) -> Dict[str, float]:
        """
        Score a single text.
        
        Args:
            text: Text to analyze.
        
        Returns:
            Dict with positive, negative, neutral scores.
        """
        # Check cache
        text_hash = hash_text(text)
        if text_hash in self._cache:
            return self._cache[text_hash]
        
        # Score with FinBERT
        try:
            pipe = self._get_pipeline()
            result = pipe(text[:512])[0]  # Truncate for safety
            
            # FinBERT returns label and score
            label = result['label'].lower()
            score = result['score']
            
            scores = {'positive': 0.0, 'negative': 0.0, 'neutral': 0.0}
            scores[label] = score
            
            # Cache result
            self._cache[text_hash] = scores
            
            return scores
            
        except Exception as e:
            logger.warning(f"Failed to score text: {e}")
            return {'positive': 0.0, 'negative': 0.0, 'neutral': 1.0}
    
    def score_article(self, article: NewsArticle) -> Dict[str, float]:
        """
        Score a news article.
        
        Args:
            article: NewsArticle to analyze.
        
        Returns:
            Dict with positive, negative, neutral scores.
        """
        text = article.text_for_sentiment
        if not text.strip():
            return {'positive': 0.0, 'negative': 0.0, 'neutral': 1.0}
        return self._score_text(text)
    
    def score_articles(
        self,
        articles: List[NewsArticle]
    ) -> List[Dict[str, float]]:
        """
        Score multiple articles.
        
        Args:
            articles: List of NewsArticle objects.
        
        Returns:
            List of score dicts.
        """
        scores = []
        new_scores = 0
        
        for article in articles:
            score = self.score_article(article)
            scores.append(score)
            if article.text_hash not in self._cache:
                new_scores += 1
        
        # Save cache if new scores were added
        if new_scores > 0:
            self._save_cache()
            logger.debug(f"Scored {new_scores} new articles")
        
        return scores
    
    def aggregate_scores(
        self,
        scores: List[Dict[str, float]]
    ) -> Tuple[float, float, float]:
        """
        Aggregate multiple sentiment scores.
        
        Args:
            scores: List of score dicts.
        
        Returns:
            Tuple of (positive_agg, negative_agg, neutral_agg).
        """
        if not scores:
            return 0.0, 0.0, 1.0
        
        positives = [s['positive'] for s in scores]
        negatives = [s['negative'] for s in scores]
        neutrals = [s['neutral'] for s in scores]
        
        if self._config.aggregation_method == "max":
            return max(positives), max(negatives), max(neutrals)
        else:  # mean
            return (
                float(np.mean(positives)),
                float(np.mean(negatives)),
                float(np.mean(neutrals))
            )
    
    def get_symbol_sentiment(
        self,
        symbol: str,
        date: datetime,
        lookback_days: Optional[int] = None
    ) -> Tuple[float, float, float]:
        """
        Get aggregated sentiment for a symbol on a date.
        
        Args:
            symbol: Stock ticker symbol.
            date: Target date.
            lookback_days: Days to look back for news.
        
        Returns:
            Tuple of (positive_score, negative_score, neutral_score).
        """
        lookback = lookback_days or self._config.news_lookback_days
        
        # Fetch news
        news_provider = get_news_provider()
        articles = news_provider.get_news_for_date(symbol, date, lookback)
        
        if not articles:
            logger.debug(f"No news for {symbol} on {date.date()}")
            return 0.0, 0.0, 1.0
        
        # Score articles
        scores = self.score_articles(articles)
        
        # Aggregate
        return self.aggregate_scores(scores)
    
    def check_sentiment_confirmation(
        self,
        symbol: str,
        date: datetime,
        side: str  # "long" or "short"
    ) -> Tuple[bool, float, str]:
        """
        Check if sentiment confirms a trade direction.
        
        Args:
            symbol: Stock ticker symbol.
            date: Trade date.
            side: "long" or "short".
        
        Returns:
            Tuple of (confirmed, score, reason).
        """
        pos, neg, neu = self.get_symbol_sentiment(symbol, date)
        
        if side == "long":
            if pos >= self._config.positive_threshold:
                return True, pos, f"Positive sentiment ({pos:.2f}) above threshold"
            else:
                return False, pos, f"Positive sentiment ({pos:.2f}) below threshold ({self._config.positive_threshold})"
        
        elif side == "short":
            if neg >= self._config.negative_threshold:
                return True, neg, f"Negative sentiment ({neg:.2f}) above threshold"
            else:
                return False, neg, f"Negative sentiment ({neg:.2f}) below threshold ({self._config.negative_threshold})"
        
        return False, 0.0, f"Unknown side: {side}"
    
    def has_news_coverage(
        self,
        symbol: str,
        date: datetime,
        lookback_days: Optional[int] = None
    ) -> bool:
        """
        Check if symbol has news coverage for sentiment confirmation.
        
        Args:
            symbol: Stock ticker symbol.
            date: Target date.
            lookback_days: Days to look back.
        
        Returns:
            bool: True if news exists for confirmation.
        """
        news_provider = get_news_provider()
        return news_provider.has_news(
            symbol, date,
            lookback_days or self._config.news_lookback_days
        )


# Global analyzer instance
_analyzer: Optional[SentimentAnalyzer] = None


def get_sentiment_analyzer() -> SentimentAnalyzer:
    """
    Get or create the global sentiment analyzer.
    
    Returns:
        SentimentAnalyzer: Global analyzer instance.
    """
    global _analyzer
    if _analyzer is None:
        _analyzer = SentimentAnalyzer()
    return _analyzer


def get_symbol_sentiment(
    symbol: str,
    date: datetime
) -> Tuple[float, float, float]:
    """
    Convenience function to get symbol sentiment.
    
    Args:
        symbol: Stock ticker symbol.
        date: Target date.
    
    Returns:
        Tuple of (positive, negative, neutral) scores.
    """
    analyzer = get_sentiment_analyzer()
    return analyzer.get_symbol_sentiment(symbol, date)


def confirm_sentiment(
    symbol: str,
    date: datetime,
    side: str
) -> Tuple[bool, float, str]:
    """
    Convenience function for sentiment confirmation.
    
    Args:
        symbol: Stock ticker symbol.
        date: Trade date.
        side: "long" or "short".
    
    Returns:
        Tuple of (confirmed, score, reason).
    """
    analyzer = get_sentiment_analyzer()
    return analyzer.check_sentiment_confirmation(symbol, date, side)


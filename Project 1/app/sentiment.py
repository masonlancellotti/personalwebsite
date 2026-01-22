"""
Sentiment analysis module using FinBERT.

Scores news article sentiment and caches results for efficiency.
IMPORTANT: Returns None when no articles available, never fake 0.50.
"""

import logging
import csv
from datetime import datetime
from typing import Optional, Dict, List, Tuple
from pathlib import Path
from dataclasses import dataclass

import pandas as pd
import numpy as np

from config import get_config, SentimentConfig
from news_provider import get_news_provider, NewsArticle
from utils import hash_text

logger = logging.getLogger("tradingbot.sentiment")

# Track if model unavailable notice has been shown
_model_unavailable_notice_shown = False


@dataclass
class SentimentScore:
    """
    Aggregated sentiment score for a symbol.
    
    Attributes:
        positive: Positive sentiment score (0-1)
        negative: Negative sentiment score (0-1)
        neutral: Neutral sentiment score (0-1)
        n: Number of articles scored
    """
    positive: float
    negative: float
    neutral: float
    n: int
    
    def __repr__(self) -> str:
        return f"SentimentScore(pos={self.positive:.2f}, neg={self.negative:.2f}, neu={self.neutral:.2f}, n={self.n})"


class SentimentAnalyzer:
    """
    FinBERT-based sentiment analyzer with caching.
    
    Uses HuggingFace transformers to score financial news sentiment.
    Returns None when no articles available - never returns fake 0.50.
    """
    
    def __init__(self, config: Optional[SentimentConfig] = None):
        """
        Initialize the sentiment analyzer.
        
        Args:
            config: Sentiment configuration.
        """
        self._config = config or get_config().sentiment
        self._pipeline = None
        self._model_available = True  # Assume available until proven otherwise
        self._cache: Dict[str, Dict[str, float]] = {}
        self._cache_path = get_config().paths.data_dir / self._config.cache_file
        self._load_cache()
        
    def _load_cache(self) -> None:
        """Load sentiment cache from disk (CSV format for append-safety)."""
        if self._cache_path.exists():
            try:
                # Read CSV
                with open(self._cache_path, 'r', newline='', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        self._cache[row['text_hash']] = {
                            'positive': float(row['positive']),
                            'negative': float(row['negative']),
                            'neutral': float(row['neutral'])
                        }
                logger.info(f"Loaded {len(self._cache)} cached sentiment scores")
            except Exception as e:
                logger.warning(f"Failed to load sentiment cache: {e}")
    
    def _save_to_cache(self, text_hash: str, scores: Dict[str, float]) -> None:
        """Append a single entry to the cache file."""
        try:
            file_exists = self._cache_path.exists()
            with open(self._cache_path, 'a', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=['text_hash', 'positive', 'negative', 'neutral'])
                if not file_exists:
                    writer.writeheader()
                writer.writerow({
                    'text_hash': text_hash,
                    'positive': scores['positive'],
                    'negative': scores['negative'],
                    'neutral': scores['neutral']
                })
        except Exception as e:
            logger.warning(f"Failed to append to sentiment cache: {e}")
    
    def _get_pipeline(self):
        """Lazy-load the FinBERT pipeline."""
        global _model_unavailable_notice_shown
        
        if not self._model_available:
            return None
            
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
                if not _model_unavailable_notice_shown:
                    logger.warning(f"Sentiment model unavailable; sentiment disabled for this run. Error: {e}")
                    _model_unavailable_notice_shown = True
                self._model_available = False
                return None
                
        return self._pipeline
    
    def _score_text(self, text: str) -> Optional[Dict[str, float]]:
        """
        Score a single text.
        
        Args:
            text: Text to analyze.
        
        Returns:
            Dict with positive, negative, neutral scores, or None if unavailable.
        """
        if not text.strip():
            return None
            
        # Check cache
        text_hash = hash_text(text)
        if text_hash in self._cache:
            return self._cache[text_hash]
        
        # Check if model available
        pipe = self._get_pipeline()
        if pipe is None:
            return None
        
        # Score with FinBERT
        try:
            result = pipe(text[:512])[0]  # Truncate for safety
            
            # FinBERT returns label and score
            label = result['label'].lower()
            score = result['score']
            
            # Distribute scores: the label gets the score, others get remainder
            scores = {'positive': 0.0, 'negative': 0.0, 'neutral': 0.0}
            scores[label] = score
            # Distribute remaining probability to other labels
            remainder = (1.0 - score) / 2
            for k in scores:
                if k != label:
                    scores[k] = remainder
            
            # Cache result (append to file)
            self._cache[text_hash] = scores
            self._save_to_cache(text_hash, scores)
            
            return scores
            
        except Exception as e:
            logger.warning(f"Failed to score text: {e}")
            return None
    
    def score_article(self, article: NewsArticle) -> Optional[Dict[str, float]]:
        """
        Score a news article.
        
        Args:
            article: NewsArticle to analyze.
        
        Returns:
            Dict with positive, negative, neutral scores, or None.
        """
        text = article.text_for_sentiment
        return self._score_text(text)
    
    def score_articles(
        self,
        articles: List[NewsArticle]
    ) -> Optional[SentimentScore]:
        """
        Score multiple articles and return aggregated score.
        
        Args:
            articles: List of NewsArticle objects.
        
        Returns:
            SentimentScore object, or None if no articles or model unavailable.
        """
        if not articles:
            return None
        
        scores = []
        for article in articles:
            score = self.score_article(article)
            if score is not None:
                scores.append(score)
        
        if not scores:
            return None
        
        # Aggregate
        positives = [s['positive'] for s in scores]
        negatives = [s['negative'] for s in scores]
        neutrals = [s['neutral'] for s in scores]
        
        if self._config.aggregation_method == "max":
            pos = max(positives)
            neg = max(negatives)
            neu = max(neutrals)
        else:  # mean
            pos = float(np.mean(positives))
            neg = float(np.mean(negatives))
            neu = float(np.mean(neutrals))
        
        return SentimentScore(positive=pos, negative=neg, neutral=neu, n=len(scores))
    
    def get_symbol_sentiment(
        self,
        symbol: str,
        date: datetime,
        lookback_days: Optional[int] = None
    ) -> Optional[SentimentScore]:
        """
        Get aggregated sentiment for a symbol on a date.
        
        Args:
            symbol: Stock ticker symbol.
            date: Target date.
            lookback_days: Days to look back for news.
        
        Returns:
            SentimentScore object, or None if no news/model unavailable.
        """
        lookback = lookback_days or self._config.lookback_days
        
        # Fetch news
        news_provider = get_news_provider()
        articles = news_provider.get_news_for_date(symbol, date, lookback)
        
        if not articles:
            return None
        
        # Score articles
        result = self.score_articles(articles)
        
        if result is not None:
            logger.debug(f"FinBERT sentiment {symbol}: pos={result.positive:.2f} neg={result.negative:.2f} n={result.n}")
        
        return result
    
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
            lookback_days or self._config.lookback_days
        )
    
    @property
    def model_available(self) -> bool:
        """Check if sentiment model is available."""
        return self._model_available


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
) -> Optional[SentimentScore]:
    """
    Convenience function to get symbol sentiment.
    
    Args:
        symbol: Stock ticker symbol.
        date: Target date.
    
    Returns:
        SentimentScore object or None.
    """
    analyzer = get_sentiment_analyzer()
    return analyzer.get_symbol_sentiment(symbol, date)

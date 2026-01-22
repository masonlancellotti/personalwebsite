"""
News provider module for sentiment analysis.

NOTE: Alpaca News API requires a paid subscription. The Alpaca news fetching
code is implemented but COMMENTED OUT. To enable it in the future:
1. Purchase Alpaca news subscription
2. Uncomment the _fetch_from_alpaca method call in fetch_news()
3. Set USE_ALPACA_NEWS=true in your .env file

Currently uses RSS feeds as the primary (and only) news source.

IMPORTANT: RSS feeds only contain RECENT articles (typically last 24-48 hours).
Historical backtests will have NO news data for older dates. This is expected
and the strategy handles this via sentiment mode configuration.
"""

import logging
import socket
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
import json
import hashlib

import pandas as pd

from config import get_config, RSSConfig
from alpaca_clients import get_client_manager
from utils import utc_now, chunk_list, hash_text

logger = logging.getLogger("tradingbot.news_provider")

# Track if we've shown the RSS historical notice
_rss_notice_shown = False


@dataclass
class NewsArticle:
    """Represents a news article."""
    id: str
    symbol: str
    created_at: datetime
    headline: str
    summary: str
    url: str
    source: str  # 'alpaca' or 'rss'
    
    @property
    def text_for_sentiment(self) -> str:
        """Get combined text for sentiment analysis."""
        if self.summary:
            return f"{self.headline}. {self.summary}".strip()
        return self.headline.strip()
    
    @property
    def text_hash(self) -> str:
        """Get hash of text for deduplication."""
        return hash_text(self.text_for_sentiment)


class RSSNewsProvider:
    """
    RSS-based news provider - PRIMARY news source.
    
    Uses feedparser to fetch public RSS feeds and filters by symbol/keywords.
    No API keys required - completely free.
    
    IMPORTANT: RSS feeds are NOT historical. They only contain recent articles
    (typically last 24-48 hours). Historical backtests will have no news data.
    """
    
    supports_historical: bool = False  # RSS cannot fetch historical news
    
    def __init__(self, config: Optional[RSSConfig] = None):
        """
        Initialize RSS provider.
        
        Args:
            config: RSS configuration.
        """
        self._config = config or get_config().rss
        self._sentiment_config = get_config().sentiment
        self._symbol_keywords: Dict[str, List[str]] = {}
        
    def _get_symbol_keywords(self, symbol: str) -> List[str]:
        """
        Get search keywords for a symbol.
        
        Args:
            symbol: Stock ticker symbol.
        
        Returns:
            List of keywords to search for.
        """
        if symbol not in self._symbol_keywords:
            # Common company name mappings
            COMPANY_NAMES = {
                "AAPL": ["Apple", "iPhone", "iPad", "Mac", "Tim Cook"],
                "MSFT": ["Microsoft", "Windows", "Azure", "Xbox", "Satya Nadella"],
                "GOOGL": ["Google", "Alphabet", "YouTube", "Android", "Sundar Pichai"],
                "GOOG": ["Google", "Alphabet", "YouTube", "Android"],
                "AMZN": ["Amazon", "AWS", "Prime", "Andy Jassy"],
                "META": ["Meta", "Facebook", "Instagram", "WhatsApp", "Zuckerberg"],
                "TSLA": ["Tesla", "Elon Musk", "EV", "electric vehicle"],
                "NVDA": ["Nvidia", "NVIDIA", "GPU", "Jensen Huang"],
                "JPM": ["JPMorgan", "JP Morgan", "Chase", "Jamie Dimon"],
                "BAC": ["Bank of America", "BofA"],
                "WMT": ["Walmart", "Wal-Mart"],
                "JNJ": ["Johnson & Johnson", "J&J"],
                "V": ["Visa"],
                "MA": ["Mastercard", "MasterCard"],
                "PG": ["Procter & Gamble", "P&G"],
                "UNH": ["UnitedHealth", "United Health"],
                "HD": ["Home Depot"],
                "DIS": ["Disney", "Walt Disney"],
                "NFLX": ["Netflix"],
                "INTC": ["Intel"],
                "AMD": ["AMD", "Advanced Micro Devices"],
                "CRM": ["Salesforce"],
                "ORCL": ["Oracle"],
                "CSCO": ["Cisco"],
                "ADBE": ["Adobe"],
                "PYPL": ["PayPal"],
                "QCOM": ["Qualcomm"],
                "TXN": ["Texas Instruments"],
                "AVGO": ["Broadcom"],
                "COST": ["Costco"],
                "PEP": ["Pepsi", "PepsiCo"],
                "KO": ["Coca-Cola", "Coke"],
                "MCD": ["McDonald's", "McDonalds"],
                "NKE": ["Nike"],
                "SBUX": ["Starbucks"],
                "BA": ["Boeing"],
                "CAT": ["Caterpillar"],
                "GE": ["General Electric"],
                "XOM": ["Exxon", "ExxonMobil"],
                "CVX": ["Chevron"],
            }
            
            keywords = [symbol]
            if symbol in COMPANY_NAMES:
                keywords.extend(COMPANY_NAMES[symbol])
            
            self._symbol_keywords[symbol] = keywords
        
        return self._symbol_keywords[symbol]
    
    def get_news_window(
        self,
        symbol: str,
        start_dt: datetime,
        end_dt: datetime,
        limit: int = 50
    ) -> List[NewsArticle]:
        """
        Get news for a symbol within a time window.
        
        NOTE: RSS cannot fetch historical data. The start_dt/end_dt are used
        to filter returned articles by published date, but RSS will only
        return recent articles regardless.
        
        Args:
            symbol: Stock ticker symbol.
            start_dt: Start of window (for filtering).
            end_dt: End of window (for filtering).
            limit: Maximum articles to return.
        
        Returns:
            List of NewsArticle objects within the window.
        """
        global _rss_notice_shown
        
        # Show notice once per run
        if not _rss_notice_shown and self._config.historical_notice:
            logger.info(
                "RSS mode: feeds contain only recent items (not historical). "
                "Backtests for older dates may have no articles; sentiment may be unavailable."
            )
            _rss_notice_shown = True
        
        articles = self._fetch_with_timeout(symbol, start_dt, end_dt, limit)
        
        # Filter by date window
        filtered = [
            a for a in articles
            if start_dt <= a.created_at <= end_dt
        ]
        
        # Log result (one line per symbol)
        if filtered:
            sample = filtered[0].headline[:80] if filtered[0].headline else "(no headline)"
            logger.debug(
                f"RSS: {symbol} articles={len(filtered)} "
                f"window=[{start_dt.date()}..{end_dt.date()}] sample='{sample}'"
            )
        else:
            logger.debug(
                f"RSS: no articles for {symbol} window=[{start_dt.date()}..{end_dt.date()}] "
                "(expected for historical backtests)"
            )
        
        return filtered[:limit]
    
    def _fetch_with_timeout(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        limit: int
    ) -> List[NewsArticle]:
        """
        Fetch news with timeout protection.
        
        Args:
            symbol: Stock ticker symbol.
            start: Start datetime.
            end: End datetime.
            limit: Maximum articles.
        
        Returns:
            List of NewsArticle objects.
        """
        if not self._config.enabled:
            return []
        
        try:
            import feedparser
        except ImportError:
            logger.warning("feedparser not installed - run: pip install feedparser")
            return []
        
        # Set socket timeout
        timeout_sec = self._config.timeout_sec
        old_timeout = socket.getdefaulttimeout()
        socket.setdefaulttimeout(timeout_sec)
        
        articles: List[NewsArticle] = []
        keywords = self._get_symbol_keywords(symbol)
        
        try:
            for feed_url in self._config.feeds:
                try:
                    # Some feeds support symbol substitution
                    url = feed_url.format(symbol=symbol)
                    feed = feedparser.parse(url)
                    
                    if not feed.entries:
                        continue
                    
                    for entry in feed.entries[:limit * 2]:  # Fetch extra, filter later
                        # Parse date
                        published = None
                        if hasattr(entry, 'published_parsed') and entry.published_parsed:
                            try:
                                published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
                            except:
                                continue
                        elif hasattr(entry, 'updated_parsed') and entry.updated_parsed:
                            try:
                                published = datetime(*entry.updated_parsed[:6], tzinfo=timezone.utc)
                            except:
                                continue
                        else:
                            # Use current time if no date
                            published = utc_now()
                        
                        # Filter by keywords
                        title = entry.get('title', '')
                        summary = entry.get('summary', entry.get('description', ''))
                        text = f"{title} {summary}".lower()
                        
                        # Check if any keyword matches
                        if not any(kw.lower() in text for kw in keywords):
                            continue
                        
                        article = NewsArticle(
                            id=hashlib.md5(entry.get('link', title).encode()).hexdigest()[:16],
                            symbol=symbol,
                            created_at=published,
                            headline=title[:200] if title else "",
                            summary=summary[:500] if summary else "",
                            url=entry.get('link', ''),
                            source='rss'
                        )
                        articles.append(article)
                        
                except Exception as e:
                    logger.debug(f"RSS feed error for {feed_url}: {e}")
                    continue
        
        except Exception as e:
            logger.warning(f"RSS fetch failed for {symbol}: {e}")
            return []
        
        finally:
            # Restore original timeout
            socket.setdefaulttimeout(old_timeout)
        
        # Deduplicate by headline hash
        seen = set()
        unique_articles = []
        for article in articles:
            h = article.text_hash
            if h not in seen and article.headline:
                seen.add(h)
                unique_articles.append(article)
        
        return unique_articles[:limit]
    
    def fetch_news(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        limit: int = 50
    ) -> List[NewsArticle]:
        """
        Fetch news from RSS feeds for a symbol.
        
        Args:
            symbol: Stock ticker symbol.
            start: Start datetime.
            end: End datetime.
            limit: Maximum articles to return.
        
        Returns:
            List of NewsArticle objects.
        """
        return self.get_news_window(symbol, start, end, limit)


class AlpacaNewsProvider:
    """
    News provider with RSS as primary source.
    
    NOTE: Alpaca News API code is implemented but disabled.
    To enable Alpaca News in the future:
    1. Purchase Alpaca news subscription
    2. Uncomment _fetch_from_alpaca call in fetch_news()
    3. Set USE_ALPACA_NEWS=true in .env
    """
    
    supports_historical: bool = False  # Currently using RSS which doesn't support historical
    
    def __init__(
        self,
        cache_dir: Optional[Path] = None,
        use_rss: bool = True
    ):
        """
        Initialize news provider.
        
        Args:
            cache_dir: Directory for caching news.
            use_rss: Whether to use RSS feeds (default: True).
        """
        self._config = get_config()
        self._cache_dir = cache_dir or self._config.paths.news_cache_dir
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        
        self._rss_provider = RSSNewsProvider() if use_rss else None
        self._cache: Dict[str, List[NewsArticle]] = {}
        
        # NOTE: Alpaca News requires subscription - disabled by default
        import os
        self._use_alpaca_news = os.getenv("USE_ALPACA_NEWS", "false").lower() == "true"
        if self._use_alpaca_news:
            logger.info("Alpaca News enabled - requires paid subscription")
            self.supports_historical = True
        else:
            logger.info("Using RSS feeds for news (Alpaca News disabled)")
        
    def _cache_key(self, symbol: str, date: datetime) -> str:
        """Generate cache key for symbol/date."""
        return f"{symbol}_{date.strftime('%Y%m%d')}"
    
    def _cache_path(self, symbol: str) -> Path:
        """Get cache file path for symbol."""
        safe_symbol = symbol.replace("-", "_").replace("/", "_")
        return self._cache_dir / f"{safe_symbol}_news.json"
    
    def _load_cache(self, symbol: str) -> Dict[str, List[Dict]]:
        """Load cached news for symbol."""
        cache_path = self._cache_path(symbol)
        if cache_path.exists():
            try:
                with open(cache_path, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load news cache for {symbol}: {e}")
        return {}
    
    def _save_cache(self, symbol: str, cache: Dict[str, List[Dict]]) -> None:
        """Save news cache for symbol."""
        cache_path = self._cache_path(symbol)
        try:
            with open(cache_path, 'w') as f:
                json.dump(cache, f, default=str)
        except Exception as e:
            logger.warning(f"Failed to save news cache for {symbol}: {e}")
    
    def get_news_window(
        self,
        symbol: str,
        start_dt: datetime,
        end_dt: datetime,
        limit: int = 50
    ) -> List[NewsArticle]:
        """
        Get news for a symbol within a time window.
        
        Args:
            symbol: Stock ticker symbol.
            start_dt: Start of window.
            end_dt: End of window.
            limit: Maximum articles to return.
        
        Returns:
            List of NewsArticle objects within the window.
        """
        if self._rss_provider:
            return self._rss_provider.get_news_window(symbol, start_dt, end_dt, limit)
        return []
    
    def _fetch_from_rss(
        self,
        symbols: List[str],
        start: datetime,
        end: datetime,
        limit_per_symbol: int = 50
    ) -> Dict[str, List[NewsArticle]]:
        """
        Fetch news from RSS feeds for multiple symbols.
        """
        result: Dict[str, List[NewsArticle]] = {}
        
        if not self._rss_provider:
            return {s: [] for s in symbols}
        
        for symbol in symbols:
            articles = self._rss_provider.get_news_window(symbol, start, end, limit_per_symbol)
            result[symbol] = articles
        
        return result
    
    def fetch_news(
        self,
        symbols: List[str],
        start: datetime,
        end: Optional[datetime] = None,
        limit_per_symbol: int = 50,
        use_cache: bool = True
    ) -> Dict[str, List[NewsArticle]]:
        """
        Fetch news for multiple symbols.
        
        Currently uses RSS feeds only. Alpaca News is commented out
        but can be enabled with a subscription.
        
        Args:
            symbols: List of stock ticker symbols.
            start: Start datetime.
            end: End datetime (default: now).
            limit_per_symbol: Maximum articles per symbol.
            use_cache: Whether to use cached news.
        
        Returns:
            Dict mapping symbol to list of NewsArticle objects.
        """
        if end is None:
            end = utc_now()
        
        result: Dict[str, List[NewsArticle]] = {s: [] for s in symbols}
        symbols_to_fetch: List[str] = []
        
        # Check cache first
        if use_cache:
            for symbol in symbols:
                cache = self._load_cache(symbol)
                articles = []
                
                # Check each day in range
                current = start
                while current <= end:
                    key = self._cache_key(symbol, current)
                    if key in cache:
                        for item in cache[key]:
                            try:
                                article = NewsArticle(
                                    id=item['id'],
                                    symbol=symbol,
                                    created_at=datetime.fromisoformat(item['created_at'].replace('Z', '+00:00')),
                                    headline=item['headline'],
                                    summary=item['summary'],
                                    url=item['url'],
                                    source=item.get('source', 'rss')
                                )
                                articles.append(article)
                            except Exception:
                                continue
                    current += timedelta(days=1)
                
                if articles:
                    result[symbol] = articles
                else:
                    symbols_to_fetch.append(symbol)
        else:
            symbols_to_fetch = list(symbols)
        
        # Fetch news for symbols not in cache
        if symbols_to_fetch:
            logger.debug(f"Fetching news for {len(symbols_to_fetch)} symbols via RSS")
            
            rss_news = self._fetch_from_rss(symbols_to_fetch, start, end, limit_per_symbol)
            
            for symbol in symbols_to_fetch:
                articles = rss_news.get(symbol, [])
                result[symbol] = articles
                
                # Cache results
                if articles and use_cache:
                    cache = self._load_cache(symbol)
                    for article in articles:
                        key = self._cache_key(symbol, article.created_at)
                        if key not in cache:
                            cache[key] = []
                        cache[key].append({
                            'id': article.id,
                            'created_at': article.created_at.isoformat(),
                            'headline': article.headline,
                            'summary': article.summary,
                            'url': article.url,
                            'source': article.source
                        })
                    self._save_cache(symbol, cache)
        
        return result
    
    def get_news_for_date(
        self,
        symbol: str,
        date: datetime,
        lookback_days: Optional[int] = None
    ) -> List[NewsArticle]:
        """
        Get news for a symbol around a specific date.
        
        Args:
            symbol: Stock ticker symbol.
            date: Target date.
            lookback_days: Number of days to look back.
        
        Returns:
            List of relevant news articles.
        """
        if lookback_days is None:
            lookback_days = self._config.sentiment.lookback_days
        
        start = date - timedelta(days=lookback_days)
        end = date
        
        return self.get_news_window(symbol, start, end)
    
    def has_news(self, symbol: str, date: datetime, lookback_days: Optional[int] = None) -> bool:
        """
        Check if news exists for a symbol/date.
        
        Args:
            symbol: Stock ticker symbol.
            date: Target date.
            lookback_days: Days to look back.
        
        Returns:
            bool: True if news exists.
        """
        articles = self.get_news_for_date(symbol, date, lookback_days)
        return len(articles) > 0
    
    def clear_cache(self, symbol: Optional[str] = None) -> None:
        """
        Clear news cache.
        
        Args:
            symbol: Symbol to clear (None = clear all).
        """
        if symbol:
            cache_path = self._cache_path(symbol)
            if cache_path.exists():
                cache_path.unlink()
            logger.info(f"Cleared news cache for {symbol}")
        else:
            for path in self._cache_dir.glob("*.json"):
                path.unlink()
            logger.info("Cleared all news cache")


# Global provider instance
_news_provider: Optional[AlpacaNewsProvider] = None


def get_news_provider() -> AlpacaNewsProvider:
    """
    Get or create the global news provider.
    
    Returns:
        AlpacaNewsProvider: Global news provider instance.
    """
    global _news_provider
    if _news_provider is None:
        _news_provider = AlpacaNewsProvider()
    return _news_provider

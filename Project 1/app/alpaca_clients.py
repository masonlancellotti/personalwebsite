"""
Alpaca API client factory module.

Creates and manages Alpaca SDK clients for trading, market data, and news.
"""

from typing import Optional, Tuple
import logging

from alpaca.trading.client import TradingClient
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.live import StockDataStream

from config import AlpacaConfig, get_config

logger = logging.getLogger("tradingbot.alpaca_clients")


class AlpacaClientManager:
    """
    Manager for Alpaca API clients.
    
    Provides lazy initialization and singleton-style access to:
    - TradingClient: Orders, positions, account info
    - StockHistoricalDataClient: Historical OHLCV data
    - StockDataStream: Real-time market data (optional)
    """
    
    def __init__(self, config: Optional[AlpacaConfig] = None):
        """
        Initialize the client manager.
        
        Args:
            config: Alpaca configuration. Uses global config if not provided.
        """
        self._config = config or get_config().alpaca
        self._trading_client: Optional[TradingClient] = None
        self._data_client: Optional[StockHistoricalDataClient] = None
        self._data_stream: Optional[StockDataStream] = None
        
    @property
    def trading_client(self) -> TradingClient:
        """
        Get or create the trading client.
        
        Returns:
            TradingClient: Alpaca trading client for orders/positions.
        """
        if self._trading_client is None:
            self._trading_client = TradingClient(
                api_key=self._config.api_key,
                secret_key=self._config.secret_key,
                paper=self._config.paper,
                url_override=self._config.base_url_trading
            )
            mode = "paper" if self._config.paper else "live"
            logger.info(f"Initialized TradingClient in {mode} mode")
        return self._trading_client
    
    @property
    def data_client(self) -> StockHistoricalDataClient:
        """
        Get or create the historical data client.
        
        Returns:
            StockHistoricalDataClient: Client for historical bars.
        """
        if self._data_client is None:
            self._data_client = StockHistoricalDataClient(
                api_key=self._config.api_key,
                secret_key=self._config.secret_key,
                url_override=self._config.base_url_data
            )
            logger.info(f"Initialized StockHistoricalDataClient (feed: {self._config.data_feed})")
        return self._data_client
    
    @property
    def data_stream(self) -> StockDataStream:
        """
        Get or create the real-time data stream.
        
        Returns:
            StockDataStream: Client for live market data.
        """
        if self._data_stream is None:
            feed = "iex" if self._config.data_feed == "iex" else "sip"
            self._data_stream = StockDataStream(
                api_key=self._config.api_key,
                secret_key=self._config.secret_key,
                feed=feed
            )
            logger.info(f"Initialized StockDataStream (feed: {feed})")
        return self._data_stream
    
    @property
    def data_feed(self) -> str:
        """
        Get configured data feed.
        
        Returns:
            str: 'iex' or 'sip'.
        """
        return self._config.data_feed
    
    @property
    def is_paper(self) -> bool:
        """
        Check if using paper trading.
        
        Returns:
            bool: True if paper trading mode.
        """
        return self._config.paper
    
    def get_account(self):
        """
        Get account information.
        
        Returns:
            TradeAccount: Account details including equity, buying power, etc.
        """
        return self.trading_client.get_account()
    
    def get_positions(self):
        """
        Get all open positions.
        
        Returns:
            List[Position]: List of open positions.
        """
        return self.trading_client.get_all_positions()
    
    def get_asset(self, symbol: str):
        """
        Get asset details for a symbol.
        
        Args:
            symbol: Stock ticker symbol.
        
        Returns:
            Asset: Asset details including tradability, shortability.
        """
        return self.trading_client.get_asset(symbol)
    
    def is_shortable(self, symbol: str) -> bool:
        """
        Check if an asset is shortable.
        
        Args:
            symbol: Stock ticker symbol.
        
        Returns:
            bool: True if the asset can be shorted.
        """
        try:
            asset = self.get_asset(symbol)
            return asset.shortable and asset.easy_to_borrow
        except Exception as e:
            logger.warning(f"Could not check shortability for {symbol}: {e}")
            return False
    
    def validate_account_for_shorting(self) -> Tuple[bool, str]:
        """
        Validate that the account supports shorting.
        
        Returns:
            Tuple[bool, str]: (is_valid, message)
        """
        try:
            account = self.get_account()
            
            # Check if margin account
            if not hasattr(account, 'shorting_enabled'):
                # Older API version, assume it's fine if we can get account
                return True, "Account validation passed (legacy)"
            
            if not account.shorting_enabled:
                return False, "Shorting is not enabled on this account"
            
            return True, "Account supports shorting"
            
        except Exception as e:
            return False, f"Account validation failed: {e}"
    
    def close(self) -> None:
        """Close all client connections."""
        if self._data_stream is not None:
            try:
                self._data_stream.close()
            except Exception:
                pass
        self._trading_client = None
        self._data_client = None
        self._data_stream = None
        logger.info("Closed all Alpaca clients")


# Global client manager instance
_client_manager: Optional[AlpacaClientManager] = None


def get_client_manager() -> AlpacaClientManager:
    """
    Get or create the global client manager.
    
    Returns:
        AlpacaClientManager: Global client manager instance.
    """
    global _client_manager
    if _client_manager is None:
        _client_manager = AlpacaClientManager()
    return _client_manager


def get_trading_client() -> TradingClient:
    """
    Convenience function to get the trading client.
    
    Returns:
        TradingClient: Alpaca trading client.
    """
    return get_client_manager().trading_client


def get_data_client() -> StockHistoricalDataClient:
    """
    Convenience function to get the data client.
    
    Returns:
        StockHistoricalDataClient: Alpaca historical data client.
    """
    return get_client_manager().data_client


def get_data_feed() -> str:
    """
    Get the configured data feed.
    
    Returns:
        str: 'iex' or 'sip'.
    """
    return get_client_manager().data_feed


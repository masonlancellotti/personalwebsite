"""Alpaca API client wrappers."""

from alpaca.trading.client import TradingClient
from alpaca.data.historical import CryptoHistoricalDataClient
from alpaca.trading.requests import GetAssetsRequest
from alpaca.trading.enums import AssetClass

# Try to import CryptoDataStream - may not be available in all versions
try:
    from alpaca.data.stream import CryptoDataStream
except ImportError:
    # If not available, we'll handle it in the property
    CryptoDataStream = None  # type: ignore

from config import settings


class AlpacaClients:
    """Wrapper for Alpaca API clients."""

    def __init__(self):
        """Initialize Alpaca clients."""
        if not settings.ALPACA_API_KEY or not settings.ALPACA_SECRET_KEY:
            raise ValueError("ALPACA_API_KEY and ALPACA_SECRET_KEY must be set in .env file")

        # Determine if we're using paper or live
        is_paper = settings.ALPACA_PAPER
        if not is_paper and not settings.ALLOW_LIVE:
            raise ValueError(
                "Live trading requires ALLOW_LIVE=true in .env. "
                "Default is paper trading (ALPACA_PAPER=true)."
            )

        self._trading_client: TradingClient | None = None
        self._data_client: CryptoHistoricalDataClient | None = None
        self._stream_client: CryptoDataStream | None = None
        self._is_paper = is_paper

    @property
    def trading_client(self) -> TradingClient:
        """Get or create trading client."""
        if self._trading_client is None:
            self._trading_client = TradingClient(
                api_key=settings.ALPACA_API_KEY,
                secret_key=settings.ALPACA_SECRET_KEY,
                paper=self._is_paper,
            )
        return self._trading_client

    @property
    def data_client(self) -> CryptoHistoricalDataClient:
        """Get or create historical data client."""
        if self._data_client is None:
            self._data_client = CryptoHistoricalDataClient(
                api_key=settings.ALPACA_API_KEY,
                secret_key=settings.ALPACA_SECRET_KEY,
            )
        return self._data_client

    @property
    def stream_client(self):
        """Get or create streaming data client."""
        if CryptoDataStream is None:
            raise ImportError(
                "CryptoDataStream not available. "
                "Please ensure you have the latest version of alpaca-py installed."
            )
        if self._stream_client is None:
            self._stream_client = CryptoDataStream(
                api_key=settings.ALPACA_API_KEY,
                secret_key=settings.ALPACA_SECRET_KEY,
            )
        return self._stream_client

    @property
    def is_paper(self) -> bool:
        """Check if using paper trading."""
        return self._is_paper


# Global clients instance (lazy initialization)
_clients: AlpacaClients | None = None


def get_clients() -> AlpacaClients:
    """Get global Alpaca clients instance."""
    global _clients
    if _clients is None:
        _clients = AlpacaClients()
    return _clients


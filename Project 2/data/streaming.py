"""WebSocket streaming and symbol state management."""

import asyncio
import time
from datetime import datetime, timezone
from typing import Callable, Optional

from alpaca.data.models import Trade, Quote
from alpaca.data.stream import CryptoDataStream
from loguru import logger

from alpaca_clients import get_clients
from config import settings


class StreamManager:
    """Manage WebSocket streaming and symbol state."""

    def __init__(
        self,
        symbols: list[str],
        on_quote: Optional[Callable[[str, Quote], None]] = None,
        on_trade: Optional[Callable[[str, Trade], None]] = None,
        batch_size: int = 50,
    ):
        """
        Initialize stream manager.

        Args:
            symbols: List of symbols to subscribe to
            on_quote: Callback for quote updates
            on_trade: Callback for trade updates
            batch_size: Number of symbols per subscription batch
        """
        self.symbols = symbols
        self.on_quote = on_quote
        self.on_trade = on_trade
        self.batch_size = batch_size

        self.clients = get_clients()
        self.stream_client: Optional[CryptoDataStream] = None

        # Symbol state: {symbol: {bid, ask, mid, spread, last_update_ts, last_trade_ts}}
        self.symbol_state: dict[str, dict] = {symbol: {} for symbol in symbols}

        self.running = False
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 10

    async def start(self):
        """Start streaming."""
        self.running = True
        await self._connect_and_subscribe()

    async def stop(self):
        """Stop streaming."""
        self.running = False
        if self.stream_client:
            try:
                await self.stream_client.stop_ws()
            except Exception as e:
                logger.error(f"Error stopping stream: {e}")

    async def _connect_and_subscribe(self):
        """Connect and subscribe to all symbols."""
        self.stream_client = self.clients.stream_client

        # Note: Alpaca streaming API uses decorators to register handlers
        # The actual implementation would register handlers before starting the stream
        # This is a simplified version - full implementation would need proper async handling

        # Subscribe in batches
        for i in range(0, len(self.symbols), self.batch_size):
            batch = self.symbols[i : i + self.batch_size]
            logger.info(f"Subscribing to batch {i//self.batch_size + 1}: {batch[:5]}... ({len(batch)} symbols)")

            # Subscribe to quotes (for bid/ask)
            self.stream_client.subscribe_crypto_quotes(batch)

            # Subscribe to trades (for last trade)
            self.stream_client.subscribe_crypto_trades(batch)

        # Start the stream (this will run forever)
        # Note: Actual implementation would need proper handler registration
        # This is a placeholder - full implementation requires async event handling
        logger.warning("Streaming implementation is simplified - full async handler setup needed")

    async def _reconnect(self):
        """Reconnect with exponential backoff."""
        if self.reconnect_attempts >= self.max_reconnect_attempts:
            logger.error("Max reconnect attempts reached")
            self.running = False
            return

        # Exponential backoff: 1s, 2s, 4s, ... max 60s
        backoff_seconds = min(2 ** self.reconnect_attempts, 60)
        logger.info(f"Reconnecting in {backoff_seconds} seconds (attempt {self.reconnect_attempts + 1})")

        await asyncio.sleep(backoff_seconds)
        self.reconnect_attempts += 1

        try:
            await self._connect_and_subscribe()
            self.reconnect_attempts = 0  # Reset on successful reconnect
        except Exception as e:
            logger.error(f"Reconnect failed: {e}")
            if self.running:
                await self._reconnect()

    def handle_quote(self, quote: Quote):
        """Handle quote update."""
        symbol = quote.symbol

        if symbol not in self.symbol_state:
            return

        bid = float(quote.bid_price) if quote.bid_price else None
        ask = float(quote.ask_price) if quote.ask_price else None

        if bid and ask:
            mid = (bid + ask) / 2.0
            spread = ask - bid
            spread_bps = (spread / mid) * 10000 if mid > 0 else 0

            self.symbol_state[symbol] = {
                "bid": bid,
                "ask": ask,
                "mid": mid,
                "spread": spread,
                "spread_bps": spread_bps,
                "last_update_ts": datetime.now(timezone.utc),
                "last_trade_ts": self.symbol_state[symbol].get("last_trade_ts"),
            }

            if self.on_quote:
                self.on_quote(symbol, quote)

    def handle_trade(self, trade: Trade):
        """Handle trade update."""
        symbol = trade.symbol

        if symbol not in self.symbol_state:
            return

        # Update last trade timestamp
        if "last_trade_ts" not in self.symbol_state[symbol]:
            self.symbol_state[symbol] = {}

        self.symbol_state[symbol]["last_trade_ts"] = datetime.now(timezone.utc)

        if self.on_trade:
            self.on_trade(symbol, trade)

    def get_symbol_state(self, symbol: str) -> dict:
        """Get current state for a symbol."""
        return self.symbol_state.get(symbol, {})

    def is_data_stale(self, symbol: str) -> bool:
        """Check if data is stale for a symbol."""
        state = self.symbol_state.get(symbol, {})
        last_update = state.get("last_update_ts")

        if last_update is None:
            return True

        if isinstance(last_update, datetime):
            age_seconds = (datetime.now(timezone.utc) - last_update).total_seconds()
        else:
            age_seconds = (datetime.now(timezone.utc).timestamp() - last_update)

        return age_seconds > settings.STALE_DATA_SECONDS

    def get_all_stale_symbols(self) -> list[str]:
        """Get list of symbols with stale data."""
        return [symbol for symbol in self.symbols if self.is_data_stale(symbol)]


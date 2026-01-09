"""SQLite storage for orders, fills, positions, and backtests."""

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from loguru import logger

from config import settings


class Storage:
    """SQLite storage manager."""

    def __init__(self, db_path: Optional[Path] = None):
        """
        Initialize storage.

        Args:
            db_path: Path to SQLite database (default: cache_dir/trading.db)
        """
        if db_path is None:
            db_path = settings.get_cache_dir() / "trading.db"
        else:
            db_path = Path(db_path)

        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Initialize schema
        self._init_schema()

    def _get_connection(self) -> sqlite3.Connection:
        """Get database connection."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self):
        """Initialize database schema."""
        conn = self._get_connection()
        cursor = conn.cursor()

        # Orders table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                client_order_id TEXT PRIMARY KEY,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                qty REAL NOT NULL,
                price REAL,
                order_type TEXT NOT NULL,
                time_in_force TEXT NOT NULL,
                status TEXT NOT NULL,
                strategy_tag TEXT,
                submitted_at TIMESTAMP NOT NULL,
                filled_at TIMESTAMP,
                canceled_at TIMESTAMP,
                alpaca_order_id TEXT,
                error_message TEXT
            )
        """)

        # Fills table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS fills (
                fill_id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_order_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                qty REAL NOT NULL,
                price REAL NOT NULL,
                fee REAL DEFAULT 0,
                filled_at TIMESTAMP NOT NULL,
                FOREIGN KEY (client_order_id) REFERENCES orders(client_order_id)
            )
        """)

        # Position snapshots table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS position_snapshots (
                snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                qty REAL NOT NULL,
                avg_entry REAL NOT NULL,
                unrealized_pnl REAL DEFAULT 0,
                timestamp TIMESTAMP NOT NULL,
                UNIQUE(symbol, timestamp)
            )
        """)

        # Backtest runs table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS backtest_runs (
                run_id INTEGER PRIMARY KEY AUTOINCREMENT,
                strategy_name TEXT NOT NULL,
                start_date DATE NOT NULL,
                end_date DATE NOT NULL,
                params_json TEXT NOT NULL,
                metrics_json TEXT,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Backtest trades table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS backtest_trades (
                trade_id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER NOT NULL,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                qty REAL NOT NULL,
                price REAL NOT NULL,
                timestamp TIMESTAMP NOT NULL,
                FOREIGN KEY (run_id) REFERENCES backtest_runs(run_id)
            )
        """)

        # Indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_orders_symbol ON orders(symbol)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_orders_submitted_at ON orders(submitted_at)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_fills_client_order_id ON fills(client_order_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_fills_filled_at ON fills(filled_at)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_snapshots_symbol_timestamp ON position_snapshots(symbol, timestamp)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_backtest_trades_run_id ON backtest_trades(run_id)")

        conn.commit()
        conn.close()

        logger.info(f"Initialized database schema at {self.db_path}")

    def write_order(
        self,
        client_order_id: str,
        symbol: str,
        side: str,
        qty: float,
        order_type: str,
        time_in_force: str,
        strategy_tag: Optional[str] = None,
        price: Optional[float] = None,
        status: str = "submitted",
        alpaca_order_id: Optional[str] = None,
    ):
        """Write order to database."""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT OR REPLACE INTO orders (
                client_order_id, symbol, side, qty, price, order_type, time_in_force,
                status, strategy_tag, submitted_at, alpaca_order_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            client_order_id,
            symbol,
            side,
            qty,
            price,
            order_type,
            time_in_force,
            status,
            strategy_tag,
            datetime.utcnow(),
            alpaca_order_id,
        ))

        conn.commit()
        conn.close()

    def update_order_status(
        self,
        client_order_id: str,
        status: str,
        alpaca_order_id: Optional[str] = None,
        error_message: Optional[str] = None,
    ):
        """Update order status."""
        conn = self._get_connection()
        cursor = conn.cursor()

        update_fields = ["status = ?"]
        params = [status]

        if alpaca_order_id:
            update_fields.append("alpaca_order_id = ?")
            params.append(alpaca_order_id)

        if status == "filled":
            update_fields.append("filled_at = ?")
            params.append(datetime.utcnow())
        elif status == "canceled":
            update_fields.append("canceled_at = ?")
            params.append(datetime.utcnow())

        if error_message:
            update_fields.append("error_message = ?")
            params.append(error_message)

        params.append(client_order_id)

        cursor.execute(
            f"UPDATE orders SET {', '.join(update_fields)} WHERE client_order_id = ?",
            params
        )

        conn.commit()
        conn.close()

    def write_fill(
        self,
        client_order_id: str,
        symbol: str,
        qty: float,
        price: float,
        fee: float = 0.0,
    ):
        """Write fill to database."""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO fills (client_order_id, symbol, qty, price, fee, filled_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            client_order_id,
            symbol,
            qty,
            price,
            fee,
            datetime.utcnow(),
        ))

        conn.commit()
        conn.close()

    def write_snapshot(
        self,
        symbol: str,
        qty: float,
        avg_entry: float,
        unrealized_pnl: float = 0.0,
        timestamp: Optional[datetime] = None,
    ):
        """Write position snapshot."""
        if timestamp is None:
            timestamp = datetime.utcnow()

        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT OR REPLACE INTO position_snapshots (symbol, qty, avg_entry, unrealized_pnl, timestamp)
            VALUES (?, ?, ?, ?, ?)
        """, (symbol, qty, avg_entry, unrealized_pnl, timestamp))

        conn.commit()
        conn.close()

    def write_backtest_run(
        self,
        strategy_name: str,
        start_date: datetime,
        end_date: datetime,
        params: dict[str, Any],
        metrics: Optional[dict[str, Any]] = None,
    ) -> int:
        """Write backtest run and return run_id."""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO backtest_runs (strategy_name, start_date, end_date, params_json, metrics_json)
            VALUES (?, ?, ?, ?, ?)
        """, (
            strategy_name,
            start_date.date(),
            end_date.date(),
            json.dumps(params),
            json.dumps(metrics) if metrics else None,
        ))

        run_id = cursor.lastrowid
        conn.commit()
        conn.close()

        return run_id

    def write_backtest_trade(
        self,
        run_id: int,
        symbol: str,
        side: str,
        qty: float,
        price: float,
        timestamp: datetime,
    ):
        """Write backtest trade."""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO backtest_trades (run_id, symbol, side, qty, price, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (run_id, symbol, side, qty, price, timestamp))

        conn.commit()
        conn.close()

    def get_open_orders(self, symbol: Optional[str] = None) -> list[dict[str, Any]]:
        """Get open orders."""
        conn = self._get_connection()
        cursor = conn.cursor()

        if symbol:
            cursor.execute("""
                SELECT * FROM orders
                WHERE status IN ('submitted', 'accepted', 'pending_new', 'pending_replace')
                AND symbol = ?
                ORDER BY submitted_at DESC
            """, (symbol,))
        else:
            cursor.execute("""
                SELECT * FROM orders
                WHERE status IN ('submitted', 'accepted', 'pending_new', 'pending_replace')
                ORDER BY submitted_at DESC
            """)

        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]

    def get_positions(self) -> dict[str, dict[str, Any]]:
        """Get latest position snapshots for each symbol."""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT symbol, qty, avg_entry, unrealized_pnl, timestamp
            FROM position_snapshots
            WHERE (symbol, timestamp) IN (
                SELECT symbol, MAX(timestamp) FROM position_snapshots GROUP BY symbol
            )
            AND qty != 0
        """)

        rows = cursor.fetchall()
        conn.close()

        return {row["symbol"]: dict(row) for row in rows}


# Global storage instance
_storage: Optional[Storage] = None


def get_storage() -> Storage:
    """Get global storage instance."""
    global _storage
    if _storage is None:
        _storage = Storage()
    return _storage









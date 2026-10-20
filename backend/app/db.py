"""SQLite data-access layer (aiosqlite).

Owns schema initialization, default seeding, and all row-level queries for the
five tables in PLAN.md section 7. One shared connection is used for the whole
app; aiosqlite serializes operations on it, so concurrent background writers
(price cache, snapshot task) and request handlers do not corrupt each other.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import aiosqlite

DEFAULT_USER = "default"
STARTING_CASH = 1000000.0
SCHEMA_PATH = Path(__file__).resolve().parents[1] / "db" / "schema.sql"

# Default watchlist, inserted with strictly increasing added_at so that
# ORDER BY added_at ASC reproduces this exact order (section 7).
SEED_WATCHLIST = [
    "HEROMOTOCO", "BEL", "PIDILITIND", "LTF", "HDFCBANK",
    "INFY", "RELIANCE", "TCS", "ICICIBANK", "TATAMOTORS",
]


def now_iso() -> str:
    """Current time as a UTC ISO-8601 string (section 7)."""
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return str(uuid.uuid4())


class Database:
    """Async wrapper over a single aiosqlite connection."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._conn: aiosqlite.Connection | None = None

    @property
    def conn(self) -> aiosqlite.Connection:
        assert self._conn is not None, "Database not connected"
        return self._conn

    async def connect(self) -> None:
        """Open the connection, create the schema, and seed defaults if empty."""
        self._conn = await aiosqlite.connect(self._path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.executescript(SCHEMA_PATH.read_text())
        await self._conn.commit()
        await self._seed_if_empty()

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    async def _seed_if_empty(self) -> None:
        async with self._conn.execute("SELECT COUNT(*) FROM users_profile") as cur:
            (count,) = await cur.fetchone()
        if count:
            return
        await self._conn.execute(
            "INSERT INTO users_profile (id, cash_balance, created_at) VALUES (?, ?, ?)",
            (DEFAULT_USER, STARTING_CASH, now_iso()),
        )
        await self._seed_watchlist()
        await self._conn.commit()

    async def _seed_watchlist(self) -> None:
        """Insert the default watchlist with strictly increasing added_at."""
        base = datetime.now(timezone.utc)
        for i, ticker in enumerate(SEED_WATCHLIST):
            added_at = (base + timedelta(milliseconds=i)).isoformat()
            await self._conn.execute(
                "INSERT INTO watchlist (id, user_id, ticker, added_at) VALUES (?, ?, ?, ?)",
                (_new_id(), DEFAULT_USER, ticker, added_at),
            )

    async def clear_chat(self) -> None:
        """Delete all chat messages (called at startup so each run begins blank)."""
        await self.conn.execute(
            "DELETE FROM chat_messages WHERE user_id = ?", (DEFAULT_USER,)
        )
        await self.conn.commit()

    async def reset_to_defaults(self) -> None:
        """Restore first-launch state: Rs 10 lakh cash, default watchlist, and no
        positions, trades, snapshots, or chat (section: Reset feature)."""
        await self.conn.execute("DELETE FROM positions WHERE user_id = ?", (DEFAULT_USER,))
        await self.conn.execute("DELETE FROM trades WHERE user_id = ?", (DEFAULT_USER,))
        await self.conn.execute(
            "DELETE FROM portfolio_snapshots WHERE user_id = ?", (DEFAULT_USER,)
        )
        await self.conn.execute("DELETE FROM chat_messages WHERE user_id = ?", (DEFAULT_USER,))
        await self.conn.execute("DELETE FROM watchlist WHERE user_id = ?", (DEFAULT_USER,))
        await self.conn.execute(
            "UPDATE users_profile SET cash_balance = ? WHERE id = ?",
            (STARTING_CASH, DEFAULT_USER),
        )
        await self._seed_watchlist()
        await self.conn.commit()

    # --- Profile ---

    async def get_cash(self) -> float:
        async with self.conn.execute(
            "SELECT cash_balance FROM users_profile WHERE id = ?", (DEFAULT_USER,)
        ) as cur:
            row = await cur.fetchone()
        return row["cash_balance"]

    async def set_cash(self, cash: float) -> None:
        await self.conn.execute(
            "UPDATE users_profile SET cash_balance = ? WHERE id = ?", (cash, DEFAULT_USER)
        )
        await self.conn.commit()

    # --- Watchlist ---

    async def list_watchlist(self) -> list[str]:
        async with self.conn.execute(
            "SELECT ticker FROM watchlist WHERE user_id = ? ORDER BY added_at ASC",
            (DEFAULT_USER,),
        ) as cur:
            rows = await cur.fetchall()
        return [r["ticker"] for r in rows]

    async def watchlist_added_at(self, ticker: str) -> str | None:
        async with self.conn.execute(
            "SELECT added_at FROM watchlist WHERE user_id = ? AND ticker = ?",
            (DEFAULT_USER, ticker),
        ) as cur:
            row = await cur.fetchone()
        return row["added_at"] if row else None

    async def add_watchlist(self, ticker: str) -> str:
        """Insert a watchlist row and return its added_at (idempotent)."""
        existing = await self.watchlist_added_at(ticker)
        if existing is not None:
            return existing
        added_at = now_iso()
        await self.conn.execute(
            "INSERT INTO watchlist (id, user_id, ticker, added_at) VALUES (?, ?, ?, ?)",
            (_new_id(), DEFAULT_USER, ticker, added_at),
        )
        await self.conn.commit()
        return added_at

    async def remove_watchlist(self, ticker: str) -> bool:
        """Delete a watchlist row. Returns True if a row was actually removed."""
        cur = await self.conn.execute(
            "DELETE FROM watchlist WHERE user_id = ? AND ticker = ?", (DEFAULT_USER, ticker)
        )
        await self.conn.commit()
        return cur.rowcount > 0

    # --- Positions ---

    async def list_positions(self) -> list[dict]:
        async with self.conn.execute(
            "SELECT ticker, quantity, avg_cost FROM positions WHERE user_id = ? ORDER BY ticker",
            (DEFAULT_USER,),
        ) as cur:
            rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def get_position(self, ticker: str) -> dict | None:
        async with self.conn.execute(
            "SELECT ticker, quantity, avg_cost FROM positions WHERE user_id = ? AND ticker = ?",
            (DEFAULT_USER, ticker),
        ) as cur:
            row = await cur.fetchone()
        return dict(row) if row else None

    async def upsert_position(self, ticker: str, quantity: float, avg_cost: float) -> None:
        await self.conn.execute(
            """INSERT INTO positions (id, user_id, ticker, quantity, avg_cost, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(user_id, ticker)
               DO UPDATE SET quantity = excluded.quantity,
                             avg_cost = excluded.avg_cost,
                             updated_at = excluded.updated_at""",
            (_new_id(), DEFAULT_USER, ticker, quantity, avg_cost, now_iso()),
        )
        await self.conn.commit()

    async def delete_position(self, ticker: str) -> None:
        await self.conn.execute(
            "DELETE FROM positions WHERE user_id = ? AND ticker = ?", (DEFAULT_USER, ticker)
        )
        await self.conn.commit()

    # --- Trades ---

    async def insert_trade(
        self, ticker: str, side: str, quantity: float, price: float
    ) -> dict:
        trade = {
            "id": _new_id(),
            "ticker": ticker,
            "side": side,
            "quantity": quantity,
            "price": price,
            "executed_at": now_iso(),
        }
        await self.conn.execute(
            """INSERT INTO trades (id, user_id, ticker, side, quantity, price, executed_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (trade["id"], DEFAULT_USER, ticker, side, quantity, price, trade["executed_at"]),
        )
        await self.conn.commit()
        return trade

    async def list_trades(self) -> list[dict]:
        async with self.conn.execute(
            """SELECT id, ticker, side, quantity, price, executed_at FROM trades
               WHERE user_id = ? ORDER BY executed_at DESC, rowid DESC""",
            (DEFAULT_USER,),
        ) as cur:
            rows = await cur.fetchall()
        return [dict(r) for r in rows]

    # --- Snapshots ---

    async def insert_snapshot(self, total_value: float) -> None:
        await self.conn.execute(
            "INSERT INTO portfolio_snapshots (id, user_id, total_value, recorded_at) VALUES (?, ?, ?, ?)",
            (_new_id(), DEFAULT_USER, total_value, now_iso()),
        )
        await self.conn.commit()

    async def list_snapshots(self) -> list[dict]:
        async with self.conn.execute(
            """SELECT total_value, recorded_at FROM portfolio_snapshots
               WHERE user_id = ? ORDER BY recorded_at ASC, rowid ASC""",
            (DEFAULT_USER,),
        ) as cur:
            rows = await cur.fetchall()
        return [dict(r) for r in rows]

    # --- Chat ---

    async def insert_chat(self, role: str, content: str, actions: list | None = None) -> None:
        await self.conn.execute(
            "INSERT INTO chat_messages (id, user_id, role, content, actions, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (
                _new_id(),
                DEFAULT_USER,
                role,
                content,
                json.dumps(actions) if actions is not None else None,
                now_iso(),
            ),
        )
        await self.conn.commit()

    async def list_chat(self, limit: int = 20) -> list[dict]:
        """Return the last `limit` chat rows, oldest first."""
        async with self.conn.execute(
            """SELECT role, content, actions, created_at FROM chat_messages
               WHERE user_id = ? ORDER BY created_at DESC, rowid DESC LIMIT ?""",
            (DEFAULT_USER, limit),
        ) as cur:
            rows = await cur.fetchall()
        result = []
        for r in reversed(rows):
            result.append(
                {
                    "role": r["role"],
                    "content": r["content"],
                    "actions": json.loads(r["actions"]) if r["actions"] else None,
                    "created_at": r["created_at"],
                }
            )
        return result

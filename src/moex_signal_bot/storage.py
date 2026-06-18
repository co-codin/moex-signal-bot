from __future__ import annotations

import datetime as dt
import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class WatchItem:
    chat_id: int
    ticker: str
    interval_minutes: int
    muted_until: dt.datetime | None
    created_at: dt.datetime
    last_checked_at: dt.datetime | None


class WatchlistStore:
    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._create_schema()

    def close(self) -> None:
        self._conn.close()

    def add_watch(
        self,
        chat_id: int,
        ticker: str,
        *,
        interval_minutes: int = 15,
        now: dt.datetime | None = None,
    ) -> None:
        now = _normalize_datetime(now)
        ticker = ticker.upper()
        interval_minutes = max(1, min(1440, int(interval_minutes)))
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO watchlist(chat_id, ticker, interval_minutes, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(chat_id, ticker)
                DO UPDATE SET interval_minutes = excluded.interval_minutes
                """,
                (chat_id, ticker, interval_minutes, _dump_datetime(now)),
            )

    def remove_watch(self, chat_id: int, ticker: str) -> bool:
        with self._conn:
            cursor = self._conn.execute(
                "DELETE FROM watchlist WHERE chat_id = ? AND ticker = ?",
                (chat_id, ticker.upper()),
            )
        return cursor.rowcount > 0

    def list_watch(self, chat_id: int) -> list[WatchItem]:
        rows = self._conn.execute(
            """
            SELECT chat_id, ticker, interval_minutes, muted_until, created_at, last_checked_at
            FROM watchlist
            WHERE chat_id = ?
            ORDER BY ticker
            """,
            (chat_id,),
        ).fetchall()
        return [_watch_item(row) for row in rows]

    def list_due(self, now: dt.datetime | None = None) -> list[WatchItem]:
        now = _normalize_datetime(now)
        rows = self._conn.execute(
            """
            SELECT chat_id, ticker, interval_minutes, muted_until, created_at, last_checked_at
            FROM watchlist
            ORDER BY chat_id, ticker
            """
        ).fetchall()
        items = [_watch_item(row) for row in rows]
        return [item for item in items if _is_due(item, now)]

    def mute(self, chat_id: int, ticker: str, muted_until: dt.datetime) -> None:
        muted_until = _normalize_datetime(muted_until)
        with self._conn:
            self._conn.execute(
                """
                UPDATE watchlist
                SET muted_until = ?
                WHERE chat_id = ? AND ticker = ?
                """,
                (_dump_datetime(muted_until), chat_id, ticker.upper()),
            )

    def is_muted(self, item: WatchItem, now: dt.datetime | None = None) -> bool:
        now = _normalize_datetime(now)
        return item.muted_until is not None and item.muted_until > now

    def mark_checked(self, chat_id: int, ticker: str, now: dt.datetime | None = None) -> None:
        now = _normalize_datetime(now)
        with self._conn:
            self._conn.execute(
                """
                UPDATE watchlist
                SET last_checked_at = ?
                WHERE chat_id = ? AND ticker = ?
                """,
                (_dump_datetime(now), chat_id, ticker.upper()),
            )

    def was_signal_sent(self, chat_id: int, ticker: str, signal_code: str, signal_key: str) -> bool:
        row = self._conn.execute(
            """
            SELECT 1
            FROM sent_signals
            WHERE chat_id = ? AND ticker = ? AND signal_code = ? AND signal_key = ?
            """,
            (chat_id, ticker.upper(), signal_code, signal_key),
        ).fetchone()
        return row is not None

    def mark_signal_sent(
        self,
        chat_id: int,
        ticker: str,
        signal_code: str,
        signal_key: str,
        sent_at: dt.datetime | None = None,
    ) -> None:
        sent_at = _normalize_datetime(sent_at)
        with self._conn:
            self._conn.execute(
                """
                INSERT OR IGNORE INTO sent_signals(chat_id, ticker, signal_code, signal_key, sent_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (chat_id, ticker.upper(), signal_code, signal_key, _dump_datetime(sent_at)),
            )

    def _create_schema(self) -> None:
        with self._conn:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS watchlist (
                    chat_id INTEGER NOT NULL,
                    ticker TEXT NOT NULL,
                    interval_minutes INTEGER NOT NULL,
                    muted_until TEXT,
                    created_at TEXT NOT NULL,
                    last_checked_at TEXT,
                    PRIMARY KEY(chat_id, ticker)
                )
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sent_signals (
                    chat_id INTEGER NOT NULL,
                    ticker TEXT NOT NULL,
                    signal_code TEXT NOT NULL,
                    signal_key TEXT NOT NULL,
                    sent_at TEXT NOT NULL,
                    PRIMARY KEY(chat_id, ticker, signal_code, signal_key)
                )
                """
            )


def _watch_item(row: sqlite3.Row) -> WatchItem:
    return WatchItem(
        chat_id=int(row["chat_id"]),
        ticker=str(row["ticker"]),
        interval_minutes=int(row["interval_minutes"]),
        muted_until=_load_datetime(row["muted_until"]),
        created_at=_load_datetime(row["created_at"]) or dt.datetime.now(dt.UTC),
        last_checked_at=_load_datetime(row["last_checked_at"]),
    )


def _is_due(item: WatchItem, now: dt.datetime) -> bool:
    if item.last_checked_at is None:
        return True
    return item.last_checked_at + dt.timedelta(minutes=item.interval_minutes) <= now


def _normalize_datetime(value: dt.datetime | None) -> dt.datetime:
    if value is None:
        return dt.datetime.now(dt.UTC)
    if value.tzinfo is None:
        return value.replace(tzinfo=dt.UTC)
    return value.astimezone(dt.UTC)


def _dump_datetime(value: dt.datetime) -> str:
    return _normalize_datetime(value).isoformat(timespec="seconds")


def _load_datetime(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    parsed = dt.datetime.fromisoformat(value)
    return _normalize_datetime(parsed)

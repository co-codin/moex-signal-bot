from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class WatchItem:
    chat_id: int
    ticker: str
    interval_minutes: int
    muted_until: dt.datetime | None
    created_at: dt.datetime
    last_checked_at: dt.datetime | None


@dataclass(frozen=True)
class ChatSettings:
    chat_id: int
    min_score: int = 60
    quiet_start: str | None = None
    quiet_end: str | None = None
    alert_types: tuple[str, ...] = ()


ALLOWED_ALERT_TYPES = (
    "sell_pressure",
    "absorption",
    "bullish_reversal",
    "weak_bounce",
    "breakdown",
    "reclaim",
    "megaalert_cluster",
)


class PostgresWatchlistStore:
    def __init__(self, database_url: str, *, connect: Callable[[str], Any] | None = None) -> None:
        if not database_url:
            raise RuntimeError("Не задана переменная окружения DATABASE_URL для PostgreSQL.")
        self.database_url = database_url
        self._conn = connect(database_url) if connect else _connect_postgres(database_url)
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
        self._write(
            """
            INSERT INTO watchlist(chat_id, ticker, interval_minutes, created_at)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT(chat_id, ticker)
            DO UPDATE SET interval_minutes = EXCLUDED.interval_minutes
            """,
            (chat_id, ticker, interval_minutes, _dump_datetime(now)),
        )

    def remove_watch(self, chat_id: int, ticker: str) -> bool:
        cursor = self._write(
            "DELETE FROM watchlist WHERE chat_id = %s AND ticker = %s",
            (chat_id, ticker.upper()),
        )
        return cursor.rowcount > 0

    def list_watch(self, chat_id: int) -> list[WatchItem]:
        rows = self._conn.execute(
            """
            SELECT chat_id, ticker, interval_minutes, muted_until, created_at, last_checked_at
            FROM watchlist
            WHERE chat_id = %s
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
        self._write(
            """
            UPDATE watchlist
            SET muted_until = %s
            WHERE chat_id = %s AND ticker = %s
            """,
            (_dump_datetime(muted_until), chat_id, ticker.upper()),
        )

    def is_muted(self, item: WatchItem, now: dt.datetime | None = None) -> bool:
        now = _normalize_datetime(now)
        return item.muted_until is not None and item.muted_until > now

    def mark_checked(self, chat_id: int, ticker: str, now: dt.datetime | None = None) -> None:
        now = _normalize_datetime(now)
        self._write(
            """
            UPDATE watchlist
            SET last_checked_at = %s
            WHERE chat_id = %s AND ticker = %s
            """,
            (_dump_datetime(now), chat_id, ticker.upper()),
        )

    def was_signal_sent(self, chat_id: int, ticker: str, signal_code: str, signal_key: str) -> bool:
        row = self._conn.execute(
            """
            SELECT 1
            FROM sent_signals
            WHERE chat_id = %s AND ticker = %s AND signal_code = %s AND signal_key = %s
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
        self._write(
            """
            INSERT INTO sent_signals(chat_id, ticker, signal_code, signal_key, sent_at)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT(chat_id, ticker, signal_code, signal_key) DO NOTHING
            """,
            (chat_id, ticker.upper(), signal_code, signal_key, _dump_datetime(sent_at)),
        )

    def get_settings(self, chat_id: int) -> ChatSettings:
        row = self._conn.execute(
            """
            SELECT chat_id, min_score, quiet_start, quiet_end, alert_types
            FROM chat_settings
            WHERE chat_id = %s
            """,
            (chat_id,),
        ).fetchone()
        if row is None:
            return ChatSettings(chat_id=chat_id)
        return ChatSettings(
            chat_id=int(row["chat_id"]),
            min_score=int(row["min_score"]),
            quiet_start=row["quiet_start"],
            quiet_end=row["quiet_end"],
            alert_types=_load_alert_types(row["alert_types"]),
        )

    def set_min_score(self, chat_id: int, min_score: int) -> None:
        min_score = max(0, min(100, int(min_score)))
        settings = self.get_settings(chat_id)
        self._write(
            """
            INSERT INTO chat_settings(chat_id, min_score, quiet_start, quiet_end, alert_types)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT(chat_id)
            DO UPDATE SET min_score = EXCLUDED.min_score
            """,
            (
                chat_id,
                min_score,
                settings.quiet_start,
                settings.quiet_end,
                _dump_alert_types(settings.alert_types),
            ),
        )

    def set_quiet_hours(self, chat_id: int, quiet_start: str | None, quiet_end: str | None) -> None:
        quiet_start = _normalize_time_value(quiet_start) if quiet_start else None
        quiet_end = _normalize_time_value(quiet_end) if quiet_end else None
        settings = self.get_settings(chat_id)
        self._write(
            """
            INSERT INTO chat_settings(chat_id, min_score, quiet_start, quiet_end, alert_types)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT(chat_id)
            DO UPDATE SET quiet_start = EXCLUDED.quiet_start,
                          quiet_end = EXCLUDED.quiet_end
            """,
            (
                chat_id,
                settings.min_score,
                quiet_start,
                quiet_end,
                _dump_alert_types(settings.alert_types),
            ),
        )

    def set_alert_types(self, chat_id: int, alert_types: tuple[str, ...]) -> None:
        normalized = _normalize_alert_types(alert_types)
        settings = self.get_settings(chat_id)
        self._write(
            """
            INSERT INTO chat_settings(chat_id, min_score, quiet_start, quiet_end, alert_types)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT(chat_id)
            DO UPDATE SET alert_types = EXCLUDED.alert_types
            """,
            (chat_id, settings.min_score, settings.quiet_start, settings.quiet_end, _dump_alert_types(normalized)),
        )

    def add_portfolio_ticker(self, chat_id: int, ticker: str, *, now: dt.datetime | None = None) -> None:
        now = _normalize_datetime(now)
        self._write(
            """
            INSERT INTO portfolio(chat_id, ticker, created_at)
            VALUES (%s, %s, %s)
            ON CONFLICT(chat_id, ticker) DO NOTHING
            """,
            (chat_id, ticker.upper(), _dump_datetime(now)),
        )

    def remove_portfolio_ticker(self, chat_id: int, ticker: str) -> bool:
        cursor = self._write(
            """
            DELETE FROM portfolio
            WHERE chat_id = %s AND ticker = %s
            """,
            (chat_id, ticker.upper()),
        )
        return cursor.rowcount > 0

    def list_portfolio(self, chat_id: int) -> list[str]:
        rows = self._conn.execute(
            """
            SELECT ticker
            FROM portfolio
            WHERE chat_id = %s
            ORDER BY created_at, ticker
            """,
            (chat_id,),
        ).fetchall()
        return [str(row["ticker"]) for row in rows]

    def _write(self, sql: str, params: tuple[Any, ...]) -> Any:
        cursor = self._conn.execute(sql, params)
        self._conn.commit()
        return cursor

    def _create_schema(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS watchlist (
                chat_id BIGINT NOT NULL,
                ticker TEXT NOT NULL,
                interval_minutes INTEGER NOT NULL,
                muted_until TIMESTAMPTZ,
                created_at TIMESTAMPTZ NOT NULL,
                last_checked_at TIMESTAMPTZ,
                PRIMARY KEY(chat_id, ticker)
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_settings (
                chat_id BIGINT PRIMARY KEY,
                min_score INTEGER NOT NULL DEFAULT 60,
                quiet_start TEXT,
                quiet_end TEXT,
                alert_types TEXT NOT NULL DEFAULT ''
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS portfolio (
                chat_id BIGINT NOT NULL,
                ticker TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL,
                PRIMARY KEY(chat_id, ticker)
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sent_signals (
                chat_id BIGINT NOT NULL,
                ticker TEXT NOT NULL,
                signal_code TEXT NOT NULL,
                signal_key TEXT NOT NULL,
                sent_at TIMESTAMPTZ NOT NULL,
                PRIMARY KEY(chat_id, ticker, signal_code, signal_key)
            )
            """
        )
        self._conn.commit()


WatchlistStore = PostgresWatchlistStore


def _connect_postgres(database_url: str) -> Any:
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ModuleNotFoundError as exc:
        raise RuntimeError("Не установлен PostgreSQL-драйвер psycopg. Выполните pip install -e .") from exc
    return psycopg.connect(database_url, row_factory=dict_row)


def _watch_item(row: Mapping[str, Any]) -> WatchItem:
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


def _dump_datetime(value: dt.datetime) -> dt.datetime:
    return _normalize_datetime(value)


def _load_datetime(value: dt.datetime | str | None) -> dt.datetime | None:
    if not value:
        return None
    parsed = dt.datetime.fromisoformat(value) if isinstance(value, str) else value
    return _normalize_datetime(parsed)


def _dump_alert_types(values: tuple[str, ...]) -> str:
    return ",".join(values)


def _load_alert_types(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(item for item in value.split(",") if item)


def _normalize_alert_types(values: tuple[str, ...]) -> tuple[str, ...]:
    lowered = tuple(item.strip().lower() for item in values if item.strip())
    if lowered in {("all",), ("reset",), ("все",)}:
        return ()
    unknown = tuple(item for item in lowered if item not in ALLOWED_ALERT_TYPES)
    if unknown:
        allowed = ", ".join(ALLOWED_ALERT_TYPES)
        raise ValueError(f"Неизвестный тип автосигнала: {', '.join(unknown)}. Доступно: {allowed}.")
    return tuple(sorted(set(lowered)))


def _normalize_time_value(value: str) -> str:
    try:
        parsed = dt.time.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("Неверный формат времени. Используйте HH:MM, например 23:00.") from exc
    return parsed.strftime("%H:%M")

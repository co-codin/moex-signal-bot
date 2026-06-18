from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from .access_control import AccessStatus, TelegramUser, normalize_access_status


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

    def list_watch_by_ticker(self, ticker: str) -> list[WatchItem]:
        rows = self._conn.execute(
            """
            SELECT chat_id, ticker, interval_minutes, muted_until, created_at, last_checked_at
            FROM watchlist
            WHERE ticker = %s
            ORDER BY chat_id, ticker
            """,
            (ticker.upper(),),
        ).fetchall()
        return [_watch_item(row) for row in rows]

    def list_due(self, now: dt.datetime | None = None) -> list[WatchItem]:
        now = _normalize_datetime(now)
        rows = self._conn.execute(
            """
            SELECT chat_id, ticker, interval_minutes, muted_until, created_at, last_checked_at
            FROM watchlist
            WHERE last_checked_at IS NULL
               OR last_checked_at + (interval_minutes * INTERVAL '1 minute') <= %s
            ORDER BY chat_id, ticker
            """,
            (_dump_datetime(now),),
        ).fetchall()
        return [_watch_item(row) for row in rows]

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
              AND status = 'sent'
            """,
            (chat_id, ticker.upper(), signal_code, signal_key),
        ).fetchone()
        return row is not None

    def reserve_signal(
        self,
        chat_id: int,
        ticker: str,
        signal_code: str,
        signal_key: str,
        reserved_at: dt.datetime | None = None,
    ) -> bool:
        reserved_at = _normalize_datetime(reserved_at)
        cursor = self._write(
            """
            INSERT INTO sent_signals(chat_id, ticker, signal_code, signal_key, sent_at, status)
            VALUES (%s, %s, %s, %s, %s, 'reserved')
            ON CONFLICT(chat_id, ticker, signal_code, signal_key) DO NOTHING
            """,
            (chat_id, ticker.upper(), signal_code, signal_key, _dump_datetime(reserved_at)),
        )
        return cursor.rowcount > 0

    def release_signal_reservation(self, chat_id: int, ticker: str, signal_code: str, signal_key: str) -> None:
        self._write(
            """
            DELETE FROM sent_signals
            WHERE chat_id = %s
              AND ticker = %s
              AND signal_code = %s
              AND signal_key = %s
              AND status = 'reserved'
            """,
            (chat_id, ticker.upper(), signal_code, signal_key),
        )

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
            INSERT INTO sent_signals(chat_id, ticker, signal_code, signal_key, sent_at, status)
            VALUES (%s, %s, %s, %s, %s, 'sent')
            ON CONFLICT(chat_id, ticker, signal_code, signal_key)
            DO UPDATE SET sent_at = EXCLUDED.sent_at,
                          status = 'sent'
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

    def record_telegram_user(
        self,
        chat_id: int,
        *,
        username: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
        status: AccessStatus = "pending",
        now: dt.datetime | None = None,
    ) -> None:
        now = _normalize_datetime(now)
        status = normalize_access_status(status)
        self._write(
            """
            INSERT INTO telegram_users(
                chat_id, username, first_name, last_name, status, note, first_seen_at, last_seen_at
            )
            VALUES (%s, %s, %s, %s, %s, '', %s, %s)
            ON CONFLICT(chat_id)
            DO UPDATE SET username = EXCLUDED.username,
                          first_name = EXCLUDED.first_name,
                          last_name = EXCLUDED.last_name,
                          last_seen_at = EXCLUDED.last_seen_at,
                          status = CASE
                              WHEN EXCLUDED.status = 'allowed' THEN 'allowed'
                              ELSE telegram_users.status
                          END
            """,
            (int(chat_id), username, first_name, last_name, status, _dump_datetime(now), _dump_datetime(now)),
        )

    def get_telegram_user(self, chat_id: int) -> TelegramUser | None:
        row = self._conn.execute(
            """
            SELECT chat_id, username, first_name, last_name, status, note, first_seen_at, last_seen_at
            FROM telegram_users
            WHERE chat_id = %s
            """,
            (int(chat_id),),
        ).fetchone()
        return _telegram_user(row) if row is not None else None

    def list_telegram_users(self, *, status: str | None = None, search: str | None = None) -> list[TelegramUser]:
        normalized_status = normalize_access_status(status) if status else None
        rows = self._conn.execute(
            """
            SELECT chat_id, username, first_name, last_name, status, note, first_seen_at, last_seen_at
            FROM telegram_users
            ORDER BY last_seen_at DESC, chat_id DESC
            """
        ).fetchall()
        users = [_telegram_user(row) for row in rows]
        if normalized_status:
            users = [user for user in users if user.status == normalized_status]
        search_text = search.strip().lower() if search else ""
        if search_text:
            users = [user for user in users if _telegram_user_matches(user, search_text)]
        return users

    def set_telegram_user_status(self, chat_id: int, status: str) -> None:
        status = normalize_access_status(status)
        now = _normalize_datetime(None)
        self._write(
            """
            INSERT INTO telegram_users(chat_id, status, note, first_seen_at, last_seen_at)
            VALUES (%s, %s, '', %s, %s)
            ON CONFLICT(chat_id)
            DO UPDATE SET status = EXCLUDED.status
            """,
            (int(chat_id), status, _dump_datetime(now), _dump_datetime(now)),
        )

    def set_telegram_user_note(self, chat_id: int, note: str) -> None:
        now = _normalize_datetime(None)
        self._write(
            """
            INSERT INTO telegram_users(chat_id, status, note, first_seen_at, last_seen_at)
            VALUES (%s, 'pending', %s, %s, %s)
            ON CONFLICT(chat_id)
            DO UPDATE SET note = EXCLUDED.note
            """,
            (int(chat_id), note.strip(), _dump_datetime(now), _dump_datetime(now)),
        )

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
                status TEXT NOT NULL DEFAULT 'sent',
                PRIMARY KEY(chat_id, ticker, signal_code, signal_key)
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS telegram_users (
                chat_id BIGINT PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                note TEXT NOT NULL DEFAULT '',
                first_seen_at TIMESTAMPTZ NOT NULL,
                last_seen_at TIMESTAMPTZ NOT NULL
            )
            """
        )
        self._conn.execute(
            """
            CREATE INDEX IF NOT EXISTS telegram_users_status_idx
            ON telegram_users(status)
            """
        )
        self._conn.execute(
            """
            ALTER TABLE sent_signals
            ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'sent'
            """
        )
        self._conn.execute(
            """
            CREATE INDEX IF NOT EXISTS watchlist_due_idx
            ON watchlist(last_checked_at)
            """
        )
        self._conn.execute(
            """
            CREATE INDEX IF NOT EXISTS watchlist_ticker_idx
            ON watchlist(ticker)
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


def _telegram_user(row: Mapping[str, Any]) -> TelegramUser:
    return TelegramUser(
        chat_id=int(row["chat_id"]),
        username=row["username"],
        first_name=row["first_name"],
        last_name=row["last_name"],
        status=normalize_access_status(row["status"]),
        note=str(row["note"] or ""),
        first_seen_at=_load_datetime(row["first_seen_at"]),
        last_seen_at=_load_datetime(row["last_seen_at"]),
    )


def _telegram_user_matches(user: TelegramUser, search: str) -> bool:
    fields = (
        str(user.chat_id),
        user.username or "",
        user.first_name or "",
        user.last_name or "",
        user.note,
    )
    return any(search in field.lower() for field in fields)


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

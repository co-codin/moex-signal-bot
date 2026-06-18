from __future__ import annotations

import datetime as dt

from .storage import (
    ChatSettings,
    WatchItem,
    _dump_alert_types,
    _is_due,
    _load_alert_types,
    _normalize_alert_types,
    _normalize_datetime,
    _normalize_time_value,
)


class InMemoryWatchlistStore:
    def __init__(self) -> None:
        self._watch: dict[tuple[int, str], WatchItem] = {}
        self._settings: dict[int, ChatSettings] = {}
        self._sent_signals: set[tuple[int, str, str, str]] = set()
        self._portfolio: dict[tuple[int, str], dt.datetime] = {}

    def close(self) -> None:
        return None

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
        key = (chat_id, ticker)
        existing = self._watch.get(key)
        self._watch[key] = WatchItem(
            chat_id=chat_id,
            ticker=ticker,
            interval_minutes=interval_minutes,
            muted_until=existing.muted_until if existing else None,
            created_at=existing.created_at if existing else now,
            last_checked_at=existing.last_checked_at if existing else None,
        )

    def remove_watch(self, chat_id: int, ticker: str) -> bool:
        return self._watch.pop((chat_id, ticker.upper()), None) is not None

    def list_watch(self, chat_id: int) -> list[WatchItem]:
        return sorted((item for item in self._watch.values() if item.chat_id == chat_id), key=lambda item: item.ticker)

    def list_due(self, now: dt.datetime | None = None) -> list[WatchItem]:
        now = _normalize_datetime(now)
        items = sorted(self._watch.values(), key=lambda item: (item.chat_id, item.ticker))
        return [item for item in items if _is_due(item, now)]

    def mute(self, chat_id: int, ticker: str, muted_until: dt.datetime) -> None:
        key = (chat_id, ticker.upper())
        item = self._watch.get(key)
        if item is None:
            return
        self._watch[key] = WatchItem(
            chat_id=item.chat_id,
            ticker=item.ticker,
            interval_minutes=item.interval_minutes,
            muted_until=_normalize_datetime(muted_until),
            created_at=item.created_at,
            last_checked_at=item.last_checked_at,
        )

    def is_muted(self, item: WatchItem, now: dt.datetime | None = None) -> bool:
        now = _normalize_datetime(now)
        return item.muted_until is not None and item.muted_until > now

    def mark_checked(self, chat_id: int, ticker: str, now: dt.datetime | None = None) -> None:
        key = (chat_id, ticker.upper())
        item = self._watch.get(key)
        if item is None:
            return
        self._watch[key] = WatchItem(
            chat_id=item.chat_id,
            ticker=item.ticker,
            interval_minutes=item.interval_minutes,
            muted_until=item.muted_until,
            created_at=item.created_at,
            last_checked_at=_normalize_datetime(now),
        )

    def was_signal_sent(self, chat_id: int, ticker: str, signal_code: str, signal_key: str) -> bool:
        return (chat_id, ticker.upper(), signal_code, signal_key) in self._sent_signals

    def mark_signal_sent(
        self,
        chat_id: int,
        ticker: str,
        signal_code: str,
        signal_key: str,
        sent_at: dt.datetime | None = None,
    ) -> None:
        _normalize_datetime(sent_at)
        self._sent_signals.add((chat_id, ticker.upper(), signal_code, signal_key))

    def get_settings(self, chat_id: int) -> ChatSettings:
        return self._settings.get(chat_id, ChatSettings(chat_id=chat_id))

    def set_min_score(self, chat_id: int, min_score: int) -> None:
        min_score = max(0, min(100, int(min_score)))
        settings = self.get_settings(chat_id)
        self._settings[chat_id] = ChatSettings(
            chat_id=chat_id,
            min_score=min_score,
            quiet_start=settings.quiet_start,
            quiet_end=settings.quiet_end,
            alert_types=settings.alert_types,
        )

    def set_quiet_hours(self, chat_id: int, quiet_start: str | None, quiet_end: str | None) -> None:
        quiet_start = _normalize_time_value(quiet_start) if quiet_start else None
        quiet_end = _normalize_time_value(quiet_end) if quiet_end else None
        settings = self.get_settings(chat_id)
        self._settings[chat_id] = ChatSettings(
            chat_id=chat_id,
            min_score=settings.min_score,
            quiet_start=quiet_start,
            quiet_end=quiet_end,
            alert_types=settings.alert_types,
        )

    def set_alert_types(self, chat_id: int, alert_types: tuple[str, ...]) -> None:
        normalized = _normalize_alert_types(alert_types)
        settings = self.get_settings(chat_id)
        self._settings[chat_id] = ChatSettings(
            chat_id=chat_id,
            min_score=settings.min_score,
            quiet_start=settings.quiet_start,
            quiet_end=settings.quiet_end,
            alert_types=_load_alert_types(_dump_alert_types(normalized)),
        )

    def add_portfolio_ticker(self, chat_id: int, ticker: str, *, now: dt.datetime | None = None) -> None:
        self._portfolio.setdefault((chat_id, ticker.upper()), _normalize_datetime(now))

    def remove_portfolio_ticker(self, chat_id: int, ticker: str) -> bool:
        return self._portfolio.pop((chat_id, ticker.upper()), None) is not None

    def list_portfolio(self, chat_id: int) -> list[str]:
        rows = [
            (ticker, created_at)
            for (item_chat_id, ticker), created_at in self._portfolio.items()
            if item_chat_id == chat_id
        ]
        return [ticker for ticker, _ in sorted(rows, key=lambda item: (item[1], item[0]))]

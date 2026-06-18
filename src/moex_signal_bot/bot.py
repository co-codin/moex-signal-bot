from __future__ import annotations

import datetime as dt
import os
from dataclasses import dataclass
from typing import Protocol

from .analytics import build_flow_statistics, build_heatmap, summarize_mega_alerts
from .formatters import (
    format_channel_signal,
    format_digest,
    format_flow_report,
    format_flow_statistics,
    format_full_report,
    format_futoi_summary,
    format_heatmap,
    format_help,
    format_mega_alert_summaries,
    format_portfolio,
    format_portfolio_risk,
    format_quote_report,
    format_scan_results,
    format_settings,
    format_signal_report,
    format_strategy_report,
    format_watchlist,
)
from .futoi import summarize_futoi
from .portfolio import build_portfolio_risk
from .scanner import build_signal_report, scan_tickers
from .signals import classify_from_days, summarize_daily_flow
from .storage import WatchlistStore


@dataclass(frozen=True)
class Command:
    name: str
    ticker: str | None
    days: int = 1
    tickers: tuple[str, ...] = ()
    minutes: int | None = None
    args: tuple[str, ...] = ()


class MarketProvider(Protocol):
    async def tradestats(self, ticker: str, start: str, end: str) -> list[dict]: ...

    async def orderstats(self, ticker: str, start: str, end: str) -> list[dict]: ...

    async def obstats(self, ticker: str, start: str, end: str) -> list[dict]: ...

    async def alerts(self, ticker: str, start: str, end: str) -> list[dict]: ...

    async def futoi(self, ticker: str, start: str, end: str) -> list[dict]: ...

    async def quote(self, ticker: str) -> dict: ...


def parse_command(text: str) -> Command:
    parts = text.strip().split()
    if not parts or not parts[0].startswith("/"):
        return Command(name="help", ticker=None, days=1)

    name = parts[0].removeprefix("/").split("@", 1)[0].lower()
    if name == "start":
        name = "help"
    if name not in {
        "help",
        "quote",
        "flow",
        "strategy",
        "book",
        "orders",
        "alerts",
        "signal",
        "scan",
        "full",
        "watch",
        "unwatch",
        "watchlist",
        "mute",
        "settings",
        "score",
        "quiet",
        "types",
        "heatmap",
        "mega",
        "digest",
        "futoi",
        "stats",
        "portfolio_add",
        "portfolio_remove",
        "portfolio",
        "portfolio_risk",
        "channel_signal",
    }:
        return Command(name="help", ticker=None, days=1)

    if name in {"watchlist", "settings", "portfolio", "portfolio_risk"}:
        return Command(name=name, ticker=None)
    if name in {"score", "quiet", "types"}:
        return Command(name=name, ticker=None, args=tuple(parts[1:]))

    ticker = parts[1].upper() if len(parts) >= 2 else None
    tickers = tuple(part.upper() for part in parts[1:] if not part.startswith("/"))
    minutes = None
    days = 7 if name == "strategy" else 1
    if name == "scan":
        return Command(name=name, ticker=ticker, tickers=tickers)
    if name in {"heatmap", "mega", "digest"}:
        return Command(name=name, ticker=ticker, tickers=tickers)
    if name in {"portfolio_add", "portfolio_remove", "futoi", "channel_signal"}:
        return Command(name=name, ticker=ticker)
    if name == "watch":
        minutes = _parse_minutes(parts[2] if len(parts) >= 3 else None, default=15)
        return Command(name=name, ticker=ticker, minutes=minutes)
    if name == "mute":
        minutes = _parse_minutes(parts[2] if len(parts) >= 3 else None, default=60)
        return Command(name=name, ticker=ticker, minutes=minutes)
    if len(parts) >= 3 and name in {"flow", "strategy"}:
        try:
            days = max(1, min(30, int(parts[2])))
        except ValueError:
            days = 1
    if len(parts) >= 3 and name == "stats":
        try:
            days = max(2, min(120, int(parts[2])))
        except ValueError:
            days = 30
    return Command(name=name, ticker=ticker, days=days)


async def handle_command(
    text: str,
    provider: MarketProvider,
    *,
    store: WatchlistStore | None = None,
    chat_id: int | None = None,
    now: dt.datetime | None = None,
    today: dt.date | None = None,
) -> str:
    command = parse_command(text)
    now = _normalize_datetime(now)
    if command.name == "help":
        return format_help()
    if command.name == "watchlist":
        if store is None or chat_id is None:
            return "Watchlist недоступен: нет локального хранилища или chat_id."
        return format_watchlist(store.list_watch(chat_id))
    if command.name == "settings":
        if store is None or chat_id is None:
            return "Настройки недоступны: нет локального хранилища или chat_id."
        return format_settings(store.get_settings(chat_id))
    if command.name == "score":
        if store is None or chat_id is None:
            return "Настройки недоступны: нет локального хранилища или chat_id."
        score = _parse_score(command.args[0] if command.args else None)
        store.set_min_score(chat_id, score)
        return f"Минимальная сила: {score}/100."
    if command.name == "quiet":
        if store is None or chat_id is None:
            return "Настройки недоступны: нет локального хранилища или chat_id."
        if len(command.args) < 2:
            return "Укажите тихие часы: /quiet 23:00 07:00."
        store.set_quiet_hours(chat_id, command.args[0], command.args[1])
        return f"Тихие часы: {command.args[0]}-{command.args[1]}."
    if command.name == "types":
        if store is None or chat_id is None:
            return "Настройки недоступны: нет локального хранилища или chat_id."
        store.set_alert_types(chat_id, tuple(command.args))
        return "Типы автосигналов: " + (", ".join(sorted(command.args)) if command.args else "все")
    if command.name == "portfolio":
        if store is None or chat_id is None:
            return "Портфель недоступен: нет локального хранилища или chat_id."
        return format_portfolio(store.list_portfolio(chat_id))
    if command.name == "portfolio_risk":
        if store is None or chat_id is None:
            return "Портфель недоступен: нет локального хранилища или chat_id."
        tickers = tuple(store.list_portfolio(chat_id))
        if not tickers:
            return format_portfolio_risk(build_portfolio_risk([]))
        reports = await scan_tickers(provider, tickers, today=today or dt.date.today())
        return format_portfolio_risk(build_portfolio_risk(reports))
    if not command.ticker:
        if command.name in {"heatmap", "mega", "digest"}:
            command = Command(name=command.name, ticker=None, tickers=_default_tickers())
        else:
            return format_help()

    if command.name == "watch":
        if store is None or chat_id is None:
            return "Автосканер недоступен: нет локального хранилища или chat_id."
        minutes = command.minutes or 15
        store.add_watch(chat_id, command.ticker, interval_minutes=minutes, now=now)
        return f"{command.ticker} добавлен в автосканер. Интервал: {minutes} мин."

    if command.name == "unwatch":
        if store is None or chat_id is None:
            return "Автосканер недоступен: нет локального хранилища или chat_id."
        removed = store.remove_watch(chat_id, command.ticker)
        if removed:
            return f"{command.ticker} удален из автосканера."
        return f"{command.ticker} не найден в watchlist."

    if command.name == "mute":
        if store is None or chat_id is None:
            return "Автосканер недоступен: нет локального хранилища или chat_id."
        minutes = command.minutes or 60
        muted_until = now + dt.timedelta(minutes=minutes)
        store.mute(chat_id, command.ticker, muted_until)
        return f"Пауза для {command.ticker}: {minutes} мин."

    if command.name == "portfolio_add":
        if store is None or chat_id is None:
            return "Портфель недоступен: нет локального хранилища или chat_id."
        store.add_portfolio_ticker(chat_id, command.ticker, now=now)
        return f"{command.ticker} добавлен в портфель."

    if command.name == "portfolio_remove":
        if store is None or chat_id is None:
            return "Портфель недоступен: нет локального хранилища или chat_id."
        removed = store.remove_portfolio_ticker(chat_id, command.ticker)
        if removed:
            return f"{command.ticker} удален из портфеля."
        return f"{command.ticker} не найден в портфеле."

    end = today or dt.date.today()
    start = end - dt.timedelta(days=command.days - 1)
    start_s = start.isoformat()
    end_s = end.isoformat()

    if command.name == "quote":
        return format_quote_report(command.ticker, await provider.quote(command.ticker))

    if command.name == "flow":
        rows = await provider.tradestats(command.ticker, start_s, end_s)
        return format_flow_report(command.ticker, summarize_daily_flow(rows))

    if command.name == "strategy":
        rows = await provider.tradestats(command.ticker, start_s, end_s)
        days = summarize_daily_flow(rows)
        state = classify_from_days(days)
        support = min((day.close_price for day in days), default=None)
        reclaim = max((day.open_price for day in days[-3:]), default=None) if days else None
        return format_strategy_report(command.ticker, state, support=support, reclaim=reclaim)

    if command.name == "signal":
        report = await _signal_report(provider, command.ticker, start_s, end_s)
        return format_signal_report(report)

    if command.name == "scan":
        reports = await scan_tickers(provider, command.tickers or (command.ticker,), today=end)
        return format_scan_results(reports)

    if command.name == "heatmap":
        reports = await scan_tickers(provider, command.tickers or _default_tickers(), today=end)
        return format_heatmap(build_heatmap(reports))

    if command.name == "mega":
        summaries = [
            summarize_mega_alerts(ticker, await provider.alerts(ticker, start_s, end_s))
            for ticker in (command.tickers or (command.ticker,))
        ]
        return format_mega_alert_summaries(summaries)

    if command.name == "digest":
        reports = await scan_tickers(provider, command.tickers or _default_tickers(), today=end)
        return format_digest(build_heatmap(reports))

    if command.name == "futoi":
        rows = await provider.futoi(command.ticker, start_s, end_s)
        return format_futoi_summary(summarize_futoi(command.ticker, rows))

    if command.name == "stats":
        rows = await provider.tradestats(command.ticker, start_s, end_s)
        return format_flow_statistics(build_flow_statistics(command.ticker, rows))

    if command.name == "channel_signal":
        report = await _signal_report(provider, command.ticker, start_s, end_s)
        return format_channel_signal(report)

    if command.name == "full":
        quote = format_quote_report(command.ticker, await provider.quote(command.ticker))
        report = await _signal_report(provider, command.ticker, start_s, end_s)
        book = _format_latest_book(command.ticker, await provider.obstats(command.ticker, start_s, end_s))
        orders = _format_order_pressure(command.ticker, await provider.orderstats(command.ticker, start_s, end_s))
        alerts = _format_alerts(command.ticker, await provider.alerts(command.ticker, start_s, end_s))
        return format_full_report(
            command.ticker,
            quote=quote,
            signal=format_signal_report(report),
            book=book,
            orders=orders,
            alerts=alerts,
        )

    if command.name == "book":
        rows = await provider.obstats(command.ticker, start_s, end_s)
        return _format_latest_book(command.ticker, rows)

    if command.name == "orders":
        rows = await provider.orderstats(command.ticker, start_s, end_s)
        return _format_order_pressure(command.ticker, rows)

    if command.name == "alerts":
        rows = await provider.alerts(command.ticker, start_s, end_s)
        return _format_alerts(command.ticker, rows)

    return format_help()


async def _signal_report(provider: MarketProvider, ticker: str, start: str, end: str):
    tradestats = await provider.tradestats(ticker, start, end)
    orderstats = await provider.orderstats(ticker, start, end)
    obstats = await provider.obstats(ticker, start, end)
    alerts = await provider.alerts(ticker, start, end)
    return build_signal_report(
        ticker,
        tradestats=tradestats,
        orderstats=orderstats,
        obstats=obstats,
        alerts=alerts,
    )


def _format_latest_book(ticker: str, rows: list[dict]) -> str:
    if not rows:
        return f"Нет данных OBStats по {ticker}."
    latest = sorted(rows, key=lambda row: (str(row.get("tradedate") or ""), str(row.get("tradetime") or "")))[-1]
    return "\n".join(
        [
            f"Стакан {ticker}",
            f"Время: {latest.get('tradedate')} {latest.get('tradetime')}",
            f"Дисбаланс всего: {float(latest.get('imbalance_val') or 0):+.2f}",
            f"Дисбаланс BBO: {float(latest.get('imbalance_val_bbo') or 0):+.2f}",
            f"Спред BBO: {float(latest.get('spread_bbo') or 0):.1f}",
        ]
    )


def _format_order_pressure(ticker: str, rows: list[dict]) -> str:
    if not rows:
        return f"Нет данных OrderStats по {ticker}."
    put_buy = sum(float(row.get("put_val_b") or 0) for row in rows)
    put_sell = sum(float(row.get("put_val_s") or 0) for row in rows)
    cancel_buy = sum(float(row.get("cancel_val_b") or 0) for row in rows)
    cancel_sell = sum(float(row.get("cancel_val_s") or 0) for row in rows)
    return "\n".join(
        [
            f"Заявки {ticker}",
            f"Выставлено покупок: {put_buy / 1_000_000_000:.2f} млрд ₽",
            f"Выставлено продаж: {put_sell / 1_000_000_000:.2f} млрд ₽",
            f"Снято покупок: {cancel_buy / 1_000_000_000:.2f} млрд ₽",
            f"Снято продаж: {cancel_sell / 1_000_000_000:.2f} млрд ₽",
        ]
    )


def _format_alerts(ticker: str, rows: list[dict]) -> str:
    if not rows:
        return f"Нет MegaAlert по {ticker} за выбранный период."
    counts: dict[str, int] = {}
    for row in rows:
        key = str(row.get("alert_type") or "unknown")
        counts[key] = counts.get(key, 0) + 1
    lines = [f"MegaAlert {ticker}", f"Всего событий: {len(rows)}"]
    for key, count in sorted(counts.items(), key=lambda item: item[1], reverse=True)[:6]:
        lines.append(f"{key}: {count}")
    return "\n".join(lines)


def _parse_minutes(value: str | None, *, default: int) -> int:
    if not value:
        return default
    normalized = value.lower().removesuffix("m").removesuffix("м")
    try:
        return max(1, min(1440, int(normalized)))
    except ValueError:
        return default


def _parse_score(value: str | None) -> int:
    if not value:
        return 60
    try:
        return max(0, min(100, int(value)))
    except ValueError:
        return 60


def _default_tickers() -> tuple[str, ...]:
    raw = os.environ.get("DEFAULT_SCAN_TICKERS", "ROSN SBER GAZP LKOH TATN TATNP")
    return tuple(item.strip().upper() for item in raw.replace(",", " ").split() if item.strip())


def _normalize_datetime(value: dt.datetime | None) -> dt.datetime:
    if value is None:
        return dt.datetime.now(dt.UTC)
    if value.tzinfo is None:
        return value.replace(tzinfo=dt.UTC)
    return value.astimezone(dt.UTC)

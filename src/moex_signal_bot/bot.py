from __future__ import annotations

import datetime as dt
from typing import Protocol

from .analytics import build_flow_statistics, build_heatmap, build_market_flow_report, summarize_mega_alerts
from .commands import Command, default_marketflow_tickers, default_tickers, parse_command, parse_score
from .formatters import (
    format_alerts,
    format_channel_signal,
    format_digest,
    format_flow_report,
    format_flow_statistics,
    format_full_report,
    format_futoi_summary,
    format_heatmap,
    format_help,
    format_latest_book,
    format_market_flow_report,
    format_mega_alert_summaries,
    format_order_pressure,
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


class MarketProvider(Protocol):
    async def tradestats(self, ticker: str, start: str, end: str) -> list[dict]: ...

    async def orderstats(self, ticker: str, start: str, end: str) -> list[dict]: ...

    async def obstats(self, ticker: str, start: str, end: str) -> list[dict]: ...

    async def alerts(self, ticker: str, start: str, end: str) -> list[dict]: ...

    async def futoi(self, ticker: str, start: str, end: str) -> list[dict]: ...

    async def quote(self, ticker: str) -> dict: ...


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
        score = parse_score(command.args[0] if command.args else None)
        store.set_min_score(chat_id, score)
        return f"Минимальная сила: {score}/100."
    if command.name == "quiet":
        if store is None or chat_id is None:
            return "Настройки недоступны: нет локального хранилища или chat_id."
        if len(command.args) < 2:
            return "Укажите тихие часы: /quiet 23:00 07:00."
        try:
            store.set_quiet_hours(chat_id, command.args[0], command.args[1])
        except ValueError as exc:
            return str(exc)
        settings = store.get_settings(chat_id)
        return f"Тихие часы: {settings.quiet_start}-{settings.quiet_end}."
    if command.name == "types":
        if store is None or chat_id is None:
            return "Настройки недоступны: нет локального хранилища или chat_id."
        try:
            store.set_alert_types(chat_id, tuple(command.args))
        except ValueError as exc:
            return str(exc)
        alert_types = store.get_settings(chat_id).alert_types
        return "Типы автосигналов: " + (", ".join(alert_types) if alert_types else "все")
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
        settings = store.get_settings(chat_id)
        return format_portfolio_risk(build_portfolio_risk(reports, min_score=settings.min_score))
    if not command.ticker:
        if command.name in {"heatmap", "mega", "digest"}:
            command = Command(name=command.name, ticker=None, tickers=default_tickers())
        elif command.name == "marketflow":
            command = Command(name=command.name, ticker=None, tickers=default_marketflow_tickers())
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
        reports = await scan_tickers(provider, command.tickers or default_tickers(), today=end)
        return format_heatmap(build_heatmap(reports))

    if command.name == "mega":
        summaries = [
            summarize_mega_alerts(ticker, await provider.alerts(ticker, start_s, end_s))
            for ticker in (command.tickers or (command.ticker,))
        ]
        return format_mega_alert_summaries(summaries)

    if command.name == "digest":
        reports = await scan_tickers(provider, command.tickers or default_tickers(), today=end)
        return format_digest(build_heatmap(reports))

    if command.name == "marketflow":
        tickers = command.tickers or default_marketflow_tickers()
        rows_by_ticker = {ticker: await provider.tradestats(ticker, end_s, end_s) for ticker in tickers}
        quotes = {ticker: await provider.quote(ticker) for ticker in tickers}
        report = build_market_flow_report(rows_by_ticker, quotes=quotes, now=now)
        return format_market_flow_report(report)

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
        book = format_latest_book(command.ticker, await provider.obstats(command.ticker, start_s, end_s))
        orders = format_order_pressure(command.ticker, await provider.orderstats(command.ticker, start_s, end_s))
        alerts = format_alerts(command.ticker, await provider.alerts(command.ticker, start_s, end_s))
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
        return format_latest_book(command.ticker, rows)

    if command.name == "orders":
        rows = await provider.orderstats(command.ticker, start_s, end_s)
        return format_order_pressure(command.ticker, rows)

    if command.name == "alerts":
        rows = await provider.alerts(command.ticker, start_s, end_s)
        return format_alerts(command.ticker, rows)

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


def _normalize_datetime(value: dt.datetime | None) -> dt.datetime:
    if value is None:
        return dt.datetime.now(dt.UTC)
    if value.tzinfo is None:
        return value.replace(tzinfo=dt.UTC)
    return value.astimezone(dt.UTC)

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Protocol

from .formatters import format_flow_report, format_help, format_quote_report, format_strategy_report
from .signals import classify_from_days, summarize_daily_flow


@dataclass(frozen=True)
class Command:
    name: str
    ticker: str | None
    days: int = 1


class MarketProvider(Protocol):
    async def tradestats(self, ticker: str, start: str, end: str) -> list[dict]: ...

    async def orderstats(self, ticker: str, start: str, end: str) -> list[dict]: ...

    async def obstats(self, ticker: str, start: str, end: str) -> list[dict]: ...

    async def alerts(self, ticker: str, start: str, end: str) -> list[dict]: ...

    async def quote(self, ticker: str) -> dict: ...


def parse_command(text: str) -> Command:
    parts = text.strip().split()
    if not parts or not parts[0].startswith("/"):
        return Command(name="help", ticker=None, days=1)

    name = parts[0].removeprefix("/").split("@", 1)[0].lower()
    if name == "start":
        name = "help"
    if name not in {"help", "quote", "flow", "strategy", "book", "orders", "alerts"}:
        return Command(name="help", ticker=None, days=1)

    ticker = parts[1].upper() if len(parts) >= 2 else None
    days = 7 if name == "strategy" else 1
    if len(parts) >= 3:
        try:
            days = max(1, min(30, int(parts[2])))
        except ValueError:
            days = 1
    return Command(name=name, ticker=ticker, days=days)


async def handle_command(text: str, provider: MarketProvider) -> str:
    command = parse_command(text)
    if command.name == "help" or not command.ticker:
        return format_help()

    end = dt.date.today()
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

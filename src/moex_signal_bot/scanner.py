from __future__ import annotations

import datetime as dt
from collections.abc import Iterable, Mapping
from typing import Any, Protocol

from .formatters import format_signal_report
from .signals import (
    SignalReport,
    TradeState,
    classify_from_days,
    classify_trade_state,
    summarize_daily_flow,
    summarize_flow,
)
from .storage import WatchlistStore


class ScannerProvider(Protocol):
    async def tradestats(self, ticker: str, start: str, end: str) -> list[dict]: ...

    async def orderstats(self, ticker: str, start: str, end: str) -> list[dict]: ...

    async def obstats(self, ticker: str, start: str, end: str) -> list[dict]: ...

    async def alerts(self, ticker: str, start: str, end: str) -> list[dict]: ...


class SignalSender(Protocol):
    async def send_message(self, chat_id: int, text: str) -> None: ...


def build_signal_report(
    ticker: str,
    *,
    tradestats: Iterable[Mapping[str, Any]],
    orderstats: Iterable[Mapping[str, Any]],
    obstats: Iterable[Mapping[str, Any]],
    alerts: Iterable[Mapping[str, Any]],
) -> SignalReport:
    ticker = ticker.upper()
    trade_rows = list(tradestats)
    order_rows = list(orderstats)
    book_rows = list(obstats)
    alert_rows = list(alerts)
    days = summarize_daily_flow(trade_rows)

    if not days:
        neutral = classify_trade_state(0.0, 0.0)
        return SignalReport(
            ticker=ticker,
            state=neutral,
            score=0,
            direction="neutral",
            latest_date="",
            latest_time="",
            price_change=0.0,
            flow_imbalance=0.0,
            buy_power=0.0,
            sell_power=0.0,
            support=None,
            reclaim=None,
            reasons=("Нет данных TradeStats для расчета.",),
            signal_key=f"{ticker}:no-data",
        )

    latest = days[-1]
    state = classify_from_days(days)
    recent_flow = summarize_flow(_last_rows(trade_rows, 3))
    latest_book = _latest_row(book_rows)
    low_alerts = _count_alerts(alert_rows, "low")
    high_alerts = _count_alerts(alert_rows, "high")
    order_bias = _order_bias(order_rows)
    bbo_imbalance = _number(latest_book, "imbalance_val_bbo") if latest_book else 0.0

    score, reasons = _score_signal(
        state=state,
        price_change=latest.price_change,
        flow_imbalance=latest.flow.imbalance,
        recent_buy_power=recent_flow.buy_power,
        recent_sell_power=recent_flow.sell_power,
        order_bias=order_bias,
        bbo_imbalance=bbo_imbalance,
        low_alerts=low_alerts,
        high_alerts=high_alerts,
    )
    support = min((day.close_price for day in days if day.close_price), default=None)
    reclaim = max((day.open_price for day in days[-3:] if day.open_price), default=None)
    signal_key = f"{latest.date}:{latest.last_time}:{state.code}:{score}"

    return SignalReport(
        ticker=ticker,
        state=state,
        score=score,
        direction=_direction_for_state(state),
        latest_date=latest.date,
        latest_time=latest.last_time,
        price_change=latest.price_change,
        flow_imbalance=latest.flow.imbalance,
        buy_power=latest.flow.buy_power,
        sell_power=latest.flow.sell_power,
        support=support,
        reclaim=reclaim,
        reasons=tuple(reasons),
        signal_key=signal_key,
    )


async def scan_tickers(
    provider: ScannerProvider,
    tickers: Iterable[str],
    *,
    days: int = 1,
    today: dt.date | None = None,
) -> list[SignalReport]:
    today = today or dt.date.today()
    start = today - dt.timedelta(days=max(1, days) - 1)
    start_s = start.isoformat()
    end_s = today.isoformat()
    reports: list[SignalReport] = []

    for ticker in _unique_tickers(tickers):
        tradestats = await provider.tradestats(ticker, start_s, end_s)
        orderstats = await provider.orderstats(ticker, start_s, end_s)
        obstats = await provider.obstats(ticker, start_s, end_s)
        alerts = await provider.alerts(ticker, start_s, end_s)
        reports.append(
            build_signal_report(
                ticker,
                tradestats=tradestats,
                orderstats=orderstats,
                obstats=obstats,
                alerts=alerts,
            )
        )

    return reports


async def run_scan_once(
    provider: ScannerProvider,
    store: WatchlistStore,
    telegram: SignalSender,
    *,
    now: dt.datetime | None = None,
    today: dt.date | None = None,
    min_score: int = 60,
) -> int:
    now = _normalize_datetime(now)
    due_items = store.list_due(now)
    reports = {
        report.ticker: report
        for report in await scan_tickers(provider, [item.ticker for item in due_items], today=today or now.date())
    }

    sent = 0
    for item in due_items:
        report = reports.get(item.ticker)
        if report is None:
            store.mark_checked(item.chat_id, item.ticker, now)
            continue
        if store.is_muted(item, now):
            store.mark_checked(item.chat_id, item.ticker, now)
            continue
        if is_actionable(report, min_score=min_score) and not store.was_signal_sent(
            item.chat_id, report.ticker, report.state.code, report.signal_key
        ):
            await telegram.send_message(item.chat_id, format_signal_report(report, automatic=True))
            store.mark_signal_sent(item.chat_id, report.ticker, report.state.code, report.signal_key, now)
            sent += 1
        store.mark_checked(item.chat_id, item.ticker, now)
    return sent


def is_actionable(report: SignalReport, *, min_score: int = 60) -> bool:
    return report.score >= min_score and report.state.code != "neutral"


def _score_signal(
    *,
    state: TradeState,
    price_change: float,
    flow_imbalance: float,
    recent_buy_power: float,
    recent_sell_power: float,
    order_bias: float,
    bbo_imbalance: float,
    low_alerts: int,
    high_alerts: int,
) -> tuple[int, list[str]]:
    score = {
        "sell_pressure": 35,
        "absorption": 30,
        "bullish_reversal": 35,
        "weak_bounce": 20,
        "neutral": 0,
    }.get(state.code, 0)
    reasons = [state.description]

    if price_change <= -1.0:
        score += 15
        reasons.append("Цена снизилась более чем на 1%.")
    elif price_change >= 1.0:
        score += 15
        reasons.append("Цена выросла более чем на 1%.")

    if flow_imbalance <= -0.10:
        score += 15
        reasons.append("Давление продаж подтверждено отрицательным потоком сделок.")
    elif flow_imbalance <= -0.05:
        score += 10
        reasons.append("Поток сделок смещен в сторону продавцов.")
    elif flow_imbalance >= 0.10:
        score += 15
        reasons.append("Поток сделок смещен в сторону покупателей.")
    elif flow_imbalance >= 0.05:
        score += 10
        reasons.append("Покупатели имеют умеренное преимущество в сделках.")

    if recent_sell_power >= 0.60:
        score += 10
        reasons.append("Последние интервалы остаются продавцовыми.")
    if recent_buy_power >= 0.60:
        score += 10
        reasons.append("Последние интервалы остаются покупательными.")

    if order_bias <= -0.10:
        score += 10
        reasons.append("В заявках заметно больше предложения.")
    elif order_bias >= 0.10:
        score += 10
        reasons.append("В заявках заметно больше спроса.")

    if bbo_imbalance <= -0.05:
        score += 5
        reasons.append("BBO-стакан смещен к продавцам.")
    elif bbo_imbalance >= 0.05:
        score += 5
        reasons.append("BBO-стакан смещен к покупателям.")

    if low_alerts:
        score += min(20, low_alerts * 4)
        reasons.append(f"MegaAlert по новым минимумам: {low_alerts}.")
    if high_alerts:
        score += min(20, high_alerts * 4)
        reasons.append(f"MegaAlert по новым максимумам: {high_alerts}.")

    return min(100, score), reasons


def _direction_for_state(state: TradeState) -> str:
    return {
        "sell_pressure": "short",
        "absorption": "watch_long",
        "bullish_reversal": "long",
        "weak_bounce": "caution",
    }.get(state.code, "neutral")


def _unique_tickers(tickers: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for ticker in tickers:
        normalized = ticker.upper()
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


def _last_rows(rows: list[Mapping[str, Any]], limit: int) -> list[Mapping[str, Any]]:
    return sorted(rows, key=lambda row: (str(row.get("tradedate") or ""), str(row.get("tradetime") or "")))[-limit:]


def _latest_row(rows: list[Mapping[str, Any]]) -> Mapping[str, Any] | None:
    if not rows:
        return None
    return sorted(rows, key=lambda row: (str(row.get("tradedate") or ""), str(row.get("tradetime") or "")))[-1]


def _count_alerts(rows: list[Mapping[str, Any]], needle: str) -> int:
    return sum(1 for row in rows if needle in str(row.get("alert_type") or "").lower())


def _order_bias(rows: list[Mapping[str, Any]]) -> float:
    put_buy = sum(_number(row, "put_val_b") for row in rows)
    put_sell = sum(_number(row, "put_val_s") for row in rows)
    total = put_buy + put_sell
    return (put_buy - put_sell) / total if total else 0.0


def _number(row: Mapping[str, Any], key: str) -> float:
    value = row.get(key)
    return float(value) if value is not None else 0.0


def _normalize_datetime(value: dt.datetime | None) -> dt.datetime:
    if value is None:
        return dt.datetime.now(dt.UTC)
    if value.tzinfo is None:
        return value.replace(tzinfo=dt.UTC)
    return value.astimezone(dt.UTC)

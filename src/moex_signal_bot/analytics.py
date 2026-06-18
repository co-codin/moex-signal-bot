from __future__ import annotations

import datetime as dt
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any
from zoneinfo import ZoneInfo

from .signals import FlowSummary, SignalReport, classify_from_days, summarize_daily_flow, summarize_flow

MSK = ZoneInfo("Europe/Moscow")


@dataclass(frozen=True)
class HeatmapEntry:
    ticker: str
    score: int
    state_title: str
    direction: str
    alert_type: str
    buy_power: float
    sell_power: float
    megaalerts: int


@dataclass(frozen=True)
class MegaAlertSummary:
    ticker: str
    total: int
    by_type: dict[str, int]
    latest: tuple[Mapping[str, Any], ...]


@dataclass(frozen=True)
class FlowStatistics:
    ticker: str
    state_code: str
    state_title: str
    samples: int
    up_after: int
    down_after: int
    flat_after: int


@dataclass(frozen=True)
class MarketFlowEntry:
    ticker: str
    flow: FlowSummary
    last_price: float | None
    last_to_prev_pct: float | None
    latest_time: str
    buckets: int


@dataclass(frozen=True)
class MarketFlowReport:
    window_start: dt.datetime
    window_end: dt.datetime
    entries: tuple[MarketFlowEntry, ...]

    @property
    def total_flow(self) -> FlowSummary:
        return FlowSummary(
            buy_value=sum(entry.flow.buy_value for entry in self.entries),
            sell_value=sum(entry.flow.sell_value for entry in self.entries),
            buy_volume=sum(entry.flow.buy_volume for entry in self.entries),
            sell_volume=sum(entry.flow.sell_volume for entry in self.entries),
            buy_trades=sum(entry.flow.buy_trades for entry in self.entries),
            sell_trades=sum(entry.flow.sell_trades for entry in self.entries),
        )


def build_heatmap(reports: Iterable[SignalReport], *, limit: int = 10) -> list[HeatmapEntry]:
    entries = [
        HeatmapEntry(
            ticker=report.ticker,
            score=report.score,
            state_title=report.state.title,
            direction=report.direction,
            alert_type=report.alert_type,
            buy_power=report.buy_power,
            sell_power=report.sell_power,
            megaalerts=report.features.megaalert_count,
        )
        for report in reports
    ]
    return sorted(entries, key=lambda item: (item.score, item.megaalerts, item.ticker), reverse=True)[:limit]


def build_market_flow_report(
    rows_by_ticker: Mapping[str, Iterable[Mapping[str, Any]]],
    *,
    quotes: Mapping[str, Mapping[str, Any]] | None = None,
    now: dt.datetime | None = None,
    window_hours: int = 2,
    limit: int = 15,
) -> MarketFlowReport:
    quotes = quotes or {}
    now_msk = _to_msk(now or dt.datetime.now(MSK))
    parsed_rows: dict[str, list[tuple[dt.datetime, Mapping[str, Any]]]] = {}
    all_times: list[dt.datetime] = []
    for ticker, rows in rows_by_ticker.items():
        parsed: list[tuple[dt.datetime, Mapping[str, Any]]] = []
        for row in rows:
            traded_at = _trade_datetime(row)
            if traded_at is None:
                continue
            parsed.append((traded_at, row))
            all_times.append(traded_at)
        parsed_rows[ticker.upper()] = sorted(parsed, key=lambda item: item[0])

    available_times = [traded_at for traded_at in all_times if traded_at <= now_msk]
    window_end = max(available_times or all_times or [now_msk])
    window_start = window_end - dt.timedelta(hours=max(1, window_hours))
    entries: list[MarketFlowEntry] = []

    for ticker, parsed in parsed_rows.items():
        window_rows = [row for traded_at, row in parsed if window_start <= traded_at <= window_end]
        if not window_rows:
            continue
        latest = window_rows[-1]
        quote = quotes.get(ticker) or {}
        entries.append(
            MarketFlowEntry(
                ticker=ticker,
                flow=summarize_flow(window_rows),
                last_price=_optional_number(quote.get("last"), fallback=_optional_number(latest.get("pr_close"))),
                last_to_prev_pct=_optional_number(quote.get("last_to_prev_pct")),
                latest_time=str(latest.get("tradetime") or ""),
                buckets=len(window_rows),
            )
        )

    sorted_entries = sorted(entries, key=lambda item: (item.flow.imbalance, item.flow.net_value), reverse=True)[:limit]
    return MarketFlowReport(window_start=window_start, window_end=window_end, entries=tuple(sorted_entries))


def summarize_mega_alerts(
    ticker: str,
    rows: Iterable[Mapping[str, Any]],
    *,
    latest_limit: int = 5,
) -> MegaAlertSummary:
    data = sorted(list(rows), key=lambda row: (str(row.get("tradedate") or ""), str(row.get("tradetime") or "")))
    counts = Counter(str(row.get("alert_type") or "unknown") for row in data)
    latest = tuple(reversed(data[-latest_limit:]))
    return MegaAlertSummary(ticker=ticker.upper(), total=len(data), by_type=dict(counts), latest=latest)


def build_flow_statistics(ticker: str, rows: Iterable[Mapping[str, Any]]) -> FlowStatistics:
    days = summarize_daily_flow(rows)
    if len(days) < 2:
        state = classify_from_days(days)
        return FlowStatistics(
            ticker=ticker.upper(),
            state_code=state.code,
            state_title=state.title,
            samples=0,
            up_after=0,
            down_after=0,
            flat_after=0,
        )

    states = [classify_from_days([day]) for day in days]
    target_state = states[-1]
    up_after = down_after = flat_after = samples = 0
    for index, day in enumerate(days[:-1]):
        if states[index].code != target_state.code:
            continue
        samples += 1
        next_day = days[index + 1]
        if next_day.close_price > day.close_price:
            up_after += 1
        elif next_day.close_price < day.close_price:
            down_after += 1
        else:
            flat_after += 1
    return FlowStatistics(
        ticker=ticker.upper(),
        state_code=target_state.code,
        state_title=target_state.title,
        samples=samples,
        up_after=up_after,
        down_after=down_after,
        flat_after=flat_after,
    )


def _trade_datetime(row: Mapping[str, Any]) -> dt.datetime | None:
    tradedate = row.get("tradedate")
    tradetime = row.get("tradetime")
    if not tradedate or not tradetime:
        return None
    try:
        return dt.datetime.fromisoformat(f"{tradedate}T{tradetime}").replace(tzinfo=MSK)
    except ValueError:
        return None


def _to_msk(value: dt.datetime) -> dt.datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=MSK)
    return value.astimezone(MSK)


def _optional_number(value: Any, *, fallback: float | None = None) -> float | None:
    if value is None:
        return fallback
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from .signals import SignalReport, classify_from_days, summarize_daily_flow


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

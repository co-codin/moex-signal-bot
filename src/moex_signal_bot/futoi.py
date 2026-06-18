from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class FutoiGroup:
    client_group: str
    long: float
    short: float
    net: float


@dataclass(frozen=True)
class FutoiSummary:
    ticker: str
    tradedate: str
    tradetime: str
    total_long: float
    total_short: float
    net: float
    groups: tuple[FutoiGroup, ...]


def summarize_futoi(ticker: str, rows: Iterable[Mapping[str, Any]]) -> FutoiSummary:
    data = sorted(list(rows), key=lambda row: (str(row.get("tradedate") or ""), str(row.get("tradetime") or "")))
    if not data:
        return FutoiSummary(
            ticker=ticker.upper(),
            tradedate="",
            tradetime="",
            total_long=0.0,
            total_short=0.0,
            net=0.0,
            groups=(),
        )

    latest = data[-1]
    latest_key = (str(latest.get("tradedate") or ""), str(latest.get("tradetime") or ""))
    latest_rows = [
        row for row in data if (str(row.get("tradedate") or ""), str(row.get("tradetime") or "")) == latest_key
    ]
    groups = tuple(
        FutoiGroup(
            client_group=str(row.get("clgroup") or "unknown"),
            long=_number(row, "pos_long"),
            short=_number(row, "pos_short"),
            net=_number(row, "pos_long") - _number(row, "pos_short"),
        )
        for row in latest_rows
    )
    total_long = sum(group.long for group in groups)
    total_short = sum(group.short for group in groups)
    return FutoiSummary(
        ticker=ticker.upper(),
        tradedate=latest_key[0],
        tradetime=latest_key[1],
        total_long=total_long,
        total_short=total_short,
        net=total_long - total_short,
        groups=groups,
    )


def _number(row: Mapping[str, Any], key: str) -> float:
    value = row.get(key)
    return float(value) if value is not None else 0.0

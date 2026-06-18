from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class OptionChainEntry:
    ticker: str
    option_type: str
    strike: float | None
    expiry: str
    last_price: float | None
    volume: float
    turnover: float
    open_interest: float


@dataclass(frozen=True)
class OptionChainSummary:
    underlying: str
    total: int
    calls: int
    puts: int
    volume: float
    turnover: float
    open_interest: float
    leaders: tuple[OptionChainEntry, ...]


@dataclass(frozen=True)
class OptionTradeActivity:
    ticker: str
    quote: Mapping[str, Any]
    trades_count: int
    volume: float
    turnover: float
    latest_trade: Mapping[str, Any] | None


def summarize_options_chain(
    underlying: str,
    rows: Iterable[Mapping[str, Any]],
    *,
    limit: int = 8,
) -> OptionChainSummary:
    underlying = underlying.upper()
    entries = [_option_entry(row) for row in rows if _matches_underlying(row, underlying)]
    calls = sum(1 for entry in entries if entry.option_type == "Call")
    puts = sum(1 for entry in entries if entry.option_type == "Put")
    leaders = tuple(
        sorted(entries, key=lambda entry: (entry.turnover, entry.volume, entry.ticker), reverse=True)[:limit]
    )
    return OptionChainSummary(
        underlying=underlying,
        total=len(entries),
        calls=calls,
        puts=puts,
        volume=sum(entry.volume for entry in entries),
        turnover=sum(entry.turnover for entry in entries),
        open_interest=sum(entry.open_interest for entry in entries),
        leaders=leaders,
    )


def summarize_option_trades(
    ticker: str,
    quote: Mapping[str, Any],
    trades: Iterable[Mapping[str, Any]],
) -> OptionTradeActivity:
    rows = sorted(list(trades), key=lambda row: str(_value(row, "tradetime", "time") or ""))
    return OptionTradeActivity(
        ticker=ticker.upper(),
        quote=quote,
        trades_count=len(rows),
        volume=sum(_trade_quantity(row) for row in rows),
        turnover=sum(_trade_value(row) for row in rows),
        latest_trade=rows[-1] if rows else None,
    )


def _option_entry(row: Mapping[str, Any]) -> OptionChainEntry:
    return OptionChainEntry(
        ticker=str(_value(row, "secid", "ticker") or "").upper(),
        option_type=_option_type(row),
        strike=_optional_number(_value(row, "strike", "strikeprice", "strike_price")),
        expiry=str(_value(row, "lasttradedate", "expirydate", "matdate") or "н/д"),
        last_price=_optional_number(_value(row, "last", "lastprice")),
        volume=_number(row, "voltoday", "volume"),
        turnover=_number(row, "valtoday", "turnover", "value"),
        open_interest=_number(row, "openposition", "openinterest", "open_interest"),
    )


def _matches_underlying(row: Mapping[str, Any], underlying: str) -> bool:
    for key in ("assetcode", "underlyingasset", "underlying_asset", "underlyingsecid"):
        value = _value(row, key)
        if value and str(value).upper() == underlying:
            return True
    ticker = str(_value(row, "secid", "ticker") or "").upper()
    return ticker.startswith(underlying)


def _option_type(row: Mapping[str, Any]) -> str:
    raw = str(_value(row, "optiontype", "option_type", "putcall") or "").strip().lower()
    if raw.startswith("c") or raw in {"call", "колл"}:
        return "Call"
    if raw.startswith("p") or raw in {"put", "пут"}:
        return "Put"
    return "н/д"


def _trade_quantity(row: Mapping[str, Any]) -> float:
    return _number(row, "quantity", "qty", "volume", "contracts")


def _trade_value(row: Mapping[str, Any]) -> float:
    value = _optional_number(_value(row, "value", "turnover", "valtoday"))
    if value is not None:
        return value
    return _number(row, "price", "last") * _trade_quantity(row)


def _number(row: Mapping[str, Any], *keys: str) -> float:
    value = _optional_number(_value(row, *keys))
    return value if value is not None else 0.0


def _optional_number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _value(row: Mapping[str, Any], *keys: str) -> Any:
    lower = {str(key).lower(): value for key, value in row.items()}
    for key in keys:
        if key in row:
            return row[key]
        if key.lower() in lower:
            return lower[key.lower()]
    return None

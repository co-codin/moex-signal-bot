from __future__ import annotations

import asyncio
import datetime as dt
from collections.abc import Callable
from typing import Any


class MoexProvider:
    def __init__(
        self,
        *,
        api_key: str | None,
        ticker_factory: Callable[[str], Any] | None = None,
        market_factory: Callable[[str], Any] | None = None,
        session_module: Any | None = None,
    ) -> None:
        if ticker_factory is None or session_module is None:
            from moexalgo import Ticker, session

            ticker_factory = ticker_factory or Ticker
            session_module = session_module or session
        self._ticker_factory = ticker_factory
        self._market_factory = market_factory
        self._session = session_module
        if api_key:
            self._session.TOKEN = api_key

    async def tradestats(self, ticker: str, start: str, end: str) -> list[dict]:
        return await self._ticker_rows(ticker, "tradestats", start, end)

    async def orderstats(self, ticker: str, start: str, end: str) -> list[dict]:
        return await self._ticker_rows(ticker, "orderstats", start, end)

    async def obstats(self, ticker: str, start: str, end: str) -> list[dict]:
        return await self._ticker_rows(ticker, "obstats", start, end)

    async def alerts(self, ticker: str, start: str, end: str) -> list[dict]:
        return await self._ticker_rows(ticker, "alerts", start, end)

    async def futoi(self, ticker: str, start: str, end: str) -> list[dict]:
        return await self._ticker_rows(ticker, "futoi", start, end)

    async def quote(self, ticker: str) -> dict:
        ticker = ticker.upper()

        def fetch() -> dict:
            instrument = self._ticker_factory(ticker)
            quote = _quote_from_marketdata(instrument, ticker)
            if quote is not None:
                return quote
            today = dt.date.today().isoformat()
            candles = list(instrument.candles(start=today, end=today, period="1D", latest=True, native=True))
            latest = candles[-1] if candles else {}
            return {
                "ticker": ticker,
                "last": latest.get("close"),
                "time": latest.get("end") or latest.get("begin"),
                "last_to_prev_pct": None,
            }

        return await asyncio.to_thread(fetch)

    async def options_chain(self, underlying: str) -> list[dict]:
        underlying = underlying.upper()

        def fetch() -> list[dict]:
            market_factory = self._market_factory
            if market_factory is None:
                from moexalgo import Market

                market_factory = Market
            market = market_factory("options")
            securities = list(market.tickers("*", native=True))
            marketdata = list(market.marketdata("*", native=True))
            return _merge_option_rows(underlying, securities, marketdata)

        return await asyncio.to_thread(fetch)

    async def option_quote(self, ticker: str) -> dict:
        return await self.quote(ticker)

    async def option_trades(self, ticker: str) -> list[dict]:
        ticker = ticker.upper()

        def fetch() -> list[dict]:
            instrument = self._ticker_factory(ticker)
            return list(instrument.trades(latest=False, native=True))

        return await asyncio.to_thread(fetch)

    async def _ticker_rows(self, ticker: str, method_name: str, start: str, end: str) -> list[dict]:
        ticker = ticker.upper()

        def fetch() -> list[dict]:
            instrument = self._ticker_factory(ticker)
            method = getattr(instrument, method_name)
            return list(method(start=start, end=end, native=True))

        return await asyncio.to_thread(fetch)


def _quote_from_marketdata(instrument: Any, ticker: str) -> dict | None:
    market = getattr(instrument, "market", None)
    marketdata = getattr(market, "marketdata", None)
    if marketdata is None:
        return None
    rows = list(marketdata("secid", "last", "bid", "offer", "lasttoprevprice", "updatetime", native=True))
    for row in rows:
        row_ticker = str(row.get("ticker") or row.get("secid") or "").upper()
        if row_ticker != ticker:
            continue
        return {
            "ticker": ticker,
            "last": row.get("last"),
            "bid": row.get("bid"),
            "offer": row.get("offer"),
            "last_to_prev_pct": row.get("lasttoprevprice"),
            "time": row.get("updatetime"),
        }
    return None


def _merge_option_rows(underlying: str, securities: list[dict], marketdata: list[dict]) -> list[dict]:
    data_by_ticker = {_row_ticker(row): row for row in marketdata if _row_ticker(row)}
    rows: list[dict] = []
    for security in securities:
        ticker = _row_ticker(security)
        if not ticker:
            continue
        merged = dict(security)
        merged.update(data_by_ticker.get(ticker, {}))
        if _option_matches_underlying(merged, underlying):
            rows.append(merged)
    return rows


def _option_matches_underlying(row: dict, underlying: str) -> bool:
    for key in ("assetcode", "underlyingasset", "underlying_asset", "underlyingsecid"):
        value = row.get(key)
        if value and str(value).upper() == underlying:
            return True
    return _row_ticker(row).startswith(underlying)


def _row_ticker(row: dict) -> str:
    return str(row.get("ticker") or row.get("secid") or "").upper()

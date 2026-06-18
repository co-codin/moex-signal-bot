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
        session_module: Any | None = None,
    ) -> None:
        if ticker_factory is None or session_module is None:
            from moexalgo import Ticker, session

            ticker_factory = ticker_factory or Ticker
            session_module = session_module or session
        self._ticker_factory = ticker_factory
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

    async def _ticker_rows(self, ticker: str, method_name: str, start: str, end: str) -> list[dict]:
        ticker = ticker.upper()

        def fetch() -> list[dict]:
            instrument = self._ticker_factory(ticker)
            method = getattr(instrument, method_name)
            return list(method(start=start, end=end, native=True))

        return await asyncio.to_thread(fetch)

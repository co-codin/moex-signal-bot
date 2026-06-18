from __future__ import annotations

import asyncio
import datetime as dt
import json
from dataclasses import dataclass
from typing import Protocol

from .formatters import format_signal_report
from .scanner import ScannerProvider, SignalSender, is_actionable, scan_tickers
from .storage import WatchItem, WatchlistStore

DEFAULT_QUEUE_KEY = "moex:scanner:jobs"


class ScannerQueue(Protocol):
    async def push(self, job: ScannerJob) -> None: ...

    async def pop(self, *, timeout_seconds: int) -> ScannerJob | None: ...


@dataclass(frozen=True)
class ScannerJob:
    chat_id: int
    ticker: str
    queued_at: dt.datetime
    attempts: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "ticker", self.ticker.upper())
        object.__setattr__(self, "queued_at", _normalize_datetime(self.queued_at))

    def to_json(self) -> str:
        return json.dumps(
            {
                "chat_id": self.chat_id,
                "ticker": self.ticker,
                "queued_at": self.queued_at.isoformat(),
                "attempts": self.attempts,
            },
            ensure_ascii=True,
            sort_keys=True,
        )

    @classmethod
    def from_json(cls, payload: str) -> ScannerJob:
        data = json.loads(payload)
        return cls(
            chat_id=int(data["chat_id"]),
            ticker=str(data["ticker"]),
            queued_at=dt.datetime.fromisoformat(str(data["queued_at"])),
            attempts=int(data.get("attempts", 0)),
        )

    def next_attempt(self) -> ScannerJob:
        return ScannerJob(
            chat_id=self.chat_id,
            ticker=self.ticker,
            queued_at=self.queued_at,
            attempts=self.attempts + 1,
        )


class RedisScannerQueue:
    def __init__(self, redis_url: str, *, queue_key: str = DEFAULT_QUEUE_KEY) -> None:
        if not redis_url:
            raise RuntimeError("Не задана переменная окружения REDIS_URL для очереди автосканера.")
        self.queue_key = queue_key
        self._client = _connect_redis(redis_url)

    async def push(self, job: ScannerJob) -> None:
        await self._client.rpush(self.queue_key, job.to_json())

    async def pop(self, *, timeout_seconds: int) -> ScannerJob | None:
        result = await self._client.blpop([self.queue_key], timeout=timeout_seconds)
        if result is None:
            return None
        _, payload = result
        return ScannerJob.from_json(payload)

    async def close(self) -> None:
        await self._client.aclose()


async def enqueue_due_scans(store: WatchlistStore, queue: ScannerQueue, *, now: dt.datetime | None = None) -> int:
    now = _normalize_datetime(now)
    enqueued = 0
    for item in store.list_due(now):
        if store.is_muted(item, now):
            store.mark_checked(item.chat_id, item.ticker, now)
            continue
        settings = store.get_settings(item.chat_id)
        if _is_quiet_time(settings.quiet_start, settings.quiet_end, now):
            store.mark_checked(item.chat_id, item.ticker, now)
            continue
        await queue.push(ScannerJob(chat_id=item.chat_id, ticker=item.ticker, queued_at=now))
        store.mark_checked(item.chat_id, item.ticker, now)
        enqueued += 1
    return enqueued


async def process_scanner_job(
    provider: ScannerProvider,
    store: WatchlistStore,
    telegram: SignalSender,
    job: ScannerJob,
    *,
    now: dt.datetime | None = None,
    today: dt.date | None = None,
    min_score: int = 60,
) -> int:
    now = _normalize_datetime(now)
    item = _find_watch_item(store, job.chat_id, job.ticker)
    if item is None:
        return 0
    if store.is_muted(item, now):
        return 0
    settings = store.get_settings(job.chat_id)
    if _is_quiet_time(settings.quiet_start, settings.quiet_end, now):
        return 0

    reports = await scan_tickers(provider, [job.ticker], today=today or now.date())
    if not reports:
        return 0
    report = reports[0]
    threshold = max(min_score, settings.min_score)
    if settings.alert_types and report.alert_type not in settings.alert_types:
        return 0
    if not is_actionable(report, min_score=threshold):
        return 0
    if store.was_signal_sent(job.chat_id, report.ticker, report.state.code, report.signal_key):
        return 0

    await telegram.send_message(job.chat_id, format_signal_report(report, automatic=True))
    store.mark_signal_sent(job.chat_id, report.ticker, report.state.code, report.signal_key, now)
    return 1


async def scanner_worker_iteration(
    provider: ScannerProvider,
    store: WatchlistStore,
    telegram: SignalSender,
    queue: ScannerQueue,
    *,
    now: dt.datetime | None = None,
    today: dt.date | None = None,
    pop_timeout_seconds: int = 5,
    max_attempts: int = 3,
    retry_delay_seconds: float = 5.0,
) -> int:
    job = await queue.pop(timeout_seconds=pop_timeout_seconds)
    if job is None:
        return 0
    try:
        return await process_scanner_job(provider, store, telegram, job, now=now, today=today)
    except Exception as exc:
        print(f"Ошибка worker автосканера для {job.ticker}: {exc}", flush=True)
        if job.attempts < max_attempts:
            if retry_delay_seconds > 0:
                await asyncio.sleep(retry_delay_seconds)
            await queue.push(job.next_attempt())
        return 0


def _find_watch_item(store: WatchlistStore, chat_id: int, ticker: str) -> WatchItem | None:
    ticker = ticker.upper()
    return next((item for item in store.list_watch(chat_id) if item.ticker == ticker), None)


def _connect_redis(redis_url: str):
    try:
        import redis.asyncio as redis
    except ModuleNotFoundError as exc:
        raise RuntimeError("Не установлен Redis-драйвер. Выполните pip install -e .") from exc
    pool = redis.ConnectionPool.from_url(redis_url, decode_responses=True)
    return redis.Redis.from_pool(pool)


def _normalize_datetime(value: dt.datetime | None) -> dt.datetime:
    if value is None:
        return dt.datetime.now(dt.UTC)
    if value.tzinfo is None:
        return value.replace(tzinfo=dt.UTC)
    return value.astimezone(dt.UTC)


def _is_quiet_time(quiet_start: str | None, quiet_end: str | None, now: dt.datetime) -> bool:
    if not quiet_start or not quiet_end:
        return False
    start = dt.time.fromisoformat(quiet_start)
    end = dt.time.fromisoformat(quiet_end)
    current = now.timetz().replace(tzinfo=None)
    if start <= end:
        return start <= current < end
    return current >= start or current < end

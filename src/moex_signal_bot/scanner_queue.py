from __future__ import annotations

import asyncio
import datetime as dt
import json
import socket
from dataclasses import dataclass
from typing import Protocol

from .access_control import AccessControlSettings, is_chat_allowed
from .formatters import format_signal_report
from .scanner import ScannerProvider, SignalSender, is_actionable, scan_tickers
from .storage import WatchItem, WatchlistStore

DEFAULT_QUEUE_KEY = "moex:scanner:stream"
DEFAULT_GROUP_NAME = "scanner-workers"
PAYLOAD_FIELD = "payload"


class ScannerQueue(Protocol):
    async def push(self, job: ScannerJob) -> None: ...

    async def pop(self, *, timeout_seconds: int) -> ScannerQueueMessage | None: ...

    async def ack(self, message: ScannerQueueMessage) -> None: ...


@dataclass(frozen=True)
class ScannerJob:
    ticker: str
    queued_at: dt.datetime
    chat_ids: tuple[int, ...] = ()
    attempts: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "ticker", self.ticker.upper())
        object.__setattr__(self, "queued_at", _normalize_datetime(self.queued_at))
        object.__setattr__(self, "chat_ids", tuple(sorted(int(chat_id) for chat_id in self.chat_ids)))

    def to_json(self) -> str:
        return json.dumps(
            {
                "ticker": self.ticker,
                "queued_at": self.queued_at.isoformat(),
                "chat_ids": list(self.chat_ids),
                "attempts": self.attempts,
            },
            ensure_ascii=True,
            sort_keys=True,
        )

    @classmethod
    def from_json(cls, payload: str) -> ScannerJob:
        data = json.loads(payload)
        raw_chat_ids = data.get("chat_ids")
        if raw_chat_ids is None and "chat_id" in data:
            raw_chat_ids = [data["chat_id"]]
        return cls(
            ticker=str(data["ticker"]),
            queued_at=dt.datetime.fromisoformat(str(data["queued_at"])),
            chat_ids=tuple(int(chat_id) for chat_id in (raw_chat_ids or ())),
            attempts=int(data.get("attempts", 0)),
        )

    def next_attempt(self) -> ScannerJob:
        return ScannerJob(
            ticker=self.ticker,
            queued_at=self.queued_at,
            chat_ids=self.chat_ids,
            attempts=self.attempts + 1,
        )


@dataclass(frozen=True)
class ScannerQueueMessage:
    job: ScannerJob
    message_id: str


class RedisScannerQueue:
    def __init__(
        self,
        redis_url: str,
        *,
        queue_key: str = DEFAULT_QUEUE_KEY,
        group_name: str = DEFAULT_GROUP_NAME,
        consumer_name: str | None = None,
        reclaim_idle_ms: int = 60_000,
        connect=None,
    ) -> None:
        if not redis_url:
            raise RuntimeError("Не задана переменная окружения REDIS_URL для очереди автосканера.")
        self.queue_key = queue_key
        self.group_name = group_name
        self.consumer_name = consumer_name or socket.gethostname()
        self.reclaim_idle_ms = max(1, int(reclaim_idle_ms))
        self._client = connect(redis_url) if connect else _connect_redis(redis_url)
        self._group_ready = False

    async def push(self, job: ScannerJob) -> None:
        await self._client.xadd(self.queue_key, {PAYLOAD_FIELD: job.to_json()})

    async def pop(self, *, timeout_seconds: int) -> ScannerQueueMessage | None:
        await self._ensure_group()
        claimed = await self._claim_stale()
        if claimed is not None:
            return claimed
        result = await self._client.xreadgroup(
            self.group_name,
            self.consumer_name,
            {self.queue_key: ">"},
            count=1,
            block=max(1, int(timeout_seconds)) * 1000,
        )
        return _message_from_streams(result)

    async def ack(self, message: ScannerQueueMessage) -> None:
        await self._client.xack(self.queue_key, self.group_name, message.message_id)

    async def close(self) -> None:
        await self._client.aclose()

    async def _ensure_group(self) -> None:
        if self._group_ready:
            return
        try:
            await self._client.execute_command("XGROUP", "CREATE", self.queue_key, self.group_name, "0", "MKSTREAM")
        except Exception as exc:
            if "BUSYGROUP" not in str(exc):
                raise
        self._group_ready = True

    async def _claim_stale(self) -> ScannerQueueMessage | None:
        result = await self._client.execute_command(
            "XAUTOCLAIM",
            self.queue_key,
            self.group_name,
            self.consumer_name,
            self.reclaim_idle_ms,
            "0-0",
            "COUNT",
            1,
        )
        messages = result[1] if result and len(result) > 1 else []
        if not messages:
            return None
        message_id, fields = messages[0]
        return _message_from_entry(message_id, fields)


async def enqueue_due_scans(store: WatchlistStore, queue: ScannerQueue, *, now: dt.datetime | None = None) -> int:
    now = _normalize_datetime(now)
    due_by_ticker: dict[str, list[WatchItem]] = {}
    for item in store.list_due(now):
        if store.is_muted(item, now):
            store.mark_checked(item.chat_id, item.ticker, now)
            continue
        settings = store.get_settings(item.chat_id)
        if _is_quiet_time(settings.quiet_start, settings.quiet_end, now):
            store.mark_checked(item.chat_id, item.ticker, now)
            continue
        due_by_ticker.setdefault(item.ticker, []).append(item)

    enqueued = 0
    for ticker, items in due_by_ticker.items():
        await queue.push(ScannerJob(ticker=ticker, queued_at=now, chat_ids=tuple(item.chat_id for item in items)))
        for item in items:
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
    access_settings: AccessControlSettings | None = None,
) -> int:
    now = _normalize_datetime(now)
    access_settings = access_settings or AccessControlSettings()
    reports = await scan_tickers(provider, [job.ticker], today=today or now.date())
    if not reports:
        return 0
    report = reports[0]
    sent = 0
    for chat_id in _job_chat_ids(store, job):
        item = _find_watch_item(store, chat_id, job.ticker)
        if item is None:
            continue
        if not is_chat_allowed(store, chat_id, access_settings):
            continue
        if store.is_muted(item, now):
            continue
        settings = store.get_settings(chat_id)
        if _is_quiet_time(settings.quiet_start, settings.quiet_end, now):
            continue
        threshold = max(min_score, settings.min_score)
        if settings.alert_types and report.alert_type not in settings.alert_types:
            continue
        if not is_actionable(report, min_score=threshold):
            continue
        if not store.reserve_signal(chat_id, report.ticker, report.state.code, report.signal_key, now):
            continue
        try:
            await telegram.send_message(chat_id, format_signal_report(report, automatic=True))
        except Exception:
            store.release_signal_reservation(chat_id, report.ticker, report.state.code, report.signal_key)
            raise
        store.mark_signal_sent(chat_id, report.ticker, report.state.code, report.signal_key, now)
        sent += 1
    return sent


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
    access_settings: AccessControlSettings | None = None,
) -> int:
    message = await queue.pop(timeout_seconds=pop_timeout_seconds)
    if message is None:
        return 0
    try:
        sent = await process_scanner_job(
            provider,
            store,
            telegram,
            message.job,
            now=now,
            today=today,
            access_settings=access_settings,
        )
        await queue.ack(message)
        return sent
    except Exception as exc:
        print(f"Ошибка worker автосканера для {message.job.ticker}: {exc}", flush=True)
        if message.job.attempts < max_attempts:
            if retry_delay_seconds > 0:
                await asyncio.sleep(retry_delay_seconds)
            await queue.push(message.job.next_attempt())
        await queue.ack(message)
        return 0


def _job_chat_ids(store: WatchlistStore, job: ScannerJob) -> tuple[int, ...]:
    if job.chat_ids:
        return job.chat_ids
    return tuple(item.chat_id for item in store.list_watch_by_ticker(job.ticker))


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


def _message_from_streams(streams) -> ScannerQueueMessage | None:
    if not streams:
        return None
    _, messages = streams[0]
    if not messages:
        return None
    message_id, fields = messages[0]
    return _message_from_entry(message_id, fields)


def _message_from_entry(message_id, fields) -> ScannerQueueMessage:
    payload = fields.get(PAYLOAD_FIELD) or fields.get(PAYLOAD_FIELD.encode())
    if isinstance(payload, bytes):
        payload = payload.decode()
    return ScannerQueueMessage(job=ScannerJob.from_json(str(payload)), message_id=str(message_id))


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

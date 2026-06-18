import asyncio
import datetime as dt

from test_scanner import FakeProvider, FakeTelegram

from moex_signal_bot.access_control import AccessControlSettings
from moex_signal_bot.memory_storage import InMemoryWatchlistStore
from moex_signal_bot.scanner_queue import (
    RedisScannerQueue,
    ScannerJob,
    ScannerQueueMessage,
    enqueue_due_scans,
    process_scanner_job,
    scanner_worker_iteration,
)


class FakeQueue:
    def __init__(self, messages=None):
        self.messages = list(messages or [])
        self.pushed = []
        self.acked = []

    async def push(self, job):
        self.pushed.append(job)

    async def pop(self, *, timeout_seconds):
        if self.messages:
            return self.messages.pop(0)
        return None

    async def ack(self, message):
        self.acked.append(message)


def test_scanner_job_round_trips_as_json():
    queued_at = dt.datetime(2026, 6, 18, 11, 0, tzinfo=dt.UTC)
    job = ScannerJob(ticker="rosn", queued_at=queued_at, chat_ids=(123, 456), attempts=2)

    decoded = ScannerJob.from_json(job.to_json())

    assert decoded == ScannerJob(ticker="ROSN", queued_at=queued_at, chat_ids=(123, 456), attempts=2)


def test_enqueue_due_scans_batches_due_chats_by_ticker_and_marks_items_checked():
    now = dt.datetime(2026, 6, 18, 11, 0, tzinfo=dt.UTC)
    store = InMemoryWatchlistStore()
    store.add_watch(123, "rosn", interval_minutes=15, now=now)
    store.add_watch(456, "ROSN", interval_minutes=15, now=now)
    store.add_watch(789, "SBER", interval_minutes=15, now=now)
    queue = FakeQueue()

    enqueued = asyncio.run(enqueue_due_scans(store, queue, now=now))

    assert enqueued == 2
    assert queue.pushed == [
        ScannerJob(ticker="ROSN", queued_at=now, chat_ids=(123, 456), attempts=0),
        ScannerJob(ticker="SBER", queued_at=now, chat_ids=(789,), attempts=0),
    ]
    assert store.list_due(now) == []


def test_process_scanner_job_scans_once_and_fans_out_to_due_chats():
    now = dt.datetime(2026, 6, 18, 11, 0, tzinfo=dt.UTC)
    store = InMemoryWatchlistStore()
    store.add_watch(123, "rosn", interval_minutes=15, now=now)
    store.add_watch(456, "ROSN", interval_minutes=15, now=now)
    telegram = FakeTelegram()
    provider = FakeProvider()
    job = ScannerJob(ticker="ROSN", queued_at=now, chat_ids=(123, 456))

    sent = asyncio.run(process_scanner_job(provider, store, telegram, job, now=now, today=dt.date(2026, 6, 18)))
    sent_again = asyncio.run(
        process_scanner_job(FakeProvider(), store, telegram, job, now=now, today=dt.date(2026, 6, 18))
    )

    assert sent == 2
    assert sent_again == 0
    assert len(telegram.sent) == 2
    assert [call for call in provider.calls if call[0] == "tradestats"] == [
        ("tradestats", "ROSN", "2026-06-18", "2026-06-18")
    ]
    assert [chat_id for chat_id, _ in telegram.sent] == [123, 456]


def test_process_scanner_job_skips_non_allowed_chats_when_access_control_enabled():
    now = dt.datetime(2026, 6, 18, 11, 0, tzinfo=dt.UTC)
    store = InMemoryWatchlistStore()
    store.add_watch(123, "rosn", interval_minutes=15, now=now)
    store.add_watch(456, "ROSN", interval_minutes=15, now=now)
    store.record_telegram_user(123, username="pending")
    store.record_telegram_user(456, username="paid")
    store.set_telegram_user_status(456, "allowed")
    telegram = FakeTelegram()
    provider = FakeProvider()
    job = ScannerJob(ticker="ROSN", queued_at=now, chat_ids=(123, 456))

    sent = asyncio.run(
        process_scanner_job(
            provider,
            store,
            telegram,
            job,
            now=now,
            today=dt.date(2026, 6, 18),
            access_settings=AccessControlSettings(enabled=True, admin_chat_ids=()),
        )
    )

    assert sent == 1
    assert [chat_id for chat_id, _ in telegram.sent] == [456]


def test_process_scanner_job_releases_reservation_when_send_fails():
    class FailingTelegram(FakeTelegram):
        async def send_message(self, chat_id, text):
            raise RuntimeError("telegram down")

    now = dt.datetime(2026, 6, 18, 11, 0, tzinfo=dt.UTC)
    store = InMemoryWatchlistStore()
    store.add_watch(123, "rosn", interval_minutes=15, now=now)
    job = ScannerJob(ticker="ROSN", queued_at=now, chat_ids=(123,))

    try:
        asyncio.run(
            process_scanner_job(
                FakeProvider(),
                store,
                FailingTelegram(),
                job,
                now=now,
                today=dt.date(2026, 6, 18),
            )
        )
    except RuntimeError:
        pass
    else:
        raise AssertionError("telegram failure must propagate for queue retry")

    assert store.was_signal_sent(123, "ROSN", "sell_pressure", "2026-06-18:10:05:00:sell_pressure:94") is False
    assert store.reserve_signal(123, "ROSN", "sell_pressure", "2026-06-18:10:05:00:sell_pressure:94", now) is True


def test_scanner_worker_iteration_requeues_failed_job_with_attempt_count():
    class FailingProvider(FakeProvider):
        async def tradestats(self, ticker, start, end):
            raise RuntimeError("temporary moex failure")

    now = dt.datetime(2026, 6, 18, 11, 0, tzinfo=dt.UTC)
    store = InMemoryWatchlistStore()
    store.add_watch(123, "rosn", interval_minutes=15, now=now)
    message = ScannerQueueMessage(ScannerJob(ticker="ROSN", queued_at=now, chat_ids=(123,)), message_id="1-0")
    queue = FakeQueue([message])
    telegram = FakeTelegram()

    sent = asyncio.run(
        scanner_worker_iteration(
            FailingProvider(),
            store,
            telegram,
            queue,
            now=now,
            today=dt.date(2026, 6, 18),
            retry_delay_seconds=0,
        )
    )

    assert sent == 0
    assert queue.acked == [message]
    assert queue.pushed == [ScannerJob(ticker="ROSN", queued_at=now, chat_ids=(123,), attempts=1)]
    assert telegram.sent == []


def test_scanner_worker_iteration_acks_successful_message():
    now = dt.datetime(2026, 6, 18, 11, 0, tzinfo=dt.UTC)
    store = InMemoryWatchlistStore()
    store.add_watch(123, "rosn", interval_minutes=15, now=now)
    message = ScannerQueueMessage(ScannerJob(ticker="ROSN", queued_at=now, chat_ids=(123,)), message_id="1-0")
    queue = FakeQueue([message])

    sent = asyncio.run(
        scanner_worker_iteration(
            FakeProvider(),
            store,
            FakeTelegram(),
            queue,
            now=now,
            today=dt.date(2026, 6, 18),
        )
    )

    assert sent == 1
    assert queue.acked == [message]


def test_redis_scanner_queue_uses_streams_with_acknowledgement():
    class FakeRedis:
        def __init__(self):
            self.calls = []

        async def execute_command(self, *args):
            self.calls.append(args)
            if args[0] == "XAUTOCLAIM":
                return ["0-0", []]
            return "OK"

        async def xadd(self, *args, **kwargs):
            self.calls.append(("xadd", args, kwargs))
            return "1-0"

        async def xreadgroup(self, *args, **kwargs):
            self.calls.append(("xreadgroup", args, kwargs))
            payload = ScannerJob(
                ticker="ROSN",
                queued_at=dt.datetime(2026, 6, 18, 11, 0, tzinfo=dt.UTC),
                chat_ids=(123,),
            )
            return [["moex:scanner:stream", [("1-0", {"payload": payload.to_json()})]]]

        async def xack(self, *args):
            self.calls.append(("xack", args))

    redis = FakeRedis()
    queue = RedisScannerQueue("redis://example", connect=lambda _: redis)

    message = asyncio.run(queue.pop(timeout_seconds=1))
    asyncio.run(queue.ack(message))

    assert message == ScannerQueueMessage(
        ScannerJob(ticker="ROSN", queued_at=dt.datetime(2026, 6, 18, 11, 0, tzinfo=dt.UTC), chat_ids=(123,)),
        message_id="1-0",
    )
    assert ("XGROUP", "CREATE", "moex:scanner:stream", "scanner-workers", "0", "MKSTREAM") in redis.calls
    assert any(call[0] == "xreadgroup" for call in redis.calls)
    assert any(call[0] == "xack" for call in redis.calls)
    assert not any(call[0] in {"blpop", "rpush"} for call in redis.calls)

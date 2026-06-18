import asyncio
import datetime as dt

from test_scanner import FakeProvider, FakeTelegram

from moex_signal_bot.memory_storage import InMemoryWatchlistStore
from moex_signal_bot.scanner_queue import (
    ScannerJob,
    enqueue_due_scans,
    process_scanner_job,
    scanner_worker_iteration,
)


class FakeQueue:
    def __init__(self, jobs=None):
        self.jobs = list(jobs or [])
        self.pushed = []

    async def push(self, job):
        self.pushed.append(job)

    async def pop(self, *, timeout_seconds):
        if self.jobs:
            return self.jobs.pop(0)
        return None


def test_scanner_job_round_trips_as_json():
    queued_at = dt.datetime(2026, 6, 18, 11, 0, tzinfo=dt.UTC)
    job = ScannerJob(chat_id=123, ticker="rosn", queued_at=queued_at, attempts=2)

    decoded = ScannerJob.from_json(job.to_json())

    assert decoded == ScannerJob(chat_id=123, ticker="ROSN", queued_at=queued_at, attempts=2)


def test_enqueue_due_scans_pushes_jobs_and_marks_items_checked():
    now = dt.datetime(2026, 6, 18, 11, 0, tzinfo=dt.UTC)
    store = InMemoryWatchlistStore()
    store.add_watch(123, "rosn", interval_minutes=15, now=now)
    queue = FakeQueue()

    enqueued = asyncio.run(enqueue_due_scans(store, queue, now=now))

    assert enqueued == 1
    assert queue.pushed == [ScannerJob(chat_id=123, ticker="ROSN", queued_at=now, attempts=0)]
    assert store.list_due(now) == []


def test_process_scanner_job_sends_actionable_signal_once():
    now = dt.datetime(2026, 6, 18, 11, 0, tzinfo=dt.UTC)
    store = InMemoryWatchlistStore()
    store.add_watch(123, "rosn", interval_minutes=15, now=now)
    telegram = FakeTelegram()
    job = ScannerJob(chat_id=123, ticker="ROSN", queued_at=now)

    sent = asyncio.run(process_scanner_job(FakeProvider(), store, telegram, job, now=now, today=dt.date(2026, 6, 18)))
    sent_again = asyncio.run(
        process_scanner_job(FakeProvider(), store, telegram, job, now=now, today=dt.date(2026, 6, 18))
    )

    assert sent == 1
    assert sent_again == 0
    assert len(telegram.sent) == 1
    assert telegram.sent[0][0] == 123
    assert "Автосигнал ROSN" in telegram.sent[0][1]


def test_scanner_worker_iteration_requeues_failed_job_with_attempt_count():
    class FailingProvider(FakeProvider):
        async def tradestats(self, ticker, start, end):
            raise RuntimeError("temporary moex failure")

    now = dt.datetime(2026, 6, 18, 11, 0, tzinfo=dt.UTC)
    store = InMemoryWatchlistStore()
    store.add_watch(123, "rosn", interval_minutes=15, now=now)
    queue = FakeQueue([ScannerJob(chat_id=123, ticker="ROSN", queued_at=now)])
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
    assert queue.pushed == [ScannerJob(chat_id=123, ticker="ROSN", queued_at=now, attempts=1)]
    assert telegram.sent == []

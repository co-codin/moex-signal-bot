import asyncio
import datetime as dt

from moex_signal_bot.memory_storage import InMemoryWatchlistStore as WatchlistStore
from moex_signal_bot.scanner import build_signal_report, run_scan_once, scan_tickers

SELLING_TRADESTATS = [
    {
        "tradedate": "2026-06-18",
        "tradetime": "10:00:00",
        "pr_open": 336,
        "pr_close": 333,
        "val_b": 20_000_000,
        "val_s": 80_000_000,
    },
    {
        "tradedate": "2026-06-18",
        "tradetime": "10:05:00",
        "pr_open": 333,
        "pr_close": 328,
        "val_b": 10_000_000,
        "val_s": 90_000_000,
    },
]


def test_build_signal_report_scores_sell_pressure_from_multiple_sources():
    report = build_signal_report(
        "rosn",
        tradestats=SELLING_TRADESTATS,
        orderstats=[{"put_val_b": 30_000_000, "put_val_s": 120_000_000}],
        obstats=[{"tradedate": "2026-06-18", "tradetime": "10:05:00", "imbalance_val_bbo": -0.21}],
        alerts=[
            {"tradedate": "2026-06-18", "tradetime": "10:04:00", "alert_type": "pr_low_min", "value": 328},
            {"tradedate": "2026-06-18", "tradetime": "10:05:00", "alert_type": "pr_low_min", "value": 327.8},
        ],
    )

    assert report.ticker == "ROSN"
    assert report.state.code == "sell_pressure"
    assert report.score >= 80
    assert report.direction == "short"
    assert report.alert_type == "breakdown"
    assert report.features.low_alerts == 2
    assert report.features.high_alerts == 0
    assert report.features.megaalert_count == 2
    assert report.features.order_bias < 0
    assert report.features.bbo_imbalance < 0
    assert report.support == 328
    assert "давление продаж" in " ".join(report.reasons).lower()


def test_build_signal_report_detects_absorption_when_buyers_hold_down_move():
    report = build_signal_report(
        "rosn",
        tradestats=[
            {
                "tradedate": "2026-06-18",
                "tradetime": "10:00:00",
                "pr_open": 336,
                "pr_close": 332,
                "val_b": 75_000_000,
                "val_s": 25_000_000,
            }
        ],
        orderstats=[{"put_val_b": 90_000_000, "put_val_s": 40_000_000}],
        obstats=[{"tradedate": "2026-06-18", "tradetime": "10:00:00", "imbalance_val_bbo": 0.18}],
        alerts=[],
    )

    assert report.state.code == "absorption"
    assert report.direction == "watch_long"
    assert report.alert_type == "absorption"
    assert report.score >= 55


class FakeProvider:
    def __init__(self):
        self.calls = []

    async def tradestats(self, ticker, start, end):
        self.calls.append(("tradestats", ticker, start, end))
        return SELLING_TRADESTATS if ticker == "ROSN" else []

    async def orderstats(self, ticker, start, end):
        self.calls.append(("orderstats", ticker, start, end))
        return [{"put_val_b": 30_000_000, "put_val_s": 120_000_000}]

    async def obstats(self, ticker, start, end):
        self.calls.append(("obstats", ticker, start, end))
        return [{"tradedate": "2026-06-18", "tradetime": "10:05:00", "imbalance_val_bbo": -0.21}]

    async def alerts(self, ticker, start, end):
        self.calls.append(("alerts", ticker, start, end))
        return [{"tradedate": "2026-06-18", "tradetime": "10:05:00", "alert_type": "pr_low_min", "value": 328}]


class FakeTelegram:
    def __init__(self):
        self.sent = []

    async def send_message(self, chat_id, text):
        self.sent.append((chat_id, text))


def test_scan_tickers_returns_actionable_reports():
    reports = asyncio.run(scan_tickers(FakeProvider(), ["rosn", "empty"], today=dt.date(2026, 6, 18)))

    assert [report.ticker for report in reports] == ["ROSN", "EMPTY"]
    assert reports[0].score >= 60
    assert reports[1].state.code == "neutral"


def test_run_scan_once_sends_due_actionable_signals_once(tmp_path):
    now = dt.datetime(2026, 6, 18, 11, 0, tzinfo=dt.UTC)
    store = WatchlistStore()
    store.add_watch(123, "rosn", interval_minutes=5, now=now)
    telegram = FakeTelegram()

    sent = asyncio.run(run_scan_once(FakeProvider(), store, telegram, now=now, today=dt.date(2026, 6, 18)))
    sent_again = asyncio.run(
        run_scan_once(FakeProvider(), store, telegram, now=now + dt.timedelta(minutes=5), today=dt.date(2026, 6, 18))
    )

    assert sent == 1
    assert sent_again == 0
    assert len(telegram.sent) == 1
    assert telegram.sent[0][0] == 123
    assert "Автосигнал ROSN" in telegram.sent[0][1]


def test_run_scan_once_releases_signal_reservation_when_send_fails(tmp_path):
    class FailingTelegram(FakeTelegram):
        async def send_message(self, chat_id, text):
            raise RuntimeError("telegram down")

    now = dt.datetime(2026, 6, 18, 11, 0, tzinfo=dt.UTC)
    store = WatchlistStore()
    store.add_watch(123, "rosn", interval_minutes=5, now=now)

    try:
        asyncio.run(run_scan_once(FakeProvider(), store, FailingTelegram(), now=now, today=dt.date(2026, 6, 18)))
    except RuntimeError:
        pass
    else:
        raise AssertionError("telegram failure must propagate")

    signal_key = "2026-06-18:10:05:00:sell_pressure:94"
    assert store.was_signal_sent(123, "ROSN", "sell_pressure", signal_key) is False
    assert store.reserve_signal(123, "ROSN", "sell_pressure", signal_key, now) is True


def test_run_scan_once_respects_chat_min_score(tmp_path):
    now = dt.datetime(2026, 6, 18, 11, 0, tzinfo=dt.UTC)
    store = WatchlistStore()
    store.add_watch(123, "rosn", interval_minutes=5, now=now)
    store.set_min_score(123, 100)
    telegram = FakeTelegram()

    sent = asyncio.run(run_scan_once(FakeProvider(), store, telegram, now=now, today=dt.date(2026, 6, 18)))

    assert sent == 0
    assert telegram.sent == []


def test_run_scan_once_respects_alert_type_filter(tmp_path):
    now = dt.datetime(2026, 6, 18, 11, 0, tzinfo=dt.UTC)
    store = WatchlistStore()
    store.add_watch(123, "rosn", interval_minutes=5, now=now)
    store.set_alert_types(123, ("absorption",))
    telegram = FakeTelegram()

    sent = asyncio.run(run_scan_once(FakeProvider(), store, telegram, now=now, today=dt.date(2026, 6, 18)))

    assert sent == 0
    assert telegram.sent == []


def test_run_scan_once_skips_provider_calls_for_muted_items(tmp_path):
    now = dt.datetime(2026, 6, 18, 11, 0, tzinfo=dt.UTC)
    store = WatchlistStore()
    store.add_watch(123, "rosn", interval_minutes=5, now=now)
    store.mute(123, "rosn", now + dt.timedelta(minutes=60))
    provider = FakeProvider()
    telegram = FakeTelegram()

    sent = asyncio.run(run_scan_once(provider, store, telegram, now=now, today=dt.date(2026, 6, 18)))

    assert sent == 0
    assert provider.calls == []
    assert telegram.sent == []


def test_run_scan_once_respects_quiet_hours(tmp_path):
    now = dt.datetime(2026, 6, 18, 21, 15, tzinfo=dt.UTC)
    store = WatchlistStore()
    store.add_watch(123, "rosn", interval_minutes=5, now=now)
    store.set_quiet_hours(123, "21:00", "07:00")
    provider = FakeProvider()
    telegram = FakeTelegram()

    sent = asyncio.run(run_scan_once(provider, store, telegram, now=now, today=dt.date(2026, 6, 18)))

    assert sent == 0
    assert provider.calls == []
    assert telegram.sent == []

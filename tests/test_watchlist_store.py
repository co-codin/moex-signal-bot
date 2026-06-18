import datetime as dt

from moex_signal_bot.storage import WatchlistStore


def test_watchlist_store_adds_lists_mutes_and_removes_tickers(tmp_path):
    store = WatchlistStore(tmp_path / "signals.sqlite3")
    now = dt.datetime(2026, 6, 18, 10, 0, tzinfo=dt.UTC)

    store.add_watch(123, "rosn", interval_minutes=5, now=now)
    store.add_watch(123, "sber", interval_minutes=15, now=now)

    items = store.list_watch(123)

    assert [item.ticker for item in items] == ["ROSN", "SBER"]
    assert items[0].interval_minutes == 5
    assert store.list_due(now) == items

    store.mark_checked(123, "ROSN", now)
    assert [item.ticker for item in store.list_due(now + dt.timedelta(minutes=4))] == ["SBER"]
    assert [item.ticker for item in store.list_due(now + dt.timedelta(minutes=5))] == ["ROSN", "SBER"]

    muted_until = now + dt.timedelta(minutes=60)
    store.mute(123, "ROSN", muted_until)

    muted = store.list_watch(123)[0]
    assert muted.muted_until == muted_until
    assert store.is_muted(muted, now + dt.timedelta(minutes=30)) is True
    assert store.is_muted(muted, now + dt.timedelta(minutes=61)) is False

    assert store.remove_watch(123, "ROSN") is True
    assert store.remove_watch(123, "ROSN") is False
    assert [item.ticker for item in store.list_watch(123)] == ["SBER"]


def test_watchlist_store_dedupes_sent_signals(tmp_path):
    store = WatchlistStore(tmp_path / "signals.sqlite3")
    now = dt.datetime(2026, 6, 18, 11, 0, tzinfo=dt.UTC)

    assert store.was_signal_sent(123, "rosn", "sell_pressure", "2026-06-18T11:00") is False

    store.mark_signal_sent(123, "rosn", "sell_pressure", "2026-06-18T11:00", now)
    store.mark_signal_sent(123, "ROSN", "sell_pressure", "2026-06-18T11:00", now)

    assert store.was_signal_sent(123, "ROSN", "sell_pressure", "2026-06-18T11:00") is True

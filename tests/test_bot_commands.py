import asyncio
import datetime as dt

from moex_signal_bot.bot import Command, handle_command, parse_command
from moex_signal_bot.storage import WatchlistStore


class FakeProvider:
    def __init__(self):
        self.calls = []

    async def tradestats(self, ticker, start, end):
        self.calls.append(("tradestats", ticker, start, end))
        return [
            {
                "tradedate": "2026-06-18",
                "tradetime": "10:00:00",
                "pr_open": 336,
                "pr_close": 330,
                "val_b": 70,
                "val_s": 30,
            },
            {
                "tradedate": "2026-06-18",
                "tradetime": "10:05:00",
                "pr_open": 330,
                "pr_close": 328,
                "val_b": 10,
                "val_s": 90,
            },
        ]

    async def orderstats(self, ticker, start, end):
        self.calls.append(("orderstats", ticker, start, end))
        return [{"put_val_b": 30_000_000, "put_val_s": 120_000_000}]

    async def obstats(self, ticker, start, end):
        self.calls.append(("obstats", ticker, start, end))
        return [{"tradedate": "2026-06-18", "tradetime": "10:05:00", "imbalance_val_bbo": -0.21}]

    async def alerts(self, ticker, start, end):
        self.calls.append(("alerts", ticker, start, end))
        return [{"tradedate": "2026-06-18", "tradetime": "10:05:00", "alert_type": "pr_low_min", "value": 328}]

    async def quote(self, ticker):
        self.calls.append(("quote", ticker))
        return {"ticker": ticker, "last": 328.5, "last_to_prev_pct": -2.1, "time": "10:05:00"}

    async def futoi(self, ticker, start, end):
        self.calls.append(("futoi", ticker, start, end))
        return [
            {"tradedate": "2026-06-18", "tradetime": "10:00:00", "clgroup": "phys", "pos_long": 100, "pos_short": 40},
            {"tradedate": "2026-06-18", "tradetime": "10:00:00", "clgroup": "jur", "pos_long": 80, "pos_short": 120},
        ]


def test_parse_command_defaults_to_russian_help_for_unknown_text():
    assert parse_command("/flow rosn 7") == Command(name="flow", ticker="ROSN", days=7)
    assert parse_command("/strategy sber") == Command(name="strategy", ticker="SBER", days=7)
    assert parse_command("/scan rosn sber").tickers == ("ROSN", "SBER")
    assert parse_command("/watch rosn 5m").minutes == 5
    assert parse_command("/heatmap rosn sber").tickers == ("ROSN", "SBER")
    assert parse_command("/score 75").args == ("75",)
    assert parse_command("что делать") == Command(name="help", ticker=None, days=1)


def test_handle_flow_command_returns_russian_buy_sell_power_report():
    text = asyncio.run(handle_command("/flow rosn 7", FakeProvider()))

    assert "ROSN" in text
    assert "Покупательная сила" in text
    assert "Продавцы" in text
    assert "Итог за период" in text


def test_handle_strategy_command_returns_russian_signal_report():
    text = asyncio.run(handle_command("/strategy rosn", FakeProvider()))

    assert "Сигнал по ROSN" in text
    assert "Состояние" in text
    assert "План" in text


def test_handle_help_command_is_russian():
    text = asyncio.run(handle_command("/help", FakeProvider()))

    assert "Команды" in text
    assert "/flow ROSN 7" in text
    assert "Scanner Pro" in text
    assert "FUTOI" in text
    assert "Портфель" in text
    assert "не является инвестиционной рекомендацией" in text
    assert "русском" in text


def test_handle_watchlist_commands_are_russian_and_persistent(tmp_path):
    store = WatchlistStore(tmp_path / "signals.sqlite3")

    added = asyncio.run(handle_command("/watch rosn 5m", FakeProvider(), store=store, chat_id=123))
    listed = asyncio.run(handle_command("/watchlist", FakeProvider(), store=store, chat_id=123))
    muted = asyncio.run(
        handle_command(
            "/mute rosn 60",
            FakeProvider(),
            store=store,
            chat_id=123,
            now=dt.datetime(2026, 6, 18, 11, 0, tzinfo=dt.UTC),
        )
    )
    removed = asyncio.run(handle_command("/unwatch rosn", FakeProvider(), store=store, chat_id=123))

    assert "ROSN добавлен" in added
    assert "ROSN" in listed
    assert "Пауза" in muted
    assert "ROSN удален" in removed


def test_handle_signal_scan_and_full_commands_return_russian_reports(tmp_path):
    store = WatchlistStore(tmp_path / "signals.sqlite3")

    signal = asyncio.run(handle_command("/signal rosn", FakeProvider(), store=store, chat_id=123))
    scan = asyncio.run(handle_command("/scan rosn sber", FakeProvider(), store=store, chat_id=123))
    full = asyncio.run(handle_command("/full rosn", FakeProvider(), store=store, chat_id=123))

    assert "Сигнал ROSN" in signal
    assert "Сканер" in scan
    assert "ROSN" in scan
    assert "Полный отчет ROSN" in full
    assert "Котировка" in full


def test_handle_settings_commands_update_watchlist_pro_preferences(tmp_path):
    store = WatchlistStore(tmp_path / "signals.sqlite3")

    score = asyncio.run(handle_command("/score 75", FakeProvider(), store=store, chat_id=123))
    quiet = asyncio.run(handle_command("/quiet 23:00 07:00", FakeProvider(), store=store, chat_id=123))
    types = asyncio.run(handle_command("/types sell_pressure absorption", FakeProvider(), store=store, chat_id=123))
    settings = asyncio.run(handle_command("/settings", FakeProvider(), store=store, chat_id=123))

    assert "Минимальная сила: 75/100" in score
    assert "Тихие часы: 23:00-07:00" in quiet
    assert "sell_pressure" in types
    assert "Настройки" in settings
    assert "75/100" in settings
    assert "absorption" in settings


def test_handle_heatmap_mega_digest_futoi_stats_and_channel_commands_are_russian(tmp_path):
    store = WatchlistStore(tmp_path / "signals.sqlite3")
    provider = FakeProvider()

    heatmap = asyncio.run(
        handle_command("/heatmap rosn sber", provider, store=store, chat_id=123, today=dt.date(2026, 6, 18))
    )
    mega = asyncio.run(handle_command("/mega rosn", provider, store=store, chat_id=123, today=dt.date(2026, 6, 18)))
    digest = asyncio.run(
        handle_command("/digest rosn sber", provider, store=store, chat_id=123, today=dt.date(2026, 6, 18))
    )
    futoi = asyncio.run(handle_command("/futoi sberf", provider, store=store, chat_id=123, today=dt.date(2026, 6, 18)))
    stats = asyncio.run(handle_command("/stats rosn 3", provider, store=store, chat_id=123, today=dt.date(2026, 6, 18)))
    channel = asyncio.run(
        handle_command("/channel_signal rosn", provider, store=store, chat_id=123, today=dt.date(2026, 6, 18))
    )

    assert "Тепловая карта" in heatmap
    assert "MegaAlert ROSN" in mega
    assert "Дайджест" in digest
    assert "FUTOI SBERF" in futoi
    assert "Статистика ROSN" in stats
    assert "MOEX Flow Alert: ROSN" in channel


def test_handle_portfolio_commands_persist_and_report_risk(tmp_path):
    store = WatchlistStore(tmp_path / "signals.sqlite3")
    provider = FakeProvider()

    added = asyncio.run(handle_command("/portfolio_add rosn", provider, store=store, chat_id=123))
    listed = asyncio.run(handle_command("/portfolio", provider, store=store, chat_id=123))
    risk = asyncio.run(
        handle_command("/portfolio_risk", provider, store=store, chat_id=123, today=dt.date(2026, 6, 18))
    )
    removed = asyncio.run(handle_command("/portfolio_remove rosn", provider, store=store, chat_id=123))

    assert "ROSN добавлен" in added
    assert "Портфель" in listed
    assert "ROSN" in listed
    assert "Риск портфеля" in risk
    assert "ROSN удален" in removed

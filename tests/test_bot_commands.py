import asyncio
import datetime as dt
from zoneinfo import ZoneInfo

from moex_signal_bot.bot import Command, handle_command, parse_command
from moex_signal_bot.memory_storage import InMemoryWatchlistStore as WatchlistStore


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

    async def options_chain(self, underlying):
        self.calls.append(("options_chain", underlying))
        return [
            {
                "secid": "SBER6L26000BA5",
                "assetcode": "SBER",
                "optiontype": "call",
                "strike": 26000,
                "lasttradedate": "2026-06-18",
                "last": 210,
                "bid": 205,
                "offer": 215,
                "voltoday": 1200,
                "valtoday": 25_200_000,
                "openposition": 3400,
            },
            {
                "secid": "SBER6R24000BA5",
                "assetcode": "SBER",
                "optiontype": "put",
                "strike": 24000,
                "lasttradedate": "2026-06-18",
                "last": 130,
                "bid": 125,
                "offer": 135,
                "voltoday": 900,
                "valtoday": 11_700_000,
                "openposition": 2800,
            },
            {
                "secid": "GAZR6L12000BA5",
                "assetcode": "GAZP",
                "optiontype": "call",
                "strike": 12000,
                "voltoday": 5000,
                "valtoday": 90_000_000,
            },
        ]

    async def option_quote(self, ticker):
        self.calls.append(("option_quote", ticker))
        return {
            "ticker": ticker,
            "last": 210,
            "bid": 205,
            "offer": 215,
            "last_to_prev_pct": 4.2,
            "time": "14:20:00",
        }

    async def option_trades(self, ticker):
        self.calls.append(("option_trades", ticker))
        return [
            {"tradetime": "14:15:00", "price": 208, "quantity": 10, "value": 208_000},
            {"tradetime": "14:20:00", "price": 210, "quantity": 5, "value": 105_000},
        ]


def test_parse_command_defaults_to_russian_help_for_unknown_text():
    assert parse_command("/flow rosn 7") == Command(name="flow", ticker="ROSN", days=7)
    assert parse_command("/strategy sber") == Command(name="strategy", ticker="SBER", days=7)
    assert parse_command("/scan rosn sber").tickers == ("ROSN", "SBER")
    assert parse_command("/watch rosn 5m").minutes == 5
    assert parse_command("/heatmap rosn sber").tickers == ("ROSN", "SBER")
    assert parse_command("/marketflow rosn sber").tickers == ("ROSN", "SBER")
    assert parse_command("/optionflow sber").ticker == "SBER"
    assert parse_command("/option sber6l26000ba5").ticker == "SBER6L26000BA5"
    assert parse_command("/score 75").args == ("75",)
    assert parse_command("/stats rosn").days == 30
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
    assert "/marketflow" in text
    assert "Scanner Pro" in text
    assert "FUTOI" in text
    assert "Портфель" in text
    assert "не является инвестиционной рекомендацией" in text
    assert "русском" in text


def test_handle_optionflow_command_returns_options_activity_not_buy_sell_flow():
    provider = FakeProvider()

    text = asyncio.run(handle_command("/optionflow sber", provider))

    assert "Опционная активность SBER" in text
    assert "SBER6L26000BA5" in text
    assert "SBER6R24000BA5" in text
    assert "Call: 1" in text
    assert "Put: 1" in text
    assert "не ALGOPACK buy/sell flow" in text
    assert "GAZR6L12000BA5" not in text
    assert ("options_chain", "SBER") in provider.calls


def test_handle_option_command_returns_contract_snapshot_and_raw_trades():
    provider = FakeProvider()

    text = asyncio.run(handle_command("/option sber6l26000ba5", provider))

    assert "Опцион SBER6L26000BA5" in text
    assert "Last: 210.00" in text
    assert "Спрос/предложение: 205.00 / 215.00" in text
    assert "Сделок: 2" in text
    assert "Оборот: 0.3 млн ₽" in text
    assert "Последняя сделка: 14:20:00 210.00 x 5" in text
    assert "не подтверждает сторону покупателя/продавца" in text
    assert ("option_quote", "SBER6L26000BA5") in provider.calls
    assert ("option_trades", "SBER6L26000BA5") in provider.calls


def test_handle_marketflow_command_shows_last_two_hour_buy_sell_leaders():
    class MarketFlowProvider(FakeProvider):
        async def tradestats(self, ticker, start, end):
            self.calls.append(("tradestats", ticker, start, end))
            rows_by_ticker = {
                "ROSN": [
                    {
                        "tradedate": "2026-06-18",
                        "tradetime": "12:10:00",
                        "pr_open": 101,
                        "pr_close": 102,
                        "val_b": 900_000_000,
                        "val_s": 100_000_000,
                    },
                    {
                        "tradedate": "2026-06-18",
                        "tradetime": "12:30:00",
                        "pr_open": 100,
                        "pr_close": 104,
                        "val_b": 200_000_000,
                        "val_s": 50_000_000,
                    },
                    {
                        "tradedate": "2026-06-18",
                        "tradetime": "14:20:00",
                        "pr_open": 104,
                        "pr_close": 110,
                        "val_b": 100_000_000,
                        "val_s": 50_000_000,
                    },
                ],
                "SBER": [
                    {
                        "tradedate": "2026-06-18",
                        "tradetime": "12:30:00",
                        "pr_open": 300,
                        "pr_close": 297,
                        "val_b": 100_000_000,
                        "val_s": 300_000_000,
                    },
                    {
                        "tradedate": "2026-06-18",
                        "tradetime": "14:20:00",
                        "pr_open": 297,
                        "pr_close": 294,
                        "val_b": 50_000_000,
                        "val_s": 250_000_000,
                    },
                ],
            }
            return rows_by_ticker[ticker]

        async def quote(self, ticker):
            self.calls.append(("quote", ticker))
            quotes = {
                "ROSN": {"last": 110.0, "last_to_prev_pct": 1.25, "time": "14:20:00"},
                "SBER": {"last": 294.0, "last_to_prev_pct": -1.1, "time": "14:20:00"},
            }
            return quotes[ticker]

    provider = MarketFlowProvider()

    text = asyncio.run(
        handle_command(
            "/marketflow rosn sber",
            provider,
            now=dt.datetime(2026, 6, 18, 14, 20, tzinfo=ZoneInfo("Europe/Moscow")),
        )
    )

    assert "Поток MOEX за последние 2 часа" in text
    assert "Окно: 12:20-14:20 MSK" in text
    assert "Покупка: 450.0 млн ₽" in text
    assert "Продажа: 650.0 млн ₽" in text
    assert "ROSN" in text
    assert "SBER" in text
    assert "+200.0 млн ₽" in text
    assert "-400.0 млн ₽" in text
    assert "+50.0%" in text
    assert "12:10:00" not in text
    assert ("tradestats", "ROSN", "2026-06-18", "2026-06-18") in provider.calls
    assert ("quote", "SBER") in provider.calls


def test_handle_watchlist_commands_are_russian_and_persistent(tmp_path):
    store = WatchlistStore()

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
    store = WatchlistStore()

    signal = asyncio.run(handle_command("/signal rosn", FakeProvider(), store=store, chat_id=123))
    scan = asyncio.run(handle_command("/scan rosn sber", FakeProvider(), store=store, chat_id=123))
    full = asyncio.run(handle_command("/full rosn", FakeProvider(), store=store, chat_id=123))

    assert "Сигнал ROSN" in signal
    assert "Сканер" in scan
    assert "ROSN" in scan
    assert "Полный отчет ROSN" in full
    assert "Котировка" in full


def test_handle_settings_commands_update_watchlist_pro_preferences(tmp_path):
    store = WatchlistStore()

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


def test_handle_settings_commands_validate_inputs_in_russian(tmp_path):
    store = WatchlistStore()

    quiet = asyncio.run(handle_command("/quiet 25:99 07:00", FakeProvider(), store=store, chat_id=123))
    types = asyncio.run(handle_command("/types typo", FakeProvider(), store=store, chat_id=123))

    assert "Неверный формат времени" in quiet
    assert "Неизвестный тип автосигнала" in types


def test_handle_heatmap_mega_digest_futoi_stats_and_channel_commands_are_russian(tmp_path):
    store = WatchlistStore()
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
    store = WatchlistStore()
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


def test_handle_portfolio_risk_uses_chat_score_threshold(tmp_path):
    store = WatchlistStore()
    provider = FakeProvider()
    asyncio.run(handle_command("/portfolio_add rosn", provider, store=store, chat_id=123))
    asyncio.run(handle_command("/score 100", provider, store=store, chat_id=123))

    risk = asyncio.run(
        handle_command("/portfolio_risk", provider, store=store, chat_id=123, today=dt.date(2026, 6, 18))
    )

    assert "Рисковых тикеров: 0" in risk

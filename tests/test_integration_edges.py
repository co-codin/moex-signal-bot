import asyncio

from moex_signal_bot.__main__ import _user_error_message
from moex_signal_bot.config import load_dotenv_values, require_env
from moex_signal_bot.moex_provider import MoexProvider
from moex_signal_bot.telegram_client import TelegramClient


def test_load_dotenv_values_reads_simple_key_value_file(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("TELEGRAM_BOT_TOKEN=abc\nMOEX_API_KEY='secret'\nEMPTY=\n", encoding="utf-8")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "already-set")

    loaded = load_dotenv_values(env_file)

    assert loaded["TELEGRAM_BOT_TOKEN"] == "already-set"
    assert loaded["MOEX_API_KEY"] == "secret"
    assert loaded["EMPTY"] == ""


def test_require_env_raises_russian_message_for_missing_key(monkeypatch):
    monkeypatch.delenv("MISSING_REQUIRED_KEY", raising=False)

    try:
        require_env("MISSING_REQUIRED_KEY")
    except RuntimeError as exc:
        assert "Не задана переменная окружения" in str(exc)
    else:
        raise AssertionError("require_env must fail for missing keys")


def test_moex_provider_sets_token_and_fetches_native_tradestats():
    class FakeSession:
        TOKEN = None

    class FakeTicker:
        def __init__(self, ticker):
            self.ticker = ticker

        def tradestats(self, *, start, end, native):
            assert self.ticker == "ROSN"
            assert start == "2026-06-12"
            assert end == "2026-06-18"
            assert native is True
            return [{"ticker": self.ticker, "val_b": 10, "val_s": 20}]

    provider = MoexProvider(api_key="token", ticker_factory=FakeTicker, session_module=FakeSession)

    rows = asyncio.run(provider.tradestats("rosn", "2026-06-12", "2026-06-18"))

    assert FakeSession.TOKEN == "token"
    assert rows == [{"ticker": "ROSN", "val_b": 10, "val_s": 20}]


def test_moex_provider_fetches_native_futoi_rows():
    class FakeSession:
        TOKEN = None

    class FakeTicker:
        def __init__(self, ticker):
            self.ticker = ticker

        def futoi(self, *, start, end, native):
            assert self.ticker == "SBERF"
            assert start == "2026-06-18"
            assert end == "2026-06-18"
            assert native is True
            return [{"ticker": self.ticker, "pos_long": 100, "pos_short": 80}]

    provider = MoexProvider(api_key=None, ticker_factory=FakeTicker, session_module=FakeSession)

    rows = asyncio.run(provider.futoi("sberf", "2026-06-18", "2026-06-18"))

    assert rows == [{"ticker": "SBERF", "pos_long": 100, "pos_short": 80}]


def test_moex_provider_quote_prefers_marketdata_snapshot():
    class FakeSession:
        TOKEN = None

    class FakeMarket:
        def marketdata(self, *fields, native):
            assert "last" in fields
            assert native is True
            return [
                {
                    "ticker": "SBER",
                    "last": 310,
                    "bid": 309.9,
                    "offer": 310.1,
                    "lasttoprevprice": 0.4,
                    "updatetime": "10:05:00",
                },
                {
                    "ticker": "ROSN",
                    "last": 328.5,
                    "bid": 328.4,
                    "offer": 328.6,
                    "lasttoprevprice": -2.1,
                    "updatetime": "10:06:00",
                },
            ]

    class FakeTicker:
        def __init__(self, ticker):
            self.ticker = ticker
            self.market = FakeMarket()

        def candles(self, **kwargs):
            raise AssertionError("quote must prefer marketdata over candles")

    provider = MoexProvider(api_key=None, ticker_factory=FakeTicker, session_module=FakeSession)

    quote = asyncio.run(provider.quote("rosn"))

    assert quote == {
        "ticker": "ROSN",
        "last": 328.5,
        "bid": 328.4,
        "offer": 328.6,
        "last_to_prev_pct": -2.1,
        "time": "10:06:00",
    }


def test_telegram_client_posts_send_message_payload():
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"ok": True, "result": []}

    class FakeHTTP:
        def __init__(self):
            self.posts = []

        async def post(self, url, json):
            self.posts.append((url, json))
            return FakeResponse()

    http = FakeHTTP()
    client = TelegramClient("TOKEN", http=http)

    asyncio.run(client.send_message(123, "Привет"))

    assert http.posts == [
        (
            "https://api.telegram.org/botTOKEN/sendMessage",
            {"chat_id": 123, "text": "Привет", "disable_web_page_preview": True},
        )
    ]


def test_user_error_message_hides_internal_exception_details():
    message = _user_error_message(RuntimeError("Bearer token rejected for https://example.invalid"))

    assert "Bearer token" not in message
    assert "https://example.invalid" not in message
    assert "не удалось выполнить команду" in message

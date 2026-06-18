import asyncio

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

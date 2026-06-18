import asyncio

from test_bot_commands import FakeProvider

from moex_signal_bot.__main__ import dispatch_telegram_message
from moex_signal_bot.access_control import AccessControlSettings
from moex_signal_bot.memory_storage import InMemoryWatchlistStore


def test_dispatch_blocks_pending_user_before_provider_calls():
    store = InMemoryWatchlistStore()
    provider = FakeProvider()

    reply = asyncio.run(
        dispatch_telegram_message(
            {"text": "/flow rosn", "chat": {"id": 123}, "from": {"id": 123, "username": "guest"}},
            provider,
            store,
            access_settings=AccessControlSettings(enabled=True, admin_chat_ids=()),
        )
    )

    user = store.get_telegram_user(123)

    assert user is not None
    assert user.status == "pending"
    assert "Доступ к боту не открыт" in reply
    assert "chat_id: 123" in reply
    assert provider.calls == []


def test_dispatch_allows_admin_and_preapproved_user():
    store = InMemoryWatchlistStore()
    admin_provider = FakeProvider()

    admin_reply = asyncio.run(
        dispatch_telegram_message(
            {"text": "/flow rosn", "chat": {"id": 777}, "from": {"id": 777, "username": "owner"}},
            admin_provider,
            store,
            access_settings=AccessControlSettings(enabled=True, admin_chat_ids=(777,)),
        )
    )

    store.record_telegram_user(123)
    store.set_telegram_user_status(123, "allowed")
    allowed_provider = FakeProvider()
    allowed_reply = asyncio.run(
        dispatch_telegram_message(
            {"text": "/flow rosn", "chat": {"id": 123}, "from": {"id": 123, "username": "paid"}},
            allowed_provider,
            store,
            access_settings=AccessControlSettings(enabled=True, admin_chat_ids=(777,)),
        )
    )

    assert store.get_telegram_user(777).status == "allowed"
    assert "Покупательная сила" in admin_reply
    assert "Покупательная сила" in allowed_reply
    assert admin_provider.calls
    assert allowed_provider.calls

import datetime as dt

from moex_signal_bot.access_control import (
    AccessControlSettings,
    access_denied_message,
    access_settings_from_env,
    is_chat_allowed,
    record_telegram_user_from_message,
)
from moex_signal_bot.memory_storage import InMemoryWatchlistStore


def test_access_settings_parse_env_and_default_to_open_mode():
    defaults = access_settings_from_env({})

    assert defaults.enabled is False
    assert defaults.admin_chat_ids == ()

    settings = access_settings_from_env({"ACCESS_CONTROL_ENABLED": "true", "ADMIN_CHAT_IDS": "123, 456 789"})

    assert settings.enabled is True
    assert settings.admin_chat_ids == (123, 456, 789)


def test_records_unknown_user_as_pending_and_allows_after_status_change():
    store = InMemoryWatchlistStore()
    settings = AccessControlSettings(enabled=True, admin_chat_ids=())
    now = dt.datetime(2026, 6, 18, 12, 0, tzinfo=dt.UTC)

    record_telegram_user_from_message(
        store,
        {
            "chat": {"id": 123},
            "from": {"id": 123, "username": "ivan", "first_name": "Иван", "last_name": "Петров"},
        },
        settings,
        now=now,
    )

    user = store.get_telegram_user(123)

    assert user is not None
    assert user.chat_id == 123
    assert user.username == "ivan"
    assert user.first_name == "Иван"
    assert user.last_name == "Петров"
    assert user.status == "pending"
    assert user.first_seen_at == now
    assert user.last_seen_at == now
    assert is_chat_allowed(store, 123, settings) is False

    store.set_telegram_user_status(123, "allowed")
    store.set_telegram_user_note(123, "Оплачен до 2026-07-01")

    allowed = store.get_telegram_user(123)

    assert allowed is not None
    assert allowed.status == "allowed"
    assert allowed.note == "Оплачен до 2026-07-01"
    assert is_chat_allowed(store, 123, settings) is True


def test_admin_user_is_recorded_as_allowed_and_denied_message_is_russian():
    store = InMemoryWatchlistStore()
    settings = AccessControlSettings(enabled=True, admin_chat_ids=(777,))

    record_telegram_user_from_message(store, {"chat": {"id": 777}, "from": {"id": 777}}, settings)

    user = store.get_telegram_user(777)

    assert user is not None
    assert user.status == "allowed"
    assert is_chat_allowed(store, 777, settings) is True
    assert is_chat_allowed(store, 555, AccessControlSettings(enabled=False, admin_chat_ids=())) is True
    assert "Доступ к боту не открыт" in access_denied_message(555)
    assert "chat_id: 555" in access_denied_message(555)

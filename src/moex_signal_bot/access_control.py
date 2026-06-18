from __future__ import annotations

import datetime as dt
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, Protocol

AccessStatus = Literal["allowed", "blocked", "pending"]
ACCESS_STATUSES: tuple[AccessStatus, ...] = ("allowed", "blocked", "pending")


@dataclass(frozen=True)
class TelegramUser:
    chat_id: int
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    status: AccessStatus = "pending"
    note: str = ""
    first_seen_at: dt.datetime | None = None
    last_seen_at: dt.datetime | None = None


@dataclass(frozen=True)
class AccessControlSettings:
    enabled: bool = False
    admin_chat_ids: tuple[int, ...] = ()

    def is_admin(self, chat_id: int) -> bool:
        return int(chat_id) in self.admin_chat_ids


class AccessStore(Protocol):
    def record_telegram_user(
        self,
        chat_id: int,
        *,
        username: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
        status: AccessStatus = "pending",
        now: dt.datetime | None = None,
    ) -> None: ...

    def get_telegram_user(self, chat_id: int) -> TelegramUser | None: ...


def access_settings_from_env(env: Mapping[str, str] | None = None) -> AccessControlSettings:
    values = env if env is not None else os.environ
    return AccessControlSettings(
        enabled=_env_bool(values.get("ACCESS_CONTROL_ENABLED")),
        admin_chat_ids=_parse_chat_ids(values.get("ADMIN_CHAT_IDS") or values.get("TELEGRAM_ADMIN_IDS")),
    )


def normalize_access_status(value: str) -> AccessStatus:
    normalized = value.strip().lower()
    aliases = {
        "allow": "allowed",
        "allowed": "allowed",
        "разрешен": "allowed",
        "разрешить": "allowed",
        "block": "blocked",
        "blocked": "blocked",
        "deny": "blocked",
        "denied": "blocked",
        "заблокирован": "blocked",
        "заблокировать": "blocked",
        "pending": "pending",
        "ожидает": "pending",
    }
    status = aliases.get(normalized)
    if status is None:
        raise ValueError("Неверный статус доступа. Используйте allowed, blocked или pending.")
    return status  # type: ignore[return-value]


def record_telegram_user_from_message(
    store: AccessStore,
    message: Mapping[str, object],
    settings: AccessControlSettings,
    *,
    now: dt.datetime | None = None,
) -> int | None:
    chat = _mapping_value(message.get("chat"))
    sender = _mapping_value(message.get("from")) or chat
    raw_chat_id = chat.get("id") if chat else sender.get("id")
    if raw_chat_id is None:
        return None
    chat_id = int(raw_chat_id)
    status: AccessStatus = "allowed" if settings.is_admin(chat_id) else "pending"
    store.record_telegram_user(
        chat_id,
        username=_optional_str(sender.get("username")),
        first_name=_optional_str(sender.get("first_name")),
        last_name=_optional_str(sender.get("last_name")),
        status=status,
        now=now,
    )
    return chat_id


def is_chat_allowed(store: AccessStore, chat_id: int, settings: AccessControlSettings) -> bool:
    if not settings.enabled or settings.is_admin(chat_id):
        return True
    user = store.get_telegram_user(chat_id)
    return user is not None and user.status == "allowed"


def access_denied_message(chat_id: int) -> str:
    return f"Доступ к боту не открыт.\nВаш chat_id: {chat_id}\nСвяжитесь с администратором, чтобы получить доступ."


def _env_bool(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "y", "on", "да"}


def _parse_chat_ids(value: str | None) -> tuple[int, ...]:
    if not value:
        return ()
    ids: list[int] = []
    for part in re.split(r"[\s,;]+", value.strip()):
        if not part:
            continue
        ids.append(int(part))
    return tuple(dict.fromkeys(ids))


def _mapping_value(value: object) -> Mapping[str, object]:
    if isinstance(value, Mapping):
        return value
    return {}


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None

from __future__ import annotations

from typing import Any

import httpx


class TelegramClient:
    def __init__(self, token: str, *, http: Any | None = None) -> None:
        self.base_url = f"https://api.telegram.org/bot{token}"
        self._http = http or httpx.AsyncClient(timeout=30)

    async def close(self) -> None:
        close = getattr(self._http, "aclose", None)
        if close:
            await close()

    async def get_updates(self, *, offset: int | None = None, timeout: int = 25) -> list[dict]:
        payload: dict[str, Any] = {"timeout": timeout, "allowed_updates": ["message"]}
        if offset is not None:
            payload["offset"] = offset
        response = await self._http.get(f"{self.base_url}/getUpdates", params=payload)
        response.raise_for_status()
        data = response.json()
        if not data.get("ok"):
            raise RuntimeError("Telegram вернул ошибку getUpdates.")
        return list(data.get("result") or [])

    async def send_message(self, chat_id: int, text: str) -> None:
        response = await self._http.post(
            f"{self.base_url}/sendMessage",
            json={"chat_id": chat_id, "text": text, "disable_web_page_preview": True},
        )
        response.raise_for_status()

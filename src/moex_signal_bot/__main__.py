from __future__ import annotations

import argparse
import asyncio
import contextlib
import os

from .bot import handle_command
from .config import load_dotenv_values, moex_api_key, require_env
from .moex_provider import MoexProvider
from .scanner import run_scan_once
from .storage import WatchlistStore
from .telegram_client import TelegramClient


async def run_polling() -> None:
    load_dotenv_values()
    provider = MoexProvider(api_key=moex_api_key())
    telegram = TelegramClient(require_env("TELEGRAM_BOT_TOKEN"))
    store = WatchlistStore(os.environ.get("MOEX_SIGNAL_DB", "signals.sqlite3"))
    scanner_task = asyncio.create_task(_scanner_loop(provider, store, telegram))
    offset: int | None = None
    try:
        while True:
            updates = await telegram.get_updates(offset=offset)
            for update in updates:
                offset = int(update["update_id"]) + 1
                message = update.get("message") or {}
                text = message.get("text")
                chat = message.get("chat") or {}
                chat_id = chat.get("id")
                if not text or chat_id is None:
                    continue
                try:
                    reply = await handle_command(text, provider, store=store, chat_id=int(chat_id))
                except Exception as exc:
                    print(f"Ошибка команды: {exc}", flush=True)
                    reply = _user_error_message(exc)
                await telegram.send_message(int(chat_id), reply)
    finally:
        scanner_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await scanner_task
        store.close()
        await telegram.close()


async def dry_run(command: str) -> None:
    load_dotenv_values()
    provider = MoexProvider(api_key=moex_api_key())
    store = WatchlistStore(os.environ.get("MOEX_SIGNAL_DB", ":memory:"))
    try:
        print(await handle_command(command, provider, store=store, chat_id=0))
    finally:
        store.close()


async def _scanner_loop(provider: MoexProvider, store: WatchlistStore, telegram: TelegramClient) -> None:
    interval = _scanner_interval_seconds()
    while True:
        await asyncio.sleep(interval)
        try:
            await run_scan_once(provider, store, telegram)
        except Exception as exc:
            print(f"Ошибка автосканера: {exc}", flush=True)


def _scanner_interval_seconds() -> int:
    raw = os.environ.get("SCANNER_INTERVAL_SECONDS", "60")
    try:
        return max(10, int(raw))
    except ValueError:
        return 60


def _user_error_message(exc: Exception) -> str:
    if isinstance(exc, ValueError) and str(exc):
        return str(exc)
    return "Ошибка: не удалось выполнить команду. Проверьте параметры или попробуйте позже."


def main() -> None:
    parser = argparse.ArgumentParser(description="MOEX Telegram signal bot")
    parser.add_argument("--dry-run", help='Выполнить команду без Telegram, например "/flow ROSN 7"')
    args = parser.parse_args()
    if args.dry_run:
        asyncio.run(dry_run(args.dry_run))
    else:
        asyncio.run(run_polling())


if __name__ == "__main__":
    main()

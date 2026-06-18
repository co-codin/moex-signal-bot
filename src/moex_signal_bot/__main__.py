from __future__ import annotations

import argparse
import asyncio
import os

from .access_control import (
    AccessControlSettings,
    access_denied_message,
    access_settings_from_env,
    is_chat_allowed,
    record_telegram_user_from_message,
)
from .bot import handle_command
from .commands import parse_command
from .config import load_dotenv_values, moex_api_key, require_env
from .formatters import format_help
from .memory_storage import InMemoryWatchlistStore
from .moex_provider import MoexProvider
from .scanner_queue import DEFAULT_QUEUE_KEY, RedisScannerQueue, enqueue_due_scans, scanner_worker_iteration
from .storage import WatchlistStore
from .telegram_client import TelegramClient


async def run_polling() -> None:
    load_dotenv_values()
    provider = MoexProvider(api_key=moex_api_key())
    telegram = TelegramClient(require_env("TELEGRAM_BOT_TOKEN"))
    store = create_store()
    access_settings = access_settings_from_env()
    offset: int | None = None
    try:
        while True:
            updates = await telegram.get_updates(offset=offset)
            for update in updates:
                offset = int(update["update_id"]) + 1
                message = update.get("message") or {}
                chat = message.get("chat") or {}
                chat_id = chat.get("id")
                if chat_id is None:
                    continue
                try:
                    reply = await dispatch_telegram_message(
                        message,
                        provider,
                        store,
                        access_settings=access_settings,
                    )
                except Exception as exc:
                    print(f"Ошибка команды: {exc}", flush=True)
                    reply = _user_error_message(exc)
                if reply is None:
                    continue
                await telegram.send_message(int(chat_id), reply)
    finally:
        store.close()
        await telegram.close()


async def dry_run(command: str) -> None:
    load_dotenv_values()
    if parse_command(command).name == "help":
        print(format_help())
        return
    provider = MoexProvider(api_key=moex_api_key())
    store = create_store(for_dry_run=True)
    try:
        print(await handle_command(command, provider, store=store, chat_id=0))
    finally:
        store.close()


async def run_scanner_scheduler() -> None:
    load_dotenv_values()
    store = create_store()
    queue = create_scanner_queue()
    interval = _scanner_interval_seconds()
    try:
        while True:
            try:
                enqueued = await enqueue_due_scans(store, queue)
                if enqueued:
                    print(f"Автосканер: поставлено задач в очередь: {enqueued}", flush=True)
            except Exception as exc:
                print(f"Ошибка scheduler автосканера: {exc}", flush=True)
            await asyncio.sleep(interval)
    finally:
        store.close()
        await queue.close()


async def run_scanner_worker() -> None:
    load_dotenv_values()
    provider = MoexProvider(api_key=moex_api_key())
    telegram = TelegramClient(require_env("TELEGRAM_BOT_TOKEN"))
    store = create_store()
    queue = create_scanner_queue()
    access_settings = access_settings_from_env()
    try:
        while True:
            sent = await scanner_worker_iteration(
                provider,
                store,
                telegram,
                queue,
                access_settings=access_settings,
                pop_timeout_seconds=_scanner_worker_pop_timeout_seconds(),
                max_attempts=_scanner_max_attempts(),
                retry_delay_seconds=_scanner_retry_delay_seconds(),
            )
            if sent:
                print(f"Автосканер worker: отправлено сигналов: {sent}", flush=True)
    finally:
        store.close()
        await queue.close()
        await telegram.close()


def run_admin_web() -> None:
    load_dotenv_values()
    import uvicorn

    from .admin_web import create_admin_app

    store = create_store()
    try:
        app = create_admin_app(
            store,
            username=require_env("ADMIN_WEB_USERNAME"),
            password=require_env("ADMIN_WEB_PASSWORD"),
        )
        uvicorn.run(
            app,
            host=os.environ.get("ADMIN_WEB_HOST", "0.0.0.0"),
            port=_env_int("ADMIN_WEB_PORT", default=8080, minimum=1),
        )
    finally:
        store.close()


async def dispatch_telegram_message(
    message: dict,
    provider: MoexProvider,
    store,
    *,
    access_settings: AccessControlSettings | None = None,
) -> str | None:
    text = message.get("text")
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    if not text or chat_id is None:
        return None

    settings = access_settings or AccessControlSettings()
    chat_id = record_telegram_user_from_message(store, message, settings) or int(chat_id)
    if not is_chat_allowed(store, chat_id, settings):
        return access_denied_message(chat_id)
    return await handle_command(str(text), provider, store=store, chat_id=int(chat_id))


def _scanner_interval_seconds() -> int:
    raw = os.environ.get("SCANNER_INTERVAL_SECONDS", "60")
    try:
        return max(10, int(raw))
    except ValueError:
        return 60


def create_store(*, for_dry_run: bool = False):
    database_url = os.environ.get("DATABASE_URL")
    if database_url:
        return WatchlistStore(database_url)
    if for_dry_run:
        return InMemoryWatchlistStore()
    raise RuntimeError("Не задана переменная окружения DATABASE_URL для PostgreSQL.")


def create_scanner_queue() -> RedisScannerQueue:
    redis_url = os.environ.get("REDIS_URL")
    if not redis_url:
        raise RuntimeError("Не задана переменная окружения REDIS_URL для очереди автосканера.")
    return RedisScannerQueue(redis_url, queue_key=os.environ.get("SCANNER_QUEUE_KEY", DEFAULT_QUEUE_KEY))


def _scanner_worker_pop_timeout_seconds() -> int:
    return _env_int("SCANNER_WORKER_POP_TIMEOUT_SECONDS", default=5, minimum=1)


def _scanner_max_attempts() -> int:
    return _env_int("SCANNER_MAX_ATTEMPTS", default=3, minimum=0)


def _scanner_retry_delay_seconds() -> float:
    return _env_float("SCANNER_RETRY_DELAY_SECONDS", default=5.0, minimum=0.0)


def _env_int(name: str, *, default: int, minimum: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return max(minimum, int(raw))
    except ValueError:
        return default


def _env_float(name: str, *, default: float, minimum: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return max(minimum, float(raw))
    except ValueError:
        return default


def _user_error_message(exc: Exception) -> str:
    if isinstance(exc, ValueError) and str(exc):
        return str(exc)
    return "Ошибка: не удалось выполнить команду. Проверьте параметры или попробуйте позже."


def main() -> None:
    parser = argparse.ArgumentParser(description="MOEX Telegram signal bot")
    parser.add_argument("--dry-run", help='Выполнить команду без Telegram, например "/flow ROSN 7"')
    parser.add_argument("--scanner-scheduler", action="store_true", help="Запустить постановщик задач автосканера")
    parser.add_argument("--scanner-worker", action="store_true", help="Запустить worker автосканера")
    parser.add_argument("--admin-web", action="store_true", help="Запустить веб-панель управления доступом")
    args = parser.parse_args()
    if args.dry_run:
        asyncio.run(dry_run(args.dry_run))
    elif args.scanner_scheduler:
        asyncio.run(run_scanner_scheduler())
    elif args.scanner_worker:
        asyncio.run(run_scanner_worker())
    elif args.admin_web:
        run_admin_web()
    else:
        asyncio.run(run_polling())


if __name__ == "__main__":
    main()

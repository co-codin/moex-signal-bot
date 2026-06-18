from __future__ import annotations

import argparse
import asyncio

from .bot import handle_command
from .config import load_dotenv_values, moex_api_key, require_env
from .moex_provider import MoexProvider
from .telegram_client import TelegramClient


async def run_polling() -> None:
    load_dotenv_values()
    provider = MoexProvider(api_key=moex_api_key())
    telegram = TelegramClient(require_env("TELEGRAM_BOT_TOKEN"))
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
                    reply = await handle_command(text, provider)
                except Exception as exc:
                    reply = f"Ошибка: {exc}"
                await telegram.send_message(int(chat_id), reply)
    finally:
        await telegram.close()


async def dry_run(command: str) -> None:
    load_dotenv_values()
    provider = MoexProvider(api_key=moex_api_key())
    print(await handle_command(command, provider))


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

import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv
from telethon import TelegramClient


load_dotenv()


def get_required_env(name: str) -> str:
    value = os.getenv(name)

    if not value:
        raise RuntimeError(
            f"Не задана обязательная переменная окружения: {name}"
        )

    return value


async def main() -> None:
    api_id = int(get_required_env("TELEGRAM_API_ID"))
    api_hash = get_required_env("TELEGRAM_API_HASH")
    session_path = Path(
        get_required_env("TELEGRAM_SESSION_PATH")
    )

    client = TelegramClient(
        session=str(session_path),
        api_id=api_id,
        api_hash=api_hash,
    )

    try:
        await client.connect()

        if not await client.is_user_authorized():
            raise RuntimeError(
                "Telegram-сессия не авторизована. "
                "Сначала запусти: uv run python -m app.auth"
            )

        print()
        print("Доступные диалоги:")
        print("-" * 90)

        async for dialog in client.iter_dialogs():
            if dialog.is_group:
                dialog_type = "GROUP"
            elif dialog.is_channel:
                dialog_type = "CHANNEL"
            elif dialog.is_user:
                dialog_type = "PRIVATE"
            else:
                dialog_type = "OTHER"

            print(
                f"{dialog_type:<8} | "
                f"{dialog.id:<20} | "
                f"{dialog.name}"
            )

    finally:
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
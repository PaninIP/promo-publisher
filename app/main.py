import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv
from telethon import TelegramClient

from app.folder_targets import load_publication_targets


load_dotenv()


def get_required_env(name: str) -> str:
    value = os.getenv(name)

    if not value:
        raise RuntimeError(
            f"Не задана обязательная переменная окружения: {name}"
        )

    return value.strip()


async def main() -> None:
    api_id_raw = get_required_env("TELEGRAM_API_ID")
    api_hash = get_required_env("TELEGRAM_API_HASH")
    session_path = Path(
        get_required_env("TELEGRAM_SESSION_PATH")
    )
    folder_name = get_required_env(
        "TELEGRAM_FOLDER_NAME"
    )

    try:
        api_id = int(api_id_raw)
    except ValueError as error:
        raise RuntimeError(
            "TELEGRAM_API_ID должен быть целым числом"
        ) from error

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
                "Запусти: uv run python -m app.auth"
            )

        targets = await load_publication_targets(
            client=client,
            folder_name=folder_name,
        )

        print()
        print(f'Папка Telegram: "{folder_name}"')
        print("-" * 90)

        for number, target in enumerate(
            targets,
            start=1,
        ):
            print(
                f"{number:<3} | "
                f"{target.kind:<12} | "
                f"{target.peer_id:<20} | "
                f"{target.name}"
            )

        print("-" * 90)
        print(f"Получателей найдено: {len(targets)}")

    finally:
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
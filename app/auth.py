import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv
from telethon import TelegramClient


load_dotenv()


def get_required_env(name: str) -> str:
    """Возвращает обязательную переменную окружения."""

    value = os.getenv(name)

    if not value:
        raise RuntimeError(
            f"Не задана обязательная переменная окружения: {name}"
        )

    return value


async def main() -> None:
    api_id_raw = get_required_env("TELEGRAM_API_ID")
    api_hash = get_required_env("TELEGRAM_API_HASH")
    phone = get_required_env("TELEGRAM_PHONE")
    session_path = get_required_env("TELEGRAM_SESSION_PATH")

    try:
        api_id = int(api_id_raw)
    except ValueError as error:
        raise RuntimeError(
            "TELEGRAM_API_ID должен быть целым числом"
        ) from error

    session_file = Path(session_path)
    session_file.parent.mkdir(parents=True, exist_ok=True)

    client = TelegramClient(
        session=str(session_file),
        api_id=api_id,
        api_hash=api_hash,
    )

    try:
        await client.start(phone=phone)

        current_user = await client.get_me()

        display_name = " ".join(
            part
            for part in [
                current_user.first_name,
                current_user.last_name,
            ]
            if part
        )

        print(
            "Авторизация выполнена:",
            display_name or current_user.username or current_user.id,
        )

        await client.send_message(
            entity="me",
            message=(
                "✅ Promo Publisher успешно подключён.\n\n"
                "Это тестовое сообщение отправлено скриптом."
            ),
        )

        print("Тестовое сообщение отправлено в «Избранное».")

    finally:
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
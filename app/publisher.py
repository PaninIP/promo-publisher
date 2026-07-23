import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.tl.types import Channel, Chat, User


load_dotenv()


def get_required_env(name: str) -> str:
    value = os.getenv(name)

    if not value:
        raise RuntimeError(
            f"Не задана обязательная переменная окружения: {name}"
        )

    return value


def get_entity_type(entity: object) -> str:
    if isinstance(entity, User):
        return "Личный пользователь"

    if isinstance(entity, Chat):
        return "Обычная группа"

    if isinstance(entity, Channel):
        if entity.broadcast:
            return "Канал"

        if entity.megagroup:
            return "Супергруппа"

        return "Telegram-канал или группа"

    return type(entity).__name__


def get_entity_name(entity: object) -> str:
    if isinstance(entity, User):
        full_name = " ".join(
            part
            for part in [
                entity.first_name,
                entity.last_name,
            ]
            if part
        )

        return full_name or entity.username or str(entity.id)

    return (
        getattr(entity, "title", None)
        or getattr(entity, "username", None)
        or str(getattr(entity, "id", "неизвестно"))
    )


async def main() -> None:
    api_id = int(get_required_env("TELEGRAM_API_ID"))
    api_hash = get_required_env("TELEGRAM_API_HASH")
    session_path = Path(
        get_required_env("TELEGRAM_SESSION_PATH")
    )

    target_chat_id = int(
        get_required_env("TARGET_CHAT_ID")
    )

    promo_message = get_required_env("PROMO_MESSAGE")

    client = TelegramClient(
        session=str(session_path),
        api_id=api_id,
        api_hash=api_hash,
    )

    try:
        await client.connect()

        if not await client.is_user_authorized():
            raise RuntimeError(
                "Telegram-сессия не авторизована"
            )

        entity = await client.get_entity(target_chat_id)

        entity_type = get_entity_type(entity)
        entity_name = get_entity_name(entity)

        print()
        print(f"Получатель: {entity_name}")
        print(f"Тип: {entity_type}")
        print(f"ID: {target_chat_id}")
        print()
        print("Сообщение:")
        print(promo_message)
        print()

        confirmation = input(
            'Для отправки введи слово "ОТПРАВИТЬ": '
        ).strip()

        if confirmation != "ОТПРАВИТЬ":
            print("Отправка отменена.")
            return

        sent_message = await client.send_message(
            entity=entity,
            message=promo_message,
            link_preview=False,
        )

        print(
            f"Сообщение отправлено. "
            f"ID сообщения: {sent_message.id}"
        )

    finally:
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
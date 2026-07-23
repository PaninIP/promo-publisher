import argparse
import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv
from telethon import TelegramClient

from app.folder_targets import load_publication_targets
from app.messages import load_messages
from app.publisher import (
    build_publication_plan,
    filter_allowed_targets,
    normalize_bot_username,
    print_publication_plan,
    publish_plan,
)


load_dotenv()


def get_required_env(name: str) -> str:
    value = os.getenv(name)

    if not value:
        raise RuntimeError(
            f"Не задана обязательная переменная окружения: {name}"
        )

    return value.strip()


def get_integer_env(
    name: str,
    default: int,
) -> int:
    raw_value = os.getenv(name)

    if raw_value is None or not raw_value.strip():
        return default

    try:
        return int(raw_value)
    except ValueError as error:
        raise RuntimeError(
            f"{name} должен быть целым числом"
        ) from error


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Публикация сообщений в разрешённые "
            "Telegram-чаты из выбранной папки"
        )
    )

    parser.add_argument(
        "--send",
        action="store_true",
        help=(
            "Выполнить реальную отправку. "
            "Без этого флага работает только предпросмотр."
        ),
    )

    parser.add_argument(
        "--target-id",
        type=int,
        action="append",
        default=[],
        help=(
            "ID конкретного получателя. "
            "Параметр можно указывать несколько раз."
        ),
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Ограничить количество получателей.",
    )

    return parser.parse_args()


def select_targets(
    targets,
    selected_target_ids: list[int],
    limit: int | None,
):
    selected = list(targets)

    if selected_target_ids:
        required_ids = set(selected_target_ids)

        selected = [
            target
            for target in selected
            if target.peer_id in required_ids
        ]

        found_ids = {
            target.peer_id
            for target in selected
        }

        missing_ids = required_ids - found_ids

        if missing_ids:
            missing_text = ", ".join(
                str(target_id)
                for target_id in sorted(missing_ids)
            )

            raise RuntimeError(
                "В папке Telegram не найдены получатели: "
                f"{missing_text}"
            )

    if limit is not None:
        if limit <= 0:
            raise RuntimeError(
                "--limit должен быть больше нуля"
            )

        selected = selected[:limit]

    return selected


async def run() -> None:
    arguments = parse_arguments()

    api_id_raw = get_required_env(
        "TELEGRAM_API_ID"
    )
    api_hash = get_required_env(
        "TELEGRAM_API_HASH"
    )
    session_path = Path(
        get_required_env(
            "TELEGRAM_SESSION_PATH"
        )
    )
    folder_name = get_required_env(
        "TELEGRAM_FOLDER_NAME"
    )
    bot_username = normalize_bot_username(
        get_required_env(
            "PROMO_BOT_USERNAME"
        )
    )

    delay_min_seconds = get_integer_env(
        "PUBLICATION_DELAY_MIN_SECONDS",
        default=15,
    )
    delay_max_seconds = get_integer_env(
        "PUBLICATION_DELAY_MAX_SECONDS",
        default=30,
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

        # Все ограничения Telegram обрабатываем сами,
        # без скрытого автоматического ожидания.
        flood_sleep_threshold=0,
    )

    try:
        await client.connect()

        if not await client.is_user_authorized():
            raise RuntimeError(
                "Telegram-сессия не авторизована. "
                "Запусти: uv run python -m app.auth"
            )

        folder_targets = await load_publication_targets(
            client=client,
            folder_name=folder_name,
        )

        allowed_targets, skipped_targets = (
            filter_allowed_targets(
                folder_targets
            )
        )

        if skipped_targets:
            print()
            print(
                "Получатели, исключённые из публикации:"
            )

            for target in skipped_targets:
                print(
                    f"- {target.name}: "
                    f"{target.kind}, "
                    f"{target.peer_id}"
                )

        selected_targets = select_targets(
            targets=allowed_targets,
            selected_target_ids=arguments.target_id,
            limit=arguments.limit,
        )

        if not selected_targets:
            raise RuntimeError(
                "После фильтрации не осталось "
                "получателей для публикации"
            )

        messages = load_messages()

        plan = build_publication_plan(
            targets=selected_targets,
            messages=messages,
            bot_username=bot_username,
        )

        print_publication_plan(plan)

        if not arguments.send:
            print()
            print(
                "Режим предпросмотра: "
                "сообщения не отправлены."
            )
            print(
                "Для реальной отправки добавь --send."
            )
            return

        expected_confirmation = (
            f"ОТПРАВИТЬ {len(plan)}"
        )

        print()
        confirmation = input(
            "Для подтверждения введи "
            f'"{expected_confirmation}": '
        ).strip()

        if confirmation != expected_confirmation:
            print("Публикация отменена.")
            return

        summary = await publish_plan(
            client=client,
            plan=plan,
            delay_min_seconds=delay_min_seconds,
            delay_max_seconds=delay_max_seconds,
        )

        print()
        print("=" * 60)
        print("Цикл публикации завершён")
        print(f"Успешно: {summary.successful}")
        print(f"Ошибок: {summary.failed}")

        if summary.aborted_reason:
            print(
                f"Причина остановки: "
                f"{summary.aborted_reason}"
            )

    finally:
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(run())
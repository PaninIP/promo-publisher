import argparse
import asyncio
import os
import random
from pathlib import Path

from dotenv import load_dotenv
from telethon import TelegramClient

from app.folder_targets import PublicationTarget, load_publication_targets
from app.messages import load_messages
from app.publisher import (
    build_publication_plan,
    filter_allowed_targets,
    print_publication_plan,
    publish_plan,
)
from app.settings import (
    RemoteConfigError,
    format_settings,
    get_integer_env,
    get_required_env,
    load_runtime_settings,
)


load_dotenv()


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Публикация сообщений в разрешённые Telegram-чаты "
            "из выбранной папки"
        )
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--send",
        action="store_true",
        help="Выполнить один реальный цикл публикации.",
    )
    mode.add_argument(
        "--daemon",
        action="store_true",
        help=(
            "Запустить постоянные циклы публикации. "
            "PUBLICATION_ENABLED=false приостанавливает отправку."
        ),
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Не запрашивать подтверждение для режима --send.",
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
    targets: list[PublicationTarget],
    selected_target_ids: list[int],
    limit: int | None,
) -> list[PublicationTarget]:
    selected = list(targets)

    if selected_target_ids:
        required_ids = set(selected_target_ids)
        selected = [
            target
            for target in selected
            if target.peer_id in required_ids
        ]
        found_ids = {target.peer_id for target in selected}
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
            raise RuntimeError("--limit должен быть больше нуля")
        selected = selected[:limit]

    return selected


async def load_targets(
    *,
    client: TelegramClient,
    folder_name: str,
    target_ids: list[int],
    limit: int | None,
) -> list[PublicationTarget]:
    folder_targets = await load_publication_targets(
        client=client,
        folder_name=folder_name,
    )
    allowed_targets, skipped_targets = filter_allowed_targets(
        folder_targets
    )

    if skipped_targets:
        print()
        print("Получатели, исключённые из публикации:")
        for target in skipped_targets:
            print(
                f"- {target.name}: {target.kind}, {target.peer_id}"
            )

    selected_targets = select_targets(
        targets=allowed_targets,
        selected_target_ids=target_ids,
        limit=limit,
    )

    if not selected_targets:
        raise RuntimeError(
            "После фильтрации не осталось получателей для публикации"
        )

    return selected_targets


async def run_single_cycle(
    *,
    client: TelegramClient,
    arguments: argparse.Namespace,
    require_confirmation: bool,
    show_plan: bool,
) -> None:
    loaded = await load_runtime_settings(client=client)
    settings = loaded.settings
    print()
    print(format_settings(loaded))

    if (arguments.send or arguments.daemon) and not settings.publication_enabled:
        print()
        print(
            "Публикация не запущена: "
            "PUBLICATION_ENABLED=false."
        )
        return

    targets = await load_targets(
        client=client,
        folder_name=settings.telegram_folder_name,
        target_ids=arguments.target_id,
        limit=arguments.limit,
    )
    messages = load_messages()
    plan = build_publication_plan(
        targets=targets,
        messages=messages,
        bot_username=settings.promo_bot_username,
    )

    if show_plan:
        print_publication_plan(plan)

    if not arguments.send and not arguments.daemon:
        print()
        print("Режим предпросмотра: сообщения не отправлены.")
        print("Для одного цикла добавь --send.")
        print("Для постоянной работы на VPS добавь --daemon.")
        return

    if require_confirmation and not arguments.yes:
        expected_confirmation = f"ОТПРАВИТЬ {len(plan)}"
        print()
        confirmation = input(
            f'Для подтверждения введи "{expected_confirmation}": '
        ).strip()

        if confirmation != expected_confirmation:
            print("Публикация отменена.")
            return

    async def settings_loader():
        return await load_runtime_settings(
            client=client,
            fail_closed=True,
        )

    summary = await publish_plan(
        client=client,
        plan=plan,
        settings_loader=settings_loader,
        config_check_seconds=get_integer_env(
            "REMOTE_CONFIG_POLL_SECONDS",
            default=5,
        ),
    )

    print()
    print("=" * 60)
    print("Цикл публикации завершён")
    print(f"Успешно: {summary.successful}")
    print(f"Ошибок: {summary.failed}")

    if summary.aborted_reason:
        print(f"Причина остановки: {summary.aborted_reason}")


async def wait_between_cycles(client: TelegramClient) -> bool:
    """Возвращает True, когда можно запускать следующий цикл."""

    poll_seconds = get_integer_env(
        "REMOTE_CONFIG_POLL_SECONDS",
        default=15,
    )

    if poll_seconds < 1:
        raise RuntimeError(
            "REMOTE_CONFIG_POLL_SECONDS должен быть больше нуля"
        )

    loaded = await load_runtime_settings(
        client=client,
        fail_closed=True,
    )
    settings = loaded.settings

    if not settings.publication_enabled:
        return False

    interval_minutes = random.randint(
        settings.publication_interval_min_minutes,
        settings.publication_interval_max_minutes,
    )
    remaining_seconds = interval_minutes * 60
    active_range = (
        settings.publication_interval_min_minutes,
        settings.publication_interval_max_minutes,
    )

    print()
    print(
        "Следующий цикл запланирован примерно через "
        f"{interval_minutes} мин."
    )

    while remaining_seconds > 0:
        await asyncio.sleep(min(poll_seconds, remaining_seconds))
        remaining_seconds -= min(poll_seconds, remaining_seconds)

        loaded = await load_runtime_settings(
            client=client,
            fail_closed=True,
        )
        settings = loaded.settings

        if not settings.publication_enabled:
            print(
                "Публикации приостановлены: "
                "PUBLICATION_ENABLED=false."
            )
            return False

        current_range = (
            settings.publication_interval_min_minutes,
            settings.publication_interval_max_minutes,
        )

        if current_range != active_range:
            interval_minutes = random.randint(*current_range)
            remaining_seconds = interval_minutes * 60
            active_range = current_range
            print(
                "Интервал изменён через Избранное. "
                "Новый отсчёт: "
                f"{interval_minutes} мин."
            )

    return True


async def run_daemon(
    *,
    client: TelegramClient,
    arguments: argparse.Namespace,
) -> None:
    poll_seconds = get_integer_env(
        "REMOTE_CONFIG_POLL_SECONDS",
        default=15,
    )
    paused_message_shown = False

    print("Постоянный режим запущен. Для остановки нажми Ctrl+C.")

    while True:
        try:
            loaded = await load_runtime_settings(
                client=client,
                fail_closed=True,
            )
        except RemoteConfigError as error:
            print(
                "[ПАУЗА] Конфигурация недоступна или некорректна. "
                f"Отправка заблокирована: {error}"
            )
            await asyncio.sleep(poll_seconds)
            continue

        if not loaded.settings.publication_enabled:
            if not paused_message_shown:
                print(
                    "[ПАУЗА] PUBLICATION_ENABLED=false. "
                    "Ни одно сообщение не будет отправлено."
                )
                paused_message_shown = True
            await asyncio.sleep(poll_seconds)
            continue

        paused_message_shown = False

        try:
            await run_single_cycle(
                client=client,
                arguments=arguments,
                require_confirmation=False,
                show_plan=False,
            )
            await wait_between_cycles(client)
        except RemoteConfigError as error:
            print(
                "[ПАУЗА] Удалённая конфигурация недоступна. "
                f"Отправка заблокирована: {error}"
            )
            await asyncio.sleep(poll_seconds)
        except Exception as error:
            print(
                f"[ОШИБКА ЦИКЛА] {type(error).__name__}: {error}"
            )
            await asyncio.sleep(poll_seconds)


async def run() -> None:
    arguments = parse_arguments()
    api_id_raw = get_required_env("TELEGRAM_API_ID")
    api_hash = get_required_env("TELEGRAM_API_HASH")
    session_path = Path(get_required_env("TELEGRAM_SESSION_PATH"))

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
        flood_sleep_threshold=0,
    )

    try:
        await client.connect()

        if not await client.is_user_authorized():
            raise RuntimeError(
                "Telegram-сессия не авторизована. "
                "Запусти: uv run python -m app.auth"
            )

        if arguments.daemon:
            await run_daemon(client=client, arguments=arguments)
        else:
            await run_single_cycle(
                client=client,
                arguments=arguments,
                require_confirmation=arguments.send,
                show_plan=True,
            )
    finally:
        await client.disconnect()


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        print("\nРабота остановлена пользователем.")

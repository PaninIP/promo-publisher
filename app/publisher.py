from __future__ import annotations

import asyncio
import json
import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from telethon import TelegramClient, errors

from app.folder_targets import PublicationTarget
from app.message_gate import (
    check_message_gate,
    save_last_sent_message_id,
)
from app.messages import (
    PromoMessage,
    choose_message,
    save_sent_message,
)
from app.settings import LoadedSettings, RemoteConfigError


HISTORY_PATH = Path("data/publication_history.jsonl")
ALLOWED_TARGET_KINDS = frozenset({"group", "supergroup"})
SettingsLoader = Callable[[], Awaitable[LoadedSettings]]


@dataclass(frozen=True)
class PlannedPublication:
    target: PublicationTarget
    message: PromoMessage
    rendered_text: str


@dataclass
class PublicationSummary:
    successful: int = 0
    failed: int = 0
    aborted_reason: str | None = None
    disabled_by_config: bool = False
    skipped_by_message_gate: int = 0


def filter_allowed_targets(
    targets: list[PublicationTarget],
) -> tuple[list[PublicationTarget], list[PublicationTarget]]:
    allowed: list[PublicationTarget] = []
    skipped: list[PublicationTarget] = []

    for target in targets:
        if target.kind in ALLOWED_TARGET_KINDS:
            allowed.append(target)
        else:
            skipped.append(target)

    return allowed, skipped


def build_publication_plan(
    targets: list[PublicationTarget],
    messages: list[PromoMessage],
    bot_username: str,
) -> list[PlannedPublication]:
    if not targets:
        return []

    if not messages:
        raise RuntimeError("Список рекламных сообщений пуст")

    plan: list[PlannedPublication] = []

    for target in targets:
        selected_message = choose_message(
            messages=messages,
            target=target.peer_id,
        )
        plan.append(
            PlannedPublication(
                target=target,
                message=selected_message,
                rendered_text=selected_message.render(
                    bot_username=bot_username,
                ),
            )
        )

    return plan


def print_publication_plan(plan: list[PlannedPublication]) -> None:
    print()
    print("План публикации")
    print("=" * 90)

    for number, publication in enumerate(plan, start=1):
        print()
        print(f"{number}. {publication.target.name}")
        print(f"Тип: {publication.target.kind}")
        print(f"ID: {publication.target.peer_id}")
        print(f"Шаблон: {publication.message.id}")
        print("-" * 90)
        print(publication.rendered_text)
        print("=" * 90)

    print()
    print(f"Публикаций в плане: {len(plan)}")


def append_history(
    *,
    publication: PlannedPublication,
    status: str,
    telegram_message_id: int | None = None,
    error: str | None = None,
) -> None:
    record = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "target_id": publication.target.peer_id,
        "target_name": publication.target.name,
        "target_kind": publication.target.kind,
        "template_id": publication.message.id,
        "status": status,
        "telegram_message_id": telegram_message_id,
        "error": error,
    }

    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)

    try:
        with HISTORY_PATH.open(mode="a", encoding="utf-8") as history_file:
            history_file.write(json.dumps(record, ensure_ascii=False))
            history_file.write("\n")
    except OSError as history_error:
        print(
            "[ПРЕДУПРЕЖДЕНИЕ] Не удалось записать журнал: "
            f"{history_error}"
        )


async def load_active_settings(
    settings_loader: SettingsLoader,
) -> LoadedSettings:
    try:
        loaded = await settings_loader()
    except RemoteConfigError:
        raise
    except Exception as error:
        raise RemoteConfigError(
            "Не удалось обновить рабочую конфигурацию"
        ) from error

    return loaded


async def interruptible_delay(
    *,
    total_seconds: int,
    settings_loader: SettingsLoader,
    check_every_seconds: int,
) -> bool:
    """Ждёт паузу и возвращает False, если публикации отключены."""

    remaining = total_seconds

    while remaining > 0:
        loaded = await load_active_settings(settings_loader)

        if not loaded.settings.publication_enabled:
            return False

        sleep_seconds = min(check_every_seconds, remaining)
        await asyncio.sleep(sleep_seconds)
        remaining -= sleep_seconds

    return True


async def publish_plan(
    *,
    client: TelegramClient,
    plan: list[PlannedPublication],
    settings_loader: SettingsLoader,
    config_check_seconds: int = 5,
) -> PublicationSummary:
    if config_check_seconds < 1:
        raise ValueError("config_check_seconds должен быть больше нуля")

    summary = PublicationSummary()
    attempted_publications = 0

    for publication in plan:
        try:
            loaded = await load_active_settings(settings_loader)
        except RemoteConfigError as error:
            summary.aborted_reason = (
                "Конфигурация недоступна или некорректна: "
                f"{error}"
            )
            print(f"[ОСТАНОВКА] {summary.aborted_reason}")
            break

        settings = loaded.settings

        if not settings.publication_enabled:
            summary.disabled_by_config = True
            summary.aborted_reason = (
                "Публикации отключены параметром "
                "PUBLICATION_ENABLED=false"
            )
            append_history(
                publication=publication,
                status="disabled_by_config",
                error=summary.aborted_reason,
            )
            print(f"[ОСТАНОВКА] {summary.aborted_reason}")
            break

        if settings.publication_message_gate_enabled:
            try:
                gate_status = await check_message_gate(
                    client=client,
                    entity=publication.target.peer,
                    target_id=publication.target.peer_id,
                    required_message_count=(
                        settings.publication_min_new_messages
                    ),
                )
            except (errors.RPCError, ValueError, RuntimeError) as error:
                summary.failed += 1
                error_text = (
                    "Не удалось проверить количество новых сообщений: "
                    f"{type(error).__name__}: {error}"
                )
                append_history(
                    publication=publication,
                    status="message_gate_error",
                    error=error_text,
                )
                print(
                    f"[ПРОПУЩЕНО] {publication.target.name}: "
                    f"{error_text}"
                )
                continue

            if not gate_status.allowed:
                summary.skipped_by_message_gate += 1
                wait_text = (
                    "после прошлой публикации появилось "
                    f"{gate_status.new_message_count} из "
                    f"{gate_status.required_message_count} "
                    "необходимых сообщений"
                )
                append_history(
                    publication=publication,
                    status="waiting_for_new_messages",
                    error=wait_text,
                )
                print(
                    f"[ОЖИДАНИЕ] {publication.target.name}: "
                    f"{wait_text}."
                )
                continue

        if attempted_publications > 0:
            delay = random.randint(
                settings.publication_delay_min_seconds,
                settings.publication_delay_max_seconds,
            )
            print()
            print(f"Пауза перед следующей публикацией: {delay} сек.")

            try:
                delay_completed = await interruptible_delay(
                    total_seconds=delay,
                    settings_loader=settings_loader,
                    check_every_seconds=config_check_seconds,
                )
            except RemoteConfigError as error:
                summary.aborted_reason = (
                    "Конфигурация недоступна во время ожидания: "
                    f"{error}"
                )
                print(f"[ОСТАНОВКА] {summary.aborted_reason}")
                break

            if not delay_completed:
                summary.disabled_by_config = True
                summary.aborted_reason = (
                    "Публикации отключены параметром "
                    "PUBLICATION_ENABLED=false"
                )
                print(f"[ОСТАНОВКА] {summary.aborted_reason}")
                break

            try:
                loaded = await load_active_settings(settings_loader)
            except RemoteConfigError as error:
                summary.aborted_reason = (
                    "Конфигурация недоступна перед отправкой: "
                    f"{error}"
                )
                print(f"[ОСТАНОВКА] {summary.aborted_reason}")
                break

            if not loaded.settings.publication_enabled:
                summary.disabled_by_config = True
                summary.aborted_reason = (
                    "Публикации отключены параметром "
                    "PUBLICATION_ENABLED=false"
                )
                print(f"[ОСТАНОВКА] {summary.aborted_reason}")
                break

        attempted_publications += 1

        print()
        print(
            f"[ОТПРАВКА] {publication.target.name} "
            f"({publication.target.peer_id})"
        )

        try:
            sent_message = await client.send_message(
                entity=publication.target.peer,
                message=publication.rendered_text,
                link_preview=False,
            )
        except errors.SlowModeWaitError as error:
            summary.failed += 1
            error_text = (
                "В чате действует медленный режим. "
                f"Повторная отправка возможна через {error.seconds} сек."
            )
            append_history(
                publication=publication,
                status="slow_mode_wait",
                error=error_text,
            )
            print(
                f"[ПРОПУЩЕНО] {publication.target.name}: {error_text}"
            )
            continue
        except errors.FloodWaitError as error:
            summary.failed += 1
            error_text = (
                "Telegram потребовал остановить запросы "
                f"на {error.seconds} сек."
            )
            summary.aborted_reason = error_text
            append_history(
                publication=publication,
                status="flood_wait",
                error=error_text,
            )
            print(f"[ОСТАНОВКА] {error_text}")
            break
        except errors.RPCError as error:
            summary.failed += 1
            error_text = f"{type(error).__name__}: {error}"
            append_history(
                publication=publication,
                status="telegram_error",
                error=error_text,
            )
            print(
                f"[ОШИБКА TELEGRAM] {publication.target.name}: "
                f"{error_text}"
            )
            continue
        except (ValueError, ConnectionError, TimeoutError) as error:
            summary.failed += 1
            error_text = f"{type(error).__name__}: {error}"
            append_history(
                publication=publication,
                status="client_error",
                error=error_text,
            )
            print(f"[ОШИБКА] {publication.target.name}: {error_text}")
            continue

        summary.successful += 1

        try:
            save_sent_message(
                target=publication.target.peer_id,
                message_id=publication.message.id,
            )
        except OSError as state_error:
            print(
                "[ПРЕДУПРЕЖДЕНИЕ] Сообщение отправлено, но состояние "
                f"шаблонов не сохранено: {state_error}"
            )

        try:
            save_last_sent_message_id(
                target_id=publication.target.peer_id,
                telegram_message_id=sent_message.id,
            )
        except (OSError, RuntimeError, ValueError) as state_error:
            print(
                "[ПРЕДУПРЕЖДЕНИЕ] Сообщение отправлено, но состояние "
                f"порога новых сообщений не сохранено: {state_error}"
            )

        append_history(
            publication=publication,
            status="sent",
            telegram_message_id=sent_message.id,
        )
        print(
            f"[ГОТОВО] {publication.target.name}: "
            f"шаблон {publication.message.id}, "
            f"Telegram message ID {sent_message.id}"
        )

    return summary

from __future__ import annotations

import asyncio
import json
import random
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from telethon import TelegramClient, errors

from app.folder_targets import PublicationTarget
from app.messages import (
    PromoMessage,
    choose_message,
    save_sent_message,
)


HISTORY_PATH = Path("data/publication_history.jsonl")

# Публикации в личные сообщения и каналы пока запрещены.
ALLOWED_TARGET_KINDS = frozenset(
    {
        "group",
        "supergroup",
    }
)


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


def normalize_bot_username(value: str) -> str:
    username = value.strip()

    if not username:
        raise RuntimeError(
            "PROMO_BOT_USERNAME не может быть пустым"
        )

    if not username.startswith("@"):
        username = f"@{username}"

    return username


def filter_allowed_targets(
    targets: list[PublicationTarget],
) -> tuple[
    list[PublicationTarget],
    list[PublicationTarget],
]:
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
        raise RuntimeError(
            "Список рекламных сообщений пуст"
        )

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


def print_publication_plan(
    plan: list[PlannedPublication],
) -> None:
    print()
    print("План публикации")
    print("=" * 90)

    for number, publication in enumerate(
        plan,
        start=1,
    ):
        print()
        print(
            f"{number}. {publication.target.name}"
        )
        print(
            f"Тип: {publication.target.kind}"
        )
        print(
            f"ID: {publication.target.peer_id}"
        )
        print(
            f"Шаблон: {publication.message.id}"
        )
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
        "created_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "target_id": publication.target.peer_id,
        "target_name": publication.target.name,
        "target_kind": publication.target.kind,
        "template_id": publication.message.id,
        "status": status,
        "telegram_message_id": telegram_message_id,
        "error": error,
    }

    HISTORY_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    try:
        with HISTORY_PATH.open(
            mode="a",
            encoding="utf-8",
        ) as history_file:
            history_file.write(
                json.dumps(
                    record,
                    ensure_ascii=False,
                )
            )
            history_file.write("\n")

    except OSError as history_error:
        print(
            "[ПРЕДУПРЕЖДЕНИЕ] "
            "Не удалось записать журнал: "
            f"{history_error}"
        )


async def publish_plan(
    *,
    client: TelegramClient,
    plan: list[PlannedPublication],
    delay_min_seconds: int,
    delay_max_seconds: int,
) -> PublicationSummary:
    if delay_min_seconds < 0:
        raise ValueError(
            "Минимальная пауза не может быть отрицательной"
        )

    if delay_max_seconds < delay_min_seconds:
        raise ValueError(
            "Максимальная пауза не может быть меньше минимальной"
        )

    summary = PublicationSummary()

    for index, publication in enumerate(plan):
        if index > 0:
            delay = random.randint(
                delay_min_seconds,
                delay_max_seconds,
            )

            print()
            print(
                f"Пауза перед следующей публикацией: "
                f"{delay} сек."
            )

            await asyncio.sleep(delay)

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
                f"Повторная отправка возможна через "
                f"{error.seconds} сек."
            )

            append_history(
                publication=publication,
                status="slow_mode_wait",
                error=error_text,
            )

            print(
                f"[ПРОПУЩЕНО] "
                f"{publication.target.name}: "
                f"{error_text}"
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

            print(
                f"[ОСТАНОВКА] {error_text}"
            )

            break

        except errors.RPCError as error:
            summary.failed += 1

            error_text = (
                f"{type(error).__name__}: {error}"
            )

            append_history(
                publication=publication,
                status="telegram_error",
                error=error_text,
            )

            print(
                f"[ОШИБКА TELEGRAM] "
                f"{publication.target.name}: "
                f"{error_text}"
            )

            continue

        except (
            ValueError,
            ConnectionError,
            TimeoutError,
        ) as error:
            summary.failed += 1

            error_text = (
                f"{type(error).__name__}: {error}"
            )

            append_history(
                publication=publication,
                status="client_error",
                error=error_text,
            )

            print(
                f"[ОШИБКА] "
                f"{publication.target.name}: "
                f"{error_text}"
            )

            continue

        summary.successful += 1

        try:
            save_sent_message(
                target=publication.target.peer_id,
                message_id=publication.message.id,
            )
        except OSError as state_error:
            print(
                "[ПРЕДУПРЕЖДЕНИЕ] "
                "Сообщение отправлено, но состояние "
                f"шаблонов не сохранено: {state_error}"
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
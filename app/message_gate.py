from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from telethon import TelegramClient


DEFAULT_GATE_STATE_PATH = Path("data/message_gate_state.json")
DEFAULT_HISTORY_PATH = Path("data/publication_history.jsonl")


@dataclass(frozen=True)
class MessageGateStatus:
    allowed: bool
    new_message_count: int
    required_message_count: int
    last_sent_message_id: int | None


def _load_gate_state(
    path: str | Path = DEFAULT_GATE_STATE_PATH,
) -> dict[str, int]:
    state_path = Path(path)

    if not state_path.exists():
        return {}

    try:
        raw_state = json.loads(
            state_path.read_text(encoding="utf-8")
        )
    except json.JSONDecodeError as error:
        raise RuntimeError(
            f"Ошибка в файле состояния {state_path}: "
            f"строка {error.lineno}, столбец {error.colno}"
        ) from error

    if not isinstance(raw_state, dict):
        raise RuntimeError(
            "Содержимое message_gate_state.json должно быть JSON-объектом"
        )

    state: dict[str, int] = {}

    for target_id, raw_message_id in raw_state.items():
        if not isinstance(raw_message_id, int) or raw_message_id <= 0:
            raise RuntimeError(
                "ID последнего сообщения для получателя "
                f"{target_id} должен быть положительным целым числом"
            )

        state[str(target_id)] = raw_message_id

    return state


def _load_last_sent_message_id_from_history(
    *,
    target_id: int | str,
    path: str | Path = DEFAULT_HISTORY_PATH,
) -> int | None:
    history_path = Path(path)

    if not history_path.exists():
        return None

    target_key = str(target_id)
    last_message_id: int | None = None

    try:
        with history_path.open(encoding="utf-8") as history_file:
            for line_number, raw_line in enumerate(history_file, start=1):
                line = raw_line.strip()

                if not line:
                    continue

                try:
                    record = json.loads(line)
                except json.JSONDecodeError as error:
                    raise RuntimeError(
                        "Ошибка в журнале публикаций "
                        f"{history_path}, строка {line_number}"
                    ) from error

                if not isinstance(record, dict):
                    continue

                if str(record.get("target_id")) != target_key:
                    continue

                if record.get("status") != "sent":
                    continue

                telegram_message_id = record.get("telegram_message_id")

                if (
                    isinstance(telegram_message_id, int)
                    and telegram_message_id > 0
                ):
                    last_message_id = telegram_message_id
    except OSError as error:
        raise RuntimeError(
            f"Не удалось прочитать журнал публикаций {history_path}"
        ) from error

    return last_message_id


def get_last_sent_message_id(
    *,
    target_id: int | str,
    state_path: str | Path = DEFAULT_GATE_STATE_PATH,
    history_path: str | Path = DEFAULT_HISTORY_PATH,
) -> int | None:
    """Возвращает ID последней успешной публикации в конкретный чат.

    Сначала используется компактный runtime-state. Если он ещё не создан,
    выполняется восстановление из существующего publication_history.jsonl.
    Благодаря этому обновление можно установить поверх уже работающего
    сервиса без повторной немедленной публикации во все чаты.
    """

    target_key = str(target_id)
    state = _load_gate_state(state_path)

    if target_key in state:
        return state[target_key]

    return _load_last_sent_message_id_from_history(
        target_id=target_id,
        path=history_path,
    )


def save_last_sent_message_id(
    *,
    target_id: int | str,
    telegram_message_id: int,
    state_path: str | Path = DEFAULT_GATE_STATE_PATH,
) -> None:
    if telegram_message_id <= 0:
        raise ValueError(
            "telegram_message_id должен быть положительным числом"
        )

    state_file = Path(state_path)
    state = _load_gate_state(state_file)
    state[str(target_id)] = telegram_message_id

    state_file.parent.mkdir(parents=True, exist_ok=True)
    temporary_file = state_file.with_suffix(
        f"{state_file.suffix}.tmp"
    )
    temporary_file.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary_file.replace(state_file)


async def count_new_external_messages(
    *,
    client: TelegramClient,
    entity: object,
    after_message_id: int,
    stop_after: int,
) -> int:
    """Считает новые содержательные сообщения после нашей публикации.

    Исходящие сообщения текущего аккаунта и служебные события Telegram
    не учитываются. Подсчёт прекращается сразу после достижения порога.
    """

    if stop_after < 1:
        raise ValueError("stop_after должен быть не меньше 1")

    count = 0

    async for message in client.iter_messages(
        entity=entity,
        min_id=after_message_id,
        reverse=True,
    ):
        message_id = getattr(message, "id", None)

        if not isinstance(message_id, int) or message_id <= after_message_id:
            continue

        if bool(getattr(message, "out", False)):
            continue

        if getattr(message, "action", None) is not None:
            continue

        count += 1

        if count >= stop_after:
            break

    return count


async def check_message_gate(
    *,
    client: TelegramClient,
    entity: object,
    target_id: int | str,
    required_message_count: int,
) -> MessageGateStatus:
    if required_message_count < 1:
        raise ValueError(
            "required_message_count должен быть не меньше 1"
        )

    last_sent_message_id = get_last_sent_message_id(
        target_id=target_id,
    )

    # Для нового чата, в который сервис ещё не публиковал, разрешаем
    # первую публикацию. После неё ID сообщения будет сохранён.
    if last_sent_message_id is None:
        return MessageGateStatus(
            allowed=True,
            new_message_count=required_message_count,
            required_message_count=required_message_count,
            last_sent_message_id=None,
        )

    new_message_count = await count_new_external_messages(
        client=client,
        entity=entity,
        after_message_id=last_sent_message_id,
        stop_after=required_message_count,
    )

    return MessageGateStatus(
        allowed=new_message_count >= required_message_count,
        new_message_count=new_message_count,
        required_message_count=required_message_count,
        last_sent_message_id=last_sent_message_id,
    )

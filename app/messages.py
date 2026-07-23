import json
import random
from dataclasses import dataclass
from pathlib import Path


DEFAULT_MESSAGES_PATH = Path("data/messages.json")
DEFAULT_STATE_PATH = Path("data/message_state.json")


@dataclass(frozen=True)
class PromoMessage:
    id: str
    text: str

    def render(self, bot_username: str) -> str:
        return self.text.replace(
            "{bot_username}",
            bot_username,
        )


def load_messages(
    path: str | Path = DEFAULT_MESSAGES_PATH,
) -> list[PromoMessage]:
    messages_path = Path(path)

    if not messages_path.exists():
        raise RuntimeError(
            f"Файл с сообщениями не найден: {messages_path}"
        )

    try:
        raw_data = json.loads(
            messages_path.read_text(encoding="utf-8")
        )
    except json.JSONDecodeError as error:
        raise RuntimeError(
            f"Ошибка в JSON-файле {messages_path}: "
            f"строка {error.lineno}, столбец {error.colno}"
        ) from error

    if not isinstance(raw_data, list):
        raise RuntimeError(
            "Содержимое messages.json должно быть JSON-массивом"
        )

    messages: list[PromoMessage] = []
    used_ids: set[str] = set()

    for index, item in enumerate(raw_data, start=1):
        if not isinstance(item, dict):
            raise RuntimeError(
                f"Сообщение №{index} должно быть JSON-объектом"
            )

        message_id = item.get("id")
        text = item.get("text")

        if not isinstance(message_id, str) or not message_id.strip():
            raise RuntimeError(
                f"У сообщения №{index} отсутствует корректное поле id"
            )

        message_id = message_id.strip()

        if message_id in used_ids:
            raise RuntimeError(
                f"ID сообщения повторяется: {message_id}"
            )

        if not isinstance(text, str) or not text.strip():
            raise RuntimeError(
                f"У сообщения {message_id} отсутствует текст"
            )

        if "{bot_username}" not in text:
            raise RuntimeError(
                f"В сообщении {message_id} отсутствует "
                "плейсхолдер {bot_username}"
            )

        used_ids.add(message_id)
        messages.append(
            PromoMessage(
                id=message_id,
                text=text.strip(),
            )
        )

    if not messages:
        raise RuntimeError(
            "В messages.json нет ни одного сообщения"
        )

    return messages


def _deduplicate_history(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()

    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)

    return result


def load_message_state(
    path: str | Path = DEFAULT_STATE_PATH,
) -> dict[str, list[str]]:
    """Загружает историю шаблонов отдельно для каждого получателя.

    Старый формат ``{"target": "promo_01"}`` поддерживается и
    автоматически преобразуется в список из одного элемента.
    """

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
            "Содержимое message_state.json должно быть JSON-объектом"
        )

    state: dict[str, list[str]] = {}

    for target, raw_history in raw_state.items():
        target_key = str(target)

        if isinstance(raw_history, str):
            history = [raw_history]
        elif isinstance(raw_history, list) and all(
            isinstance(item, str)
            for item in raw_history
        ):
            history = list(raw_history)
        else:
            raise RuntimeError(
                "История шаблонов для получателя "
                f"{target_key} должна быть строкой или массивом строк"
            )

        state[target_key] = _deduplicate_history(history)

    return state


def choose_message(
    messages: list[PromoMessage],
    target: int | str,
    state_path: str | Path = DEFAULT_STATE_PATH,
) -> PromoMessage:
    """Выбирает шаблон без повторов, пока не исчерпан весь пул.

    История ведётся отдельно для каждого чата. Когда все доступные
    шаблоны уже использованы, начинается новый круг, при этом последний
    отправленный шаблон не выбирается сразу повторно.
    """

    if not messages:
        raise RuntimeError("Список рекламных сообщений пуст")

    state = load_message_state(state_path)
    target_key = str(target)
    current_message_ids = {message.id for message in messages}

    history = [
        message_id
        for message_id in state.get(target_key, [])
        if message_id in current_message_ids
    ]
    used_ids = set(history)

    available_messages = [
        message
        for message in messages
        if message.id not in used_ids
    ]

    if not available_messages:
        previous_message_id = history[-1] if history else None
        available_messages = [
            message
            for message in messages
            if message.id != previous_message_id
        ]

    if not available_messages:
        available_messages = messages

    return random.choice(available_messages)


def save_sent_message(
    target: int | str,
    message_id: str,
    state_path: str | Path = DEFAULT_STATE_PATH,
) -> None:
    """Сохраняет успешно отправленный шаблон в истории получателя."""

    state_file = Path(state_path)
    state = load_message_state(state_file)
    target_key = str(target)
    history = state.get(target_key, [])

    # Повторное появление ID означает начало нового круга ротации.
    if message_id in history:
        history = [message_id]
    else:
        history = [*history, message_id]

    state[target_key] = history
    state_file.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    serialized_state = json.dumps(
        state,
        ensure_ascii=False,
        indent=2,
    )
    temporary_file = state_file.with_suffix(
        f"{state_file.suffix}.tmp"
    )
    temporary_file.write_text(
        serialized_state,
        encoding="utf-8",
    )
    temporary_file.replace(state_file)

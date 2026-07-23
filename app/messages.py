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


def load_message_state(
    path: str | Path = DEFAULT_STATE_PATH,
) -> dict[str, str]:
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

    return {
        str(target): str(message_id)
        for target, message_id in raw_state.items()
    }


def choose_message(
    messages: list[PromoMessage],
    target: int | str,
    state_path: str | Path = DEFAULT_STATE_PATH,
) -> PromoMessage:
    state = load_message_state(state_path)
    target_key = str(target)

    previous_message_id = state.get(target_key)

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
    state_file = Path(state_path)
    state = load_message_state(state_file)

    state[str(target)] = message_id

    state_file.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    state_file.write_text(
        json.dumps(
            state,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
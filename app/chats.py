import json
from dataclasses import dataclass
from pathlib import Path


CHATS_PATH = Path("data/chats.json")


@dataclass(frozen=True)
class Chat:
    name: str
    target: int | str
    enabled: bool


def load_chats(path: Path = CHATS_PATH) -> list[Chat]:
    if not path.exists():
        raise RuntimeError(
            f"Файл со списком бесед не найден: {path}"
        )

    try:
        raw_chats = json.loads(
            path.read_text(encoding="utf-8")
        )
    except json.JSONDecodeError as error:
        raise RuntimeError(
            f"Ошибка в {path}: строка {error.lineno}, "
            f"столбец {error.colno}"
        ) from error

    if not isinstance(raw_chats, list):
        raise RuntimeError(
            "Содержимое chats.json должно быть массивом"
        )

    chats: list[Chat] = []

    for index, item in enumerate(raw_chats, start=1):
        if not isinstance(item, dict):
            raise RuntimeError(
                f"Запись №{index} должна быть объектом"
            )

        name = item.get("name")
        target = item.get("target")
        enabled = item.get("enabled", True)

        if not isinstance(name, str) or not name.strip():
            raise RuntimeError(
                f"У записи №{index} некорректное поле name"
            )

        if not isinstance(target, (int, str)):
            raise RuntimeError(
                f"У записи №{index} target должен быть "
                "числом или строкой"
            )

        if not isinstance(enabled, bool):
            raise RuntimeError(
                f"У записи №{index} enabled должен быть "
                "true или false"
            )

        chats.append(
            Chat(
                name=name.strip(),
                target=target,
                enabled=enabled,
            )
        )

    return chats


def load_enabled_chats() -> list[Chat]:
    return [
        chat
        for chat in load_chats()
        if chat.enabled
    ]
from dataclasses import dataclass
from typing import Any

from telethon import TelegramClient, utils
from telethon.tl.functions.messages import GetDialogFiltersRequest
from telethon.tl.types import Channel, Chat, User


@dataclass(frozen=True)
class PublicationTarget:
    name: str
    peer: Any
    peer_id: int
    kind: str


def _extract_text(value: Any) -> str:
    """Получает обычную строку из названия Telegram-папки."""

    if isinstance(value, str):
        return value

    text = getattr(value, "text", None)

    if isinstance(text, str):
        return text

    return str(value)


def _get_peer_key(peer: Any) -> tuple[str, str]:
    """Создаёт ключ для сравнения и удаления дубликатов."""

    for attribute in ("user_id", "chat_id", "channel_id"):
        value = getattr(peer, attribute, None)

        if value is not None:
            return attribute, str(value)

    return type(peer).__name__, repr(peer)


def _get_entity_kind(entity: Any) -> str:
    if isinstance(entity, User):
        if entity.bot:
            return "bot"

        return "user"

    if isinstance(entity, Chat):
        return "group"

    if isinstance(entity, Channel):
        if entity.megagroup:
            return "supergroup"

        if entity.broadcast:
            return "channel"

        return "channel"

    return type(entity).__name__


async def load_publication_targets(
    client: TelegramClient,
    folder_name: str,
) -> list[PublicationTarget]:
    """Загружает явно добавленные чаты из Telegram-папки."""

    response = await client(GetDialogFiltersRequest())
    dialog_filters = getattr(response, "filters", response)

    required_name = folder_name.strip().casefold()
    selected_filter = None
    available_folders: list[str] = []

    for dialog_filter in dialog_filters:
        title_value = getattr(dialog_filter, "title", None)

        if title_value is None:
            continue

        title = _extract_text(title_value).strip()

        if not title:
            continue

        available_folders.append(title)

        if title.casefold() == required_name:
            selected_filter = dialog_filter

    if selected_filter is None:
        available_text = ", ".join(available_folders) or "не найдены"

        raise RuntimeError(
            f'Папка Telegram "{folder_name}" не найдена. '
            f"Доступные папки: {available_text}"
        )

    automatic_rules = [
        rule
        for rule in (
            "contacts",
            "non_contacts",
            "groups",
            "broadcasts",
            "bots",
        )
        if bool(getattr(selected_filter, rule, False))
    ]

    if automatic_rules:
        raise RuntimeError(
            f'Папка "{folder_name}" использует автоматические '
            f"категории: {', '.join(automatic_rules)}. "
            "Отключи их и добавляй разрешённые чаты вручную."
        )

    included_peers = [
        *getattr(selected_filter, "pinned_peers", []),
        *getattr(selected_filter, "include_peers", []),
    ]

    excluded_peer_keys = {
        _get_peer_key(peer)
        for peer in getattr(
            selected_filter,
            "exclude_peers",
            [],
        )
    }

    targets: list[PublicationTarget] = []
    processed_peer_keys: set[tuple[str, str]] = set()

    for peer in included_peers:
        peer_key = _get_peer_key(peer)

        if peer_key in processed_peer_keys:
            continue

        if peer_key in excluded_peer_keys:
            continue

        processed_peer_keys.add(peer_key)

        entity = await client.get_entity(peer)

        targets.append(
            PublicationTarget(
                name=utils.get_display_name(entity),
                peer=peer,
                peer_id=utils.get_peer_id(entity),
                kind=_get_entity_kind(entity),
            )
        )

    if not targets:
        raise RuntimeError(
            f'В папке "{folder_name}" нет явно добавленных чатов.'
        )

    return targets
from __future__ import annotations

import os
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from telethon import TelegramClient


REMOTE_ALLOWED_KEYS = frozenset(
    {
        "PUBLICATION_ENABLED",
        "PUBLICATION_DELAY_MIN_SECONDS",
        "PUBLICATION_DELAY_MAX_SECONDS",
        "PUBLICATION_INTERVAL_MIN_MINUTES",
        "PUBLICATION_INTERVAL_MAX_MINUTES",
        "TELEGRAM_FOLDER_NAME",
        "PROMO_BOT_USERNAME",
    }
)

REMOTE_FORBIDDEN_KEYS = frozenset(
    {
        "TELEGRAM_API_ID",
        "TELEGRAM_API_HASH",
        "TELEGRAM_PHONE",
        "TELEGRAM_SESSION_PATH",
        "REMOTE_CONFIG_ENABLED",
        "REMOTE_CONFIG_MARKER",
        "REMOTE_CONFIG_REQUIRED",
        "REMOTE_CONFIG_POLL_SECONDS",
    }
)


class MessageLike(Protocol):
    id: int
    raw_text: str | None


class RemoteConfigError(RuntimeError):
    """Ошибка чтения или проверки конфигурации из Избранного."""


@dataclass(frozen=True)
class RuntimeSettings:
    publication_enabled: bool
    publication_delay_min_seconds: int
    publication_delay_max_seconds: int
    publication_interval_min_minutes: int
    publication_interval_max_minutes: int
    telegram_folder_name: str
    promo_bot_username: str


@dataclass(frozen=True)
class LoadedSettings:
    settings: RuntimeSettings
    source: str
    source_message_id: int | None = None


def get_required_env(name: str) -> str:
    value = os.getenv(name)

    if value is None or not value.strip():
        raise RuntimeError(
            f"Не задана обязательная переменная окружения: {name}"
        )

    return value.strip()


def parse_boolean(
    value: str,
    *,
    setting_name: str,
) -> bool:
    normalized = value.strip().casefold()

    if normalized in {"true", "1", "yes", "on"}:
        return True

    if normalized in {"false", "0", "no", "off"}:
        return False

    raise RuntimeError(
        f"{setting_name} должен иметь значение true или false"
    )


def get_boolean_env(name: str, default: bool) -> bool:
    value = os.getenv(name)

    if value is None or not value.strip():
        return default

    return parse_boolean(value, setting_name=name)


def get_integer_env(name: str, default: int) -> int:
    value = os.getenv(name)

    if value is None or not value.strip():
        return default

    try:
        return int(value)
    except ValueError as error:
        raise RuntimeError(
            f"{name} должен быть целым числом"
        ) from error


def normalize_bot_username(value: str) -> str:
    username = value.strip()

    if not username:
        raise RuntimeError(
            "PROMO_BOT_USERNAME не может быть пустым"
        )

    if not username.startswith("@"):
        username = f"@{username}"

    return username


def validate_settings(settings: RuntimeSettings) -> RuntimeSettings:
    if settings.publication_delay_min_seconds < 0:
        raise RuntimeError(
            "PUBLICATION_DELAY_MIN_SECONDS не может быть отрицательным"
        )

    if (
        settings.publication_delay_max_seconds
        < settings.publication_delay_min_seconds
    ):
        raise RuntimeError(
            "PUBLICATION_DELAY_MAX_SECONDS не может быть меньше "
            "PUBLICATION_DELAY_MIN_SECONDS"
        )

    if settings.publication_interval_min_minutes < 1:
        raise RuntimeError(
            "PUBLICATION_INTERVAL_MIN_MINUTES должен быть не меньше 1"
        )

    if (
        settings.publication_interval_max_minutes
        < settings.publication_interval_min_minutes
    ):
        raise RuntimeError(
            "PUBLICATION_INTERVAL_MAX_MINUTES не может быть меньше "
            "PUBLICATION_INTERVAL_MIN_MINUTES"
        )

    folder_name = settings.telegram_folder_name.strip()

    if not folder_name:
        raise RuntimeError(
            "TELEGRAM_FOLDER_NAME не может быть пустым"
        )

    return replace(
        settings,
        telegram_folder_name=folder_name,
        promo_bot_username=normalize_bot_username(
            settings.promo_bot_username
        ),
    )


def load_default_settings() -> RuntimeSettings:
    return validate_settings(
        RuntimeSettings(
            publication_enabled=get_boolean_env(
                "PUBLICATION_ENABLED",
                default=False,
            ),
            publication_delay_min_seconds=get_integer_env(
                "PUBLICATION_DELAY_MIN_SECONDS",
                default=15,
            ),
            publication_delay_max_seconds=get_integer_env(
                "PUBLICATION_DELAY_MAX_SECONDS",
                default=30,
            ),
            publication_interval_min_minutes=get_integer_env(
                "PUBLICATION_INTERVAL_MIN_MINUTES",
                default=60,
            ),
            publication_interval_max_minutes=get_integer_env(
                "PUBLICATION_INTERVAL_MAX_MINUTES",
                default=90,
            ),
            telegram_folder_name=get_required_env(
                "TELEGRAM_FOLDER_NAME"
            ),
            promo_bot_username=get_required_env(
                "PROMO_BOT_USERNAME"
            ),
        )
    )


def normalize_marker(value: str) -> str:
    return value.strip().lstrip("#").strip().casefold()


def parse_remote_config_text(
    text: str,
    *,
    marker: str,
) -> dict[str, str]:
    lines = text.splitlines()
    first_meaningful_line = next(
        (line.strip() for line in lines if line.strip()),
        "",
    )

    if normalize_marker(first_meaningful_line) != normalize_marker(marker):
        raise RemoteConfigError(
            "Первая непустая строка сообщения не совпадает "
            "с маркером удалённой конфигурации"
        )

    values: dict[str, str] = {}
    marker_skipped = False

    for line_number, original_line in enumerate(lines, start=1):
        line = original_line.strip()

        if not line:
            continue

        if not marker_skipped:
            marker_skipped = True
            continue

        if line.startswith("#"):
            continue

        if "=" not in line:
            raise RemoteConfigError(
                "Некорректная строка удалённой конфигурации "
                f"№{line_number}: {original_line}"
            )

        key, value = line.split("=", maxsplit=1)
        key = key.strip()
        value = value.strip()

        if not key:
            raise RemoteConfigError(
                f"Пустое имя параметра в строке №{line_number}"
            )

        if key in values:
            raise RemoteConfigError(
                f"Параметр {key} указан несколько раз"
            )

        values[key] = value

    forbidden_keys = sorted(
        REMOTE_FORBIDDEN_KEYS.intersection(values)
    )

    if forbidden_keys:
        raise RemoteConfigError(
            "В удалённой конфигурации запрещены параметры подключения: "
            + ", ".join(forbidden_keys)
        )

    unknown_keys = sorted(set(values) - REMOTE_ALLOWED_KEYS)

    if unknown_keys:
        raise RemoteConfigError(
            "Неизвестные параметры удалённой конфигурации: "
            + ", ".join(unknown_keys)
        )

    return values


def apply_remote_overrides(
    defaults: RuntimeSettings,
    values: dict[str, str],
) -> RuntimeSettings:
    settings = defaults

    if "PUBLICATION_ENABLED" in values:
        settings = replace(
            settings,
            publication_enabled=parse_boolean(
                values["PUBLICATION_ENABLED"],
                setting_name="PUBLICATION_ENABLED",
            ),
        )

    integer_fields = {
        "PUBLICATION_DELAY_MIN_SECONDS": (
            "publication_delay_min_seconds"
        ),
        "PUBLICATION_DELAY_MAX_SECONDS": (
            "publication_delay_max_seconds"
        ),
        "PUBLICATION_INTERVAL_MIN_MINUTES": (
            "publication_interval_min_minutes"
        ),
        "PUBLICATION_INTERVAL_MAX_MINUTES": (
            "publication_interval_max_minutes"
        ),
    }

    for config_key, field_name in integer_fields.items():
        if config_key not in values:
            continue

        try:
            integer_value = int(values[config_key])
        except ValueError as error:
            raise RemoteConfigError(
                f"{config_key} должен быть целым числом"
            ) from error

        settings = replace(
            settings,
            **{field_name: integer_value},
        )

    if "TELEGRAM_FOLDER_NAME" in values:
        settings = replace(
            settings,
            telegram_folder_name=values["TELEGRAM_FOLDER_NAME"],
        )

    if "PROMO_BOT_USERNAME" in values:
        settings = replace(
            settings,
            promo_bot_username=values["PROMO_BOT_USERNAME"],
        )

    try:
        return validate_settings(settings)
    except RuntimeError as error:
        raise RemoteConfigError(str(error)) from error


async def find_remote_config_message(
    *,
    client: TelegramClient,
    marker: str,
) -> MessageLike | None:
    search_term = marker.strip().lstrip("#").strip()

    async for message in client.iter_messages(
        entity="me",
        search=search_term,
        limit=20,
    ):
        text = message.raw_text or ""
        first_meaningful_line = next(
            (line.strip() for line in text.splitlines() if line.strip()),
            "",
        )

        if normalize_marker(first_meaningful_line) == normalize_marker(marker):
            return message

    return None


async def load_runtime_settings(
    *,
    client: TelegramClient,
    fail_closed: bool = False,
) -> LoadedSettings:
    defaults = load_default_settings()

    if not get_boolean_env("REMOTE_CONFIG_ENABLED", default=True):
        return LoadedSettings(
            settings=defaults,
            source="local_env",
        )

    marker = os.getenv(
        "REMOTE_CONFIG_MARKER",
        "promo-publisher-config",
    ).strip()

    if not marker:
        raise RemoteConfigError(
            "REMOTE_CONFIG_MARKER не может быть пустым"
        )

    remote_required = get_boolean_env(
        "REMOTE_CONFIG_REQUIRED",
        default=True,
    )

    try:
        message = await find_remote_config_message(
            client=client,
            marker=marker,
        )
    except Exception as error:
        if fail_closed or remote_required:
            raise RemoteConfigError(
                "Не удалось прочитать конфигурацию из Избранного"
            ) from error

        return LoadedSettings(
            settings=defaults,
            source="local_env_fallback",
        )

    if message is None:
        if fail_closed or remote_required:
            raise RemoteConfigError(
                "Сообщение удалённой конфигурации не найдено в Избранном"
            )

        return LoadedSettings(
            settings=defaults,
            source="local_env_fallback",
        )

    values = parse_remote_config_text(
        message.raw_text or "",
        marker=marker,
    )
    settings = apply_remote_overrides(defaults, values)

    return LoadedSettings(
        settings=settings,
        source="saved_messages",
        source_message_id=message.id,
    )


def format_settings(loaded: LoadedSettings) -> str:
    settings = loaded.settings
    lines = [
        "Конфигурация приложения",
        "-" * 60,
        f"Источник: {loaded.source}",
        f"Публикации включены: {settings.publication_enabled}",
        (
            "Пауза между чатами: "
            f"{settings.publication_delay_min_seconds}–"
            f"{settings.publication_delay_max_seconds} сек."
        ),
        (
            "Интервал между циклами: "
            f"{settings.publication_interval_min_minutes}–"
            f"{settings.publication_interval_max_minutes} мин."
        ),
        f'Папка Telegram: "{settings.telegram_folder_name}"',
        f"Рекламируемый бот: {settings.promo_bot_username}",
    ]

    if loaded.source_message_id is not None:
        lines.insert(
            3,
            f"ID сообщения в Избранном: {loaded.source_message_id}",
        )

    lines.append("-" * 60)
    return "\n".join(lines)

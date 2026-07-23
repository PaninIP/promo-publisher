# Promo Publisher

Сервис на Telethon для публикации сообщений от пользовательского Telegram-аккаунта в заранее разрешённых чатах. Получатели берутся из пользовательской папки Telegram, например `Реклама`.

## Возможности

- авторизация пользовательского аккаунта через MTProto;
- получение разрешённых чатов из Telegram-папки;
- ротация рекламных шаблонов без немедленного повторения;
- предпросмотр, один ручной цикл и постоянный режим для VPS;
- пауза между чатами и интервал между циклами;
- удалённая конфигурация через сообщение в «Избранном»;
- аварийный выключатель `PUBLICATION_ENABLED=false`;
- повторная проверка выключателя перед каждой отправкой и во время ожидания;
- безопасная остановка при ошибке удалённой конфигурации;
- журнал публикаций в JSON Lines.

Приложение предназначено только для чатов, правила которых разрешают соответствующие публикации.

## Установка

```powershell
uv sync
Copy-Item .env.example .env
```

Заполни в `.env` только реальные параметры подключения и локальные значения по умолчанию. Файлы `.env` и `*.session` нельзя публиковать.

## Авторизация

```powershell
uv run python -m app.auth
```

## Удалённая конфигурация

Создай в «Избранном» одно сообщение и редактируй именно его:

```dotenv
#promo-publisher-config

PUBLICATION_ENABLED=false

PUBLICATION_DELAY_MIN_SECONDS=15
PUBLICATION_DELAY_MAX_SECONDS=30

PUBLICATION_INTERVAL_MIN_MINUTES=60
PUBLICATION_INTERVAL_MAX_MINUTES=90

TELEGRAM_FOLDER_NAME=Реклама
PROMO_BOT_USERNAME=@your_bot_username
```

Параметры подключения `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, `TELEGRAM_PHONE` и `TELEGRAM_SESSION_PATH` в сообщение добавлять нельзя.

### Выключатель публикаций

```dotenv
PUBLICATION_ENABLED=false
```

В постоянном режиме это значение блокирует новые отправки. Конфигурация проверяется перед каждой публикацией и во время пауз. Если сообщение конфигурации отсутствует, недоступно или содержит ошибку, приложение действует безопасно и не отправляет новые сообщения.

Для запуска публикаций измени значение на:

```dotenv
PUBLICATION_ENABLED=true
```

## Команды

Просмотреть все диалоги аккаунта:

```powershell
uv run python -m app.discover_chats
```

Предпросмотр без отправки:

```powershell
uv run python -m app.main
```

Предпросмотр одного чата:

```powershell
uv run python -m app.main --target-id -1001234567890
```

Один цикл с подтверждением:

```powershell
uv run python -m app.main --send
```

Один цикл без интерактивного подтверждения:

```powershell
uv run python -m app.main --send --yes
```

Постоянная работа на VPS:

```powershell
uv run python -m app.main --daemon
```

При старте постоянного режима первый цикл выполняется сразу, если `PUBLICATION_ENABLED=true`. Затем приложение ждёт случайный интервал из удалённой конфигурации.

## Проверка

```powershell
uv run python -m compileall app tests
uv run python -m unittest discover -s tests -v
```

## Runtime-файлы

Локально могут появиться:

- `data/message_state.json` — последний шаблон по каждому чату;
- `data/publication_history.jsonl` — журнал результатов;
- `data/promo_publisher.session` — Telegram-сессия.

Они исключены из Git и не должны попадать в репозиторий.

# Promo Publisher

Сервис на Telethon для публикации сообщений от пользовательского Telegram-аккаунта в заранее разрешённых чатах. Получатели берутся из пользовательской папки Telegram, например `Реклама`.

Приложение предназначено только для чатов, правила которых разрешают соответствующие публикации.

## Возможности

- авторизация пользовательского аккаунта через MTProto;
- получение разрешённых групп и супергрупп из Telegram-папки;
- 100 уникальных рекламных шаблонов;
- отдельная ротация шаблонов для каждого чата без повторов до исчерпания пула;
- предпросмотр, один ручной цикл и постоянный режим для VPS;
- настраиваемая пауза между чатами и интервал между циклами;
- удалённая конфигурация через сообщение в «Избранном»;
- аварийный выключатель `PUBLICATION_ENABLED=false`;
- повторная проверка выключателя перед каждой отправкой и во время ожидания;
- безопасная остановка при отсутствии или ошибке удалённой конфигурации;
- журнал публикаций в формате JSON Lines.

## Структура

- `app/auth.py` — первичная авторизация Telegram-аккаунта;
- `app/discover_chats.py` — просмотр доступных диалогов;
- `app/folder_targets.py` — загрузка получателей из Telegram-папки;
- `app/messages.py` — загрузка и ротация шаблонов;
- `app/publisher.py` — контролируемая отправка и журналирование;
- `app/settings.py` — локальная и удалённая конфигурация;
- `app/main.py` — точка запуска;
- `data/messages.json` — 100 вариантов сообщений;
- `deploy/promo-publisher.service` — шаблон systemd-сервиса.

## Локальная установка

```powershell
uv sync
Copy-Item .env.example .env
```

Заполни `.env` реальными параметрами подключения и локальными значениями по умолчанию. Файлы `.env` и `*.session` нельзя публиковать.

## Авторизация

```powershell
uv run python -m app.auth
```

После успешной авторизации появится файл сессии, например `data/promo_publisher.session`.

## Удалённая конфигурация

Создай в «Избранном» одно обычное текстовое сообщение и редактируй именно его:

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

### Аварийный выключатель

```dotenv
PUBLICATION_ENABLED=false
```

В постоянном режиме это значение блокирует новые отправки. Конфигурация проверяется перед каждой публикацией и во время пауз. Если сообщение конфигурации отсутствует, недоступно или содержит ошибку, приложение действует по принципу fail closed и ничего не отправляет.

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

Постоянная работа:

```powershell
uv run python -m app.main --daemon
```

При старте постоянного режима первый цикл выполняется сразу, если `PUBLICATION_ENABLED=true`. После завершения цикла приложение ждёт случайный интервал из конфигурации.

## Проверка

```powershell
uv run python -m compileall app tests
uv run python -m unittest discover -s tests -v
uv run python -c "from app.messages import load_messages; print(len(load_messages()))"
```

Ожидается 10 успешных тестов и число `100`.

## Runtime-файлы

Локально создаются:

- `data/message_state.json` — история использованных шаблонов отдельно для каждого чата;
- `data/publication_history.jsonl` — журнал результатов;
- `data/promo_publisher.session` — Telegram-сессия.

Эти файлы исключены из Git.

## Развёртывание на Ubuntu VPS

Пример рассчитан на каталог `/opt/promo-publisher` и системного пользователя `promo-publisher`.

### 1. Подготовка сервера

```bash
sudo apt update
sudo apt install -y git curl ca-certificates
sudo useradd --system --create-home --shell /bin/bash promo-publisher
sudo mkdir -p /opt/promo-publisher
sudo chown promo-publisher:promo-publisher /opt/promo-publisher
```

### 2. Установка uv

```bash
sudo -u promo-publisher -H bash -lc 'curl -LsSf https://astral.sh/uv/install.sh | sh'
```

### 3. Клонирование проекта

```bash
sudo -u promo-publisher -H git clone <REPOSITORY_URL> /opt/promo-publisher
cd /opt/promo-publisher
sudo -u promo-publisher -H /home/promo-publisher/.local/bin/uv sync --frozen
```

Для приватного репозитория заранее настрой SSH-ключ или другой безопасный способ доступа к GitHub.

### 4. Секреты и Telegram-сессия

Создай `/opt/promo-publisher/.env` на основе `.env.example` и перенеси существующий session-файл в `/opt/promo-publisher/data/`.

```bash
sudo chown promo-publisher:promo-publisher /opt/promo-publisher/.env
sudo chown -R promo-publisher:promo-publisher /opt/promo-publisher/data
sudo chmod 600 /opt/promo-publisher/.env
sudo chmod 600 /opt/promo-publisher/data/*.session
```

### 5. Контрольная проверка

```bash
cd /opt/promo-publisher
sudo -u promo-publisher -H /home/promo-publisher/.local/bin/uv run python -m unittest discover -s tests -v
sudo -u promo-publisher -H /home/promo-publisher/.local/bin/uv run python -m app.main --limit 1
```

### 6. systemd

```bash
sudo cp deploy/promo-publisher.service /etc/systemd/system/promo-publisher.service
sudo systemctl daemon-reload
sudo systemctl enable --now promo-publisher
sudo systemctl status promo-publisher
```

Журнал сервиса:

```bash
sudo journalctl -u promo-publisher -f
```

Остановка и запуск:

```bash
sudo systemctl stop promo-publisher
sudo systemctl start promo-publisher
sudo systemctl restart promo-publisher
```

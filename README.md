# MOEX Signal Bot

Русскоязычный Telegram-бот для анализа российских акций на MOEX по данным `moexalgo` и ALGOPACK.

Бот показывает котировки, покупательную и продавцовую силу, состояние стакана, давление заявок, события MegaAlert и скоринговые торговые сигналы. Также есть MOEX Flow Pro: автоматический Scanner Pro через Redis Streams и worker-процессы, расширенные настройки watchlist, FUTOI по фьючерсам, тепловая карта, портфельный риск, дайджест, простая статистика похожих состояний и короткий формат сигнала для Telegram-каналов.

Сигналы являются аналитикой по данным, а не инвестиционной рекомендацией.

## Возможности

- Русские ответы Telegram-бота.
- Анализ `TradeStats`: покупки, продажи, чистый поток, buy/sell power.
- Анализ `OrderStats`: выставленные и снятые заявки покупателей и продавцов.
- Анализ `OBStats`: дисбаланс стакана и BBO.
- Анализ `MegaAlert`: аномальные события ALGOPACK.
- Скоринговые сигналы по нескольким источникам данных.
- Watchlist и автоматический сканер с хранением в PostgreSQL.
- Redis Streams очередь с ACK/reclaim для фонового автосканера и горизонтального масштабирования scanner workers.
- Настройки автосканера: минимальный score, тихие часы и фильтр типов сигналов.
- Тепловая карта по тикерам и краткий рыночный дайджест.
- FUTOI по фьючерсам MOEX.
- Портфельный мониторинг риска.
- Канальный формат `MOEX Flow Alert`.
- Дедупликация автосигналов, чтобы не спамить пользователя одинаковыми событиями.
- Docker-образ для запуска сервиса.
- Ruff и pre-commit для проверки качества кода.

## Команды бота

| Команда | Что делает |
| --- | --- |
| `/help` | Показывает список команд. |
| `/quote ROSN` | Краткая текущая котировка. |
| `/flow ROSN 7` | Покупательная и продавцовая сила по `TradeStats` за N дней. |
| `/strategy ROSN` | Базовый сценарий по потоку сделок. |
| `/signal ROSN` | Скоринговый сигнал по `TradeStats`, `OrderStats`, `OBStats` и `MegaAlert`. |
| `/scan ROSN SBER LKOH` | Быстрый сканер по нескольким тикерам. |
| `/full ROSN` | Полный отчет по тикеру. |
| `/book ROSN` | Краткий статус стакана по `OBStats`. |
| `/orders ROSN` | Давление выставленных и снятых заявок по `OrderStats`. |
| `/alerts ROSN` | Сводка событий `MegaAlert`. |
| `/heatmap ROSN SBER LKOH` | Тепловая карта по силе сигнала, потоку и MegaAlert. |
| `/mega ROSN` | Расширенная лента MegaAlert по одному или нескольким тикерам. |
| `/digest ROSN SBER` | Краткий дайджест главных сигналов. |
| `/stats ROSN 30` | Историческая статистика похожих состояний по `TradeStats`. |
| `/watch ROSN 15m` | Добавить тикер в автоматический сканер с интервалом 15 минут. |
| `/unwatch ROSN` | Удалить тикер из автоматического сканера. |
| `/watchlist` | Показать тикеры автосканера. |
| `/mute ROSN 60` | Поставить автосигналы по тикеру на паузу на 60 минут. |
| `/settings` | Показать настройки Scanner Pro. |
| `/score 70` | Минимальная сила автосигнала для чата. |
| `/quiet 23:00 07:00` | Тихие часы без автосигналов. |
| `/types sell_pressure absorption` | Фильтр типов автосигналов. |
| `/futoi SBERF` | Открытый интерес по фьючерсу через FUTOI. |
| `/portfolio_add ROSN` | Добавить тикер в портфель. |
| `/portfolio_remove ROSN` | Удалить тикер из портфеля. |
| `/portfolio` | Показать портфель. |
| `/portfolio_risk` | Проверить риск по портфелю. |
| `/channel_signal ROSN` | Короткий сигнал для публикации в Telegram-канале. |

Тикеры нормализуются в верхний регистр. По умолчанию бот рассчитан на рынок акций MOEX TQBR.

## Prompt Templates

- [Full MOEX stock analysis prompt](prompts/stock-analysis.md) - шаблон для полного анализа конкретного тикера, например `ROSN`.

## Как работает сигнал

Базовая сила покупок и продаж считается из `TradeStats`:

```text
buy_power = val_b / (val_b + val_s)
sell_power = val_s / (val_b + val_s)
imbalance = (val_b - val_s) / (val_b + val_s)
```

Состояния:

- `Давление продавцов`: цена падает вместе с отрицательным дисбалансом сделок.
- `Абсорбция продаж`: цена снижается, но покупатели забирают значимую часть продаж.
- `Бычий разворот`: цена растет вместе с положительным потоком.
- `Слабый отскок`: цена растет, но поток не подтверждает контроль покупателей.
- `Нейтрально`: явного преимущества нет.

Скоринг учитывает:

- изменение цены за день;
- дисбаланс сделок;
- последние интервалы покупок и продаж;
- давление выставленных заявок;
- дисбаланс BBO в стакане;
- события MegaAlert по новым минимумам или максимумам.

Автосканер работает в три шага:

1. `bot` принимает Telegram-команды и пишет watchlist/settings в PostgreSQL.
2. `scanner-scheduler` регулярно ищет due watchlist items и ставит ticker-level задачи в Redis Stream.
3. Один или несколько `scanner-worker` процессов берут задачи из Redis Stream, читают MOEX/ALGOPACK один раз на тикер, проверяют дедупликацию в PostgreSQL и отправляют Telegram-сигналы всем due чатам из задачи.

Автосканер отправляет сообщение только если:

- тикер есть в watchlist пользователя;
- наступил интервал проверки;
- сигнал достаточно сильный;
- такой сигнал еще не отправлялся этому чату;
- тикер не находится на паузе после `/mute`.
- текущее время не попадает в тихие часы `/quiet`;
- тип сигнала проходит фильтр `/types`, если фильтр задан.

Типы сигналов Scanner Pro:

- `sell_pressure`: продавцы контролируют поток.
- `absorption`: цена снижается, но покупатели активно забирают продажи.
- `bullish_reversal`: рост цены подтвержден покупательным потоком.
- `weak_bounce`: отскок без сильного подтверждения покупателями.
- `breakdown`: продавцовый сигнал с новыми минимумами или сильным снижением.
- `reclaim`: возврат контроля или движение к покупателям.
- `megaalert_cluster`: несколько аномальных событий MegaAlert.

## Переменные окружения

Создайте локальный `.env` по примеру `.env.example`:

```bash
TELEGRAM_BOT_TOKEN=
MOEX_API_KEY=
POSTGRES_DB=moex_signal_bot
POSTGRES_USER=moex
POSTGRES_PASSWORD=change-me
DATABASE_URL=postgresql://moex:change-me@postgres:5432/moex_signal_bot
REDIS_URL=redis://redis:6379/0
SCANNER_QUEUE_KEY=moex:scanner:stream
SCANNER_INTERVAL_SECONDS=60
SCANNER_WORKER_POP_TIMEOUT_SECONDS=5
SCANNER_MAX_ATTEMPTS=3
SCANNER_RETRY_DELAY_SECONDS=5
DEFAULT_SCAN_TICKERS=ROSN SBER GAZP LKOH TATN TATNP
```

Можно использовать `MOEXALGO_API_KEY` вместо `MOEX_API_KEY`.

Назначение переменных:

- `TELEGRAM_BOT_TOKEN`: токен Telegram-бота.
- `MOEX_API_KEY`: API-ключ MOEX/ALGOPACK для `moexalgo`.
- `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`: параметры контейнера PostgreSQL в Docker Compose.
- `DATABASE_URL`: строка подключения PostgreSQL для watchlist, настроек, портфеля и дедупликации.
- `REDIS_URL`: строка подключения Redis для очереди задач автосканера.
- `SCANNER_QUEUE_KEY`: имя Redis Stream для задач автосканера.
- `SCANNER_INTERVAL_SECONDS`: частота scheduler-цикла автосканера.
- `SCANNER_WORKER_POP_TIMEOUT_SECONDS`: сколько worker ждет задачу из Redis перед следующим циклом.
- `SCANNER_MAX_ATTEMPTS`: сколько повторных попыток делать для упавшей задачи.
- `SCANNER_RETRY_DELAY_SECONDS`: пауза перед повторной постановкой упавшей задачи.
- `DEFAULT_SCAN_TICKERS`: тикеры для `/heatmap`, `/mega` и `/digest`, если пользователь не указал список.

Не коммитьте реальные токены, JWT, `.env`, дампы PostgreSQL и пользовательские данные.

## Локальный запуск

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
DATABASE_URL=postgresql://moex:change-me@localhost:5432/moex_signal_bot python -m moex_signal_bot
```

Локальная проверка без Telegram:

```bash
python -m moex_signal_bot --dry-run "/help"
python -m moex_signal_bot --dry-run "/flow ROSN 7"
python -m moex_signal_bot --dry-run "/signal ROSN"
python -m moex_signal_bot --dry-run "/scan ROSN SBER"
python -m moex_signal_bot --dry-run "/heatmap ROSN SBER"
python -m moex_signal_bot --dry-run "/futoi SBERF"
```

Если используется локальный checkout `moexalgo`, можно добавить его в `PYTHONPATH`:

```bash
PYTHONPATH=src:/home/elijah/Desktop/moexalgo python3 -m moex_signal_bot --dry-run "/help"
```

## Makefile

Основные команды собраны в `Makefile`:

```bash
make install
make test
make lint
make check
make docker-build
make compose-up
make workers WORKERS=3
make compose-logs
make compose-down
```

`make check` запускает `pytest`, `ruff check`, `ruff format --check` и `git diff --check`. `make workers WORKERS=3` масштабирует только `scanner-worker`; `bot` и `scanner-scheduler` должны оставаться в одном экземпляре.

## Docker

Рекомендуемый запуск через Docker Compose:

```bash
cp .env.example .env
# Заполните TELEGRAM_BOT_TOKEN, MOEX_API_KEY и смените POSTGRES_PASSWORD/DATABASE_URL.
docker compose up -d --build
```

Проверка логов:

```bash
docker compose logs -f bot
docker compose logs -f scanner-scheduler scanner-worker
```

Масштабирование worker-процессов автосканера:

```bash
docker compose up -d --scale scanner-worker=3
```

Остановка:

```bash
docker compose down
```

Данные PostgreSQL хранятся в volume `postgres-data`. Redis queue/cache хранится в volume `redis-data`.

Сборка одиночного образа:

```bash
docker build -t moex-signal-bot .
```

Запуск одиночного контейнера требует внешний PostgreSQL. Для автоматического сканера также нужны внешний Redis и отдельные процессы scheduler/worker:

```bash
docker run --rm --env-file .env moex-signal-bot
docker run --rm --env-file .env moex-signal-bot python -m moex_signal_bot --scanner-scheduler
docker run --rm --env-file .env moex-signal-bot python -m moex_signal_bot --scanner-worker
```

Проверка образа без секретов:

```bash
docker run --rm moex-signal-bot python -m moex_signal_bot --dry-run "/help"
```

## Проверка качества

```bash
python3 -m pytest -q
ruff check .
ruff format --check .
pre-commit run --all-files
```

Установка pre-commit хуков:

```bash
pre-commit install
```

## Структура проекта

```text
src/moex_signal_bot/
  bot.py              # разбор команд и Telegram-ответы
  moex_provider.py    # адаптер moexalgo
  signals.py          # базовые модели и классификация
  scanner.py          # скоринг и автоматический сканер
  scanner_queue.py    # Redis-очередь, scheduler jobs и worker processing
  analytics.py        # heatmap, MegaAlert feed, digest и статистика
  futoi.py            # агрегация открытого интереса FUTOI
  portfolio.py        # риск портфеля
  storage.py          # PostgreSQL watchlist, настройки, портфель и дедупликация
  memory_storage.py   # in-memory store для тестов и dry-run без DATABASE_URL
  formatters.py       # русские текстовые отчеты
  telegram_client.py  # Telegram Bot API client
  __main__.py         # polling loop и scanner loop
tests/                # unit и integration-style тесты
```

## Безопасность и ограничения

- Бот не размещает торговые заявки и не подключается к брокерскому API.
- Автосигналы являются уведомлениями, а не автоматической торговлей.
- Запускайте только один экземпляр `bot`: Telegram long polling не рассчитан на несколько polling-реплик.
- Запускайте только один `scanner-scheduler`, чтобы не ставить дублирующие задачи.
- `scanner-worker` можно масштабировать через `docker compose up -d --scale scanner-worker=3`.
- Пользователь сам отвечает за интерпретацию сигналов, риск и размер позиции.
- Перед расширением в сторону реальной торговли нужны отдельные risk controls, журнал решений, лимиты и ручное подтверждение.

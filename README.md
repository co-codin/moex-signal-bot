# MOEX Signal Bot

Русскоязычный Telegram-бот для анализа российских акций на MOEX по данным `moexalgo` и ALGOPACK.

Бот показывает котировки, покупательную и продавцовую силу, состояние стакана, давление заявок, события MegaAlert и скоринговые торговые сигналы. Также есть автоматический сканер: пользователь добавляет тикеры в watchlist, а бот сам отправляет сильные новые сигналы с дедупликацией.

Сигналы являются аналитикой по данным, а не инвестиционной рекомендацией.

## Возможности

- Русские ответы Telegram-бота.
- Анализ `TradeStats`: покупки, продажи, чистый поток, buy/sell power.
- Анализ `OrderStats`: выставленные и снятые заявки покупателей и продавцов.
- Анализ `OBStats`: дисбаланс стакана и BBO.
- Анализ `MegaAlert`: аномальные события ALGOPACK.
- Скоринговые сигналы по нескольким источникам данных.
- Watchlist и автоматический сканер с хранением в SQLite.
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
| `/watch ROSN 15m` | Добавить тикер в автоматический сканер с интервалом 15 минут. |
| `/unwatch ROSN` | Удалить тикер из автоматического сканера. |
| `/watchlist` | Показать тикеры автосканера. |
| `/mute ROSN 60` | Поставить автосигналы по тикеру на паузу на 60 минут. |

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

Автосканер отправляет сообщение только если:

- тикер есть в watchlist пользователя;
- наступил интервал проверки;
- сигнал достаточно сильный;
- такой сигнал еще не отправлялся этому чату;
- тикер не находится на паузе после `/mute`.

## Переменные окружения

Создайте локальный `.env` по примеру `.env.example`:

```bash
TELEGRAM_BOT_TOKEN=
MOEX_API_KEY=
MOEX_SIGNAL_DB=signals.sqlite3
SCANNER_INTERVAL_SECONDS=60
```

Можно использовать `MOEXALGO_API_KEY` вместо `MOEX_API_KEY`.

Назначение переменных:

- `TELEGRAM_BOT_TOKEN`: токен Telegram-бота.
- `MOEX_API_KEY`: API-ключ MOEX/ALGOPACK для `moexalgo`.
- `MOEX_SIGNAL_DB`: путь к SQLite базе watchlist и дедупликации.
- `SCANNER_INTERVAL_SECONDS`: частота фонового цикла автосканера.

Не коммитьте реальные токены, JWT, `.env`, SQLite базы и пользовательские данные.

## Локальный запуск

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
python -m moex_signal_bot
```

Локальная проверка без Telegram:

```bash
python -m moex_signal_bot --dry-run "/help"
python -m moex_signal_bot --dry-run "/flow ROSN 7"
python -m moex_signal_bot --dry-run "/signal ROSN"
python -m moex_signal_bot --dry-run "/scan ROSN SBER"
```

Если используется локальный checkout `moexalgo`, можно добавить его в `PYTHONPATH`:

```bash
PYTHONPATH=src:/home/elijah/Desktop/moexalgo python3 -m moex_signal_bot --dry-run "/help"
```

## Docker

Сборка:

```bash
docker build -t moex-signal-bot .
```

Запуск:

```bash
docker run --rm --env-file .env -v moex-signal-data:/data moex-signal-bot
```

В Docker по умолчанию база хранится в `/data/signals.sqlite3`, поэтому volume сохраняет watchlist и историю отправленных сигналов между перезапусками.

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
  storage.py          # SQLite watchlist и дедупликация
  formatters.py       # русские текстовые отчеты
  telegram_client.py  # Telegram Bot API client
  __main__.py         # polling loop и scanner loop
tests/                # unit и integration-style тесты
```

## Безопасность и ограничения

- Бот не размещает торговые заявки и не подключается к брокерскому API.
- Автосигналы являются уведомлениями, а не автоматической торговлей.
- Пользователь сам отвечает за интерпретацию сигналов, риск и размер позиции.
- Перед расширением в сторону реальной торговли нужны отдельные risk controls, журнал решений, лимиты и ручное подтверждение.

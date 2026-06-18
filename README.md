# MOEX Signal Bot

Русскоязычный Telegram-бот для анализа MOEX/ALGOPACK по тикерам акций.

## Возможности

- `/quote ROSN` - краткая котировка.
- `/flow ROSN 7` - покупательная и продавцовая сила по `TradeStats`.
- `/strategy ROSN` - сценарий: давление продавцов, абсорбция, разворот или нейтрально.
- `/signal ROSN` - скоринговый сигнал по `TradeStats`, `OrderStats`, `OBStats` и `MegaAlert`.
- `/scan ROSN SBER` - быстрый сканер по нескольким тикерам.
- `/full ROSN` - полный отчет по тикеру.
- `/book ROSN` - последние метрики стакана по `OBStats`.
- `/orders ROSN` - давление выставленных и снятых заявок по `OrderStats`.
- `/alerts ROSN` - события `MegaAlert`.
- `/watch ROSN 15m` - добавить тикер в автоматический сканер.
- `/unwatch ROSN` - удалить тикер из автоматического сканера.
- `/watchlist` - показать тикеры автосканера.
- `/mute ROSN 60` - поставить автосигналы по тикеру на паузу.

Все ответы бота написаны на русском языке. Сигналы являются аналитикой по данным, а не инвестиционной рекомендацией.

## Переменные окружения

Создайте локальный `.env` по примеру `.env.example`:

```bash
TELEGRAM_BOT_TOKEN=...
MOEX_API_KEY=...
MOEX_SIGNAL_DB=signals.sqlite3
SCANNER_INTERVAL_SECONDS=60
```

`MOEX_API_KEY` можно заменить на `MOEXALGO_API_KEY`. `MOEX_SIGNAL_DB` хранит watchlist и дедупликацию автосигналов.

## Запуск

Из каталога проекта:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
python -m moex_signal_bot
```

Для локальной проверки без Telegram:

```bash
python -m moex_signal_bot --dry-run "/help"
python -m moex_signal_bot --dry-run "/flow ROSN 7"
python -m moex_signal_bot --dry-run "/signal ROSN"
```

Если используется локальный checkout `moexalgo`, можно запускать без публикации пакета так:

```bash
PYTHONPATH=src:/home/elijah/Desktop/moexalgo python3 -m moex_signal_bot --dry-run "/help"
```

## Логика сигналов

Бот считает покупательную/продавцовую силу как:

```text
buy_power = val_b / (val_b + val_s)
sell_power = val_s / (val_b + val_s)
imbalance = (val_b - val_s) / (val_b + val_s)
```

Базовые состояния:

- `Давление продавцов`: цена падает, дисбаланс сделок отрицательный.
- `Абсорбция продаж`: цена падает, но поток сделок положительный.
- `Бычий разворот`: цена растет вместе с положительным потоком.
- `Слабый отскок`: цена растет, но поток не подтверждает покупателей.
- `Нейтрально`: явного преимущества нет.

Автосканер отправляет сигнал только если скоринг достаточно сильный, тикер находится в watchlist, сигнал еще не отправлялся этому чату, и тикер не поставлен на паузу.

## Docker

```bash
docker build -t moex-signal-bot .
docker run --rm --env-file .env -v moex-signal-data:/data moex-signal-bot
```

## Проверка

```bash
python3 -m pytest -q
ruff check .
ruff format --check .
pre-commit run --all-files
```

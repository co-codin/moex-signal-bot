# MOEX Signal Bot

Русскоязычный Telegram-бот для анализа MOEX/ALGOPACK по тикерам акций.

## Возможности

- `/quote ROSN` - краткая котировка.
- `/flow ROSN 7` - покупательная и продавцовая сила по `TradeStats`.
- `/strategy ROSN` - сценарий: давление продавцов, абсорбция, разворот или нейтрально.
- `/book ROSN` - последние метрики стакана по `OBStats`.
- `/orders ROSN` - давление выставленных и снятых заявок по `OrderStats`.
- `/alerts ROSN` - события `MegaAlert`.

Все ответы бота написаны на русском языке. Сигналы являются аналитикой по данным, а не инвестиционной рекомендацией.

## Переменные окружения

Создайте локальный `.env` по примеру `.env.example`:

```bash
TELEGRAM_BOT_TOKEN=...
MOEX_API_KEY=...
```

`MOEX_API_KEY` можно заменить на `MOEXALGO_API_KEY`.

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

## Проверка

```bash
python3 -m pytest -q
```

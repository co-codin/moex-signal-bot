# MOEX Signal Bot

This file governs the whole repository.

## Project Rules

- Keep all Telegram responses in Russian.
- Не коммитьте реальные токены, JWT, `.env`, local SQLite databases, or live chat/user data.
- Treat bot output as analytics, not investment advice. Keep the disclaimer in signal-style responses.
- Prefer small, test-backed changes in `src/moex_signal_bot`.
- Preserve direct Telegram Bot API polling unless a task explicitly asks for another framework.

## Market Data

- Use MOEX/ALGOPACK fields consistently:
  - `TradeStats`: `val_b`, `val_s`, `pr_open`, `pr_close`, `tradedate`, `tradetime`.
  - `OrderStats`: `put_val_b`, `put_val_s`, `cancel_val_b`, `cancel_val_s`.
  - `OBStats`: `imbalance_val`, `imbalance_val_bbo`, `spread_bbo`.
  - `MegaAlert`: `alert_type` and price/value fields when present.
- Normalize tickers to uppercase.
- Keep scanner deduplication conservative so automatic Telegram sends do not spam users.

## Verification

Run these before claiming completion after code changes:

```bash
python3 -m pytest -q
ruff check .
ruff format --check .
```

For packaging changes, also run a Docker build when Docker is available:

```bash
docker build -t moex-signal-bot .
```

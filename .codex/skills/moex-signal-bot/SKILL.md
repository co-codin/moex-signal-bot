---
name: moex-signal-bot
description: Work on this Russian MOEX Telegram signal bot. Use when modifying bot commands, ALGOPACK/MOEX data handling, signal scoring, watchlist scanning, Telegram auto-alerts, Docker packaging, or repository verification.
---

# MOEX Signal Bot

## Overview

Use this skill to keep changes aligned with the bot's domain and operating guardrails: Russian Telegram output, MOEX/ALGOPACK data, conservative auto-alerts, and no committed secrets.

## Workflow

1. Read `AGENTS.md`, `README.md`, and the relevant modules before editing.
2. Add or update focused tests before changing signal scoring, scanner persistence, command parsing, or runtime behavior.
3. Keep user-facing bot text in Russian.
4. Normalize ticker symbols to uppercase at boundaries.
5. Avoid storing or printing real Telegram tokens, MOEX JWTs, chat data, or `.env` values.
6. Run `python3 -m pytest -q`, `ruff check .`, and `ruff format --check .` before reporting completion.

## Signal Rules

- Treat signals as analytics, not investment recommendations.
- Prefer transparent factors over opaque scoring: price change, buy/sell flow, order pressure, book imbalance, and MegaAlert context.
- Automatic scanner sends must be deduped by chat, ticker, signal code, and signal key.
- Muted watchlist items must not send automatic signals.
- Do not broaden scanner scope to live trading or order placement without an explicit user request and separate safety review.

## Files

- `src/moex_signal_bot/bot.py`: command parsing and handlers.
- `src/moex_signal_bot/scanner.py`: signal scoring and auto-send scanner.
- `src/moex_signal_bot/storage.py`: SQLite watchlist and dedup persistence.
- `src/moex_signal_bot/formatters.py`: Russian response formatting.
- `tests/`: behavior and regression coverage.

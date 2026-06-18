# Web Admin Access Control Design

## Goal

Build a browser admin panel that controls which Telegram users can use the MOEX Signal Bot.

## Architecture

The admin panel is a small server-rendered FastAPI service inside the existing Python package. It uses the same PostgreSQL database as the bot and scanner, so access decisions are shared across polling, manual commands, and automatic scanner sends.

The bot remains open by default. Access enforcement activates only when `ACCESS_CONTROL_ENABLED=true`, which prevents accidental lockouts during existing deployments.

## Components

- `src/moex_signal_bot/access_control.py`: access status model, environment parsing, user metadata extraction, and authorization helpers.
- `src/moex_signal_bot/storage.py`: PostgreSQL `telegram_users` table and methods for recording users, listing users, and changing status.
- `src/moex_signal_bot/memory_storage.py`: test-friendly in-memory implementation of the same access-control methods.
- `src/moex_signal_bot/admin_web.py`: FastAPI app with HTTP Basic authentication and server-rendered HTML.
- `src/moex_signal_bot/__main__.py`: `--admin-web` command and bot/scanner access enforcement wiring.

## Data Model

`telegram_users` stores:

- `chat_id BIGINT PRIMARY KEY`
- Telegram identity fields: `username`, `first_name`, `last_name`
- `status TEXT NOT NULL DEFAULT 'pending'`
- `note TEXT NOT NULL DEFAULT ''`
- timestamps: `first_seen_at`, `last_seen_at`

Allowed statuses are `allowed`, `blocked`, and `pending`.

## Access Rules

- If `ACCESS_CONTROL_ENABLED` is not enabled, all users can use the bot.
- If enabled, only users with status `allowed` can run normal bot commands.
- Chat IDs from `ADMIN_CHAT_IDS` are always allowed and are recorded as `allowed`.
- Unknown users are recorded as `pending` and receive a Russian access-denied message with their `chat_id`.
- Blocked and pending users are skipped by scanner workers.

## Web UI

The web UI is Russian-language and intentionally simple:

- dashboard counters for allowed, pending, and blocked users;
- filterable user table;
- one-click status update forms;
- note editing per user.

Authentication uses HTTP Basic with `ADMIN_WEB_USERNAME` and `ADMIN_WEB_PASSWORD`.

## Deployment

Docker Compose adds an `admin-web` service that runs:

```bash
python -m moex_signal_bot --admin-web
```

The service listens on `ADMIN_WEB_HOST`/`ADMIN_WEB_PORT` and exposes port `8080` by default.

## Testing

Tests cover:

- access-control parsing and open-by-default behavior;
- user recording and status changes in memory storage;
- bot command gating before MOEX provider calls;
- scanner skipping non-allowed chats;
- web admin auth, dashboard rendering, and status updates.

## Risks

- HTTP Basic should be placed behind HTTPS or a private network in production.
- Access control depends on correctly configuring `ACCESS_CONTROL_ENABLED=true`.
- The panel controls Telegram `chat_id`, not broader identity verification.

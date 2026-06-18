# Web Admin Access Control Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a browser admin panel that lets the owner allow, block, and review Telegram users of the MOEX Signal Bot.

**Architecture:** Add a shared access-control layer backed by PostgreSQL, gate manual bot commands and scanner sends through it, and expose status management through a small FastAPI server-rendered web UI. Keep access control disabled by default to preserve current deployments.

**Tech Stack:** Python 3.12, FastAPI, Starlette TestClient, PostgreSQL via existing psycopg store, existing Docker Compose.

---

### Task 1: Access-Control Domain And Store Tests

**Files:**
- Create: `src/moex_signal_bot/access_control.py`
- Modify: `src/moex_signal_bot/storage.py`
- Modify: `src/moex_signal_bot/memory_storage.py`
- Test: `tests/test_access_control.py`

- [ ] **Step 1: Write failing tests**

Create tests for `AccessControlSettings`, in-memory user recording, admin allow-list behavior, and status transitions.

- [ ] **Step 2: Run red tests**

Run: `python3 -m pytest tests/test_access_control.py -q`

Expected: fails because `moex_signal_bot.access_control` does not exist.

- [ ] **Step 3: Implement minimal domain and store methods**

Add `TelegramUser`, `AccessControlSettings`, status normalization, `access_settings_from_env`, and store methods:

- `record_telegram_user`
- `get_telegram_user`
- `list_telegram_users`
- `set_telegram_user_status`
- `set_telegram_user_note`
- `is_chat_allowed`

- [ ] **Step 4: Run green tests**

Run: `python3 -m pytest tests/test_access_control.py -q`

Expected: pass.

### Task 2: Bot And Scanner Enforcement

**Files:**
- Modify: `src/moex_signal_bot/__main__.py`
- Modify: `src/moex_signal_bot/scanner_queue.py`
- Test: `tests/test_bot_access_control.py`
- Test: `tests/test_scanner_queue.py`

- [ ] **Step 1: Write failing tests**

Add tests that a pending user is blocked before provider calls, an admin/allowed user can run commands, and scanner jobs skip pending or blocked chats.

- [ ] **Step 2: Run red tests**

Run: `python3 -m pytest tests/test_bot_access_control.py tests/test_scanner_queue.py -q`

Expected: access-gating tests fail.

- [ ] **Step 3: Implement enforcement**

Add a dispatch helper in `__main__.py` that records Telegram users and checks access before `handle_command`. Add scanner filtering so non-allowed users receive no automatic signal.

- [ ] **Step 4: Run green tests**

Run: `python3 -m pytest tests/test_bot_access_control.py tests/test_scanner_queue.py -q`

Expected: pass.

### Task 3: Web Admin UI

**Files:**
- Create: `src/moex_signal_bot/admin_web.py`
- Modify: `src/moex_signal_bot/__main__.py`
- Test: `tests/test_admin_web.py`

- [ ] **Step 1: Write failing tests**

Cover HTTP Basic rejection, dashboard rendering, status update, and note update.

- [ ] **Step 2: Run red tests**

Run: `python3 -m pytest tests/test_admin_web.py -q`

Expected: fails because `admin_web` does not exist.

- [ ] **Step 3: Implement FastAPI app**

Add `create_admin_app`, `/`, `/users/{chat_id}/status`, and `/users/{chat_id}/note`. Render plain HTML with Russian labels and CSRF-free simple forms suitable for private admin use.

- [ ] **Step 4: Run green tests**

Run: `python3 -m pytest tests/test_admin_web.py -q`

Expected: pass.

### Task 4: Packaging, Compose, And Docs

**Files:**
- Modify: `pyproject.toml`
- Modify: `docker-compose.yml`
- Modify: `Makefile`
- Modify: `.env.example`
- Modify: `README.md`
- Test: `tests/test_tooling_files.py`

- [ ] **Step 1: Write failing checks**

Extend tooling tests to require FastAPI dependency, admin web compose service, admin env vars, and README admin instructions.

- [ ] **Step 2: Run red tests**

Run: `python3 -m pytest tests/test_tooling_files.py -q`

Expected: fails on missing admin web wiring.

- [ ] **Step 3: Wire deployment files**

Add `fastapi`, `uvicorn[standard]`, and test dependency support. Add `admin-web` Compose service and `make admin-web`. Document setup and security notes.

- [ ] **Step 4: Run green tests**

Run: `python3 -m pytest tests/test_tooling_files.py -q`

Expected: pass.

### Task 5: Full Verification And Commit

**Files:**
- All changed files

- [ ] **Step 1: Run targeted tests**

Run all new and touched tests:

```bash
python3 -m pytest tests/test_access_control.py tests/test_bot_access_control.py tests/test_admin_web.py tests/test_scanner_queue.py tests/test_tooling_files.py -q
```

- [ ] **Step 2: Run repository verification**

```bash
python3 -m pytest -q
ruff check .
ruff format --check .
git diff --check
```

- [ ] **Step 3: Build Docker image if Docker is available**

```bash
docker build --pull=false -t moex-signal-bot .
```

- [ ] **Step 4: Commit**

Use a Lore-style commit message describing why access control was added and what was tested.

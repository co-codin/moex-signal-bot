# MOEX Flow Pro Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add command-driven MVPs for Scanner Pro, Watchlist Pro, FUTOI, heatmap, stats, portfolio risk, MegaAlert feed, digest, and channel export.

**Architecture:** Keep Telegram polling and current provider abstractions. Add focused analytics modules and extend persistent storage for user settings and portfolio tickers. Keep all user-visible bot output in Russian.

**Tech Stack:** Python 3.12, `moexalgo`, `httpx`, PostgreSQL, pytest, Ruff.

---

## File Structure

- Modify `src/moex_signal_bot/signals.py`: add richer signal metadata and daily outcome helpers.
- Modify `src/moex_signal_bot/scanner.py`: add alert-type derivation and setting-aware automatic sends.
- Create `src/moex_signal_bot/analytics.py`: heatmap, MegaAlert feed, digest, and historical stats helpers.
- Create `src/moex_signal_bot/futoi.py`: FUTOI aggregation helpers.
- Create `src/moex_signal_bot/portfolio.py`: portfolio risk aggregation helpers.
- Modify `src/moex_signal_bot/storage.py`: add settings and portfolio tables.
- Modify `src/moex_signal_bot/moex_provider.py`: add FUTOI access.
- Modify `src/moex_signal_bot/bot.py`: parse and handle new commands.
- Modify `src/moex_signal_bot/formatters.py`: add Russian output formatters.
- Modify `README.md` and `.env.example`: document new commands and config knobs.
- Add or update tests under `tests/`.

### Task 1: Storage Settings And Portfolio

**Files:**
- Modify: `src/moex_signal_bot/storage.py`
- Test: `tests/test_watchlist_store.py`

- [ ] **Step 1: Write failing tests**

```python
def test_store_persists_chat_settings(tmp_path):
    store = InMemoryWatchlistStore()
    try:
        store.set_min_score(42, 75)
        store.set_quiet_hours(42, "23:00", "07:00")
        store.set_alert_types(42, ("sell_pressure", "absorption"))
        settings = store.get_settings(42)
        assert settings.min_score == 75
        assert settings.quiet_start == "23:00"
        assert settings.quiet_end == "07:00"
        assert settings.alert_types == ("absorption", "sell_pressure")
    finally:
        store.close()


def test_store_persists_portfolio(tmp_path):
    store = InMemoryWatchlistStore()
    try:
        store.add_portfolio_ticker(42, "rosn")
        store.add_portfolio_ticker(42, "SBER")
        assert store.list_portfolio(42) == ["ROSN", "SBER"]
        assert store.remove_portfolio_ticker(42, "ROSN") is True
        assert store.list_portfolio(42) == ["SBER"]
    finally:
        store.close()
```

- [ ] **Step 2: Verify tests fail**

Run: `python3 -m pytest tests/test_watchlist_store.py -q`
Expected: FAIL because settings and portfolio APIs are missing.

- [ ] **Step 3: Implement storage APIs and migrations**

Add `ChatSettings`, `get_settings`, `set_min_score`, `set_quiet_hours`, `set_alert_types`, `add_portfolio_ticker`, `remove_portfolio_ticker`, and `list_portfolio`.

- [ ] **Step 4: Verify storage tests pass**

Run: `python3 -m pytest tests/test_watchlist_store.py -q`
Expected: PASS.

### Task 2: Analytics Modules

**Files:**
- Create: `src/moex_signal_bot/analytics.py`
- Create: `src/moex_signal_bot/futoi.py`
- Create: `src/moex_signal_bot/portfolio.py`
- Test: `tests/test_pro_features.py`

- [ ] **Step 1: Write failing tests**

Cover heatmap ranking, MegaAlert summaries, stats outcomes, FUTOI summaries, and portfolio risk aggregation using in-memory row dictionaries.

- [ ] **Step 2: Verify tests fail**

Run: `python3 -m pytest tests/test_pro_features.py -q`
Expected: FAIL because modules are missing.

- [ ] **Step 3: Implement minimal helpers**

Implement pure functions that operate on existing `SignalReport` objects and row dictionaries.

- [ ] **Step 4: Verify tests pass**

Run: `python3 -m pytest tests/test_pro_features.py -q`
Expected: PASS.

### Task 3: Bot Commands And Formatters

**Files:**
- Modify: `src/moex_signal_bot/bot.py`
- Modify: `src/moex_signal_bot/formatters.py`
- Modify: `src/moex_signal_bot/moex_provider.py`
- Test: `tests/test_bot_commands.py`

- [ ] **Step 1: Write failing command tests**

Add tests for `/settings`, `/score`, `/quiet`, `/types`, `/heatmap`, `/mega`, `/digest`, `/futoi`, `/stats`, portfolio commands, and `/channel_signal`.

- [ ] **Step 2: Verify tests fail**

Run: `python3 -m pytest tests/test_bot_commands.py -q`
Expected: FAIL because commands are unsupported.

- [ ] **Step 3: Implement parser, handlers, provider FUTOI method, and formatters**

Keep output concise, Russian, and explicit when data is unavailable.

- [ ] **Step 4: Verify command tests pass**

Run: `python3 -m pytest tests/test_bot_commands.py -q`
Expected: PASS.

### Task 4: Scanner Pro Filtering

**Files:**
- Modify: `src/moex_signal_bot/signals.py`
- Modify: `src/moex_signal_bot/scanner.py`
- Test: `tests/test_scanner.py`

- [ ] **Step 1: Write failing scanner tests**

Cover per-chat min score, alert-type filters, and quiet hours preventing automatic sends.

- [ ] **Step 2: Verify tests fail**

Run: `python3 -m pytest tests/test_scanner.py -q`
Expected: FAIL because scanner ignores settings.

- [ ] **Step 3: Implement alert types and setting-aware sends**

Add `alert_type` to `SignalReport`, derive it in `build_signal_report`, and check store settings in `run_scan_once`.

- [ ] **Step 4: Verify scanner tests pass**

Run: `python3 -m pytest tests/test_scanner.py -q`
Expected: PASS.

### Task 5: Documentation And Full Verification

**Files:**
- Modify: `README.md`
- Modify: `.env.example`

- [ ] **Step 1: Document new commands and env knobs**

Document `DEFAULT_SCAN_TICKERS`, scanner settings, FUTOI, heatmap, portfolio, and digest commands.

- [ ] **Step 2: Run full verification**

Run:

```bash
python3 -m pytest -q
ruff check .
ruff format --check .
docker build -t moex-signal-bot . || true
```

Expected: tests and Ruff pass. Docker result is reported with evidence if Docker is unavailable.

## Self-Review

- Spec coverage: every approved feature has a command or helper in the tasks.
- Placeholder scan: no placeholder implementation steps remain.
- Type consistency: storage settings feed scanner filters; provider FUTOI feeds FUTOI formatter; analytics helpers consume `SignalReport` and raw MOEX rows.

# MOEX Flow Pro Design

## Goal

Expand the Russian Telegram bot from a single-stock signal helper into a practical MOEX Flow Pro assistant that can scan watchlists, explain market pressure, monitor portfolios, summarize MegaAlerts, expose futures open interest, produce basic historical statistics, and format channel-ready alerts.

## Product Scope

The first implementation pass ships command-driven MVPs for all approved business ideas while preserving the existing polling bot and persistent storage model. Automatic sends remain conservative: only watchlist scanner messages are sent without a direct user command, and they continue to use score thresholds, mutes, and deduplication.

## Features

- Scanner Pro: classify signals into richer alert types such as sell pressure, absorption, bullish reversal, MegaAlert cluster, breakdown, and reclaim.
- Watchlist Pro: store per-chat settings for minimum score, quiet hours, and alert type filters.
- FUTOI futures module: read MOEX FUTOI rows through `moexalgo` and summarize long/short open interest by client group.
- Market heatmap: rank provided or default tickers by score, buy pressure, sell pressure, MegaAlert count, and absorption candidates.
- Backtest/statistics MVP: use historical TradeStats daily summaries to count what happened after similar flow states.
- Portfolio risk monitor: persist user portfolio tickers and show combined risk states.
- MegaAlert feed: summarize latest abnormal activity globally for a ticker list or for one ticker.
- Daily digest: concise summary of market leaders, pressure, alerts, and watchlist context.
- Channel export mode: short Russian signal text suitable for Telegram channel reposts.

## Architecture

Keep `bot.py` as the command router and move new calculations into focused modules. `analytics.py` owns reusable ranking/statistics helpers. `futoi.py` owns futures open-interest summaries. `portfolio.py` owns portfolio risk aggregation. `storage.py` remains the PostgreSQL boundary for per-user state. `formatters.py` remains the Russian presentation layer.

## Data Sources

The implementation uses the existing `MoexProvider` for TradeStats, OrderStats, OBStats, MegaAlert, and quote data. It extends the provider with `futoi(ticker, start, end)` and keeps APIM tokens in environment variables only. No tokens, chat data, or PostgreSQL dumps are committed.

## Commands

- `/settings`, `/score N`, `/quiet START END`, `/types TYPE...`
- `/heatmap [TICKER...]`
- `/mega [TICKER...]`
- `/digest [TICKER...]`
- `/futoi FUTURE`
- `/stats TICKER [DAYS]`
- `/portfolio_add TICKER`, `/portfolio_remove TICKER`, `/portfolio`, `/portfolio_risk`
- `/channel_signal TICKER`

## Error Handling

Unavailable datasets are reported clearly in Russian. Commands clamp user-provided numbers to safe ranges. Scanner sends stay deduplicated and honor quiet hours, mutes, score thresholds, and alert-type filters.

## Testing

Tests cover command parsing, formatter output, storage behavior, scanner setting filters, heatmap ranking, MegaAlert summaries, FUTOI aggregation, portfolio risk aggregation, and stats classification. Verification remains:

```bash
python3 -m pytest -q
ruff check .
ruff format --check .
```

Docker build is run when Docker is available.

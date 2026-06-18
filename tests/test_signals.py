from moex_signal_bot.signals import (
    classify_trade_state,
    summarize_daily_flow,
    summarize_flow,
)


def test_summarize_flow_calculates_buy_sell_power_and_net_value():
    rows = [
        {"val_b": 70_000_000, "val_s": 30_000_000, "vol_b": 200, "vol_s": 100, "trades_b": 20, "trades_s": 10},
        {"val_b": 10_000_000, "val_s": 90_000_000, "vol_b": 20, "vol_s": 180, "trades_b": 3, "trades_s": 27},
    ]

    summary = summarize_flow(rows)

    assert summary.buy_value == 80_000_000
    assert summary.sell_value == 120_000_000
    assert summary.net_value == -40_000_000
    assert summary.buy_power == 0.4
    assert summary.sell_power == 0.6
    assert summary.imbalance == -0.2
    assert summary.buy_volume == 220
    assert summary.sell_volume == 280
    assert summary.buy_trades == 23
    assert summary.sell_trades == 37


def test_summarize_daily_flow_groups_rows_and_keeps_open_close():
    rows = [
        {"tradedate": "2026-06-17", "tradetime": "10:00:00", "pr_open": 340, "pr_close": 338, "val_b": 10, "val_s": 20},
        {"tradedate": "2026-06-17", "tradetime": "10:05:00", "pr_open": 338, "pr_close": 337, "val_b": 30, "val_s": 10},
        {"tradedate": "2026-06-18", "tradetime": "10:00:00", "pr_open": 336, "pr_close": 329, "val_b": 20, "val_s": 80},
    ]

    days = summarize_daily_flow(rows)

    assert [day.date for day in days] == ["2026-06-17", "2026-06-18"]
    assert days[0].open_price == 340
    assert days[0].close_price == 337
    assert days[0].flow.net_value == 10
    assert days[1].open_price == 336
    assert days[1].close_price == 329
    assert days[1].flow.sell_power == 0.8


def test_classify_trade_state_detects_selling_absorption_and_reversal():
    assert classify_trade_state(price_change=-2.4, flow_imbalance=-0.18).code == "sell_pressure"
    assert classify_trade_state(price_change=-2.4, flow_imbalance=0.08).code == "absorption"
    assert classify_trade_state(price_change=1.2, flow_imbalance=0.16).code == "bullish_reversal"
    assert classify_trade_state(price_change=0.2, flow_imbalance=0.01).code == "neutral"

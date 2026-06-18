from moex_signal_bot.analytics import build_flow_statistics, build_heatmap, summarize_mega_alerts
from moex_signal_bot.futoi import summarize_futoi
from moex_signal_bot.portfolio import build_portfolio_risk
from moex_signal_bot.scanner import build_signal_report


def test_build_heatmap_ranks_reports_and_keeps_alert_context():
    sell_report = build_signal_report(
        "rosn",
        tradestats=[
            {
                "tradedate": "2026-06-18",
                "tradetime": "10:00:00",
                "pr_open": 336,
                "pr_close": 328,
                "val_b": 20_000_000,
                "val_s": 80_000_000,
            }
        ],
        orderstats=[{"put_val_b": 30_000_000, "put_val_s": 120_000_000}],
        obstats=[{"tradedate": "2026-06-18", "tradetime": "10:00:00", "imbalance_val_bbo": -0.2}],
        alerts=[
            {"alert_type": "pr_low_min"},
            {"alert_type": "pr_low_min"},
        ],
    )
    neutral_report = build_signal_report("sber", tradestats=[], orderstats=[], obstats=[], alerts=[])

    heatmap = build_heatmap([neutral_report, sell_report])

    assert [entry.ticker for entry in heatmap] == ["ROSN", "SBER"]
    assert heatmap[0].score >= 80
    assert heatmap[0].alert_type in {"sell_pressure", "breakdown", "megaalert_cluster"}
    assert heatmap[0].megaalerts == 2


def test_summarize_mega_alerts_counts_types_and_latest_rows():
    summary = summarize_mega_alerts(
        "ROSN",
        [
            {"tradedate": "2026-06-18", "tradetime": "10:00:00", "alert_type": "pr_low_min", "value": 329},
            {"tradedate": "2026-06-18", "tradetime": "10:05:00", "alert_type": "pr_low_min", "value": 328},
            {"tradedate": "2026-06-18", "tradetime": "10:06:00", "alert_type": "vol_99_9_pctl", "value": 10},
        ],
    )

    assert summary.ticker == "ROSN"
    assert summary.total == 3
    assert summary.by_type["pr_low_min"] == 2
    assert summary.latest[0]["tradetime"] == "10:06:00"


def test_build_flow_statistics_counts_next_day_outcomes_for_latest_state():
    stats = build_flow_statistics(
        "ROSN",
        [
            {
                "tradedate": "2026-06-15",
                "tradetime": "10:00:00",
                "pr_open": 100,
                "pr_close": 98,
                "val_b": 20,
                "val_s": 80,
            },
            {
                "tradedate": "2026-06-16",
                "tradetime": "10:00:00",
                "pr_open": 98,
                "pr_close": 97,
                "val_b": 20,
                "val_s": 80,
            },
            {
                "tradedate": "2026-06-17",
                "tradetime": "10:00:00",
                "pr_open": 97,
                "pr_close": 96,
                "val_b": 80,
                "val_s": 20,
            },
            {
                "tradedate": "2026-06-18",
                "tradetime": "10:00:00",
                "pr_open": 96,
                "pr_close": 95,
                "val_b": 80,
                "val_s": 20,
            },
        ],
    )

    assert stats.ticker == "ROSN"
    assert stats.state_code == "absorption"
    assert stats.samples == 1
    assert stats.down_after == 1
    assert stats.up_after == 0


def test_summarize_futoi_aggregates_latest_open_interest_rows():
    summary = summarize_futoi(
        "SBERF",
        [
            {"tradedate": "2026-06-18", "tradetime": "10:00:00", "clgroup": "phys", "pos_long": 100, "pos_short": 40},
            {"tradedate": "2026-06-18", "tradetime": "10:00:00", "clgroup": "jur", "pos_long": 80, "pos_short": 120},
            {"tradedate": "2026-06-18", "tradetime": "09:00:00", "clgroup": "phys", "pos_long": 50, "pos_short": 60},
        ],
    )

    assert summary.ticker == "SBERF"
    assert summary.total_long == 180
    assert summary.total_short == 160
    assert summary.net == 20
    assert summary.groups[0].client_group == "phys"


def test_build_portfolio_risk_summarizes_risky_reports():
    risky = build_signal_report(
        "tatn",
        tradestats=[
            {
                "tradedate": "2026-06-18",
                "tradetime": "10:00:00",
                "pr_open": 540,
                "pr_close": 528,
                "val_b": 20_000_000,
                "val_s": 80_000_000,
            }
        ],
        orderstats=[{"put_val_b": 30_000_000, "put_val_s": 120_000_000}],
        obstats=[{"tradedate": "2026-06-18", "tradetime": "10:00:00", "imbalance_val_bbo": -0.2}],
        alerts=[],
    )
    neutral = build_signal_report("sber", tradestats=[], orderstats=[], obstats=[], alerts=[])

    risk = build_portfolio_risk([neutral, risky])

    assert risk.total == 2
    assert risk.risky_count == 1
    assert risk.risky_tickers == ("TATN",)

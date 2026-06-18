from moex_signal_bot.formatters import format_flow_report, format_strategy_report
from moex_signal_bot.signals import DayFlow, FlowSummary, TradeState


def test_format_flow_report_is_russian_and_contains_daily_table():
    day = DayFlow(
        date="2026-06-18",
        first_time="10:00:00",
        last_time="10:25:00",
        open_price=336.2,
        close_price=327.05,
        buckets=42,
        flow=FlowSummary(
            buy_value=585_700_000,
            sell_value=575_900_000,
            buy_volume=1,
            sell_volume=1,
            buy_trades=1,
            sell_trades=1,
        ),
    )

    text = format_flow_report("ROSN", [day])

    assert "Покупательная сила ROSN" in text
    assert "2026-06-18" in text
    assert "50.4%" in text
    assert "49.6%" in text
    assert "+9.8 млн ₽" in text


def test_format_strategy_report_includes_risk_language_in_russian():
    state = TradeState(
        code="absorption",
        title="Абсорбция продаж",
        description="Цена падает, но покупатели забирают часть продаж.",
        action="Ждать подтверждение выше VWAP.",
    )

    text = format_strategy_report("ROSN", state, support=327.0, reclaim=337.0)

    assert "Сигнал по ROSN" in text
    assert "Абсорбция продаж" in text
    assert "Поддержка" in text
    assert "Возврат контроля" in text
    assert "не является инвестиционной рекомендацией" in text

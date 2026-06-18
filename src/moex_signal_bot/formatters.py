from __future__ import annotations

from .signals import DayFlow, FlowSummary, SignalReport, TradeState
from .storage import WatchItem


def format_percent(value: float) -> str:
    return f"{value * 100:.1f}%"


def format_mrub(value: float, *, signed: bool = False) -> str:
    sign = "+" if signed and value >= 0 else ""
    return f"{sign}{value / 1_000_000:.1f} млн ₽"


def format_price(value: float | None) -> str:
    return "н/д" if value is None else f"{value:.2f}"


def format_flow_report(ticker: str, days: list[DayFlow]) -> str:
    if not days:
        return f"Нет данных TradeStats по {ticker} за выбранный период."

    total = _sum_flows(day.flow for day in days)
    lines = [
        f"Покупательная сила {ticker}",
        "",
        f"Итог за период: Покупатели {format_percent(total.buy_power)}, Продавцы {format_percent(total.sell_power)}.",
        f"Чистый поток: {format_mrub(total.net_value, signed=True)}.",
        "",
        "Дни:",
    ]
    for day in days:
        lines.append(
            " | ".join(
                [
                    day.date,
                    f"{format_price(day.open_price)} -> {format_price(day.close_price)}",
                    f"покупатели {format_percent(day.flow.buy_power)}",
                    f"продавцы {format_percent(day.flow.sell_power)}",
                    format_mrub(day.flow.net_value, signed=True),
                ]
            )
        )
    return "\n".join(lines)


def format_strategy_report(ticker: str, state: TradeState, *, support: float | None, reclaim: float | None) -> str:
    return "\n".join(
        [
            f"Сигнал по {ticker}",
            f"Состояние: {state.title}",
            state.description,
            "",
            f"План: {state.action}",
            f"Поддержка: {format_price(support)}",
            f"Возврат контроля: {format_price(reclaim)}",
            "",
            "Это аналитический сигнал, не является инвестиционной рекомендацией.",
        ]
    )


def format_signal_report(report: SignalReport, *, automatic: bool = False) -> str:
    title = "Автосигнал" if automatic else "Сигнал"
    lines = [
        f"{title} {report.ticker}",
        f"Сила: {report.score}/100",
        f"Состояние: {report.state.title}",
        f"Направление: {_format_direction(report.direction)}",
        f"Время: {_format_signal_time(report)}",
        f"Цена за день: {report.price_change:+.2f}%",
        f"Покупатели: {format_percent(report.buy_power)}, продавцы: {format_percent(report.sell_power)}",
        f"Поддержка: {format_price(report.support)}",
        f"Возврат контроля: {format_price(report.reclaim)}",
        "",
        "Причины:",
    ]
    lines.extend(f"- {reason}" for reason in report.reasons[:6])
    lines.extend(
        [
            "",
            f"План: {report.state.action}",
            "Это аналитический сигнал, не является инвестиционной рекомендацией.",
        ]
    )
    return "\n".join(lines)


def format_scan_results(reports: list[SignalReport]) -> str:
    if not reports:
        return "Сканер: нет тикеров для проверки."

    lines = ["Сканер", ""]
    for report in sorted(reports, key=lambda item: item.score, reverse=True):
        lines.append(
            " | ".join(
                [
                    report.ticker,
                    f"{report.score}/100",
                    report.state.title,
                    _format_direction(report.direction),
                ]
            )
        )
    lines.extend(["", "Сильные автосигналы отправляются только по watchlist и с дедупликацией."])
    return "\n".join(lines)


def format_watchlist(items: list[WatchItem]) -> str:
    if not items:
        return "Watchlist пуст. Добавьте тикер командой /watch ROSN 15m."
    lines = ["Watchlist"]
    for item in items:
        muted = f", пауза до {item.muted_until:%Y-%m-%d %H:%M UTC}" if item.muted_until else ""
        lines.append(f"{item.ticker}: каждые {item.interval_minutes} мин{muted}")
    return "\n".join(lines)


def format_full_report(
    ticker: str,
    *,
    quote: str,
    signal: str,
    book: str,
    orders: str,
    alerts: str,
) -> str:
    return "\n\n".join(
        [
            f"Полный отчет {ticker}",
            quote,
            signal,
            book,
            orders,
            alerts,
        ]
    )


def format_quote_report(ticker: str, quote: dict) -> str:
    return "\n".join(
        [
            f"Котировка {ticker}",
            f"Последняя цена: {format_price(_optional_float(quote.get('last')))}",
            f"Изменение к предыдущей: {_format_optional_percent(quote.get('last_to_prev_pct'))}",
            f"Время: {quote.get('time') or 'н/д'}",
        ]
    )


def format_help() -> str:
    return "\n".join(
        [
            "Команды на русском:",
            "/quote ROSN - текущая котировка",
            "/flow ROSN 7 - покупательная/продавцовая сила за N дней",
            "/strategy ROSN - торговый сценарий по потоку сделок",
            "/signal ROSN - скоринговый сигнал по TradeStats, OrderStats, OBStats и MegaAlert",
            "/scan ROSN SBER - быстрый сканер по нескольким тикерам",
            "/full ROSN - полный отчет по тикеру",
            "/book ROSN - краткий статус стакана",
            "/orders ROSN - давление выставленных и снятых заявок",
            "/alerts ROSN - аномальные события ALGOPACK",
            "/watch ROSN 15m - добавить тикер в автосканер",
            "/unwatch ROSN - удалить тикер из автосканера",
            "/watchlist - показать автосканер",
            "/mute ROSN 60 - поставить автосигналы на паузу на N минут",
            "",
            "По умолчанию тикеры читаются на рынке акций MOEX TQBR.",
        ]
    )


def _sum_flows(flows) -> FlowSummary:
    buy_value = sell_value = 0.0
    buy_volume = sell_volume = 0.0
    buy_trades = sell_trades = 0.0
    for flow in flows:
        buy_value += flow.buy_value
        sell_value += flow.sell_value
        buy_volume += flow.buy_volume
        sell_volume += flow.sell_volume
        buy_trades += flow.buy_trades
        sell_trades += flow.sell_trades
    return FlowSummary(
        buy_value=buy_value,
        sell_value=sell_value,
        buy_volume=buy_volume,
        sell_volume=sell_volume,
        buy_trades=buy_trades,
        sell_trades=sell_trades,
    )


def _optional_float(value) -> float | None:
    return None if value is None else float(value)


def _format_optional_percent(value) -> str:
    return "н/д" if value is None else f"{float(value):+.2f}%"


def _format_direction(direction: str) -> str:
    return {
        "short": "риск снижения",
        "watch_long": "наблюдать лонг после подтверждения",
        "long": "риск роста",
        "caution": "осторожно, отскок слабый",
        "neutral": "нейтрально",
    }.get(direction, direction)


def _format_signal_time(report: SignalReport) -> str:
    if not report.latest_date:
        return "н/д"
    if not report.latest_time:
        return report.latest_date
    return f"{report.latest_date} {report.latest_time}"

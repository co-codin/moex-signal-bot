from __future__ import annotations

from .analytics import FlowStatistics, HeatmapEntry, MegaAlertSummary
from .commands import COMMAND_SPECS
from .futoi import FutoiSummary
from .portfolio import PortfolioRisk
from .signals import DayFlow, FlowSummary, SignalReport, TradeState
from .storage import ALLOWED_ALERT_TYPES, ChatSettings, WatchItem


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


def format_heatmap(entries: list[HeatmapEntry]) -> str:
    if not entries:
        return "Тепловая карта: нет тикеров для проверки."
    lines = ["Тепловая карта MOEX", ""]
    for entry in entries:
        lines.append(
            " | ".join(
                [
                    entry.ticker,
                    f"{entry.score}/100",
                    entry.state_title,
                    f"тип {entry.alert_type}",
                    f"buy {format_percent(entry.buy_power)}",
                    f"sell {format_percent(entry.sell_power)}",
                    f"MegaAlert {entry.megaalerts}",
                ]
            )
        )
    return "\n".join(lines)


def format_mega_alert_summaries(summaries: list[MegaAlertSummary]) -> str:
    if not summaries:
        return "MegaAlert: нет тикеров для проверки."
    blocks: list[str] = []
    for summary in summaries:
        lines = [f"MegaAlert {summary.ticker}", f"Всего событий: {summary.total}"]
        if summary.by_type:
            for key, count in sorted(summary.by_type.items(), key=lambda item: item[1], reverse=True)[:5]:
                lines.append(f"{key}: {count}")
        else:
            lines.append("Событий нет.")
        if summary.latest:
            lines.append("Последние:")
            for row in summary.latest[:3]:
                lines.append(
                    f"- {row.get('tradedate') or 'н/д'} {row.get('tradetime') or 'н/д'} "
                    f"{row.get('alert_type') or 'unknown'} {row.get('value') or row.get('price') or ''}".strip()
                )
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def format_digest(entries: list[HeatmapEntry]) -> str:
    if not entries:
        return "Дайджест: нет данных для проверки."
    leaders = entries[:3]
    lines = ["Дайджест MOEX Flow", ""]
    lines.append("Главные сигналы:")
    for entry in leaders:
        lines.append(f"- {entry.ticker}: {entry.score}/100, {entry.state_title}, {entry.alert_type}")
    lines.append("")
    lines.append("Это аналитический обзор, не является инвестиционной рекомендацией.")
    return "\n".join(lines)


def format_futoi_summary(summary: FutoiSummary) -> str:
    if not summary.groups:
        return f"FUTOI {summary.ticker}: нет данных."
    lines = [
        f"FUTOI {summary.ticker}",
        f"Время: {summary.tradedate} {summary.tradetime}",
        f"Лонги: {summary.total_long:,.0f}".replace(",", " "),
        f"Шорты: {summary.total_short:,.0f}".replace(",", " "),
        f"Нетто: {summary.net:+,.0f}".replace(",", " "),
        "",
        "Группы:",
    ]
    for group in summary.groups:
        lines.append(
            (f"{group.client_group}: лонг {group.long:,.0f}, шорт {group.short:,.0f}, нетто {group.net:+,.0f}").replace(
                ",", " "
            )
        )
    return "\n".join(lines)


def format_flow_statistics(stats: FlowStatistics) -> str:
    return "\n".join(
        [
            f"Статистика {stats.ticker}",
            f"Текущее состояние: {stats.state_title}",
            f"Похожих случаев: {stats.samples}",
            f"После этого рост: {stats.up_after}",
            f"После этого снижение: {stats.down_after}",
            f"Без изменения: {stats.flat_after}",
            "",
            "Статистика описывает прошлые наблюдения и не является прогнозом.",
        ]
    )


def format_portfolio(tickers: list[str]) -> str:
    if not tickers:
        return "Портфель пуст. Добавьте тикер командой /portfolio_add ROSN."
    return "\n".join(["Портфель", *tickers])


def format_portfolio_risk(risk: PortfolioRisk) -> str:
    if risk.total == 0:
        return "Риск портфеля: портфель пуст."
    risky = ", ".join(risk.risky_tickers) if risk.risky_tickers else "нет"
    lines = [
        "Риск портфеля",
        f"Тикеров: {risk.total}",
        f"Средняя сила сигналов: {risk.average_score:.1f}/100",
        f"Рисковых тикеров: {risk.risky_count}",
        f"Список риска: {risky}",
    ]
    return "\n".join(lines)


def format_settings(settings: ChatSettings) -> str:
    quiet = (
        f"{settings.quiet_start}-{settings.quiet_end}" if settings.quiet_start and settings.quiet_end else "не заданы"
    )
    types = ", ".join(settings.alert_types) if settings.alert_types else "все"
    return "\n".join(
        [
            "Настройки автосканера",
            f"Минимальная сила: {settings.min_score}/100",
            f"Тихие часы: {quiet}",
            f"Типы сигналов: {types}",
        ]
    )


def format_channel_signal(report: SignalReport) -> str:
    return "\n".join(
        [
            f"MOEX Flow Alert: {report.ticker}",
            f"{report.score}/100 | {report.state.title} | {report.alert_type}",
            f"Buy {format_percent(report.buy_power)} / Sell {format_percent(report.sell_power)}",
            f"Level: support {format_price(report.support)}, reclaim {format_price(report.reclaim)}",
            "Не инвестиционная рекомендация.",
        ]
    )


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
    lines = [
        f"Котировка {ticker}",
        f"Последняя цена: {format_price(_optional_float(quote.get('last')))}",
        f"Изменение к предыдущей: {_format_optional_percent(quote.get('last_to_prev_pct'))}",
    ]
    bid = _optional_float(quote.get("bid"))
    offer = _optional_float(quote.get("offer"))
    if bid is not None or offer is not None:
        lines.append(f"Спрос/предложение: {format_price(bid)} / {format_price(offer)}")
    lines.append(f"Время: {quote.get('time') or 'н/д'}")
    return "\n".join(lines)


def format_help() -> str:
    lines = ["Команды на русском:"]
    sections = tuple(dict.fromkeys(spec.section for spec in COMMAND_SPECS))
    for section in sections:
        lines.extend(["", f"{section}:"])
        lines.extend(f"{spec.usage} - {spec.description}" for spec in COMMAND_SPECS if spec.section == section)
    lines.extend(
        [
            "",
            "Типы сигналов: " + ", ".join(ALLOWED_ALERT_TYPES) + ".",
            "По умолчанию тикеры читаются на рынке акций MOEX TQBR; FUTOI работает по фьючерсам.",
            "Бот показывает аналитику по данным MOEX/ALGOPACK и не является инвестиционной рекомендацией.",
        ]
    )
    return "\n".join(lines)


def format_latest_book(ticker: str, rows: list[dict]) -> str:
    if not rows:
        return f"Нет данных OBStats по {ticker}."
    latest = sorted(rows, key=lambda row: (str(row.get("tradedate") or ""), str(row.get("tradetime") or "")))[-1]
    return "\n".join(
        [
            f"Стакан {ticker}",
            f"Время: {latest.get('tradedate')} {latest.get('tradetime')}",
            f"Дисбаланс всего: {float(latest.get('imbalance_val') or 0):+.2f}",
            f"Дисбаланс BBO: {float(latest.get('imbalance_val_bbo') or 0):+.2f}",
            f"Спред BBO: {float(latest.get('spread_bbo') or 0):.1f}",
        ]
    )


def format_order_pressure(ticker: str, rows: list[dict]) -> str:
    if not rows:
        return f"Нет данных OrderStats по {ticker}."
    put_buy = sum(float(row.get("put_val_b") or 0) for row in rows)
    put_sell = sum(float(row.get("put_val_s") or 0) for row in rows)
    cancel_buy = sum(float(row.get("cancel_val_b") or 0) for row in rows)
    cancel_sell = sum(float(row.get("cancel_val_s") or 0) for row in rows)
    return "\n".join(
        [
            f"Заявки {ticker}",
            f"Выставлено покупок: {put_buy / 1_000_000_000:.2f} млрд ₽",
            f"Выставлено продаж: {put_sell / 1_000_000_000:.2f} млрд ₽",
            f"Снято покупок: {cancel_buy / 1_000_000_000:.2f} млрд ₽",
            f"Снято продаж: {cancel_sell / 1_000_000_000:.2f} млрд ₽",
        ]
    )


def format_alerts(ticker: str, rows: list[dict]) -> str:
    if not rows:
        return f"Нет MegaAlert по {ticker} за выбранный период."
    counts: dict[str, int] = {}
    for row in rows:
        key = str(row.get("alert_type") or "unknown")
        counts[key] = counts.get(key, 0) + 1
    lines = [f"MegaAlert {ticker}", f"Всего событий: {len(rows)}"]
    for key, count in sorted(counts.items(), key=lambda item: item[1], reverse=True)[:6]:
        lines.append(f"{key}: {count}")
    return "\n".join(lines)


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

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class FlowSummary:
    buy_value: float = 0.0
    sell_value: float = 0.0
    buy_volume: float = 0.0
    sell_volume: float = 0.0
    buy_trades: float = 0.0
    sell_trades: float = 0.0

    @property
    def total_value(self) -> float:
        return self.buy_value + self.sell_value

    @property
    def net_value(self) -> float:
        return self.buy_value - self.sell_value

    @property
    def buy_power(self) -> float:
        return self.buy_value / self.total_value if self.total_value else 0.0

    @property
    def sell_power(self) -> float:
        return self.sell_value / self.total_value if self.total_value else 0.0

    @property
    def imbalance(self) -> float:
        return self.net_value / self.total_value if self.total_value else 0.0


@dataclass(frozen=True)
class DayFlow:
    date: str
    first_time: str
    last_time: str
    open_price: float
    close_price: float
    buckets: int
    flow: FlowSummary

    @property
    def price_change(self) -> float:
        if not self.open_price:
            return 0.0
        return (self.close_price / self.open_price - 1.0) * 100.0


@dataclass(frozen=True)
class TradeState:
    code: str
    title: str
    description: str
    action: str


@dataclass(frozen=True)
class SignalFeatures:
    low_alerts: int = 0
    high_alerts: int = 0
    megaalert_count: int = 0
    order_bias: float = 0.0
    bbo_imbalance: float = 0.0


@dataclass(frozen=True)
class SignalReport:
    ticker: str
    state: TradeState
    score: int
    direction: str
    alert_type: str
    latest_date: str
    latest_time: str
    price_change: float
    flow_imbalance: float
    buy_power: float
    sell_power: float
    support: float | None
    reclaim: float | None
    reasons: tuple[str, ...]
    signal_key: str
    features: SignalFeatures = field(default_factory=SignalFeatures)


def _number(row: Mapping[str, Any], key: str) -> float:
    value = row.get(key)
    return float(value) if value is not None else 0.0


def summarize_flow(rows: Iterable[Mapping[str, Any]]) -> FlowSummary:
    buy_value = sell_value = 0.0
    buy_volume = sell_volume = 0.0
    buy_trades = sell_trades = 0.0
    for row in rows:
        buy_value += _number(row, "val_b")
        sell_value += _number(row, "val_s")
        buy_volume += _number(row, "vol_b")
        sell_volume += _number(row, "vol_s")
        buy_trades += _number(row, "trades_b")
        sell_trades += _number(row, "trades_s")
    return FlowSummary(
        buy_value=buy_value,
        sell_value=sell_value,
        buy_volume=buy_volume,
        sell_volume=sell_volume,
        buy_trades=buy_trades,
        sell_trades=sell_trades,
    )


def summarize_daily_flow(rows: Iterable[Mapping[str, Any]]) -> list[DayFlow]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        date = row.get("tradedate")
        if date:
            grouped[str(date)].append(row)

    days: list[DayFlow] = []
    for date in sorted(grouped):
        day_rows = sorted(grouped[date], key=lambda row: str(row.get("tradetime") or ""))
        first = day_rows[0]
        last = day_rows[-1]
        days.append(
            DayFlow(
                date=date,
                first_time=str(first.get("tradetime") or ""),
                last_time=str(last.get("tradetime") or ""),
                open_price=_number(first, "pr_open"),
                close_price=_number(last, "pr_close"),
                buckets=len(day_rows),
                flow=summarize_flow(day_rows),
            )
        )
    return days


def classify_trade_state(price_change: float, flow_imbalance: float) -> TradeState:
    if price_change <= -0.5 and flow_imbalance <= -0.05:
        return TradeState(
            code="sell_pressure",
            title="Давление продавцов",
            description="Цена падает вместе с отрицательным дисбалансом сделок.",
            action="Лонги только после остановки новых минимумов и возврата выше VWAP.",
        )
    if price_change <= -0.5 and flow_imbalance >= 0.03:
        return TradeState(
            code="absorption",
            title="Абсорбция продаж",
            description="Цена снижается, но покупатели забирают значимую часть рыночных продаж.",
            action="Ждать подтверждение: закрепление выше VWAP или пробой ближайшего локального максимума.",
        )
    if price_change >= 0.5 and flow_imbalance >= 0.05:
        return TradeState(
            code="bullish_reversal",
            title="Бычий разворот",
            description="Цена растет вместе с положительным дисбалансом сделок.",
            action="Работать только с риском ниже последнего локального минимума.",
        )
    if price_change >= 0.5 and flow_imbalance <= -0.03:
        return TradeState(
            code="weak_bounce",
            title="Слабый отскок",
            description="Цена растет, но поток сделок не подтверждает контроль покупателей.",
            action="Не догонять движение; ждать повторное подтверждение спроса.",
        )
    return TradeState(
        code="neutral",
        title="Нейтрально",
        description="Нет устойчивого преимущества покупателей или продавцов.",
        action="Ждать расширения диапазона и подтверждения потоком сделок.",
    )


def classify_from_days(days: list[DayFlow]) -> TradeState:
    if not days:
        return classify_trade_state(0.0, 0.0)
    latest = days[-1]
    return classify_trade_state(latest.price_change, latest.flow.imbalance)

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Command:
    name: str
    ticker: str | None
    days: int = 1
    tickers: tuple[str, ...] = ()
    minutes: int | None = None
    args: tuple[str, ...] = ()


@dataclass(frozen=True)
class CommandSpec:
    name: str
    usage: str
    description: str
    section: str


COMMAND_SPECS: tuple[CommandSpec, ...] = (
    CommandSpec("quote", "/quote ROSN", "текущая котировка", "Быстрый анализ"),
    CommandSpec("flow", "/flow ROSN 7", "покупательная/продавцовая сила за N дней", "Быстрый анализ"),
    CommandSpec("strategy", "/strategy ROSN", "торговый сценарий по потоку сделок", "Быстрый анализ"),
    CommandSpec(
        "signal",
        "/signal ROSN",
        "скоринговый сигнал по TradeStats, OrderStats, OBStats и MegaAlert",
        "Быстрый анализ",
    ),
    CommandSpec("full", "/full ROSN", "полный отчет по тикеру", "Быстрый анализ"),
    CommandSpec("book", "/book ROSN", "краткий статус стакана", "Быстрый анализ"),
    CommandSpec("orders", "/orders ROSN", "давление выставленных и снятых заявок", "Быстрый анализ"),
    CommandSpec("alerts", "/alerts ROSN", "аномальные события ALGOPACK", "Быстрый анализ"),
    CommandSpec("scan", "/scan ROSN SBER", "быстрый сканер по нескольким тикерам", "Scanner Pro и рынок"),
    CommandSpec(
        "marketflow",
        "/marketflow",
        "лидеры покупок/продаж по корзине за последние 2 часа",
        "Scanner Pro и рынок",
    ),
    CommandSpec(
        "heatmap",
        "/heatmap ROSN SBER",
        "тепловая карта: сила, поток, MegaAlert и тип сигнала",
        "Scanner Pro и рынок",
    ),
    CommandSpec(
        "mega", "/mega ROSN", "лента MegaAlert с типами аномалий и последними событиями", "Scanner Pro и рынок"
    ),
    CommandSpec("digest", "/digest ROSN SBER", "краткий дайджест главных сигналов", "Scanner Pro и рынок"),
    CommandSpec("stats", "/stats ROSN 30", "статистика похожих состояний на истории TradeStats", "Scanner Pro и рынок"),
    CommandSpec("watch", "/watch ROSN 15m", "добавить тикер в автосканер", "Автосканер watchlist"),
    CommandSpec("unwatch", "/unwatch ROSN", "удалить тикер из автосканера", "Автосканер watchlist"),
    CommandSpec("watchlist", "/watchlist", "показать автосканер", "Автосканер watchlist"),
    CommandSpec("mute", "/mute ROSN 60", "поставить автосигналы на паузу на N минут", "Автосканер watchlist"),
    CommandSpec("settings", "/settings", "настройки автосканера", "Автосканер watchlist"),
    CommandSpec("score", "/score 70", "минимальная сила автосигнала", "Автосканер watchlist"),
    CommandSpec("quiet", "/quiet 23:00 07:00", "тихие часы", "Автосканер watchlist"),
    CommandSpec("types", "/types sell_pressure absorption", "фильтр типов автосигналов", "Автосканер watchlist"),
    CommandSpec("futoi", "/futoi SBERF", "открытый интерес по фьючерсу", "Фьючерсы и FUTOI"),
    CommandSpec("portfolio_add", "/portfolio_add ROSN", "добавить бумагу в портфель", "Портфель"),
    CommandSpec("portfolio_remove", "/portfolio_remove ROSN", "удалить бумагу из портфеля", "Портфель"),
    CommandSpec("portfolio", "/portfolio", "показать портфель", "Портфель"),
    CommandSpec("portfolio_risk", "/portfolio_risk", "риск портфеля", "Портфель"),
    CommandSpec("channel_signal", "/channel_signal ROSN", "короткий сигнал для канала", "Каналы"),
)

KNOWN_COMMANDS = {spec.name for spec in COMMAND_SPECS} | {"help"}
NO_TICKER_COMMANDS = {"watchlist", "settings", "portfolio", "portfolio_risk"}
ARG_COMMANDS = {"score", "quiet", "types"}
MULTI_TICKER_COMMANDS = {"scan", "heatmap", "mega", "digest", "marketflow"}
ONE_TICKER_COMMANDS = {"portfolio_add", "portfolio_remove", "futoi", "channel_signal"}


def parse_command(text: str) -> Command:
    parts = text.strip().split()
    if not parts or not parts[0].startswith("/"):
        return Command(name="help", ticker=None, days=1)

    name = parts[0].removeprefix("/").split("@", 1)[0].lower()
    if name == "start":
        name = "help"
    if name not in KNOWN_COMMANDS:
        return Command(name="help", ticker=None, days=1)

    if name in NO_TICKER_COMMANDS:
        return Command(name=name, ticker=None)
    if name in ARG_COMMANDS:
        return Command(name=name, ticker=None, args=tuple(parts[1:]))

    ticker = parts[1].upper() if len(parts) >= 2 else None
    tickers = tuple(part.upper() for part in parts[1:] if not part.startswith("/"))
    days = 30 if name == "stats" else 7 if name == "strategy" else 1
    if name in MULTI_TICKER_COMMANDS:
        return Command(name=name, ticker=ticker, tickers=tickers)
    if name in ONE_TICKER_COMMANDS:
        return Command(name=name, ticker=ticker)
    if name == "watch":
        return Command(
            name=name, ticker=ticker, minutes=parse_minutes(parts[2] if len(parts) >= 3 else None, default=15)
        )
    if name == "mute":
        return Command(
            name=name, ticker=ticker, minutes=parse_minutes(parts[2] if len(parts) >= 3 else None, default=60)
        )
    if len(parts) >= 3 and name in {"flow", "strategy"}:
        try:
            days = max(1, min(30, int(parts[2])))
        except ValueError:
            days = 1
    if len(parts) >= 3 and name == "stats":
        try:
            days = max(2, min(120, int(parts[2])))
        except ValueError:
            days = 30
    return Command(name=name, ticker=ticker, days=days)


def parse_minutes(value: str | None, *, default: int) -> int:
    if not value:
        return default
    normalized = value.lower().removesuffix("m").removesuffix("м")
    try:
        return max(1, min(1440, int(normalized)))
    except ValueError:
        return default


def parse_score(value: str | None) -> int:
    if not value:
        return 60
    try:
        return max(0, min(100, int(value)))
    except ValueError:
        return 60


def default_tickers() -> tuple[str, ...]:
    raw = os.environ.get("DEFAULT_SCAN_TICKERS", "ROSN SBER GAZP LKOH TATN TATNP")
    return tuple(item.strip().upper() for item in raw.replace(",", " ").split() if item.strip())


def default_marketflow_tickers() -> tuple[str, ...]:
    raw = os.environ.get(
        "DEFAULT_MARKETFLOW_TICKERS",
        "TATN PLZL OZON LKOH GMKN ROSN SBER VTBR NVTK T GAZP MOEX SNGS YDEX X5",
    )
    return tuple(item.strip().upper() for item in raw.replace(",", " ").split() if item.strip())

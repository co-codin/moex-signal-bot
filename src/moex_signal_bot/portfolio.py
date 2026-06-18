from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from .signals import SignalReport


@dataclass(frozen=True)
class PortfolioRisk:
    total: int
    risky_count: int
    average_score: float
    risky_tickers: tuple[str, ...]
    reports: tuple[SignalReport, ...]


def build_portfolio_risk(reports: Iterable[SignalReport], *, min_score: int = 60) -> PortfolioRisk:
    ordered = tuple(sorted(reports, key=lambda report: report.score, reverse=True))
    risky = tuple(report.ticker for report in ordered if report.score >= min_score and report.state.code != "neutral")
    average = sum(report.score for report in ordered) / len(ordered) if ordered else 0.0
    return PortfolioRisk(
        total=len(ordered),
        risky_count=len(risky),
        average_score=average,
        risky_tickers=risky,
        reports=ordered,
    )

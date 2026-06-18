# Full MOEX Stock Analysis Prompt

Use this prompt to request a complete analysis for a specific MOEX ticker such as `ROSN`.

```text
Analyze the MOEX stock {TICKER}, for example ROSN, as of today.

Use fresh market data and clearly separate:
1. Confirmed data from MOEX/ALGOPACK
2. Your interpretation
3. Trading scenario ideas
4. Risk warnings

Required sections:

1. Current Market Snapshot
- Last price
- Open, high, low
- Previous close
- VWAP or weighted average price
- Daily change in RUB and %
- Volume and turnover
- Bid/offer if available
- Exact data timestamp

2. Buy/Sell Power
Use TradeStats:
- Total buy value
- Total sell value
- Buy power %
- Sell power %
- Net flow in RUB
- Last 3-5 intervals buy/sell power
- Explain whether buyers or sellers control the tape

Formula:
buy_power = val_b / (val_b + val_s)
sell_power = val_s / (val_b + val_s)
net_flow = val_b - val_s

3. Order Pressure
Use OrderStats:
- Placed buy orders
- Placed sell orders
- Cancelled buy orders
- Cancelled sell orders
- Explain whether the order flow supports buyers or sellers

4. Order Book / OBStats
Use OBStats:
- Total imbalance
- BBO imbalance
- Spread
- Explain whether the book supports accumulation, selling pressure, or neutral behavior

5. MegaAlerts
Use ALGOPACK MegaAlert:
- Total alerts today
- Alerts by type
- Latest alerts with time, alert type, value/price
- New low / new high alerts
- Explain what these alerts mean for the current session

6. Technical Levels
Identify:
- Intraday support
- Intraday resistance
- Breakdown level
- Reclaim/control level
- Stop-risk zone
- Invalidating level for the main scenario

7. Signal Classification
Classify the stock into one:
- Strong selling pressure
- Selling pressure
- Absorption
- Bullish reversal
- Weak bounce
- Neutral

Give a score from 0 to 100 and explain the score.

8. Trading Scenarios
Provide:
- Bearish scenario
- Bullish scenario
- Neutral/no-trade scenario

For each scenario include:
- Trigger
- Confirmation
- Invalidating level
- Main risk

9. Final Summary
Give a concise conclusion:
- Who controls the stock now: buyers or sellers?
- Is the stock better for long, short, or wait?
- What exact level changes the view?

Important:
- Do not give financial advice.
- Do not invent unavailable data.
- If TradeStats, OrderStats, OBStats, or MegaAlert are unavailable, say so clearly.
- Always include exact dates and timestamps.
- Keep the answer practical and concise.
```

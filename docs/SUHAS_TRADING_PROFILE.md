# Suhas Trading Profile

This customization adds a safety-first validation layer to the upstream AI-Trader project without replacing its existing trading engine.

## Purpose

The profile is designed for India and US equity workflows where a trade idea should be revalidated immediately before execution. It is intentionally conservative and defaults to paper mode.

Supported markets:

- NSE
- BSE
- NYSE
- NASDAQ

## Default guardrails

- Live execution disabled by default.
- Maximum portfolio risk per trade: 1%.
- Minimum reward/risk ratio: 2.0.
- Maximum allowed move beyond the planned reference level before the setup is treated as chasing: 1.5%.
- Maximum quote age: 120 seconds.
- Minimum independent confirmation sources: 2.
- Mandatory checks: news, technical setup, and current portfolio exposure.

All values are configurable through `.env`.

## API

### Read the active profile

`GET /api/suhas/profile`

### Evaluate a proposed entry

`POST /api/suhas/evaluate-entry`

Example payload:

```json
{
  "symbol": "AAPL",
  "market": "NASDAQ",
  "direction": "long",
  "current_price": 101.0,
  "reference_price": 100.0,
  "entry_price": 101.0,
  "stop_loss": 99.0,
  "target_price": 105.0,
  "quantity": 10,
  "portfolio_value": 100000.0,
  "price_timestamp": "2026-07-13T10:00:00Z",
  "quote_source": "verified-live-feed",
  "confirmation_source_count": 2,
  "news_checked": true,
  "technical_checked": true,
  "portfolio_checked": true,
  "live_execution_requested": false
}
```

The response returns `BUY`, `SELL`, or `WAIT`, eligibility, execution mode, reasons, warnings, and calculated risk metrics.

## Research workflow

Before marking the confirmation flags as true, the calling agent or service should verify the setup using current information. The preferred source set includes:

- TradingView
- Reuters
- Economic Times
- Moneycontrol
- Investing.com
- Screener.in
- MarketsMojo
- Tickertape
- TipRanks
- ChartInk
- Yahoo Finance
- CNBC / CNBC-TV18

The policy does not scrape or trust any one source automatically. The caller is responsible for providing fresh, independently confirmed inputs.

## Important design boundary

This module does not place broker orders and does not claim to predict market outcomes. It validates the structure and freshness of a proposed trade before another system or a human decides whether to act.

Keeping this customization in separate files reduces conflicts when pulling future updates from `HKUDS/AI-Trader`.

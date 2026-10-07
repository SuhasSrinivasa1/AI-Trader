# Multify Trader Pro v4.5.0 — AUTO Direction Selector

v4.5 starts from the validated v4.4 pivot-wave build and adds an adaptive, one-sided AUTO decision from Wave 2 onward while preserving the latency-first Wave 1 Multify path.

## AUTO execution
- Wave 1 remains deterministic: paid Multify Equity BUY -> immediate long -> profitable/trailing long exit -> immediate Wave-1 MIS short -> short cover.
- Wave 2–20 no longer blindly execute both directions in AUTO.
- At each eligible Wave 2+ transition, AUTO chooses exactly one of **LONG**, **SHORT**, or **HOLD**.
- Ambiguous evidence produces HOLD; the engine does not force a trade.
- LONG ONLY and SHORT ONLY remain deterministic modes and are not changed by the adaptive selector.

## Direction selector
The selector is intentionally auditable rather than a black box.

Trajectory component (40%):
- recency-weighted Up-vs-Down pivot amplitude dominance;
- drift from the Multify campaign anchor;
- higher/lower recent peaks and bottoms.

Live technical/context component (60%):
- 1-minute candle/price structure;
- relative volume and volume-price impulse;
- VWAP, EMA9/20, slope, RSI, MACD, ATR, Bollinger/Donchian/ORB context;
- spread and order-book imbalance where available;
- intraday day-change context;
- market cap and 52-week position as low-weight stock context.

The decision and every input score are persisted to the diagnostic log as `AUTO_SELECTOR/WAVE_DIRECTION_DECISION`.

Static company ratios such as P/E, ROCE and leverage are not used as second-level execution gates in this APK because the current Groww trading feed does not provide a complete real-time fundamentals set. Those slower fundamentals remain appropriate for Forecast Lab when a reliable external fundamentals source is connected.

## Learning provenance
- Uploaded historical Excel seeds **Wave-1 Long only**.
- Wave-1 Long uses the latest **30 calendar days**, never the latest 30 calls.
- Short learning uses **Wave-1 Down only** from confirmed live pivots from 2026-10-07 onward; no historical short reconstruction.
- Waves 2–20 remain independent pivot observations.

## Reliability fixes from v4.4 log audit
- Default notification capture is restricted to the real Multify package `com.multyfi.invest` unless an explicit package override is configured.
- Listener explicit rebinds are debounced.
- Historical seed refresh is idempotent across process restarts when the embedded history is already current.
- Broker execution audit now records submit-start, broker-accepted and fill-confirmed timestamps with latency values.
- Wave-1 sample reporting distinguishes the date-weighted learning window rather than treating all historical calls as equal-weight days.

## Existing risk/execution contract retained
- Long: no stop-loss; never sell below weighted average cost; ₹5,000 averaging each further 2% decline within configured budget; learned arm level then ₹1 trailing reversal.
- Short: no averaging; no per-trade stop; learned Wave-1 Down arm level then ₹1 trailing reversal; ₹2,000 cumulative daily gross short-loss blocker.
- Wave detector remains a 0.40% live-price pivot/ZigZag engine independent of candles.
- Primary UI remains **Execution | Forecast | Settings** with Live and Shadow P&L pinned.

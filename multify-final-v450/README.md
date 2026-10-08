# Multify Trader Pro v4.5.0 — AUTO Wave Direction

v4.5 starts from the validated v4.4.0 pivot-wave build and adds trajectory-aware AUTO execution from Wave 2 onward.

## AUTO execution contract
- **Wave 1 is unchanged**: paid Multify Equity BUY -> immediate CNC long -> profitable close only -> immediate MIS short -> cover.
- **Wave 2 through Wave 20 no longer force both sides.**
- At each later-wave transition, AUTO selects exactly one outcome: **LONG**, **SHORT**, or **SKIP**.
- A weak/mixed score is skipped rather than forcing a trade.
- LONG ONLY and SHORT ONLY modes keep their explicit one-sided behavior.

## Wave 2+ mathematical selector
The selector uses the live Groww quote/candle feed plus confirmed pivot history:
- higher-high / higher-low vs lower-high / lower-low structure,
- current price vs VWAP,
- EMA 9/20 separation,
- ATR-normalized trend slope,
- MACD histogram,
- RSI context,
- relative-volume candle impulse,
- opening-range and Donchian breakout/breakdown context,
- order-book imbalance when supplied,
- day trajectory,
- recent Up-vs-Down pivot balance,
- low-weight 52-week range context.

Candles and volume help choose direction; they **do not define waves**. Waves remain the v4.4 scale-invariant 0.40% favourable move + 0.40% reversal pivots.

Full external fundamentals such as P/E, ROCE, leverage and filing data are not invented when the connected Groww feed does not provide them. They can be added later as a slow context layer without delaying the execution path.

## Log-driven fixes
- Default notification source is now exact package **com.multyfi.invest** when the user has not configured an override.
- Broker market orders now log **submit -> acknowledgement -> fill latency**.
- Wave-1 Long sample count is the number of contributing profitable dates, not raw call count.
- The summary short statistic is **Wave-1 Down only**; Down-2..Down-20 remain independent and are not averaged into one global short number.
- Historical Excel seeding is persisted by seed version to avoid repeated full reseeding on foreground-service restarts.
- Strategy/diagnostic catalog is updated to match the current deterministic rules.

## Existing rules retained
- Wave-1 Long uses the latest 30 calendar days only.
- Excel seeds Wave-1 Long only.
- Short/Down learning starts from confirmed live pivots only.
- LONG: no stop-loss; never sell below weighted average; ₹5,000 add each further 2% down within budget.
- SHORT: no averaging; no per-trade stop; ₹2,000 cumulative daily gross short-side loss blocker.
- Learned/fallback wave arm level starts the fixed ₹1 trailing reversal.
- UI remains **Execution | Forecast | Settings**, with Live and Shadow P&L pinned.

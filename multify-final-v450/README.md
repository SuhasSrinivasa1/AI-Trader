# Multify Trader Pro v4.5.0 — Directional AUTO Waves

v4.5 starts from the validated v4.4.0 pivot-wave source and applies the auditable `multify-final-v450/patch.gz.b64.part*` delta.

## Wave 1 remains deterministic
- Paid Multify Equity BUY is still the Wave-1 trigger.
- AUTO Wave 1 remains the fast lifecycle: immediate CNC long -> profitable ₹1 trailing exit -> immediate MIS short -> learned/bootstrapped short arm -> ₹1 trailing cover.
- Long stop-loss remains NONE; underwater long sale remains prohibited.
- Long averaging remains ₹5,000 on each further 2% decline within the configured budget.
- Short averaging remains NONE; there is no per-trade short stop.
- The ₹2,000 cumulative daily gross short-side loss blocker remains active.

## AUTO Wave 2–20: one direction only
Starting with execution Wave 2, AUTO no longer mechanically trades both directions.

At each confirmed 0.40% pivot, the engine computes one transparent directional score:
- **65% trajectory**: recent confirmed Up/Down leg dominance plus campaign net move.
- **35% technical context**: the existing Groww-driven strategy feature set (candles, VWAP/EMAs, RSI/MACD/ATR/Donchian/ORB, relative volume, spread/order-book imbalance, day change, market-cap/52-week context).
- Recent legs receive higher weight than older legs.
- Relative volume can strengthen confidence but does not independently flip direction.

Execution is pivot-safe:
- A confirmed **Down** pivot is the only place Wave 2+ AUTO may open a selected **LONG**.
- A confirmed **Up** pivot is the only place Wave 2+ AUTO may open a selected **SHORT**.
- The directional score is evaluated only when a pivot is confirmed; it is not polled into repeated entries between pivots.
- If the stronger mathematical side does not match the next safe pivot entry, the leg is **skipped** rather than chased.
- Each execution Wave 2–20 is therefore one selected position, not an automatic long+short pair.

LONG_ONLY and SHORT_ONLY modes retain their explicit side restrictions.

## Wave/statistical learning
- Waves continue to be defined by live-price pivots, not candle boundaries: >=0.40% favourable excursion followed by >=0.40% reversal.
- Up-1/Down-1 through Up-20/Down-20 remain independent raw statistical buckets.
- The uploaded historical spreadsheet seeds **Wave-1 Long only**, using the latest **30 calendar days**.
- Wave-1 Long sample count now reflects contributing calendar dates rather than profitable call count.
- Top-level short learning is restricted to Wave-1 Down observations; later Down waves remain independent in the 20-wave table.
- Short/Down history is not reconstructed from the spreadsheet.

## Execution/logging reliability
- Default notification package filter is now the real Multify package: `com.multyfi.invest`; unrelated simulator notifications are rejected before entering the signal pipeline.
- The history-seed import now has a persistent version marker so foreground-service restarts do not repeatedly rescan/import the seed asset.
- Broker market-order audit events record submitted, accepted and filled timestamps plus submit->accept, accept->fill and submit->fill latency.
- Directional AUTO decisions persist both LONG and SHORT strategy snapshots with the `AUTO_WAVE_DIRECTION` tag so diagnostic exports can reconstruct why a side was selected or skipped.
- Exported strategy catalog reflects the current 30-calendar-day, pivot-wave and directional-AUTO rules.

## UI
Primary navigation remains deliberately small:
**Execution | Forecast | Settings**

Live P&L and Shadow P&L remain visible across the primary screens. Execution retains the compact 20-wave table and now identifies AUTO Wave 2+ as trajectory-led, one-side-only execution.

## Fundamentals note
v4.5 uses the market/fundamental-like fields already available in the current Groww/instrument context (including market-cap and 52-week positioning) together with live volume/candle/order-book features. It does **not** invent P/E, ROCE, debt, filings or other company fundamentals that the current Groww Trading API feed does not provide. Those slower-moving fields remain a Forecast Lab extension for a future reliable fundamentals provider and do not delay the Multify execution lane.

The APK retains the stable package id and signing lineage used by the v4 release family.

# Multify Trader Pro v4.4.0 — Pivot Waves + 30-Day Wave-1 Seed

v4.4 starts from the validated v4.3.0 source and applies the auditable `multify-final-v440/patch.gz.b64.part*` delta.

## Execution remains the fast lane
- Paid Multify Equity lifecycle only; Free, F&O and commodity alerts remain ignored.
- Live controls remain mutually exclusive: **AUTO**, **LONG ONLY**, **SHORT ONLY**, plus ARM/DISARM.
- Selected execution waves remain 1–20; budget remains ₹10,000–₹2,00,000 in ₹5,000 steps.
- Forecast/research/wave aggregation is kept out of the critical notification → broker-order path.
- Long rules remain: no stop-loss, never sell below weighted average cost, ₹5,000 add on each further 2% decline within budget, learned arm level then ₹1 trailing reversal.
- Short rules remain: no averaging, no per-trade stop, learned arm level then ₹1 trailing reversal, ₹2,000 cumulative daily gross short-side loss blocker.

## True pivot-wave engine
- Candle patterns do **not** define waves.
- A wave is confirmed from the live quote path using a scale-invariant percentage ZigZag rule.
- A leg must first move at least **0.40%** in its favourable direction; a subsequent **0.40% reversal** confirms the peak or bottom.
- Up-1 starts at the actual Groww fill when available; otherwise the contemporaneous Shadow quote anchors the campaign and is re-anchored to the live fill before any pivot is confirmed.
- Initial adverse movement before Up-1 is armed is logged but is not mislabeled as Down-1.
- The engine records independent **Up-1/Down-1 through Up-20/Down-20** observations with start/extreme/confirmation prices and timestamps.
- Pivot math is unit-tested for UP, DOWN, noise rejection, adverse initial movement and price-scale invariance.

## Learning provenance
- The uploaded `2026-10-06_historical_stocks_intraday.xlsx` is embedded as a CSV seed **only for Wave-1 Long**.
- The active Wave-1 Long statistic always uses the latest **30 calendar days** (`today - 29 days` through today), never the latest 30 calls.
- Multiple eligible profitable calls on the same date are first averaged by date, so one busy recommendation date cannot dominate the window.
- Waves 2–20 receive no Excel seed.
- Down/short learning receives no Excel or reconstructed historical seed and starts from confirmed live Down pivots from **2026-10-07** onward.
- Raw historical observations are retained for audit even after they fall outside the active 30-day window.

## Simplified UI
Only three primary tabs remain: **Execution | Forecast | Settings**.
- Live P&L and Shadow P&L are pinned across all three.
- Execution contains the current campaign plus a compact 20-wave average/sample table.
- Forecast keeps the frozen max-five-per-day cards and after-market WIN/FAIL audit.
- Settings contains the execution controls, broker setup, emergency manual signal and diagnostic export.

## Diagnostics
The exported diagnostic ZIP now includes raw wave campaigns, confirmed pivots, current 20-wave averages and the current 30-day learning snapshot in addition to notifications, fills, positions, forecasts and engine logs.

The APK retains the stable package id and signing lineage used by the v4 release family.

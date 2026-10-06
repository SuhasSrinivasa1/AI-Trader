# Multify Trader Pro v4.4.0 — Wave Pivot + Simple UI

This release starts from the validated v4.3.0 Statistical Execution source and applies the auditable `multify-final-v440/patch.gz.b64.part*` delta.

## Core execution
- Paid Multify **Equity** lifecycle only. Free, F&O and commodity alerts remain ignored.
- Live master ARM/DISARM plus one mutually exclusive mode: **AUTO**, **LONG ONLY**, or **SHORT ONLY**.
- Wave selector: **1–20**, default 1.
- Shared live/Shadow budget: **₹10,000–₹2,00,000** in ₹5,000 steps.
- Shadow remains active regardless of live arming.
- Time-critical execution stays in the foreground service. Forecast/research work is suspended while an execution/wave campaign is active.

## Wave definition
- Candlestick patterns do **not** define the execution waves.
- Wave 1 starts at the immediate Multify BUY reference (actual live fill when available; otherwise contemporaneous quote for Shadow/audit).
- UP phase tracks the running high. A peak is confirmed only after a **0.40% reversal** from that high.
- DOWN phase tracks the running low. A bottom is confirmed only after a **0.40% rebound** from that low.
- Each Up-n and Down-n leg is stored independently through Wave 20 with start/extreme/confirmation prices and timestamps.
- Raw confirmed pivots are persisted for audit and exported in the diagnostic ZIP.
- The **0.40% pivot threshold is statistical wave detection only**. The **₹1 trail** remains the execution profit-management rule after a learned average is reached.

## Wave-1 Long seed
- Derived from the user-provided workbook `2026-10-06_historical_stocks_intraday.xlsx`.
- The workbook seeds **Wave 1 Long only**; it does not seed Wave 2–20 or any short/down-wave average.
- Active Wave-1 Long learning always uses the latest **30 calendar days**, not the latest 30 calls.
- Multiple profitable completed BUY calls on the same calendar date are averaged within that date first, then each date receives one equal vote.
- Failed/red rows remain stored for audit but do not define the positive profit-arm level.
- App-generated early/trailing exits do not contaminate this learner; a live Wave-1 Multify outcome is updated from the actual Multify Book Profit lifecycle event.

## Later waves and short learning
- Wave 2–20 and all DOWN/short averages start from live confirmed-pivot observations.
- No historical short average is imported from the Excel.
- If a later leg has no learned average yet, it is explicitly treated as learning from the confirmed pivot rather than borrowing Wave-1's value.

## Deterministic risk/exits
- Long stop-loss: **none** in the Multify lane.
- Negative long sell: **prohibited**.
- Long averaging: **₹5,000 at every further 2% decline**, within configured budget, longs only.
- Short averaging: **none**.
- Per-trade short stop-loss: **none**.
- Cumulative daily gross short-side loss blocker: **₹2,000**.
- Learned long/short move arms a fixed **₹1 favorable-price trail**.

## Simple UI
Primary navigation is only:
1. **Execution**
2. **Forecast**
3. **Settings**

A persistent strip shows **Live P&L**, **Shadow P&L**, and live-arm status on every tab. Execution includes the compact **20-wave averages** table.

## Diagnostics
The export ZIP includes raw wave trackers, confirmed pivots and the current independent 20-wave averages in addition to notification/order/fill/audit state.

The APK keeps the stable package id and signing lineage used by the v4 release family.

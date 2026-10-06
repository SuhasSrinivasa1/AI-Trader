# Multify Trader Pro v4.3.0 — Statistical Execution + Forecast Lab

This release starts from the validated v4.2.0 Manual Entry Final source and applies the auditable `multify-final-v430/patch.gz.b64.part*` delta.

## Multify execution lane
- Paid Equity Multify lifecycle only. Free, F&O and commodity alerts remain ignored.
- Live execution has a master ARM/DISARM state and one mutually-exclusive mode: **AUTO**, **LONG ONLY**, or **SHORT ONLY**.
- Wave selector: **1–20**, default 1.
- Shared live/Shadow budget selector: **₹10,000–₹2,00,000** in ₹5,000 steps.
- Shadow remains active even when live execution is disarmed.
- Time-critical notification/order processing stays on the foreground-service lane; WorkManager remains recovery only.

## Deterministic long rules
- Paid Equity BUY enters the long immediately when the live lane is armed and the selected mode permits longs.
- CNC long has **no stop-loss**.
- A long below its weighted-average acquisition price is never sold by the deterministic Multify lane.
- Downward averaging applies only to longs: **₹5,000 at each further 2% decline**, subject to the configured campaign budget.
- The learned rolling long move is an **arming level**, not a sell target.
- Once the learned level is reached, profit is managed with a fixed **₹1 trailing reversal**.

## Deterministic short rules
- Shorts are MIS and are never averaged.
- There is no per-trade short stop-loss.
- The learned short move is an arming level; after it is reached, the short is covered on a **₹1 reversal from the favorable low-water mark**.
- A **₹2,000 cumulative daily gross short-side loss blocker** closes the active short and prevents additional live shorts for that day.
- MIS shorts are force-flat near market close.

## Audit and statistics
- Dashboard shows both **Shadow P&L** and **Live P&L**.
- Stores and displays independent wave statistics for **Up/Down 1 through 20**, including sample counts.
- Raw historical campaign/trade data remains available while live target learning continues to emphasize the rolling recent window.

## Forecast Lab
- Separate from the Multify execution fast lane.
- Creates at most **5 frozen forecast candidates per trading day**, spaced dynamically through the session.
- Each frozen card records timestamp, entry, statistical target, stop reference and score.
- After market close each issued forecast is audited as **WIN/FAIL** with realized close-direction P&L and favorable/adverse excursion data.
- Repeated Multify tickers are retained and included in candidate history.
- Forecast/research work cannot block the time-critical Multify notification/order path.

### Data-source note
This release contains the Forecast Lab execution/audit foundation and uses the existing Groww market/candle data plus stored Multify history. A separate full company-fundamentals feed for P/E, ROCE, leverage, filings and similar fields is **not bundled in this APK** and should be added only when a reliable provider/source is connected.

The APK keeps the stable package id and signing lineage used by the v4 release family.

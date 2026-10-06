# Multify Trader Pro v4.3.0 — Statistical Waves

This payload starts from the signed v4.2.0 Manual Entry Final source and applies the auditable compressed `patch.gz.b64.part*` delta before building.

## Deterministic Multify execution

- Paid Equity Multify lifecycle only; Free, F&O and commodity alerts remain ignored.
- Separate `LIVE ARMED` switch and mutually-exclusive execution modes: `AUTO`, `LONG ONLY`, `SHORT ONLY`.
- `AUTO`: long -> close long -> short -> cover; `LONG ONLY`: long legs only; `SHORT ONLY`: post-Book-Profit short legs only.
- Wave selector: 1–20, default 1. Budget: ₹10,000–₹2,00,000 in ₹5,000 increments, default ₹1,00,000.
- Long positions: CNC, no stop-loss, negative long sell prohibited, ₹5,000 averaging at each further 2% decline subject to campaign budget.
- Long profit management: rolling learned target arms a fixed ₹1 trailing exit instead of selling at the target.
- Short positions: MIS, no averaging, no per-trade stop-loss. Learned short target arms a fixed ₹1 trailing cover.
- Daily short-side gross-loss circuit breaker: −₹2,000. Once reached, the active short is covered and additional live shorts are blocked for the day.
- Shadow runs regardless of live arm state using the selected budget/wave count. Dashboard exposes Shadow and Live P&L separately.
- Up-1/Down-1 through Up-20/Down-20 are stored/reported independently with sample counts over the latest 30 observed trading dates.

## Latency isolation

- The foreground service gives live Multify position management the fast lane at ~1 second cadence.
- While a live managed position exists, Shadow aggregation, forecast scans and after-hours research are skipped from that service loop.
- Notification processing and managed-position updates use a mutual-exclusion lane so heavy analytics cannot interleave with the live broker transition.
- WorkManager remains recovery-only.

## Forecast Lab

- Forecast Lab remains independent from the Multify execution lane.
- Maximum five frozen forecasts per trading day, accumulated dynamically through the session.
- Each forecast stores timestamp, entry, target, stop and later after-market WIN/FAIL, outcome, maximum favourable move and maximum adverse move.
- Forecast scoring uses the app's existing market/candle/strategy feature set plus rolling Multify and same-symbol outcome history. Full external company-fundamental coverage is not claimed by this build.
- After-hours replay finalizes forecast outcomes and audits Multify matches.

## Stable update identity

The build workflow removes the debug application-id suffix and signs with the existing v4 stable signing lineage so the APK keeps package `com.multify.traderpro.vivoy73final`.

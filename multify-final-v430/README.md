# Multify Trader Pro v4.3.0 — Statistical Waves

This release keeps the paid-Equity Multify execution path deterministic and latency-first.

## Live execution
- Master arm remains OFF by default.
- Mutually exclusive execution mode: AUTO, LONG ONLY, SHORT ONLY.
- Wave selector: 1–20, default 1.
- Campaign/Shadow budget: ₹10,000–₹2,00,000 in ₹5,000 steps.
- AUTO: long → sell → immediate MIS short → cover, repeated up to selected wave count.
- LONG ONLY: only real long legs; down legs between later waves are tracked virtually.
- SHORT ONLY: only real short legs; up legs between later waves are tracked virtually.
- Free calls, F&O and commodity notifications remain ignored.

## Long rules
- Immediate CNC entry on a paid Equity BUY when mode allows longs.
- No long stop-loss.
- A Fast Track long is never sold below weighted average entry.
- Add approximately ₹5,000 at each further 2% decline while campaign budget remains.
- Recalculate weighted average after every add.
- Reaching the rolling learned long move arms a ₹1 trailing exit instead of selling immediately.

## Short rules
- No averaging.
- No per-trade protective stop-loss.
- Reaching the learned downside target arms a ₹1 trailing cover.
- Cumulative daily Fast Track short gross loss of ₹2,000 closes/blocks short risk for the day.
- MIS is force-flat before session close.

## Separation of work
Forecast generation, fundamentals, strategy snapshots and after-market research stay outside the paid-equity notification/order fast path.

Package lineage remains `com.multify.traderpro.vivoy73final` so the APK can update the existing installation when signing lineage matches.

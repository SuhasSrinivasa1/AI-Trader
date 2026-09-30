# Univest AutoTrade v2.1.0

Univest-only Android delivery automation reliability build.

Locked execution contract:
- Source: official Univest Android package `com.univest.capp` only.
- Equity recommendations with duration <= 3 months: ₹20,000 CNC initial buy.
- Official Univest back-in-range / ideal-range signal: ₹5,000 CNC add.
- Controlled downward averaging for app-managed LIVE campaigns: up to three ₹5,000 CNC GTT levels at -2%, -4%, and -6% from the initial fill anchor.
- Official book-profit / exit: cancel tracked averaging GTTs and sell the full reconciled CNC holding.
- PAPER mode never mutates LIVE campaign state and can never block a later LIVE entry.
- Broker holdings and pending orders are authoritative; stale local ACTIVE state is automatically repaired.
- Exact duplicate Android notification deliveries are suppressed; a signal is not permanently consumed before broker readiness/execution.
- UI is daily (IST) and signal-focused; historical diagnostics remain available in the export ZIP.
- Groww TOTP authentication reuses cached tokens before generating another access token.

This build retains the historical package/class names required for Android upgrade/listener continuity.

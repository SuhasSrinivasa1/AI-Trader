# Multyfi AutoBuy S24 v1.6.0

Private Samsung Galaxy S24 Ultra / Android 16 release.

## Three configurable sizing windows

- 09:00–09:30 IST: default ₹10,000; forced MIS intraday.
- 09:30–10:00 IST: default ₹10,000; product follows the Multyfi call.
- 10:00–15:30 IST: default ₹5,000; product follows the Multyfi call.

Quantity is calculated independently for each notification as `floor(window amount / maximum permitted buy price)`.

## Entry execution

Complete Multyfi notifications are read through Android NotificationListenerService. The app submits a regular NSE CASH LIMIT BUY immediately at the configured capped price instead of attempting a near-LTP entry GTT. An immediate strategy-monitor tick then reconciles actual fills and creates stop-loss GTT protection for filled quantity.

## Existing safety lifecycle

- Strict complete-signal parsing.
- Duplicate and overlapping-symbol protection.
- Surfshark Dedicated IP and exact Groww whitelist verification.
- Daily Groww authentication and DDPI gate.
- Actual-fill stop-loss GTT.
- Target exit after stop-loss cancellation is verified.
- Strict symbol-matched Multyfi early-exit handling.
- MIS timed exit.
- Local audit trail and boot/background recovery.

Auto-Buy remains OFF after installation. No live Groww order is submitted by CI.
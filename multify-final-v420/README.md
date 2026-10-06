# Multify Trader Pro v4.2.0 — Manual Entry Final

This payload starts from the latest v4.1.0 learning-30 source bundle and applies the auditable `patch.part*` delta before building.

Release changes:
- Adds a Manual Entry form for paid Equity **BUY** and **Book Profit** lifecycle events.
- Manual signals enter the same parser, NSE-master, authentication, risk, deterministic Shadow and optional Fast Track pipeline; they do not bypass live-trading gates.
- Moves time-critical notification processing/position monitoring into a sticky foreground execution service, with WorkManager retained only as recovery.
- Adds listener reconnect/watchdog counters for Vivo/Funtouch reliability.
- Keeps response sampling and daily/after-market learning active outside the notification-listener lifecycle.
- Retains the agreed rules: ₹5,000 averaging at each further 2% decline within the campaign budget, rolling latest 30 trading-day long target learning, 100%-maximum post-sell short retracement learning, and existing hard-risk overrides.

Build output is stable-signed using the signing material already present on the v4 release lineage and is produced by `.github/workflows/build-multify-final-v420.yml`.

# NSE Unified Scanner v1.0.0

Private S24 Ultra intraday scanner/trader. This is a standalone package (`com.suhas.nseunifiedscanner`) and does not replace or modify Multyfi AutoBuy.

## Core behavior
- Scans the Groww NSE CASH EQ universe every five minutes.
- Ranks the top three 30-minute momentum opportunities using VWAP, RSI, MACD acceleration, relative volume, one-hour momentum, pivot R1/R2 room, candle quality, spread, turnover, depth, circuit room and overall NSE breadth.
- A bounded online model replays every recommendation for 30 minutes and adapts the score threshold/weights. It never changes the hard +0.50% net objective, risk protection or 30-minute time exit.
- A recommendation can be displayed as WATCH while BUY remains disabled. The app does not force three live trades.
- One-click BUY uses the configured percentage of available Groww MIS margin (default 98%, configurable 50-100%), rechecks price/IP/authentication, reconciles actual fill, and then protects the position.
- Target price is recalculated from the actual fill and quantity to target +0.50% net after the published Groww/NSE intraday charge model plus a conservative slippage reserve.
- Protection attempts CASH MIS OCO; if unavailable/rejected it falls back to a broker SL-M plus app-monitored target. An unprotected fill triggers an emergency exit.
- One active position at a time. Maximum holding horizon 30 minutes and absolute app exit deadline 15:10 IST.

## Important limits
This is a trading tool, not a profit guarantee. The displayed hit rate is empirical and starts at zero. The 80% value is a selection objective; when evidence degrades the app tightens its threshold and can return WATCH/no-trade rather than inventing confidence.

PE and news are intentionally not hard-coded into v1 because the Groww Trading API does not expose a stable fundamentals/news endpoint. Market cap, 52-week position, circuits, breadth and live microstructure are available. A future optional official-event overlay can be added only when a stable authenticated source is available.

## Build
The CI workflow compiles with Java 17 / Android API 36, targets API 34 for stable long-running private sideload operation on Android 16, runs JVM tests and lint, builds the APK, installs it on an API-36 emulator, cold-launches it, checks the UI, and scans Logcat for crashes. No live Groww order is submitted in CI.

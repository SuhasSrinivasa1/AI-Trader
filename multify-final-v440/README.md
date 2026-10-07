# Multify Trader Pro v4.4.0 — Wave Capture + Simplified UI

- Wave-1 Up seed is the uploaded historical Excel only.
- Active Wave-1 Long learning window is the latest 30 calendar days, never the last 30 calls.
- Profitable realized Wave-1 returns are averaged per date so a multi-call date gets one vote.
- Wave 2–20 Up and every Down/short wave start from live observations.
- No historical short reconstruction/backfill is used for the active short average.
- A confirmed wave requires at least a 0.4% leg and a 0.4% reversal from the extreme.
- Raw wave states and observations persist in Room for Up/Down 1–20.
- The 0.4% detector is measurement only. Trading exits remain learned-arm + ₹1 trail.
- Navigation is simplified to Execution / Forecast / Settings.
- Shadow P&L and Live P&L remain visible on every tab.
- Existing deterministic risk/execution rules from v4.3 remain intact.

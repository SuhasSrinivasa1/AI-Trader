# Multyfi AutoBuy Pro v2.2.4

Budget selection is based on the Multyfi recommendation type, not notification time:

- Intraday/Intra day/MIS: Intraday budget and MIS LIMIT route.
- Swing: Swing budget and CNC entry GTT route.
- Ordinary or unlabelled equity: Swing budget and CNC entry GTT route.
- Multibagger: Multibagger budget and CNC entry GTT route.
- Free recommendation: Free budget; route still follows whether the notification explicitly says Intraday/MIS.

Existing on-device values migrate without reset:

- old 09:00–09:30 amount -> Intraday
- old 09:30–10:00 amount -> Swing
- old 10:00–15:30 amount -> Multibagger
- existing Free amount -> Free

Time remains the weekday/market-hours execution gate and supplies the entry cancellation cutoff. All v2.2.3 MIS/CNC stop-loss protection, daily Groww authentication, early exit handling, persistent armed preference and ₹0.10 price normalization remain unchanged.

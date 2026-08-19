from pathlib import Path
p=Path('unified-scanner/app/src/main/java/com/suhas/nseunifiedscanner/MainActivity.java')
s=p.read_text()
s=s.replace('BUY-qualified calls keep the official accuracy score. Ranks 4–10 remain lower-weight shadow learning. v1.2 additionally learns recovery-from-negative, HOD rejection, breakout confirmation and clear-path-to-target behaviour. Learning cannot override the +0.30% net objective, ₹2,000 executable-net profit lock, 30-minute time stop, liquidity, spread, R:R, protection or re-entry rules.','BUY-qualified calls keep the official +0.30% net accuracy score. Ranks 4–15 are forward shadow snapshots. v1.6 learns pre-spike pressure, 1-minute volume acceleration, compression, higher lows, VWAP location, recovery and HOD resistance. Late vertical spikes are penalized. Learning cannot override protection, liquidity, spread, clear-path, re-entry or 30-minute rules.')
s=s.replace('Shadow outcomes update model weights at 25% strength and never alter the headline hit-rate.','Shadow outcomes train at adaptive 8–20% weight and never alter the headline accuracy score.')
s=s.replace('target an estimated +0.50% net after current published charges','target an estimated +0.30% net after charges and the configured slippage reserve')
p.write_text(s)
print('v1.6 UI consistency fix applied')

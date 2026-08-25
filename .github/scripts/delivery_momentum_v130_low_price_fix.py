from pathlib import Path
p=Path('delivery-momentum/app/src/main/java/com/suhas/nsedeliverymomentum/DeliveryMomentumService.java')
s=p.read_text()
old='GrowwClient.Ohlc o=e.getValue();if(o.open<=0||o.last<20||o.high<=o.low)continue;'
new='GrowwClient.Ohlc o=e.getValue();if(o.open<=0||o.last<5||o.high<=o.low)continue;'
if old not in s: raise SystemExit('trajectory price-floor anchor missing')
p.write_text(s.replace(old,new))
assert 'o.last<5||o.high<=o.low' in p.read_text()
print('Trajectory engine now admits liquid quality stocks priced below ₹20; liquidity/turnover gates still apply')

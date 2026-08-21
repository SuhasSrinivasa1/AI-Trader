from pathlib import Path
p=Path('unified-scanner/app/src/main/java/com/suhas/nseunifiedscanner/ScannerEngine.java')
s=p.read_text()
old='double atrPct=f.atr>0?f.atr/entry*100.0:0.25;double targetFeasibility=TradeSetupLogic.clamp((atrPct*2.8)/Math.max(0.25,reqMove),0,1);'
new='double atrMovePct=f.atr>0?f.atr/entry*100.0:0.25;double targetFeasibility=TradeSetupLogic.clamp((atrMovePct*2.8)/Math.max(0.25,reqMove),0,1);'
if old not in s: raise SystemExit('v2 compile-fix anchor missing')
p.write_text(s.replace(old,new,1))
print('v2.0 compile fix applied')

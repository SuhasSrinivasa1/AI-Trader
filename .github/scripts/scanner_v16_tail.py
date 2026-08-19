from pathlib import Path
ROOT=Path('unified-scanner/app/src/main/java/com/suhas/nseunifiedscanner')

def rep(path,old,new):
    p=Path(path);s=p.read_text()
    if old not in s: raise SystemExit(f'v1.6 tail anchor missing in {p}: {old[:180]!r}')
    p.write_text(s.replace(old,new,1))

def opt(path,old,new):
    p=Path(path);s=p.read_text()
    if old in s:p.write_text(s.replace(old,new,1))

sp=ROOT/'ScannerEngine.java'; lp=ROOT/'LearningStore.java'; lip=ROOT/'LearningInsights.java'; mp=ROOT/'MainActivity.java'; up=ROOT/'UnifiedService.java'; gp=Path('unified-scanner/app/build.gradle')

rep(sp,
'''GrowwApi.Result<List<GrowwApi.Candle>> hr=GrowwApi.candles(token,r.growwSymbol,st.format(API_TIME),en.format(API_TIME),"5minute"); if(!hr.ok)continue;\n                String outcome=null;for(GrowwApi.Candle c:hr.value){boolean hitT=c.high>=r.target;boolean hitS=c.low<=r.stop;''',
'''GrowwApi.Result<List<GrowwApi.Candle>> hr=GrowwApi.candles(token,r.growwSymbol,st.format(API_TIME),en.format(API_TIME),"1minute"); if(!hr.ok)continue;\n                String outcome=null;for(GrowwApi.Candle c:hr.value){boolean hitT=c.high>=r.target;boolean hitS=c.low<=r.stop;''')

rep(sp,
'''for(int i=0;i<Math.min(10,recs.size());i++){Recommendation x=recs.get(i);if(i>=3||!x.qualified)insights.recordShadowIfNew(x);}''',
'''for(int i=0;i<Math.min(15,recs.size());i++){Recommendation x=recs.get(i);if(i>=3||!x.qualified)insights.recordShadowIfNew(x);}''')

rep(sp,
'''double entry,rsi,relVol,atr,oneHour,vwap,r1,r2,distR1,roomR2,wickRatio,dayPct,baseScore,sessionHod,hodDistancePct,hodDrawdownPct,recoveryPct,fromOpenPct;boolean crossedGreen,breakoutConfirmed,freshHodPressure,hodRejected;''',
'''double entry,rsi,relVol,atr,oneHour,vwap,r1,r2,distR1,roomR2,wickRatio,dayPct,baseScore,sessionHod,hodDistancePct,hodDrawdownPct,recoveryPct,fromOpenPct,earlyPressure,price3mPct,price5mPct,extension10mPct,volumeAccel,compressionPct,microBreakoutPct,rsi1m;boolean crossedGreen,breakoutConfirmed,freshHodPressure,hodRejected,preSpike,lateSpike,macd1mAccel,higherLows;''')

rep(lp,
'''static final String[] NAMES={"vwap","rsi","relvol","macd","momentum","breakout","liquidity","market","depth","range","time","hodroom","recovery","rejection"};\n    private static final double[] DEFAULT={0.92,0.55,0.78,0.72,0.62,0.58,0.68,0.55,0.35,0.35,0.45,0.62,0.52,0.68};''',
'''static final String[] NAMES={"vwap","rsi","relvol","macd","momentum","breakout","liquidity","market","depth","range","time","hodroom","recovery","rejection","earlypress","volaccel","compression","extension"};\n    private static final double[] DEFAULT={0.92,0.55,0.78,0.72,0.62,0.58,0.68,0.55,0.35,0.35,0.45,0.62,0.52,0.68,0.82,0.72,0.58,0.74};''')
opt(lp,'else if(s.rate>=86.0 && s.n>=50) minScore=Math.max(80,minScore-1);','else if(s.rate>=86.0 && s.n>=50) minScore=Math.max(76,minScore-1);')

rep(lip,
'''if(System.currentTimeMillis()-last<10*60_000L && Math.abs(r.entry-old)/Math.max(0.01,old)<0.003)return -1;''',
'''if(System.currentTimeMillis()-last<5*60_000L && Math.abs(r.entry-old)/Math.max(0.01,old)<0.002)return -1;''')

rep(up,
'''double target=ChargeModel.requiredSellPrice(fillPrice,filled,0.005,0.0007,rec.tick);''',
'''double target=ChargeModel.requiredSellPrice(fillPrice,filled,0.003,0.0006,rec.tick);''')

opt(mp,'5-minute adaptive intraday engine • HOD-aware • 30-minute horizon','1-minute pre-spike pressure • 5-minute confirmation • 30-minute horizon')
opt(mp,'ACCURACY SCORE • 30-MIN','0.30% NET ACCURACY • 30-MIN')
opt(mp,'TOP 3 • NEXT 30 MINUTES','EARLY RADAR • NEXT 30 MINUTES')
opt(mp,'A ranked Top 3 is shown whenever the discovery scan has enough data. BUY appears only when strict hard gates + learned quality threshold pass. Same stock may remain ranked on consecutive scans.','Ranks developing pressure BEFORE a vertical move using 1-minute volume acceleration, compression, VWAP location, higher lows and micro-breakout pressure. Completed spikes are penalized. BUY still requires hard execution/path gates.')
opt(mp,'NET OBJECTIVE +0.50% after estimated Groww/NSE charges • actual target recalculated from fill + quantity','NET OBJECTIVE +0.30% after estimated Groww/NSE charges • actual target recalculated from fill + quantity')
opt(mp,'+0.50% net objective','+0.30% net objective')
opt(mp,'+0.50% executable-net profit lock','+0.30% primary target')
opt(mp,
'''c.addView(txt("Setup "+setup+" • prior HOD "+(hod>0?("₹"+money(hod)):"—")+" • target-clearance "+String.format(Locale.US,"%+.2f%%",hodRoom)+" • recovery "+String.format(Locale.US,"%.2f%%",recov),11,r.features.optBoolean("clearPath",true)?MUTED:RED,false));c.addView(space(8));''',
'''double ep=r.features.optDouble("earlyPressure",0),va=r.features.optDouble("volumeAccel",0),p5=r.features.optDouble("price5mPct",0);boolean late=r.features.optBoolean("lateSpike",false);c.addView(txt("Setup "+setup+" • EARLY "+String.format(Locale.US,"%.0f/100",ep)+" • vol accel "+String.format(Locale.US,"%.2fx",va)+" • 5m "+String.format(Locale.US,"%+.2f%%",p5)+(late?" • LATE SPIKE ✗":""),11,late?RED:ACCENT,false));c.addView(txt("prior HOD "+(hod>0?("₹"+money(hod)):"—")+" • target-clearance "+String.format(Locale.US,"%+.2f%%",hodRoom)+" • recovery "+String.format(Locale.US,"%.2f%%",recov),11,r.features.optBoolean("clearPath",true)?MUTED:RED,false));c.addView(space(8));''')
opt(mp,'v1.5.0 • standalone package com.suhas.nseunifiedscanner','v1.6.0 • standalone package com.suhas.nseunifiedscanner')

rep(gp,"versionCode 150\n        versionName '1.5.0'","versionCode 160\n        versionName '1.6.0'")
print('v1.6 tail patch applied')

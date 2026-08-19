from pathlib import Path

ROOT=Path('unified-scanner/app/src/main/java/com/suhas/nseunifiedscanner')

def rep(path,old,new):
    p=Path(path);s=p.read_text()
    if old not in s: raise SystemExit(f'v1.5 anchor missing in {p}: {old[:180]!r}')
    p.write_text(s.replace(old,new,1))

def opt(path,old,new):
    p=Path(path);s=p.read_text()
    if old in s:p.write_text(s.replace(old,new,1))

sp=ROOT/'ScannerEngine.java'
lip=ROOT/'LearningInsights.java'
mp=ROOT/'MainActivity.java'
gp=Path('unified-scanner/app/build.gradle')

# ---------------------------------------------------------------------------
# 1) Reduce full-universe REST pressure. LTP stays fresh every scan; the broad
#    OHLC snapshot is cached for 15 minutes and deep candidates still use fresh
#    candles + quotes. This prevents 2,600-stock scans from starving themselves.
# ---------------------------------------------------------------------------
rep(sp,
'''    private final LearningStore learning;\n    private final LearningInsights insights;''',
'''    private final LearningStore learning;\n    private final LearningInsights insights;\n    private final Map<String,GrowwApi.Ohlc> broadOhlcCache=new HashMap<>();\n    private long broadOhlcCacheMs=0L;''')

rep(sp,
'''            resolvePending(token);\n            resolveShadowPending(token);\n            List<Instrument> universe=loadUniverse();''',
'''            resolvePending(token);\n            resolveShadowPending(token);\n            insights.repairBootstrapModelIfNeeded();\n            List<Instrument> universe=loadUniverse();''')

rep(sp,
'''            Map<String,Double> ltps=new HashMap<>(); Map<String,GrowwApi.Ohlc> ohlcs=new HashMap<>();\n            int positive=0, valid=0;\n            for(int i=0;i<universe.size();i+=50){\n                List<Instrument> chunk=universe.subList(i,Math.min(i+50,universe.size())); List<String> symbols=new ArrayList<>(); for(Instrument x:chunk)symbols.add(x.symbol);\n                GrowwApi.Result<Map<String,Double>> lr=GrowwApi.ltpBatch(token,symbols); if(lr.ok)ltps.putAll(lr.value);\n                GrowwApi.Result<Map<String,GrowwApi.Ohlc>> or=GrowwApi.ohlcBatch(token,symbols); if(or.ok)ohlcs.putAll(or.value);\n            }''',
'''            Map<String,Double> ltps=new HashMap<>(); Map<String,GrowwApi.Ohlc> ohlcs=new HashMap<>();\n            int positive=0, valid=0;long nowMs=System.currentTimeMillis();boolean refreshBroadOhlc=broadOhlcCache.isEmpty()||nowMs-broadOhlcCacheMs>=15*60_000L;\n            for(int i=0;i<universe.size();i+=50){\n                List<Instrument> chunk=universe.subList(i,Math.min(i+50,universe.size())); List<String> symbols=new ArrayList<>(); for(Instrument x:chunk)symbols.add(x.symbol);\n                GrowwApi.Result<Map<String,Double>> lr=GrowwApi.ltpBatch(token,symbols); if(lr.ok)ltps.putAll(lr.value);\n                if(refreshBroadOhlc){GrowwApi.Result<Map<String,GrowwApi.Ohlc>> or=GrowwApi.ohlcBatch(token,symbols); if(or.ok)broadOhlcCache.putAll(or.value);}\n            }\n            if(refreshBroadOhlc&&!broadOhlcCache.isEmpty())broadOhlcCacheMs=nowMs;ohlcs.putAll(broadOhlcCache);''')

# ---------------------------------------------------------------------------
# 2) Discovery was too narrow. Keep execution gates strict, but let the deep
#    ranker see relative-strength, VWAP-continuation and early recovery names.
# ---------------------------------------------------------------------------
rep(sp,
'''        if(entry<vwap*0.996||rsi<44||rsi>80||oneHour<-0.35||relVol<0.60||roomR2<0.15||distR1>1.10||distR1<-1.50||wickRatio>3.0)return null;\n        if(!macd.bullish&&!recoveryDiscovery&&macd.hist<macd.prevHist)return null;''',
'''        boolean relativeStrengthDiscovery=p.dayPct>=0.65&&entry>=vwap*0.994;\n        if(entry<vwap*0.992||rsi<40||rsi>82||oneHour<-0.55||relVol<0.40||roomR2<-0.20||distR1>2.20||distR1<-2.80||wickRatio>4.0)return null;\n        if(!macd.bullish&&!recoveryDiscovery&&!relativeStrengthDiscovery&&macd.hist<macd.prevHist)return null;''')

# ---------------------------------------------------------------------------
# 3) Execution qualification: independent setup pathways. Classic R1 proximity
#    becomes a score feature, not a universal veto. HOD clear-path, liquidity,
#    spread, target room and protection remain hard safety requirements.
# ---------------------------------------------------------------------------
old='''double indicativeTarget=GrowwApi.roundToTick(entry*1.0070,f.instrument.tick,true);\n        // Regime-aware thresholds: a healthy market can qualify earlier; a weak market must prove more volume/momentum.\n        double relFloor=breadth>=58.0?1.18:(breadth<40.0?1.40:1.28);\n        double momFloor=breadth>=58.0?0.34:(breadth<40.0?0.55:0.44);\n        double spreadFloor=breadth>=58.0?0.20:0.18;\n        boolean momentumHard=entry>f.vwap && f.rsi>=54 && f.rsi<=72 && f.relVol>=relFloor && f.macd.hist>0 && f.macd.hist>=f.macd.prevHist && f.oneHour>=momFloor && f.oneHour<=4.0 && spreadPct<=spreadFloor && turnover>=55_000_000d && roomR2>=0.68 && distR1>=-0.60 && distR1<=0.40 && circuitRoom>=0.80;\n        boolean recoveryHard=entry>f.vwap && TradeSetupLogic.recoverySetup(f.crossedGreen,f.recoveryPct,f.fromOpenPct,f.rsi,f.relVol,f.macd.hist,f.macd.prevHist,f.oneHour,spreadPct,turnover,roomR2,circuitRoom,breadth,depthRatio);\n        boolean volumeIgnitionHard=entry>=f.vwap*0.999 && TradeSetupLogic.volumeIgnitionSetup(f.rsi,f.relVol,f.macd.hist,f.macd.prevHist,f.oneHour,spreadPct,turnover,roomR2,circuitRoom,breadth,depthRatio,f.wickRatio);\n        boolean clearPath=TradeSetupLogic.clearPath(entry,indicativeTarget,f.sessionHod,f.hodRejected,f.breakoutConfirmed,f.freshHodPressure);\n        boolean hard=(momentumHard||recoveryHard||volumeIgnitionHard)&&clearPath;\n        double liquidity=Math.min(1.0,turnover/300_000_000d); double market=AdaptiveModel.clamp((breadth-40)/35.0,0,1);'''
new='''double indicativeTarget=GrowwApi.roundToTick(entry*1.0070,f.instrument.tick,true);\n        // v1.5: weak breadth must not automatically kill strong individual leaders.\n        double relFloor=breadth>=58.0?1.10:(breadth<40.0?1.18:1.15);\n        double momFloor=breadth>=58.0?0.20:(breadth<40.0?0.25:0.28);\n        double spreadFloor=0.20;\n        boolean structuralRoom=roomR2>=0.35||f.breakoutConfirmed||f.freshHodPressure;\n        boolean momentumHard=entry>f.vwap && f.rsi>=52 && f.rsi<=74 && f.relVol>=relFloor && f.macd.hist>0 && f.macd.hist>=f.macd.prevHist && f.oneHour>=momFloor && f.oneHour<=4.5 && spreadPct<=spreadFloor && turnover>=75_000_000d && structuralRoom && circuitRoom>=0.80;\n        boolean recoveryClassic=entry>f.vwap && TradeSetupLogic.recoverySetup(f.crossedGreen,f.recoveryPct,f.fromOpenPct,f.rsi,f.relVol,f.macd.hist,f.macd.prevHist,f.oneHour,spreadPct,turnover,roomR2,circuitRoom,breadth,depthRatio);\n        boolean recoveryFast=entry>=f.vwap*0.999 && f.crossedGreen && f.recoveryPct>=1.10 && f.recoveryPct<=9.0 && f.fromOpenPct>=0.15 && f.rsi>=50 && f.rsi<=72 && f.relVol>=1.05 && (f.macd.hist>0||f.macd.hist>=f.macd.prevHist) && f.oneHour>=0.05 && spreadPct<=0.20 && turnover>=75_000_000d && structuralRoom && circuitRoom>=0.80 && (breadth>=30.0||depthRatio>=0.56);\n        boolean recoveryHard=recoveryClassic||recoveryFast;\n        boolean volumeIgnitionHard=entry>=f.vwap*0.999 && TradeSetupLogic.volumeIgnitionSetup(f.rsi,f.relVol,f.macd.hist,f.macd.prevHist,f.oneHour,spreadPct,turnover,Math.max(roomR2,0.68),circuitRoom,breadth,depthRatio,f.wickRatio);\n        boolean relativeStrengthHard=breadth<48.0 && f.dayPct>=0.75 && entry>=f.vwap*1.0005 && f.rsi>=52 && f.rsi<=74 && f.relVol>=1.05 && (f.macd.hist>0||f.macd.hist>=f.macd.prevHist) && f.oneHour>=0.12 && spreadPct<=0.20 && turnover>=100_000_000d && structuralRoom && circuitRoom>=0.80 && depthRatio>=0.48;\n        boolean vwapTrendHard=entry>=f.vwap*1.0010 && f.rsi>=52 && f.rsi<=72 && f.relVol>=1.10 && f.macd.hist>=f.macd.prevHist && f.oneHour>=0.18 && spreadPct<=0.18 && turnover>=100_000_000d && structuralRoom && circuitRoom>=0.80 && depthRatio>=0.50;\n        boolean clearPath=TradeSetupLogic.clearPath(entry,indicativeTarget,f.sessionHod,f.hodRejected,f.breakoutConfirmed,f.freshHodPressure);\n        boolean hard=(momentumHard||recoveryHard||volumeIgnitionHard||relativeStrengthHard||vwapTrendHard)&&clearPath;\n        double liquidity=Math.min(1.0,turnover/300_000_000d); double market=AdaptiveModel.clamp((breadth-40)/35.0,0,1);'''
rep(sp,old,new)

rep(sp,
'''features.put("setupType",recoveryHard?"RECOVERY":(volumeIgnitionHard?"VOLUME IGNITION":(f.breakoutConfirmed||f.freshHodPressure?"HOD MOMENTUM":"MOMENTUM")));''',
'''features.put("setupType",recoveryHard?"RECOVERY":(volumeIgnitionHard?"VOLUME IGNITION":(relativeStrengthHard?"RELATIVE STRENGTH":(vwapTrendHard?"VWAP TREND":(f.breakoutConfirmed||f.freshHodPressure?"HOD MOMENTUM":"MOMENTUM")))));''')

rep(sp,
'''double score=f.baseScore + Math.min(8,liquidity*8) + Math.max(-4,Math.min(5,(depthRatio-0.5)*12)) - Math.max(0,(spreadPct-0.08)*20) - Math.max(0,(f.rsi-68)*1.6) - Math.max(0,(f.wickRatio-0.7)*3) + (recoveryHard?5:0) + (volumeIgnitionHard?5:0) + (f.breakoutConfirmed?4:0) - (f.hodRejected&&!f.breakoutConfirmed?10:0) - (!clearPath?12:0);''',
'''double score=f.baseScore + Math.min(8,liquidity*8) + Math.max(-4,Math.min(5,(depthRatio-0.5)*12)) - Math.max(0,(spreadPct-0.08)*20) - Math.max(0,(f.rsi-70)*1.4) - Math.max(0,(f.wickRatio-0.9)*2.5) + (recoveryHard?6:0) + (volumeIgnitionHard?5:0) + (relativeStrengthHard?6:0) + (vwapTrendHard?4:0) + (f.breakoutConfirmed?4:0) - (f.hodRejected&&!f.breakoutConfirmed?10:0) - (!clearPath?12:0);''')

# Bootstrap must be able to generate primary outcomes. The untrained model no
# longer vetoes a technically valid setup. After calibration it becomes a gate.
rep(sp,
'''boolean qualified=hard && score>=minScore && (modelN<30?probability>=0.70:probability>=0.80);''',
'''int effectiveMin=modelN<30?Math.min(minScore,78):minScore;double modelGate=modelN<30?0.0:(modelN<60?0.62:0.72);boolean qualified=hard && score>=effectiveMin && (modelN<30||probability>=modelGate);''')
rep(sp,
'''r.reason=reason(r,hard,minScore,modelN); return r;''',
'''r.reason=reason(r,hard,effectiveMin,modelN); return r;''')

# Show the real effective floor in the dashboard while bootstrap is active.
rep(sp,
'''result.recommendations=recs; result.success=stats; result.minScore=minScore; result.scanned=universe.size(); result.prefiltered=pre.size();''',
'''result.recommendations=recs; result.success=stats; result.minScore=stats.n<30?Math.min(minScore,78):minScore; result.scanned=universe.size(); result.prefiltered=pre.size();''')

# ---------------------------------------------------------------------------
# 4) Shadow learning should inform, not dominate. 58 low-quality shadow samples
#    at 25% weight can overwhelm a model that has zero primary outcomes. Reduce
#    early weight and perform one safe bootstrap rebase while preserving history.
# ---------------------------------------------------------------------------
rep(lip,
'''if(n==1 && !"AMBIGUOUS".equals(outcome)) AdaptiveModel.update(context,features,"SUCCESS".equals(outcome)?1.0:0.0,0.25);''',
'''if(n==1 && !"AMBIGUOUS".equals(outcome)){int primary=new LearningStore(context).stats().n;double weight=primary<30?0.08:primary<60?0.15:0.20;AdaptiveModel.update(context,features,"SUCCESS".equals(outcome)?1.0:0.0,weight);}''')

repair='''\n    synchronized void repairBootstrapModelIfNeeded(){\n        try{\n            LearningStore.Stats primary=new LearningStore(context).stats();if(primary.n>=5)return;\n            android.content.SharedPreferences guard=context.getSharedPreferences("scanner_prefs",Context.MODE_PRIVATE);if(guard.getBoolean("v15_bootstrap_repaired",false))return;\n            int shadowResolved=0;try(SQLiteDatabase db=open();Cursor c=db.rawQuery("SELECT COUNT(*) FROM shadow_samples WHERE status IN ('SUCCESS','FAIL','TIMEOUT')",null)){if(c.moveToFirst())shadowResolved=c.getInt(0);}\n            if(shadowResolved<20)return;\n            context.getSharedPreferences("model_weights",Context.MODE_PRIVATE).edit().clear().apply();\n            int floor=guard.getInt("min_score",82);android.content.SharedPreferences.Editor e=guard.edit().putBoolean("v15_bootstrap_repaired",true);if(floor>78)e.putInt("min_score",78);e.apply();\n            new LearningStore(context).audit("BOOTSTRAP","v1.5 re-based model defaults after "+shadowResolved+" shadow outcomes and "+primary.n+" primary outcomes; raw history preserved");\n        }catch(Exception ignore){}\n    }\n\n'''
rep(lip,'\n    private long[] todayBounds(){',repair+'    private long[] todayBounds(){')

# ---------------------------------------------------------------------------
# 5) UI wording: make bootstrap behaviour explicit and list the new setup types.
# ---------------------------------------------------------------------------
opt(mp,
'''10 is an opportunity goal, not a forced-trade quota. Accuracy and clear-path rules remain higher priority.''',
'''10 is an opportunity goal, not a forced-trade quota. During the first 30 primary outcomes the model learns but does not veto technically valid setups; hard risk/path gates remain mandatory.''')
opt(mp,'v1.4.0 • standalone package com.suhas.nseunifiedscanner','v1.5.0 • standalone package com.suhas.nseunifiedscanner')

# ---------------------------------------------------------------------------
# Version bump after v1.4 patch.
# ---------------------------------------------------------------------------
rep(gp,"versionCode 140\n        versionName '1.4.0'","versionCode 150\n        versionName '1.5.0'")

print('v1.5 bootstrap qualification + faster scanner patch applied')

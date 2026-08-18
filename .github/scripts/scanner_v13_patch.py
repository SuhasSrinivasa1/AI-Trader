from pathlib import Path
import re

ROOT=Path('unified-scanner/app/src/main/java/com/suhas/nseunifiedscanner')

def replace_once(path, old, new):
    p=Path(path); s=p.read_text()
    if old not in s:
        raise SystemExit(f'v1.3 anchor missing in {p}: {old[:140]!r}')
    p.write_text(s.replace(old,new,1))

def regex_once(path, pattern, repl, flags=0):
    p=Path(path); s=p.read_text()
    out,n=re.subn(pattern,repl,s,count=1,flags=flags)
    if n!=1:
        raise SystemExit(f'v1.3 regex anchor missing in {p}: {pattern[:140]!r} (n={n})')
    p.write_text(out)

# ---------------------------------------------------------------------------
# ScannerEngine: more discovery, market-regime thresholds, volume ignition,
# and a true after-hours replay-only mode.
# ---------------------------------------------------------------------------
sp=ROOT/'ScannerEngine.java'
replace_once(sp,'private static final int TOP_PREFILTER=40;\n    private static final int TOP_QUOTE=22;',
                'private static final int TOP_PREFILTER=48;\n    private static final int TOP_QUOTE=26;')

old='''double indicativeTarget=GrowwApi.roundToTick(entry*1.0070,f.instrument.tick,true);\n        boolean momentumHard=entry>f.vwap && f.rsi>=55 && f.rsi<=72 && f.relVol>=1.30 && f.macd.hist>0 && f.macd.hist>=f.macd.prevHist && f.oneHour>=0.45 && f.oneHour<=4.0 && spreadPct<=0.22 && turnover>=50_000_000d && roomR2>=0.68 && distR1>=-0.55 && distR1<=0.38 && circuitRoom>=0.80;\n        boolean recoveryHard=entry>f.vwap && TradeSetupLogic.recoverySetup(f.crossedGreen,f.recoveryPct,f.fromOpenPct,f.rsi,f.relVol,f.macd.hist,f.macd.prevHist,f.oneHour,spreadPct,turnover,roomR2,circuitRoom,breadth,depthRatio);\n        boolean clearPath=TradeSetupLogic.clearPath(entry,indicativeTarget,f.sessionHod,f.hodRejected,f.breakoutConfirmed,f.freshHodPressure);\n        boolean hard=(momentumHard||recoveryHard)&&clearPath;\n        double liquidity=Math.min(1.0,turnover/300_000_000d); double market=AdaptiveModel.clamp((breadth-40)/35.0,0,1);'''
new='''double indicativeTarget=GrowwApi.roundToTick(entry*1.0070,f.instrument.tick,true);\n        // Regime-aware thresholds: a healthy market can qualify earlier; a weak market must prove more volume/momentum.\n        double relFloor=breadth>=58.0?1.18:(breadth<40.0?1.40:1.28);\n        double momFloor=breadth>=58.0?0.34:(breadth<40.0?0.55:0.44);\n        double spreadFloor=breadth>=58.0?0.20:0.18;\n        boolean momentumHard=entry>f.vwap && f.rsi>=54 && f.rsi<=72 && f.relVol>=relFloor && f.macd.hist>0 && f.macd.hist>=f.macd.prevHist && f.oneHour>=momFloor && f.oneHour<=4.0 && spreadPct<=spreadFloor && turnover>=55_000_000d && roomR2>=0.68 && distR1>=-0.60 && distR1<=0.40 && circuitRoom>=0.80;\n        boolean recoveryHard=entry>f.vwap && TradeSetupLogic.recoverySetup(f.crossedGreen,f.recoveryPct,f.fromOpenPct,f.rsi,f.relVol,f.macd.hist,f.macd.prevHist,f.oneHour,spreadPct,turnover,roomR2,circuitRoom,breadth,depthRatio);\n        boolean volumeIgnitionHard=entry>=f.vwap*0.999 && TradeSetupLogic.volumeIgnitionSetup(f.rsi,f.relVol,f.macd.hist,f.macd.prevHist,f.oneHour,spreadPct,turnover,roomR2,circuitRoom,breadth,depthRatio,f.wickRatio);\n        boolean clearPath=TradeSetupLogic.clearPath(entry,indicativeTarget,f.sessionHod,f.hodRejected,f.breakoutConfirmed,f.freshHodPressure);\n        boolean hard=(momentumHard||recoveryHard||volumeIgnitionHard)&&clearPath;\n        double liquidity=Math.min(1.0,turnover/300_000_000d); double market=AdaptiveModel.clamp((breadth-40)/35.0,0,1);'''
replace_once(sp,old,new)

replace_once(sp,
'''features.put("setupType",recoveryHard?"RECOVERY":(f.breakoutConfirmed||f.freshHodPressure?"HOD MOMENTUM":"MOMENTUM"));''',
'''features.put("setupType",recoveryHard?"RECOVERY":(volumeIgnitionHard?"VOLUME IGNITION":(f.breakoutConfirmed||f.freshHodPressure?"HOD MOMENTUM":"MOMENTUM")));''')

replace_once(sp,
'''double score=f.baseScore + Math.min(8,liquidity*8) + Math.max(-4,Math.min(5,(depthRatio-0.5)*12)) - Math.max(0,(spreadPct-0.08)*20) - Math.max(0,(f.rsi-68)*1.6) - Math.max(0,(f.wickRatio-0.7)*3) + (recoveryHard?5:0) + (f.breakoutConfirmed?4:0) - (f.hodRejected&&!f.breakoutConfirmed?10:0) - (!clearPath?12:0);''',
'''double score=f.baseScore + Math.min(8,liquidity*8) + Math.max(-4,Math.min(5,(depthRatio-0.5)*12)) - Math.max(0,(spreadPct-0.08)*20) - Math.max(0,(f.rsi-68)*1.6) - Math.max(0,(f.wickRatio-0.7)*3) + (recoveryHard?5:0) + (volumeIgnitionHard?5:0) + (f.breakoutConfirmed?4:0) - (f.hodRejected&&!f.breakoutConfirmed?10:0) - (!clearPath?12:0);''')

insert='''\n    ScanResult afterHoursMaintenance(String token) {\n        ScanResult result=new ScanResult(); result.scanMs=System.currentTimeMillis();\n        result.marketLabel="CLOSED / replay-learning";\n        result.error="";\n        try {\n            if(token!=null&&!token.isEmpty()){ resolvePending(token); resolveShadowPending(token); }\n            result.success=learning.stats();\n            result.minScore=context.getSharedPreferences("scanner_prefs",Context.MODE_PRIVATE).getInt("min_score",82);\n            result.recommendations=new ArrayList<>();\n            saveState(result);\n            learning.audit("AFTER_HOURS","Market closed • replay-learning only • no actionable recommendations");\n        } catch(Exception e) {\n            result.error=e.getMessage()==null?e.getClass().getSimpleName():e.getMessage();\n            saveState(result);\n        }\n        return result;\n    }\n\n'''
replace_once(sp,'\n    private FeatureCandidate features(PreCandidate p,List<GrowwApi.Candle> candles,double breadth){',insert+'    private FeatureCandidate features(PreCandidate p,List<GrowwApi.Candle> candles,double breadth){')

# ---------------------------------------------------------------------------
# LearningInsights: pipeline counters for the daily quality goal.
# ---------------------------------------------------------------------------
lip=ROOT/'LearningInsights.java'
pipeline='''\n    synchronized PipelineStats pipelineStats(){\n        PipelineStats s=new PipelineStats();long[] b=todayBounds();\n        String[] args={String.valueOf(b[0]),String.valueOf(b[1])};\n        try(SQLiteDatabase db=open();Cursor c=db.rawQuery("SELECT COUNT(*),SUM(CASE WHEN status='PENDING' THEN 1 ELSE 0 END),SUM(CASE WHEN status='SUCCESS' THEN 1 ELSE 0 END),SUM(CASE WHEN status='FAIL' THEN 1 ELSE 0 END),SUM(CASE WHEN status='TIMEOUT' THEN 1 ELSE 0 END) FROM recommendations WHERE scan_ms>=? AND scan_ms<?",args)){\n            if(c.moveToFirst()){s.qualified=c.getInt(0);s.pending=c.isNull(1)?0:c.getInt(1);s.hits=c.isNull(2)?0:c.getInt(2);s.stops=c.isNull(3)?0:c.getInt(3);s.timeouts=c.isNull(4)?0:c.getInt(4);}\n        }catch(Exception ignore){}\n        try(SQLiteDatabase db=open();Cursor c=db.rawQuery("SELECT COUNT(*) FROM shadow_samples WHERE scan_ms>=? AND scan_ms<?",args)){if(c.moveToFirst())s.shadowObserved=c.getInt(0);}catch(Exception ignore){}\n        s.observed=s.qualified+s.shadowObserved;\n        return s;\n    }\n\n'''
replace_once(lip,'\n    private long[] todayBounds(){',pipeline+'    private long[] todayBounds(){')
replace_once(lip,'    static final class ShadowStats{int resolvedToday,hitsToday,pending;}\n}',
'''    static final class ShadowStats{int resolvedToday,hitsToday,pending;}\n    static final class PipelineStats{int observed,shadowObserved,qualified,pending,hits,stops,timeouts;}\n}''')

# ---------------------------------------------------------------------------
# UnifiedService: after-hours is never actionable, LIVE auto-disarms, and no
# stale evening scan can look like a live NSE feed.
# ---------------------------------------------------------------------------
up=ROOT/'UnifiedService.java'
replace_once(up,
'''if(!manual && !ScannerEngine.marketHoursNow()) { setStatus("Market closed • next scan during NSE hours"); return; }\n            String token=ensureToken(false);''',
'''if(!ScannerEngine.marketHoursNow()) {\n                prefs().edit().putBoolean("live_armed",false).putBoolean("market_open",false).putBoolean("nse_feed_ok",false).putLong("nse_feed_checked_ms",System.currentTimeMillis()).apply();\n                String maintenanceToken=ensureToken(false);\n                if(!maintenanceToken.isEmpty()) scanner.afterHoursMaintenance(maintenanceToken);\n                setStatus("Market closed • replay-learning mode • LIVE disarmed");\n                return;\n            }\n            prefs().edit().putBoolean("market_open",true).apply();\n            String token=ensureToken(false);''')

replace_once(up,
'''private final Runnable monitorLoop=new Runnable(){@Override public void run(){\n        if(monitoring.compareAndSet(false,true)) tradeWork.execute(()->{try{monitorActive();}finally{monitoring.set(false);}});''',
'''private final Runnable monitorLoop=new Runnable(){@Override public void run(){\n        if(!ScannerEngine.marketHoursNow() && ActiveTrade.load(UnifiedService.this)==null && prefs().getBoolean("live_armed",false)) prefs().edit().putBoolean("live_armed",false).apply();\n        if(monitoring.compareAndSet(false,true)) tradeWork.execute(()->{try{monitorActive();}finally{monitoring.set(false);}});''')

# ---------------------------------------------------------------------------
# Boot receiver: never restore the live-trading arm after a reboot. Active
# position recovery still starts the service and keeps broker protection alive.
# ---------------------------------------------------------------------------
bp=ROOT/'BootReceiver.java'
replace_once(bp,
'''@Override public void onReceive(Context context, Intent intent) {\n        boolean needsRecovery=ActiveTrade.load(context)!=null;''',
'''@Override public void onReceive(Context context, Intent intent) {\n        context.getSharedPreferences("scanner_prefs",Context.MODE_PRIVATE).edit().putBoolean("live_armed",false).apply();\n        boolean needsRecovery=ActiveTrade.load(context)!=null;''')

# ---------------------------------------------------------------------------
# UI: daily goal, honest calibration, market-closed status, and a concise
# rejection checklist. WATCH targets remain indicative only.
# ---------------------------------------------------------------------------
mp=ROOT/'MainActivity.java'
replace_once(mp,
'''private LinearLayout body,recs,hits;private TextView successRate,successSub,market,status,scanMeta,active,connectivity,historySummary,learningMeta;private Switch liveSwitch;''',
'''private LinearLayout body,recs,hits;private TextView successRate,successSub,dailyGoal,market,status,scanMeta,active,connectivity,historySummary,learningMeta;private Switch liveSwitch;''')

replace_once(mp,
'''body.addView(perf);\n        body.addView(space(10));''',
'''body.addView(perf);\n        body.addView(space(10));\n\n        LinearLayout goal=card();goal.addView(txt("TODAY • QUALITY GOAL 10",12,ACCENT,true));dailyGoal=txt("Observed 0 • Qualified 0 • Hits 0 • Pending 0",13,TEXT,true);goal.addView(dailyGoal);goal.addView(txt("10 is an opportunity goal, not a forced-trade quota. Accuracy and clear-path rules remain higher priority.",11,MUTED,false));body.addView(goal);\n        body.addView(space(10));''')

replace_once(mp,
'''renderHistory();renderConnectivity();LearningInsights.ShadowStats sh=insights.shadowStats();''',
'''LearningInsights.PipelineStats pipe=insights.pipelineStats();dailyGoal.setText("Observed "+pipe.observed+" • Qualified "+pipe.qualified+"/10 • Hits "+pipe.hits+" • Pending "+pipe.pending+" • Stops "+pipe.stops+" • Timeouts "+pipe.timeouts);\n        renderHistory();renderConnectivity();LearningInsights.ShadowStats sh=insights.shadowStats();''')

replace_once(mp,
'''String a=api&&apiAge<8*60*60_000L?"✅ CONNECTED":"⚠ AUTH / CHECK REQUIRED";String i=ip==1&&ipAge<30*60_000L?"✅ MATCHED":ip==-1?"❌ MISMATCH":"○ NOT VERIFIED";String f=feed&&feedAge<7*60_000L?"✅ LIVE":"⚠ STALE / WAITING";connectivity.setText("Groww API  "+a+"\\nStatic IP  "+i+"\\nNSE feed  "+f+"\\nGreen is shown only after an actual API/feed check; the IP value itself is never displayed.");''',
'''String a=api&&apiAge<8*60*60_000L?"✅ CONNECTED":"⚠ AUTH / CHECK REQUIRED";String i=ip==1&&ipAge<30*60_000L?"✅ MATCHED":ip==-1?"❌ MISMATCH":"○ NOT VERIFIED";boolean open=ScannerEngine.marketHoursNow();String f=!open?"○ MARKET CLOSED":feed&&feedAge<7*60_000L?"✅ LIVE":"⚠ STALE / WAITING";connectivity.setText("Groww API  "+a+"\\nStatic IP  "+i+"\\nNSE feed  "+f+"\\nGreen LIVE is shown only during NSE market hours after a fresh feed check.");''')

# De-emphasize early model probability. The probability exists internally but
# is not presented as authoritative before 30 resolved primary samples.
replace_once(mp,
'''c.addView(txt(String.format(Locale.US,"Score %.0f/100  •  model %.0f%%  •  max 30 min",r.score,r.probability*100),12,MUTED,false));c.addView(space(8));''',
'''LearningStore.Stats ms=learning.stats();String modelLabel=ms.n<30?("calibration "+ms.n+"/30"):(String.format(Locale.US,"model %.0f%%",r.probability*100));c.addView(txt(String.format(Locale.US,"Score %.0f/100  •  %s  •  max 30 min",r.score,modelLabel),12,MUTED,false));c.addView(space(8));''')

replace_once(mp,
'''c.addView(space(6));c.addView(txt(r.reason,11,r.qualified?GREEN:AMBER,false));c.addView(space(8));''',
'''c.addView(space(6));if(!r.qualified)c.addView(txt(gateChecklist(r,st.minScore),11,MUTED,false));c.addView(txt(r.reason,11,r.qualified?GREEN:AMBER,false));c.addView(space(8));''')

check_method='''\n    private String gateChecklist(ScannerEngine.Recommendation r,int minScore){\n        StringBuilder b=new StringBuilder("WHY "+(r.qualified?"QUALIFIED":"WATCH")+" • ");\n        b.append(r.entry>=r.vwap?"✓VWAP ":"✗VWAP ");\n        b.append(r.relVol>=1.20?"✓VOL ":"✗VOL ");\n        b.append(r.rsi>=52&&r.rsi<=73?"✓RSI ":"✗RSI ");\n        b.append(r.features.optBoolean("clearPath",true)?"✓PATH ":"✗PATH ");\n        b.append(r.features.optBoolean("hodRejected",false)?"✗HOD-REJECT ":"✓HOD ");\n        b.append(r.score>=minScore?"✓SCORE":"✗SCORE");\n        if(!r.qualified)b.append(" • indicative entry/target/SL only");\n        return b.toString();\n    }\n\n'''
replace_once(mp,'\n    private void details(ScannerEngine.Recommendation r){',check_method+'    private void details(ScannerEngine.Recommendation r){')

replace_once(mp,'v1.2.0 • standalone package com.suhas.nseunifiedscanner','v1.3.0 • standalone package com.suhas.nseunifiedscanner')
replace_once(mp,'Live mode only enables the BUY button for scanner-qualified setups. Entry is still blocked outside 09:15–14:40 IST,','Live mode only enables the BUY button for scanner-qualified setups. LIVE automatically disarms when the market closes and after a reboot. Entry is still blocked outside 09:15–14:40 IST,')

# ---------------------------------------------------------------------------
# Version.
# ---------------------------------------------------------------------------
gp=Path('unified-scanner/app/build.gradle')
replace_once(gp,"versionCode 110\n        versionName '1.1.0'","versionCode 130\n        versionName '1.3.0'")

print('v1.3 patch applied')

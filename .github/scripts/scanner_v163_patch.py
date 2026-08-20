from pathlib import Path
import re

ROOT=Path('unified-scanner/app/src/main/java/com/suhas/nseunifiedscanner')
TEST=Path('unified-scanner/app/src/test/java/com/suhas/nseunifiedscanner')
sp=ROOT/'ScannerEngine.java'; gpapi=ROOT/'GrowwApi.java'; lp=ROOT/'LearningStore.java'; mp=ROOT/'MainActivity.java'; gp=Path('unified-scanner/app/build.gradle')

def must(path, old, new):
    p=Path(path); s=p.read_text()
    if old not in s: raise SystemExit(f'v1.6.3 anchor missing in {p}: {old[:220]!r}')
    p.write_text(s.replace(old,new,1))

def opt(path, old, new):
    p=Path(path); s=p.read_text()
    if old in s: p.write_text(s.replace(old,new,1))

# ---------------------------------------------------------------------------
# Market-depth-aware spread logic. Never fabricate a 0.25% spread.
# ---------------------------------------------------------------------------
(ROOT/'MarketMicrostructureLogic.java').write_text('''package com.suhas.nseunifiedscanner;\n\nfinal class MarketMicrostructureLogic {\n    private MarketMicrostructureLogic(){}\n    static double spreadPct(double bid,double ask,double ltp){\n        if(!(ltp>0)||!(bid>0)||!(ask>0)||ask<bid)return -1.0;\n        return (ask-bid)/ltp*100.0;\n    }\n    static double bestBid(double... prices){double b=0;for(double p:prices)if(p>0)b=Math.max(b,p);return b;}\n    static double bestAsk(double... prices){double a=Double.POSITIVE_INFINITY;for(double p:prices)if(p>0)a=Math.min(a,p);return Double.isFinite(a)?a:0;}\n    static boolean known(double spreadPct){return spreadPct>=0&&Double.isFinite(spreadPct);}\n}\n''')
(TEST/'MarketMicrostructureLogicTest.java').write_text('''package com.suhas.nseunifiedscanner;\nimport org.junit.Test;\nimport static org.junit.Assert.*;\npublic class MarketMicrostructureLogicTest {\n @Test public void validSpreadIsCalculated(){assertEquals(0.10,MarketMicrostructureLogic.spreadPct(99.95,100.05,100.0),0.00001);}\n @Test public void missingSpreadIsUnknownNotArtificialQuarterPercent(){assertEquals(-1.0,MarketMicrostructureLogic.spreadPct(0,0,100),0.0);}\n @Test public void depthHelpersChooseTrueBestPrices(){assertEquals(100.10,MarketMicrostructureLogic.bestBid(99.9,100.10,100.0),0.0001);assertEquals(100.20,MarketMicrostructureLogic.bestAsk(100.4,100.20,100.3),0.0001);}\n}\n''')

# Parse Groww quote depth as a fallback when top-level bid/offer fields are absent.
must(gpapi,
'''            q.bid = p.optDouble("bid_price", 0);\n            q.ask = p.optDouble("offer_price", 0);\n            q.totalBuy = p.optDouble("total_buy_quantity", 0);\n''',
'''            q.bid = p.optDouble("bid_price", 0);\n            q.ask = p.optDouble("offer_price", 0);\n            q.spreadSource=(q.bid>0&&q.ask>0&&q.ask>=q.bid)?"TOP":"UNKNOWN";\n            if("UNKNOWN".equals(q.spreadSource)){\n                JSONObject depth=p.optJSONObject("depth");\n                JSONArray buys=depth==null?null:depth.optJSONArray("buy"), sells=depth==null?null:depth.optJSONArray("sell");\n                double bestBid=0,bestAsk=0;\n                if(buys!=null)for(int i=0;i<buys.length();i++){JSONObject x=buys.optJSONObject(i);if(x!=null)bestBid=Math.max(bestBid,x.optDouble("price",0));}\n                if(sells!=null)for(int i=0;i<sells.length();i++){JSONObject x=sells.optJSONObject(i);if(x!=null){double px=x.optDouble("price",0);if(px>0&&(bestAsk<=0||px<bestAsk))bestAsk=px;}}\n                if(bestBid>0&&bestAsk>=bestBid){q.bid=bestBid;q.ask=bestAsk;q.spreadSource="DEPTH";}\n            }\n            q.totalBuy = p.optDouble("total_buy_quantity", 0);\n''')

must(gpapi,
'''    static final class Quote { String symbol; double ltp, dayChangePct, marketCap, bid, ask, totalBuy, totalSell, week52High, week52Low, upperCircuit, lowerCircuit; long volume; }\n''',
'''    static final class Quote { String symbol,spreadSource="UNKNOWN"; double ltp, dayChangePct, marketCap, bid, ask, totalBuy, totalSell, week52High, week52Low, upperCircuit, lowerCircuit; long volume; }\n''')

# ---------------------------------------------------------------------------
# Strategy correction: 10k quantity-aware target + real/unknown spread handling.
# ---------------------------------------------------------------------------
must(sp,
'''        double spreadPct=(q.bid>0&&q.ask>0&&q.ask>=q.bid)?((q.ask-q.bid)/entry*100.0):0.25;\n        double turnover=entry*q.volume; double depthRatio=(q.totalBuy+q.totalSell)>0?q.totalBuy/(q.totalBuy+q.totalSell):0.5;\n''',
'''        double spreadPct=MarketMicrostructureLogic.spreadPct(q.bid,q.ask,entry);boolean spreadKnown=MarketMicrostructureLogic.known(spreadPct);\n        double turnover=entry*q.volume; double depthRatio=(q.totalBuy+q.totalSell)>0?q.totalBuy/(q.totalBuy+q.totalSell):0.5;\n''')

must(sp,
'''        double indicativeTarget=GrowwApi.roundToTick(entry*1.0048,f.instrument.tick,true);\n        double spreadFloor=0.20;boolean structuralRoom=roomR2>=0.22||f.breakoutConfirmed||f.freshHodPressure;\n''',
'''        int plannedQty=FixedCapitalLogic.quantity(entry);double indicativeTarget=plannedQty>0?ChargeModel.requiredSellPrice(entry,plannedQty,FixedCapitalLogic.NET_TARGET_PCT,FixedCapitalLogic.SLIPPAGE_RESERVE_PCT,f.instrument.tick):GrowwApi.roundToTick(entry*1.0065,f.instrument.tick,true);\n        double spreadFloor=0.20;boolean structuralRoom=roomR2>=0.22||f.breakoutConfirmed||f.freshHodPressure;\n''')

for old,new in [
('boolean preSpikeHard=microReady && entry>=f.vwap*0.9975 && f.rsi>=48 && f.rsi<=70 && f.relVol>=0.90 && f.volumeAccel>=1.12 && spreadPct<=spreadFloor',
 'boolean preSpikeHard=microReady && spreadKnown && entry>=f.vwap*0.9975 && f.rsi>=48 && f.rsi<=70 && f.relVol>=0.90 && f.volumeAccel>=1.12 && spreadPct<=spreadFloor'),
('boolean recoveryHard=microReady && f.crossedGreen && f.recoveryPct>=0.80 && f.fromOpenPct>=-0.10 && spreadPct<=0.20',
 'boolean recoveryHard=microReady && spreadKnown && f.crossedGreen && f.recoveryPct>=0.80 && f.fromOpenPct>=-0.10 && spreadPct<=0.20'),
('boolean volumeBuildHard=microReady && f.volumeAccel>=1.45 && f.rsi1m>=49&&f.rsi1m<=67 && f.macd1mAccel && spreadPct<=0.20',
 'boolean volumeBuildHard=microReady && spreadKnown && f.volumeAccel>=1.45 && f.rsi1m>=49&&f.rsi1m<=67 && f.macd1mAccel && spreadPct<=0.20'),
('boolean relativeStrengthHard=microReady && breadth<48.0 && f.dayPct>=0.25 && f.dayPct<=3.0 && f.oneHour>=-0.05 && depthRatio>=0.48 && turnover>=80_000_000d;',
 'boolean relativeStrengthHard=microReady && spreadKnown && breadth<48.0 && f.dayPct>=0.25 && f.dayPct<=3.0 && f.oneHour>=-0.05 && depthRatio>=0.48 && turnover>=80_000_000d;')]:
    must(sp,old,new)

must(sp,
'''        boolean bullishHodBreakout=entry>=f.vwap && TradeSetupLogic.bullishHodBreakoutSetup(breadth,f.earlyPressure,f.volumeAccel,f.rsi1m,f.macd1mAccel,f.higherLows,f.microBreakoutPct,depthRatio,spreadPct,turnover,hodRoom,f.hodRejected,f.price5mPct,f.lateSpike);\n''',
'''        boolean bullishHodBreakout=spreadKnown && entry>=f.vwap && TradeSetupLogic.bullishHodBreakoutSetup(breadth,f.earlyPressure,f.volumeAccel,f.rsi1m,f.macd1mAccel,f.higherLows,f.microBreakoutPct,depthRatio,spreadPct,turnover,hodRoom,f.hodRejected,f.price5mPct,f.lateSpike);\n''')

must(sp,
'''            features.put("hodroom",TradeSetupLogic.clamp((hodRoom+0.20)/1.20,0,1));features.put("recovery",TradeSetupLogic.clamp(f.recoveryPct/5.0,0,1));''',
'''            features.put("spreadKnown",spreadKnown);features.put("spreadSource",q.spreadSource);double capQuality=q.marketCap>0?TradeSetupLogic.clamp((Math.log10(Math.max(1,q.marketCap))-9.0)/2.5,0,1):0.5;features.put("capquality",capQuality);features.put("hodroom",TradeSetupLogic.clamp((hodRoom+0.20)/1.20,0,1));features.put("recovery",TradeSetupLogic.clamp(f.recoveryPct/5.0,0,1));''')

must(sp,
'''        double score=f.baseScore + f.earlyPressure*0.22 + Math.min(7,liquidity*7) + Math.max(-4,Math.min(5,(depthRatio-0.5)*12)) - Math.max(0,(spreadPct-0.08)*20) + (recoveryHard?5:0) + (volumeBuildHard?5:0) + (relativeStrengthHard?4:0) + (bullishHodBreakout?7:0) + (f.higherLows?3:0) - (f.hodRejected&&!f.breakoutConfirmed?10:0) - (!clearPath?12:0) - (f.lateSpike?38:0);\n''',
'''        double spreadPenalty=spreadKnown?Math.max(0,(spreadPct-0.08)*20):10.0;double capBonus=q.marketCap>0?Math.max(-2,Math.min(3,(Math.log10(Math.max(1,q.marketCap))-9.0)*1.5)):0;\n        double score=f.baseScore + f.earlyPressure*0.22 + Math.min(7,liquidity*7) + Math.max(-4,Math.min(5,(depthRatio-0.5)*12)) - spreadPenalty + capBonus + (recoveryHard?5:0) + (volumeBuildHard?5:0) + (relativeStrengthHard?4:0) + (bullishHodBreakout?7:0) + (f.higherLows?3:0) - (f.hodRejected&&!f.breakoutConfirmed?10:0) - (!clearPath?12:0) - (f.lateSpike?38:0);\n''')

must(sp,
'''        if(r.qualified&&r.features.optBoolean("bullishHodBreakout",false))return "QUALIFIED • BULLISH HOD BREAKOUT • early pressure + volume + bullish breadth confirmed through prior HOD";\n        if(r.qualified)return "QUALIFIED • "+setup+" • clear path to target + volume/VWAP/liquidity aligned";\n''',
'''        if(r.qualified&&r.features.optBoolean("bullishHodBreakout",false))return "QUALIFIED • BULLISH HOD BREAKOUT • early pressure + volume + bullish breadth confirmed through prior HOD";\n        if(r.qualified)return "QUALIFIED • "+setup+" • clear path to target + volume/VWAP/liquidity aligned";\n        if(!r.features.optBoolean("spreadKnown",false))return "WATCH • "+setup+" • SPREAD UNKNOWN — Groww top bid/offer and market depth unavailable; BUY blocked safely";\n''')

# Allow the learner to discover whether company scale (market-cap quality) materially changes 30-minute hit rates.
must(lp,
'    static final String[] NAMES={"vwap","rsi","relvol","macd","momentum","breakout","liquidity","market","depth","range","time","hodroom","recovery","rejection","earlypress","volaccel","compression","extension","bullregime","hodbreak","microsetup"};\n    private static final double[] DEFAULT={0.92,0.55,0.78,0.72,0.62,0.58,0.68,0.55,0.35,0.35,0.45,0.62,0.52,0.68,0.82,0.72,0.58,0.74,0.38,0.30,0.28};\n',
'    static final String[] NAMES={"vwap","rsi","relvol","macd","momentum","breakout","liquidity","market","depth","range","time","hodroom","recovery","rejection","earlypress","volaccel","compression","extension","bullregime","hodbreak","microsetup","capquality"};\n    private static final double[] DEFAULT={0.92,0.55,0.78,0.72,0.62,0.58,0.68,0.55,0.35,0.35,0.45,0.62,0.52,0.68,0.82,0.72,0.58,0.74,0.38,0.30,0.28,0.12};\n')

# ---------------------------------------------------------------------------
# UI: real spread source, meaningful planned target economics, fixed-capital arming text.
# ---------------------------------------------------------------------------
s=mp.read_text()
s=s.replace('R1 %.2f  • R2 %.2f  • room %.2f%%  • spread %.2f%%\\nBuy depth %.0f%%  • turnover ₹%.1f Cr",r.vwap,r.rsi,r.relVol,r.oneHour,r.r1,r.r2,r.roomR2,r.spreadPct,r.depthBuyPct,r.turnover/10_000_000d)',
'''R1 %.2f  • R2 %.2f  • room %.2f%%  • %s\\nBuy depth %.0f%%  • turnover ₹%.1f Cr",r.vwap,r.rsi,r.relVol,r.oneHour,r.r1,r.r2,r.roomR2,(r.spreadPct>=0?("spread "+String.format(Locale.US,"%.3f%%",r.spreadPct)+" ["+r.features.optString("spreadSource","TOP")+"]"):"SPREAD UNKNOWN"),r.depthBuyPct,r.turnover/10_000_000d)''')
s=s.replace('int plannedQty=FixedCapitalLogic.quantity(r.entry);double plannedCapital=FixedCapitalLogic.deployed(plannedQty,r.entry);double plannedNet=FixedCapitalLogic.targetNetRupees(plannedQty,r.entry);c.addView(txt("FIXED TEST CAPITAL ₹10,000 • planned qty "+plannedQty+" • deploy ~₹"+money(plannedCapital)+" • net objective ≥₹"+money(plannedNet),11,GREEN,true));',
'''int plannedQty=FixedCapitalLogic.quantity(r.entry);double plannedCapital=FixedCapitalLogic.deployed(plannedQty,r.entry);double plannedNet=FixedCapitalLogic.targetNetRupees(plannedQty,r.entry);double estNetAtCardTarget=plannedQty>0?ChargeModel.netPnl(r.entry,r.target,plannedQty):0;c.addView(txt("FIXED TEST CAPITAL ₹10,000 • planned qty "+plannedQty+" • deploy ~₹"+money(plannedCapital)+" • target net est ~₹"+money(estNetAtCardTarget)+" (objective ≥₹"+money(plannedNet)+")",11,GREEN,true));''')
s=s.replace('b.append(r.rsi>=52&&r.rsi<=73?"✓RSI ":"✗RSI ");\n        b.append(r.features.optBoolean("clearPath",true)?"✓PATH ":"✗PATH ");',
'''b.append(r.rsi>=52&&r.rsi<=73?"✓RSI ":"✗RSI ");\n        b.append(r.features.optBoolean("spreadKnown",false)&&r.spreadPct<=0.20?"✓SPREAD ":"✗SPREAD ");\n        b.append(r.features.optBoolean("clearPath",true)?"✓PATH ":"✗PATH ");''')
s=s.replace('Spread %.3f%%\\nMarket breadth %.1f%%\\n\\n%s",r.symbol,r.entry,r.target,r.stop,r.rsi,r.relVol,r.oneHour,r.vwap,r.r1,r.r2,r.roomR2,r.spreadPct,r.breadth,r.reason)',
'''Spread %s\\nMarket breadth %.1f%%\\n\\n%s",r.symbol,r.entry,r.target,r.stop,r.rsi,r.relVol,r.oneHour,r.vwap,r.r1,r.r2,r.roomR2,(r.spreadPct>=0?(String.format(Locale.US,"%.3f%% [%s]",r.spreadPct,r.features.optString("spreadSource","TOP"))):"UNKNOWN"),r.breadth,r.reason)''')
s=s.replace('BUY will use up to the configured share of available MIS margin (default 98%), open only one position at a time, create broker protection, target an estimated +0.30% net after charges and the configured slippage reserve, and force a time exit by 30 minutes or 15:10 IST. Profit and an 80% hit rate cannot be guaranteed.',
'''Each BUY is capped to approximately ₹10,000 trade value regardless of wallet balance. The app rechecks price and required MIS margin, sends the order, reconciles the actual fill, then recalculates the +0.30% NET target after estimated charges/slippage and establishes stop protection. One active position at a time; maximum 30 minutes. Profit and an 80% hit rate cannot be guaranteed.''')
s=s.replace('No active position\\n₹2,000 NET PROFIT LOCK • armed automatically on every app trade','No active position\\n₹10,000 TEST MODE • +0.30% NET target per qualified trade')
s=s.replace('\\n₹2K PROFIT LOCK • executable-net est ₹"+money(est)','\\n₹10K TEST MODE • executable-net est ₹"+money(est)')
s=s.replace('v1.6.2 • ₹10K fixed test capital • standalone package com.suhas.nseunifiedscanner','v1.6.3 • depth-aware spread + ₹10K charge-aware target • standalone package com.suhas.nseunifiedscanner')
mp.write_text(s)

(TEST/'FixedCapitalTargetEconomicsTest.java').write_text('''package com.suhas.nseunifiedscanner;\nimport org.junit.Test;\nimport static org.junit.Assert.*;\npublic class FixedCapitalTargetEconomicsTest {\n @Test public void chargeAwareTargetReallyClearsPointThreePercentNet(){double buy=100.0;int q=FixedCapitalLogic.quantity(buy);double target=ChargeModel.requiredSellPrice(buy,q,FixedCapitalLogic.NET_TARGET_PCT,FixedCapitalLogic.SLIPPAGE_RESERVE_PCT,0.05);double net=ChargeModel.netPnl(buy,target,q);assertTrue(net>=FixedCapitalLogic.targetNetRupees(q,buy));assertTrue(target>buy*1.0048);}\n}\n''')

s=gp.read_text()
if "versionCode 162" not in s or "versionName '1.6.2'" not in s: raise SystemExit('v1.6.3 build.gradle version anchor missing')
s=s.replace("versionCode 162\n        versionName '1.6.2'","versionCode 163\n        versionName '1.6.3'")
gp.write_text(s)

print('v1.6.3 depth-aware spread + charge-aware target patch applied')

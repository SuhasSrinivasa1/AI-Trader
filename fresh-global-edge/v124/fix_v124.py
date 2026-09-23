#!/usr/bin/env python3
from pathlib import Path
import re, sys
root=Path(sys.argv[1]).resolve()

def rw(rel): return (root/rel).read_text(encoding='utf-8')
def wr(rel,s): (root/rel).write_text(s,encoding='utf-8')
def one(s,pat,repl,label,flags=re.S|re.M):
    out,n=re.subn(pat,repl,s,count=1,flags=flags)
    if n!=1: raise SystemExit(f'{label}: {n}')
    return out

g='app/build.gradle.kts';s=rw(g);s=s.replace('versionCode = 123','versionCode = 124',1).replace('versionName = "1.2.3"','versionName = "1.2.4"',1);wr(g,s)

sig='app/src/main/java/com/suhas/ucsentinel/domain/engine/SignalEngine.kt';s=rw(sig)
s=s.replace('UC_CONTINUATION_V2_ADAPTIVE_2026_09','PRE_UC_PREDICTOR_V3_2026_09',1)
def rule(i,body):
    global s
    s=one(s,rf'^\s{{12}}r\("{i}".*?^\s{{12}}\}},',body,'rule '+i)
rule('UC001','''            r("UC001","Pre-UC headroom 1-6%","Circuit",4.0) { c ->
                val d=pctDistance(c.quote.lastPrice,c.quote.upperCircuit)
                (c.quote.upperCircuit>c.quote.lastPrice && d in 1.0..6.0) to ("UC headroom "+fmt(d)+"%")
            },''')
rule('UC002','''            r("UC002","Pre-UC sweet spot 1-3.5%","Circuit",3.0) { c ->
                val d=pctDistance(c.quote.lastPrice,c.quote.upperCircuit)
                (c.quote.upperCircuit>c.quote.lastPrice && d in 1.0..3.5) to ("UC headroom "+fmt(d)+"%")
            },''')
rule('UC003','''            r("UC003","Not locked at circuit","Circuit",2.0) { c ->
                val d=pctDistance(c.quote.lastPrice,c.quote.upperCircuit)
                (c.quote.upperCircuit<=0.0 || d>=0.75) to ("UC headroom "+fmt(d)+"%")
            },''')
rule('UC004','''            r("UC004","Approaching UC with room to enter","Circuit",1.0) { c ->
                val d=pctDistance(c.quote.lastPrice,c.quote.upperCircuit)
                (c.quote.upperCircuit>c.quote.lastPrice && d in 0.75..8.0) to ("UC headroom "+fmt(d)+"%")
            },''')
rule('UC006','''            r("UC006","Sell-side liquidity still available","Depth",4.0) { c ->
                (c.quote.totalSellQuantity>0L && (c.quote.offerQuantity>0L || c.quote.sellDepth.any{it.quantity>0L})) to
                    ("Buy "+c.quote.totalBuyQuantity+", Sell "+c.quote.totalSellQuantity)
            },''')
rule('UC007','''            r("UC007","Buy/Sell ratio >= 1.5","Depth",3.0) { c ->
                val x=ratio(c.quote.totalBuyQuantity,c.quote.totalSellQuantity)
                (x>=1.5) to ("Ratio "+fmt(x)+"x")
            },''')
rule('UC008','''            r("UC008","Buy/Sell ratio >= 2.5","Depth",3.0) { c ->
                val x=ratio(c.quote.totalBuyQuantity,c.quote.totalSellQuantity)
                (x>=2.5) to ("Ratio "+fmt(x)+"x")
            },''')
rule('UC009','''            r("UC009","Best bid supports current price","Depth",2.5) { c ->
                val d=pctDistance(c.quote.bidPrice,c.quote.lastPrice)
                (c.quote.bidPrice>0.0 && d<=0.50) to ("Bid support "+fmt(d)+"%")
            },''')
rule('UC010','''            r("UC010","Executable offer still present","Depth",2.5) { c ->
                (c.quote.offerPrice>0.0 && c.quote.offerQuantity>0L) to ("Offer qty "+c.quote.offerQuantity)
            },''')
rule('UC011','''            r("UC011","Top depth sell side tradable","Depth",2.0) { c ->
                val q=c.quote.sellDepth.sumOf{it.quantity}
                (q>0L) to ("Depth sell qty "+q)
            },''')
rule('UC013','''            r("UC013","Early momentum >= 1.5%","Momentum",2.0) { c ->
                (c.quote.dayChangePercent>=1.5) to ("Change "+fmt(c.quote.dayChangePercent)+"%")
            },''')
rule('UC014','''            r("UC014","Strong early momentum >= 3%","Momentum",2.2) { c ->
                (c.quote.dayChangePercent>=3.0) to ("Change "+fmt(c.quote.dayChangePercent)+"%")
            },''')
rule('UC015','''            r("UC015","Acceleration >= 5%","Momentum",2.4) { c ->
                (c.quote.dayChangePercent>=5.0) to ("Change "+fmt(c.quote.dayChangePercent)+"%")
            },''')
rule('UC038','''            r("UC038","Recent candles green >= 60%","Intraday",2.0) { c ->
                val x=Indicators.greenCandleRatio(c.intraday,8)
                (x>=0.60) to ("Green "+fmt(x*100)+"%")
            },''')
rule('UC039','''            r("UC039","Recent candles green >= 75%","Intraday",2.5) { c ->
                val x=Indicators.greenCandleRatio(c.intraday,8)
                (x>=0.75) to ("Green "+fmt(x*100)+"%")
            },''')
wr(sig,s)

sc='app/src/main/java/com/suhas/ucsentinel/domain/engine/ScannerEngine.kt';s=rw(sc)
s=one(s,r'\s+val pct = \(o\.high / o\.close - 1\.0\) \* 100\.0.*?if \(candidate\) prelim \+= instrument to o','''
                val belowHighPct=(o.high/o.close-1.0)*100.0
                val closeFromOpen=if(o.open>0.0)(o.close/o.open-1.0)*100.0 else 0.0
                val rangePct=if(o.low>0.0)(o.high/o.low-1.0)*100.0 else 0.0
                val holdingHigh=belowHighPct<=if(nextSessionMode)2.0 else 1.25
                val candidate=holdingHigh && (closeFromOpen>=(if(nextSessionMode)0.30 else 0.75) || rangePct>=1.5)
                if(candidate)prelim+=instrument to o''','prelim')
s=one(s,r'val rankedPrelim = prelim\s*\.sortedByDescending \{ \(_, o\) ->.*?\.take\(settings\.maxQuotesPerScan\)','''val rankedPrelim=prelim.sortedByDescending{(_,o)->
            if(o.close<=0.0||o.open<=0.0)-999.0 else ((o.close/o.open-1.0)*150.0-(o.high/o.close-1.0)*100.0)
        }.take(settings.maxQuotesPerScan)''','rank')
s=one(s,r'val distanceToUc = if \(quote\.upperCircuit <= 0\).*?if \(quote\.dayChangePercent < minDayMove\) continue','''val distanceToUc=if(quote.upperCircuit<=0.0){if(nextSessionMode)6.0 else 999.0}else((quote.upperCircuit-quote.lastPrice)/quote.upperCircuit*100.0)
            val pc=quote.previousClose.takeIf{it.isFinite()&&it>0.0}
            val band=if(pc!=null&&quote.upperCircuit>pc)((quote.upperCircuit/pc-1.0)*100.0).coerceIn(2.0,20.0) else 0.0
            val progress=if(band>0.0)quote.dayChangePercent/band else 0.0
            if((quote.upperCircuit>0.0&&quote.lastPrice>=quote.upperCircuit*0.995)||(band>0.0&&progress>=0.85))continue
            val minHead=if(nextSessionMode)1.0 else 0.75
            val maxHead=if(nextSessionMode)12.0 else 8.0
            val minMove=if(nextSessionMode)0.5 else 1.0
            if(quote.upperCircuit>0.0&&distanceToUc !in minHead..maxHead)continue
            if(quote.dayChangePercent<minMove)continue''','gate')
s=one(s,r'var score = signalEngine\.score\(results, adaptivePrecision\).*?quote\.totalBuyQuantity\.toDouble\(\) / quote\.totalSellQuantity\s*\n\s*\}','''var score=signalEngine.score(results,adaptivePrecision)
            val avgVol=Indicators.avgVolume(daily.dropLast(1),20)
            val volumeRatio=if(avgVol<=0.0)0.0 else quote.volume/avgVol
            val buySellRatio=if(quote.totalSellQuantity<=0L){if(quote.totalBuyQuantity>0)99.0 else 0.0}else quote.totalBuyQuantity.toDouble()/quote.totalSellQuantity
            if(quote.upperCircuit>0.0&&distanceToUc in 1.0..3.5)score+=5.0 else if(quote.upperCircuit>0.0&&distanceToUc in 3.5..6.0)score+=2.5
            if(buySellRatio>=1.5&&quote.offerQuantity>0L)score+=2.5
            if(volumeRatio>=1.5)score+=2.0
            if(volumeRatio>=3.0)score+=1.5
            if(quote.dayChangePercent in 1.5..8.0)score+=1.5
            if(Indicators.consecutiveCircuitLikeDays(daily)>=1)score+=1.0
            score=score.coerceIn(0.0,100.0)''','score')
s=s.replace('val strategies = buildList {\n                if (executionReady)', 'val strategies = buildList {\n                add("PRE_UC")\n                if (executionReady)',1)
wr(sc,s)

repo='app/src/main/java/com/suhas/ucsentinel/data/repository/UCSentinelRepository.kt';s=rw(repo)
s=s.replace('recordCandidateCalls(ScannerSection.UC_CONTINUATION,TradeCallBucket.NEXT_SESSION,uc.candidates,"UC next-session research",System.currentTimeMillis())','if(uc.message.startsWith("NEXT SESSION •"))recordCandidateCalls(ScannerSection.UC_CONTINUATION,TradeCallBucket.NEXT_SESSION,uc.candidates,"PRE-UC next-session prediction",System.currentTimeMillis())',1)
s=s.replace('&&uc.candidates.isNotEmpty()){','&&!uc.message.startsWith("WATCHLIST ONLY")&&uc.candidates.isNotEmpty()){',1)
s=one(s,r'\s+val detail="\$\{c\.companyName\}.*?"\n','''
            val headroom=if(c.upperCircuit>c.price&&c.upperCircuit>0.0)(c.upperCircuit/c.price-1.0)*100.0 else 0.0
            val detail=c.companyName+" • score "+"%.0f".format(c.score)+" • "+"%.2f".format(c.dayChangePercent)+"% • vol "+"%.1f".format(c.volumeRatio)+"x • UC headroom "+"%.2f".format(headroom)+"%"
''','detail')
wr(repo,s)

ui='app/src/main/java/com/suhas/ucsentinel/ui/CompactMarketScreens.kt';s=rw(ui)
s=s.replace('NEXT SESSION • UC','NEXT SESSION • PRE-UC').replace('LONG • UC','LONG • PRE-UC').replace('3 PM • UC','3 PM • PRE-UC')
wr(ui,s)
print('v1.2.4 PRE-UC predictor applied')

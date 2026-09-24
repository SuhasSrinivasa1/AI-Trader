#!/usr/bin/env python3
from pathlib import Path
import sys
root=Path(sys.argv[1]).resolve()
p=root/"app/src/main/java/com/suhas/ucsentinel/data/repository/UCSentinelRepository.kt"
s=p.read_text(encoding="utf-8")

def one(old,new,label):
    global s
    n=s.count(old)
    if n!=1: raise SystemExit(f"{label}: expected 1 found {n}")
    s=s.replace(old,new,1)

one(
'''        val(bundle,active)=activeStrategyDefinitions(settings)
        val token=accessToken();val universe=if(instruments.cached().isEmpty())instruments.refresh() else instruments.cached()
''',
'''        val(bundle,active)=activeStrategyDefinitions(settings)
        val governedPerfs=governedStrategyPerformances(bundle.strategies,settings).associateBy{it.strategyId}
        val token=accessToken();val universe=if(instruments.cached().isEmpty())instruments.refresh() else instruments.cached()
        val sectorBundle=runCatching{sectorClient.classifications(false)}.getOrNull()
        val evidenceAge=System.currentTimeMillis()-(fabricStore.evidence(1).firstOrNull()?.observedAt?:0L)
        if(evidenceAge>15L*60_000L)runCatching{refreshNews()}
''',"strategy evidence setup")

one(
'''        val movers=mutableListOf<Pair<Instrument,Double>>()
        cash.chunked(50).forEachIndexed{idx,batch->
            val map=runCatching{groww.getOhlcBatch(token,batch.map{it.tradingSymbol})}.getOrDefault(emptyMap())
''',
'''        val movers=mutableListOf<Pair<Instrument,Double>>()
        val marketOhlc=mutableMapOf<String,Ohlc>()
        cash.chunked(50).forEachIndexed{idx,batch->
            val map=runCatching{groww.getOhlcBatch(token,batch.map{it.tradingSymbol})}.getOrDefault(emptyMap())
            marketOhlc.putAll(map)
''',"market OHLC for sector breadth")

one(
'''        val now=ZonedDateTime.now(ist);val date=now.toLocalDate();val start=date.atTime(9,15).format(dateTimeFmt);val end=now.plusMinutes(1).format(dateTimeFmt)
''',
'''        val now=ZonedDateTime.now(ist);val date=now.toLocalDate();val start=date.atTime(9,15).format(dateTimeFmt);val end=now.plusMinutes(1).format(dateTimeFmt)
        val macroRisk=EvidenceFabricEngine.activeMacroRisk(date,fabricStore.macroEvents())
''',"macro risk setup")

start=s.index("        val rejectedBefore=prefs.loadRejectedShadows(2500).size")
end=s.index("\n        // Same-side rules compete first.",start)
new_block=r'''        val rejectedBefore=prefs.loadRejectedShadows(2500).size
        val challengerBefore=fabricStore.challengerShadows(2500).size
        val rawSetups=mutableListOf<Pair<StrategySetup,Quote>>();var enriched=0;var quoteRejected=0;var historyFailed=0;var candleShort=0;var rulesMatched=0
        for((idx,inst) in selected.withIndex()){
            val q=quote(inst.tradingSymbol)?:continue
            val sp=spreadPct(q);val tradedValue=q.volume*q.lastPrice
            if(!ExecutionQuality.executableQuote(q)){quoteRejected++;continue}
            val candleResult=runCatching{groww.getHistoricalCandles(token,inst.tradingSymbol,start,end,"5minute")}
            if(candleResult.isFailure){historyFailed++;continue}
            val candles=candleResult.getOrDefault(emptyList())
            if(candles.size<4){candleShort++;continue};enriched++

            val sectorState=sectorBundle?.let{sectorClient.peerState(inst.tradingSymbol,it,marketOhlc,System.currentTimeMillis())}
            sectorState?.let{fabricStore.saveSectorState(it)}
            val pit=fabricStore.evidenceAsOf(inst.tradingSymbol,now.toInstant().toEpochMilli())
            val fundamentalCount=pit.count{it.kind==EvidenceKind.FUNDAMENTAL}
            val analystCount=pit.count{it.kind==EvidenceKind.ANALYST_RATING}
            val earningsCount=pit.count{it.kind==EvidenceKind.EARNINGS_EVENT}
            val evidenceText=buildString{
                sectorState?.let{
                    append(" • industry ").append(it.industry)
                    append(" • peers ").append(it.positivePeers).append("/").append(it.peerCount).append(" positive")
                    append(" • sector breadth ").append("%.0f".format(it.peerBreadthPct)).append("%")
                    append(" • stock-vs-sector ").append("%+.2f".format(it.relativeStrengthPct)).append("%")
                }
                if(fundamentalCount+analystCount+earningsCount>0){
                    append(" • PIT evidence F=").append(fundamentalCount).append(" A=").append(analystCount).append(" E=").append(earningsCount)
                }
                if(macroRisk.isNotEmpty())append(" • macro risk ").append(macroRisk.joinToString(","){it.title})
            }

            for(def in active){
                val e=strategyEngine.evaluate(def,candles)?:continue;rulesMatched++
                val age=listingAge[inst.tradingSymbol];val boost=if(age!=null&&age<=settings.newListingDays)2.0 else 0.0
                val sectorAdj=sectorState?.let{ss->
                    when(e.direction){
                        TradeDirection.LONG->when{ss.participationAligned&&ss.relativeStrengthPct>0.0->2.0;ss.peerBreadthPct<30.0&&ss.relativeStrengthPct<0.0->-2.0;else->0.0}
                        TradeDirection.SHORT->when{ss.peerBreadthPct<=45.0&&ss.relativeStrengthPct<0.0->2.0;ss.peerBreadthPct>70.0&&ss.relativeStrengthPct>0.0->-2.0;else->0.0}
                    }
                }?:0.0
                val macroAdj=if(macroRisk.any{it.severity.equals("HIGH",true)})-2.0 else 0.0
                val earningsAdj=if(earningsCount>0)-1.0 else 0.0
                val rawScore=(e.score+boost+sectorAdj+macroAdj+earningsAdj).coerceIn(0.0,100.0)
                val liquidity="₹${"%.1f".format(tradedValue/100000.0)}L traded • vol ${q.volume} • spread ${"%.2f".format(sp)}%"
                val baseSetup=StrategySetup(inst.tradingSymbol,inst.name,def.id,def.name,e.direction,rawScore,q.lastPrice,e.targetPct,e.stopPct,
                    e.evidence+" • "+liquidity+(if(boost>0)" • new-listing context" else "")+evidenceText,age)
                fun reject(setup:StrategySetup,reason:String){recordRejectedStrategyShadow(setup,reason)}

                if(e.targetPct<ExecutionQuality.MIN_PLAN_SEPARATION_PCT||e.stopPct<ExecutionQuality.MIN_PLAN_SEPARATION_PCT){
                    reject(baseSetup,"PLAN_SEPARATION_GATE");continue
                }
                if(e.direction==TradeDirection.SHORT&&!inst.sellAllowed){reject(baseSetup,"SHORT_NOT_ALLOWED");continue}
                if(e.direction==TradeDirection.LONG&&!hasAsk(q)){reject(baseSetup,"NO_EXECUTABLE_ASK");continue}
                if(e.direction==TradeDirection.SHORT&&!hasBid(q)){reject(baseSetup,"NO_EXECUTABLE_BID");continue}

                val sectorHardFail=sectorState?.let{ss->
                    ss.peerCount>=5&&when(e.direction){
                        TradeDirection.LONG->ss.peerBreadthPct<20.0&&ss.relativeStrengthPct< -1.0
                        TradeDirection.SHORT->ss.peerBreadthPct>80.0&&ss.relativeStrengthPct>1.0
                    }
                }?:false
                if(sectorHardFail){
                    reject(baseSetup,"SECTOR_PARTICIPATION_HARD_GATE");continue
                }

                val hb=handbookSynergy.evaluate(baseSetup,candles,q)
                val setup=baseSetup.copy(
                    score=hb.adjustedScore,
                    evidence=baseSetup.evidence+" • "+hb.evidence,
                    researchSignature=hb.signature,
                    handbookQualityPct=hb.qualityPct,
                    handbookPattern=hb.primaryPattern,
                    handbookCombination=hb.combination
                )
                if(hb.hardFail){reject(setup,"HANDBOOK_HARD_GATE "+hb.failedHardFilters.joinToString(",").take(160));continue}
                if(setup.score<68.0){reject(setup,"RESEARCH_SCORE_FLOOR "+"%.1f".format(setup.score)+" < 68.0");continue}

                when(governedPerfs[def.id]?.status?:StrategyStatus.CHALLENGER){
                    StrategyStatus.CHALLENGER->{
                        recordChallengerShadow(setup,now)
                        continue
                    }
                    StrategyStatus.PROBATION->{
                        reject(setup,"PROBATION_NON_EXECUTABLE")
                        continue
                    }
                    StrategyStatus.SUSPENDED->{
                        reject(setup,"DECAY_SUSPENDED_NON_EXECUTABLE")
                        continue
                    }
                    StrategyStatus.ACTIVE,StrategyStatus.CHAMPION->rawSetups+=setup to q
                }
            }
            if(idx%10==9)progress("Strategies: Evidence Fabric + sector peers ${idx+1}/${selected.size}")
        }
'''
s=s[:start]+new_block+s[end:]

# Every new live strategy gets a permanent decision snapshot.
needle='''                surviving+=StrategyRecommendation(id,setup,System.currentTimeMillis(),System.currentTimeMillis(),q.lastPrice,
                    tradedValue=q.volume*q.lastPrice,volume=q.volume,spreadPct=sp)
                existingKeys+=key;newlyOpened+=setup
'''
replacement='''                surviving+=StrategyRecommendation(id,setup,System.currentTimeMillis(),System.currentTimeMillis(),q.lastPrice,
                    tradedValue=q.volume*q.lastPrice,volume=q.volume,spreadPct=sp)
                saveDecision(setup.symbol,"STRATEGY",setup.strategyId,setup.direction.name,setup.score,DecisionAction.LIVE,
                    "ACTIVE/CHAMPION strategy passed Evidence Fabric and hard gates",listOf("EXECUTION_QUALITY_PASS","HANDBOOK_PASS","SECTOR_GATE_PASS"))
                existingKeys+=key;newlyOpened+=setup
'''
one(needle,replacement,"strategy live decision")

# Governed performances + Challenger counters in summary.
one("        val perfs=prefs.strategyPerformances(bundle.strategies,settings)\n",
    "        val perfs=governedStrategyPerformances(bundle.strategies,settings)\n","governed summary perfs")
old='''        val champions=perfs.count{it.status==StrategyStatus.CHAMPION}
        val suspended=perfs.count{it.status==StrategyStatus.SUSPENDED}
        val summary=StrategyTournamentSummary(System.currentTimeMillis(),cash.size,active.size,enriched,top.map{it.first},active,perfs,bundle.version,
            "${active.size} active • HB 100/50/50 • ${selected.size} symbols • ${enriched} enriched • ${quoteRejected} liquidity rejects • ${historyFailed} history failures • ${candleShort} short histories • ${rulesMatched} rule matches • ${surviving.size} LIVE • ${newlyOpened.size} new • CHAMP ${champions} • SUSP ${suspended} • rejected+journal ${rejectedAdded}",
            insights,rejectedAfter,HandbookSynergyEngine.VERSION)
'''
new='''        val champions=perfs.count{it.status==StrategyStatus.CHAMPION}
        val challengers=perfs.count{it.status==StrategyStatus.CHALLENGER}
        val suspended=perfs.count{it.status==StrategyStatus.SUSPENDED}
        val challengerAfter=fabricStore.challengerShadows(2500).size
        val challengerAdded=(challengerAfter-challengerBefore).coerceAtLeast(0)
        val summary=StrategyTournamentSummary(System.currentTimeMillis(),cash.size,active.size,enriched,top.map{it.first},active,perfs,bundle.version,
            "${active.size} rules • Evidence Fabric • HB 100/50/50 • ${selected.size} symbols • ${enriched} enriched • ${quoteRejected} liquidity rejects • ${rulesMatched} rule matches • ${surviving.size} LIVE • ${newlyOpened.size} new • CHAMP ${champions} • CHALL ${challengers} (+${challengerAdded} shadows) • SUSP ${suspended} • rejected+journal ${rejectedAdded}",
            insights,rejectedAfter,HandbookSynergyEngine.VERSION)
'''
one(old,new,"strategy summary challenger counts")

p.write_text(s,encoding="utf-8")
print("Strategy Evidence Fabric, sector intelligence and true Challenger lane applied")

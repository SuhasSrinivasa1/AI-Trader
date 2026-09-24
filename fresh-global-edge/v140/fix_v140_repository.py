#!/usr/bin/env python3
from pathlib import Path
import sys
root=Path(sys.argv[1]).resolve()
def rw(p): return (root/p).read_text(encoding="utf-8")
def wr(p,s): (root/p).write_text(s,encoding="utf-8")
def one(s,old,new,label):
    n=s.count(old)
    if n!=1: raise SystemExit(f"{label}: expected 1 found {n}")
    return s.replace(old,new,1)

p="app/build.gradle.kts";s=rw(p)
s=one(s,"versionCode = 130","versionCode = 140","versionCode")
s=one(s,'versionName = "1.3.0"','versionName = "1.4.0"',"versionName")
wr(p,s)

p="app/src/main/java/com/suhas/ucsentinel/data/repository/UCSentinelRepository.kt";s=rw(p)
s=one(s,
'''    private val strategyEngine=TradingStrategyEngine()
    private val autopsyEngine=TradeAutopsyEngine()
''',
'''    private val strategyEngine=TradingStrategyEngine()
    private val handbookSynergy=HandbookSynergyEngine()
    private val autopsyEngine=TradeAutopsyEngine()
''',"handbook engine field")

start=s.index("    private fun activeStrategyDefinitions(settings:AppSettings):Pair<StrategyCatalogClient.Bundle,List<TradingStrategyDefinition>>{")
end=s.index("\n    private fun nextTradingDate",start)
new_active='''    private fun activeStrategyDefinitions(settings:AppSettings):Pair<StrategyCatalogClient.Bundle,List<TradingStrategyDefinition>>{
        val bundle=strategyCatalog?:strategyCatalogClient.embedded().also{strategyCatalog=it}
        val today=LocalDate.now(ist);val wf=java.time.temporal.WeekFields.ISO
        fun weekKey(d:LocalDate)=d.get(wf.weekBasedYear()).toString()+"-W"+d.get(wf.weekOfWeekBasedYear()).toString().padStart(2,'0')
        val thisWeek=weekKey(today);val perfs=prefs.strategyPerformances(bundle.strategies,settings).associateBy{it.strategyId}
        val suspended=bundle.strategies.filter{perfs[it.id]?.status==StrategyStatus.SUSPENDED}.map{it.id}.toSet()
        val closed=prefs.loadStrategyClosed(2000);val byId=closed.associateBy{"STRATEGY|"+it.id}
        val buckets=mutableMapOf<String,MutableList<Pair<Boolean,Double>>>()
        prefs.loadAutopsies(2000).filter{it.engineLabel=="STRATEGY"}.forEach{a->
            val r=byId[a.sourceId]?:return@forEach;val key=r.setup.strategyId+"|"+r.setup.direction.name+"|"+a.regime.name
            buckets.getOrPut(key){mutableListOf()}+=((r.status==StrategyRecommendationStatus.WIN) to r.returnPct)
        }
        val regimeProtected=buckets.entries.filter{(_,rows)->rows.size>=4&&rows.count{it.first}*100.0/rows.size>=50.0&&rows.map{it.second}.average()>0.0}
            .map{it.key.substringBefore("|")}.filterNot{suspended.contains(it)}.toSet()
        val champions=bundle.strategies.filter{perfs[it.id]?.status==StrategyStatus.CHAMPION&&it.id !in suspended}.sortedByDescending{it.priority}
        val championIds=champions.map{it.id}.toSet()
        val saved=prefs.loadStrategySummary();val savedDate=saved?.generatedAt?.takeIf{it>0L}?.let{Instant.ofEpochMilli(it).atZone(ist).toLocalDate()}
        val savedIds=if(savedDate!=null&&weekKey(savedDate)==thisWeek)saved?.activeStrategies.orEmpty().map{it.id}else emptyList()
        val savedPreferred=savedIds.mapNotNull{id->bundle.strategies.firstOrNull{it.id==id}}
            .filter{it.id !in suspended&&(perfs[it.id]?.status!=StrategyStatus.PROBATION||it.id in regimeProtected)}
        val pool=bundle.strategies.filter{it.id !in championIds&&it.id !in suspended&&(perfs[it.id]?.status!=StrategyStatus.PROBATION||it.id in regimeProtected)}
            .sortedByDescending{it.priority}
        val weeklyOffset=((today.get(wf.weekOfWeekBasedYear())-1)%maxOf(1,pool.size))
        val rotated=if(pool.isEmpty())emptyList() else pool.drop(weeklyOffset)+pool.take(weeklyOffset)
        val active=(champions+savedPreferred+rotated).distinctBy{it.id}.take(settings.strategyActiveCount.coerceIn(20,40))
        DiagnosticLog.log(appContext,"STRATEGY-WEEKLY","week="+thisWeek+" • active="+active.size+" • champions="+champions.size+" • suspended="+suspended.size+" • regime-protected="+regimeProtected.size)
        return bundle to active
    }
'''
s=s[:start]+new_active+s[end:]

rs=s.index("    private fun recordRejectedStrategyShadow")
re=s.index("    private fun recordRejectedGlobalShadow",rs)
segment=s[rs:re]
old='''            targetSessionDate=targetSessionFor(TradeCallBucket.LIVE,nowMs).toString(),reason=reason
        ))
'''
new='''            targetSessionDate=targetSessionFor(TradeCallBucket.LIVE,nowMs).toString(),
            reason=reason+" • STRAT="+s.strategyId+(if(s.researchSignature.isBlank())"" else " • SIG="+s.researchSignature.take(140))
        ))
'''
if segment.count(old)!=1: raise SystemExit("rejected strategy reason anchor mismatch")
segment=segment.replace(old,new,1);s=s[:rs]+segment+s[re:]

start=s.index("        val rawSetups=mutableListOf<Pair<StrategySetup,Quote>>()")
end=s.index("        prefs.saveStrategyLedger(surviving,closed)",start)
new_block='''        val rejectedBefore=prefs.loadRejectedShadows(2500).size
        val rawSetups=mutableListOf<Pair<StrategySetup,Quote>>();var enriched=0;var quoteRejected=0;var historyFailed=0;var candleShort=0;var rulesMatched=0
        for((idx,inst) in selected.withIndex()){
            val q=quote(inst.tradingSymbol)?:continue;val sp=spreadPct(q);val tradedValue=q.volume*q.lastPrice
            if(!ExecutionQuality.executableQuote(q)){quoteRejected++;continue}
            val candleResult=runCatching{groww.getHistoricalCandles(token,inst.tradingSymbol,start,end,"5minute")}
            if(candleResult.isFailure){historyFailed++;continue}
            val candles=candleResult.getOrDefault(emptyList());if(candles.size<4){candleShort++;continue};enriched++
            for(def in active){
                val e=strategyEngine.evaluate(def,candles)?:continue;rulesMatched++
                val age=listingAge[inst.tradingSymbol];val boost=if(age!=null&&age<=settings.newListingDays)2.0 else 0.0
                val rawScore=(e.score+boost).coerceAtMost(100.0)
                val liquidity="₹${"%.1f".format(tradedValue/100000.0)}L traded • vol ${q.volume} • spread ${"%.2f".format(sp)}%"
                val baseSetup=StrategySetup(inst.tradingSymbol,inst.name,def.id,def.name,e.direction,rawScore,q.lastPrice,e.targetPct,e.stopPct,
                    e.evidence+" • "+liquidity+(if(boost>0)" • new-listing context" else ""),age)
                fun reject(setup:StrategySetup,reason:String){recordRejectedStrategyShadow(setup,reason)}
                if(e.targetPct<ExecutionQuality.MIN_PLAN_SEPARATION_PCT||e.stopPct<ExecutionQuality.MIN_PLAN_SEPARATION_PCT){reject(baseSetup,"PLAN_SEPARATION_GATE");continue}
                if(e.direction==TradeDirection.SHORT&&!inst.sellAllowed){reject(baseSetup,"SHORT_NOT_ALLOWED");continue}
                if(e.direction==TradeDirection.LONG&&!hasAsk(q)){reject(baseSetup,"NO_EXECUTABLE_ASK");continue}
                if(e.direction==TradeDirection.SHORT&&!hasBid(q)){reject(baseSetup,"NO_EXECUTABLE_BID");continue}
                val hb=handbookSynergy.evaluate(baseSetup,candles,q)
                val setup=baseSetup.copy(score=hb.adjustedScore,evidence=baseSetup.evidence+" • "+hb.evidence,researchSignature=hb.signature,
                    handbookQualityPct=hb.qualityPct,handbookPattern=hb.primaryPattern,handbookCombination=hb.combination)
                if(hb.hardFail){reject(setup,"HANDBOOK_HARD_GATE "+hb.failedHardFilters.joinToString(",").take(160));continue}
                if(setup.score<68.0){reject(setup,"RESEARCH_SCORE_FLOOR "+"%.1f".format(setup.score)+" < 68.0");continue}
                rawSetups+=setup to q
            }
            if(idx%10==9)progress("Strategies: handbook synergy ${idx+1}/${selected.size}")
        }
        val combined=rawSetups.groupBy{it.first.symbol to it.first.direction}.map{(_,pairs)->
            val ranked=pairs.sortedByDescending{it.first.score};val primary=ranked.first();val agree=ranked.take(3)
            ranked.drop(1).forEach{(setup,_)->recordRejectedStrategyShadow(setup,"SAME_SIDE_RULE_DEDUP stronger="+primary.first.strategyId)}
            val names=agree.map{it.first.strategyName}.distinct();val boost=((names.size-1)*2.0).coerceAtMost(4.0)
            primary.first.copy(strategyName=names.joinToString(" + "),score=(primary.first.score+boost).coerceAtMost(100.0),
                evidence="${names.size} strategy confirmation • "+agree.joinToString(" | "){it.first.evidence.take(120)}) to primary.second
        }
        val directionalWinners=combined.groupBy{it.first.symbol}.mapNotNull{(_,v)->
            val winner=v.maxByOrNull{it.first.score}
            if(winner!=null)v.filterNot{it===winner}.forEach{(setup,_)->recordRejectedStrategyShadow(setup,"DIRECTION_CONFLICT_LOST winner="+winner.first.direction.name)}
            winner
        }.sortedByDescending{it.first.score}
        val topLimit=settings.strategyTopCandidates.coerceIn(10,20)
        directionalWinners.drop(topLimit).forEach{(setup,_)->recordRejectedStrategyShadow(setup,"RANK_CUTOFF top="+topLimit)}
        val top=directionalWinners.take(topLimit);val confirmedTop=top.filter{it.first.score>=72.0}
        top.filter{it.first.score<72.0}.forEach{(setup,_)->recordRejectedStrategyShadow(setup,"BELOW_LIVE_THRESHOLD "+"%.1f".format(setup.score)+" < 72.0")}
        val existingKeys=surviving.map{"${it.setup.symbol}|${it.setup.direction.name}"}.toMutableSet();val newlyOpened=mutableListOf<StrategySetup>()
        if(now.toLocalTime()<LocalTime.of(15,10)){
            for((setup,q) in confirmedTop){
                val key="${setup.symbol}|${setup.direction.name}"
                if(key in existingKeys){recordRejectedStrategyShadow(setup,"ALREADY_LIVE_DUPLICATE");continue}
                val sp=spreadPct(q);val id="${date}|$key|${setup.strategyId}"
                surviving+=StrategyRecommendation(id,setup,System.currentTimeMillis(),System.currentTimeMillis(),q.lastPrice,tradedValue=q.volume*q.lastPrice,volume=q.volume,spreadPct=sp)
                existingKeys+=key;newlyOpened+=setup
            }
        }else confirmedTop.forEach{(setup,_)->recordRejectedStrategyShadow(setup,"LATE_SESSION_GATE >=15:10")}
'''
s=s[:start]+new_block+s[end:]

old='''        val perfs=prefs.strategyPerformances(bundle.strategies,settings)
        val summary=StrategyTournamentSummary(System.currentTimeMillis(),cash.size,active.size,enriched,top.map{it.first},active,perfs,bundle.version,
            "${active.size} strategies • ${selected.size} symbols • ${enriched} enriched • ${quoteRejected} liquidity rejects • ${historyFailed} history failures • ${candleShort} short histories • ${rulesMatched} rule matches • ${surviving.size} LIVE • ${newlyOpened.size} new • ${top.size} watching")
        DiagnosticLog.log(appContext,"STRATEGY","${summary.message}")
'''
new='''        val perfs=prefs.strategyPerformances(bundle.strategies,settings);val insights=prefs.championResearchInsights(bundle.strategies,6)
        val rejectedAfter=prefs.loadRejectedShadows(2500).size;val rejectedAdded=(rejectedAfter-rejectedBefore).coerceAtLeast(0)
        val champions=perfs.count{it.status==StrategyStatus.CHAMPION};val suspended=perfs.count{it.status==StrategyStatus.SUSPENDED}
        val summary=StrategyTournamentSummary(System.currentTimeMillis(),cash.size,active.size,enriched,top.map{it.first},active,perfs,bundle.version,
            "${active.size} active • HB 100/50/50 • ${selected.size} symbols • ${enriched} enriched • ${quoteRejected} liquidity rejects • ${historyFailed} history failures • ${candleShort} short histories • ${rulesMatched} rule matches • ${surviving.size} LIVE • ${newlyOpened.size} new • CHAMP ${champions} • SUSP ${suspended} • rejected+journal ${rejectedAdded}",
            insights,rejectedAfter,HandbookSynergyEngine.VERSION)
        DiagnosticLog.log(appContext,"STRATEGY","${summary.message}")
'''
s=one(s,old,new,"research summary")
wr(p,s)
print("Global Edge v1.4.0 handbook synergy, complete rejection journal and champion governance applied")

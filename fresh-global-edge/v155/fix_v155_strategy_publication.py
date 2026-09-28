#!/usr/bin/env python3
from pathlib import Path
import sys
root=Path(sys.argv[1]).resolve()

def rw(rel): return (root/rel).read_text(encoding="utf-8")
def wr(rel,s): (root/rel).write_text(s,encoding="utf-8")
def one(s,old,new,label):
    n=s.count(old)
    if n!=1: raise SystemExit(f"{label}: expected 1 found {n}")
    return s.replace(old,new,1)

# Version bump.
p="app/build.gradle.kts"; s=rw(p)
s=one(s,"versionCode = 154","versionCode = 155","versionCode")
s=one(s,'versionName = "1.5.4"','versionName = "1.5.5"',"versionName")
wr(p,s)

# Strategy scanner: a high-quality Challenger can publish to LIVE after all hard
# data/execution/risk gates pass. Maturity remains visible and Challenger shadow
# evidence is still collected prospectively.
p="app/src/main/java/com/suhas/ucsentinel/data/repository/UCSentinelRepository.kt"; s=rw(p)
old='''        val existingKeys=surviving.map{"${it.setup.symbol}|${it.setup.direction.name}"}.toMutableSet();val newlyOpened=mutableListOf<StrategySetup>()
        var challengerOpened=0
        if(now.toLocalTime()<LocalTime.of(15,10)){
            // Challenger evidence is deliberately broader than LIVE publication. 68-71.9 setups
            // remain completely non-executable, but now generate prospective samples so a good
            // strategy can earn ACTIVE/CHAMPION status instead of starving for observations.
            for((setup,_) in researchTop){
                val status=governance[setup.strategyId]?.status?:StrategyStatus.CHALLENGER
                if(status==StrategyStatus.CHALLENGER&&openChallengerShadow(setup))challengerOpened++
            }
            for((setup,q) in confirmedTop){
                val status=governance[setup.strategyId]?.status?:StrategyStatus.CHALLENGER
                if(status==StrategyStatus.CHALLENGER)continue
                if(!ExecutionQuality.executableQuote(q)){
                    recordRejectedStrategyShadow(setup,"LIVE_EXECUTION_GATE")
                    continue
                }
                if(status!=StrategyStatus.ACTIVE&&status!=StrategyStatus.CHAMPION){
                    recordRejectedStrategyShadow(setup,"GOVERNANCE_"+status.name)
                    continue
                }
                val key="${setup.symbol}|${setup.direction.name}"
                if(key in existingKeys){recordRejectedStrategyShadow(setup,"ALREADY_LIVE_DUPLICATE");continue}
                val sp=spreadPct(q);val id="${date}|$key|${setup.strategyId}"
                surviving+=StrategyRecommendation(id,setup,System.currentTimeMillis(),System.currentTimeMillis(),q.lastPrice,tradedValue=q.volume*q.lastPrice,volume=q.volume,spreadPct=sp)
                existingKeys+=key;newlyOpened+=setup
                prefs.appendDecisionSnapshot(setup,"LIVE_PUBLISHED",status.name,NseTradingCalendar2026.VERSION,HandbookSynergyEngine.VERSION,
                    sectorIndustry=industryBundle?.bySymbol?.get(setup.symbol).orEmpty(),macroRisk=evidenceFabric.macroRisk(now,macroEvents).first?.name?:"NONE")
                DiagnosticLog.log(appContext,"DECISION","LIVE_PUBLISHED • ${setup.symbol} • ${setup.strategyId} • $status")
            }
        }else confirmedTop.forEach{(setup,_)->recordRejectedStrategyShadow(setup,"LATE_SESSION_GATE >=15:10")}
'''
new='''        val existingKeys=surviving.map{"${it.setup.symbol}|${it.setup.direction.name}"}.toMutableSet();val newlyOpened=mutableListOf<StrategySetup>()
        var challengerOpened=0
        var challengerPublished=0
        var activePublished=0
        var championPublished=0
        var probationBlocked=0
        var suspendedBlocked=0
        var liveExecutionRejected=0
        var liveCapRejected=0
        val maxNewLivePerPass=5
        if(now.toLocalTime()<LocalTime.of(15,10)){
            // 68-71.9 remains research/shadow only. A 72+ Challenger may now become LIVE
            // only after the same hard handbook/macro/liquidity/execution gates as mature
            // strategies. The Challenger shadow lane still runs independently for evidence.
            for((setup,_) in researchTop){
                val status=governance[setup.strategyId]?.status?:StrategyStatus.CHALLENGER
                if(status==StrategyStatus.CHALLENGER&&openChallengerShadow(setup))challengerOpened++
            }
            for((setup,q) in confirmedTop){
                val status=governance[setup.strategyId]?.status?:StrategyStatus.CHALLENGER
                if(!ExecutionQuality.executableQuote(q)){
                    liveExecutionRejected++
                    recordRejectedStrategyShadow(setup,"LIVE_EXECUTION_GATE")
                    continue
                }
                if(status==StrategyStatus.SUSPENDED){
                    suspendedBlocked++
                    recordRejectedStrategyShadow(setup,"GOVERNANCE_SUSPENDED")
                    continue
                }
                if(status==StrategyStatus.PROBATION){
                    probationBlocked++
                    recordRejectedStrategyShadow(setup,"GOVERNANCE_PROBATION")
                    continue
                }
                if(newlyOpened.size>=maxNewLivePerPass){
                    liveCapRejected++
                    recordRejectedStrategyShadow(setup,"LIVE_PUBLICATION_CAP top="+maxNewLivePerPass)
                    continue
                }
                val key="${setup.symbol}|${setup.direction.name}"
                if(key in existingKeys){recordRejectedStrategyShadow(setup,"ALREADY_LIVE_DUPLICATE");continue}
                val maturityNote="maturity "+status.name+(if(status==StrategyStatus.CHALLENGER)" • prospective shadow active" else "")
                val liveSetup=setup.copy(evidence=setup.evidence+" • "+maturityNote)
                val sp=spreadPct(q);val id="${date}|$key|${setup.strategyId}"
                surviving+=StrategyRecommendation(id,liveSetup,System.currentTimeMillis(),System.currentTimeMillis(),q.lastPrice,tradedValue=q.volume*q.lastPrice,volume=q.volume,spreadPct=sp)
                existingKeys+=key;newlyOpened+=liveSetup
                when(status){
                    StrategyStatus.CHALLENGER->challengerPublished++
                    StrategyStatus.ACTIVE->activePublished++
                    StrategyStatus.CHAMPION->championPublished++
                    else->{}
                }
                prefs.appendDecisionSnapshot(liveSetup,"LIVE_PUBLISHED",status.name,NseTradingCalendar2026.VERSION,HandbookSynergyEngine.VERSION,
                    sectorIndustry=industryBundle?.bySymbol?.get(setup.symbol).orEmpty(),macroRisk=evidenceFabric.macroRisk(now,macroEvents).first?.name?:"NONE")
                DiagnosticLog.log(appContext,"DECISION","LIVE_PUBLISHED • ${setup.symbol} • ${setup.strategyId} • $status")
            }
        }else confirmedTop.forEach{(setup,_)->recordRejectedStrategyShadow(setup,"LATE_SESSION_GATE >=15:10")}
'''
s=one(s,old,new,"strategy publication governance")

old='''            (if(challengerOnly)"SHADOW RUN • " else "")+"${active.size} active • HB 100/50/50 • ${selected.size} symbols • ${enriched} enriched • ${quoteRejected} liquidity rejects • ${historyFailed} history failures • ${candleShort} short histories • ${rulesMatched} rule matches • ${surviving.size} LIVE • ${newlyOpened.size} new • challenger shadows +$challengerOpened • CHAMP ${champions} • SUSP ${suspended} • rejected+journal ${rejectedAdded}",
'''
new='''            (if(challengerOnly)"SHADOW RUN • " else "")+"${active.size} active • HB 100/50/50 • ${selected.size} symbols • ${enriched} enriched • ${quoteRejected} liquidity rejects • ${historyFailed} history failures • ${candleShort} short histories • ${rulesMatched} rule matches • ${confirmedTop.size} score>=72 • ${liveExecutionRejected} execution rejects • ${probationBlocked} probation blocked • ${suspendedBlocked} suspended blocked • ${liveCapRejected} cap rejects • ${surviving.size} LIVE • ${newlyOpened.size} new [C ${challengerPublished} / A ${activePublished} / CH ${championPublished}] • challenger shadows +$challengerOpened • CHAMP ${champions} • SUSP ${suspended} • rejected+journal ${rejectedAdded}",
'''
s=one(s,old,new,"strategy summary diagnostics")
wr(p,s)

# UC: preserve the strict LIVE safety gate, but expose the funnel so a blank LIVE
# tab is explainable rather than opaque.
p="app/src/main/java/com/suhas/ucsentinel/domain/engine/ScannerEngine.kt"; s=rw(p)
old='''        val qualified = qualifiedAll.take(settings.maxFinalCandidates)
'''
new='''        val qualified = qualifiedAll.take(settings.maxFinalCandidates)
        val scoreQualifiedCount=candidates.count{it.score>=effectiveThreshold}
        val liveReadyCount=candidates.count{"UC_LIVE_READY" in it.activeStrategies}
        val executionReadyCount=candidates.count{"EXECUTION_READY" in it.activeStrategies}
        val funnel="funnel raw ${candidates.size} • score ${scoreQualifiedCount} • UC-ready ${liveReadyCount} • execution-ready ${executionReadyCount} • LIVE ${qualified.size}"
'''
s=one(s,old,new,"uc funnel counters")

old='''                nextSessionMode && qualified.isNotEmpty() -> "NEXT SESSION • ${qualified.size} UC candidate(s) passed research threshold ${"%.1f".format(effectiveThreshold)}"
                nextSessionMode && final.isNotEmpty() -> "NEXT SESSION WATCH • best ${"%.1f".format(final.first().score)} vs threshold ${"%.1f".format(effectiveThreshold)}"
                qualified.isNotEmpty() -> "${qualified.size} candidate(s) passed UC threshold ${"%.1f".format(effectiveThreshold)}${if(settings.adaptiveRangesEnabled) " • adaptive" else ""}"
                final.isNotEmpty() -> "WATCHLIST ONLY • no qualified UC candidate • best ${"%.1f".format(final.first().score)} vs threshold ${"%.1f".format(effectiveThreshold)}"
                settings.adaptiveRangesEnabled -> "NO QUALIFIED UC CANDIDATE • adaptive floor ${thresholdDecision?.floor?.toInt() ?: 66}"
                else -> "NO QUALIFIED UC CANDIDATE"
'''
new='''                nextSessionMode && qualified.isNotEmpty() -> "NEXT SESSION • ${qualified.size} UC candidate(s) passed research threshold ${"%.1f".format(effectiveThreshold)} • $funnel"
                nextSessionMode && final.isNotEmpty() -> "NEXT SESSION WATCH • best ${"%.1f".format(final.first().score)} vs threshold ${"%.1f".format(effectiveThreshold)} • $funnel"
                qualified.isNotEmpty() -> "${qualified.size} candidate(s) passed UC threshold ${"%.1f".format(effectiveThreshold)}${if(settings.adaptiveRangesEnabled) " • adaptive" else ""} • $funnel"
                final.isNotEmpty() -> "WATCHLIST ONLY • no qualified UC candidate • best ${"%.1f".format(final.first().score)} vs threshold ${"%.1f".format(effectiveThreshold)} • $funnel"
                settings.adaptiveRangesEnabled -> "NO QUALIFIED UC CANDIDATE • adaptive floor ${thresholdDecision?.floor?.toInt() ?: 66} • $funnel"
                else -> "NO QUALIFIED UC CANDIDATE • $funnel"
'''
s=one(s,old,new,"uc message diagnostics")
wr(p,s)

# UI: make Strategy/UC diagnostics visible when LIVE is empty.
p="app/src/main/java/com/suhas/ucsentinel/ui/CompactMarketScreens.kt"; s=rw(p)
old='''                if(live.isEmpty())item{EmptyState("No live upper-circuit call","The scanner will not force a stock into LIVE. NEXT and 3 PM lists remain available separately.")}
'''
new='''                if(live.isEmpty())item{EmptyState("No live upper-circuit call",if(ucMessage.isNotBlank())ucMessage else "The scanner will not force a stock into LIVE. Open WATCH to inspect near-miss research candidates.")}
'''
s=one(s,old,new,"uc empty state diagnostics")

old='''            if(visibleLive.isEmpty()&&visibleWatch.isEmpty())item{EmptyState(if(state.marketSession.isOpen)"No live strategy call" else "Market closed • no LIVE strategy calls",if(state.marketSession.isOpen)"Scanner is running; no liquid setup has reached the LIVE threshold yet." else "Intraday strategy calls are closed and scored after the session; they never remain LIVE overnight.")}
'''
new='''            if(visibleLive.isEmpty()&&visibleWatch.isEmpty())item{EmptyState(if(state.marketSession.isOpen)"No live strategy call" else "Market closed • no LIVE strategy calls",if(state.marketSession.isOpen)(state.strategyTournamentSummary?.message?.takeIf{it.isNotBlank()}?:"Scanner is running; no setup has cleared score, execution and hard-risk gates yet.") else "Intraday strategy calls are closed and scored after the session; they never remain LIVE overnight.")}
'''
s=one(s,old,new,"strategy empty state diagnostics")
wr(p,s)

print("Global Edge v1.5.5 strategy publication + UC diagnostics patch applied")

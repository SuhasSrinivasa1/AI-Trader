#!/usr/bin/env python3
from pathlib import Path
import sys
root=Path(sys.argv[1]).resolve()
def rw(rel): return (root/rel).read_text(encoding="utf-8")
def wr(rel,s): (root/rel).write_text(s,encoding="utf-8")
def one(s,old,new,label):
    n=s.count(old)
    if n!=1: raise SystemExit(f"{label}: expected 1, found {n}")
    return s.replace(old,new,1)
p="app/src/main/java/com/suhas/ucsentinel/data/repository/UCSentinelRepository.kt";s=rw(p)

needle='''        val settings=prefs.loadSettings();require(settings.strategyTournamentEnabled){"Strategy tournament is disabled"}
        require(ensureAutomationAuthentication()){ "Groww authentication is required. TOTP mode can renew automatically." }
'''
replacement='''        val settings=prefs.loadSettings();require(settings.strategyTournamentEnabled){"Strategy tournament is disabled"}
        require(marketSessionInfo().isOpen){"Strategy live/shadow scan runs only during an exact NSE regular session."}
        require(ensureAutomationAuthentication()){ "Groww authentication is required. TOTP mode can renew automatically." }
        refreshEvidenceFeedsIfDue()
'''
s=one(s,needle,replacement,"strategy calendar/evidence gate")

needle='''        val movers=mutableListOf<Pair<Instrument,Double>>()
        cash.chunked(50).forEachIndexed{idx,batch->
'''
replacement='''        val movers=mutableListOf<Pair<Instrument,Double>>()
        val signedReturn=mutableMapOf<String,Double>()
        cash.chunked(50).forEachIndexed{idx,batch->
'''
s=one(s,needle,replacement,"sector signed returns")
needle='''                val move=if(o.open>0)kotlin.math.abs(o.close/o.open-1.0)*100 else 0.0
                movers+=i to move
'''
replacement='''                val signed=if(o.open>0)(o.close/o.open-1.0)*100 else 0.0
                val move=kotlin.math.abs(signed)
                signedReturn[i.tradingSymbol]=signed
                movers+=i to move
'''
s=one(s,needle,replacement,"sector returns")

needle='''        val listingAge=newListingsCache.associate{it.symbol to it.daysListed}
        val now=ZonedDateTime.now(ist);val date=now.toLocalDate();val start=date.atTime(9,15).format(dateTimeFmt);val end=now.plusMinutes(1).format(dateTimeFmt)
'''
replacement=r'''        val listingAge=newListingsCache.associate{it.symbol to it.daysListed}
        val now=ZonedDateTime.now(ist);val date=now.toLocalDate();val start=date.atTime(9,15).format(dateTimeFmt);val end=now.plusMinutes(1).format(dateTimeFmt)
        val industryMap=runCatching{sectorClient.load(false)}.getOrDefault(emptyMap())
        val sectorRows=mutableMapOf<String,SectorIntelligence>()
        selected.forEach{inst->
            val industry=industryMap[inst.tradingSymbol]?:return@forEach
            val peerSymbols=industryMap.filterValues{it==industry}.keys
            val peerReturns=peerSymbols.mapNotNull{signedReturn[it]}
            val stockRet=signedReturn[inst.tradingSymbol]?:return@forEach
            if(peerReturns.size<2)return@forEach
            val avg=peerReturns.average()
            val breadth=peerReturns.count{it>0.0}*100.0/peerReturns.size
            val confirmation=(stockRet>0.0&&breadth>=55.0)||(stockRet<0.0&&breadth<=45.0)
            sectorRows[inst.tradingSymbol]=SectorIntelligence(inst.tradingSymbol,industry,peerReturns.size,breadth,avg,stockRet,stockRet-avg,confirmation,System.currentTimeMillis(),SectorIndustryClient.SOURCE_LABEL)
        }
        latestSectorContext=sectorRows
        DiagnosticLog.log(appContext,"SECTOR","NIFTY500 mapped=${industryMap.size} selected-context=${sectorRows.size}")
        MacroEventRegistry.active(date).forEach{event->
            evidenceStore.recordProspectiveEvidence("",EvidenceType.MACRO_EVENT,event.id,event.label,event.source,date.toString(),"",event.severity,event.hardBlock)
        }
'''
s=one(s,needle,replacement,"sector context")

needle='''                val hb=handbookSynergy.evaluate(baseSetup,candles,q)
                val setup=baseSetup.copy(score=hb.adjustedScore,evidence=baseSetup.evidence+" • "+hb.evidence,researchSignature=hb.signature,
                    handbookQualityPct=hb.qualityPct,handbookPattern=hb.primaryPattern,handbookCombination=hb.combination)
                if(hb.hardFail){reject(setup,"HANDBOOK_HARD_GATE "+hb.failedHardFilters.joinToString(",").take(160));continue}
                if(setup.score<68.0){reject(setup,"RESEARCH_SCORE_FLOOR "+"%.1f".format(setup.score)+" < 68.0");continue}
                rawSetups+=setup to q
'''
replacement=r'''                val hb=handbookSynergy.evaluate(baseSetup,candles,q)
                val sector=sectorRows[inst.tradingSymbol]
                val sectorSupport=sector?.let{if(e.direction==TradeDirection.LONG)it.breadthPct>=55.0&&it.stockVsSectorPct>=-0.5 else it.breadthPct<=45.0&&it.stockVsSectorPct<=0.5}
                val sectorAdj=when(sectorSupport){true->2.0;false->-2.0;null->0.0}
                val activeMacro=MacroEventRegistry.active(date)
                val macroAdj=if(activeMacro.isNotEmpty())-2.0 else 0.0
                val pit=evidenceStore.evidenceAt(inst.tradingSymbol,System.currentTimeMillis())
                val sameDayHard=pit.any{it.hardBlock&&it.effectiveAtText==date.toString()}
                val evidenceText=buildString{
                    append(baseSetup.evidence);append(" • ");append(hb.evidence)
                    if(sector!=null)append(" • Sector ${sector.industry}: breadth ${"%.0f".format(sector.breadthPct)}%, stock-v-sector ${"%+.2f".format(sector.stockVsSectorPct)}%")
                    if(activeMacro.isNotEmpty())append(" • Macro risk: "+activeMacro.joinToString{it.label})
                    val pcount=pit.count{it.type==EvidenceType.FUNDAMENTAL||it.type==EvidenceType.ANALYST_REVISION||it.type==EvidenceType.EARNINGS_DATE}
                    if(pcount>0)append(" • PIT evidence $pcount item(s), no backfill")
                }
                val setup=baseSetup.copy(score=(hb.adjustedScore+sectorAdj+macroAdj).coerceIn(0.0,100.0),evidence=evidenceText,researchSignature=hb.signature,
                    handbookQualityPct=hb.qualityPct,handbookPattern=hb.primaryPattern,handbookCombination=hb.combination)
                if(sameDayHard){reject(setup,"POINT_IN_TIME_EVENT_HARD_GATE same-day earnings/event");continue}
                if(hb.hardFail){reject(setup,"HANDBOOK_HARD_GATE "+hb.failedHardFilters.joinToString(",").take(160));continue}
                if(setup.score<68.0){reject(setup,"RESEARCH_SCORE_FLOOR "+"%.1f".format(setup.score)+" < 68.0");continue}
                val lifecycle=effectiveStrategyStatus(def.id,bundle.strategies,settings)
                if(lifecycle==StrategyStatus.CHALLENGER){
                    recordChallengerShadow(setup,now,30)
                    continue
                }
                if(lifecycle==StrategyStatus.PROBATION||lifecycle==StrategyStatus.SUSPENDED){
                    reject(setup,"LIFECYCLE_GATE $lifecycle")
                    continue
                }
                rawSetups+=setup to q
'''
s=one(s,needle,replacement,"PIT sector challenger overlay")

needle='''                surviving+=StrategyRecommendation(id,setup,System.currentTimeMillis(),System.currentTimeMillis(),q.lastPrice,tradedValue=q.volume*q.lastPrice,volume=q.volume,spreadPct=sp)
                existingKeys+=key;newlyOpened+=setup
'''
replacement='''                surviving+=StrategyRecommendation(id,setup,System.currentTimeMillis(),System.currentTimeMillis(),q.lastPrice,tradedValue=q.volume*q.lastPrice,volume=q.volume,spreadPct=sp)
                recordDecisionSnapshot(setup.symbol,setup.direction.name,"STRATEGY",setup.strategyId,"LIVE_PUBLISHED",setup.score,setup.evidence,false)
                existingKeys+=key;newlyOpened+=setup
'''
s=one(s,needle,replacement,"strategy live decision")

s=s.replace("val perfs=prefs.strategyPerformances(bundle.strategies,settings);val insights=prefs.championResearchInsights(bundle.strategies,6)",
            "val perfs=effectiveStrategyPerformances(bundle.strategies,settings);val insights=prefs.championResearchInsights(bundle.strategies,6)",1)
s=s.replace('val champions=perfs.count{it.status==StrategyStatus.CHAMPION};val suspended=perfs.count{it.status==StrategyStatus.SUSPENDED}',
            'val champions=perfs.count{it.status==StrategyStatus.CHAMPION};val suspended=perfs.count{it.status==StrategyStatus.SUSPENDED};val challengerOpen=evidenceStore.loadChallengers(3000).count{it.status==ChallengerShadowStatus.OPEN}',1)
s=s.replace('• CHAMP ${champions} • SUSP ${suspended} • rejected+journal ${rejectedAdded}"',
            '• CHAMP ${champions} • SUSP ${suspended} • CHALLENGER open ${challengerOpen} • rejected+journal ${rejectedAdded}"',1)

anchor='''    suspend fun refreshGlobalMappings(force:Boolean=false):Int{
'''
insert=r'''    suspend fun refreshSectorIntelligence():Int{
        val map=sectorClient.load(true)
        DiagnosticLog.log(appContext,"SECTOR","Manual NIFTY500 industry refresh mapped=${map.size}")
        return map.size
    }

'''+anchor
s=one(s,anchor,insert,"sector refresh")


wr(p,s)
print('v1.5 sector/evidence strategy scan applied')

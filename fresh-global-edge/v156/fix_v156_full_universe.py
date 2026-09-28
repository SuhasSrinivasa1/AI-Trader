#!/usr/bin/env python3
from pathlib import Path
import sys
root=Path(sys.argv[1]).resolve()

def rw(rel): return (root/rel).read_text(encoding='utf-8')
def wr(rel,s): (root/rel).write_text(s,encoding='utf-8')
def replace_once(s,old,new,label):
    n=s.count(old)
    if n != 1: raise SystemExit(f'{label}: expected 1 found {n}')
    return s.replace(old,new,1)

p='app/build.gradle.kts'; s=rw(p)
s=replace_once(s,'versionCode = 155','versionCode = 156','versionCode')
s=replace_once(s,'versionName = "1.5.5"','versionName = "1.5.6"','versionName')
wr(p,s)

p='app/src/main/java/com/suhas/ucsentinel/data/local/AppPreferences.kt'; s=rw(p)
anchor='    fun lastStrategyCatalogRefreshAt():Long=prefs.getLong("last_strategy_catalog_refresh_at",0L)\n'
if 'fun strategyDeepScanCursor()' not in s:
    if anchor not in s: raise SystemExit('prefs cursor anchor missing')
    s=s.replace(anchor,anchor+'    fun strategyDeepScanCursor():Int=prefs.getInt("strategy_deep_scan_cursor_v156",0).coerceAtLeast(0)\n    fun setStrategyDeepScanCursor(value:Int){prefs.edit().putInt("strategy_deep_scan_cursor_v156",value.coerceAtLeast(0)).apply()}\n',1)
wr(p,s)

p='app/src/main/java/com/suhas/ucsentinel/data/repository/UCSentinelRepository.kt'; s=rw(p)
start=s.index('        // Intraday strategy execution is deliberately stricter than the broad UC universe.')
end=s.index('        val listingAge=newListingsCache.associate{it.symbol to it.daysListed}', start)
new_sel='''        // FULL NSE universe: use Groww's instrument master and screen every currently buy-allowed
        // NSE CASH equity (instrument_type=EQ). The previous fixed 24-40 top-mover sample is removed.
        // Stage 1 uses the official OHLC multi-symbol API in batches of 50 across the whole universe.
        val cash=universe.filter{it.exchange=="NSE"&&it.segment=="CASH"&&it.instrumentType=="EQ"&&it.buyAllowed}.distinctBy{it.tradingSymbol}
        val carried=(lastSavedDualSummary()?.uc?.candidates.orEmpty()+lastSavedDualSummary()?.demand?.candidates.orEmpty()).map{it.symbol}.toSet()
        val existingLive=prefs.loadStrategyLive().toMutableList()
        val prioritySymbols=(carried+existingLive.map{it.setup.symbol}).toSet()
        progress("Strategies: FULL NSE equity scan ${cash.size} stocks • ${active.size} rules • OHLC batches of 50")

        data class Stage1(val instrument:Instrument,val movePct:Double,val rangePct:Double)
        val stage1=mutableListOf<Stage1>()
        val sessionOhlc=linkedMapOf<String,Ohlc>()
        val batches=cash.chunked(50)
        batches.forEachIndexed{idx,batch->
            val map=runCatching{groww.getOhlcBatch(token,batch.map{it.tradingSymbol})}.getOrDefault(emptyMap())
            sessionOhlc.putAll(map)
            batch.forEach{i->
                val o=map[i.tradingSymbol]?:return@forEach
                if(o.close<20.0||o.open<=0.0||o.high<=0.0||o.low<=0.0)return@forEach
                val move=kotlin.math.abs(o.close/o.open-1.0)*100.0
                val range=((o.high-o.low)/o.open*100.0).coerceAtLeast(0.0)
                // Broad entry prefilter, not a sample. Every symbol is checked in Stage 1; names that
                // meet entry-motion criteria enter the deep queue. Open/carry names are always retained.
                if(move>=0.15||range>=0.45||i.tradingSymbol in prioritySymbols)stage1+=Stage1(i,move,range)
            }
            if(idx%10==9||idx==batches.lastIndex)
                progress("Strategies: full-universe OHLC ${minOf((idx+1)*50,cash.size)}/${cash.size} • entry-prefilter ${stage1.size}")
        }

        // API-safe deep stage. The deep queue is deterministic and continued next pass; it is never
        // randomly sampled or silently dropped. 450 names/pass stays compatible with a 5-minute cadence
        // under the app's conservative historical request pacing.
        val deepBudget=450
        val essential=stage1.filter{it.instrument.tradingSymbol in prioritySymbols}
        val rest=stage1.filterNot{it.instrument.tradingSymbol in prioritySymbols}.sortedBy{it.instrument.tradingSymbol}
        val cursor=if(rest.isEmpty())0 else prefs.strategyDeepScanCursor()%rest.size
        val rotated=if(rest.isEmpty())emptyList() else rest.drop(cursor)+rest.take(cursor)
        val room=(deepBudget-essential.size).coerceAtLeast(0)
        val chosenRest=rotated.take(room)
        val selected=(essential+chosenRest).distinctBy{it.instrument.tradingSymbol}
        val nextCursor=if(rest.isEmpty())0 else (cursor+chosenRest.size)%rest.size
        prefs.setStrategyDeepScanCursor(nextCursor)
        val deferred=(stage1.size-selected.size).coerceAtLeast(0)
        progress("Strategies: deep scan ${selected.size}/${stage1.size} qualifying stocks • deferred $deferred queued, not sampled")
'''
s=s[:start]+new_sel+s[end:]

needle='        val existingLive=prefs.loadStrategyLive().toMutableList()\n        val closed=prefs.loadStrategyClosed(500).toMutableList()\n'
if needle not in s: raise SystemExit('existingLive duplicate anchor missing')
s=s.replace(needle,'        val closed=prefs.loadStrategyClosed(500).toMutableList()\n',1)

start=s.index('        val rejectedBefore=prefs.loadRejectedShadows(2500).size')
end=s.index('        val combined=rawSetups.groupBy', start)
new_loop='''        val rejectedBefore=prefs.loadRejectedShadows(2500).size
        val rawSetups=mutableListOf<Pair<StrategySetup,Quote>>();var enriched=0;var quoteRejected=0;var historyFailed=0;var candleShort=0;var rulesMatched=0
        for((idx,row) in selected.withIndex()){
            val inst=row.instrument
            // Historical/rule evaluation comes before single-symbol Quote/depth. This is deliberate:
            // Live Data quota is spent only when at least one strategy rule actually fires.
            val candleResult=runCatching{groww.getHistoricalCandles(token,inst.tradingSymbol,start,end,"5minute")}
            if(candleResult.isFailure){historyFailed++;continue}
            val candles=candleResult.getOrDefault(emptyList());if(candles.size<2){candleShort++;continue}
            val evals=buildList{
                for(def in active){
                    if(challengerOnly && governance[def.id]?.status!=StrategyStatus.CHALLENGER)continue
                    val e=strategyEngine.evaluate(def,candles)?:continue
                    add(def to e)
                }
            }
            if(evals.isEmpty()){
                if(idx%25==24)progress("Strategies: deep rules ${idx+1}/${selected.size} • matches $rulesMatched")
                continue
            }
            rulesMatched+=evals.size

            val q=quote(inst.tradingSymbol)?:continue;val sp=spreadPct(q);val tradedValue=q.volume*q.lastPrice
            val strictQuoteReady=ExecutionQuality.executableQuote(q)
            val earlyResearch=now.toLocalTime()<LocalTime.of(9,45)
            val researchQuoteReady=if(earlyResearch) ExecutionQuality.discoveryQuote(q)&&hasBid(q)&&hasAsk(q) else strictQuoteReady
            if(!researchQuoteReady){quoteRejected++;continue}
            enriched++

            for((def,e) in evals){
                val age=listingAge[inst.tradingSymbol];val boost=if(age!=null&&age<=settings.newListingDays)2.0 else 0.0
                val rawScore=(e.score+boost).coerceAtMost(100.0)
                val maturity=governance[def.id]?.status?:StrategyStatus.CHALLENGER
                val liquidity="₹${"%.1f".format(tradedValue/100000.0)}L traded • vol ${q.volume} • spread ${"%.2f".format(sp)}%"
                val baseSetup=StrategySetup(inst.tradingSymbol,inst.name,def.id,def.name,e.direction,rawScore,q.lastPrice,e.targetPct,e.stopPct,
                    e.evidence+" • "+liquidity+" • maturity "+maturity.name+(if(boost>0)" • new-listing context" else ""),age)
                fun reject(setup:StrategySetup,reason:String){recordRejectedStrategyShadow(setup,reason)}
                if(e.targetPct<ExecutionQuality.MIN_PLAN_SEPARATION_PCT||e.stopPct<ExecutionQuality.MIN_PLAN_SEPARATION_PCT){reject(baseSetup,"PLAN_SEPARATION_GATE");continue}
                if(e.direction==TradeDirection.SHORT&&(inst.series!="EQ"||!inst.sellAllowed)){reject(baseSetup,"SHORT_NOT_INTRADAY_ELIGIBLE");continue}
                if(e.direction==TradeDirection.LONG&&!hasAsk(q)){reject(baseSetup,"NO_EXECUTABLE_ASK");continue}
                if(e.direction==TradeDirection.SHORT&&!hasBid(q)){reject(baseSetup,"NO_EXECUTABLE_BID");continue}
                val hb=handbookSynergy.evaluate(baseSetup,candles,q)
                var setup=baseSetup.copy(score=hb.adjustedScore,evidence=baseSetup.evidence+" • "+hb.evidence,researchSignature=hb.signature,
                    handbookQualityPct=hb.qualityPct,handbookPattern=hb.primaryPattern,handbookCombination=hb.combination)

                val sector=industryBundle?.let{evidenceFabric.sector(setup.symbol,setup.direction,it.bySymbol,sessionOhlc)}
                if(sector!=null){
                    val adj=evidenceFabric.sectorAdjustment(sector)
                    setup=setup.copy(score=(setup.score+adj).coerceIn(0.0,100.0),evidence=setup.evidence+
                        " • sector ${sector.industry} • peers ${sector.peersObserved} • breadth ${"%.0f".format(sector.directionalBreadthPct)}% • RS ${"%+.2f".format(sector.relativeStrengthPct)}%")
                    val eid=("SECTOR|"+setup.symbol+"|"+sector.observedAt).hashCode().toUInt().toString(16)
                    prefs.appendPointInTimeEvidence(PointInTimeEvidence("PIT-"+eid,setup.symbol,EvidenceKind.SECTOR,"NIFTY500 industry intelligence",
                        "industry=${sector.industry}; breadth=${sector.directionalBreadthPct}; relativeStrength=${sector.relativeStrengthPct}; peerConfirmed=${sector.peerConfirmed}",
                        sector.source,observedAt=sector.observedAt,effectiveAt=sector.observedAt,revisionId=eid,notes="Prospective sector snapshot"))
                }
                if(evidenceFabric.shouldHardWaitForMacro(now,macroEvents)){reject(setup,"MACRO_HARD_WAIT "+(evidenceFabric.macroRisk(now,macroEvents).second));continue}
                val companyEvent=evidenceFabric.companyEventRisk(setup.symbol,System.currentTimeMillis(),macroEvents)
                if(companyEvent!=null)setup=setup.copy(score=(setup.score-2.0).coerceAtLeast(0.0),evidence=setup.evidence+" • event-risk "+companyEvent.title)
                if(hb.hardFail){reject(setup,"HANDBOOK_HARD_GATE "+hb.failedHardFilters.joinToString(",").take(160));continue}
                if(setup.score<68.0){reject(setup,"RESEARCH_SCORE_FLOOR "+"%.1f".format(setup.score)+" < 68.0");continue}
                rawSetups+=setup to q
            }
            if(idx%25==24||idx==selected.lastIndex)progress("Strategies: deep rules ${idx+1}/${selected.size} • rule matches $rulesMatched • matched+quoted $enriched")
        }
'''
s=s[:start]+new_loop+s[end:]

old='''            (if(challengerOnly)"SHADOW RUN • " else "")+"${active.size} active • HB 100/50/50 • ${selected.size} symbols • ${enriched} enriched • ${quoteRejected} liquidity rejects • ${historyFailed} history failures • ${candleShort} short histories • ${rulesMatched} rule matches • ${confirmedTop.size} score>=72 • ${liveExecutionRejected} execution rejects • ${probationBlocked} probation blocked • ${suspendedBlocked} suspended blocked • ${liveCapRejected} cap rejects • ${surviving.size} LIVE • ${newlyOpened.size} new [C ${challengerPublished} / A ${activePublished} / CH ${championPublished}] • challenger shadows +$challengerOpened • CHAMP ${champions} • SUSP ${suspended} • rejected+journal ${rejectedAdded}",
'''
new='''            (if(challengerOnly)"SHADOW RUN • " else "")+"FULL NSE ${cash.size} • OHLC all • entry-prefilter ${stage1.size} • deep ${selected.size} • queued ${deferred} • ${active.size} rules • HB 100/50/50 • ${enriched} matched+quoted • ${quoteRejected} liquidity rejects • ${historyFailed} history failures • ${candleShort} short histories • ${rulesMatched} rule matches • ${confirmedTop.size} score>=72 • ${liveExecutionRejected} execution rejects • ${probationBlocked} probation blocked • ${suspendedBlocked} suspended blocked • ${liveCapRejected} cap rejects • ${surviving.size} LIVE • ${newlyOpened.size} new [C ${challengerPublished} / A ${activePublished} / CH ${championPublished}] • challenger shadows +$challengerOpened • CHAMP ${champions} • SUSP ${suspended} • rejected+journal ${rejectedAdded}",
'''
s=replace_once(s,old,new,'summary line')
wr(p,s)
print('v1.5.6 full-universe patch applied')

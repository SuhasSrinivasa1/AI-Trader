#!/usr/bin/env python3
from pathlib import Path
import re,sys
root=Path(sys.argv[1]).resolve()
p=root/"app/src/main/java/com/suhas/ucsentinel/data/repository/UCSentinelRepository.kt"
s=p.read_text(encoding="utf-8")

def one(old,new,label):
    global s
    n=s.count(old)
    if n!=1: raise SystemExit(f"{label}: expected 1 found {n}")
    s=s.replace(old,new,1)

# v1.5 services + seeded prospective macro registry.
one(
'''    private val handbookSynergy=HandbookSynergyEngine()
    private val autopsyEngine=TradeAutopsyEngine()
''',
'''    private val handbookSynergy=HandbookSynergyEngine()
    private val evidenceFabric=EvidenceFabricEngine()
    private val industryClient=NiftyIndustryClient(context)
    private val autopsyEngine=TradeAutopsyEngine()
''',"services")
one(
'''    private val dualScanReuseMs=4L*60_000L

    fun credentials()''',
'''    private val dualScanReuseMs=4L*60_000L

    init {
        prefs.mergeMacroEvents(evidenceFabric.seededMacroEvents())
        DiagnosticLog.log(appContext,"BOOT","v1.5 evidence fabric • calendar="+NseTradingCalendar2026.VERSION+" • handbook="+HandbookSynergyEngine.VERSION)
    }

    fun credentials()''',"init")

# Expose new ledgers for UI / diagnostics.
one(
'''    fun tradeAutopsies():List<TradeAutopsyRecord> = prefs.loadAutopsies(800)
    fun openTradeCalls''',
'''    fun tradeAutopsies():List<TradeAutopsyRecord> = prefs.loadAutopsies(800)
    fun challengerShadows():List<ChallengerShadowRecord> = prefs.loadChallengerShadows(4000)
    fun brokerOrders():List<BrokerOrderRecord> = prefs.loadBrokerOrders(500)
    fun decisionSnapshots():List<DecisionSnapshot> = prefs.loadDecisionSnapshots(3000)
    fun pointInTimeEvidence():List<PointInTimeEvidence> = prefs.loadPointInTimeEvidence(5000)
    fun evidenceFabricSummary(now:ZonedDateTime=ZonedDateTime.now(ist)):EvidenceFabricSummary{
        val d=now.toLocalDate();val shadows=prefs.loadChallengerShadows(4000)
        val next7=now.plusDays(7).toInstant().toEpochMilli()
        return EvidenceFabricSummary(
            calendarVersion=NseTradingCalendar2026.VERSION,
            remainingWeekSessions=NseTradingCalendar2026.remainingSessionsInWeek(d),
            remainingMonthSessions=NseTradingCalendar2026.remainingSessionsInMonth(d),
            pointInTimeEvidenceCount=prefs.loadPointInTimeEvidence(5000).size,
            macroEventsNext7Days=prefs.loadMacroEvents(1000).count{it.endAt>=now.toInstant().toEpochMilli()&&it.startAt<=next7},
            challengerPending=shadows.count{it.outcome==ChallengerShadowOutcome.PENDING},
            challengerResolved=shadows.count{it.outcome!=ChallengerShadowOutcome.PENDING},
            brokerOrders=prefs.loadBrokerOrders(500).size,
            decisionSnapshots=prefs.loadDecisionSnapshots(3000).size,
            sectorMapVersion=prefs.sectorMapVersion()
        )
    }
    fun openTradeCalls''',"expose")

# Exact NSE calendar.
start=s.index("    fun marketSessionInfo(now:ZonedDateTime=ZonedDateTime.now(ist)):MarketSessionInfo{")
end=s.index("\n    suspend fun authenticate()",start)
s=s[:start]+'''    fun marketSessionInfo(now:ZonedDateTime=ZonedDateTime.now(ist)):MarketSessionInfo{
        val x=NseTradingCalendar2026.phase(now)
        val phase=when{
            !x.tradingDate->MarketPhase.WEEKEND
            x.open->MarketPhase.OPEN
            now.toLocalTime()<NseTradingCalendar2026.open->MarketPhase.PRE_OPEN
            else->MarketPhase.POST_CLOSE
        }
        return MarketSessionInfo(phase,x.tradingDate,x.open,x.label,x.sessionDate.toString())
    }
'''+s[end:]

# Manual live order: exact calendar, macro kill gate, deterministic reference id,
# pre-submit durable ledger, no POST retry, ambiguous-result reconciliation by reference id.
start=s.index("    suspend fun placeManualMarketOrder(")
end=s.index("\n    fun canAutoRenewGroww()",start)
s=s[:start]+'''    suspend fun placeManualMarketOrder(symbol:String,side:String,product:String,quantity:Int,signalEntryPrice:Double=0.0):String{
        val now=ZonedDateTime.now(ist)
        require(marketSessionInfo(now).isOpen){"Market is closed. Manual live orders are enabled only during the NSE regular 09:15–15:30 IST session."}
        require(!evidenceFabric.shouldHardWaitForMacro(now,prefs.loadMacroEvents(1000))){"WAIT / NO TRADE: macro hard-risk window is active."}
        require(quantity>0){"Quantity must be greater than zero"}
        val normalizedSide=side.trim().uppercase();val normalizedProduct=product.trim().uppercase();val normalizedSymbol=symbol.trim().uppercase()
        require((normalizedSide=="BUY"&&normalizedProduct=="CNC")||(normalizedSide=="SELL"&&normalizedProduct=="MIS")){"Order mapping rejected. LONG must be BUY/CNC; SHORT must be SELL/MIS."}

        val uncertain=prefs.loadBrokerOrders(500).firstOrNull{
            it.symbol==normalizedSymbol&&it.side==normalizedSide&&it.status=="SUBMIT_UNCERTAIN"&&System.currentTimeMillis()-it.submittedAt<30L*60_000L
        }
        require(uncertain==null){"A recent submission for $normalizedSymbol has an uncertain broker outcome. Run Broker Reconcile before trying again."}

        val actualIp=currentPublicIpv4()
        require(actualIp==EXPECTED_TRADING_STATIC_IP){"Static IP mismatch. Expected $EXPECTED_TRADING_STATIC_IP but current public IPv4 is $actualIp."}
        if(!accessTokenIsCurrent())require(ensureAutomationAuthentication()){"Groww authentication is required before placing an order."}
        val token=accessToken();require(token.isNotBlank()){"Groww access token is unavailable. Authenticate again."}

        val referenceId=("GE-"+System.currentTimeMillis()+"-"+normalizedSymbol.take(8)).take(60)
        val pending=BrokerOrderRecord(
            growwOrderId="PENDING-"+referenceId,referenceId=referenceId,symbol=normalizedSymbol,side=normalizedSide,product=normalizedProduct,
            requestedQuantity=quantity,submittedAt=System.currentTimeMillis(),signalEntryPrice=signalEntryPrice,status="SUBMITTING",remainingQuantity=quantity
        )
        prefs.upsertBrokerOrder(pending)
        DiagnosticLog.log(appContext,"ORDER-SUBMIT","manual confirmation • ref=$referenceId • $normalizedSide $normalizedSymbol • $normalizedProduct • qty=$quantity • signalEntry=$signalEntryPrice")
        try{
            val placed=groww.placeMarketOrder(token,normalizedSymbol,quantity,normalizedProduct,normalizedSide,referenceId)
            val accepted=BrokerOrderRecord(
                growwOrderId=placed.growwOrderId.ifBlank{"PENDING-"+referenceId},referenceId=placed.orderReferenceId.ifBlank{referenceId},
                symbol=normalizedSymbol,side=normalizedSide,product=normalizedProduct,requestedQuantity=quantity,submittedAt=pending.submittedAt,
                signalEntryPrice=signalEntryPrice,status=placed.orderStatus.ifBlank{"ACCEPTED"},remark=placed.remark,remainingQuantity=quantity
            )
            prefs.saveBrokerOrders(prefs.loadBrokerOrders(500).filterNot{it.referenceId==referenceId}+accepted)
            DiagnosticLog.log(appContext,"ORDER-SUBMIT","accepted • ref=$referenceId • growwId=${accepted.growwOrderId} • status=${accepted.status}")
            runCatching{reconcileBrokerOrders(accepted.growwOrderId)}
            val refreshed=prefs.loadBrokerOrders(500).firstOrNull{it.referenceId==referenceId}?:accepted
            return "Groww order ${refreshed.growwOrderId} • ${refreshed.status} • filled ${refreshed.filledQuantity}/${refreshed.requestedQuantity}"+if(refreshed.averageFillPrice>0)" • avg ₹${"%.2f".format(refreshed.averageFillPrice)}" else ""
        }catch(t:Throwable){
            val definite=t.message.orEmpty().contains(Regex("""Groww order failed \(4\d\d\)"""))||t.message.orEmpty().contains("order rejected",true)
            if(definite){
                prefs.saveBrokerOrders(prefs.loadBrokerOrders(500).filterNot{it.referenceId==referenceId}+pending.copy(status="REJECTED",reconciliationError=t.message.orEmpty()))
                DiagnosticLog.log(appContext,"ORDER-SUBMIT","definitive rejection • ref=$referenceId",t)
                throw t
            }
            val recovered=runCatching{groww.getOrderStatusByReference(token,referenceId)}.getOrNull()
            if(recovered!=null&&recovered.growwOrderId.isNotBlank()){
                val accepted=pending.copy(growwOrderId=recovered.growwOrderId,status=recovered.orderStatus.ifBlank{"ACCEPTED"},remark=recovered.remark,reconciliationError="")
                prefs.saveBrokerOrders(prefs.loadBrokerOrders(500).filterNot{it.referenceId==referenceId}+accepted)
                runCatching{reconcileBrokerOrders(accepted.growwOrderId)}
                DiagnosticLog.log(appContext,"ORDER-SUBMIT","recovered ambiguous submission by reference • ref=$referenceId • growwId=${accepted.growwOrderId}")
                return "Groww order ${accepted.growwOrderId} • recovered by reference • ${accepted.status}"
            }
            prefs.saveBrokerOrders(prefs.loadBrokerOrders(500).filterNot{it.referenceId==referenceId}+pending.copy(status="SUBMIT_UNCERTAIN",reconciliationError=t.message.orEmpty()))
            DiagnosticLog.log(appContext,"ORDER-SUBMIT","ambiguous result • ref=$referenceId • DO NOT RETRY until reconcile",t)
            throw IllegalStateException("Order submission outcome is uncertain. Do not press PLACE ORDER again yet; use Broker Reconcile. Reference: $referenceId")
        }
    }

    suspend fun reconcileBrokerOrders(onlyGrowwOrderId:String?=null):Int{
        if(!ensureAutomationAuthentication())return 0
        val token=accessToken();if(token.isBlank())return 0
        val all=prefs.loadBrokerOrders(500).toMutableList();if(all.isEmpty())return 0
        var changed=0
        val updated=all.map{record->
            if(onlyGrowwOrderId!=null&&record.growwOrderId!=onlyGrowwOrderId)return@map record
            if(record.status in setOf("COMPLETE","COMPLETED","CANCELLED","REJECTED")&&record.lastReconciledAt>0L&&System.currentTimeMillis()-record.lastReconciledAt<60L*60_000L)return@map record
            var base=record
            try{
                if(base.growwOrderId.startsWith("PENDING-")){
                    val byRef=groww.getOrderStatusByReference(token,base.referenceId)
                    if(byRef.growwOrderId.isNotBlank())base=base.copy(growwOrderId=byRef.growwOrderId,status=byRef.orderStatus,remark=byRef.remark)
                }
                if(base.growwOrderId.startsWith("PENDING-"))return@map base.copy(lastReconciledAt=System.currentTimeMillis(),reconciliationError="Broker order id still unavailable")
                val d=groww.getOrderDetail(token,base.growwOrderId)
                val fills=runCatching{groww.getOrderTrades(token,base.growwOrderId)}.getOrDefault(base.fills)
                changed++
                DiagnosticLog.log(appContext,"BROKER-RECON","${base.symbol} • ${base.growwOrderId} • status=${d.orderStatus} • fill=${d.filledQuantity}/${d.quantity} • avg=${d.averageFillPrice}")
                fills.forEach{f->DiagnosticLog.log(appContext,"FILL","order=${base.growwOrderId} • trade=${f.growwTradeId} • qty=${f.quantity} • price=${f.price} • ${f.tradeStatus}")}
                base.copy(
                    growwOrderId=d.growwOrderId,status=d.orderStatus,remark=d.remark,requestedQuantity=if(d.quantity>0)d.quantity else base.requestedQuantity,
                    filledQuantity=d.filledQuantity,remainingQuantity=d.remainingQuantity,averageFillPrice=d.averageFillPrice,lastReconciledAt=System.currentTimeMillis(),
                    fills=fills,reconciliationError=""
                )
            }catch(t:Throwable){
                DiagnosticLog.log(appContext,"BROKER-RECON","reconcile failed • ref=${base.referenceId}",t)
                base.copy(lastReconciledAt=System.currentTimeMillis(),reconciliationError=t.message.orEmpty().take(240))
            }
        }
        prefs.saveBrokerOrders(updated)
        return changed
    }
'''+s[end:]

# Prospective evidence capture from exchange news. We never backdate observedAt.
one(
'''    suspend fun refreshNews():List<NewsItem> = news.latest()
''',
'''    suspend fun refreshNews():List<NewsItem>{
        val items=news.latest();val observedAt=System.currentTimeMillis()
        items.forEach{n->
            val text=(n.title+" "+n.summary).lowercase()
            val kind=when{
                listOf("quarter","result","earnings","revenue","profit","eps","financial result").any{text.contains(it)}->EvidenceKind.FUNDAMENTAL
                listOf("analyst","rating","upgrade","downgrade","target price","revision").any{text.contains(it)}->EvidenceKind.ANALYST
                else->EvidenceKind.COMPANY_EVENT
            }
            val id=("NEWS|"+n.source+"|"+n.symbol+"|"+n.title).hashCode().toUInt().toString(16)
            prefs.appendPointInTimeEvidence(PointInTimeEvidence(
                id="PIT-"+id,symbol=n.symbol.uppercase(),kind=kind,metric=n.title.take(120),value=n.summary.take(600),source=n.source,
                sourceUrl=n.url,observedAt=observedAt,effectiveAt=observedAt,publishedAt=observedAt,revisionId=id,
                notes="Prospective capture; observed_at is never back-filled."
            ))
            if(n.symbol.isNotBlank()&&listOf("earnings","financial result","results","board meeting").any{text.contains(it)}){
                parseProspectiveEventDate(n.title+" "+n.summary,observedAt)?.let{date->
                    val z=date.atStartOfDay(ist).toInstant().toEpochMilli()
                    prefs.mergeMacroEvents(listOf(MacroEventRecord(
                        id="COMPANY-"+n.symbol.uppercase()+"-"+date,title=n.symbol.uppercase()+" earnings / results event",startAt=z,
                        endAt=date.atTime(23,59,59).atZone(ist).toInstant().toEpochMilli(),risk=EventRiskLevel.MEDIUM,source=n.source,sourceUrl=n.url,
                        symbol=n.symbol.uppercase(),observedAt=observedAt,prospective=true
                    )))
                }
            }
        }
        DiagnosticLog.log(appContext,"EVIDENCE","captured ${items.size} prospective exchange-news observations • PIT total=${prefs.loadPointInTimeEvidence(5000).size}")
        return items
    }

    private fun parseProspectiveEventDate(text:String,observedAt:Long):LocalDate?{
        val base=Instant.ofEpochMilli(observedAt).atZone(ist).toLocalDate()
        val iso=Regex("""\b(20\d{2})[-/](\d{1,2})[-/](\d{1,2})\b""").find(text)
        if(iso!=null){
            val d=runCatching{LocalDate.of(iso.groupValues[1].toInt(),iso.groupValues[2].toInt(),iso.groupValues[3].toInt())}.getOrNull()
            if(d!=null&&d>=base.minusDays(1)&&d<=base.plusDays(180))return d
        }
        val dmy=Regex("""\b(\d{1,2})[-/](\d{1,2})[-/](20\d{2})\b""").find(text)
        if(dmy!=null){
            val d=runCatching{LocalDate.of(dmy.groupValues[3].toInt(),dmy.groupValues[2].toInt(),dmy.groupValues[1].toInt())}.getOrNull()
            if(d!=null&&d>=base.minusDays(1)&&d<=base.plusDays(180))return d
        }
        return null
    }
''',"news")

# Exact next session.
start=s.index("    private fun nextTradingDate(from:LocalDate):LocalDate{")
end=s.index("\n    private fun targetSessionFor",start)
s=s[:start]+'''    private fun nextTradingDate(from:LocalDate):LocalDate=NseTradingCalendar2026.nextTradingDate(from)
'''+s[end:]
s=s.replace('''TradeCallBucket.NEXT_SESSION->if(d.dayOfWeek !in setOf(DayOfWeek.SATURDAY,DayOfWeek.SUNDAY)&&t<LocalTime.of(9,15))d else nextTradingDate(d)''',
            '''TradeCallBucket.NEXT_SESSION->if(NseTradingCalendar2026.isTradingDate(d)&&t<NseTradingCalendar2026.open)d else nextTradingDate(d)''')

# Rejected strategy candidates get immutable decision snapshots too.
needle='''        prefs.appendRejectedShadow(RejectedCandidateRecord(
            id="REJECT|STRATEGY|${s.direction.name}|${s.symbol}|$nowMs",engineLabel="STRATEGY",symbol=s.symbol,direction=s.direction,
            score=s.score,entryPrice=plan.entry,stopPrice=plan.stop,targetPrice=plan.target,capturedAt=nowMs,
            targetSessionDate=targetSessionFor(TradeCallBucket.LIVE,nowMs).toString(),
            reason=reason+" • STRAT="+s.strategyId+(if(s.researchSignature.isBlank())"" else " • SIG="+s.researchSignature.take(140))
        ))
'''
replacement=needle+'''        prefs.appendDecisionSnapshot(s,"WAIT",reason,NseTradingCalendar2026.VERSION,HandbookSynergyEngine.VERSION,at=nowMs)
        DiagnosticLog.log(appContext,"DECISION","WAIT • ${s.symbol} • ${s.strategyId} • $reason")
'''
# placeholder will be converted before script stored, so actual source already has dollar signs.
if needle not in s: raise SystemExit("rejected decision anchor not found")
s=s.replace(needle,replacement,1)

# Insert Challenger helpers before scanTradingStrategies.
scan_marker="    suspend fun scanTradingStrategies(progress:suspend(String)->Unit={}):StrategyTournamentSummary=strategyMutex.withLock{"
idx=s.index(scan_marker)
helpers='''    private fun openChallengerShadow(setup:StrategySetup,nowMs:Long=System.currentTimeMillis()):Boolean{
        val resolveAt=NseTradingCalendar2026.addTradingMinutes(nowMs,30)
        val sessionDate=Instant.ofEpochMilli(resolveAt).atZone(ist).toLocalDate().toString()
        val x=ChallengerShadowRecord(
            id="CHAL|${setup.strategyId}|${setup.direction.name}|${setup.symbol}|$nowMs",strategyId=setup.strategyId,strategyName=setup.strategyName,
            symbol=setup.symbol,direction=setup.direction,score=setup.score,entryPrice=setup.entryPrice,openedAt=nowMs,resolveAt=resolveAt,
            scheduledSessionDate=sessionDate,researchSignature=setup.researchSignature,evidence=setup.evidence
        )
        val added=prefs.appendChallengerShadow(x)
        if(added){
            prefs.appendDecisionSnapshot(setup,"CHALLENGER_SHADOW","Non-executable 30-trading-minute prospective shadow",NseTradingCalendar2026.VERSION,HandbookSynergyEngine.VERSION,at=nowMs)
            DiagnosticLog.log(appContext,"CHALLENGER","opened non-executable shadow • ${setup.symbol} • ${setup.strategyId} • resolve=${Instant.ofEpochMilli(resolveAt).atZone(ist)}")
        }
        return added
    }

    suspend fun resolveChallengerShadows():Int{
        val all=prefs.loadChallengerShadows(4000).toMutableList();val nowMs=System.currentTimeMillis()
        val due=all.filter{it.outcome==ChallengerShadowOutcome.PENDING&&nowMs>=it.resolveAt+5L*60_000L}
        if(due.isEmpty())return 0
        if(!ensureAutomationAuthentication())return 0
        val token=accessToken();if(token.isBlank())return 0
        var changed=0
        val updated=all.map{r->
            if(r !in due)return@map r
            val target=Instant.ofEpochMilli(r.resolveAt).atZone(ist)
            val from=target.minusMinutes(5).format(dateTimeFmt);val to=target.plusMinutes(15).format(dateTimeFmt)
            val candles=runCatching{groww.getHistoricalCandles(token,r.symbol,from,to,"5minute")}.getOrNull()
            val candle=candles?.sortedBy{it.epochSeconds}?.firstOrNull{it.epochSeconds*1000L>=r.resolveAt}
            if(candle==null){
                val age=nowMs-r.resolveAt
                if(age>24L*60*60_000L){
                    changed++;DiagnosticLog.log(appContext,"CHALLENGER-RESOLVE","UNRESOLVED_DATA • ${r.symbol} • scheduled=$target")
                    r.copy(outcome=ChallengerShadowOutcome.UNRESOLVED_DATA,resolvedAt=nowMs,note="No historical 5-minute bar at/after scheduled horizon; latest/current quote was intentionally not substituted.")
                }else r
            }else{
                val px=candle.close
                val ret=if(r.entryPrice<=0.0)0.0 else if(r.direction==TradeDirection.LONG)(px/r.entryPrice-1.0)*100.0 else (r.entryPrice/px-1.0)*100.0
                val out=if(ret>0.0)ChallengerShadowOutcome.WIN else ChallengerShadowOutcome.LOSS
                changed++;DiagnosticLog.log(appContext,"CHALLENGER-RESOLVE","$out • ${r.symbol} • ${r.strategyId} • horizon=${"%.2f".format(px)} • return=${"%+.2f".format(ret)}%")
                r.copy(outcome=out,resolvedAt=nowMs,horizonPrice=px,returnPct=ret,note="Resolved from first historical 5-minute bar at/after the frozen scheduled horizon.")
            }
        }
        if(changed>0)prefs.saveChallengerShadows(updated)
        return changed
    }

'''
s=s[:idx]+helpers+s[idx:]

# Strategy scan: capture the session OHLC map for industry breadth.
one(
'''        val movers=mutableListOf<Pair<Instrument,Double>>()
        cash.chunked(50).forEachIndexed{idx,batch->
            val map=runCatching{groww.getOhlcBatch(token,batch.map{it.tradingSymbol})}.getOrDefault(emptyMap())
''',
'''        val movers=mutableListOf<Pair<Instrument,Double>>()
        val sessionOhlc=linkedMapOf<String,Ohlc>()
        cash.chunked(50).forEachIndexed{idx,batch->
            val map=runCatching{groww.getOhlcBatch(token,batch.map{it.tradingSymbol})}.getOrDefault(emptyMap())
            sessionOhlc.putAll(map)
''',"ohlc map")

# Load sector map, macro registry and governance status before individual strategy evaluation.
one(
'''        val listingAge=newListingsCache.associate{it.symbol to it.daysListed}
        val now=ZonedDateTime.now(ist);val date=now.toLocalDate();val start=date.atTime(9,15).format(dateTimeFmt);val end=now.plusMinutes(1).format(dateTimeFmt)
''',
'''        val listingAge=newListingsCache.associate{it.symbol to it.daysListed}
        val industryBundle=withContext(Dispatchers.IO){runCatching{industryClient.load(false)}.getOrNull()}
        if(industryBundle!=null&&industryBundle.fetchedAt>0L)prefs.setSectorMapVersion(industryBundle.source+"@"+industryBundle.fetchedAt)
        val governance=prefs.strategyPerformances(bundle.strategies,settings).associateBy{it.strategyId}
        val macroEvents=prefs.loadMacroEvents(1000)
        val now=ZonedDateTime.now(ist);val date=now.toLocalDate();val start=date.atTime(9,15).format(dateTimeFmt);val end=now.plusMinutes(1).format(dateTimeFmt)
''',"sector setup")

# Inject sector/event intelligence after Handbook overlay creates 'setup', before hard gate checks.
anchor='''                val setup=baseSetup.copy(score=hb.adjustedScore,evidence=baseSetup.evidence+" • "+hb.evidence,researchSignature=hb.signature,
                    handbookQualityPct=hb.qualityPct,handbookPattern=hb.primaryPattern,handbookCombination=hb.combination)
                if(hb.hardFail){reject(setup,"HANDBOOK_HARD_GATE "+hb.failedHardFilters.joinToString(",").take(160));continue}
                if(setup.score<68.0){reject(setup,"RESEARCH_SCORE_FLOOR "+"%.1f".format(setup.score)+" < 68.0");continue}
                rawSetups+=setup to q
'''
replacement='''                var setup=baseSetup.copy(score=hb.adjustedScore,evidence=baseSetup.evidence+" • "+hb.evidence,researchSignature=hb.signature,
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
'''
one(anchor,replacement,"sector event overlay")

# Replace final opening block so challengers are strictly shadow-only.
start=s.index('''        val existingKeys=surviving.map{"${it.setup.symbol}|${it.setup.direction.name}"}''')
end=s.index("        prefs.saveStrategyLedger(surviving,closed)",start)
opening='''        val existingKeys=surviving.map{"${it.setup.symbol}|${it.setup.direction.name}"}.toMutableSet();val newlyOpened=mutableListOf<StrategySetup>()
        var challengerOpened=0
        if(now.toLocalTime()<LocalTime.of(15,10)){
            for((setup,q) in confirmedTop){
                val status=governance[setup.strategyId]?.status?:StrategyStatus.CHALLENGER
                if(status==StrategyStatus.CHALLENGER){
                    if(openChallengerShadow(setup))challengerOpened++
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
s=s[:start]+opening+s[end:]

# Add challenger count to summary message.
s=s.replace('''• ${surviving.size} LIVE • ${newlyOpened.size} new • CHAMP ${champions} • SUSP ${suspended} • rejected+journal ${rejectedAdded}"''',
            '''• ${surviving.size} LIVE • ${newlyOpened.size} new • challenger shadows +$challengerOpened • CHAMP ${champions} • SUSP ${suspended} • rejected+journal ${rejectedAdded}"''')

# Add v1.5 detail to reports.
weekly_anchor='''        appendLine("--- SHADOW STRATEGY LAB ---")
        prefs.shadowLearningSummary(30).forEach{appendLine(it)}
'''
weekly_repl=weekly_anchor+'''        appendLine("--- V1.5 CHALLENGER LANE ---")
        val ch=prefs.loadChallengerShadows(4000)
        appendLine("Challengers: total=${ch.size} pending=${ch.count{it.outcome==ChallengerShadowOutcome.PENDING}} win=${ch.count{it.outcome==ChallengerShadowOutcome.WIN}} loss=${ch.count{it.outcome==ChallengerShadowOutcome.LOSS}} unresolved=${ch.count{it.outcome==ChallengerShadowOutcome.UNRESOLVED_DATA}}")
        ch.take(40).forEach{appendLine(it.toString())}
        appendLine("--- POINT-IN-TIME EVIDENCE / DECISION AUDIT ---")
        appendLine("PIT evidence="+prefs.loadPointInTimeEvidence(5000).size+" • macro events="+prefs.loadMacroEvents(1000).size+" • decisions="+prefs.loadDecisionSnapshots(3000).size+" • sectorMap="+prefs.sectorMapVersion())
        prefs.loadDecisionSnapshots(50).forEach{appendLine(it.toString())}
        appendLine("--- BROKER RECONCILIATION ---")
        prefs.loadBrokerOrders(100).forEach{appendLine(it.toString())}
'''
one(weekly_anchor,weekly_repl,"weekly report")

eod_anchor='''        appendLine("--- NEW LISTINGS CACHE ("+newListingsCache.size+") ---")
        newListingsCache.forEach{appendLine(it.toString())}
'''
eod_repl='''        appendLine("--- V1.5 EVIDENCE FABRIC ---")
        appendLine("Calendar="+NseTradingCalendar2026.VERSION+" • handbook="+HandbookSynergyEngine.VERSION+" • sectorMap="+prefs.sectorMapVersion())
        appendLine("PIT evidence="+prefs.loadPointInTimeEvidence(5000).size+" • macroEvents="+prefs.loadMacroEvents(1000).size+" • decisions="+prefs.loadDecisionSnapshots(3000).size)
        prefs.loadDecisionSnapshots(200).forEach{appendLine(it.toString())}
        appendLine("--- CHALLENGER SHADOWS ("+prefs.loadChallengerShadows(4000).size+") ---")
        prefs.loadChallengerShadows(4000).forEach{appendLine(it.toString())}
        appendLine("--- BROKER ORDER/FILL RECONCILIATION ("+prefs.loadBrokerOrders(500).size+") ---")
        prefs.loadBrokerOrders(500).forEach{appendLine(it.toString())}
        appendLine("--- NEW LISTINGS CACHE ("+newListingsCache.size+") ---")
        newListingsCache.forEach{appendLine(it.toString())}
'''
one(eod_anchor,eod_repl,"eod report")

p.write_text(s,encoding="utf-8")
print("Global Edge v1.5 repository finalization applied")

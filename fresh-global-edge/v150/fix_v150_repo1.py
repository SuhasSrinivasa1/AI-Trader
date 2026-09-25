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

# Repository wiring.
p="app/src/main/java/com/suhas/ucsentinel/data/repository/UCSentinelRepository.kt";s=rw(p)

s=one(s,
'''    private val prefs=AppPreferences(context)
    private val groww=GrowwClient()
    private val news=ExchangeNewsClient()
''',
'''    private val prefs=AppPreferences(context)
    private val evidenceStore=EvidenceLedgerStore(context)
    private val groww=GrowwClient()
    private val news=ExchangeNewsClient()
    private val sectorClient=SectorIndustryClient(context)
''',"repository stores")

s=one(s,
'''    private val dualScanReuseMs=4L*60_000L
''',
'''    private val dualScanReuseMs=4L*60_000L
    private var lastEvidenceRefreshAt:Long=0L
    private var latestSectorContext:Map<String,SectorIntelligence> = emptyMap()
''',"repository state")

anchor='''    fun closedTradeCalls(engine:TradeCallEngine?=null):List<TradeCallRecord> = tradeCalls().filter{it.outcome!=TradeCallOutcome.OPEN&&(engine==null||it.engine==engine)}.sortedByDescending{it.closedAt}

'''
insert=anchor+r'''    fun challengerShadows():List<ChallengerShadowRecord> = evidenceStore.loadChallengers(3000)
    fun brokerOrders():List<BrokerOrderRecord> = evidenceStore.loadBrokerOrders(500)
    fun decisionSnapshots():List<DecisionSnapshot> = evidenceStore.loadDecisions(1500)
    fun evidenceRecords():List<PointInTimeEvidence> = evidenceStore.loadEvidence(5000)

    fun evidenceFabricSummary(now:ZonedDateTime=ZonedDateTime.now(ist)):EvidenceFabricSummary{
        val ev=evidenceStore.loadEvidence(5000)
        val shadows=evidenceStore.loadChallengers(3000)
        val broker=evidenceStore.loadBrokerOrders(500)
        val decisions=evidenceStore.loadDecisions(1500)
        val nextMacro=MacroEventRegistry.next(now.toLocalDate())
        val calendar=NseTradingCalendar2026.sessionLabel(now.toLocalDate())+
            " • week left "+NseTradingCalendar2026.remainingWeekSessions(now.toLocalDate())+
            " • month left "+NseTradingCalendar2026.remainingMonthSessions(now.toLocalDate())
        return EvidenceFabricSummary(
            generatedAt=System.currentTimeMillis(),
            pointInTimeEvidenceCount=ev.size,
            fundamentalCount=ev.count{it.type==EvidenceType.FUNDAMENTAL},
            analystCount=ev.count{it.type==EvidenceType.ANALYST_REVISION},
            earningsEventCount=ev.count{it.type==EvidenceType.EARNINGS_DATE},
            sectorMappedCount=latestSectorContext.size,
            challengerOpen=shadows.count{it.status==ChallengerShadowStatus.OPEN},
            challengerResolved=shadows.count{it.status!=ChallengerShadowStatus.OPEN},
            brokerOrders=broker.size,
            unreconciledBrokerOrders=broker.count{it.lastReconciledAt==0L||it.remainingQuantity>0},
            decisionSnapshots=decisions.size,
            calendarLabel=calendar,
            nextMacroEvent=nextMacro?.let{it.label+" • "+it.start}.orEmpty()
        )
    }

'''
s=one(s,anchor,insert,"repository evidence surface")

start=s.index("    fun marketSessionInfo(now:ZonedDateTime=ZonedDateTime.now(ist)):MarketSessionInfo{")
end=s.index("\n    suspend fun authenticate()",start)
market=r'''    fun marketSessionInfo(now:ZonedDateTime=ZonedDateTime.now(ist)):MarketSessionInfo{
        val date=now.toLocalDate()
        val tradingDay=NseTradingCalendar2026.isRegularSession(date)
        val time=now.toLocalTime()
        val phase=when{
            !tradingDay->MarketPhase.WEEKEND
            time<LocalTime.of(9,15)->MarketPhase.PRE_OPEN
            time<=LocalTime.of(15,30)->MarketPhase.OPEN
            else->MarketPhase.POST_CLOSE
        }
        val base=NseTradingCalendar2026.sessionLabel(date)
        val label=when(phase){
            MarketPhase.WEEKEND->base
            MarketPhase.PRE_OPEN->"Market closed • pre-open • $base"
            MarketPhase.OPEN->"NSE regular market window open"
            MarketPhase.POST_CLOSE->"Market closed • showing last valid regular-session data"
        }
        return MarketSessionInfo(phase,tradingDay,phase==MarketPhase.OPEN,label,date.toString())
    }
'''
s=s[:start]+market+s[end:]

start=s.index("    suspend fun placeManualMarketOrder(symbol:String,side:String,product:String,quantity:Int):String{")
end=s.index("\n    fun canAutoRenewGroww()",start)
order=r'''    suspend fun placeManualMarketOrder(symbol:String,side:String,product:String,quantity:Int):String{
        require(marketSessionInfo().isOpen){"Market is closed. Manual live orders are enabled only during a regular NSE 09:15–15:30 IST session."}
        require(quantity>0){"Quantity must be greater than zero"}
        val normalizedSymbol=symbol.trim().uppercase()
        val normalizedSide=side.trim().uppercase()
        val normalizedProduct=product.trim().uppercase()
        require((normalizedSide=="BUY"&&normalizedProduct=="CNC")||(normalizedSide=="SELL"&&normalizedProduct=="MIS")){
            "Order mapping rejected. LONG must be BUY/CNC; SHORT must be SELL/MIS."
        }
        val actualIp=currentPublicIpv4()
        require(actualIp==EXPECTED_TRADING_STATIC_IP){
            "Static IP mismatch. Expected $EXPECTED_TRADING_STATIC_IP but current public IPv4 is $actualIp."
        }
        if(!accessTokenIsCurrent())require(ensureAutomationAuthentication()){"Groww authentication is required before placing an order."}
        val token=accessToken();require(token.isNotBlank()){"Groww access token is unavailable. Authenticate again."}

        val q=groww.getQuote(token,normalizedSymbol)
        require(ExecutionQuality.executableQuote(q)){"Live quote is not executable. Order blocked by liquidity/spread gate."}
        require(if(normalizedSide=="BUY")ExecutionQuality.hasAsk(q) else ExecutionQuality.hasBid(q)){
            if(normalizedSide=="BUY")"No executable ask. Order blocked." else "No executable bid. Order blocked."
        }

        val recent=evidenceStore.loadBrokerOrders(200).firstOrNull{
            it.symbol==normalizedSymbol&&it.transactionType==normalizedSide&&it.product==normalizedProduct&&
                System.currentTimeMillis()-it.submittedAt<45_000L
        }
        require(recent==null){"Duplicate-order guard: a matching $normalizedSide $normalizedSymbol order was submitted within the last 45 seconds."}

        val submission=groww.placeMarketOrderDetailed(token,normalizedSymbol,quantity,normalizedProduct,normalizedSide)
        val record=BrokerOrderRecord(
            growwOrderId=submission.growwOrderId,
            orderReferenceId=submission.orderReferenceId,
            symbol=normalizedSymbol,
            transactionType=normalizedSide,
            product=normalizedProduct,
            requestedQuantity=quantity,
            submittedAt=System.currentTimeMillis(),
            orderStatus=submission.orderStatus,
            remark=submission.remark
        )
        evidenceStore.saveBrokerOrder(record)
        DiagnosticLog.log(appContext,"BROKER-SUBMIT","$normalizedSide $normalizedSymbol qty=$quantity product=$normalizedProduct order=${submission.growwOrderId} status=${submission.orderStatus}")
        runCatching{reconcileBrokerOrder(record.growwOrderId)}
        return "Groww order ${submission.growwOrderId} • ${submission.orderStatus}"+if(submission.remark.isBlank())"" else " • ${submission.remark}"
    }

    suspend fun reconcileBrokerOrder(growwOrderId:String):BrokerOrderRecord{
        require(ensureAutomationAuthentication()){"Groww authentication required for reconciliation"}
        val token=accessToken()
        val existing=evidenceStore.loadBrokerOrders(500).firstOrNull{it.growwOrderId==growwOrderId}
            ?:error("Broker order not found in local ledger")
        val detail=groww.getOrderDetail(token,growwOrderId)
        val fills=runCatching{groww.getOrderTrades(token,growwOrderId)}.getOrDefault(existing.fills)
        val updated=existing.copy(
            orderStatus=detail.orderStatus.ifBlank{existing.orderStatus},
            filledQuantity=detail.filledQuantity,
            remainingQuantity=detail.remainingQuantity,
            averageFillPrice=detail.averageFillPrice,
            remark=detail.remark.ifBlank{existing.remark},
            lastReconciledAt=System.currentTimeMillis(),
            fills=fills
        )
        evidenceStore.saveBrokerOrder(updated)
        DiagnosticLog.log(appContext,"BROKER-RECON","order=$growwOrderId status=${updated.orderStatus} filled=${updated.filledQuantity}/${updated.requestedQuantity} avg=${"%.2f".format(updated.averageFillPrice)} fills=${updated.fills.size}")
        return updated
    }

    suspend fun reconcileBrokerOrders():Int{
        if(!ensureAutomationAuthentication())return 0
        val rows=evidenceStore.loadBrokerOrders(100)
            .filter{System.currentTimeMillis()-it.submittedAt<7L*24*60*60*1000L}
            .take(30)
        var changed=0
        for(r in rows){
            runCatching{reconcileBrokerOrder(r.growwOrderId)}.onSuccess{changed++}
                .onFailure{DiagnosticLog.log(appContext,"BROKER-RECON","Failed ${r.growwOrderId}",it)}
        }
        return changed
    }
'''
s=s[:start]+order+s[end:]

old='''    suspend fun refreshNews():List<NewsItem> = news.latest()
'''
new=r'''    suspend fun refreshNews():List<NewsItem>{
        val items=news.latest()
        val before=evidenceStore.loadEvidence(5000).size
        evidenceStore.ingestExchangeNews(items)
        val after=evidenceStore.loadEvidence(5000).size
        lastEvidenceRefreshAt=System.currentTimeMillis()
        DiagnosticLog.log(appContext,"EVIDENCE","Exchange evidence refresh items=${items.size} new=${(after-before).coerceAtLeast(0)} total=$after")
        return items
    }

    private suspend fun refreshEvidenceFeedsIfDue(){
        if(System.currentTimeMillis()-lastEvidenceRefreshAt<30L*60_000L)return
        runCatching{refreshNews()}.onFailure{DiagnosticLog.log(appContext,"EVIDENCE","Prospective exchange evidence refresh failed",it)}
    }
'''
s=one(s,old,new,"refreshNews")

s=one(s,
'''        progress("Automation: refreshing new listings")
        runCatching{refreshNewListings()}
''',
'''        progress("Automation: refreshing new listings")
        runCatching{refreshNewListings()}
        progress("Automation: capturing point-in-time exchange evidence")
        runCatching{refreshNews()}
''',"bootstrap evidence")

anchor='''    private fun activeStrategyDefinitions(settings:AppSettings):Pair<StrategyCatalogClient.Bundle,List<TradingStrategyDefinition>>{
'''
helper=r'''    private fun effectiveStrategyPerformances(defs:List<TradingStrategyDefinition>,settings:AppSettings):List<StrategyPerformance>{
        return prefs.strategyPerformances(defs,settings).map{p->
            if(p.status!=StrategyStatus.CHALLENGER)return@map p
            val sh=evidenceStore.challengerStats(p.strategyId)
            if(sh.observations>=12&&sh.sessions>=4&&sh.winRatePct>=55.0&&sh.avgReturnPct>0.0){
                p.copy(status=StrategyStatus.ACTIVE)
            }else p
        }
    }

    private fun effectiveStrategyStatus(id:String,defs:List<TradingStrategyDefinition>,settings:AppSettings):StrategyStatus =
        effectiveStrategyPerformances(defs,settings).firstOrNull{it.strategyId==id}?.status?:StrategyStatus.CHALLENGER

'''+anchor
s=one(s,anchor,helper,"effective challenger lifecycle")
s=s.replace("val thisWeek=weekKey(today);val perfs=prefs.strategyPerformances(bundle.strategies,settings).associateBy{it.strategyId}",
            "val thisWeek=weekKey(today);val perfs=effectiveStrategyPerformances(bundle.strategies,settings).associateBy{it.strategyId}",1)

old='''    private fun nextTradingDate(from:LocalDate):LocalDate{
        var d=from.plusDays(1)
        while(d.dayOfWeek==DayOfWeek.SATURDAY||d.dayOfWeek==DayOfWeek.SUNDAY)d=d.plusDays(1)
        return d
    }
'''
new='''    private fun nextTradingDate(from:LocalDate):LocalDate=NseTradingCalendar2026.nextRegularSession(from)
'''
s=one(s,old,new,"nextTradingDate")
s=s.replace('TradeCallBucket.NEXT_SESSION->if(d.dayOfWeek !in setOf(DayOfWeek.SATURDAY,DayOfWeek.SUNDAY)&&t<LocalTime.of(9,15))d else nextTradingDate(d)',
            'TradeCallBucket.NEXT_SESSION->if(NseTradingCalendar2026.isRegularSession(d)&&t<LocalTime.of(9,15))d else nextTradingDate(d)',1)


wr(p,s)
print('v1.5 repository base integration applied')

#!/usr/bin/env python3
from pathlib import Path
import sys,re
root=Path(sys.argv[1]).resolve()
p=root/"app/src/main/java/com/suhas/ucsentinel/data/repository/UCSentinelRepository.kt"
s=p.read_text(encoding="utf-8")
def one(old,new,label):
    global s
    n=s.count(old)
    if n!=1: raise SystemExit(f"{label}: expected 1 found {n}")
    s=s.replace(old,new,1)

one('''    private val prefs=AppPreferences(context)
    private val groww=GrowwClient()
    private val news=ExchangeNewsClient()
''','''    private val prefs=AppPreferences(context)
    private val fabricStore=ResearchFabricStore(context)
    private val groww=GrowwClient()
    private val news=ExchangeNewsClient()
    private val sectorClient=SectorIntelligenceClient()
''',"fabric fields")

# Public accessors.
anchor='''    fun tradeCalls():List<TradeCallRecord> = prefs.loadTradeCalls(1500)
    fun tradeAutopsies():List<TradeAutopsyRecord> = prefs.loadAutopsies(800)
'''
insert='''    fun tradeCalls():List<TradeCallRecord> = prefs.loadTradeCalls(1500)
    fun tradeAutopsies():List<TradeAutopsyRecord> = prefs.loadAutopsies(800)
    fun evidenceFabricSummary():EvidenceFabricSummary = fabricStore.summary()
    fun pointInTimeEvidence():List<PointInTimeEvidence> = fabricStore.evidence(3000)
    fun challengerShadows():List<ChallengerShadowRecord> = fabricStore.challengerShadows(2500)
    fun brokerOrders():List<BrokerOrderRecord> = fabricStore.brokerOrders(500)
    fun brokerPortfolio():BrokerPortfolioSnapshot = fabricStore.portfolio()
    fun decisionSnapshots():List<DecisionSnapshot> = fabricStore.decisions(1500)
'''
one(anchor,insert,"public fabric accessors")

# Replace market session calendar.
start=s.index("    fun marketSessionInfo(now:ZonedDateTime=ZonedDateTime.now(ist)):MarketSessionInfo{")
end=s.index("\n    suspend fun authenticate()",start)
market=r'''    fun marketSessionInfo(now:ZonedDateTime=ZonedDateTime.now(ist)):MarketSessionInfo{
        val z=now.withZoneSameInstant(ist)
        val tradingDay=NseTradingCalendar.isRegularTradingDay(z.toLocalDate())
        val time=z.toLocalTime()
        val phase=when{
            !tradingDay->MarketPhase.WEEKEND
            time<NseTradingCalendar.regularOpen->MarketPhase.PRE_OPEN
            time<=NseTradingCalendar.regularClose->MarketPhase.OPEN
            else->MarketPhase.POST_CLOSE
        }
        val verified=if(NseTradingCalendar.calendarVerified(z.toLocalDate()))" • 2026 NSE calendar verified" else " • provisional calendar"
        val label=when(phase){
            MarketPhase.WEEKEND->"Market closed • NSE holiday/weekend"+verified
            MarketPhase.PRE_OPEN->"Market closed • pre-open"+verified
            MarketPhase.OPEN->"NSE regular session open"+verified
            MarketPhase.POST_CLOSE->"Market closed • showing last valid session data"+verified
        }
        return MarketSessionInfo(phase,tradingDay,phase==MarketPhase.OPEN,label,z.toLocalDate().toString())
    }
'''
s=s[:start]+market+s[end:]

# Replace manual placement with durable broker ledger + decision snapshot + duplicate guard.
start=s.index("    suspend fun placeManualMarketOrder(")
end=s.index("\n    fun canAutoRenewGroww()",start)
manual=r'''    suspend fun placeManualMarketOrder(symbol:String,side:String,product:String,quantity:Int,expectedEntryPrice:Double=0.0):String{
        require(marketSessionInfo().isOpen){"Market is closed. Manual live orders are enabled only during the verified NSE regular session."}
        require(quantity>0){"Quantity must be greater than zero"}
        val normalizedSide=side.trim().uppercase();val normalizedProduct=product.trim().uppercase();val normalizedSymbol=symbol.trim().uppercase()
        require((normalizedSide=="BUY"&&normalizedProduct=="CNC")||(normalizedSide=="SELL"&&normalizedProduct=="MIS")){
            "Order mapping rejected. LONG must be BUY/CNC; SHORT must be SELL/MIS."
        }
        val duplicate=fabricStore.brokerOrders(100).firstOrNull{
            it.symbol==normalizedSymbol&&it.side==normalizedSide&&
                it.syncState !in setOf(BrokerSyncState.REJECTED,BrokerSyncState.CANCELLED)&&
                System.currentTimeMillis()-it.placedAt<20_000L
        }
        require(duplicate==null){"Duplicate-order guard: a $normalizedSide $normalizedSymbol request was already submitted in the last 20 seconds."}
        val actualIp=currentPublicIpv4()
        require(actualIp==EXPECTED_TRADING_STATIC_IP){
            "Static IP mismatch. Expected $EXPECTED_TRADING_STATIC_IP but current public IPv4 is $actualIp."
        }
        if(!accessTokenIsCurrent())require(ensureAutomationAuthentication()){"Groww authentication is required before placing an order."}
        val token=accessToken();require(token.isNotBlank()){"Groww access token is unavailable. Authenticate again."}
        val order=groww.placeMarketOrderDetailed(token,normalizedSymbol,quantity,normalizedProduct,normalizedSide,expectedEntryPrice)
        fabricStore.saveBrokerOrder(order)
        saveDecision(normalizedSymbol,"BROKER","MANUAL",if(normalizedSide=="BUY")"LONG" else "SHORT",0.0,DecisionAction.MANUAL_ORDER,
            "User pressed PLACE ORDER • Groww order "+order.growwOrderId,listOf("STATIC_IP_MATCH","NSE_REGULAR_SESSION","EXPLICIT_USER_CONFIRMATION"))
        val reconciled=runCatching{reconcileBrokerOrder(order,token)}.getOrDefault(order)
        return "Groww order ${reconciled.growwOrderId} • ${reconciled.orderStatus} • filled ${reconciled.filledQty}/${reconciled.requestedQty}"+
            if(reconciled.averageFillPrice>0.0)" • avg ₹${"%.2f".format(reconciled.averageFillPrice)}" else ""
    }
'''
s=s[:start]+manual+s[end:]

# Refresh news becomes prospective evidence capture.
one('''    suspend fun refreshUniverse():Int=instruments.refresh().size
    suspend fun refreshNews():List<NewsItem> = news.latest()
''','''    suspend fun refreshUniverse():Int=instruments.refresh().size
    suspend fun refreshNews():List<NewsItem>{
        val items=news.latest()
        fabricStore.appendEvidence(EvidenceFabricEngine.classifyNews(items,System.currentTimeMillis()))
        return items
    }
''',"news evidence capture")

# Governance helper is inserted before activeStrategyDefinitions.
anchor="    private fun activeStrategyDefinitions(settings:AppSettings):Pair<StrategyCatalogClient.Bundle,List<TradingStrategyDefinition>>{"
idx=s.index(anchor)
helper=r'''    private fun governedStrategyPerformances(defs:List<TradingStrategyDefinition>,settings:AppSettings):List<StrategyPerformance>{
        val base=prefs.strategyPerformances(defs,settings)
        val shadows=fabricStore.challengerShadows(2500).filter{it.status==ChallengerShadowStatus.WIN||it.status==ChallengerShadowStatus.LOSS}
        return base.map{p->
            if(p.status!=StrategyStatus.CHALLENGER)return@map p
            val rows=shadows.filter{it.strategyId==p.strategyId}.sortedBy{it.resolvedAt}
            if(rows.isEmpty())return@map p
            val n=rows.size;val wins=rows.count{it.status==ChallengerShadowStatus.WIN};val acc=wins*100.0/n
            val avg=rows.map{it.returnPct}.average();val days=rows.map{it.sessionDate}.filter{it.isNotBlank()}.distinct().size
            val status=when{
                n>=12&&days>=4&&acc>=50.0&&avg>0.0->StrategyStatus.ACTIVE
                n>=12&&days>=4->StrategyStatus.PROBATION
                else->StrategyStatus.CHALLENGER
            }
            p.copy(observations=n,wins=wins,accuracyPct=acc,avgReturnPct=avg,expectancyPct=avg,status=status)
        }
    }

    private fun saveDecision(symbol:String,engine:String,strategyId:String,direction:String,score:Double,action:DecisionAction,reason:String,gates:List<String> = emptyList()){
        val now=System.currentTimeMillis()
        val evidence=fabricStore.evidenceAsOf(symbol,now)
        val sector=fabricStore.sectorState(symbol)
        val macro=EvidenceFabricEngine.activeMacroRisk(Instant.ofEpochMilli(now).atZone(ist).toLocalDate(),fabricStore.macroEvents())
        val parts=listOf(symbol,engine,strategyId,direction,"%.4f".format(score),action.name,reason,now.toString(),NseTradingCalendar.VERSION,
            strategyCatalogVersion(),HandbookSynergyEngine.VERSION,sector?.sourceVersion.orEmpty(),evidence.joinToString(","){it.id},macro.joinToString(","){it.id},gates.joinToString(","))
        val hash=EvidenceFabricEngine.decisionHash(parts)
        fabricStore.saveDecision(DecisionSnapshot(
            id="DEC-"+hash.take(20),decisionHash=hash,symbol=symbol,engine=engine,strategyId=strategyId,direction=direction,score=score,action=action,reason=reason,
            decisionAt=now,marketDataAt=now,calendarVersion=NseTradingCalendar.VERSION,strategyCatalogVersion=strategyCatalogVersion(),handbookVersion=HandbookSynergyEngine.VERSION,
            sectorEvidence=sector?.let{it.industry+" • breadth "+"%.0f".format(it.peerBreadthPct)+"% • RS "+"%+.2f".format(it.relativeStrengthPct)+"%"}.orEmpty(),
            pointInTimeEvidenceIds=evidence.take(20).map{it.id},eventRisk=macro.joinToString(" • "){it.title+" "+it.severity},gates=gates
        ))
    }

    private fun recordChallengerShadow(setup:StrategySetup,now:ZonedDateTime){
        val horizonMinutes=30
        val horizon=NseTradingCalendar.scheduledHorizon(now,horizonMinutes)
        val id="CHAL|${setup.strategyId}|${setup.direction.name}|${setup.symbol}|${now.toInstant().toEpochMilli()}"
        fabricStore.appendChallengerShadow(ChallengerShadowRecord(
            id=id,strategyId=setup.strategyId,strategyName=setup.strategyName,symbol=setup.symbol,direction=setup.direction,score=setup.score,entryPrice=setup.entryPrice,
            capturedAt=now.toInstant().toEpochMilli(),scheduledHorizonAt=horizon.toInstant().toEpochMilli(),horizonMinutes=horizonMinutes,
            researchSignature=setup.researchSignature,evidence=setup.evidence,sessionDate=horizon.toLocalDate().toString()
        ))
        saveDecision(setup.symbol,"STRATEGY",setup.strategyId,setup.direction.name,setup.score,DecisionAction.CHALLENGER_SHADOW,
            "Challenger is research-only until prospective shadow promotion",listOf("NON_EXECUTABLE_CHALLENGER","SCHEDULED_HORIZON_30M"))
    }

    suspend fun resolveChallengerShadows(force:Boolean=false):Int{
        val all=fabricStore.challengerShadows(2500).toMutableList()
        val due=all.filter{it.status==ChallengerShadowStatus.OPEN&&(force||System.currentTimeMillis()>=it.scheduledHorizonAt)}
        if(due.isEmpty())return 0
        if(!ensureAutomationAuthentication())return 0
        val token=accessToken();var changed=0
        val updated=all.map{r->
            if(r !in due)return@map r
            val h=Instant.ofEpochMilli(r.scheduledHorizonAt).atZone(ist)
            val from=h.minusMinutes(5).format(dateTimeFmt);val to=h.plusMinutes(15).format(dateTimeFmt)
            val candles=runCatching{groww.getHistoricalCandles(token,r.symbol,from,to,"5minute")}.getOrNull()
            val bar=candles?.sortedBy{it.epochSeconds}?.firstOrNull{it.epochSeconds*1000L>=r.scheduledHorizonAt}
            if(bar==null){
                val sessionClosed=ZonedDateTime.now(ist).isAfter(NseTradingCalendar.sessionClose(h.toLocalDate()).plusMinutes(20))
                if(sessionClosed){changed++;r.copy(status=ChallengerShadowStatus.UNRESOLVED_DATA,resolvedAt=System.currentTimeMillis())}else r
            }else{
                val px=bar.close
                val ret=if(r.entryPrice<=0.0||px<=0.0)0.0 else if(r.direction==TradeDirection.LONG)(px/r.entryPrice-1.0)*100.0 else (r.entryPrice/px-1.0)*100.0
                changed++
                r.copy(status=if(ret>0.0)ChallengerShadowStatus.WIN else ChallengerShadowStatus.LOSS,resolvedAt=System.currentTimeMillis(),horizonPrice=px,returnPct=ret)
            }
        }
        if(changed>0)fabricStore.saveChallengerShadows(updated)
        return changed
    }

    private suspend fun reconcileBrokerOrder(order:BrokerOrderRecord,token:String):BrokerOrderRecord{
        val detail=groww.getOrderDetail(token,order)
        val fills=runCatching{groww.getTradesForOrder(token,detail.growwOrderId)}.getOrDefault(detail.fills)
        val filledFromTrades=fills.sumOf{it.quantity}
        val avgFromTrades=if(filledFromTrades>0)fills.sumOf{it.price*it.quantity}/filledFromTrades else detail.averageFillPrice
        val merged=detail.copy(
            fills=fills,
            filledQty=maxOf(detail.filledQty,filledFromTrades),
            remainingQty=(detail.requestedQty-maxOf(detail.filledQty,filledFromTrades)).coerceAtLeast(0),
            averageFillPrice=if(avgFromTrades>0.0)avgFromTrades else detail.averageFillPrice,
            syncState=when{
                detail.syncState in setOf(BrokerSyncState.REJECTED,BrokerSyncState.CANCELLED)->detail.syncState
                maxOf(detail.filledQty,filledFromTrades)>=detail.requestedQty->BrokerSyncState.COMPLETE
                maxOf(detail.filledQty,filledFromTrades)>0->BrokerSyncState.PARTIAL
                else->detail.syncState
            }
        )
        fabricStore.saveBrokerOrder(merged);return merged
    }

    suspend fun reconcileBrokerOrders():Int{
        if(!ensureAutomationAuthentication())return 0
        val token=accessToken();var changed=0
        val recentCutoff=System.currentTimeMillis()-7L*24*60*60*1000
        for(order in fabricStore.brokerOrders(200).filter{it.placedAt>=recentCutoff}){
            runCatching{reconcileBrokerOrder(order,token)}.onSuccess{changed++}.onFailure{t->
                fabricStore.saveBrokerOrder(order.copy(lastReconciledAt=System.currentTimeMillis(),syncState=BrokerSyncState.ERROR,lastError=t.message.orEmpty().take(180)))
            }
        }
        return changed
    }

    suspend fun refreshBrokerPortfolio():BrokerPortfolioSnapshot{
        if(!ensureAutomationAuthentication())return fabricStore.portfolio()
        val token=accessToken()
        val holdings=groww.getHoldings(token);val positions=groww.getCashPositions(token)
        val symbols=(holdings.map{it.symbol}+positions.map{it.symbol}).filter{it.isNotBlank()}.distinct()
        val prices=mutableMapOf<String,Double>()
        symbols.chunked(50).forEach{batch->
            runCatching{groww.getOhlcBatch(token,batch)}.getOrDefault(emptyMap()).forEach{(sym,o)->prices[sym]=o.close}
        }
        val hh=holdings.map{h->val px=prices[h.symbol]?:0.0;h.copy(lastPrice=px,currentValue=if(px>0.0)px*h.quantity else 0.0)}
        val pp=positions.map{pos->val px=prices[pos.symbol]?:0.0;val unreal=if(px>0.0&&pos.averagePrice>0.0)(px-pos.averagePrice)*pos.netQuantity else 0.0;pos.copy(lastPrice=px,pnl=pos.pnl+unreal)}
        val snap=BrokerPortfolioSnapshot(System.currentTimeMillis(),hh,pp,"Groww holdings ${hh.size} • positions ${pp.size}")
        fabricStore.savePortfolio(snap);return snap
    }

'''
s=s[:idx]+helper+s[idx:]

# governed performance in activeStrategyDefinitions.
one("val thisWeek=weekKey(today);val perfs=prefs.strategyPerformances(bundle.strategies,settings).associateBy{it.strategyId}",
    "val thisWeek=weekKey(today);val perfs=governedStrategyPerformances(bundle.strategies,settings).associateBy{it.strategyId}","governed active perfs")

# NSE calendar next trading date.
old='''    private fun nextTradingDate(from:LocalDate):LocalDate{
        var d=from.plusDays(1)
        while(d.dayOfWeek==DayOfWeek.SATURDAY||d.dayOfWeek==DayOfWeek.SUNDAY)d=d.plusDays(1)
        return d
    }
'''
one(old,'''    private fun nextTradingDate(from:LocalDate):LocalDate=NseTradingCalendar.nextTradingDay(from)
''',"next trading calendar")

# Rejected/published decision snapshots.
old='''        prefs.appendRejectedShadow(RejectedCandidateRecord(
            id="REJECT|${engine.name}|${bucket.name}|${c.symbol}|$nowMs",engineLabel=engine.name,symbol=c.symbol,direction=TradeDirection.LONG,
            score=c.score,entryPrice=plan.entry,stopPrice=plan.stop,targetPrice=plan.target,capturedAt=nowMs,
            targetSessionDate=targetSessionFor(bucket,nowMs).toString(),reason=reason
        ))
    }
'''
new=old.replace("        ))\n    }\n","        ))\n        saveDecision(c.symbol,engine.name,\"\",TradeDirection.LONG.name,c.score,DecisionAction.WAIT,reason,listOf(\"REJECTED_CANDIDATE_GATE\"))\n    }\n")
one(old,new,"candidate reject decision")

# Strategy reject decision.
needle='''        prefs.appendRejectedShadow(RejectedCandidateRecord(
            id="REJECT|STRATEGY|${s.direction.name}|${s.symbol}|$nowMs",engineLabel="STRATEGY",symbol=s.symbol,direction=s.direction,
            score=s.score,entryPrice=plan.entry,stopPrice=plan.stop,targetPrice=plan.target,capturedAt=nowMs,
            targetSessionDate=targetSessionFor(TradeCallBucket.LIVE,nowMs).toString(),
            reason=reason+" • STRAT="+s.strategyId+(if(s.researchSignature.isBlank())"" else " • SIG="+s.researchSignature.take(140))
        ))
    }
'''
replacement=needle.replace("        ))\n    }\n","        ))\n        saveDecision(s.symbol,\"STRATEGY\",s.strategyId,s.direction.name,s.score,DecisionAction.WAIT,reason,listOf(\"STRATEGY_GATE\"))\n    }\n")
one(needle,replacement,"strategy reject decision")

# Global reject decision.
old='''        prefs.appendRejectedShadow(RejectedCandidateRecord(
            id="REJECT|GLOBAL|${direction.name}|${c.indianSymbol}|$nowMs",engineLabel=TradeCallEngine.GLOBAL.name,symbol=c.indianSymbol,direction=direction,
            score=c.score,entryPrice=plan.entry,stopPrice=plan.stop,targetPrice=plan.target,capturedAt=nowMs,
            targetSessionDate=targetSessionFor(bucket,nowMs).toString(),reason=reason
        ))
    }
'''
new=old.replace("        ))\n    }\n","        ))\n        saveDecision(c.indianSymbol,TradeCallEngine.GLOBAL.name,\"\",direction.name,c.score,DecisionAction.WAIT,reason,listOf(\"GLOBAL_CONFIRMATION_GATE\"))\n    }\n")
one(old,new,"global reject decision")

# Add decisions to published UC calls.
needle='''            ledger+=TradeCallRecord(id,engine,bucket,c.symbol,c.companyName,TradeDirection.LONG,c.score,plan.entry,plan.stop,plan.target,plan.target2,nowMs,targetSessionFor(bucket,nowMs).toString(),source,detail)
            added++
'''
replacement='''            ledger+=TradeCallRecord(id,engine,bucket,c.symbol,c.companyName,TradeDirection.LONG,c.score,plan.entry,plan.stop,plan.target,plan.target2,nowMs,targetSessionFor(bucket,nowMs).toString(),source,detail)
            saveDecision(c.symbol,engine.name,"",TradeDirection.LONG.name,c.score,DecisionAction.LIVE,source,listOf("PUBLISHED_CALL"))
            added++
'''
one(needle,replacement,"candidate live decision")

needle='''            ledger+=TradeCallRecord(id,TradeCallEngine.GLOBAL,bucket,c.indianSymbol,c.indianCompany,direction,c.score,plan.entry,plan.stop,plan.target,plan.target2,nowMs,targetSessionFor(bucket,nowMs).toString(),"Global ${bucket.name}",detail,globalLearningKey(c))
            added++
'''
replacement='''            ledger+=TradeCallRecord(id,TradeCallEngine.GLOBAL,bucket,c.indianSymbol,c.indianCompany,direction,c.score,plan.entry,plan.stop,plan.target,plan.target2,nowMs,targetSessionFor(bucket,nowMs).toString(),"Global ${bucket.name}",detail,globalLearningKey(c))
            saveDecision(c.indianSymbol,TradeCallEngine.GLOBAL.name,"",direction.name,c.score,DecisionAction.LIVE,"Global "+bucket.name,listOf("PUBLISHED_GLOBAL_CALL"))
            added++
'''
one(needle,replacement,"global live decision")

# Add broker + challenger reconciliation to autonomous learning.
needle='''            runCatching{reconcileRejectedShadows()}.onFailure{DiagnosticLog.log(appContext,"LEARNING15M","Rejected-candidate shadow reconciliation failed",it)}
            runCatching{runLearningCycle()}.onFailure{DiagnosticLog.log(appContext,"LEARNING15M","Outcome evaluation failed",it)}
'''
replacement='''            runCatching{reconcileRejectedShadows()}.onFailure{DiagnosticLog.log(appContext,"LEARNING15M","Rejected-candidate shadow reconciliation failed",it)}
            runCatching{resolveChallengerShadows(false)}.onFailure{DiagnosticLog.log(appContext,"LEARNING15M","Challenger horizon reconciliation failed",it)}
            runCatching{reconcileBrokerOrders()}.onFailure{DiagnosticLog.log(appContext,"LEARNING15M","Groww order reconciliation failed",it)}
            runCatching{refreshBrokerPortfolio()}.onFailure{DiagnosticLog.log(appContext,"LEARNING15M","Groww portfolio refresh failed",it)}
            runCatching{runLearningCycle()}.onFailure{DiagnosticLog.log(appContext,"LEARNING15M","Outcome evaluation failed",it)}
'''
one(needle,replacement,"autonomous fabric reconciliation")

p.write_text(s,encoding="utf-8")
print("Repository foundation for v1.5.0 applied")

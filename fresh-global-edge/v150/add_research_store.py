#!/usr/bin/env python3
from pathlib import Path
import sys
root=Path(sys.argv[1]).resolve()
p=root/"app/src/main/java/com/suhas/ucsentinel/data/local/ResearchFabricStore.kt"
p.parent.mkdir(parents=True,exist_ok=True)
p.write_text(r'''package com.suhas.globaledgeai.data.local

import android.content.Context
import com.suhas.globaledgeai.domain.engine.EvidenceFabricEngine
import com.suhas.globaledgeai.domain.engine.NseTradingCalendar
import com.suhas.globaledgeai.domain.model.*
import org.json.JSONArray
import org.json.JSONObject
import java.time.LocalDate
import java.time.ZoneId

class ResearchFabricStore(context:Context){
    private val prefs=context.getSharedPreferences("global_edge_ai_prefs",Context.MODE_PRIVATE)
    private val ist=ZoneId.of("Asia/Kolkata")
    private fun finite(v:Double)=if(v.isFinite())v else 0.0

    init{
        if(!prefs.getBoolean("macro_registry_v150_seeded",false)){
            saveMacroEvents(EvidenceFabricEngine.seedMacroEvents())
            prefs.edit().putBoolean("macro_registry_v150_seeded",true).apply()
        }
    }

    private fun evidenceToJson(x:PointInTimeEvidence)=JSONObject()
        .put("id",x.id).put("symbol",x.symbol).put("kind",x.kind.name).put("label",x.label).put("detail",x.detail)
        .put("observedAt",x.observedAt).put("effectiveAt",x.effectiveAt).put("source",x.source).put("sourceUrl",x.sourceUrl)
        .put("revisionId",x.revisionId).put("scoreImpact",finite(x.scoreImpact))
    private fun evidenceFromJson(j:JSONObject)=PointInTimeEvidence(
        j.optString("id"),j.optString("symbol"),runCatching{EvidenceKind.valueOf(j.optString("kind"))}.getOrDefault(EvidenceKind.NEWS),
        j.optString("label"),j.optString("detail"),j.optLong("observedAt"),j.optLong("effectiveAt"),j.optString("source"),j.optString("sourceUrl"),
        j.optString("revisionId"),j.optDouble("scoreImpact")
    )
    fun evidence(limit:Int=3000):List<PointInTimeEvidence>{
        val a=runCatching{JSONArray(prefs.getString("point_in_time_evidence_v150","[]")?:"[]")}.getOrElse{JSONArray()}
        return buildList{for(i in 0 until a.length()){val j=a.optJSONObject(i)?:continue;add(evidenceFromJson(j))}}.sortedByDescending{it.observedAt}.take(limit)
    }
    fun appendEvidence(items:List<PointInTimeEvidence>){
        if(items.isEmpty())return
        val all=(evidence(3000)+items).distinctBy{it.id}.sortedByDescending{it.observedAt}.take(3000)
        val a=JSONArray();all.forEach{a.put(evidenceToJson(it))}
        prefs.edit().putString("point_in_time_evidence_v150",a.toString()).apply()
    }
    fun evidenceAsOf(symbol:String,timestamp:Long):List<PointInTimeEvidence> =
        evidence(3000).filter{(it.symbol.isBlank()||it.symbol.equals(symbol,true))&&it.observedAt<=timestamp&&it.effectiveAt<=timestamp}

    private fun macroToJson(x:MacroRiskEvent)=JSONObject().put("id",x.id).put("title",x.title).put("startDateIso",x.startDateIso).put("endDateIso",x.endDateIso)
        .put("severity",x.severity).put("source",x.source).put("sourceUrl",x.sourceUrl).put("observedAt",x.observedAt)
    private fun macroFromJson(j:JSONObject)=MacroRiskEvent(j.optString("id"),j.optString("title"),j.optString("startDateIso"),j.optString("endDateIso"),j.optString("severity"),j.optString("source"),j.optString("sourceUrl"),j.optLong("observedAt"))
    fun macroEvents():List<MacroRiskEvent>{
        val a=runCatching{JSONArray(prefs.getString("macro_events_v150","[]")?:"[]")}.getOrElse{JSONArray()}
        return buildList{for(i in 0 until a.length()){val j=a.optJSONObject(i)?:continue;add(macroFromJson(j))}}.sortedBy{it.startDateIso}
    }
    fun saveMacroEvents(items:List<MacroRiskEvent>){
        val a=JSONArray();items.distinctBy{it.id}.forEach{a.put(macroToJson(it))}
        prefs.edit().putString("macro_events_v150",a.toString()).apply()
    }

    private fun sectorToJson(x:SectorPeerState)=JSONObject().put("symbol",x.symbol).put("industry",x.industry).put("peerCount",x.peerCount)
        .put("positivePeers",x.positivePeers).put("negativePeers",x.negativePeers).put("peerBreadthPct",finite(x.peerBreadthPct))
        .put("peerAverageReturnPct",finite(x.peerAverageReturnPct)).put("stockReturnPct",finite(x.stockReturnPct)).put("relativeStrengthPct",finite(x.relativeStrengthPct))
        .put("participationAligned",x.participationAligned).put("sourceVersion",x.sourceVersion).put("observedAt",x.observedAt)
    private fun sectorFromJson(j:JSONObject)=SectorPeerState(j.optString("symbol"),j.optString("industry"),j.optInt("peerCount"),j.optInt("positivePeers"),j.optInt("negativePeers"),
        j.optDouble("peerBreadthPct"),j.optDouble("peerAverageReturnPct"),j.optDouble("stockReturnPct"),j.optDouble("relativeStrengthPct"),j.optBoolean("participationAligned"),j.optString("sourceVersion"),j.optLong("observedAt"))
    fun saveSectorState(x:SectorPeerState){
        val root=runCatching{JSONObject(prefs.getString("sector_state_v150","{}")?:"{}")}.getOrElse{JSONObject()}
        root.put(x.symbol,sectorToJson(x));prefs.edit().putString("sector_state_v150",root.toString()).apply()
    }
    fun sectorState(symbol:String):SectorPeerState?{
        val root=runCatching{JSONObject(prefs.getString("sector_state_v150","{}")?:"{}")}.getOrElse{JSONObject()}
        return root.optJSONObject(symbol.uppercase())?.let(::sectorFromJson)
    }
    fun sectorStates():List<SectorPeerState>{
        val root=runCatching{JSONObject(prefs.getString("sector_state_v150","{}")?:"{}")}.getOrElse{JSONObject()}
        return buildList{val it=root.keys();while(it.hasNext()){val k=it.next();root.optJSONObject(k)?.let{j->add(sectorFromJson(j))}}}.sortedByDescending{it.observedAt}
    }

    private fun shadowToJson(x:ChallengerShadowRecord)=JSONObject().put("id",x.id).put("strategyId",x.strategyId).put("strategyName",x.strategyName).put("symbol",x.symbol)
        .put("direction",x.direction.name).put("score",finite(x.score)).put("entryPrice",finite(x.entryPrice)).put("capturedAt",x.capturedAt)
        .put("scheduledHorizonAt",x.scheduledHorizonAt).put("horizonMinutes",x.horizonMinutes).put("researchSignature",x.researchSignature)
        .put("evidence",x.evidence).put("status",x.status.name).put("resolvedAt",x.resolvedAt).put("horizonPrice",finite(x.horizonPrice))
        .put("returnPct",finite(x.returnPct)).put("sessionDate",x.sessionDate)
    private fun shadowFromJson(j:JSONObject)=ChallengerShadowRecord(j.optString("id"),j.optString("strategyId"),j.optString("strategyName"),j.optString("symbol"),
        runCatching{TradeDirection.valueOf(j.optString("direction"))}.getOrDefault(TradeDirection.LONG),j.optDouble("score"),j.optDouble("entryPrice"),
        j.optLong("capturedAt"),j.optLong("scheduledHorizonAt"),j.optInt("horizonMinutes",30),j.optString("researchSignature"),j.optString("evidence"),
        runCatching{ChallengerShadowStatus.valueOf(j.optString("status"))}.getOrDefault(ChallengerShadowStatus.OPEN),j.optLong("resolvedAt"),j.optDouble("horizonPrice"),j.optDouble("returnPct"),j.optString("sessionDate"))
    fun challengerShadows(limit:Int=2500):List<ChallengerShadowRecord>{
        val a=runCatching{JSONArray(prefs.getString("challenger_shadows_v150","[]")?:"[]")}.getOrElse{JSONArray()}
        return buildList{for(i in 0 until a.length()){val j=a.optJSONObject(i)?:continue;add(shadowFromJson(j))}}.sortedByDescending{it.capturedAt}.take(limit)
    }
    fun saveChallengerShadows(items:List<ChallengerShadowRecord>){
        val a=JSONArray();items.distinctBy{it.id}.sortedByDescending{it.capturedAt}.take(2500).forEach{a.put(shadowToJson(it))}
        prefs.edit().putString("challenger_shadows_v150",a.toString()).apply()
    }
    fun appendChallengerShadow(x:ChallengerShadowRecord){
        val all=challengerShadows(2500).toMutableList()
        val duplicate=all.any{it.status==ChallengerShadowStatus.OPEN&&it.strategyId==x.strategyId&&it.symbol==x.symbol&&it.direction==x.direction&&kotlin.math.abs(x.capturedAt-it.capturedAt)<20L*60_000L}
        if(!duplicate){all+=x;saveChallengerShadows(all)}
    }

    private fun fillToJson(x:BrokerFill)=JSONObject().put("growwTradeId",x.growwTradeId).put("exchangeTradeId",x.exchangeTradeId).put("exchangeOrderId",x.exchangeOrderId)
        .put("quantity",x.quantity).put("price",finite(x.price)).put("tradeStatus",x.tradeStatus).put("tradeDateTime",x.tradeDateTime).put("settlementNumber",x.settlementNumber)
    private fun fillFromJson(j:JSONObject)=BrokerFill(j.optString("growwTradeId"),j.optString("exchangeTradeId"),j.optString("exchangeOrderId"),j.optInt("quantity"),j.optDouble("price"),j.optString("tradeStatus"),j.optString("tradeDateTime"),j.optString("settlementNumber"))
    private fun orderToJson(x:BrokerOrderRecord):JSONObject{
        val fills=JSONArray();x.fills.forEach{fills.put(fillToJson(it))}
        return JSONObject().put("localId",x.localId).put("growwOrderId",x.growwOrderId).put("orderReferenceId",x.orderReferenceId).put("symbol",x.symbol)
            .put("side",x.side).put("product",x.product).put("requestedQty",x.requestedQty).put("expectedEntryPrice",finite(x.expectedEntryPrice))
            .put("orderStatus",x.orderStatus).put("filledQty",x.filledQty).put("remainingQty",x.remainingQty).put("averageFillPrice",finite(x.averageFillPrice))
            .put("placedAt",x.placedAt).put("lastReconciledAt",x.lastReconciledAt).put("fills",fills).put("syncState",x.syncState.name).put("remark",x.remark).put("lastError",x.lastError)
    }
    private fun orderFromJson(j:JSONObject):BrokerOrderRecord{
        val a=j.optJSONArray("fills")?:JSONArray();val fills=buildList{for(i in 0 until a.length()){val x=a.optJSONObject(i)?:continue;add(fillFromJson(x))}}
        return BrokerOrderRecord(j.optString("localId"),j.optString("growwOrderId"),j.optString("orderReferenceId"),j.optString("symbol"),j.optString("side"),j.optString("product"),
            j.optInt("requestedQty"),j.optDouble("expectedEntryPrice"),j.optString("orderStatus"),j.optInt("filledQty"),j.optInt("remainingQty"),j.optDouble("averageFillPrice"),
            j.optLong("placedAt"),j.optLong("lastReconciledAt"),fills,runCatching{BrokerSyncState.valueOf(j.optString("syncState"))}.getOrDefault(BrokerSyncState.NEW),j.optString("remark"),j.optString("lastError"))
    }
    fun brokerOrders(limit:Int=500):List<BrokerOrderRecord>{
        val a=runCatching{JSONArray(prefs.getString("broker_orders_v150","[]")?:"[]")}.getOrElse{JSONArray()}
        return buildList{for(i in 0 until a.length()){val j=a.optJSONObject(i)?:continue;add(orderFromJson(j))}}.sortedByDescending{it.placedAt}.take(limit)
    }
    fun saveBrokerOrder(x:BrokerOrderRecord){
        val all=brokerOrders(500).filterNot{it.localId==x.localId||it.growwOrderId.isNotBlank()&&it.growwOrderId==x.growwOrderId}.toMutableList();all+=x
        val a=JSONArray();all.sortedByDescending{it.placedAt}.take(500).forEach{a.put(orderToJson(it))}
        prefs.edit().putString("broker_orders_v150",a.toString()).apply()
    }

    private fun holdingToJson(x:BrokerHolding)=JSONObject().put("symbol",x.symbol).put("quantity",x.quantity).put("averagePrice",finite(x.averagePrice)).put("lastPrice",finite(x.lastPrice)).put("investedValue",finite(x.investedValue)).put("currentValue",finite(x.currentValue))
    private fun holdingFromJson(j:JSONObject)=BrokerHolding(j.optString("symbol"),j.optInt("quantity"),j.optDouble("averagePrice"),j.optDouble("lastPrice"),j.optDouble("investedValue"),j.optDouble("currentValue"))
    private fun positionToJson(x:BrokerPosition)=JSONObject().put("symbol",x.symbol).put("product",x.product).put("netQuantity",x.netQuantity).put("averagePrice",finite(x.averagePrice)).put("lastPrice",finite(x.lastPrice)).put("pnl",finite(x.pnl))
    private fun positionFromJson(j:JSONObject)=BrokerPosition(j.optString("symbol"),j.optString("product"),j.optInt("netQuantity"),j.optDouble("averagePrice"),j.optDouble("lastPrice"),j.optDouble("pnl"))
    fun savePortfolio(x:BrokerPortfolioSnapshot){
        val h=JSONArray();x.holdings.forEach{h.put(holdingToJson(it))};val p=JSONArray();x.positions.forEach{p.put(positionToJson(it))}
        prefs.edit().putString("broker_portfolio_v150",JSONObject().put("capturedAt",x.capturedAt).put("message",x.message).put("holdings",h).put("positions",p).toString()).apply()
    }
    fun portfolio():BrokerPortfolioSnapshot{
        val j=runCatching{JSONObject(prefs.getString("broker_portfolio_v150","{}")?:"{}")}.getOrElse{JSONObject()}
        val ha=j.optJSONArray("holdings")?:JSONArray();val pa=j.optJSONArray("positions")?:JSONArray()
        val holdings=buildList{for(i in 0 until ha.length()){val x=ha.optJSONObject(i)?:continue;add(holdingFromJson(x))}}
        val positions=buildList{for(i in 0 until pa.length()){val x=pa.optJSONObject(i)?:continue;add(positionFromJson(x))}}
        return BrokerPortfolioSnapshot(j.optLong("capturedAt"),holdings,positions,j.optString("message"))
    }

    private fun decisionToJson(x:DecisionSnapshot):JSONObject{
        val ev=JSONArray();x.pointInTimeEvidenceIds.forEach{ev.put(it)};val gates=JSONArray();x.gates.forEach{gates.put(it)}
        return JSONObject().put("id",x.id).put("decisionHash",x.decisionHash).put("symbol",x.symbol).put("engine",x.engine).put("strategyId",x.strategyId)
            .put("direction",x.direction).put("score",finite(x.score)).put("action",x.action.name).put("reason",x.reason).put("decisionAt",x.decisionAt)
            .put("marketDataAt",x.marketDataAt).put("calendarVersion",x.calendarVersion).put("strategyCatalogVersion",x.strategyCatalogVersion).put("handbookVersion",x.handbookVersion)
            .put("sectorEvidence",x.sectorEvidence).put("pointInTimeEvidenceIds",ev).put("eventRisk",x.eventRisk).put("gates",gates)
    }
    private fun decisionFromJson(j:JSONObject):DecisionSnapshot{
        val e=j.optJSONArray("pointInTimeEvidenceIds")?:JSONArray();val g=j.optJSONArray("gates")?:JSONArray()
        val ev=buildList{for(i in 0 until e.length())add(e.optString(i))};val gates=buildList{for(i in 0 until g.length())add(g.optString(i))}
        return DecisionSnapshot(j.optString("id"),j.optString("decisionHash"),j.optString("symbol"),j.optString("engine"),j.optString("strategyId"),j.optString("direction"),j.optDouble("score"),
            runCatching{DecisionAction.valueOf(j.optString("action"))}.getOrDefault(DecisionAction.WAIT),j.optString("reason"),j.optLong("decisionAt"),j.optLong("marketDataAt"),
            j.optString("calendarVersion"),j.optString("strategyCatalogVersion"),j.optString("handbookVersion"),j.optString("sectorEvidence"),ev,j.optString("eventRisk"),gates)
    }
    fun decisions(limit:Int=1500):List<DecisionSnapshot>{
        val a=runCatching{JSONArray(prefs.getString("decision_snapshots_v150","[]")?:"[]")}.getOrElse{JSONArray()}
        return buildList{for(i in 0 until a.length()){val j=a.optJSONObject(i)?:continue;add(decisionFromJson(j))}}.sortedByDescending{it.decisionAt}.take(limit)
    }
    fun saveDecision(x:DecisionSnapshot){
        val all=(decisions(1500)+x).distinctBy{it.id}.sortedByDescending{it.decisionAt}.take(1500)
        val a=JSONArray();all.forEach{a.put(decisionToJson(it))}
        prefs.edit().putString("decision_snapshots_v150",a.toString()).apply()
    }

    fun summary(now:Long=System.currentTimeMillis()):EvidenceFabricSummary{
        val today=java.time.Instant.ofEpochMilli(now).atZone(ist).toLocalDate()
        val ev=evidence(3000);val sh=challengerShadows(2500);val orders=brokerOrders(500)
        return EvidenceFabricSummary(
            generatedAt=now,calendarVersion=NseTradingCalendar.VERSION,
            weekSessionsRemaining=NseTradingCalendar.sessionsRemainingInWeek(today,true),
            monthSessionsRemaining=NseTradingCalendar.sessionsRemainingInMonth(today,true),
            macroRisk=EvidenceFabricEngine.activeMacroRisk(today,macroEvents()),
            evidenceCount=ev.size,
            fundamentalCount=ev.count{it.kind==EvidenceKind.FUNDAMENTAL},
            analystCount=ev.count{it.kind==EvidenceKind.ANALYST_RATING},
            earningsEventCount=ev.count{it.kind==EvidenceKind.EARNINGS_EVENT},
            challengerOpen=sh.count{it.status==ChallengerShadowStatus.OPEN},
            challengerResolved=sh.count{it.status==ChallengerShadowStatus.WIN||it.status==ChallengerShadowStatus.LOSS},
            brokerOrders=orders.size,
            brokerOrdersPending=orders.count{it.syncState in setOf(BrokerSyncState.NEW,BrokerSyncState.PARTIAL,BrokerSyncState.ERROR)},
            latestDecisions=decisions(30)
        )
    }
}
''',encoding="utf-8")
print("ResearchFabricStore.kt created")

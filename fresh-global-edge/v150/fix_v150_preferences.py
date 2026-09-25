#!/usr/bin/env python3
from pathlib import Path
import re,sys
root=Path(sys.argv[1]).resolve()
p=root/"app/src/main/java/com/suhas/ucsentinel/data/local/AppPreferences.kt"
s=p.read_text(encoding="utf-8")
if "import java.security.MessageDigest" not in s:
    s=s.replace("import java.time.ZoneId\n","import java.time.ZoneId\nimport java.security.MessageDigest\n")

# Replace strategyPerformances with Challenger shadow-gated promotion while preserving
# Champion's stricter live/holdout/walk-forward requirements.
start=s.index("    fun strategyPerformances(defs:List<TradingStrategyDefinition>,settings:AppSettings):List<StrategyPerformance>{")
end=s.index("\n    private fun strategyWalkForwardStable",start)
new=r'''    fun strategyPerformances(defs:List<TradingStrategyDefinition>,settings:AppSettings):List<StrategyPerformance>{
        val legacy=runCatching{JSONObject(prefs.getString("strategy_stats","{}")?:"{}")}.getOrElse{JSONObject()}
        val durable=loadStrategyClosed(2000).filter{it.status==StrategyRecommendationStatus.WIN||it.status==StrategyRecommendationStatus.LOSS}.sortedBy{it.closedAt}
        val shadowAll=loadChallengerShadows(4000).filter{it.outcome==ChallengerShadowOutcome.WIN||it.outcome==ChallengerShadowOutcome.LOSS}.sortedBy{it.resolvedAt}
        fun winRate(rows:List<StrategyRecommendation>)=if(rows.isEmpty())0.0 else rows.count{it.status==StrategyRecommendationStatus.WIN}*100.0/rows.size
        fun avgReturn(rows:List<StrategyRecommendation>)=if(rows.isEmpty())0.0 else rows.map{finite(it.returnPct)}.average()
        fun maxDrawdown(rows:List<StrategyRecommendation>):Double{
            var equity=0.0;var peak=0.0;var trough=0.0
            rows.forEach{equity+=finite(it.returnPct);peak=maxOf(peak,equity);trough=minOf(trough,equity-peak)}
            return kotlin.math.abs(trough)
        }
        return defs.map{d->
            val rows=durable.filter{it.setup.strategyId==d.id}
            val shadow=shadowAll.filter{it.strategyId==d.id}
            val shadowN=shadow.size;val shadowWins=shadow.count{it.outcome==ChallengerShadowOutcome.WIN}
            val shadowAcc=if(shadowN==0)0.0 else shadowWins*100.0/shadowN
            val shadowAvg=if(shadowN==0)0.0 else shadow.map{finite(it.returnPct)}.average()
            val shadowDays=shadow.map{it.scheduledSessionDate}.filter{it.isNotBlank()}.distinct().size
            val shadowHoldoutSize=if(shadowN<4)0 else kotlin.math.ceil(shadowN*0.25).toInt().coerceAtLeast(3).coerceAtMost(shadowN)
            val shadowHoldout=if(shadowHoldoutSize>0)shadow.takeLast(shadowHoldoutSize) else emptyList()
            val shadowHoldoutAcc=if(shadowHoldout.isEmpty())0.0 else shadowHoldout.count{it.outcome==ChallengerShadowOutcome.WIN}*100.0/shadowHoldout.size
            val shadowHoldoutAvg=if(shadowHoldout.isEmpty())0.0 else shadowHoldout.map{finite(it.returnPct)}.average()
            val shadowAdjusted=shadowAcc-multipleTestingPenaltyPct(shadowN)
            val shadowQualified=shadowN>=12&&shadowDays>=4&&shadowAvg>0.0&&shadowAcc>=55.0&&shadowHoldout.size>=3&&shadowHoldoutAcc>=50.0&&shadowHoldoutAvg>0.0&&shadowAdjusted>=48.0

            val x=legacy.optJSONObject(d.id)?:JSONObject()
            val liveN=if(rows.isNotEmpty())rows.size else x.optInt("observations").coerceAtLeast(0)
            val liveW=if(rows.isNotEmpty())rows.count{it.status==StrategyRecommendationStatus.WIN} else x.optInt("wins").coerceIn(0,liveN)
            val liveAcc=if(liveN==0)0.0 else liveW*100.0/liveN
            val liveAvg=if(rows.isNotEmpty())avgReturn(rows) else if(liveN==0)0.0 else finite(storedFinite(x,"sumReturn")/liveN)
            val floor=wilsonLower(liveW,liveN)*100.0
            val maxDd=if(rows.isNotEmpty())maxDrawdown(rows) else kotlin.math.abs(storedFinite(x,"maxDrawdown"))
            val holdoutSize=if(rows.isEmpty())0 else kotlin.math.ceil(rows.size*0.20).toInt().coerceAtLeast(4).coerceAtMost(rows.size)
            val holdout=if(holdoutSize>0)rows.takeLast(holdoutSize) else emptyList()
            val holdoutAcc=winRate(holdout);val holdoutAvg=avgReturn(holdout)
            val wfStable=rows.size>=18&&strategyWalkForwardStable(rows)
            val adjustedAcc=(liveAcc-multipleTestingPenaltyPct(liveN)).coerceAtLeast(0.0)
            val recent=rows.takeLast(minOf(10,rows.size));val baseline=rows.dropLast(recent.size).takeLast(20)
            val recentAcc=winRate(recent);val recentAvg=avgReturn(recent);val baseAcc=winRate(baseline)
            val decayed=recent.size>=8&&((recentAvg<=0.0&&recentAcc<40.0)||(baseline.size>=8&&baseAcc-recentAcc>=25.0&&recentAvg<0.0))
            val status=when{
                decayed->StrategyStatus.SUSPENDED
                liveN>=settings.strategyMinChampionSamples.coerceAtLeast(30)&&liveAcc>=settings.strategyMinChampionAccuracy&&liveAvg>0.0&&floor>=50.0&&
                    holdout.size>=6&&holdoutAcc>=50.0&&holdoutAvg>0.0&&wfStable&&adjustedAcc>=55.0->StrategyStatus.CHAMPION
                liveN>=18&&!wfStable->StrategyStatus.PROBATION
                liveN>=10&&liveAvg<=0.0->StrategyStatus.PROBATION
                liveN>=5->StrategyStatus.ACTIVE
                shadowN>=12&&!shadowQualified->StrategyStatus.PROBATION
                shadowQualified->StrategyStatus.ACTIVE
                else->StrategyStatus.CHALLENGER
            }
            val totalN=liveN+shadowN
            val totalW=liveW+shadowWins
            val totalAcc=if(totalN==0)0.0 else totalW*100.0/totalN
            val totalAvg=if(totalN==0)0.0 else ((liveAvg*liveN)+(shadowAvg*shadowN))/totalN
            StrategyPerformance(d.id,d.name,totalN,totalW,finite(totalAcc),finite(totalAvg),finite(totalAvg),finite(maxDd),finite(floor),status)
        }.sortedWith(compareBy<StrategyPerformance>{it.status.ordinal}.thenByDescending{it.expectancyPct}.thenByDescending{it.accuracyPct})
    }
'''
s=s[:start]+new+s[end:]

# Insert v1.5 ledgers before final helper functions.
marker="    private fun scanToJson(s:ScanSummary):JSONObject"
idx=s.index(marker)
block=r'''
    // ---------- v1.5 point-in-time evidence / events / Challenger / broker / audit ledgers ----------

    private fun evidenceToJson(x:PointInTimeEvidence)=JSONObject()
        .put("id",x.id).put("symbol",x.symbol).put("kind",x.kind.name).put("metric",x.metric).put("value",x.value)
        .put("source",x.source).put("sourceUrl",x.sourceUrl).put("observedAt",x.observedAt).put("effectiveAt",x.effectiveAt)
        .put("publishedAt",x.publishedAt).put("revisionId",x.revisionId).put("notes",x.notes)
    private fun evidenceFromJson(j:JSONObject)=PointInTimeEvidence(
        j.optString("id"),j.optString("symbol"),runCatching{EvidenceKind.valueOf(j.optString("kind"))}.getOrDefault(EvidenceKind.COMPANY_EVENT),
        j.optString("metric"),j.optString("value"),j.optString("source"),j.optString("sourceUrl"),j.optLong("observedAt"),
        j.optLong("effectiveAt"),j.optLong("publishedAt"),j.optString("revisionId"),j.optString("notes")
    )
    fun loadPointInTimeEvidence(limit:Int=5000):List<PointInTimeEvidence>{
        val a=runCatching{JSONArray(prefs.getString("pit_evidence_v150","[]")?:"[]")}.getOrElse{JSONArray()}
        return buildList{for(i in 0 until a.length())runCatching{add(evidenceFromJson(a.getJSONObject(i)))}}
            .sortedByDescending{it.observedAt}.take(limit)
    }
    fun appendPointInTimeEvidence(x:PointInTimeEvidence){
        val all=loadPointInTimeEvidence(5000).filterNot{it.id==x.id}.toMutableList();all+=x
        val a=JSONArray();all.sortedByDescending{it.observedAt}.take(5000).forEach{a.put(evidenceToJson(it))}
        prefs.edit().putString("pit_evidence_v150",a.toString()).apply()
    }
    fun pointInTimeEvidenceAsOf(symbol:String,asOf:Long):List<PointInTimeEvidence> =
        loadPointInTimeEvidence(5000).filter{it.symbol.equals(symbol,true)&&it.observedAt<=asOf&&it.effectiveAt<=asOf}

    private fun macroToJson(x:MacroEventRecord)=JSONObject().put("id",x.id).put("title",x.title).put("startAt",x.startAt).put("endAt",x.endAt)
        .put("risk",x.risk.name).put("source",x.source).put("sourceUrl",x.sourceUrl).put("symbol",x.symbol).put("observedAt",x.observedAt).put("prospective",x.prospective)
    private fun macroFromJson(j:JSONObject)=MacroEventRecord(j.optString("id"),j.optString("title"),j.optLong("startAt"),j.optLong("endAt"),
        runCatching{EventRiskLevel.valueOf(j.optString("risk"))}.getOrDefault(EventRiskLevel.MEDIUM),j.optString("source"),j.optString("sourceUrl"),
        j.optString("symbol"),j.optLong("observedAt"),j.optBoolean("prospective",true))
    fun loadMacroEvents(limit:Int=1000):List<MacroEventRecord>{
        val a=runCatching{JSONArray(prefs.getString("macro_events_v150","[]")?:"[]")}.getOrElse{JSONArray()}
        return buildList{for(i in 0 until a.length())runCatching{add(macroFromJson(a.getJSONObject(i)))}}
            .sortedBy{it.startAt}.take(limit)
    }
    fun mergeMacroEvents(items:List<MacroEventRecord>){
        val all=(loadMacroEvents(1000)+items).associateBy{it.id}.values.sortedBy{it.startAt}.takeLast(1000)
        val a=JSONArray();all.forEach{a.put(macroToJson(it))}
        prefs.edit().putString("macro_events_v150",a.toString()).apply()
    }

    private fun challengerToJson(x:ChallengerShadowRecord)=JSONObject().put("id",x.id).put("strategyId",x.strategyId).put("strategyName",x.strategyName)
        .put("symbol",x.symbol).put("direction",x.direction.name).put("score",finite(x.score)).put("entryPrice",finite(x.entryPrice))
        .put("openedAt",x.openedAt).put("resolveAt",x.resolveAt).put("scheduledSessionDate",x.scheduledSessionDate)
        .put("researchSignature",x.researchSignature).put("evidence",x.evidence).put("outcome",x.outcome.name).put("resolvedAt",x.resolvedAt)
        .put("horizonPrice",finite(x.horizonPrice)).put("returnPct",finite(x.returnPct)).put("note",x.note)
    private fun challengerFromJson(j:JSONObject)=ChallengerShadowRecord(j.optString("id"),j.optString("strategyId"),j.optString("strategyName"),j.optString("symbol"),
        runCatching{TradeDirection.valueOf(j.optString("direction"))}.getOrDefault(TradeDirection.LONG),j.optDouble("score"),j.optDouble("entryPrice"),
        j.optLong("openedAt"),j.optLong("resolveAt"),j.optString("scheduledSessionDate"),j.optString("researchSignature"),j.optString("evidence"),
        runCatching{ChallengerShadowOutcome.valueOf(j.optString("outcome"))}.getOrDefault(ChallengerShadowOutcome.PENDING),
        j.optLong("resolvedAt"),j.optDouble("horizonPrice"),j.optDouble("returnPct"),j.optString("note"))
    fun loadChallengerShadows(limit:Int=4000):List<ChallengerShadowRecord>{
        val a=runCatching{JSONArray(prefs.getString("challenger_shadow_v150","[]")?:"[]")}.getOrElse{JSONArray()}
        return buildList{for(i in 0 until a.length())runCatching{add(challengerFromJson(a.getJSONObject(i)))}}
            .sortedByDescending{it.openedAt}.take(limit)
    }
    fun saveChallengerShadows(records:List<ChallengerShadowRecord>){
        val a=JSONArray();records.distinctBy{it.id}.sortedByDescending{it.openedAt}.take(4000).forEach{a.put(challengerToJson(it))}
        prefs.edit().putString("challenger_shadow_v150",a.toString()).apply()
    }
    fun appendChallengerShadow(x:ChallengerShadowRecord):Boolean{
        val all=loadChallengerShadows(4000).toMutableList()
        val dup=all.any{it.outcome==ChallengerShadowOutcome.PENDING&&it.strategyId==x.strategyId&&it.symbol==x.symbol&&it.direction==x.direction&&kotlin.math.abs(it.openedAt-x.openedAt)<30L*60_000L}
        if(dup)return false
        all+=x;saveChallengerShadows(all);return true
    }

    private fun fillToJson(x:BrokerFillRecord)=JSONObject().put("growwTradeId",x.growwTradeId).put("exchangeTradeId",x.exchangeTradeId).put("exchangeOrderId",x.exchangeOrderId)
        .put("quantity",x.quantity).put("price",finite(x.price)).put("tradeStatus",x.tradeStatus).put("tradeDateTime",x.tradeDateTime).put("remark",x.remark)
    private fun fillFromJson(j:JSONObject)=BrokerFillRecord(j.optString("growwTradeId"),j.optString("exchangeTradeId"),j.optString("exchangeOrderId"),j.optInt("quantity"),
        j.optDouble("price"),j.optString("tradeStatus"),j.optString("tradeDateTime"),j.optString("remark"))
    private fun brokerToJson(x:BrokerOrderRecord):JSONObject{
        val f=JSONArray();x.fills.forEach{f.put(fillToJson(it))}
        return JSONObject().put("growwOrderId",x.growwOrderId).put("referenceId",x.referenceId).put("symbol",x.symbol).put("side",x.side).put("product",x.product)
            .put("requestedQuantity",x.requestedQuantity).put("submittedAt",x.submittedAt).put("signalEntryPrice",finite(x.signalEntryPrice)).put("status",x.status)
            .put("remark",x.remark).put("filledQuantity",x.filledQuantity).put("remainingQuantity",x.remainingQuantity).put("averageFillPrice",finite(x.averageFillPrice))
            .put("lastReconciledAt",x.lastReconciledAt).put("fills",f).put("reconciliationError",x.reconciliationError)
    }
    private fun brokerFromJson(j:JSONObject):BrokerOrderRecord{
        val a=j.optJSONArray("fills")?:JSONArray();val fills=buildList{for(i in 0 until a.length())runCatching{add(fillFromJson(a.getJSONObject(i)))}}
        return BrokerOrderRecord(j.optString("growwOrderId"),j.optString("referenceId"),j.optString("symbol"),j.optString("side"),j.optString("product"),
            j.optInt("requestedQuantity"),j.optLong("submittedAt"),j.optDouble("signalEntryPrice"),j.optString("status","SUBMITTED"),j.optString("remark"),
            j.optInt("filledQuantity"),j.optInt("remainingQuantity"),j.optDouble("averageFillPrice"),j.optLong("lastReconciledAt"),fills,j.optString("reconciliationError"))
    }
    fun loadBrokerOrders(limit:Int=500):List<BrokerOrderRecord>{
        val a=runCatching{JSONArray(prefs.getString("broker_orders_v150","[]")?:"[]")}.getOrElse{JSONArray()}
        return buildList{for(i in 0 until a.length())runCatching{add(brokerFromJson(a.getJSONObject(i)))}}
            .sortedByDescending{it.submittedAt}.take(limit)
    }
    fun saveBrokerOrders(records:List<BrokerOrderRecord>){
        val a=JSONArray();records.distinctBy{it.growwOrderId}.sortedByDescending{it.submittedAt}.take(500).forEach{a.put(brokerToJson(it))}
        prefs.edit().putString("broker_orders_v150",a.toString()).apply()
    }
    fun upsertBrokerOrder(x:BrokerOrderRecord){
        val all=loadBrokerOrders(500).filterNot{it.growwOrderId==x.growwOrderId}.toMutableList();all+=x;saveBrokerOrders(all)
    }

    private fun decisionToJson(x:DecisionSnapshot)=JSONObject().put("id",x.id).put("hash",x.hash).put("symbol",x.symbol).put("direction",x.direction.name)
        .put("strategyId",x.strategyId).put("decision",x.decision).put("reason",x.reason).put("score",finite(x.score)).put("decisionAt",x.decisionAt)
        .put("calendarVersion",x.calendarVersion).put("handbookVersion",x.handbookVersion).put("researchSignature",x.researchSignature)
        .put("evidence",x.evidence).put("pointInTimeEvidenceCount",x.pointInTimeEvidenceCount).put("sectorIndustry",x.sectorIndustry).put("macroRisk",x.macroRisk)
    private fun decisionFromJson(j:JSONObject)=DecisionSnapshot(j.optString("id"),j.optString("hash"),j.optString("symbol"),
        runCatching{TradeDirection.valueOf(j.optString("direction"))}.getOrDefault(TradeDirection.LONG),j.optString("strategyId"),j.optString("decision"),
        j.optString("reason"),j.optDouble("score"),j.optLong("decisionAt"),j.optString("calendarVersion"),j.optString("handbookVersion"),j.optString("researchSignature"),
        j.optString("evidence"),j.optInt("pointInTimeEvidenceCount"),j.optString("sectorIndustry"),j.optString("macroRisk"))
    fun loadDecisionSnapshots(limit:Int=3000):List<DecisionSnapshot>{
        val a=runCatching{JSONArray(prefs.getString("decision_snapshots_v150","[]")?:"[]")}.getOrElse{JSONArray()}
        return buildList{for(i in 0 until a.length())runCatching{add(decisionFromJson(a.getJSONObject(i)))}}
            .sortedByDescending{it.decisionAt}.take(limit)
    }
    fun appendDecisionSnapshot(setup:StrategySetup,decision:String,reason:String,calendarVersion:String,handbookVersion:String,sectorIndustry:String="",macroRisk:String="NONE",at:Long=System.currentTimeMillis()):DecisionSnapshot{
        val evidenceCount=pointInTimeEvidenceAsOf(setup.symbol,at).size
        val raw=listOf(setup.symbol,setup.direction.name,setup.strategyId,decision,reason,setup.score.toString(),at.toString(),calendarVersion,handbookVersion,setup.researchSignature,setup.evidence,evidenceCount.toString(),sectorIndustry,macroRisk).joinToString("|")
        val hash=MessageDigest.getInstance("SHA-256").digest(raw.toByteArray(Charsets.UTF_8)).joinToString(""){"%02x".format(it)}
        val x=DecisionSnapshot("DEC-"+hash.take(20),hash,setup.symbol,setup.direction,setup.strategyId,decision,reason,setup.score,at,calendarVersion,handbookVersion,setup.researchSignature,setup.evidence,evidenceCount,sectorIndustry,macroRisk)
        val all=loadDecisionSnapshots(3000).filterNot{it.id==x.id}.toMutableList();all+=x
        val a=JSONArray();all.sortedByDescending{it.decisionAt}.take(3000).forEach{a.put(decisionToJson(it))}
        prefs.edit().putString("decision_snapshots_v150",a.toString()).apply()
        return x
    }

    fun sectorMapVersion():String=prefs.getString("sector_map_version_v150","").orEmpty()
    fun setSectorMapVersion(v:String){prefs.edit().putString("sector_map_version_v150",v).apply()}

'''
s=s[:idx]+block+s[idx:]
p.write_text(s,encoding="utf-8")
print("v1.5 ledgers and Challenger promotion policy applied")

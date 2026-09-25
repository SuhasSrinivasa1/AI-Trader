package com.suhas.globaledgeai.data.local

import android.content.Context
import com.suhas.globaledgeai.domain.model.*
import org.json.JSONArray
import org.json.JSONObject
import java.security.MessageDigest
import java.time.LocalDate
import java.util.Locale

class EvidenceLedgerStore(context:Context){
    private val prefs=context.getSharedPreferences("global_edge_evidence_ledger_v150",Context.MODE_PRIVATE)
    private fun finite(v:Double)=if(v.isFinite())v else 0.0

    fun recordEvidence(record:PointInTimeEvidence){
        val all=loadEvidence(5000).toMutableList()
        if(all.none{it.id==record.id}){all+=record;saveEvidence(all)}
    }

    fun recordProspectiveEvidence(
        symbol:String,type:EvidenceType,key:String,value:String,source:String,
        effectiveAtText:String="",publishedAtText:String="",severity:EvidenceSeverity=EvidenceSeverity.INFO,
        hardBlock:Boolean=false,observedAt:Long=System.currentTimeMillis()
    ):PointInTimeEvidence{
        val stable=(symbol+"|"+type.name+"|"+key+"|"+value+"|"+source+"|"+observedAt).take(500)
        val id="EVID-"+sha256(stable).take(20)
        val r=PointInTimeEvidence(id,symbol.trim().uppercase(),type,key,value,source,observedAt,effectiveAtText,publishedAtText,severity,hardBlock)
        recordEvidence(r);return r
    }

    fun ingestExchangeNews(items:List<NewsItem>){
        val now=System.currentTimeMillis()
        items.forEach{n->
            val text=(n.title+" "+n.summary).lowercase(Locale.ROOT)
            val type=when{
                listOf("financial result","quarterly result","annual result","earnings","results for the quarter").any{text.contains(it)}->EvidenceType.FUNDAMENTAL
                listOf("upgrade","downgrade","target price","rating revision","analyst").any{text.contains(it)}->EvidenceType.ANALYST_REVISION
                listOf("board meeting","consider financial results","earnings date").any{text.contains(it)}->EvidenceType.EARNINGS_DATE
                else->null
            }?:return@forEach
            val eventDate=discoverDate(n.title+" "+n.summary).orEmpty()
            recordProspectiveEvidence(
                symbol=n.symbol,type=type,key=n.title.take(120),value=n.summary.take(500),
                source=n.source,effectiveAtText=eventDate,publishedAtText=n.publishedAt,
                severity=if(type==EvidenceType.EARNINGS_DATE)EvidenceSeverity.HIGH else EvidenceSeverity.MEDIUM,
                hardBlock=type==EvidenceType.EARNINGS_DATE&&eventDate.isNotBlank(),observedAt=now
            )
        }
    }

    fun evidenceAt(symbol:String,cutoffMs:Long):List<PointInTimeEvidence>{
        val s=symbol.trim().uppercase()
        return loadEvidence(5000).filter{it.observedAt<=cutoffMs&&(it.symbol.isBlank()||it.symbol==s)}.sortedByDescending{it.observedAt}
    }

    fun evidenceForEventDate(symbol:String,date:LocalDate,cutoffMs:Long):List<PointInTimeEvidence> =
        evidenceAt(symbol,cutoffMs).filter{it.effectiveAtText==date.toString()}

    private fun saveEvidence(records:List<PointInTimeEvidence>){
        val a=JSONArray()
        records.distinctBy{it.id}.sortedByDescending{it.observedAt}.take(5000).forEach{r->
            a.put(JSONObject().put("id",r.id).put("symbol",r.symbol).put("type",r.type.name).put("key",r.key).put("value",r.value)
                .put("source",r.source).put("observedAt",r.observedAt).put("effectiveAtText",r.effectiveAtText).put("publishedAtText",r.publishedAtText)
                .put("severity",r.severity.name).put("hardBlock",r.hardBlock))
        }
        prefs.edit().putString("pit_evidence",a.toString()).apply()
    }

    fun loadEvidence(limit:Int=5000):List<PointInTimeEvidence>{
        val a=runCatching{JSONArray(prefs.getString("pit_evidence","[]")?:"[]")}.getOrElse{JSONArray()}
        return buildList{
            for(i in 0 until a.length()){
                val j=a.optJSONObject(i)?:continue
                add(PointInTimeEvidence(
                    j.optString("id"),j.optString("symbol"),
                    runCatching{EvidenceType.valueOf(j.optString("type"))}.getOrDefault(EvidenceType.FUNDAMENTAL),
                    j.optString("key"),j.optString("value"),j.optString("source"),j.optLong("observedAt"),
                    j.optString("effectiveAtText"),j.optString("publishedAtText"),
                    runCatching{EvidenceSeverity.valueOf(j.optString("severity"))}.getOrDefault(EvidenceSeverity.INFO),
                    j.optBoolean("hardBlock")
                ))
            }
        }.sortedByDescending{it.observedAt}.take(limit)
    }

    fun saveChallenger(record:ChallengerShadowRecord){
        val all=loadChallengers(3000).filterNot{it.id==record.id}.toMutableList();all+=record
        val a=JSONArray()
        all.sortedByDescending{it.openedAt}.take(3000).forEach{r->
            a.put(JSONObject().put("id",r.id).put("strategyId",r.strategyId).put("strategyName",r.strategyName).put("symbol",r.symbol).put("direction",r.direction.name)
                .put("entryPrice",finite(r.entryPrice)).put("score",finite(r.score)).put("openedAt",r.openedAt).put("horizonAt",r.horizonAt).put("horizonMinutes",r.horizonMinutes)
                .put("targetPct",finite(r.targetPct)).put("stopPct",finite(r.stopPct)).put("evidence",r.evidence).put("status",r.status.name).put("resolvedAt",r.resolvedAt)
                .put("horizonPrice",finite(r.horizonPrice)).put("returnPct",finite(r.returnPct)).put("resolutionNote",r.resolutionNote).put("calendarVersion",r.calendarVersion))
        }
        prefs.edit().putString("challenger_shadows",a.toString()).apply()
    }

    fun loadChallengers(limit:Int=3000):List<ChallengerShadowRecord>{
        val a=runCatching{JSONArray(prefs.getString("challenger_shadows","[]")?:"[]")}.getOrElse{JSONArray()}
        return buildList{
            for(i in 0 until a.length()){
                val j=a.optJSONObject(i)?:continue
                add(ChallengerShadowRecord(
                    j.optString("id"),j.optString("strategyId"),j.optString("strategyName"),j.optString("symbol"),
                    runCatching{TradeDirection.valueOf(j.optString("direction"))}.getOrDefault(TradeDirection.LONG),
                    j.optDouble("entryPrice"),j.optDouble("score"),j.optLong("openedAt"),j.optLong("horizonAt"),j.optInt("horizonMinutes"),
                    j.optDouble("targetPct"),j.optDouble("stopPct"),j.optString("evidence"),
                    runCatching{ChallengerShadowStatus.valueOf(j.optString("status"))}.getOrDefault(ChallengerShadowStatus.OPEN),
                    j.optLong("resolvedAt"),j.optDouble("horizonPrice"),j.optDouble("returnPct"),j.optString("resolutionNote"),j.optString("calendarVersion")
                ))
            }
        }.sortedByDescending{it.openedAt}.take(limit)
    }

    data class ShadowStats(val observations:Int,val wins:Int,val winRatePct:Double,val avgReturnPct:Double)

    fun challengerStats(strategyId:String):ShadowStats{
        val rows=loadChallengers(3000).filter{it.strategyId==strategyId&&it.status in setOf(ChallengerShadowStatus.WIN,ChallengerShadowStatus.LOSS)}
        val wins=rows.count{it.status==ChallengerShadowStatus.WIN}
        return ShadowStats(rows.size,wins,if(rows.isEmpty())0.0 else wins*100.0/rows.size,if(rows.isEmpty())0.0 else rows.map{it.returnPct}.average())
    }

    fun saveBrokerOrder(record:BrokerOrderRecord){
        val all=loadBrokerOrders(500).filterNot{it.growwOrderId==record.growwOrderId}.toMutableList();all+=record
        val a=JSONArray()
        all.sortedByDescending{it.submittedAt}.take(500).forEach{r->
            val fills=JSONArray()
            r.fills.forEach{f->fills.put(JSONObject().put("growwTradeId",f.growwTradeId).put("exchangeTradeId",f.exchangeTradeId).put("price",finite(f.price)).put("quantity",f.quantity).put("tradeStatus",f.tradeStatus).put("tradeDateTime",f.tradeDateTime))}
            a.put(JSONObject().put("growwOrderId",r.growwOrderId).put("orderReferenceId",r.orderReferenceId).put("symbol",r.symbol).put("transactionType",r.transactionType)
                .put("product",r.product).put("requestedQuantity",r.requestedQuantity).put("submittedAt",r.submittedAt).put("orderStatus",r.orderStatus)
                .put("filledQuantity",r.filledQuantity).put("remainingQuantity",r.remainingQuantity).put("averageFillPrice",finite(r.averageFillPrice)).put("remark",r.remark)
                .put("lastReconciledAt",r.lastReconciledAt).put("fills",fills))
        }
        prefs.edit().putString("broker_orders",a.toString()).apply()
    }

    fun loadBrokerOrders(limit:Int=500):List<BrokerOrderRecord>{
        val a=runCatching{JSONArray(prefs.getString("broker_orders","[]")?:"[]")}.getOrElse{JSONArray()}
        return buildList{
            for(i in 0 until a.length()){
                val j=a.optJSONObject(i)?:continue
                val fa=j.optJSONArray("fills")?:JSONArray()
                val fills=buildList{
                    for(k in 0 until fa.length()){
                        val f=fa.optJSONObject(k)?:continue
                        add(BrokerFill(f.optString("growwTradeId"),f.optString("exchangeTradeId"),f.optDouble("price"),f.optInt("quantity"),f.optString("tradeStatus"),f.optString("tradeDateTime")))
                    }
                }
                add(BrokerOrderRecord(j.optString("growwOrderId"),j.optString("orderReferenceId"),j.optString("symbol"),j.optString("transactionType"),j.optString("product"),
                    j.optInt("requestedQuantity"),j.optLong("submittedAt"),j.optString("orderStatus"),j.optInt("filledQuantity"),j.optInt("remainingQuantity"),
                    j.optDouble("averageFillPrice"),j.optString("remark"),j.optLong("lastReconciledAt"),fills))
            }
        }.sortedByDescending{it.submittedAt}.take(limit)
    }

    fun saveDecision(record:DecisionSnapshot){
        val all=loadDecisions(1500).filterNot{it.id==record.id}.toMutableList();all+=record
        val a=JSONArray()
        all.sortedByDescending{it.decisionAt}.take(1500).forEach{r->
            val ev=JSONArray();r.evidenceIds.forEach{ev.put(it)}
            a.put(JSONObject().put("id",r.id).put("symbol",r.symbol).put("direction",r.direction).put("engine",r.engine).put("strategyId",r.strategyId)
                .put("action",r.action).put("score",finite(r.score)).put("decisionAt",r.decisionAt).put("calendarVersion",r.calendarVersion).put("industry",r.industry)
                .put("sectorBreadthPct",finite(r.sectorBreadthPct)).put("stockVsSectorPct",finite(r.stockVsSectorPct)).put("evidenceIds",ev)
                .put("hardGate",r.hardGate).put("reason",r.reason).put("decisionHash",r.decisionHash))
        }
        prefs.edit().putString("decision_snapshots",a.toString()).apply()
    }

    fun loadDecisions(limit:Int=1500):List<DecisionSnapshot>{
        val a=runCatching{JSONArray(prefs.getString("decision_snapshots","[]")?:"[]")}.getOrElse{JSONArray()}
        return buildList{
            for(i in 0 until a.length()){
                val j=a.optJSONObject(i)?:continue
                val ea=j.optJSONArray("evidenceIds")?:JSONArray()
                val ids=buildList{for(k in 0 until ea.length())add(ea.optString(k))}
                add(DecisionSnapshot(j.optString("id"),j.optString("symbol"),j.optString("direction"),j.optString("engine"),j.optString("strategyId"),j.optString("action"),
                    j.optDouble("score"),j.optLong("decisionAt"),j.optString("calendarVersion"),j.optString("industry"),j.optDouble("sectorBreadthPct"),j.optDouble("stockVsSectorPct"),
                    ids,j.optBoolean("hardGate"),j.optString("reason"),j.optString("decisionHash")))
            }
        }.sortedByDescending{it.decisionAt}.take(limit)
    }

    fun decisionHash(raw:String)=sha256(raw)
    private fun sha256(raw:String)=MessageDigest.getInstance("SHA-256").digest(raw.toByteArray()).joinToString(""){"%02x".format(it)}

    private fun discoverDate(text:String):String?{
        Regex("""\\b(20\\d{2})[-/](\\d{1,2})[-/](\\d{1,2})\\b""").find(text)?.let{m->
            return runCatching{LocalDate.of(m.groupValues[1].toInt(),m.groupValues[2].toInt(),m.groupValues[3].toInt()).toString()}.getOrNull()
        }
        val months=mapOf("jan" to 1,"feb" to 2,"mar" to 3,"apr" to 4,"may" to 5,"jun" to 6,"jul" to 7,"aug" to 8,"sep" to 9,"oct" to 10,"nov" to 11,"dec" to 12)
        Regex("""\\b(\\d{1,2})\\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\\s+(20\\d{2})\\b""",RegexOption.IGNORE_CASE).find(text)?.let{m->
            val mon=months[m.groupValues[2].take(3).lowercase()]?:return@let
            return runCatching{LocalDate.of(m.groupValues[3].toInt(),mon,m.groupValues[1].toInt()).toString()}.getOrNull()
        }
        return null
    }
}

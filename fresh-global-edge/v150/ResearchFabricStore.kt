package com.suhas.globaledgeai.data.local

import android.content.Context
import com.suhas.globaledgeai.domain.model.*
import org.json.JSONArray
import org.json.JSONObject
import java.security.MessageDigest

class ResearchFabricStore(context:Context){
    private val prefs=context.getSharedPreferences("research_fabric_v150",Context.MODE_PRIVATE)

    fun captureEvidence(e:PointInTimeEvidence){
        val all=loadEvidence(3000).filterNot{it.id==e.id}.toMutableList();all+=e
        val a=JSONArray()
        all.sortedByDescending{it.observedAt}.take(3000).forEach{x->
            a.put(JSONObject().put("id",x.id).put("symbol",x.symbol).put("kind",x.kind.name)
                .put("field",x.field).put("value",x.value).put("source",x.source)
                .put("effectiveAt",x.effectiveAt).put("observedAt",x.observedAt)
                .put("retrievedAt",x.retrievedAt).put("revisionId",x.revisionId))
        }
        prefs.edit().putString("evidence",a.toString()).apply()
    }

    fun loadEvidence(limit:Int=3000):List<PointInTimeEvidence>{
        val a=runCatching{JSONArray(prefs.getString("evidence","[]"))}.getOrElse{JSONArray()}
        return buildList{
            for(i in 0 until a.length()){
                val j=a.optJSONObject(i)?:continue
                add(PointInTimeEvidence(
                    j.optString("id"),j.optString("symbol"),
                    runCatching{EvidenceKind.valueOf(j.optString("kind"))}.getOrDefault(EvidenceKind.FUNDAMENTAL),
                    j.optString("field"),j.optString("value"),j.optString("source"),
                    j.optLong("effectiveAt"),j.optLong("observedAt"),j.optLong("retrievedAt"),j.optString("revisionId")
                ))
            }
        }.sortedByDescending{it.observedAt}.take(limit)
    }

    fun evidenceAsOf(symbol:String,cutoffAt:Long):List<PointInTimeEvidence> =
        loadEvidence().filter{it.symbol.equals(symbol,true)&&it.observedAt<=cutoffAt&&it.retrievedAt<=cutoffAt}

    fun appendChallenger(r:ChallengerShadowRecord){
        val all=loadChallengers(3000).filterNot{it.id==r.id}.toMutableList();all+=r;saveChallengers(all)
    }

    fun saveChallengers(rows:List<ChallengerShadowRecord>){
        val a=JSONArray()
        rows.sortedByDescending{it.openedAt}.take(3000).forEach{x->
            a.put(JSONObject()
                .put("id",x.id).put("strategyId",x.strategyId).put("strategyName",x.strategyName)
                .put("symbol",x.symbol).put("direction",x.direction.name).put("score",x.score)
                .put("entryPrice",x.entryPrice).put("targetPct",x.targetPct).put("stopPct",x.stopPct)
                .put("openedAt",x.openedAt).put("horizonAt",x.horizonAt)
                .put("calendarVersion",x.calendarVersion).put("researchSignature",x.researchSignature)
                .put("outcome",x.outcome.name).put("resolvedAt",x.resolvedAt)
                .put("horizonPrice",x.horizonPrice).put("returnPct",x.returnPct)
                .put("resolutionNote",x.resolutionNote))
        }
        prefs.edit().putString("challengers",a.toString()).apply()
    }

    fun loadChallengers(limit:Int=3000):List<ChallengerShadowRecord>{
        val a=runCatching{JSONArray(prefs.getString("challengers","[]"))}.getOrElse{JSONArray()}
        return buildList{
            for(i in 0 until a.length()){
                val j=a.optJSONObject(i)?:continue
                add(ChallengerShadowRecord(
                    j.optString("id"),j.optString("strategyId"),j.optString("strategyName"),j.optString("symbol"),
                    runCatching{TradeDirection.valueOf(j.optString("direction"))}.getOrDefault(TradeDirection.LONG),
                    j.optDouble("score"),j.optDouble("entryPrice"),j.optDouble("targetPct"),j.optDouble("stopPct"),
                    j.optLong("openedAt"),j.optLong("horizonAt"),j.optString("calendarVersion"),
                    j.optString("researchSignature"),
                    runCatching{ChallengerOutcome.valueOf(j.optString("outcome"))}.getOrDefault(ChallengerOutcome.PENDING),
                    j.optLong("resolvedAt"),j.optDouble("horizonPrice"),j.optDouble("returnPct"),j.optString("resolutionNote")
                ))
            }
        }.sortedByDescending{it.openedAt}.take(limit)
    }

    fun appendDecision(
        symbol:String,decision:String,strategyId:String,score:Double,evidenceVersion:String,
        calendarVersion:String,evidence:String,dataCutoffAt:Long
    ):DecisionSnapshot{
        val captured=System.currentTimeMillis()
        val raw=listOf(symbol,decision,strategyId,score.toString(),captured.toString(),dataCutoffAt.toString(),evidenceVersion,calendarVersion,evidence).joinToString("|")
        val id=MessageDigest.getInstance("SHA-256").digest(raw.toByteArray()).joinToString(""){"%02x".format(it)}.take(20)
        val d=DecisionSnapshot(id,symbol,decision,captured,strategyId,score,evidenceVersion,calendarVersion,evidence.take(1200),dataCutoffAt)
        val all=loadDecisions(3000).filterNot{it.id==id}.toMutableList();all+=d
        val a=JSONArray()
        all.sortedByDescending{it.capturedAt}.take(3000).forEach{x->
            a.put(JSONObject().put("id",x.id).put("symbol",x.symbol).put("decision",x.decision)
                .put("capturedAt",x.capturedAt).put("strategyId",x.strategyId).put("score",x.score)
                .put("evidenceVersion",x.evidenceVersion).put("calendarVersion",x.calendarVersion)
                .put("evidence",x.evidence).put("dataCutoffAt",x.dataCutoffAt))
        }
        prefs.edit().putString("decisions",a.toString()).apply()
        return d
    }

    fun loadDecisions(limit:Int=3000):List<DecisionSnapshot>{
        val a=runCatching{JSONArray(prefs.getString("decisions","[]"))}.getOrElse{JSONArray()}
        return buildList{
            for(i in 0 until a.length()){
                val j=a.optJSONObject(i)?:continue
                add(DecisionSnapshot(
                    j.optString("id"),j.optString("symbol"),j.optString("decision"),j.optLong("capturedAt"),
                    j.optString("strategyId"),j.optDouble("score"),j.optString("evidenceVersion"),
                    j.optString("calendarVersion"),j.optString("evidence"),j.optLong("dataCutoffAt")
                ))
            }
        }.sortedByDescending{it.capturedAt}.take(limit)
    }

    fun upsertMacroEvents(events:List<MacroEvent>){
        val all=loadMacroEvents().associateBy{it.id}.toMutableMap()
        events.forEach{all[it.id]=it}
        val a=JSONArray()
        all.values.sortedBy{it.decisionAt}.forEach{x->
            a.put(JSONObject().put("id",x.id).put("label",x.label).put("startAt",x.startAt)
                .put("decisionAt",x.decisionAt).put("observedAt",x.observedAt).put("source",x.source)
                .put("riskWindowMinutes",x.riskWindowMinutes).put("symbol",x.symbol))
        }
        prefs.edit().putString("macro_events",a.toString()).apply()
    }

    fun loadMacroEvents():List<MacroEvent>{
        val a=runCatching{JSONArray(prefs.getString("macro_events","[]"))}.getOrElse{JSONArray()}
        return buildList{
            for(i in 0 until a.length()){
                val j=a.optJSONObject(i)?:continue
                add(MacroEvent(j.optString("id"),j.optString("label"),j.optLong("startAt"),j.optLong("decisionAt"),
                    j.optLong("observedAt"),j.optString("source"),j.optInt("riskWindowMinutes",120),j.optString("symbol")))
            }
        }.sortedBy{it.decisionAt}
    }
}

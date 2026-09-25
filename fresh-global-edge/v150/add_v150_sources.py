#!/usr/bin/env python3
from pathlib import Path
import sys
root=Path(sys.argv[1]).resolve()

models=root/"app/src/main/java/com/suhas/ucsentinel/domain/model/V150Models.kt"
models.parent.mkdir(parents=True,exist_ok=True)
models.write_text(r'''package com.suhas.globaledgeai.domain.model

enum class EvidenceKind { FUNDAMENTAL, ANALYST, EARNINGS_DATE, SECTOR, MACRO, EXECUTION, RISK, DECISION }
enum class ChallengerShadowState { OPEN, RESOLVED, UNRESOLVED_DATA }
enum class BrokerReconState { SUBMITTED, OPEN, PARTIAL, FILLED, REJECTED, CANCELLED, UNKNOWN }

data class PointInTimeEvidence(
    val id:String,
    val symbol:String,
    val kind:EvidenceKind,
    val label:String,
    val value:String,
    val source:String,
    val effectiveAt:Long,
    val observedAt:Long,
    val retrievedAt:Long,
    val sourceVersion:String=""
)

data class MacroEventRecord(
    val id:String,
    val title:String,
    val startsAt:Long,
    val endsAt:Long,
    val source:String,
    val riskLevel:String="HIGH"
)

data class SectorSnapshot(
    val symbol:String,
    val industry:String,
    val observedAt:Long,
    val stockReturnPct:Double,
    val sectorReturnPct:Double,
    val peerBreadthPct:Double,
    val relativeStrengthPct:Double,
    val peerConfirmationPct:Double,
    val source:String
)

data class ChallengerShadowRecord(
    val id:String,
    val strategyId:String,
    val strategyName:String,
    val symbol:String,
    val direction:TradeDirection,
    val score:Double,
    val entryPrice:Double,
    val targetPct:Double,
    val stopPct:Double,
    val openedAt:Long,
    val dueAt:Long,
    val dueSessionDate:String,
    val researchSignature:String,
    val evidence:String,
    val state:ChallengerShadowState=ChallengerShadowState.OPEN,
    val resolvedAt:Long=0L,
    val horizonPrice:Double=0.0,
    val returnPct:Double=0.0,
    val win:Boolean=false,
    val resolutionNote:String=""
)

data class BrokerFill(
    val tradeId:String,
    val quantity:Int,
    val price:Double,
    val tradedAt:String
)

data class BrokerExecutionRecord(
    val localId:String,
    val growwOrderId:String,
    val orderReferenceId:String,
    val symbol:String,
    val side:String,
    val product:String,
    val requestedQuantity:Int,
    val submittedAt:Long,
    val status:String,
    val state:BrokerReconState,
    val filledQuantity:Int=0,
    val remainingQuantity:Int=0,
    val averageFillPrice:Double=0.0,
    val lastReconciledAt:Long=0L,
    val remark:String="",
    val fills:List<BrokerFill> = emptyList()
)

data class DecisionSnapshot(
    val id:String,
    val symbol:String,
    val direction:String,
    val action:String,
    val decisionAt:Long,
    val strategyId:String,
    val score:Double,
    val researchSignature:String,
    val handbookPattern:String,
    val handbookCombination:String,
    val calendarVersion:String,
    val catalogVersion:String,
    val evidenceIds:List<String>,
    val hardGates:List<String>,
    val sourceHash:String
)
''',encoding="utf-8")

calendar=root/"app/src/main/java/com/suhas/ucsentinel/domain/engine/NseTradingCalendar2026.kt"
calendar.write_text(r'''package com.suhas.globaledgeai.domain.engine

import java.time.*

object NseTradingCalendar2026 {
    const val VERSION="NSE-CMTR-71775-2026"
    private val ist=ZoneId.of("Asia/Kolkata")
    private val holidays=setOf(
        LocalDate.of(2026,1,26),
        LocalDate.of(2026,3,3),
        LocalDate.of(2026,3,26),
        LocalDate.of(2026,3,31),
        LocalDate.of(2026,4,3),
        LocalDate.of(2026,4,14),
        LocalDate.of(2026,5,1),
        LocalDate.of(2026,5,28),
        LocalDate.of(2026,6,26),
        LocalDate.of(2026,9,14),
        LocalDate.of(2026,10,2),
        LocalDate.of(2026,10,20),
        LocalDate.of(2026,11,10),
        LocalDate.of(2026,11,24),
        LocalDate.of(2026,12,25)
    )
    fun isTradingDate(d:LocalDate)=d.year!=2026 || (d.dayOfWeek !in setOf(DayOfWeek.SATURDAY,DayOfWeek.SUNDAY) && d !in holidays)
    fun nextTradingDate(from:LocalDate):LocalDate{var d=from.plusDays(1);while(!isTradingDate(d))d=d.plusDays(1);return d}
    fun remainingSessionsInWeek(from:LocalDate):Int{
        var d=from;var n=0
        while(d.dayOfWeek!=DayOfWeek.SATURDAY){if(isTradingDate(d)&&!d.isBefore(from))n++;d=d.plusDays(1)}
        return n
    }
    fun remainingSessionsInMonth(from:LocalDate):Int{
        var d=from;var n=0
        while(d.month==from.month){if(isTradingDate(d)&&!d.isBefore(from))n++;d=d.plusDays(1)}
        return n
    }
    fun addTradingMinutes(epochMs:Long,minutes:Int):Long{
        var z=Instant.ofEpochMilli(epochMs).atZone(ist)
        var left=minutes.coerceAtLeast(0)
        if(!isTradingDate(z.toLocalDate())||z.toLocalTime()<LocalTime.of(9,15)){
            var d=z.toLocalDate()
            if(!isTradingDate(d))d=nextTradingDate(d)
            z=d.atTime(9,15).atZone(ist)
        }
        if(z.toLocalTime()>=LocalTime.of(15,30))z=nextTradingDate(z.toLocalDate()).atTime(9,15).atZone(ist)
        while(left>0){
            val close=z.toLocalDate().atTime(15,30).atZone(ist)
            val available=Duration.between(z,close).toMinutes().toInt().coerceAtLeast(0)
            if(left<=available){z=z.plusMinutes(left.toLong());left=0}
            else{left-=available;z=nextTradingDate(z.toLocalDate()).atTime(9,15).atZone(ist)}
        }
        return z.toInstant().toEpochMilli()
    }
}
''',encoding="utf-8")

fabric=root/"app/src/main/java/com/suhas/ucsentinel/domain/engine/EvidenceFabricEngine.kt"
fabric.write_text(r'''package com.suhas.globaledgeai.domain.engine

import com.suhas.globaledgeai.domain.model.*
import java.security.MessageDigest
import java.time.*
import kotlin.math.abs

object EvidenceFabricEngine {
    const val VERSION="EVIDENCE-FABRIC-2026.09.25"
    private val ist=ZoneId.of("Asia/Kolkata")

    fun rbiMpcEvents2026():List<MacroEventRecord>{
        fun event(id:String,title:String,start:LocalDate,end:LocalDate):MacroEventRecord{
            val s=start.atTime(0,0).atZone(ist).toInstant().toEpochMilli()
            val e=end.atTime(23,59).atZone(ist).toInstant().toEpochMilli()
            return MacroEventRecord(id,title,s,e,"RBI MPC FY2026-27 published schedule","HIGH")
        }
        return listOf(
            event("RBI-MPC-2026-10","RBI MPC October 2026",LocalDate.of(2026,10,5),LocalDate.of(2026,10,7)),
            event("RBI-MPC-2026-12","RBI MPC December 2026",LocalDate.of(2026,12,2),LocalDate.of(2026,12,4))
        )
    }

    fun macroRiskAt(epochMs:Long,events:List<MacroEventRecord>):String{
        val oneDay=24L*60*60*1000
        val near=events.any{epochMs in (it.startsAt-oneDay)..(it.endsAt+oneDay)}
        return if(near)"HIGH" else "NORMAL"
    }

    fun pointInTimeVisible(records:List<PointInTimeEvidence>,asOf:Long):List<PointInTimeEvidence> =
        records.filter{it.observedAt<=asOf && it.retrievedAt<=asOf && it.effectiveAt<=asOf}

    fun sectorSnapshot(symbol:String,industry:String,stockReturnPct:Double,peerReturns:List<Double>,observedAt:Long,source:String):SectorSnapshot{
        val valid=peerReturns.filter{it.isFinite()}
        val sector=if(valid.isEmpty())0.0 else valid.average()
        val breadth=if(valid.isEmpty())0.0 else valid.count{it>0.0}*100.0/valid.size
        val rel=stockReturnPct-sector
        val confirm=if(valid.isEmpty())0.0 else valid.count{if(stockReturnPct>=0)it>=0 else it<=0}*100.0/valid.size
        return SectorSnapshot(symbol,industry,observedAt,stockReturnPct,sector,breadth,rel,confirm,source)
    }

    fun hash(parts:List<String>):String{
        val bytes=MessageDigest.getInstance("SHA-256").digest(parts.joinToString("|").toByteArray())
        return bytes.joinToString(""){"%02x".format(it)}
    }
}
''',encoding="utf-8")

print("v1.5.0 core evidence/calendar models created")

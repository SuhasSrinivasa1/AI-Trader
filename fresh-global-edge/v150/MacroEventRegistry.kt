package com.suhas.globaledgeai.domain.engine

import com.suhas.globaledgeai.domain.model.MacroEvent
import java.time.LocalDate
import java.time.LocalTime
import java.time.ZoneId

class MacroEventRegistry {
    companion object {
        const val VERSION="RBI-MPC-FY27-2026-03-23"
        private val IST=ZoneId.of("Asia/Kolkata")
    }

    fun seededEvents(observedAt:Long):List<MacroEvent>{
        fun event(id:String,label:String,start:LocalDate,decision:LocalDate)=MacroEvent(
            id=id,
            label=label,
            startAt=start.atTime(LocalTime.of(0,0)).atZone(IST).toInstant().toEpochMilli(),
            decisionAt=decision.atTime(LocalTime.of(10,0)).atZone(IST).toInstant().toEpochMilli(),
            observedAt=observedAt,
            source="RBI Press Release 2025-2026/2306",
            riskWindowMinutes=180
        )
        return listOf(
            event("RBI-MPC-2026-10","RBI MPC decision",LocalDate.of(2026,10,5),LocalDate.of(2026,10,7)),
            event("RBI-MPC-2026-12","RBI MPC decision",LocalDate.of(2026,12,2),LocalDate.of(2026,12,4)),
            event("RBI-MPC-2027-02","RBI MPC decision",LocalDate.of(2027,2,3),LocalDate.of(2027,2,5))
        )
    }

    fun isRiskWindow(nowMs:Long,events:List<MacroEvent>):Boolean =
        events.any{e->
            val pad=e.riskWindowMinutes*60_000L
            nowMs>=e.decisionAt-pad&&nowMs<=e.decisionAt+pad
        }
}

package com.suhas.globaledgeai.domain.engine

import com.suhas.globaledgeai.domain.model.*
import java.time.LocalDate

object MacroEventRegistry {
    const val VERSION="RBI-MPC-2026-27-20260323"

    data class Event(
        val id:String,val label:String,val start:LocalDate,val end:LocalDate,
        val severity:EvidenceSeverity,val hardBlock:Boolean,val source:String
    )

    val seeded=listOf(
        Event("RBI-MPC-2026-04","RBI MPC • Apr 6–8",LocalDate.of(2026,4,6),LocalDate.of(2026,4,8),EvidenceSeverity.HIGH,false,"RBI press release 23-Mar-2026"),
        Event("RBI-MPC-2026-06","RBI MPC • Jun 3–5",LocalDate.of(2026,6,3),LocalDate.of(2026,6,5),EvidenceSeverity.HIGH,false,"RBI press release 23-Mar-2026"),
        Event("RBI-MPC-2026-08","RBI MPC • Aug 3–5",LocalDate.of(2026,8,3),LocalDate.of(2026,8,5),EvidenceSeverity.HIGH,false,"RBI press release 23-Mar-2026"),
        Event("RBI-MPC-2026-10","RBI MPC • Oct 5–7",LocalDate.of(2026,10,5),LocalDate.of(2026,10,7),EvidenceSeverity.HIGH,false,"RBI press release 23-Mar-2026"),
        Event("RBI-MPC-2026-12","RBI MPC • Dec 2–4",LocalDate.of(2026,12,2),LocalDate.of(2026,12,4),EvidenceSeverity.HIGH,false,"RBI press release 23-Mar-2026"),
        Event("RBI-MPC-2027-02","RBI MPC • Feb 3–5",LocalDate.of(2027,2,3),LocalDate.of(2027,2,5),EvidenceSeverity.HIGH,false,"RBI press release 23-Mar-2026")
    )

    fun active(date:LocalDate)=seeded.filter{!date.isBefore(it.start)&&!date.isAfter(it.end)}
    fun next(date:LocalDate)=seeded.filter{!it.end.isBefore(date)}.minByOrNull{it.start}
}

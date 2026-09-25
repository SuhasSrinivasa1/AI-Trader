#!/usr/bin/env python3
from pathlib import Path
import sys
root=Path(sys.argv[1]).resolve()

def one(s,old,new,label):
    n=s.count(old)
    if n!=1: raise SystemExit(f"{label}: expected 1 found {n}")
    return s.replace(old,new,1)

# 1) Exact current 2026 NSE calendar: include the subsequently announced full Budget Sunday
# session (01-Feb-2026) and the subsequently announced 15-Jan-2026 election holiday.
p=root/"app/src/main/java/com/suhas/ucsentinel/domain/engine/NseTradingCalendar.kt"
s=p.read_text(encoding="utf-8")
anchor='''    private val holidays2026=setOf(
'''
insert='''    private val specialFullSessions2026=setOf(
        // NSE/CMTR/72349: Sunday Budget session, standard 09:15-15:30 market timings.
        LocalDate.of(2026,2,1)
    )

    private val holidays2026=setOf(
'''
s=one(s,anchor,insert,"special 2026 full session")
old='''    fun isRegularTradingDay(date:LocalDate):Boolean{
        if(date.dayOfWeek==DayOfWeek.SATURDAY||date.dayOfWeek==DayOfWeek.SUNDAY)return false
        if(date.year==2026&&date in holidays2026)return false
'''
new='''    fun isRegularTradingDay(date:LocalDate):Boolean{
        if(date.year==2026&&date in specialFullSessions2026)return true
        if(date.dayOfWeek==DayOfWeek.SATURDAY||date.dayOfWeek==DayOfWeek.SUNDAY)return false
        if(date.year==2026&&date in holidays2026)return false
'''
s=one(s,old,new,"calendar special-session handling")
s=s.replace(
    'Source: NSE "Holidays for the calendar year 2026 - Equities", captured 24-Sep-2026.',
    'Source: NSE 2026 Equities holiday calendar plus subsequent NSE 2026 special-session/holiday circulars, captured 25-Sep-2026.'
)
p.write_text(s,encoding="utf-8")

# 2) Research hardening: stale earnings evidence must not permanently penalize a stock.
# RBI HIGH-risk meeting decision day is a true WAIT gate rather than merely a score adjustment.
p=root/"app/src/main/java/com/suhas/ucsentinel/data/repository/UCSentinelRepository.kt"
s=p.read_text(encoding="utf-8")
old='''        val now=ZonedDateTime.now(ist);val date=now.toLocalDate();val start=date.atTime(9,15).format(dateTimeFmt);val end=now.plusMinutes(1).format(dateTimeFmt)
        val macroRisk=EvidenceFabricEngine.activeMacroRisk(date,fabricStore.macroEvents())
'''
new='''        val now=ZonedDateTime.now(ist);val date=now.toLocalDate();val start=date.atTime(9,15).format(dateTimeFmt);val end=now.plusMinutes(1).format(dateTimeFmt)
        val macroRisk=EvidenceFabricEngine.activeMacroRisk(date,fabricStore.macroEvents())
        val macroDecisionRisk=macroRisk.filter{it.severity.equals("HIGH",true)&&it.endDateIso==date.toString()}
'''
s=one(s,old,new,"macro decision risk")
old='''            val pit=fabricStore.evidenceAsOf(inst.tradingSymbol,now.toInstant().toEpochMilli())
            val fundamentalCount=pit.count{it.kind==EvidenceKind.FUNDAMENTAL}
            val analystCount=pit.count{it.kind==EvidenceKind.ANALYST_RATING}
            val earningsCount=pit.count{it.kind==EvidenceKind.EARNINGS_EVENT}
'''
new='''            val nowMs=now.toInstant().toEpochMilli()
            val pit=fabricStore.evidenceAsOf(inst.tradingSymbol,nowMs)
            val fundamentalCount=pit.count{it.kind==EvidenceKind.FUNDAMENTAL}
            val analystCount=pit.count{it.kind==EvidenceKind.ANALYST_RATING}
            // Only a genuinely current/upcoming earnings event affects today's trade. Old result
            // announcements remain in the point-in-time audit store but do not create permanent risk.
            val currentEarnings=pit.filter{it.kind==EvidenceKind.EARNINGS_EVENT&&it.effectiveAt>=nowMs-6L*60*60*1000&&it.effectiveAt<=nowMs+24L*60*60*1000}
            val earningsCount=currentEarnings.size
'''
s=one(s,old,new,"current earnings evidence window")
needle='''                fun reject(setup:StrategySetup,reason:String){recordRejectedStrategyShadow(setup,reason)}

                if(e.targetPct<ExecutionQuality.MIN_PLAN_SEPARATION_PCT||e.stopPct<ExecutionQuality.MIN_PLAN_SEPARATION_PCT){
'''
replacement='''                fun reject(setup:StrategySetup,reason:String){recordRejectedStrategyShadow(setup,reason)}

                // A scheduled HIGH macro decision is an explicit research WAIT gate. The score
                // cannot override it, matching the handbook's hard-gate architecture.
                if(macroDecisionRisk.isNotEmpty()){
                    reject(baseSetup,"MACRO_DECISION_HARD_GATE "+macroDecisionRisk.joinToString(","){it.title})
                    continue
                }

                if(e.targetPct<ExecutionQuality.MIN_PLAN_SEPARATION_PCT||e.stopPct<ExecutionQuality.MIN_PLAN_SEPARATION_PCT){
'''
s=one(s,needle,replacement,"macro hard gate")
p.write_text(s,encoding="utf-8")

print("v1.5.0 final calendar/event hardening applied")

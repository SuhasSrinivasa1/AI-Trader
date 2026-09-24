#!/usr/bin/env python3
from pathlib import Path
import sys
root=Path(sys.argv[1]).resolve()
p=root/"app/src/main/java/com/suhas/ucsentinel/data/repository/UCSentinelRepository.kt"
s=p.read_text(encoding="utf-8")
def one(old,new,label):
    global s
    n=s.count(old)
    if n!=1: raise SystemExit(f"{label}: expected 1 found {n}")
    s=s.replace(old,new,1)

one(
'''            TradeCallBucket.NEXT_SESSION->if(d.dayOfWeek !in setOf(DayOfWeek.SATURDAY,DayOfWeek.SUNDAY)&&t<LocalTime.of(9,15))d else nextTradingDate(d)
''',
'''            TradeCallBucket.NEXT_SESSION->if(NseTradingCalendar.isRegularTradingDay(d)&&t<NseTradingCalendar.regularOpen)d else nextTradingDate(d)
''',"next-session calendar")

one(
'''        val now=ZonedDateTime.now(ist)
        val indiaDay=now.dayOfWeek !in setOf(DayOfWeek.SATURDAY,DayOfWeek.SUNDAY)
        val indiaMarketOpen=indiaDay && !now.toLocalTime().isBefore(LocalTime.of(9,15)) && now.toLocalTime().isBefore(LocalTime.of(15,31))
''',
'''        val now=ZonedDateTime.now(ist)
        val indiaDay=NseTradingCalendar.isRegularTradingDay(now.toLocalDate())
        val indiaMarketOpen=NseTradingCalendar.isOpen(now)
''',"global lead calendar")

one(
'''        var predictionDate=if(now.toLocalTime()<LocalTime.of(9,15))now.toLocalDate().minusDays(1) else now.toLocalDate()
        while(predictionDate.dayOfWeek==DayOfWeek.SATURDAY||predictionDate.dayOfWeek==DayOfWeek.SUNDAY)predictionDate=predictionDate.minusDays(1)
''',
'''        var predictionDate=if(now.toLocalTime()<NseTradingCalendar.regularOpen)now.toLocalDate().minusDays(1) else now.toLocalDate()
        while(!NseTradingCalendar.isRegularTradingDay(predictionDate))predictionDate=predictionDate.minusDays(1)
''',"pre-UC prediction calendar")

p.write_text(s,encoding="utf-8")
print("NSE 2026 calendar propagated to Global Lead and next-session publication")

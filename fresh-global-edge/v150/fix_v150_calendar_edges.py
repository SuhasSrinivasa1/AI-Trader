#!/usr/bin/env python3
from pathlib import Path
import sys
root=Path(sys.argv[1]).resolve()
p=root/"app/src/main/java/com/suhas/ucsentinel/data/repository/UCSentinelRepository.kt"
s=p.read_text(encoding="utf-8")
s=s.replace('''        val weekend=ZonedDateTime.now(ist).dayOfWeek in setOf(DayOfWeek.SATURDAY,DayOfWeek.SUNDAY)
''','''        val weekend=!NseTradingCalendar2026.isTradingDate(LocalDate.now(ist))
''')
old='''        val indiaDay=now.dayOfWeek !in setOf(DayOfWeek.SATURDAY,DayOfWeek.SUNDAY)
        val indiaMarketOpen=indiaDay && !now.toLocalTime().isBefore(LocalTime.of(9,15)) && now.toLocalTime().isBefore(LocalTime.of(15,31))
'''
new='''        val indiaMarketOpen=marketSessionInfo(now).isOpen
'''
if s.count(old)!=1: raise SystemExit("global market-open anchor mismatch")
s=s.replace(old,new,1)
old='''        var predictionDate=if(now.toLocalTime()<LocalTime.of(9,15))now.toLocalDate().minusDays(1) else now.toLocalDate()
        while(predictionDate.dayOfWeek==DayOfWeek.SATURDAY||predictionDate.dayOfWeek==DayOfWeek.SUNDAY)predictionDate=predictionDate.minusDays(1)
'''
new='''        val today=now.toLocalDate()
        val predictionDate=if(NseTradingCalendar2026.isTradingDate(today)&&now.toLocalTime()>=NseTradingCalendar2026.open)today
            else NseTradingCalendar2026.previousTradingDate(today)
'''
if s.count(old)!=1: raise SystemExit("prediction-date anchor mismatch")
s=s.replace(old,new,1)
p.write_text(s,encoding="utf-8")
print("Exact NSE calendar propagated to global and next-session publication gates")

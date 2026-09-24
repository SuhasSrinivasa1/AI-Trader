#!/usr/bin/env python3
from pathlib import Path
import sys
root=Path(sys.argv[1]).resolve()
p=root/"app/src/main/java/com/suhas/ucsentinel/domain/engine/NseTradingCalendar.kt"
p.parent.mkdir(parents=True,exist_ok=True)
p.write_text(r'''package com.suhas.globaledgeai.domain.engine

import java.time.*

/**
 * Point-in-time regular-session calendar for NSE Equity CASH.
 * Source: NSE "Holidays for the calendar year 2026 - Equities", captured 24-Sep-2026.
 * Muhurat Trading on 08-Nov-2026 is intentionally NOT treated as a regular 09:15-15:30 session.
 */
object NseTradingCalendar {
    const val VERSION="NSE-EQUITY-2026-OFFICIAL-2026-09-24"
    val zone:ZoneId=ZoneId.of("Asia/Kolkata")
    val regularOpen:LocalTime=LocalTime.of(9,15)
    val regularClose:LocalTime=LocalTime.of(15,30)

    private val holidays2026=setOf(
        LocalDate.of(2026,1,15),
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

    fun isRegularTradingDay(date:LocalDate):Boolean{
        if(date.dayOfWeek==DayOfWeek.SATURDAY||date.dayOfWeek==DayOfWeek.SUNDAY)return false
        if(date.year==2026&&date in holidays2026)return false
        // Outside the packaged 2026 calendar, weekdays are treated as provisional rather than "verified".
        return true
    }

    fun calendarVerified(date:LocalDate):Boolean=date.year==2026

    fun nextTradingDay(from:LocalDate):LocalDate{
        var d=from.plusDays(1)
        while(!isRegularTradingDay(d))d=d.plusDays(1)
        return d
    }

    fun previousTradingDay(from:LocalDate):LocalDate{
        var d=from.minusDays(1)
        while(!isRegularTradingDay(d))d=d.minusDays(1)
        return d
    }

    fun sessionsRemainingInWeek(from:LocalDate,includeToday:Boolean=true):Int{
        val end=from.plusDays((DayOfWeek.SUNDAY.value-from.dayOfWeek.value).toLong())
        var d=if(includeToday)from else from.plusDays(1);var n=0
        while(!d.isAfter(end)){if(isRegularTradingDay(d))n++;d=d.plusDays(1)}
        return n
    }

    fun sessionsRemainingInMonth(from:LocalDate,includeToday:Boolean=true):Int{
        val end=from.withDayOfMonth(from.lengthOfMonth())
        var d=if(includeToday)from else from.plusDays(1);var n=0
        while(!d.isAfter(end)){if(isRegularTradingDay(d))n++;d=d.plusDays(1)}
        return n
    }

    fun sessionOpen(date:LocalDate):ZonedDateTime=date.atTime(regularOpen).atZone(zone)
    fun sessionClose(date:LocalDate):ZonedDateTime=date.atTime(regularClose).atZone(zone)

    fun scheduledHorizon(start:ZonedDateTime,minutes:Int):ZonedDateTime{
        require(minutes>0)
        var remaining=minutes.toLong()
        var cursor=start.withZoneSameInstant(zone)
        if(!isRegularTradingDay(cursor.toLocalDate())||cursor.toLocalTime()>=regularClose){
            cursor=sessionOpen(nextTradingDay(cursor.toLocalDate()))
        }else if(cursor.toLocalTime()<regularOpen){
            cursor=sessionOpen(cursor.toLocalDate())
        }
        while(true){
            val close=sessionClose(cursor.toLocalDate())
            val available=Duration.between(cursor,close).toMinutes().coerceAtLeast(0)
            if(remaining<=available)return cursor.plusMinutes(remaining)
            remaining-=available
            cursor=sessionOpen(nextTradingDay(cursor.toLocalDate()))
        }
    }

    fun isOpen(now:ZonedDateTime):Boolean{
        val z=now.withZoneSameInstant(zone)
        return isRegularTradingDay(z.toLocalDate())&&!z.toLocalTime().isBefore(regularOpen)&&!z.toLocalTime().isAfter(regularClose)
    }
}
''',encoding="utf-8")
print("NseTradingCalendar.kt created")

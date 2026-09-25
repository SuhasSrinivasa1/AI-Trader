package com.suhas.globaledgeai.domain.engine

import java.time.*

class NseTradingCalendar {
    companion object {
        const val VERSION="NSE-EQ-2026-v1"
        val IST:ZoneId=ZoneId.of("Asia/Kolkata")
    }

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

    fun isRegularSessionDay(date:LocalDate):Boolean =
        date.year==2026 &&
            date.dayOfWeek !in setOf(DayOfWeek.SATURDAY,DayOfWeek.SUNDAY) &&
            date !in holidays

    fun isRegularSessionOpen(now:ZonedDateTime=ZonedDateTime.now(IST)):Boolean =
        isRegularSessionDay(now.toLocalDate()) &&
            !now.toLocalTime().isBefore(LocalTime.of(9,15)) &&
            !now.toLocalTime().isAfter(LocalTime.of(15,30))

    fun nextRegularSession(from:LocalDate):LocalDate{
        var d=from.plusDays(1)
        repeat(370){
            if(isRegularSessionDay(d))return d
            d=d.plusDays(1)
        }
        return d
    }

    fun currentOrNextRegularSession(now:ZonedDateTime=ZonedDateTime.now(IST)):LocalDate{
        val d=now.toLocalDate()
        if(isRegularSessionDay(d)&&now.toLocalTime()<LocalTime.of(15,30))return d
        return nextRegularSession(d)
    }

    fun remainingRegularSessions(from:LocalDate,toInclusive:LocalDate):Int{
        if(toInclusive<from)return 0
        var d=from;var n=0
        while(!d.isAfter(toInclusive)){if(isRegularSessionDay(d))n++;d=d.plusDays(1)}
        return n
    }

    fun scheduledHorizon(openedAt:Long,minutes:Int=60):Long{
        val z=Instant.ofEpochMilli(openedAt).atZone(IST)
        val target=z.plusMinutes(minutes.toLong())
        val close=z.toLocalDate().atTime(15,30).atZone(IST)
        if(isRegularSessionDay(z.toLocalDate())&&target.isBefore(close))return target.toInstant().toEpochMilli()
        val next=if(isRegularSessionDay(z.toLocalDate())&&z.toLocalTime()<LocalTime.of(15,30))z.toLocalDate() else nextRegularSession(z.toLocalDate())
        return next.atTime(15,30).atZone(IST).toInstant().toEpochMilli()
    }

    fun sessionWindow(date:LocalDate):Pair<ZonedDateTime,ZonedDateTime> =
        date.atTime(9,15).atZone(IST) to date.atTime(15,30).atZone(IST)
}

package com.suhas.globaledgeai.domain.engine

import java.time.*

object NseTradingCalendar2026 {
    const val VERSION="NSE-CMTR-71775-2026"
    const val SOURCE="NSE/CMTR/71775 dated 12-Dec-2025"
    val muhuratDate:LocalDate=LocalDate.of(2026,11,8)

    private val holidays=linkedMapOf(
        LocalDate.of(2026,1,26) to "Republic Day",
        LocalDate.of(2026,3,3) to "Holi",
        LocalDate.of(2026,3,26) to "Shri Ram Navami",
        LocalDate.of(2026,3,31) to "Shri Mahavir Jayanti",
        LocalDate.of(2026,4,3) to "Good Friday",
        LocalDate.of(2026,4,14) to "Dr. Baba Saheb Ambedkar Jayanti",
        LocalDate.of(2026,5,1) to "Maharashtra Day",
        LocalDate.of(2026,5,28) to "Bakri Id",
        LocalDate.of(2026,6,26) to "Muharram",
        LocalDate.of(2026,9,14) to "Ganesh Chaturthi",
        LocalDate.of(2026,10,2) to "Mahatma Gandhi Jayanti",
        LocalDate.of(2026,10,20) to "Dussehra",
        LocalDate.of(2026,11,10) to "Diwali-Balipratipada",
        LocalDate.of(2026,11,24) to "Prakash Gurpurb Sri Guru Nanak Dev",
        LocalDate.of(2026,12,25) to "Christmas"
    )

    fun holidayName(date:LocalDate):String?=holidays[date]
    fun isRegularSession(date:LocalDate):Boolean{
        if(date.year!=2026)return date.dayOfWeek !in setOf(DayOfWeek.SATURDAY,DayOfWeek.SUNDAY)
        return date.dayOfWeek !in setOf(DayOfWeek.SATURDAY,DayOfWeek.SUNDAY) && date !in holidays
    }
    fun isMuhuratDate(date:LocalDate)=date==muhuratDate

    fun nextRegularSession(after:LocalDate):LocalDate{
        var d=after.plusDays(1);var guard=0
        while(!isRegularSession(d)&&guard++<20)d=d.plusDays(1)
        return d
    }

    fun regularSessionsBetween(startInclusive:LocalDate,endInclusive:LocalDate):Int{
        if(endInclusive<startInclusive)return 0
        var d=startInclusive;var n=0
        while(!d.isAfter(endInclusive)){if(isRegularSession(d))n++;d=d.plusDays(1)}
        return n
    }

    fun remainingWeekSessions(date:LocalDate):Int{
        val end=date.plusDays((DayOfWeek.FRIDAY.value-date.dayOfWeek.value).coerceAtLeast(0).toLong())
        return regularSessionsBetween(date,end)
    }

    fun remainingMonthSessions(date:LocalDate):Int=
        regularSessionsBetween(date,date.withDayOfMonth(date.lengthOfMonth()))

    fun sessionLabel(date:LocalDate):String=when{
        holidayName(date)!=null->"NSE holiday • "+holidayName(date)
        isMuhuratDate(date)->"Muhurat Trading date • special-session timings are not treated as a regular session"
        isRegularSession(date)->"NSE regular session"
        else->"NSE closed • weekend"
    }
}

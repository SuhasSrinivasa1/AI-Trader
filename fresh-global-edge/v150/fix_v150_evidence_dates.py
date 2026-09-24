#!/usr/bin/env python3
from pathlib import Path
import sys
root=Path(sys.argv[1]).resolve()
p=root/"app/src/main/java/com/suhas/ucsentinel/domain/engine/EvidenceFabricEngine.kt"
s=p.read_text(encoding="utf-8")

s=s.replace("import java.time.LocalDate\n","import java.time.*\nimport java.time.format.DateTimeFormatter\nimport java.util.Locale\n")

anchor='''    private fun sha256(v:String)=MessageDigest.getInstance("SHA-256").digest(v.toByteArray()).joinToString(""){"%02x".format(it)}

'''
helper=anchor+'''    private fun discoveredEventTime(text:String,observedAt:Long):Long{
        val zone=ZoneId.of("Asia/Kolkata")
        val candidates=mutableListOf<LocalDate>()
        Regex("""\\b(\\d{1,2})[/-](\\d{1,2})[/-](20\\d{2})\\b""").findAll(text).forEach{m->
            runCatching{LocalDate.of(m.groupValues[3].toInt(),m.groupValues[2].toInt(),m.groupValues[1].toInt())}.getOrNull()?.let{candidates+=it}
        }
        val formats=listOf(
            DateTimeFormatter.ofPattern("d-MMM-yyyy",Locale.ENGLISH),
            DateTimeFormatter.ofPattern("d MMM yyyy",Locale.ENGLISH),
            DateTimeFormatter.ofPattern("MMM d yyyy",Locale.ENGLISH),
            DateTimeFormatter.ofPattern("MMMM d yyyy",Locale.ENGLISH)
        )
        val normalized=text.replace(","," ")
        Regex("""\\b\\d{1,2}[- ]?[A-Za-z]{3,9}[- ]?20\\d{2}\\b|\\b[A-Za-z]{3,9} \\d{1,2} 20\\d{2}\\b""").findAll(normalized).forEach{m->
            val token=m.value.replace(Regex("""\\s+""")," ").trim()
            formats.asSequence().mapNotNull{f->runCatching{LocalDate.parse(token,f)}.getOrNull()}.firstOrNull()?.let{candidates+=it}
        }
        if(candidates.isEmpty())return observedAt
        val observedDate=Instant.ofEpochMilli(observedAt).atZone(zone).toLocalDate()
        val plausible=candidates.filter{!it.isBefore(observedDate.minusDays(7))&&it.isBefore(observedDate.plusYears(1))}
        val eventDate=plausible.minOrNull()?:return observedAt
        return eventDate.atStartOfDay(zone).toInstant().toEpochMilli()
    }

'''
if s.count(anchor)!=1: raise SystemExit("sha anchor mismatch")
s=s.replace(anchor,helper,1)

old='''                observedAt=observedAt,
                effectiveAt=observedAt,
                source=n.source,
'''
new='''                observedAt=observedAt,
                effectiveAt=if(kind==EvidenceKind.EARNINGS_EVENT)discoveredEventTime(n.title+" "+n.summary,observedAt) else observedAt,
                source=n.source,
'''
if s.count(old)!=1: raise SystemExit("effectiveAt anchor mismatch")
s=s.replace(old,new,1)
p.write_text(s,encoding="utf-8")
print("Prospective earnings/event dates parsed when explicitly present in exchange evidence")

package com.suhas.globaledgeai.domain.engine

import com.suhas.globaledgeai.domain.model.*
import java.time.*
import java.time.format.DateTimeFormatter
import java.util.Locale

/**
 * Converts newly observed disclosures/news into point-in-time evidence.
 * It never rewrites an old observedAt timestamp and never fabricates structured values.
 */
class EvidenceIngestionEngine {
    companion object { const val VERSION="PIT-EVIDENCE-2026.09" }
    private val ist=ZoneId.of("Asia/Kolkata")

    data class Ingested(val evidence:List<PointInTimeEvidence>,val events:List<MacroEvent>)

    fun ingest(items:List<NewsItem>,observedAt:Long=System.currentTimeMillis()):Ingested{
        val evidence=mutableListOf<PointInTimeEvidence>()
        val events=mutableListOf<MacroEvent>()
        items.forEach{n->
            val symbol=n.symbol.trim().uppercase()
            val text=(n.title+" "+n.summary).trim()
            val lower=text.lowercase(Locale.ENGLISH)
            val source=n.source.ifBlank{"DISCLOSURE"}
            val revision=(n.url.ifBlank{n.publishedAt+"|"+n.title}).hashCode().toUInt().toString(16)
            fun add(kind:EvidenceKind,field:String,value:String=text.take(1000)){
                val id=(kind.name+"|"+symbol+"|"+field+"|"+revision).hashCode().toUInt().toString(16)
                evidence+=PointInTimeEvidence(id,symbol,kind,field,value,source,observedAt,observedAt,observedAt,revision)
            }

            val fundamental= listOf(
                "financial result","financial results","quarterly result","quarterly results","annual result","annual results",
                "revenue","net profit","ebitda","earnings","audited financial","unaudited financial","profit and loss"
            ).any{it in lower}
            if(fundamental)add(EvidenceKind.FUNDAMENTAL,"DISCLOSED_FUNDAMENTAL")

            val analyst=listOf(
                "analyst meeting","analysts meeting","investor meeting","investors meeting","investor presentation",
                "earnings call","conference call","institutional investor","credit rating","rating action","research report"
            ).any{it in lower}
            if(analyst)add(EvidenceKind.ANALYST,"ANALYST_OR_INVESTOR_EVIDENCE")

            val earningsEvent=listOf(
                "board meeting","financial results","quarterly results","results for the quarter",
                "consider and approve the financial","earnings call"
            ).any{it in lower}
            if(earningsEvent){
                add(EvidenceKind.EARNINGS_EVENT,"EARNINGS_EVENT_DISCOVERED")
                val future=extractFutureDate(text,Instant.ofEpochMilli(observedAt).atZone(ist).toLocalDate())
                if(future!=null&&symbol.isNotBlank()){
                    val at=future.atTime(9,0).atZone(ist).toInstant().toEpochMilli()
                    events+=MacroEvent(
                        id="EARNINGS|"+symbol+"|"+future,
                        label=symbol+" earnings/results event",
                        startAt=future.atStartOfDay(ist).toInstant().toEpochMilli(),
                        decisionAt=at,
                        observedAt=observedAt,
                        source=source+" • "+n.url,
                        riskWindowMinutes=390,
                        symbol=symbol
                    )
                }
            }
        }
        return Ingested(evidence.distinctBy{it.id},events.distinctBy{it.id})
    }

    private fun extractFutureDate(text:String,asOf:LocalDate):LocalDate?{
        val candidates=mutableListOf<LocalDate>()
        val numeric=Regex("""\b([0-3]?\d)[-/\.]([01]?\d)[-/\.](20\d{2})\b""")
        numeric.findAll(text).forEach{m->
            val d=m.groupValues[1].toIntOrNull();val mo=m.groupValues[2].toIntOrNull();val y=m.groupValues[3].toIntOrNull()
            if(d!=null&&mo!=null&&y!=null)runCatching{LocalDate.of(y,mo,d)}.getOrNull()?.let(candidates::add)
        }
        val monthNames="Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?"
        val named1=Regex("""\b([0-3]?\d)\s+($monthNames)[,\s]+(20\d{2})\b""",RegexOption.IGNORE_CASE)
        val named2=Regex("""\b($monthNames)\s+([0-3]?\d)[,\s]+(20\d{2})\b""",RegexOption.IGNORE_CASE)
        val fmts=listOf(DateTimeFormatter.ofPattern("d MMM yyyy",Locale.ENGLISH),DateTimeFormatter.ofPattern("d MMMM yyyy",Locale.ENGLISH))
        named1.findAll(text).forEach{m->
            val raw=m.groupValues[1]+" "+m.groupValues[2]+" "+m.groupValues[3]
            fmts.asSequence().mapNotNull{runCatching{LocalDate.parse(raw,it)}.getOrNull()}.firstOrNull()?.let(candidates::add)
        }
        named2.findAll(text).forEach{m->
            val raw=m.groupValues[2]+" "+m.groupValues[1]+" "+m.groupValues[3]
            fmts.asSequence().mapNotNull{runCatching{LocalDate.parse(raw,it)}.getOrNull()}.firstOrNull()?.let(candidates::add)
        }
        return candidates.filter{!it.isBefore(asOf)}.minOrNull()
    }
}

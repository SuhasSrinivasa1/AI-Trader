#!/usr/bin/env python3
from pathlib import Path
import sys
root=Path(sys.argv[1]).resolve()
remote=root/"app/src/main/java/com/suhas/ucsentinel/data/remote/SectorIntelligenceClient.kt"
remote.parent.mkdir(parents=True,exist_ok=True)
remote.write_text(r'''package com.suhas.globaledgeai.data.remote

import com.suhas.globaledgeai.domain.model.Ohlc
import com.suhas.globaledgeai.domain.model.SectorPeerState
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import okhttp3.Request
import java.time.LocalDate
import java.util.concurrent.TimeUnit

class SectorIntelligenceClient {
    data class IndustryRow(val symbol:String,val company:String,val industry:String,val series:String,val isin:String)
    data class Bundle(val version:String,val rows:Map<String,IndustryRow>)

    private val http=OkHttpClient.Builder().connectTimeout(15,TimeUnit.SECONDS).readTimeout(20,TimeUnit.SECONDS).build()
    private val url="https://www.niftyindices.com/IndexConstituent/ind_nifty500list.csv"
    @Volatile private var cached:Bundle?=null

    suspend fun classifications(force:Boolean=false):Bundle=withContext(Dispatchers.IO){
        if(!force)cached?.let{return@withContext it}
        val request=Request.Builder().url(url).header("User-Agent","Global-Edge-AI-Trader/1.5").get().build()
        http.newCall(request).execute().use{response->
            require(response.isSuccessful){"NIFTY 500 industry map HTTP \${response.code}"}
            val raw=response.body?.string().orEmpty()
            require(raw.isNotBlank()){"Empty NIFTY 500 industry map"}
            parse(raw).also{cached=it}
        }
    }

    private fun parseCsvLine(line:String):List<String>{
        val out=mutableListOf<String>();val b=StringBuilder();var quoted=false;var i=0
        while(i<line.length){
            val ch=line[i]
            when{
                ch=='"'&&quoted&&i+1<line.length&&line[i+1]=='"'->{b.append('"');i++}
                ch=='"'->quoted=!quoted
                ch==','&&!quoted->{out+=b.toString().trim();b.setLength(0)}
                else->b.append(ch)
            }
            i++
        }
        out+=b.toString().trim()
        return out
    }

    private fun parse(raw:String):Bundle{
        val lines=raw.lineSequence().filter{it.isNotBlank()}.toList()
        require(lines.size>1){"NIFTY 500 industry CSV has no data"}
        val header=parseCsvLine(lines.first()).map{it.lowercase().trim()}
        fun idx(vararg names:String)=names.asSequence().map{header.indexOf(it.lowercase())}.firstOrNull{it>=0}?:-1
        val symbolIdx=idx("symbol");val companyIdx=idx("company name","company");val industryIdx=idx("industry");val seriesIdx=idx("series");val isinIdx=idx("isin code","isin")
        require(symbolIdx>=0&&industryIdx>=0){"NIFTY 500 industry CSV schema changed"}
        val rows=linkedMapOf<String,IndustryRow>()
        lines.drop(1).forEach{line->
            val x=parseCsvLine(line)
            fun get(i:Int)=if(i>=0&&i<x.size)x[i].trim() else ""
            val symbol=get(symbolIdx).uppercase();val industry=get(industryIdx)
            if(symbol.isNotBlank()&&industry.isNotBlank())rows[symbol]=IndustryRow(symbol,get(companyIdx),industry,get(seriesIdx),get(isinIdx))
        }
        return Bundle("NIFTY500-INDUSTRY-"+LocalDate.now().toString(),rows)
    }

    fun peerState(symbol:String,bundle:Bundle,ohlc:Map<String,Ohlc>,observedAt:Long=System.currentTimeMillis()):SectorPeerState?{
        val row=bundle.rows[symbol]?:return null
        val peers=bundle.rows.values.filter{it.industry==row.industry}.mapNotNull{x->
            val o=ohlc[x.symbol]?:return@mapNotNull null
            if(o.open<=0.0||o.close<=0.0)return@mapNotNull null
            x.symbol to ((o.close/o.open-1.0)*100.0)
        }
        if(peers.size<2)return null
        val stock=peers.firstOrNull{it.first==symbol}?.second?:return null
        val peerOnly=peers.filterNot{it.first==symbol};if(peerOnly.isEmpty())return null
        val avg=peerOnly.map{it.second}.average();val pos=peerOnly.count{it.second>0.0};val neg=peerOnly.count{it.second<0.0}
        val breadth=pos*100.0/peerOnly.size;val aligned=if(stock>=0.0)breadth>=55.0 else (100.0-breadth)>=55.0
        return SectorPeerState(symbol,row.industry,peerOnly.size,pos,neg,breadth,avg,stock,stock-avg,aligned,bundle.version,observedAt)
    }
}
''',encoding="utf-8")

engine=root/"app/src/main/java/com/suhas/ucsentinel/domain/engine/EvidenceFabricEngine.kt"
engine.parent.mkdir(parents=True,exist_ok=True)
engine.write_text(r'''package com.suhas.globaledgeai.domain.engine

import com.suhas.globaledgeai.domain.model.*
import java.security.MessageDigest
import java.time.LocalDate

object EvidenceFabricEngine {
    const val VERSION="EVIDENCE-FABRIC-2026.09.24"

    private fun sha256(v:String)=MessageDigest.getInstance("SHA-256").digest(v.toByteArray()).joinToString(""){"%02x".format(it)}

    fun classifyNews(items:List<NewsItem>,observedAt:Long=System.currentTimeMillis()):List<PointInTimeEvidence>{
        return items.mapNotNull{n->
            val text=(n.title+" "+n.summary).lowercase()
            val kind=when{
                listOf("financial result","quarterly result","annual result","earnings","profit","revenue","ebitda","margin").any{text.contains(it)}->EvidenceKind.FUNDAMENTAL
                listOf("rating","outlook","upgrade","downgrade","revision","analyst").any{text.contains(it)}->EvidenceKind.ANALYST_RATING
                listOf("board meeting","consider financial results","earnings date").any{text.contains(it)}->EvidenceKind.EARNINGS_EVENT
                listOf("dividend","buyback","merger","acquisition","scheme of arrangement","corporate action").any{text.contains(it)}->EvidenceKind.CORPORATE_EVENT
                else->return@mapNotNull null
            }
            val seed=n.source+"|"+n.symbol+"|"+n.title+"|"+n.publishedAt
            PointInTimeEvidence(
                id="EVID-"+sha256(seed).take(20),
                symbol=n.symbol.trim().uppercase(),
                kind=kind,
                label=n.title.take(180),
                detail=n.summary.take(400),
                observedAt=observedAt,
                effectiveAt=observedAt,
                source=n.source,
                sourceUrl=n.url,
                revisionId=sha256(seed),
                scoreImpact=0.0
            )
        }.distinctBy{it.id}
    }

    fun seedMacroEvents(observedAt:Long=System.currentTimeMillis()):List<MacroRiskEvent> = listOf(
        MacroRiskEvent("RBI-MPC-2026-10","RBI Monetary Policy Committee meeting","2026-10-05","2026-10-07","HIGH","Reserve Bank of India",observedAt=observedAt),
        MacroRiskEvent("RBI-MPC-2026-12","RBI Monetary Policy Committee meeting","2026-12-02","2026-12-04","HIGH","Reserve Bank of India",observedAt=observedAt)
    )

    fun activeMacroRisk(date:LocalDate,events:List<MacroRiskEvent>):List<MacroRiskEvent> =
        events.filter{e->
            val start=runCatching{LocalDate.parse(e.startDateIso)}.getOrNull()?:return@filter false
            val end=runCatching{LocalDate.parse(e.endDateIso)}.getOrNull()?:start
            !date.isBefore(start)&&!date.isAfter(end)
        }

    fun decisionHash(parts:List<String>):String{
        val raw=parts.joinToString("|")
        return sha256(raw)
    }
}
''',encoding="utf-8")
print("SectorIntelligenceClient.kt and EvidenceFabricEngine.kt created")

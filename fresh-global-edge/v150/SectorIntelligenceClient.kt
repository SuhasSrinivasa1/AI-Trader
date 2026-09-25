package com.suhas.globaledgeai.data.remote

import android.content.Context
import com.suhas.globaledgeai.domain.model.SectorClassification
import okhttp3.OkHttpClient
import okhttp3.Request
import java.util.concurrent.TimeUnit

class SectorIntelligenceClient(context:Context){
    companion object {
        const val SOURCE_URL="https://www.niftyindices.com/IndexConstituent/ind_nifty500list.csv"
    }
    private val prefs=context.getSharedPreferences("sector_intelligence_v150",Context.MODE_PRIVATE)
    private val http=OkHttpClient.Builder().connectTimeout(15,TimeUnit.SECONDS).readTimeout(20,TimeUnit.SECONDS).build()

    data class Snapshot(val observedAt:Long,val rows:Map<String,SectorClassification>)

    fun loadCached():Snapshot{
        val at=prefs.getLong("observed_at",0L)
        val raw=prefs.getString("csv",null).orEmpty()
        return Snapshot(at,parse(raw,at))
    }

    fun refresh():Snapshot{
        val req=Request.Builder().url(SOURCE_URL).header("User-Agent","Global-Edge-AI-Trader/1.5").build()
        val raw=http.newCall(req).execute().use{response->
            require(response.isSuccessful){"NIFTY 500 constituent feed HTTP "+response.code}
            response.body?.string().orEmpty()
        }
        require(raw.contains("Symbol",true)&&raw.lines().size>100){"NIFTY 500 constituent feed was not valid CSV"}
        val at=System.currentTimeMillis()
        prefs.edit().putLong("observed_at",at).putString("csv",raw).apply()
        return Snapshot(at,parse(raw,at))
    }

    fun loadOrRefresh(maxAgeMs:Long=24L*60*60*1000):Snapshot{
        val cached=loadCached()
        if(cached.rows.isNotEmpty()&&System.currentTimeMillis()-cached.observedAt<=maxAgeMs)return cached
        return runCatching{refresh()}.getOrElse{cached}
    }

    private fun parse(raw:String,at:Long):Map<String,SectorClassification>{
        if(raw.isBlank())return emptyMap()
        val lines=raw.lineSequence().filter{it.isNotBlank()}.toList()
        if(lines.size<2)return emptyMap()
        val header=csv(lines.first()).map{it.trim().lowercase()}
        val symbolIdx=header.indexOfFirst{it=="symbol"}
        val companyIdx=header.indexOfFirst{it.contains("company")}
        val industryIdx=header.indexOfFirst{it=="industry"||it.contains("industry")}
        if(symbolIdx<0||industryIdx<0)return emptyMap()
        val out=linkedMapOf<String,SectorClassification>()
        lines.drop(1).forEach{line->
            val x=csv(line)
            if(x.size<=maxOf(symbolIdx,industryIdx))return@forEach
            val symbol=x[symbolIdx].trim().uppercase()
            val industry=x[industryIdx].trim()
            val company=x.getOrNull(companyIdx)?.trim().orEmpty()
            if(symbol.isNotBlank()&&industry.isNotBlank())out[symbol]=SectorClassification(symbol,company,industry,at,SOURCE_URL)
        }
        return out
    }

    private fun csv(line:String):List<String>{
        val out=mutableListOf<String>();val b=StringBuilder();var q=false;var i=0
        while(i<line.length){
            val c=line[i]
            if(c=='"'){
                if(q&&i+1<line.length&&line[i+1]=='"'){b.append('"');i++}else q=!q
            }else if(c==','&&!q){out+=b.toString();b.setLength(0)}else b.append(c)
            i++
        }
        out+=b.toString()
        return out
    }
}

package com.suhas.globaledgeai.data.remote

import android.content.Context
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import okhttp3.Request
import java.io.File
import java.util.concurrent.TimeUnit

class SectorIndustryClient(context:Context){
    companion object{
        const val SOURCE_URL="https://www.niftyindices.com/IndexConstituent/ind_nifty500list.csv"
        const val SOURCE_LABEL="NSE Indices • NIFTY 500 Index Constituent"
    }
    private val app=context.applicationContext
    private val cache=File(app.filesDir,"nifty500-industry.csv")
    private val stamp=File(app.filesDir,"nifty500-industry.timestamp")
    private val http=OkHttpClient.Builder().connectTimeout(20,TimeUnit.SECONDS).readTimeout(30,TimeUnit.SECONDS).build()

    suspend fun load(force:Boolean=false):Map<String,String> = withContext(Dispatchers.IO){
        val savedAt=if(stamp.exists())stamp.readText().trim().toLongOrNull()?:0L else 0L
        val age=if(savedAt>0L)System.currentTimeMillis()-savedAt else Long.MAX_VALUE
        if(force||!cache.exists()||age>7L*24*60*60*1000L){
            runCatching{
                val req=Request.Builder().url(SOURCE_URL).header("User-Agent","Global-Edge-AI-Trader/1.5").get().build()
                http.newCall(req).execute().use{r->
                    require(r.isSuccessful){"NIFTY 500 constituent HTTP "+r.code}
                    val body=r.body?.string().orEmpty()
                    require(body.contains("Symbol",true)&&body.length>1000){"Invalid NIFTY 500 constituent response"}
                    cache.writeText(body);stamp.writeText(System.currentTimeMillis().toString())
                }
            }
        }
        if(!cache.exists())return@withContext emptyMap()
        parse(cache.readText())
    }

    private fun parse(raw:String):Map<String,String>{
        val lines=raw.lineSequence().filter{it.isNotBlank()}.toList()
        if(lines.isEmpty())return emptyMap()
        val header=csv(lines.first()).map{it.trim()}
        val symbolIdx=header.indexOfFirst{it.equals("Symbol",true)}
        val industryIdx=header.indexOfFirst{it.equals("Industry",true)}
        if(symbolIdx<0||industryIdx<0)return emptyMap()
        return buildMap{
            lines.drop(1).forEach{line->
                val row=csv(line)
                if(row.size>maxOf(symbolIdx,industryIdx)){
                    val symbol=row[symbolIdx].trim().uppercase()
                    val industry=row[industryIdx].trim()
                    if(symbol.isNotBlank()&&industry.isNotBlank())put(symbol,industry)
                }
            }
        }
    }

    private fun csv(line:String):List<String>{
        val out=mutableListOf<String>();val b=StringBuilder();var quoted=false;var i=0
        while(i<line.length){
            val c=line[i]
            when{
                c=='"'&&quoted&&i+1<line.length&&line[i+1]=='"'->{b.append('"');i++}
                c=='"'->quoted=!quoted
                c==','&&!quoted->{out+=b.toString();b.setLength(0)}
                else->b.append(c)
            }
            i++
        }
        out+=b.toString();return out
    }
}

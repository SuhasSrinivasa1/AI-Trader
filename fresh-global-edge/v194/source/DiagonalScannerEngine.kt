package com.suhas.globaledgeai.domain.engine

import com.suhas.globaledgeai.data.remote.GrowwClient
import com.suhas.globaledgeai.domain.model.*
import java.time.ZoneId
import java.time.ZonedDateTime
import java.time.format.DateTimeFormatter
import kotlin.math.abs
import kotlin.math.max
import kotlin.math.min

/**
 * v1.8.4 Diagonal engine.
 * Finds sustained intraday trends rather than order-book "pressure" predictions.
 * A candidate should move progressively in one direction across the session with
 * high linearity, hourly consistency, VWAP agreement and healthy participation.
 */
class DiagonalScannerEngine(private val growwClient: GrowwClient) {
    companion object { const val MODEL_VERSION="DIAGONAL-V1-1.8.4" }
    private val ist=ZoneId.of("Asia/Kolkata")
    private val fmt=DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss")

    private data class TrendStats(
        val direction:TradeDirection,
        val slopePctPerBar:Double,
        val r2:Double,
        val monotonicPct:Double,
        val netMovePct:Double,
        val vwapAligned:Boolean,
        val rvol:Double
    )

    private fun trendStats(candles:List<Candle>):TrendStats?{
        if(candles.size<6)return null
        val closes=candles.map{it.close}.filter{it.isFinite()&&it>0.0}
        if(closes.size<6)return null
        val base=closes.first()
        val ys=closes.map{(it/base-1.0)*100.0}
        val n=ys.size.toDouble();val xMean=(ys.indices.sum().toDouble()/n);val yMean=ys.average()
        var sxx=0.0;var sxy=0.0;var sst=0.0;var ssr=0.0
        for(i in ys.indices){val dx=i-xMean;val dy=ys[i]-yMean;sxx+=dx*dx;sxy+=dx*dy;sst+=dy*dy}
        val slope=if(sxx>0.0)sxy/sxx else 0.0
        for(i in ys.indices){val pred=yMean+slope*(i-xMean);val e=ys[i]-pred;ssr+=e*e}
        val r2=if(sst>1e-9)(1.0-ssr/sst).coerceIn(0.0,1.0) else 0.0
        val direction=if(slope>=0.0)TradeDirection.LONG else TradeDirection.SHORT
        val hourly=candles.chunked(12).mapNotNull{it.lastOrNull()?.close?.takeIf{p->p.isFinite()&&p>0.0}}
        val directionalSteps=hourly.zipWithNext().count{(a,b)->if(direction==TradeDirection.LONG)b>=a else b<=a}
        val monotonic=if(hourly.size>=2)directionalSteps.toDouble()/(hourly.size-1) else 0.0
        val totalVol=candles.sumOf{it.volume.toDouble()}.coerceAtLeast(1.0)
        val vwap=candles.sumOf{((it.high+it.low+it.close)/3.0)*it.volume}/totalVol
        val vwapAligned=if(direction==TradeDirection.LONG)closes.last()>=vwap else closes.last()<=vwap
        val recentVol=candles.last().volume.toDouble()
        val priorAvg=candles.dropLast(1).takeLast(12).map{it.volume.toDouble()}.average().takeIf{it.isFinite()&&it>0.0}?:1.0
        val rvol=(recentVol/priorAvg).takeIf{it.isFinite()}?:0.0
        return TrendStats(direction,slope,r2,monotonic,(closes.last()/base-1.0)*100.0,vwapAligned,rvol)
    }

    suspend fun scan(
        accessToken:String,
        universe:List<Instrument>,
        newListings:List<ListedSecurity>,
        settings:AppSettings,
        progress:suspend(String)->Unit={}
    ):ScanSummary{
        val started=System.currentTimeMillis()
        val cash=universe.filter{ExecutionQuality.eligibleInstrument(it)}
        val prelim=mutableListOf<Pair<Instrument,Ohlc>>()
        progress("Diagonal: screening ${cash.size} NSE cash stocks")
        cash.chunked(50).forEachIndexed{idx,batch->
            val map=growwClient.getOhlcBatch(accessToken,batch.map{it.tradingSymbol})
            batch.forEach{instrument->
                val o=map[instrument.tradingSymbol]?:return@forEach
                if(o.close<20.0||o.close>20_000.0||o.open<=0.0)return@forEach
                val move=(o.close/o.open-1.0)*100.0
                if(abs(move)>=0.20)prelim+=instrument to o
            }
            progress("Diagonal pre-screen ${((idx+1)*50).coerceAtMost(cash.size)}/${cash.size}")
        }
        val ranked=prelim.sortedByDescending{(_,o)->abs((o.close/o.open-1.0)*100.0)}
        val budget=settings.maxQuotesPerScan.coerceIn(80,120).coerceAtMost(ranked.size)
        val selected=ranked.take(budget)
        val now=ZonedDateTime.now(ist)
        val intraStart=now.toLocalDate().atTime(9,15).format(fmt)
        val intraEnd=now.toLocalDate().atTime(15,30).format(fmt)
        val newMap=newListings.associateBy{it.symbol}
        val candidates=mutableListOf<Candidate>()
        for((index,pair) in selected.withIndex()){
            val instrument=pair.first
            val quote=runCatching{growwClient.getQuote(accessToken,instrument.tradingSymbol)}.getOrNull()?:continue
            if(!ExecutionQuality.discoveryQuote(quote))continue
            val candles=runCatching{growwClient.getHistoricalCandles(accessToken,instrument.tradingSymbol,intraStart,intraEnd,"5minute")}.getOrDefault(emptyList())
            val t=trendStats(candles)?:continue
            if(abs(t.netMovePct)<0.25)continue
            val linearity=t.r2*45.0
            val monotonic=t.monotonicPct*25.0
            val move=min(15.0,abs(t.netMovePct)*4.0)
            val vwap=if(t.vwapAligned)7.0 else 0.0
            val participation=min(8.0,max(0.0,t.rvol-0.8)*5.0)
            val slopeBonus=min(5.0,abs(t.slopePctPerBar)*30.0)
            val score=(linearity+monotonic+move+vwap+participation+slopeBonus).coerceIn(0.0,100.0)
            val executionReady=ExecutionQuality.executableQuote(quote)
            val ratio=if(quote.totalSellQuantity<=0L)if(quote.totalBuyQuantity>0)99.0 else 0.0 else quote.totalBuyQuantity.toDouble()/quote.totalSellQuantity
            val signals=listOf(
                SignalResult("DIAG_LINEARITY","Trend linearity","DIAGONAL",t.r2>=0.55,45.0,"R² ${"%.2f".format(t.r2)}"),
                SignalResult("DIAG_HOURLY","Hourly consistency","DIAGONAL",t.monotonicPct>=0.65,25.0,"${"%.0f".format(t.monotonicPct*100)}% directional hourly steps"),
                SignalResult("DIAG_VWAP","VWAP agreement","DIAGONAL",t.vwapAligned,7.0,if(t.vwapAligned)"Price aligned with VWAP trend" else "Price not aligned with VWAP"),
                SignalResult("DIAG_RVOL","Recent volume participation","VOLUME",t.rvol>=1.0,8.0,"Recent RVOL ${"%.2f".format(t.rvol)}x")
            )
            val directionTag=if(t.direction==TradeDirection.LONG)"DIAGONAL_UP" else "DIAGONAL_DOWN"
            val confidence=when{score>=88->ConfidenceBand.VERY_HIGH;score>=78->ConfidenceBand.HIGH;score>=68->ConfidenceBand.MEDIUM;else->ConfidenceBand.LOW}
            candidates+=Candidate(
                symbol=instrument.tradingSymbol,companyName=instrument.name,
                kind=if(newMap.containsKey(instrument.tradingSymbol))CandidateKind.POST_LISTING else CandidateKind.SEASONED,
                section=ScannerSection.DEMAND_SQUEEZE,price=quote.lastPrice,upperCircuit=quote.upperCircuit,
                dayChangePercent=quote.dayChangePercent,score=score,confidence=confidence,
                passedSignals=signals.count{it.passed},totalSignals=signals.size,buySellRatio=ratio,volumeRatio=t.rvol,
                consecutiveCircuitLikeDays=0,signals=signals,
                activeStrategies=buildList{add(directionTag);add("DIAGONAL_RESEARCH");if(executionReady&&score>=settings.demandMinScore)add("DIAGONAL_STRONG")},
                generatedAt=System.currentTimeMillis(),modelVersion=MODEL_VERSION,predictionHorizonHours=6,
                targetMovePct=(0.6+abs(t.netMovePct)*0.25).coerceIn(0.6,3.0),
                setupScore=t.r2*100.0,accelerationScore=t.monotonicPct*100.0,microstructureScore=t.rvol*50.0
            )
            progress("Diagonal ${index+1}/${selected.size}: ${instrument.tradingSymbol}")
        }
        val up=candidates.filter{"DIAGONAL_UP" in it.activeStrategies}.sortedByDescending{it.score}.take(10)
        val down=candidates.filter{"DIAGONAL_DOWN" in it.activeStrategies}.sortedByDescending{it.score}.take(10)
        val final=(up+down).sortedByDescending{it.score}
        return ScanSummary(
            section=ScannerSection.DEMAND_SQUEEZE,startedAt=started,completedAt=System.currentTimeMillis(),
            universeCount=cash.size,preliminaryCount=ranked.size,quotedCount=selected.size,candidates=final,
            newListingsScanned=newListings.size,
            message="DIAGONAL • full ${cash.size} • prelim ${ranked.size} • deep ${selected.size} • UP ${up.size} • DOWN ${down.size} • model $MODEL_VERSION"
        )
    }
}

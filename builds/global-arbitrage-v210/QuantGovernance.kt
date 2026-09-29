package com.suhas.globaledgeai.ui

import com.suhas.globaledgeai.domain.model.StrategyRecommendation
import com.suhas.globaledgeai.domain.model.StrategyRecommendationStatus
import kotlin.math.abs
import kotlin.math.max
import kotlin.math.min

object QuantGovernance {
    data class ComboStat(
        val label:String,
        val samples:Int,
        val wins:Int,
        val accuracyPct:Double,
        val avgReturnPct:Double,
        val expectancyPct:Double,
        val maxDrawdownPct:Double,
        val recentAvgPct:Double,
        val status:String
    )

    data class HedgeShadow(
        val unhedgedPnl:Double,
        val hedgedPnl:Double,
        val hedgeCost:Double,
        val hedgeBenefit:Double,
        val averageHedgeRatio:Double,
        val observations:Int
    )

    fun shadowPnl(rows:List<StrategyRecommendation>,capital:Double):Double{
        if(rows.isEmpty()||capital<=0.0)return 0.0
        val allocation=min(150_000.0,capital/max(1,min(3,rows.size)))
        return rows.sumOf{r->
            val gross=allocation*(r.returnPct/100.0)
            val executionReserve=allocation*0.0012
            gross-executionReserve
        }
    }

    fun arbitrageRows(rows:List<StrategyRecommendation>):List<StrategyRecommendation>{
        val keys=listOf("arbitrage","parity","basis","calendar","pair","relative value","relative-value","synthetic future","stat arb")
        return rows.filter{r->
            val text=(r.setup.strategyName+" "+r.setup.handbookCombination+" "+r.setup.handbookPattern+" "+r.setup.evidence).lowercase()
            keys.any{text.contains(it)}
        }
    }

    fun dynamicHedgeRatio(score:Double,priorWinRatePct:Double?,recentAvgPct:Double?):Double{
        var ratio=0.35
        when{
            score>=90.0->ratio-=0.17
            score>=84.0->ratio-=0.10
            score<72.0->ratio+=0.15
            score<78.0->ratio+=0.08
        }
        priorWinRatePct?.let{
            if(it<42.0)ratio+=0.15
            else if(it<50.0)ratio+=0.08
            else if(it>=70.0)ratio-=0.07
        }
        recentAvgPct?.let{
            if(it<0.0)ratio+=0.08
            else if(it>0.8)ratio-=0.05
        }
        return ratio.coerceIn(0.10,0.80)
    }

    fun hedgeShadow(rows:List<StrategyRecommendation>,capital:Double):HedgeShadow{
        if(rows.isEmpty()||capital<=0.0)return HedgeShadow(0.0,0.0,0.0,0.0,0.0,0)
        val sorted=rows.sortedBy{it.openedAt}
        val allocation=min(150_000.0,capital/3.0).coerceAtLeast(10_000.0)
        var unhedged=0.0
        var hedged=0.0
        var costs=0.0
        var ratios=0.0
        val prior=mutableListOf<StrategyRecommendation>()
        sorted.forEach{r->
            val lookback=prior.takeLast(20)
            val completed=lookback.filter{it.status==StrategyRecommendationStatus.WIN||it.status==StrategyRecommendationStatus.LOSS}
            val winRate=if(completed.size>=5)completed.count{it.status==StrategyRecommendationStatus.WIN}*100.0/completed.size else null
            val recentAvg=if(completed.size>=5)completed.map{it.returnPct}.average() else null
            val ratio=dynamicHedgeRatio(r.setup.score,winRate,recentAvg)
            val raw=allocation*(r.returnPct/100.0)
            // Shadow-only linear hedge model: opposite exposure offsets ratio% of the directional move.
            // A conservative 8 bps round-trip reserve is charged to the hedged notional.
            val cost=allocation*ratio*0.0008
            val hedgeLeg=-raw*ratio
            unhedged+=raw
            hedged+=raw+hedgeLeg-cost
            costs+=cost
            ratios+=ratio
            prior+=r
        }
        return HedgeShadow(unhedged,hedged,costs,hedged-unhedged,ratios/sorted.size,sorted.size)
    }

    fun combinationStats(rows:List<StrategyRecommendation>):List<ComboStat>{
        val done=rows.filter{it.status==StrategyRecommendationStatus.WIN||it.status==StrategyRecommendationStatus.LOSS}
        return done.groupBy{r->
            r.setup.handbookCombination.trim().ifBlank{r.setup.strategyName.trim().ifBlank{r.setup.strategyId}}
        }.map{(label,group)->
            val ordered=group.sortedBy{it.closedAt}
            val wins=ordered.count{it.status==StrategyRecommendationStatus.WIN}
            val accuracy=if(ordered.isEmpty())0.0 else wins*100.0/ordered.size
            val avg=if(ordered.isEmpty())0.0 else ordered.map{it.returnPct}.average()
            var equity=0.0
            var peak=0.0
            var maxDd=0.0
            ordered.forEach{r->
                equity+=r.returnPct
                peak=max(peak,equity)
                maxDd=max(maxDd,abs(min(0.0,equity-peak)))
            }
            val recent=ordered.takeLast(min(10,ordered.size))
            val recentAvg=if(recent.isEmpty())0.0 else recent.map{it.returnPct}.average()
            val status=when{
                ordered.size>=30&&accuracy>=60.0&&avg>0.0&&recentAvg>0.0&&maxDd<=12.0->"CHAMPION"
                ordered.size>=12&&avg>0.0&&recentAvg>=0.0->"CHALLENGER"
                ordered.size>=10&&avg<=0.0->"PROBATION"
                else->"LEARNING"
            }
            ComboStat(label,ordered.size,wins,accuracy,avg,avg,maxDd,recentAvg,status)
        }.sortedWith(compareBy<ComboStat>{when(it.status){"CHAMPION"->0;"CHALLENGER"->1;"LEARNING"->2;else->3}}.thenByDescending{it.expectancyPct}.thenByDescending{it.samples})
    }

    fun governanceText(rows:List<StrategyRecommendation>,capital:Double):String=buildString{
        val combos=combinationStats(rows)
        val hedge=hedgeShadow(rows,capital)
        appendLine("=== QUANT GOVERNANCE v2.1 ===")
        appendLine("Closed observations: "+rows.size)
        appendLine("Combination champions: "+combos.count{it.status=="CHAMPION"})
        appendLine("Combination challengers: "+combos.count{it.status=="CHALLENGER"})
        combos.take(40).forEach{
            appendLine("${it.status} | ${it.label} | n=${it.samples} | win=${"%.1f".format(it.accuracyPct)}% | avg=${"%+.3f".format(it.avgReturnPct)}% | maxDD=${"%.2f".format(it.maxDrawdownPct)}% | recent=${"%+.3f".format(it.recentAvgPct)}%")
        }
        appendLine("Hedge shadow observations: "+hedge.observations)
        appendLine("Hedge shadow average ratio: "+("%.1f".format(hedge.averageHedgeRatio*100))+"%")
        appendLine("Hedge shadow cost reserve: "+("%.2f".format(hedge.hedgeCost)))
        appendLine("Hedge shadow economic benefit: "+("%+.2f".format(hedge.hedgeBenefit)))
    }
}

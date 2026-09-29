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

    data class HedgePolicyStat(
        val name:String,val observations:Int,val hedgedPnl:Double,val hedgeCost:Double,
        val maxDrawdown:Double,val drawdownReduction:Double,val avgHedgeRatio:Double,
        val utility:Double,val status:String
    )

    data class EngineChampion(
        val engine:String,val label:String,val samples:Int,val metric:String,val status:String
    )

    data class MetaAllocation(
        val arbitragePct:Int,val hedgingPct:Int,val directionalPct:Int,val rationale:String
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


    fun directionalRows(rows:List<StrategyRecommendation>):List<StrategyRecommendation>{
        val arbIds=arbitrageRows(rows).map{it.id}.toSet()
        return rows.filter{it.id !in arbIds}
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


    private fun pnlDrawdown(pnls:List<Double>):Double{
        var equity=0.0
        var peak=0.0
        var dd=0.0
        pnls.forEach{p->
            equity+=p
            peak=max(peak,equity)
            dd=max(dd,peak-equity)
        }
        return dd
    }

    private fun policyRatio(name:String,r:StrategyRecommendation,prior:List<StrategyRecommendation>):Double=
        when(name){
            "Conservative 25%"->0.25
            "Balanced 45%"->0.45
            "Defensive 65%"->0.65
            else->{
                val recent=prior.takeLast(20)
                val wr=if(recent.size>=5)recent.count{it.status==StrategyRecommendationStatus.WIN}*100.0/recent.size else null
                val avg=if(recent.size>=5)recent.map{it.returnPct}.average() else null
                dynamicHedgeRatio(r.setup.score,wr,avg)
            }
        }

    fun hedgePolicyStats(rows:List<StrategyRecommendation>,capital:Double):List<HedgePolicyStat>{
        val done=rows.filter{it.status==StrategyRecommendationStatus.WIN||it.status==StrategyRecommendationStatus.LOSS}.sortedBy{it.openedAt}
        if(done.isEmpty()||capital<=0.0)return emptyList()
        val allocation=min(150_000.0,capital/3.0).coerceAtLeast(10_000.0)
        val raw=done.map{allocation*(it.returnPct/100.0)}
        val rawDd=pnlDrawdown(raw)
        return listOf("Conservative 25%","Balanced 45%","Defensive 65%","Profit-Lock Adaptive").map{name->
            val prior=mutableListOf<StrategyRecommendation>()
            val pnls=mutableListOf<Double>()
            var costs=0.0
            var ratios=0.0
            done.forEachIndexed{i,r->
                val hr=policyRatio(name,r,prior)
                val cost=allocation*hr*0.0008
                pnls+=raw[i]*(1.0-hr)-cost
                costs+=cost
                ratios+=hr
                prior+=r
            }
            val pnl=pnls.sum()
            val dd=pnlDrawdown(pnls)
            val cut=rawDd-dd
            val utility=pnl+cut*0.70-costs*0.10
            HedgePolicyStat(name,done.size,pnl,costs,dd,cut,ratios/done.size,utility,"LEARNING")
        }.sortedByDescending{it.utility}.mapIndexed{i,x->
            x.copy(status=when{
                x.observations>=30&&i==0&&x.utility>0.0->"CHAMPION"
                x.observations>=12&&i<=1->"CHALLENGER"
                x.utility<0.0&&x.observations>=10->"PROBATION"
                else->"LEARNING"
            })
        }
    }

    fun engineChampions(rows:List<StrategyRecommendation>,capital:Double):List<EngineChampion>{
        val arb=combinationStats(arbitrageRows(rows)).firstOrNull()
        val dir=combinationStats(directionalRows(rows)).firstOrNull()
        val hedge=hedgePolicyStats(directionalRows(rows),capital).firstOrNull()
        return listOf(
            EngineChampion("ARBITRAGE",arb?.label?:"No qualified relative-value evidence",arb?.samples?:0,
                arb?.let{"win ${"%.1f".format(it.accuracyPct)}% • avg ${"%+.2f".format(it.avgReturnPct)}%"}?:"Awaiting F&O parity/basis observations",arb?.status?:"LEARNING"),
            EngineChampion("HEDGING",hedge?.name?:"Adaptive hedge learner",hedge?.observations?:0,
                hedge?.let{"utility ₹${"%,.0f".format(it.utility)} • DD cut ₹${"%,.0f".format(it.drawdownReduction)}"}?:"Awaiting completed directional observations",hedge?.status?:"LEARNING"),
            EngineChampion("DIRECTIONAL F&O",dir?.label?:"No qualified directional combination",dir?.samples?:0,
                dir?.let{"win ${"%.1f".format(it.accuracyPct)}% • avg ${"%+.2f".format(it.avgReturnPct)}%"}?:"Awaiting directional observations",dir?.status?:"LEARNING")
        )
    }

    fun metaAllocation(rows:List<StrategyRecommendation>,capital:Double):MetaAllocation{
        val arb=combinationStats(arbitrageRows(rows)).firstOrNull()
        val dir=combinationStats(directionalRows(rows)).firstOrNull()
        val hedge=hedgePolicyStats(directionalRows(rows),capital).firstOrNull()
        var hedgePct=20
        if(hedge!=null&&hedge.drawdownReduction>0.0)hedgePct=25
        if(hedge?.status=="CHAMPION")hedgePct=30
        val remaining=100-hedgePct
        val arbScore=(arb?.expectancyPct?:0.0).coerceAtLeast(0.0)+if(arb?.status=="CHAMPION")1.0 else 0.0
        val dirScore=(dir?.expectancyPct?:0.0).coerceAtLeast(0.0)+if(dir?.status=="CHAMPION")1.0 else 0.0
        val arbPct=when{
            arb==null||arb.samples<10->min(15,remaining)
            arbScore+dirScore<=0.0->remaining/2
            else->((remaining*arbScore/(arbScore+dirScore)).toInt()).coerceIn(15,remaining-15)
        }
        val dirPct=remaining-arbPct
        val why=if(arb==null||arb.samples<10)
            "Arbitrage has limited measured evidence, so directional shadow gets more capital while hedge reserve stays protected."
        else
            "Allocation follows positive expectancy with a hedge reserve and Champion bonus."
        return MetaAllocation(arbPct,hedgePct,dirPct,why)
    }

    fun governanceText(rows:List<StrategyRecommendation>,capital:Double):String=buildString{
        val combos=combinationStats(rows)
        val hedge=hedgeShadow(rows,capital)
        appendLine("=== QUANT GOVERNANCE v2.2 ===")
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

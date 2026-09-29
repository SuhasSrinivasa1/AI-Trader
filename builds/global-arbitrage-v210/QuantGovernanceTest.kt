package com.suhas.globaledgeai

import com.suhas.globaledgeai.domain.model.*
import com.suhas.globaledgeai.ui.QuantGovernance
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class QuantGovernanceTest {
    private fun row(i:Int,win:Boolean,combo:String="VWAP + RVOL + OI"):StrategyRecommendation{
        val setup=StrategySetup(
            symbol="TEST",companyName="Test",strategyId="combo",strategyName="Combo",
            direction=TradeDirection.LONG,score=82.0,entryPrice=100.0,targetPct=1.0,stopPct=0.8,
            evidence="test",generatedAt=i.toLong(),handbookCombination=combo
        )
        return StrategyRecommendation(
            id="r$i",setup=setup,openedAt=i.toLong(),lastSeenAt=i.toLong(),lastPrice=if(win)101.0 else 99.5,
            closedAt=(i+1).toLong(),exitPrice=if(win)101.0 else 99.5,
            status=if(win)StrategyRecommendationStatus.WIN else StrategyRecommendationStatus.LOSS,
            returnPct=if(win)1.0 else -0.5
        )
    }

    @Test fun hedgeRatioRisesWhenPriorQualityIsWeak(){
        val strong=QuantGovernance.dynamicHedgeRatio(90.0,75.0,1.0)
        val weak=QuantGovernance.dynamicHedgeRatio(70.0,35.0,-0.5)
        assertTrue(weak>strong)
        assertTrue(strong in 0.10..0.80)
        assertTrue(weak in 0.10..0.80)
    }

    @Test fun profitableRepeatedCombinationCanBecomeChampion(){
        val rows=(0 until 30).map{i->row(i,win=i%5!=0)}
        val stat=QuantGovernance.combinationStats(rows).single()
        assertEquals("CHAMPION",stat.status)
        assertTrue(stat.accuracyPct>=60.0)
        assertTrue(stat.avgReturnPct>0.0)
    }

    @Test fun weakCombinationDoesNotBecomeChampion(){
        val rows=(0 until 30).map{i->row(i,win=i%3==0,combo="Weak combo")}
        val stat=QuantGovernance.combinationStats(rows).single()
        assertTrue(stat.status!="CHAMPION")
    }
}

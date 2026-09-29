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
    @Test fun threeEngineChampionsAreAlwaysRepresented(){
        val rows=(0 until 36).map{i->row(i,win=i%4!=0)}
        val engines=QuantGovernance.engineChampions(rows,500_000.0)
        assertEquals(3,engines.size)
        assertTrue(engines.map{it.engine}.containsAll(listOf("ARBITRAGE","HEDGING","DIRECTIONAL F&O")))
    }

    @Test fun metaAllocationAlwaysSumsToOneHundred(){
        val rows=(0 until 36).map{i->row(i,win=i%4!=0)}
        val meta=QuantGovernance.metaAllocation(rows,500_000.0)
        assertEquals(100,meta.arbitragePct+meta.hedgingPct+meta.directionalPct)
        assertTrue(meta.hedgingPct>=20)
    }

    @Test fun directionalRowsExcludeTaggedArbitrageRows(){
        val normal=row(1,true,"VWAP + RVOL + OI")
        val arb=row(2,true,"cash futures basis arbitrage")
        val rows=listOf(normal,arb)
        assertEquals(1,QuantGovernance.arbitrageRows(rows).size)
        assertEquals(1,QuantGovernance.directionalRows(rows).size)
        assertEquals(normal.id,QuantGovernance.directionalRows(rows).single().id)
    }

}

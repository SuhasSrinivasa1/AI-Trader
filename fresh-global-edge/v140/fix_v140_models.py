#!/usr/bin/env python3
from pathlib import Path
import sys
root=Path(sys.argv[1]).resolve()
p=root/"app/src/main/java/com/suhas/ucsentinel/domain/model/Models.kt"
s=p.read_text(encoding="utf-8")
def rep(old,new,label):
    global s
    n=s.count(old)
    if n!=1: raise SystemExit(f"{label}: expected 1 found {n}")
    s=s.replace(old,new,1)

rep("enum class StrategyStatus { CHAMPION, ACTIVE, CHALLENGER, PROBATION }",
    "enum class StrategyStatus { CHAMPION, ACTIVE, CHALLENGER, PROBATION, SUSPENDED }","strategy status")

rep('''data class StrategySetup(
    val symbol:String,val companyName:String,val strategyId:String,val strategyName:String,val direction:TradeDirection,
    val score:Double,val entryPrice:Double,val targetPct:Double,val stopPct:Double,val evidence:String,
    val listingAgeDays:Long?=null,val generatedAt:Long=System.currentTimeMillis()
)''',
'''data class StrategySetup(
    val symbol:String,val companyName:String,val strategyId:String,val strategyName:String,val direction:TradeDirection,
    val score:Double,val entryPrice:Double,val targetPct:Double,val stopPct:Double,val evidence:String,
    val listingAgeDays:Long?=null,val generatedAt:Long=System.currentTimeMillis(),
    val researchSignature:String="",val handbookQualityPct:Double=0.0,val handbookPattern:String="",val handbookCombination:String=""
)''',"strategy setup research metadata")

rep('''data class StrategyTournamentSummary(
    val generatedAt:Long,val universeCount:Int,val strategiesRun:Int,val symbolsEnriched:Int,
    val topSetups:List<StrategySetup>,val activeStrategies:List<TradingStrategyDefinition>,
    val performances:List<StrategyPerformance>,val catalogVersion:String,val message:String
)''',
'''data class StrategyTournamentSummary(
    val generatedAt:Long,val universeCount:Int,val strategiesRun:Int,val symbolsEnriched:Int,
    val topSetups:List<StrategySetup>,val activeStrategies:List<TradingStrategyDefinition>,
    val performances:List<StrategyPerformance>,val catalogVersion:String,val message:String,
    val championInsights:List<String> = emptyList(),val rejectedJournalCount:Int=0,val handbookVersion:String=""
)''',"tournament research fields")

p.write_text(s,encoding="utf-8")
print("v1.4.0 research model fields applied")

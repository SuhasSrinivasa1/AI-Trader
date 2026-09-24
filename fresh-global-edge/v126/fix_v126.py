#!/usr/bin/env python3
from pathlib import Path
import re,sys
root=Path(sys.argv[1]).resolve()

def rw(p): return (root/p).read_text(encoding="utf-8")
def wr(p,s): (root/p).write_text(s,encoding="utf-8")
def rep(s,old,new,label,count=1):
    n=s.count(old)
    if n!=count: raise SystemExit(f"{label}: expected {count}, found {n}")
    return s.replace(old,new,count)

# version
p="app/build.gradle.kts";s=rw(p)
s=rep(s,"versionCode = 125","versionCode = 126","versionCode")
s=rep(s,'versionName = "1.2.5"','versionName = "1.2.6"',"versionName")
wr(p,s)

# Hide the Pre-Pressure section from main navigation. The engine remains internal context
# for Strategy/Global learning so this does not disturb the working recommendation stack.
p="app/src/main/java/com/suhas/ucsentinel/ui/AppNavigation.kt";s=rw(p)
s=s.replace('    PRESSURE("Pressure",Icons.Default.Bolt),\n','',1)
s=s.replace('            MainTab.PRESSURE->PressureCompactScreen(state,vm,padding)\n','',1)
wr(p,s)

# PRE-UC discovery was too strict after changing from "already at UC" recognition to prediction.
# Relax discovery/score floors, but preserve the hard anti-late gate and minimum headroom.
p="app/src/main/java/com/suhas/ucsentinel/domain/engine/AdaptiveRangeEngine.kt";s=rw(p)
s=rep(s,
'        chooseThreshold(base, scores, floor = 66.0, ceiling = 88.0, targetCount = targetCount.coerceIn(1, 5))',
'        chooseThreshold(base, scores, floor = 60.0, ceiling = 84.0, targetCount = targetCount.coerceIn(1, 5))',
"UC adaptive range")
wr(p,s)

p="app/src/main/java/com/suhas/ucsentinel/domain/engine/ScannerEngine.kt";s=rw(p)
s=rep(s,
'                val holdingHigh=belowHighPct<=if(nextSessionMode)2.0 else 1.25\n                val candidate=holdingHigh && (closeFromOpen>=(if(nextSessionMode)0.30 else 0.75) || rangePct>=1.5)',
'                val holdingHigh=belowHighPct<=if(nextSessionMode)2.5 else 1.75\n                val candidate=holdingHigh && (closeFromOpen>=(if(nextSessionMode)0.20 else 0.40) || rangePct>=1.0)',
"PRE-UC preliminary breadth")
s=rep(s,
'            val maxHead=if(nextSessionMode)12.0 else 8.0\n            val minMove=if(nextSessionMode)0.5 else 1.0',
'            val maxHead=if(nextSessionMode)15.0 else 10.0\n            val minMove=if(nextSessionMode)0.20 else 0.40',
"PRE-UC headroom/momentum")
# Keep the late-move rejection exactly in place and add a diagnostic progress message.
s=rep(s,
'            if((quote.upperCircuit>0.0&&quote.lastPrice>=quote.upperCircuit*0.995)||(band>0.0&&progress>=0.85))continue',
'            if((quote.upperCircuit>0.0&&quote.lastPrice>=quote.upperCircuit*0.995)||(band>0.0&&progress>=0.85)){\n                progress("Skipped "+instrument.tradingSymbol+": PRE-UC late gate • band progress "+"%.0f".format(progress*100)+"%")\n                continue\n            }',
"PRE-UC late diagnostic")
wr(p,s)

# UC daily auto-tuning must use the same new PRE-UC score range.
p="app/src/main/java/com/suhas/ucsentinel/data/repository/UCSentinelRepository.kt";s=rw(p)
s=rep(s,
'val ucBase=tune(current.minScore,uc,TradeCallEngine.UPPER_CIRCUIT,66.0,88.0);val prBase=tune(current.demandMinScore,pr,TradeCallEngine.PRESSURE,62.0,86.0)',
'val ucBase=tune(current.minScore,uc,TradeCallEngine.UPPER_CIRCUIT,60.0,84.0);val prBase=tune(current.demandMinScore,pr,TradeCallEngine.PRESSURE,62.0,86.0)',
"UC autotune range")
s=rep(s,
'minScore=(ucBase+ucAutopsy+ucCalibration).coerceIn(66.0,88.0)',
'minScore=(ucBase+ucAutopsy+ucCalibration).coerceIn(60.0,84.0)',
"UC autotune clamp")

# Weekly strategy slate:
# - active strategy selection is frozen for the ISO week;
# - no mid-week demotion after a single day;
# - when the weekly slate is recomputed, a strategy with a proven profitable
#   direction+market-regime pocket is protected from blanket probation.
old='''    private fun activeStrategyDefinitions(settings:AppSettings):Pair<StrategyCatalogClient.Bundle,List<TradingStrategyDefinition>>{
        val bundle=strategyCatalog?:strategyCatalogClient.embedded().also{strategyCatalog=it}
        val perfs=prefs.strategyPerformances(bundle.strategies,settings).associateBy{it.strategyId}
        val champions=bundle.strategies.filter{perfs[it.id]?.status==StrategyStatus.CHAMPION}.sortedByDescending{it.priority}
        val pool=bundle.strategies.filter{it.id !in champions.map{c->c.id}.toSet() && perfs[it.id]?.status!=StrategyStatus.PROBATION}.sortedByDescending{it.priority}
        val need=(settings.strategyActiveCount.coerceIn(20,40)-champions.size).coerceAtLeast(0)
        val weeklyOffset=((LocalDate.now(ist).dayOfYear/7)%maxOf(1,pool.size))
        val rotated=if(pool.isEmpty())emptyList() else (pool.drop(weeklyOffset)+pool.take(weeklyOffset))
        val active=(champions+rotated.take(need)).distinctBy{it.id}.take(settings.strategyActiveCount.coerceIn(20,40))
        return bundle to active
    }
'''
new='''    private fun activeStrategyDefinitions(settings:AppSettings):Pair<StrategyCatalogClient.Bundle,List<TradingStrategyDefinition>>{
        val bundle=strategyCatalog?:strategyCatalogClient.embedded().also{strategyCatalog=it}
        val today=LocalDate.now(ist)
        val wf=java.time.temporal.WeekFields.ISO
        fun weekKey(d:LocalDate)=d.get(wf.weekBasedYear()).toString()+"-W"+d.get(wf.weekOfWeekBasedYear()).toString().padStart(2,'0')
        val thisWeek=weekKey(today)

        // Freeze the active slate for a complete ISO week. A bad Tuesday cannot eject a strategy
        // that may be appropriate for another regime later in the same week.
        val saved=prefs.loadStrategySummary()
        val savedDate=saved?.generatedAt?.takeIf{it>0L}?.let{Instant.ofEpochMilli(it).atZone(ist).toLocalDate()}
        val savedIds=saved?.activeStrategies.orEmpty().map{it.id}.toSet()
        if(savedDate!=null && weekKey(savedDate)==thisWeek && savedIds.isNotEmpty()){
            val frozen=bundle.strategies.filter{it.id in savedIds}
                .sortedBy{savedIds.toList().indexOf(it.id)}
                .take(settings.strategyActiveCount.coerceIn(20,40))
            if(frozen.isNotEmpty())return bundle to frozen
        }

        val perfs=prefs.strategyPerformances(bundle.strategies,settings).associateBy{it.strategyId}

        // Protect strategies that are demonstrably profitable in at least one direction+market-regime
        // pocket. This avoids globally demoting a bearish strategy just because the recent market was bullish,
        // or vice versa. Protection needs multiple autopsied observations.
        val closed=prefs.loadStrategyClosed(2000)
        val byId=closed.associateBy{"STRATEGY|"+it.id}
        val buckets=mutableMapOf<String,MutableList<Pair<Boolean,Double>>>()
        prefs.loadAutopsies(2000).filter{it.engineLabel=="STRATEGY"}.forEach{a->
            val r=byId[a.sourceId]?:return@forEach
            val key=r.setup.strategyId+"|"+r.setup.direction.name+"|"+a.regime.name
            buckets.getOrPut(key){mutableListOf()}+=((r.status==StrategyRecommendationStatus.WIN) to r.returnPct)
        }
        val regimeProtected=buckets.entries.filter{(_,rows)->
            rows.size>=4 && rows.count{it.first}*100.0/rows.size>=50.0 && rows.map{it.second}.average()>0.0
        }.map{it.key.substringBefore("|")}.toSet()

        val champions=bundle.strategies.filter{perfs[it.id]?.status==StrategyStatus.CHAMPION}.sortedByDescending{it.priority}
        val championIds=champions.map{it.id}.toSet()
        val pool=bundle.strategies.filter{
            it.id !in championIds &&
            (perfs[it.id]?.status!=StrategyStatus.PROBATION || it.id in regimeProtected)
        }.sortedByDescending{it.priority}
        val need=(settings.strategyActiveCount.coerceIn(20,40)-champions.size).coerceAtLeast(0)
        val weeklyOffset=((today.get(wf.weekOfWeekBasedYear())-1)%maxOf(1,pool.size))
        val rotated=if(pool.isEmpty())emptyList() else (pool.drop(weeklyOffset)+pool.take(weeklyOffset))
        val active=(champions+rotated.take(need)).distinctBy{it.id}.take(settings.strategyActiveCount.coerceIn(20,40))
        DiagnosticLog.log(appContext,"STRATEGY-WEEKLY","week="+thisWeek+" • active="+active.size+" • champions="+champions.size+" • regime-protected="+regimeProtected.size+" • probation excluded="+bundle.strategies.count{perfs[it.id]?.status==StrategyStatus.PROBATION && it.id !in regimeProtected})
        return bundle to active
    }
'''
s=rep(s,old,new,"weekly strategy selection")
wr(p,s)

# Clarify the strategy header so the user knows the slate is weekly, not 20 new strategies today.
p="app/src/main/java/com/suhas/ucsentinel/ui/CompactMarketScreens.kt";s=rw(p)
s=rep(s,
'        state.strategyTournamentSummary?.message?.takeIf{it.isNotBlank()}?.let{msg->item{Text("Engine • $msg",style=MaterialTheme.typography.labelSmall,color=MaterialTheme.colorScheme.onSurfaceVariant)}}',
'        state.strategyTournamentSummary?.message?.takeIf{it.isNotBlank()}?.let{msg->item{Text("Engine • weekly slate • $msg",style=MaterialTheme.typography.labelSmall,color=MaterialTheme.colorScheme.onSurfaceVariant)}}',
"strategy weekly label")
wr(p,s)

print("Global Edge v1.2.6 weekly-regime + UC recall + UI cleanup applied")

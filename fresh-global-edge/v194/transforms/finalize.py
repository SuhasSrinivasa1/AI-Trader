from pathlib import Path

ROOT=Path("/tmp/v194")

def rw(rel, fn):
    p=ROOT/rel
    s=p.read_text()
    n=fn(s)
    if n==s:
        print("no-op", rel)
    else:
        p.write_text(n)
        print("updated", rel)

def rep(old,new):
    return lambda s: s.replace(old,new)

# Freeze exactly five 3 PM next-day UC names, independent of the ordinary UC live cap.
rw("app/src/main/java/com/suhas/ucsentinel/data/repository/UCSentinelRepository.kt",
   rep('.take(settings.maxFinalCandidates.coerceIn(1,5))', '.take(5)'))

# Global must not interpret Diagonal research as retired Pressure confirmation.
def global_independent(s):
    s=s.replace('        val pressure=lastSavedDualSummary()?.demand?.candidates?.associate{it.symbol to it.score}.orEmpty()\n','')
    s=s.replace('        val diagonalContext=lastSavedDualSummary()?.demand?.candidates?.associate{it.symbol to it.score}.orEmpty()\n','')
    s=s.replace('globalLeadEngine.finalCandidate(m,f,benchmarks[m.benchmarkTicker],q,prior,pressure[m.indianSymbol],settings,now,direction)',
                'globalLeadEngine.finalCandidate(m,f,benchmarks[m.benchmarkTicker],q,prior,null,settings,now,direction)')
    s=s.replace('globalLeadEngine.finalCandidate(m,f,benchmarks[m.benchmarkTicker],q,prior,diagonalContext[m.indianSymbol],settings,now,direction)',
                'globalLeadEngine.finalCandidate(m,f,benchmarks[m.benchmarkTicker],q,prior,null,settings,now,direction)')
    marker='    suspend fun strategyV2EventCount():Int{ensureStrategyLearningV2Migrated();return strategyLearning.eventCount()}\n'
    method='''\n    suspend fun runChallengerShadowResearchOffHours():Int{\n        if(!ensureAutomationAuthentication())return 0\n        val summary=runCatching{scanTradingStrategies(challengerOnly=true)}.getOrNull()?:return 0\n        return summary.topSetups.size\n    }\n'''
    if 'runChallengerShadowResearchOffHours' not in s and marker in s:
        s=s.replace(marker,marker+method)
    return s
rw("app/src/main/java/com/suhas/ucsentinel/data/repository/UCSentinelRepository.kt",global_independent)

# Weekend deep-learning refresh: catalogue + Challenger shadow research.
def nightly(s):
    old='''            val catalog=if(weekend)runCatching{repo.refreshStrategyCatalog(true)}.getOrDefault(0) else 0\n            runCatching{repo.scanUpperCircuitNextSession()}\n'''
    new='''            val catalog=if(weekend)runCatching{repo.refreshStrategyCatalog(true)}.getOrDefault(0) else 0\n            if(weekend)runCatching{repo.runChallengerShadowResearchOffHours()}\n            runCatching{repo.scanUpperCircuitNextSession()}\n'''
    if old in s: s=s.replace(old,new,1)
    return s
rw("app/src/main/java/com/suhas/ucsentinel/worker/NightlyLearningWorker.kt",nightly)

# Pressure is not a production toggle any more; the legacy setting is retained only for schema compatibility.
rw("app/src/main/java/com/suhas/ucsentinel/domain/model/Models.kt",
   rep('val pressureAutoScanEnabled:Boolean=true,val pressureScanIntervalMinutes:Int=5',
       'val pressureAutoScanEnabled:Boolean=false,val pressureScanIntervalMinutes:Int=5'))

# Strategy Lab terminology: mix company fundamentals and market drivers, with evidence-first empty states.
def more(s):
    s=s.replace('Top 10 company fundamentals tracked','Top 10 drivers')
    s=s.replace('val fundamentals=listOf("Revenue growth","EPS / profit growth","ROE","ROCE","Operating-margin trend","Debt / equity","Cash-flow quality","Valuation vs sector","Promoter / institutional ownership change","Earnings / result momentum")',
'''val fundamentals=listOf(
        "Relative volume / volume acceleration",
        "VWAP position / reclaim / hold",
        "EMA / trend structure",
        "Sector relative strength",
        "Breakout / support-resistance distance",
        "Volatility / ATR compression-expansion",
        "Liquidity / spread / depth",
        "Earnings / profit growth",
        "ROE / ROCE / balance-sheet quality",
        "Valuation / ownership context"
    )''')
    s=s.replace('• Learning attribution','• Learning')
    return s
rw("app/src/main/java/com/suhas/ucsentinel/ui/MoreScreen.kt",more)

print("v1.8.4 finalization complete")

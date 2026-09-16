from pathlib import Path
import re, sys
root=Path(sys.argv[1])

def read(rel): return (root/rel).read_text()
def write(rel,s): (root/rel).write_text(s)
def must_replace(s, old, new, label):
    if old not in s:
        raise SystemExit(f'missing needle: {label}')
    return s.replace(old,new,1)

# version bump
p='app/build.gradle.kts'
s=read(p)
s=must_replace(s,'versionCode = 100','versionCode = 101','versionCode')
s=must_replace(s,'versionName = "1.0.0"','versionName = "1.0.1"','versionName')
write(p,s)

# ScanWorker: run full UC + pressure scan on every background heartbeat while market is open.
p='app/src/main/java/com/suhas/ucsentinel/worker/ScanWorker.kt'
s=read(p)
old='''        suspend fun automatedPass(){\n            val nearClose=now>=LocalTime.of(14,30)\n            if(nearClose&&settings.autoScanEnabled){\n                // Dedicated near-close jobs plus the 15-minute heartbeat make the 3 PM audit resilient.\n                val due=forceNearClose||System.currentTimeMillis()-repo.lastNearCloseAutoScanAt()>=12L*60*1000\n                if(due){\n                    repo.scanAll()\n                    repo.markNearCloseAutoScanAt()\n                    repo.markPressureScanAt()\n                }\n            }else if(settings.pressureAutoScanEnabled){\n                val intervalMs=settings.pressureScanIntervalMinutes.coerceIn(15,120).toLong()*60*1000\n                if(System.currentTimeMillis()-repo.lastPressureScanAt()>=intervalMs){\n                    repo.scanDemandOnly()\n                    repo.markPressureScanAt()\n                }\n            }\n            if(settings.strategyTournamentEnabled){\n                val strategyInterval=if(nearClose)15L else 30L\n                if(forceNearClose||System.currentTimeMillis()-repo.lastStrategyScanAt()>=strategyInterval*60*1000){\n                    runCatching{repo.scanTradingStrategies()}\n                }\n            }\n            // Freeze only after the near-close scan attempt, never before it.\n            repo.ensureTodayFreezeAudit(nowZ)\n        }'''
new='''        suspend fun automatedPass(){\n            val nearClose=now>=LocalTime.of(14,30)\n            val nowMs=System.currentTimeMillis()\n\n            // WorkManager's supported periodic minimum is 15 minutes. Every heartbeat now runs\n            // the complete UC + pressure scan, so the Upper Circuit tab no longer depends on\n            // the manual Scan all button. A foreground loop in MainViewModel adds 5-minute\n            // refreshes while the app is open.\n            if(settings.autoScanEnabled){\n                val due=forceNearClose||nowMs-repo.lastPressureScanAt()>=12L*60*1000\n                if(due){\n                    repo.scanAll()\n                    repo.markPressureScanAt(nowMs)\n                    if(nearClose)repo.markNearCloseAutoScanAt(nowMs)\n                }\n            }else if(settings.pressureAutoScanEnabled){\n                val intervalMs=settings.pressureScanIntervalMinutes.coerceIn(15,120).toLong()*60*1000\n                if(nowMs-repo.lastPressureScanAt()>=intervalMs){\n                    repo.scanDemandOnly()\n                    repo.markPressureScanAt(nowMs)\n                }\n            }\n            if(settings.strategyTournamentEnabled){\n                val strategyInterval=if(nearClose)15L else 30L\n                if(forceNearClose||nowMs-repo.lastStrategyScanAt()>=strategyInterval*60*1000){\n                    runCatching{repo.scanTradingStrategies()}\n                }\n            }\n            // Freeze only after the near-close scan attempt, never before it.\n            repo.ensureTodayFreezeAudit(nowZ)\n        }'''
s=must_replace(s,old,new,'ScanWorker automatedPass')
write(p,s)

# MainViewModel: foreground 5-minute auto scan and 15-minute strategy/global refresh.
p='app/src/main/java/com/suhas/ucsentinel/ui/MainViewModel.kt'
s=read(p)
old='''class MainViewModel(private val repo:GlobalEdgeAITraderRepository):ViewModel(){\n    private val _state=MutableStateFlow(buildInitialState())\n    val state:StateFlow<UiState> = _state.asStateFlow()\n    init{'''
new='''class MainViewModel(private val repo:GlobalEdgeAITraderRepository):ViewModel(){\n    private val _state=MutableStateFlow(buildInitialState())\n    val state:StateFlow<UiState> = _state.asStateFlow()\n    private var lastForegroundMarketScanAt=0L\n    private var lastForegroundStrategyScanAt=0L\n    private var lastForegroundGlobalScanAt=0L\n    init{'''
s=must_replace(s,old,new,'MainViewModel fields')
old='''        viewModelScope.launch{\n            while(isActive){\n                delay(30_000L)\n                reliabilityRefresh()\n            }\n        }'''
new='''        viewModelScope.launch{\n            // The process-level WorkManager heartbeat is 15 minutes (Android minimum). While the\n            // app is open, refresh the live market models every 5 minutes and the heavier engines\n            // every 15 minutes without requiring any button press.\n            delay(5_000L)\n            while(isActive){\n                runForegroundAutomation()\n                reliabilityRefresh()\n                delay(30_000L)\n            }\n        }'''
s=must_replace(s,old,new,'MainViewModel init loop')
insert_before='''    private fun buildInitialState():UiState{'''
method='''    private suspend fun runForegroundAutomation(){\n        if(_state.value.busy)return\n        val settings=repo.settings()\n        val session=repo.marketSessionInfo()\n        val now=System.currentTimeMillis()\n\n        // Global lead is cross-time-zone intelligence, so keep it fresh even outside NSE hours.\n        if(settings.globalLeadEnabled && now-lastForegroundGlobalScanAt>=15L*60*1000){\n            lastForegroundGlobalScanAt=now\n            runCatching{repo.scanGlobalLead()}.onSuccess{summary->\n                _state.value=_state.value.copy(globalLeadSummary=summary,lastGlobalLeadScanAt=summary.generatedAt,error=null)\n            }\n        }\n\n        if(!session.isOpen)return\n        if(settings.autoScanEnabled && now-lastForegroundMarketScanAt>=5L*60*1000){\n            lastForegroundMarketScanAt=now\n            runCatching{repo.scanAll()}.onSuccess{dual->\n                repo.markPressureScanAt()\n                _state.value=_state.value.copy(dualSummary=dual,newListings=dual.newListings,status="Automatic market scan updated",error=null)\n            }.onFailure{t->\n                // Do not replace a valid cached scan with a transient network/rate-limit banner.\n                if(repo.lastSavedDualSummary()==null){\n                    _state.value=_state.value.copy(status="Automatic scan will retry",error=t.message?.takeIf{it.isNotBlank()})\n                }\n            }\n        }\n        if(settings.strategyTournamentEnabled && now-lastForegroundStrategyScanAt>=15L*60*1000){\n            lastForegroundStrategyScanAt=now\n            runCatching{repo.scanTradingStrategies()}.onSuccess{summary->\n                _state.value=_state.value.copy(strategyTournamentSummary=summary,lastStrategyScanAt=summary.generatedAt,error=null)\n            }\n        }\n    }\n\n'''
if insert_before not in s: raise SystemExit('missing MainViewModel insert point')
s=s.replace(insert_before,method+insert_before,1)
write(p,s)

# TradingStrategyEngine numeric safety.
p='app/src/main/java/com/suhas/ucsentinel/domain/engine/TradingStrategyEngine.kt'
s=read(p)
s=must_replace(s,'        val c=candles.last();val p=candles[candles.lastIndex-1]\n',
'''        val c=candles.last();val p=candles[candles.lastIndex-1]\n        if(!c.open.isFinite()||!c.high.isFinite()||!c.low.isFinite()||!c.close.isFinite()||c.close<=0.0)return null\n''','strategy candle finite guard')
s=must_replace(s,'        val rvol=c.volume/avgv(20)\n','        val rvol=(c.volume/avgv(20)).takeIf{it.isFinite()}?:0.0\n','rvol')
s=must_replace(s,'        val atr=Indicators.atrPercent(candles,14).coerceAtLeast(0.05)\n','        val atr=(Indicators.atrPercent(candles,14).takeIf{it.isFinite()}?:0.05).coerceAtLeast(0.05)\n','atr')
s=must_replace(s,'        val vwap=session.sumOf{((it.high+it.low+it.close)/3.0)*it.volume}/totalVol\n','        val vwap=(session.sumOf{((it.high+it.low+it.close)/3.0)*it.volume}/totalVol).takeIf{it.isFinite()}?:c.close\n','vwap')
s=must_replace(s,'        fun mk(d:TradeDirection,raw:Number,why:String,target:Double=max(0.5,min(3.0,atr*1.2)),stop:Double=max(0.4,min(2.0,atr*0.9)))=Eval(d,raw.toDouble().coerceIn(0.0,100.0),target,stop,why)\n',
'''        fun mk(d:TradeDirection,raw:Number,why:String,target:Double=max(0.5,min(3.0,atr*1.2)),stop:Double=max(0.4,min(2.0,atr*0.9))):Eval{\n            val safeScore=raw.toDouble().takeIf{it.isFinite()}?.coerceIn(0.0,100.0)?:0.0\n            val safeTarget=target.takeIf{it.isFinite()}?.coerceIn(0.1,20.0)?:1.0\n            val safeStop=stop.takeIf{it.isFinite()}?.coerceIn(0.1,20.0)?:1.0\n            return Eval(d,safeScore,safeTarget,safeStop,why)\n        }\n''','mk safe')
write(p,s)

# AppPreferences: sanitize all persisted market doubles so org.json can never throw "Forbidden numeric value: NaN".
p='app/src/main/java/com/suhas/ucsentinel/data/local/AppPreferences.kt'
s=read(p)
needle='''    private val ist=ZoneId.of("Asia/Kolkata")\n'''
repl='''    private val ist=ZoneId.of("Asia/Kolkata")\n    private fun finite(v:Double):Double=if(v.isFinite())v else 0.0\n    private fun finiteOrNull(v:Double?):Any=v?.takeIf{it.isFinite()}?:JSONObject.NULL\n'''
s=must_replace(s,needle,repl,'finite helpers')
old='''        val setups=JSONArray();summary.topSetups.forEach{x->setups.put(JSONObject().put("symbol",x.symbol).put("companyName",x.companyName).put("strategyId",x.strategyId).put("strategyName",x.strategyName).put("direction",x.direction.name).put("score",x.score).put("entryPrice",x.entryPrice).put("targetPct",x.targetPct).put("stopPct",x.stopPct).put("evidence",x.evidence).put("listingAgeDays",x.listingAgeDays?:-1).put("generatedAt",x.generatedAt))}\n'''
new='''        val setups=JSONArray();summary.topSetups.forEach{x->setups.put(JSONObject().put("symbol",x.symbol).put("companyName",x.companyName).put("strategyId",x.strategyId).put("strategyName",x.strategyName).put("direction",x.direction.name).put("score",finite(x.score)).put("entryPrice",finite(x.entryPrice)).put("targetPct",finite(x.targetPct)).put("stopPct",finite(x.stopPct)).put("evidence",x.evidence).put("listingAgeDays",x.listingAgeDays?:-1).put("generatedAt",x.generatedAt))}\n'''
s=must_replace(s,old,new,'strategy setups persistence')
old='''        val perfs=JSONArray();summary.performances.forEach{x->perfs.put(JSONObject().put("strategyId",x.strategyId).put("name",x.name).put("observations",x.observations).put("wins",x.wins).put("accuracyPct",x.accuracyPct).put("avgReturnPct",x.avgReturnPct).put("expectancyPct",x.expectancyPct).put("maxDrawdownPct",x.maxDrawdownPct).put("confidenceFloorPct",x.confidenceFloorPct).put("status",x.status.name))}\n'''
new='''        val perfs=JSONArray();summary.performances.forEach{x->perfs.put(JSONObject().put("strategyId",x.strategyId).put("name",x.name).put("observations",x.observations).put("wins",x.wins).put("accuracyPct",finite(x.accuracyPct)).put("avgReturnPct",finite(x.avgReturnPct)).put("expectancyPct",finite(x.expectancyPct)).put("maxDrawdownPct",finite(x.maxDrawdownPct)).put("confidenceFloorPct",finite(x.confidenceFloorPct)).put("status",x.status.name))}\n'''
s=must_replace(s,old,new,'strategy perfs persistence')
pat=re.compile(r'    private fun candidateToJson\(c:Candidate,includeSignals:Boolean\):JSONObject\{.*?\}\n',re.S)
m=pat.search(s)
if not m: raise SystemExit('missing candidateToJson')
new='''    private fun candidateToJson(c:Candidate,includeSignals:Boolean):JSONObject{\n        val ids=JSONArray();if(includeSignals)c.signals.filter{it.passed}.forEach{ids.put(it.id)}\n        val strategies=JSONArray();c.activeStrategies.forEach{strategies.put(it)}\n        return JSONObject().put("symbol",c.symbol).put("companyName",c.companyName).put("kind",c.kind.name).put("section",c.section.name)\n            .put("price",finite(c.price)).put("upperCircuit",finite(c.upperCircuit)).put("dayChangePercent",finite(c.dayChangePercent)).put("score",finite(c.score))\n            .put("confidence",c.confidence.name).put("passedSignals",c.passedSignals).put("totalSignals",c.totalSignals)\n            .put("buySellRatio",finite(c.buySellRatio)).put("volumeRatio",finite(c.volumeRatio)).put("consecutiveCircuitLikeDays",c.consecutiveCircuitLikeDays)\n            .put("listingAgeDays",c.listingAgeDays?:-1).put("generatedAt",c.generatedAt).put("predictionPhase",c.predictionPhase?.name?:"")\n            .put("modelVersion",c.modelVersion).put("predictionHorizonHours",c.predictionHorizonHours).put("targetMovePct",finiteOrNull(c.targetMovePct))\n            .put("setupScore",finiteOrNull(c.setupScore)).put("accelerationScore",finiteOrNull(c.accelerationScore)).put("microstructureScore",finiteOrNull(c.microstructureScore))\n            .put("riskPenalty",finiteOrNull(c.riskPenalty)).put("signalIds",ids).put("activeStrategies",strategies)\n    }\n'''
s=s[:m.start()]+new+s[m.end():]
for field in ['relationshipWeight','score','foreignGapPct','foreignDayPct','foreignFromOpenPct','foreignExcessPct','foreignVolumeRatio','foreignCloseLocation','indianPrice','indianOpen','indianFromOpenPct','indianDayPct','indianBuySellRatio','freshnessPct','pressureConfirmationScore','expectedTargetPct']:
    s=s.replace(f'.put("{field}",c.{field})',f'.put("{field}",finite(c.{field}))')
s=s.replace('.put("targetMovePct",targetMovePct?:JSONObject.NULL)', '.put("targetMovePct",finiteOrNull(targetMovePct))')
old='''    fun updateStrategyResult(strategyId:String,name:String,returnPct:Double,win:Boolean){val root='''
new='''    fun updateStrategyResult(strategyId:String,name:String,returnPct:Double,win:Boolean){val safeReturn=finite(returnPct);val root='''
s=must_replace(s,old,new,'updateStrategyResult start')
s=s.replace('val sum=x.optDouble("sumReturn")+returnPct;val equity=x.optDouble("equity",0.0)+returnPct;', 'val sum=x.optDouble("sumReturn")+safeReturn;val equity=x.optDouble("equity",0.0)+safeReturn;',1)
s=s.replace('return v.takeIf{!it.isNaN()}', 'return v.takeIf{it.isFinite()}',1)
write(p,s)

print('Global Edge AI Trader v1.0.1 upgrade applied')

#!/usr/bin/env python3
from __future__ import annotations
from pathlib import Path
import re
import sys

root = Path(sys.argv[1]).resolve()
if not root.exists():
    raise SystemExit(f"source root not found: {root}")

def read(rel: str) -> str:
    return (root / rel).read_text(encoding="utf-8")

def write(rel: str, text: str) -> None:
    (root / rel).write_text(text, encoding="utf-8")

def must_replace(text: str, old: str, new: str, label: str, count: int = 1) -> str:
    actual = text.count(old)
    if actual < count:
        raise SystemExit(f"{label}: expected at least {count} occurrence(s), found {actual}")
    return text.replace(old, new, count)

def replace_class_method(text: str, signature_regex: str, next_signature_regex: str, replacement: str, label: str) -> str:
    pattern = re.compile(rf"(?ms)^    {signature_regex}.*?(?=^    {next_signature_regex})")
    updated, n = pattern.subn(replacement.rstrip() + "\n\n", text, count=1)
    if n != 1:
        raise SystemExit(f"{label}: method replacement count={n}")
    return updated

# Version bump.
gradle_rel = "app/build.gradle.kts"
g = read(gradle_rel)
g = must_replace(g, "versionCode = 121", "versionCode = 122", "versionCode")
g = must_replace(g, 'versionName = "1.2.1"', 'versionName = "1.2.2"', "versionName")
write(gradle_rel, g)

# 1) Harden Groww numeric parsing. Kotlin "NaN".toDoubleOrNull() returns Double.NaN,
# and org.json rejects JSONObject.put(NaN) with "Forbidden numeric value: NaN".
groww_rel = "app/src/main/java/com/suhas/ucsentinel/data/remote/GrowwClient.kt"
t = read(groww_rel)
t = must_replace(
    t,
    "class GrowwClient {\n\n    companion object {",
    """class GrowwClient {

    private fun finiteNumber(value:Double,fallback:Double=0.0):Double =
        if(value.isFinite()) value else fallback

    private fun jsonDouble(obj:JSONObject,name:String,fallback:Double=0.0):Double =
        finiteNumber(obj.optDouble(name,fallback),fallback)

    companion object {""",
    "Groww finite helpers",
)
t = must_replace(
    t,
    'obj.put(parts[0].trim().trim(\'"\'), parts[1].trim().toDoubleOrNull() ?: 0.0)',
    'val parsed=parts[1].trim().toDoubleOrNull();obj.put(parts[0].trim().trim(\'"\'),parsed?.takeIf{it.isFinite()}?:0.0)',
    "loose OHLC NaN guard",
)
t = t.replace('open = obj.optDouble("open", 0.0)', 'open = jsonDouble(obj,"open")')
t = t.replace('high = obj.optDouble("high", 0.0)', 'high = jsonDouble(obj,"high")')
t = t.replace('low = obj.optDouble("low", 0.0)', 'low = jsonDouble(obj,"low")')
t = t.replace('close = obj.optDouble("close", 0.0)', 'close = jsonDouble(obj,"close")')

old_candles = """                add(
                    Candle(
                        epochSeconds = row.optLong(0),
                        open = row.optDouble(1),
                        high = row.optDouble(2),
                        low = row.optDouble(3),
                        close = row.optDouble(4),
                        volume = row.optLong(5)
                    )
                )"""
new_candles = """                val open=finiteNumber(row.optDouble(1))
                val high=finiteNumber(row.optDouble(2))
                val low=finiteNumber(row.optDouble(3))
                val close=finiteNumber(row.optDouble(4))
                if(open<=0.0||high<=0.0||low<=0.0||close<=0.0)continue
                add(
                    Candle(
                        epochSeconds = row.optLong(0),
                        open = open,
                        high = high,
                        low = low,
                        close = close,
                        volume = row.optLong(5).coerceAtLeast(0L)
                    )
                )"""
t = must_replace(t, old_candles, new_candles, "historical candle finite guard")

old_levels = 'add(DepthLevel(x.optDouble("price"), x.optLong("quantity")))'
new_levels = 'val price=jsonDouble(x,"price");if(price>0.0)add(DepthLevel(price,x.optLong("quantity").coerceAtLeast(0L)))'
t = must_replace(t, old_levels, new_levels, "depth finite guard")

quote_repls = {
    'lastPrice = p.optDouble("last_price")':'lastPrice = jsonDouble(p,"last_price")',
    'previousClose = o.optDouble("close")':'previousClose = jsonDouble(o,"close")',
    'dayChangePercent = p.optDouble("day_change_perc")':'dayChangePercent = jsonDouble(p,"day_change_perc")',
    'upperCircuit = p.optDouble("upper_circuit_limit")':'upperCircuit = jsonDouble(p,"upper_circuit_limit")',
    'lowerCircuit = p.optDouble("lower_circuit_limit")':'lowerCircuit = jsonDouble(p,"lower_circuit_limit")',
    'bidPrice = p.optDouble("bid_price")':'bidPrice = jsonDouble(p,"bid_price")',
    'offerPrice = p.optDouble("offer_price")':'offerPrice = jsonDouble(p,"offer_price")',
    'marketCap = p.optDouble("market_cap")':'marketCap = jsonDouble(p,"market_cap")',
    'week52High = p.optDouble("week_52_high")':'week52High = jsonDouble(p,"week_52_high")',
    'week52Low = p.optDouble("week_52_low")':'week52Low = jsonDouble(p,"week_52_low")',
    'open = o.optDouble("open")':'open = jsonDouble(o,"open")',
    'high = o.optDouble("high")':'high = jsonDouble(o,"high")',
    'low = o.optDouble("low")':'low = jsonDouble(o,"low")',
    'close = o.optDouble("close")':'close = jsonDouble(o,"close")',
}
for old, new in quote_repls.items():
    if old in t:
        t = t.replace(old, new)
write(groww_rel, t)

# 2) Harden persistent learning accumulators so a poisoned value can never
# break a live scan or a ledger write.
prefs_rel = "app/src/main/java/com/suhas/ucsentinel/data/local/AppPreferences.kt"
p = read(prefs_rel)
p = must_replace(
    p,
    "    private fun finite(v:Double):Double=if(v.isFinite())v else 0.0\n    private fun finiteOrNull(v:Double?):Any=v?.takeIf{it.isFinite()}?:JSONObject.NULL",
    """    private fun finite(v:Double):Double=if(v.isFinite())v else 0.0
    private fun finiteOrNull(v:Double?):Any=v?.takeIf{it.isFinite()}?:JSONObject.NULL
    private fun storedFinite(j:JSONObject,name:String,default:Double=0.0):Double{
        val v=j.optDouble(name,default)
        return if(v.isFinite())v else default
    }""",
    "preferences finite helpers",
)

p = replace_class_method(
    p,
    r"fun updateStrategyResult\(strategyId:String,name:String,returnPct:Double,win:Boolean\)\{",
    r"fun strategyPerformances\(",
    """    fun updateStrategyResult(strategyId:String,name:String,returnPct:Double,win:Boolean){
        val safeReturn=finite(returnPct)
        val root=runCatching{JSONObject(prefs.getString("strategy_stats","{}")?:"{}")}.getOrElse{JSONObject()}
        val x=root.optJSONObject(strategyId)?:JSONObject()
        val n=x.optInt("observations").coerceAtLeast(0)+1
        val wins=x.optInt("wins").coerceIn(0,n-1)+(if(win)1 else 0)
        val sum=finite(storedFinite(x,"sumReturn")+safeReturn)
        val equity=finite(storedFinite(x,"equity")+safeReturn)
        val peak=maxOf(storedFinite(x,"peak"),equity)
        val dd=minOf(storedFinite(x,"maxDrawdown"),equity-peak)
        x.put("name",name).put("observations",n).put("wins",wins)
            .put("sumReturn",finite(sum)).put("equity",finite(equity))
            .put("peak",finite(peak)).put("maxDrawdown",finite(dd))
        root.put(strategyId,x)
        prefs.edit().putString("strategy_stats",root.toString()).apply()
    }""",
    "updateStrategyResult",
)

p = replace_class_method(
    p,
    r"fun strategyPerformances\(defs:List<TradingStrategyDefinition>,settings:AppSettings\):List<StrategyPerformance>\{",
    r"private fun wilsonLower\(",
    """    fun strategyPerformances(defs:List<TradingStrategyDefinition>,settings:AppSettings):List<StrategyPerformance>{
        val root=runCatching{JSONObject(prefs.getString("strategy_stats","{}")?:"{}")}.getOrElse{JSONObject()}
        return defs.map{d->
            val x=root.optJSONObject(d.id)?:JSONObject()
            val n=x.optInt("observations").coerceAtLeast(0)
            val w=x.optInt("wins").coerceIn(0,n)
            val acc=if(n==0)0.0 else w*100.0/n
            val avg=if(n==0)0.0 else finite(storedFinite(x,"sumReturn")/n)
            val floor=wilsonLower(w,n)*100.0
            val maxDd=kotlin.math.abs(storedFinite(x,"maxDrawdown"))
            val status=when{
                n>=settings.strategyMinChampionSamples&&acc>=settings.strategyMinChampionAccuracy&&avg>0&&floor>=50.0->StrategyStatus.CHAMPION
                n>=10&&avg<=0->StrategyStatus.PROBATION
                n>=5->StrategyStatus.ACTIVE
                else->StrategyStatus.CHALLENGER
            }
            StrategyPerformance(d.id,d.name,n,w,finite(acc),avg,avg,finite(maxDd),finite(floor),status)
        }.sortedWith(compareBy<StrategyPerformance>{it.status.ordinal}.thenByDescending{it.expectancyPct}.thenByDescending{it.accuracyPct})
    }""",
    "strategyPerformances",
)

p = replace_class_method(
    p,
    r"fun updateGlobalLearning\(key:String,returnPct:Double,win:Boolean\)\{",
    r"fun globalScoreAdjustment\(",
    """    fun updateGlobalLearning(key:String,returnPct:Double,win:Boolean){
        if(key.isBlank()||!returnPct.isFinite())return
        val root=globalLearningRoot()
        val x=root.optJSONObject(key)?:JSONObject()
        val sum=finite(storedFinite(x,"sumReturn")+returnPct)
        x.put("observations",x.optInt("observations").coerceAtLeast(0)+1)
            .put("wins",x.optInt("wins").coerceAtLeast(0)+(if(win)1 else 0))
            .put("sumReturn",sum)
            .put("lastAt",System.currentTimeMillis())
        root.put(key,x)
        prefs.edit().putString("global_learning_stats",root.toString()).apply()
    }""",
    "updateGlobalLearning",
)

p = replace_class_method(
    p,
    r"fun globalScoreAdjustment\(key:String\):Double\{",
    r"fun globalLearningSummary\(",
    """    fun globalScoreAdjustment(key:String):Double{
        val x=globalLearningRoot().optJSONObject(key)?:return 0.0
        val n=x.optInt("observations")
        if(n<4)return 0.0
        val wins=x.optInt("wins").coerceIn(0,n)
        val winRate=wins.toDouble()/n
        val avg=finite(storedFinite(x,"sumReturn")/n)
        return (((winRate-0.5)*10.0)+(avg*1.5)).takeIf{it.isFinite()}?.coerceIn(-6.0,6.0)?:0.0
    }""",
    "globalScoreAdjustment",
)

p = replace_class_method(
    p,
    r"private fun updateShadowLearning\(record:TradeAutopsyRecord\)\{",
    r"fun shadowLearningSummary\(",
    """    private fun updateShadowLearning(record:TradeAutopsyRecord){
        val root=runCatching{JSONObject(prefs.getString("shadow_strategy_stats_v120","{}")?:"{}")}.getOrElse{JSONObject()}
        for(x in record.shadowResults){
            val key="${record.engineLabel}|${record.regime.name}|${x.strategyId}"
            val j=root.optJSONObject(key)?:JSONObject()
            val safeReturn=finite(x.returnPct)
            j.put("strategyName",x.strategyName).put("observations",j.optInt("observations").coerceAtLeast(0)+1)
                .put("tradedWins",j.optInt("tradedWins").coerceAtLeast(0)+(if(x.outcome==ShadowOutcome.WIN)1 else 0))
                .put("tradedLosses",j.optInt("tradedLosses").coerceAtLeast(0)+(if(x.outcome==ShadowOutcome.LOSS)1 else 0))
                .put("avoidedLosses",j.optInt("avoidedLosses").coerceAtLeast(0)+(if(x.outcome==ShadowOutcome.AVOIDED_LOSS)1 else 0))
                .put("missedWins",j.optInt("missedWins").coerceAtLeast(0)+(if(x.outcome==ShadowOutcome.MISSED_WIN)1 else 0))
                .put("sumReturn",finite(storedFinite(j,"sumReturn")+safeReturn)).put("lastAt",record.generatedAt)
            val days=j.optString("days").split(',').filter{it.isNotBlank()}.toMutableSet()
            days+=record.sessionDate
            j.put("days",days.sorted().takeLast(30).joinToString(","))
            root.put(key,j)
        }
        prefs.edit().putString("shadow_strategy_stats_v120",root.toString()).apply()
    }""",
    "updateShadowLearning",
)
write(prefs_rel, p)

# 3) Make immutable call closing transactional: persist CLOSED/DONE first, then learning.
repo_rel = "app/src/main/java/com/suhas/ucsentinel/data/repository/UCSentinelRepository.kt"
u = read(repo_rel)

u = replace_class_method(
    u,
    r"suspend fun reconcileTradeCallLedger\(\):Int\{",
    r"suspend fun closeExpiredStrategyCalls\(\):Int\{",
    """    suspend fun reconcileTradeCallLedger():Int{
        val all=prefs.loadTradeCalls(1500).toMutableList()
        val open=all.filter{it.outcome==TradeCallOutcome.OPEN}
        if(open.isEmpty())return 0
        if(!ensureAutomationAuthentication())return 0
        val token=accessToken()
        val now=ZonedDateTime.now(ist)
        val today=now.toLocalDate()
        var changed=0
        val quoteCache=mutableMapOf<String,Quote?>()
        val candleCache=mutableMapOf<String,List<Candle>?>()
        val globalLearning=mutableListOf<Triple<String,Double,Boolean>>()

        val updated=all.map{call->
            if(call.outcome!=TradeCallOutcome.OPEN)return@map call
            val targetDate=runCatching{LocalDate.parse(call.targetSessionDate)}.getOrNull()?:return@map call
            if(today<targetDate)return@map call
            if(today==targetDate&&now.toLocalTime()<LocalTime.of(9,15))return@map call

            val sessionEnd=targetDate.atTime(15,31).atZone(ist)
            val opened=Instant.ofEpochMilli(call.openedAt).atZone(ist)
            val startZ=if(call.bucket==TradeCallBucket.LIVE&&opened.toLocalDate()==targetDate)opened else targetDate.atTime(9,15).atZone(ist)
            val endZ=if(today==targetDate&&now.isBefore(sessionEnd))now.plusMinutes(1) else sessionEnd
            val cacheKey="${call.symbol}|$targetDate|${startZ.toLocalTime()}|${endZ.toLocalTime()}"
            val candles=if(candleCache.containsKey(cacheKey))candleCache[cacheKey] else runCatching{
                groww.getHistoricalCandles(token,call.symbol,startZ.format(dateTimeFmt),endZ.format(dateTimeFmt),"5minute")
            }.getOrNull().also{candleCache[cacheKey]=it}

            var outcome=candles?.let{candleOutcome(call,it)}
            val q=quoteCache.getOrPut(call.symbol){runCatching{groww.getQuote(token,call.symbol)}.getOrNull()}
            if(outcome==null&&today==targetDate&&q!=null&&q.lastPrice.isFinite()&&q.lastPrice>0.0){
                val targetHit=if(call.direction==TradeDirection.LONG)q.lastPrice>=call.targetPrice else q.lastPrice<=call.targetPrice
                val stopHit=if(call.direction==TradeDirection.LONG)q.lastPrice<=call.stopPrice else q.lastPrice>=call.stopPrice
                outcome=when{
                    stopHit->TradeCallOutcome.LOSS to call.stopPrice
                    targetHit->TradeCallOutcome.WIN to call.targetPrice
                    else->null
                }
            }

            val expired=today>targetDate||(today==targetDate&&now.toLocalTime()>=LocalTime.of(15,30))
            var forcedExpiry=false
            if(outcome==null&&expired){
                val fallback=candles?.lastOrNull()?.close?.takeIf{it.isFinite()&&it>0.0}
                    ?:q?.lastPrice?.takeIf{it.isFinite()&&it>0.0}
                    ?:call.entryPrice.takeIf{it.isFinite()&&it>0.0}
                    ?:0.0
                outcome=TradeCallOutcome.LOSS to fallback
                forcedExpiry=true
            }
            if(outcome==null)return@map call

            val(out,exitRaw)=outcome!!
            val exit=exitRaw.takeIf{it.isFinite()&&it>0.0}?:call.entryPrice
            val ret=callReturnPct(call,exit)
            changed++
            if(call.engine==TradeCallEngine.GLOBAL&&call.learningKey.isNotBlank()){
                globalLearning+=Triple(call.learningKey,ret,out==TradeCallOutcome.WIN)
            }
            call.copy(
                outcome=out,
                closedAt=System.currentTimeMillis(),
                exitPrice=exit,
                returnPct=ret,
                closeReason=when(out){
                    TradeCallOutcome.WIN->"Target reached"
                    TradeCallOutcome.LOSS->when{
                        forcedExpiry&&candles==null->"Prediction horizon expired • historical replay unavailable"
                        forcedExpiry->"Target not reached by prediction horizon"
                        else->"Stop reached"
                    }
                    else->""
                }
            )
        }

        if(changed>0){
            prefs.saveTradeCalls(updated)
            DiagnosticLog.log(appContext,"CALL-LEDGER","closed $changed calls with WIN/LOSS")
        }
        globalLearning.forEach{(key,ret,win)->
            runCatching{prefs.updateGlobalLearning(key,ret,win)}
                .onFailure{DiagnosticLog.log(appContext,"CALL-LEDGER","Global learning update failed after durable close",it)}
        }
        return changed
    }""",
    "reconcileTradeCallLedger",
)

u = replace_class_method(
    u,
    r"suspend fun closeExpiredStrategyCalls\(\):Int\{",
    r"suspend fun scanTradingStrategies\(",
    """    suspend fun closeExpiredStrategyCalls():Int{
        val now=ZonedDateTime.now(ist)
        if(now.toLocalTime()<LocalTime.of(15,30)&&marketSessionInfo(now).isOpen)return 0
        val live=prefs.loadStrategyLive()
        if(live.isEmpty())return 0
        if(!ensureAutomationAuthentication())return 0
        val token=accessToken()
        val closed=prefs.loadStrategyClosed(500).toMutableList()
        val surviving=mutableListOf<StrategyRecommendation>()
        val learningUpdates=mutableListOf<Triple<StrategySetup,Double,Boolean>>()
        var changed=0

        for(r in live){
            val opened=Instant.ofEpochMilli(r.openedAt).atZone(ist)
            val sessionDate=opened.toLocalDate()
            if(now.toLocalDate()<sessionDate||(now.toLocalDate()==sessionDate&&now.toLocalTime()<LocalTime.of(15,30))){
                surviving+=r
                continue
            }

            val end=sessionDate.atTime(15,31).atZone(ist)
            val candles=runCatching{
                groww.getHistoricalCandles(token,r.setup.symbol,opened.format(dateTimeFmt),end.format(dateTimeFmt),"5minute")
            }.getOrNull()
            val q=runCatching{groww.getQuote(token,r.setup.symbol)}.getOrNull()
            val target=if(r.setup.direction==TradeDirection.LONG)r.setup.entryPrice*(1+r.setup.targetPct/100.0) else r.setup.entryPrice*(1-r.setup.targetPct/100.0)
            val stop=if(r.setup.direction==TradeDirection.LONG)r.setup.entryPrice*(1-r.setup.stopPct/100.0) else r.setup.entryPrice*(1+r.setup.stopPct/100.0)

            var win=false
            var stopHit=false
            val replayAvailable=candles!=null
            var exit=candles?.lastOrNull()?.close?.takeIf{it.isFinite()&&it>0.0}
                ?:q?.lastPrice?.takeIf{it.isFinite()&&it>0.0}
                ?:r.lastPrice.takeIf{it.isFinite()&&it>0.0}
                ?:r.setup.entryPrice

            candles?.sortedBy{it.epochSeconds}?.forEach{c->
                if(win||stopHit)return@forEach
                if(!c.high.isFinite()||!c.low.isFinite())return@forEach
                val th=if(r.setup.direction==TradeDirection.LONG)c.high>=target else c.low<=target
                val sh=if(r.setup.direction==TradeDirection.LONG)c.low<=stop else c.high>=stop
                if(th&&sh){stopHit=true;exit=stop}
                else if(sh){stopHit=true;exit=stop}
                else if(th){win=true;exit=target}
            }

            val rawRet=if(r.setup.entryPrice<=0.0||exit<=0.0)0.0 else if(r.setup.direction==TradeDirection.LONG)(exit/r.setup.entryPrice-1.0)*100.0 else (r.setup.entryPrice/exit-1.0)*100.0
            val ret=rawRet.takeIf{it.isFinite()}?:0.0
            val done=r.copy(
                lastSeenAt=System.currentTimeMillis(),
                lastPrice=exit,
                closedAt=System.currentTimeMillis(),
                exitPrice=exit,
                status=if(win)StrategyRecommendationStatus.WIN else StrategyRecommendationStatus.LOSS,
                returnPct=ret,
                closeReason=when{
                    win->"Target reached"
                    stopHit->"Stop reached"
                    !replayAvailable->"Prediction horizon expired • historical replay unavailable"
                    else->"Target not reached by session close"
                }
            )
            closed.removeAll{it.id==done.id}
            closed.add(done)
            learningUpdates+=Triple(r.setup,ret,win)
            changed++
        }

        prefs.saveStrategyLedger(surviving,closed)
        learningUpdates.forEach{(setup,ret,win)->
            runCatching{prefs.updateStrategyResult(setup.strategyId,setup.strategyName,ret,win)}
                .onFailure{DiagnosticLog.log(appContext,"STRATEGY","Learning update failed after durable close for ${setup.symbol}",it)}
        }
        if(changed>0)DiagnosticLog.log(appContext,"STRATEGY","closed $changed expired intraday calls with WIN/LOSS")
        return changed
    }""",
    "closeExpiredStrategyCalls",
)

scan_start = u.find("    suspend fun scanTradingStrategies(")
scan_end = u.find("\n    suspend fun refreshGlobalMappings", scan_start)
if scan_start < 0 or scan_end < 0:
    raise SystemExit("scanTradingStrategies range not found")
scan = u[scan_start:scan_end]

scan = must_replace(
    scan,
    "        val closed=prefs.loadStrategyClosed(500).toMutableList()\n        val surviving=mutableListOf<StrategyRecommendation>()",
    """        val closed=prefs.loadStrategyClosed(500).toMutableList()
        val surviving=mutableListOf<StrategyRecommendation>()
        val durableLearningUpdates=mutableListOf<Triple<StrategySetup,Double,Boolean>>()""",
    "strategy durable update list",
)

scan = must_replace(
    scan,
    """        fun returnPct(setup:StrategySetup,exit:Double):Double{
            if(setup.entryPrice<=0.0||exit<=0.0)return 0.0
            return if(setup.direction==TradeDirection.LONG)(exit/setup.entryPrice-1.0)*100.0 else (setup.entryPrice/exit-1.0)*100.0
        }""",
    """        fun returnPct(setup:StrategySetup,exit:Double):Double{
            if(setup.entryPrice<=0.0||exit<=0.0||!exit.isFinite())return 0.0
            val raw=if(setup.direction==TradeDirection.LONG)(exit/setup.entryPrice-1.0)*100.0 else (setup.entryPrice/exit-1.0)*100.0
            return raw.takeIf{it.isFinite()}?:0.0
        }""",
    "strategy return finite",
)

scan = must_replace(
    scan,
    """                if(status==StrategyRecommendationStatus.WIN||status==StrategyRecommendationStatus.LOSS){
                    prefs.updateStrategyResult(r.setup.strategyId,r.setup.strategyName,ret,status==StrategyRecommendationStatus.WIN)
                }""",
    """                if(status==StrategyRecommendationStatus.WIN||status==StrategyRecommendationStatus.LOSS){
                    durableLearningUpdates+=Triple(r.setup,ret,status==StrategyRecommendationStatus.WIN)
                }""",
    "strategy defer learning",
)

scan = must_replace(
    scan,
    "        prefs.saveStrategyLedger(surviving,closed)\n        prefs.pruneMemory(settings.memoryRetentionDays.coerceAtLeast(30))",
    """        prefs.saveStrategyLedger(surviving,closed)
        durableLearningUpdates.forEach{(setup,ret,win)->
            runCatching{prefs.updateStrategyResult(setup.strategyId,setup.strategyName,ret,win)}
                .onFailure{DiagnosticLog.log(appContext,"STRATEGY","Learning update failed after durable close for ${setup.symbol}",it)}
        }
        prefs.pruneMemory(settings.memoryRetentionDays.coerceAtLeast(30))""",
    "strategy persist before learning",
)

u = u[:scan_start] + scan + u[scan_end:]

u = must_replace(
    u,
    """    private fun callReturnPct(call:TradeCallRecord,exit:Double):Double{
        if(call.entryPrice<=0.0||exit<=0.0)return 0.0
        return if(call.direction==TradeDirection.LONG)(exit/call.entryPrice-1.0)*100.0 else (call.entryPrice/exit-1.0)*100.0
    }""",
    """    private fun callReturnPct(call:TradeCallRecord,exit:Double):Double{
        if(call.entryPrice<=0.0||exit<=0.0||!exit.isFinite())return 0.0
        val raw=if(call.direction==TradeDirection.LONG)(exit/call.entryPrice-1.0)*100.0 else (call.entryPrice/exit-1.0)*100.0
        return raw.takeIf{it.isFinite()}?:0.0
    }""",
    "call return finite",
)
write(repo_rel, u)

# 4) Foreground app also performs governance so opening it after 15:30 repairs DONE/CLOSED
# even if Android killed the foreground service.
vm_rel = "app/src/main/java/com/suhas/ucsentinel/ui/MainViewModel.kt"
v = read(vm_rel)
v = must_replace(
    v,
    "    private var lastForegroundGlobalScanAt=0L",
    "    private var lastForegroundGlobalScanAt=0L\n    private var lastForegroundGovernanceAt=0L",
    "foreground governance state",
)
v = must_replace(
    v,
    """        val session=repo.marketSessionInfo()
        val now=System.currentTimeMillis()

        if(!session.isOpen){""",
    """        val session=repo.marketSessionInfo()
        val now=System.currentTimeMillis()

        if(now-lastForegroundGovernanceAt>=5L*60_000L){
            lastForegroundGovernanceAt=now
            runCatching{repo.closeExpiredStrategyCalls()}
            runCatching{repo.reconcileTradeCallLedger()}
        }

        if(!session.isOpen){""",
    "foreground governance pass",
)
write(vm_rel, v)

# 5) Call governance is scoring/closure, not learning; use the five-minute market cadence.
svc_rel = "app/src/main/java/com/suhas/ucsentinel/worker/MarketScanService.kt"
s = read(svc_rel)
s = must_replace(
    s,
    "if (nowMs-lastGovernancePass >= 15L*60_000L) {",
    "if (nowMs-lastGovernancePass >= 5L*60_000L) {",
    "service governance cadence",
)
write(svc_rel, s)

print("Global Edge v1.2.2 reliability patch applied")

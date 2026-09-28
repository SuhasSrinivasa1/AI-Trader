#!/usr/bin/env python3
from pathlib import Path
import sys
root=Path(sys.argv[1]).resolve()

def rw(rel): return (root/rel).read_text(encoding="utf-8")
def wr(rel,s): (root/rel).write_text(s,encoding="utf-8")
def one(s,old,new,label):
    n=s.count(old)
    if n!=1: raise SystemExit(f"{label}: expected 1 found {n}")
    return s.replace(old,new,1)

p="app/build.gradle.kts"; s=rw(p)
s=one(s,"versionCode = 152","versionCode = 153","versionCode")
s=one(s,'versionName = "1.5.2"','versionName = "1.5.3"',"versionName")
wr(p,s)

p="app/src/main/java/com/suhas/ucsentinel/data/local/AppPreferences.kt"; s=rw(p)
anchor='''    fun saveTradeCalls(records:List<TradeCallRecord>){
        val a=JSONArray();records.distinctBy{it.id}.sortedByDescending{it.openedAt}.take(1500).forEach{a.put(tradeCallToJson(it))}
        prefs.edit().putString("trade_call_ledger_v118",a.toString()).apply()
    }

'''
addition=(anchor+r'''    fun enforceGlobalLiveOnlyFlow():Int{
        if(prefs.getBoolean("global_live_only_flow_v153",false))return 0
        val all=loadTradeCalls(1500)
        val researchOnly=all.filter{it.engine==TradeCallEngine.GLOBAL&&it.bucket!=TradeCallBucket.LIVE}

        if(researchOnly.isNotEmpty()){
            val archive=runCatching{JSONArray(prefs.getString("global_next_research_archive_v153","[]")?:"[]")}.getOrElse{JSONArray()}
            val known=mutableSetOf<String>()
            for(i in 0 until archive.length())archive.optJSONObject(i)?.optString("id")?.takeIf{it.isNotBlank()}?.let(known::add)
            researchOnly.filterNot{it.id in known}.forEach{archive.put(tradeCallToJson(it))}
            saveTradeCalls(all.filterNot{it.engine==TradeCallEngine.GLOBAL&&it.bucket!=TradeCallBucket.LIVE})
            prefs.edit().putString("global_next_research_archive_v153",archive.toString()).apply()
        }

        val root=JSONObject()
        all.filter{
            it.engine==TradeCallEngine.GLOBAL&&it.bucket==TradeCallBucket.LIVE&&
                it.outcome!=TradeCallOutcome.OPEN&&it.learningKey.isNotBlank()&&it.returnPct.isFinite()
        }.sortedBy{it.closedAt}.forEach{call->
            val x=root.optJSONObject(call.learningKey)?:JSONObject()
            val n=x.optInt("observations").coerceAtLeast(0)
            val wins=x.optInt("wins").coerceAtLeast(0)
            val sum=x.optDouble("sumReturn",0.0).takeIf{it.isFinite()}?:0.0
            x.put("observations",n+1)
                .put("wins",wins+(if(call.outcome==TradeCallOutcome.WIN)1 else 0))
                .put("sumReturn",sum+call.returnPct)
                .put("lastAt",call.closedAt.takeIf{it>0L}?:call.openedAt)
            root.put(call.learningKey,x)
        }
        prefs.edit()
            .putString("global_learning_stats",root.toString())
            .putBoolean("global_live_only_flow_v153",true)
            .apply()
        return researchOnly.size
    }

''')
s=one(s,anchor,addition,"global ledger migration")
wr(p,s)

p="app/src/main/java/com/suhas/ucsentinel/data/repository/UCSentinelRepository.kt"; s=rw(p)
old='''            val bucket=when{
                indiaMarketOpen&&(c.action==GlobalLeadAction.ENTER_AFTER_OPEN||c.action==GlobalLeadAction.KEEP_NEXT_SESSION)->TradeCallBucket.LIVE
                !indiaMarketOpen&&c.action==GlobalLeadAction.NEXT_OPEN_WATCH->TradeCallBucket.NEXT_SESSION
                else->continue
            }
'''
new='''            // Global state machine: RESEARCH/NEXT -> LIVE -> DONE.
            // NEXT is never a trade call and therefore can never be reconciled into DONE.
            val bucket=when{
                indiaMarketOpen&&(c.action==GlobalLeadAction.ENTER_AFTER_OPEN||c.action==GlobalLeadAction.KEEP_NEXT_SESSION)->TradeCallBucket.LIVE
                else->continue
            }
'''
s=one(s,old,new,"global call creation")
old='''            if(call.outcome!=TradeCallOutcome.OPEN)return@map call
            val targetDate=runCatching{LocalDate.parse(call.targetSessionDate)}.getOrNull()?:return@map call
'''
new='''            if(call.outcome!=TradeCallOutcome.OPEN)return@map call
            if(call.engine==TradeCallEngine.GLOBAL&&call.bucket!=TradeCallBucket.LIVE)return@map call
            val targetDate=runCatching{LocalDate.parse(call.targetSessionDate)}.getOrNull()?:return@map call
'''
s=one(s,old,new,"global reconcile live-only")
old='''            if(call.engine==TradeCallEngine.GLOBAL&&call.learningKey.isNotBlank()){
                globalLearning+=Triple(call.learningKey,ret,out==TradeCallOutcome.WIN)
            }
'''
new='''            if(call.engine==TradeCallEngine.GLOBAL&&call.bucket==TradeCallBucket.LIVE&&call.learningKey.isNotBlank()){
                globalLearning+=Triple(call.learningKey,ret,out==TradeCallOutcome.WIN)
            }
'''
s=one(s,old,new,"global learning live-only")
old='''    suspend fun scanGlobalLead(progress:suspend(String)->Unit={}):GlobalLeadSummary=globalMutex.withLock{
        val settings=prefs.loadSettings()
'''
new='''    suspend fun scanGlobalLead(progress:suspend(String)->Unit={}):GlobalLeadSummary=globalMutex.withLock{
        val migrated=prefs.enforceGlobalLiveOnlyFlow()
        if(migrated>0)DiagnosticLog.log(appContext,"GLOBAL-FLOW","Archived __D__migrated legacy NEXT/research records; DONE and learning are LIVE-only")
        val settings=prefs.loadSettings()
'''.replace("__D__","$")
s=one(s,old,new,"global migration trigger")
s=s.replace(
'''val glDone=ledger.filter{it.engine==TradeCallEngine.GLOBAL&&it.outcome!=TradeCallOutcome.OPEN}''',
'''val glDone=ledger.filter{it.engine==TradeCallEngine.GLOBAL&&it.bucket==TradeCallBucket.LIVE&&it.outcome!=TradeCallOutcome.OPEN}'''
)
wr(p,s)

p="app/src/main/java/com/suhas/ucsentinel/ui/CompactMarketScreens.kt"; s=rw(p)
s=one(s,
'''    val watch=all.filter{it.action==GlobalLeadAction.WAIT_FOR_CONFIRMATION||it.action==GlobalLeadAction.OBSERVE}.take(6)
    val closed=state.tradeCalls.filter{it.engine==TradeCallEngine.GLOBAL&&it.outcome!=TradeCallOutcome.OPEN}.sortedByDescending{it.closedAt}
''',
'''    val closed=state.tradeCalls.filter{it.engine==TradeCallEngine.GLOBAL&&it.bucket==TradeCallBucket.LIVE&&it.outcome!=TradeCallOutcome.OPEN}.sortedByDescending{it.closedAt}
''',"ui live-only done")

old='''            GlobalCompactView.NEXT_SESSION->{
                if(next.isEmpty()&&watch.isEmpty())item{EmptyState("No next-session global signal yet",summary?.message?:"Global mapping scan is running; India execution confirmation starts at 09:15 IST.")}
                else{
                    if(next.isNotEmpty())items(next,key={"next-__D__{it.direction}-__D__{it.indianSymbol}"}){c->
                        val indiaRef=if(c.indianPrice>=20.0)" • India ref ₹__D__{"%.2f".format(c.indianPrice)}" else " • India reference pending"
                        TradeCard(c.indianSymbol,"NEXT SESSION • __D__{c.direction.name}",c.score,globalPlan(c),"Lead __D__{c.foreignTicker} • __D__{c.exchange} • foreign __D__{"%.2f".format(c.foreignDayPct)}%__D__indiaRef","Research signal • live entry revalidated after 09:15 IST")
                    }
                    if(watch.isNotEmpty()){
                        item{Text("RESEARCH WATCH __D__{watch.size}",style=MaterialTheme.typography.labelMedium,fontWeight=FontWeight.Bold,color=MaterialTheme.colorScheme.onSurfaceVariant)}
                        items(watch,key={"global-watch-__D__{it.direction}-__D__{it.indianSymbol}"}){c->TradeCard(c.indianSymbol,"WATCH • __D__{c.direction.name}",c.score,globalPlan(c),"Lead __D__{c.foreignTicker} • __D__{c.exchange} • foreign __D__{"%.2f".format(c.foreignDayPct)}%","Below NEXT confirmation threshold • not counted as a call")}
                    }
                }
            }
'''.replace("__D__","$")
new='''            GlobalCompactView.NEXT_SESSION->{
                if(next.isEmpty())item{EmptyState("No next-session global signal yet",summary?.message?:"NEXT is a pre-market research shortlist. At/after 09:15 IST each candidate is revalidated; only confirmed candidates are promoted to LIVE.")}
                else items(next,key={"next-__D__{it.direction}-__D__{it.indianSymbol}"}){c->
                    val indiaRef=if(c.indianPrice>=20.0)" • India ref ₹__D__{"%.2f".format(c.indianPrice)}" else " • India reference pending"
                    TradeCard(c.indianSymbol,"NEXT SESSION • __D__{c.direction.name}",c.score,globalPlan(c),"Lead __D__{c.foreignTicker} • __D__{c.exchange} • foreign __D__{"%.2f".format(c.foreignDayPct)}%__D__indiaRef","Research only • not a call • must be revalidated into LIVE after 09:15 IST")
                }
            }
'''.replace("__D__","$")
s=one(s,old,new,"hide research watch frontend")
s=one(s,
'''                if(closed.isEmpty())item{EmptyState("No closed global calls","Every price-specific Global call will finish here as WIN or LOSS, including repeated calls for the same stock.")}
''',
'''                if(closed.isEmpty())item{EmptyState("No completed LIVE global calls","DONE contains only signals that were first confirmed in LIVE. NEXT and research-watch candidates never enter DONE directly.")}
''',"done empty state")
wr(p,s)

print("Global Edge v1.5.3 Global flow fix applied")

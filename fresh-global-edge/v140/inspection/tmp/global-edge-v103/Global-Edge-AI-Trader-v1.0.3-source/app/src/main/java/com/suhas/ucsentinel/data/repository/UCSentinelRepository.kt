package com.suhas.globaledgeai.data.repository

import android.content.Context
import com.suhas.globaledgeai.data.local.*
import com.suhas.globaledgeai.data.remote.*
import com.suhas.globaledgeai.domain.engine.*
import com.suhas.globaledgeai.domain.model.*
import com.suhas.globaledgeai.diagnostics.DiagnosticLog
import org.json.JSONArray
import org.json.JSONObject
import java.time.*
import java.time.format.DateTimeFormatter
import kotlin.math.abs
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.net.HttpURLConnection
import java.net.URL

class GlobalEdgeAITraderRepository(context:Context){
    companion object{ const val EXPECTED_TRADING_STATIC_IP="169.150.209.215" }
    private val appContext=context.applicationContext
    private val secureStore=SecureCredentialStore(context)
    private val prefs=AppPreferences(context)
    private val groww=GrowwClient()
    private val news=ExchangeNewsClient()
    private val nseMaster=NseSecurityMasterClient()
    private val instruments=InstrumentRepository(groww)
    private val ucScanner=ScannerEngine(groww)
    private val demandScanner=DemandScannerEngine(groww)
    private val replay=ReplayEngine(groww)
    private val globalMarket=GlobalMarketClient(context)
    private val globalLeadEngine=GlobalLeadEngine()
    private val strategyEngine=TradingStrategyEngine()
    private val autopsyEngine=TradeAutopsyEngine()
    private val strategyCatalogClient=StrategyCatalogClient(context)
    private var strategyCatalog:StrategyCatalogClient.Bundle?=null
    private var globalMappings:GlobalMarketClient.MappingBundle?=null
    private val globalMutex=Mutex()
    private val strategyMutex=Mutex()
    private val ist=ZoneId.of("Asia/Kolkata")
    private val dateTimeFmt=DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss")
    private var newListingsCache:List<ListedSecurity> = prefs.loadNewListings()
    private val scanMutex=Mutex()
    private var lastDualSummary:DualScanSummary?=loadLastDualFromDisk()
    private var lastDualScanAt:Long=maxOf(lastDualSummary?.uc?.completedAt?:0L,lastDualSummary?.demand?.completedAt?:0L)
    private val dualScanReuseMs=4L*60_000L

    fun credentials()=secureStore.loadCredentials()
    fun saveCredentials(c:Credentials)=secureStore.saveCredentials(c)
    fun accessToken()=secureStore.accessToken()
    fun tokenExpiry()=secureStore.accessTokenExpiry()
    fun settings()=prefs.loadSettings()
    fun saveSettings(s:AppSettings)=prefs.saveSettings(s)
    fun tradingStaticIp()=EXPECTED_TRADING_STATIC_IP
    fun saveTradingStaticIp(value:String){ /* v1.2.8: route is intentionally pinned in this build */ }
    suspend fun currentPublicIpv4():String=withContext(Dispatchers.IO){
        val connection=(URL("https://api.ipify.org").openConnection() as HttpURLConnection).apply{
            connectTimeout=5_000
            readTimeout=5_000
            requestMethod="GET"
            setRequestProperty("Accept","text/plain")
            useCaches=false
        }
        try{
            val code=connection.responseCode
            require(code in 200..299){"Public IP check failed: HTTP $code"}
            connection.inputStream.bufferedReader().use{it.readText().trim()}
                .also{ip->require(ip.matches(Regex("""^(?:\d{1,3}\.){3}\d{1,3}$"""))){"Invalid IPv4 response"}}
        }finally{connection.disconnect()}
    }
    fun strategyMetrics()=prefs.signalMetrics()
    fun accuracies()=mapOf(
        ScannerSection.UC_CONTINUATION to prefs.sectionAccuracy(ScannerSection.UC_CONTINUATION,SignalEngine.MODEL_VERSION),
        ScannerSection.DEMAND_SQUEEZE to prefs.sectionAccuracy(ScannerSection.DEMAND_SQUEEZE,DemandSignalEngine.MODEL_VERSION)
    )
    fun newListings()=newListingsCache
    fun listingFeedHealth()=prefs.listingFeedHealth()
    fun lastMarketDataSuccessAt()=prefs.lastMarketDataSuccessAt()
    fun lastSavedDualSummary()=lastDualSummary ?: loadLastDualFromDisk()
    fun lastPressureScanAt()=prefs.lastPressureScanAt()
    fun markPressureScanAt(value:Long=System.currentTimeMillis())=prefs.setLastPressureScanAt(value)
    fun lastNearCloseAutoScanAt()=prefs.lastNearCloseAutoScanAt()
    fun markNearCloseAutoScanAt(value:Long=System.currentTimeMillis())=prefs.setLastNearCloseAutoScanAt(value)
    fun lastLearningAt()=prefs.lastLearningAt()
    fun lastAutonomousLearningAt()=prefs.lastAutonomousLearningAt()
    fun globalLeadSummary()=prefs.loadGlobalLeadSummary()
    fun globalLeadClosedRecommendations()=prefs.loadGlobalLeadClosed()
    fun lastGlobalLeadScanAt()=prefs.lastGlobalLeadScanAt()
    fun lastGlobalMappingRefreshAt()=prefs.lastGlobalMappingRefreshAt()
    fun globalMappingVersion()=prefs.globalMappingVersion()
    fun strategyTournamentSummary()=prefs.loadStrategySummary()
    fun strategyLiveRecommendations()=prefs.loadStrategyLive()
    fun strategyClosedRecommendations()=prefs.loadStrategyClosed()
    fun lastStrategyScanAt()=prefs.lastStrategyScanAt()
    fun lastStrategyAttemptAt()=prefs.lastStrategyAttemptAt()
    fun lastStrategyErrorAt()=prefs.lastStrategyErrorAt()
    fun lastStrategyError()=prefs.lastStrategyError()
    fun markStrategyScanAttempt(value:Long=System.currentTimeMillis())=prefs.markStrategyAttempt(value)
    fun markStrategyScanError(t:Throwable){prefs.markStrategyError(t.message.orEmpty().ifBlank{t::class.java.simpleName})}
    fun lastStrategyCatalogRefreshAt()=prefs.lastStrategyCatalogRefreshAt()
    fun strategyCatalogVersion()=strategyCatalog?.version?:prefs.strategyCatalogVersion()
    fun freezeHistory(section:ScannerSection,limit:Int=20)=prefs.freezeHistory(section,limit)
    fun freezeRecordToday(section:ScannerSection)=prefs.freezeRecord(LocalDate.now(ist).toString(),section)
    fun latestFreezeRecord(section:ScannerSection)=prefs.freezeHistory(section,1).firstOrNull()

    fun tradeCalls():List<TradeCallRecord> = prefs.loadTradeCalls(1500)
    fun tradeAutopsies():List<TradeAutopsyRecord> = prefs.loadAutopsies(800)
    fun openTradeCalls(engine:TradeCallEngine?=null):List<TradeCallRecord> = tradeCalls().filter{it.outcome==TradeCallOutcome.OPEN&&(engine==null||it.engine==engine)}
    fun closedTradeCalls(engine:TradeCallEngine?=null):List<TradeCallRecord> = tradeCalls().filter{it.outcome!=TradeCallOutcome.OPEN&&(engine==null||it.engine==engine)}.sortedByDescending{it.closedAt}

    fun marketSessionInfo(now:ZonedDateTime=ZonedDateTime.now(ist)):MarketSessionInfo{
        val day=now.dayOfWeek
        val tradingDay=day!=DayOfWeek.SATURDAY && day!=DayOfWeek.SUNDAY
        val time=now.toLocalTime()
        val phase=when{
            !tradingDay->MarketPhase.WEEKEND
            time<LocalTime.of(9,15)->MarketPhase.PRE_OPEN
            time<=LocalTime.of(15,30)->MarketPhase.OPEN
            else->MarketPhase.POST_CLOSE
        }
        val label=when(phase){
            MarketPhase.WEEKEND->"Market closed • weekend"
            MarketPhase.PRE_OPEN->"Market closed • pre-open"
            MarketPhase.OPEN->"NSE market window open"
            MarketPhase.POST_CLOSE->"Market closed • showing last valid session data"
        }
        return MarketSessionInfo(phase,tradingDay,phase==MarketPhase.OPEN,label,now.toLocalDate().toString())
    }

    suspend fun authenticate():String{
        val(token,expiry)=groww.authenticate(secureStore.loadCredentials())
        secureStore.saveAccessToken(token,expiry)
        return expiry
    }

    suspend fun placeManualMarketOrder(symbol:String,side:String,product:String,quantity:Int):String{
        require(marketSessionInfo().isOpen){"Market is closed. Manual live orders are enabled only during the NSE 09:15–15:30 IST session."}
        require(quantity>0){"Quantity must be greater than zero"}
        val normalizedSide=side.trim().uppercase()
        val normalizedProduct=product.trim().uppercase()
        require((normalizedSide=="BUY"&&normalizedProduct=="CNC")||(normalizedSide=="SELL"&&normalizedProduct=="MIS")){
            "Order mapping rejected. LONG must be BUY/CNC; SHORT must be SELL/MIS."
        }
        val actualIp=currentPublicIpv4()
        require(actualIp==EXPECTED_TRADING_STATIC_IP){
            "Static IP mismatch. Expected $EXPECTED_TRADING_STATIC_IP but current public IPv4 is $actualIp."
        }
        if(!accessTokenIsCurrent()){
            require(ensureAutomationAuthentication()){"Groww authentication is required before placing an order."}
        }
        val token=accessToken()
        require(token.isNotBlank()){"Groww access token is unavailable. Authenticate again."}
        return groww.placeMarketOrder(token,symbol,quantity,normalizedProduct,normalizedSide)
    }

    fun canAutoRenewGroww():Boolean{
        val c=secureStore.loadCredentials()
        return c.mode==AuthMode.TOTP && c.apiKeyOrTotpToken.isNotBlank() && c.secret.isNotBlank()
    }

    fun accessTokenIsCurrent(now:ZonedDateTime=ZonedDateTime.now(ist)):Boolean{
        if(secureStore.accessToken().isBlank())return false
        val savedAt=secureStore.accessTokenSavedAt()
        if(savedAt<=0L)return false
        val cutoffDate=if(now.toLocalTime()>=LocalTime.of(6,0))now.toLocalDate() else now.toLocalDate().minusDays(1)
        val cutoff=cutoffDate.atTime(6,0).atZone(ist).toInstant().toEpochMilli()
        return savedAt>=cutoff
    }

    suspend fun ensureAutomationAuthentication():Boolean{
        if(accessTokenIsCurrent())return true
        if(!canAutoRenewGroww())return false
        return runCatching{authenticate();true}.getOrElse{
            secureStore.clearAccessToken()
            false
        }
    }

    fun invalidateAccessToken(){secureStore.clearAccessToken()}

    fun isAuthenticationFailure(t:Throwable):Boolean{
        val m=t.message.orEmpty().lowercase()
        return "(401)" in m || "(403)" in m || "unauthorized" in m || "invalid token" in m || "access token" in m && "expired" in m
    }

    suspend fun bootstrapAfterAuthentication(progress:suspend(String)->Unit={}):String{
        progress("Automation: refreshing instrument universe")
        runCatching{refreshUniverse()}
        progress("Automation: refreshing new listings")
        runCatching{refreshNewListings()}
        if(prefs.loadSettings().globalLeadEnabled){
            progress("Automation: refreshing weekly global counterpart map")
            runCatching{refreshGlobalMappings(false)}
            progress("Automation: scanning foreign-market leads")
            runCatching{scanGlobalLead(progress)}
        }
        if(prefs.loadSettings().strategyTournamentEnabled){
            progress("Automation: refreshing weekly strategy catalogue")
            runCatching{refreshStrategyCatalog(false)}
        }
        if(prefs.loadSettings().learningEnabled){
            progress("Automation: checking due learning outcomes")
            runCatching{runLearningCycle()}
        }
        val session=marketSessionInfo()
        if(session.isOpen){
            progress("Automation: starting live discovery")
            runCatching{scanAll(progress)}
            if(prefs.loadSettings().strategyTournamentEnabled) runCatching{scanTradingStrategies(progress)}
            ensureTodayFreezeAudit()
            return "Automation active • live finding + learning armed"
        }
        ensureTodayFreezeAudit()
        return "Automation active • next market-session scans are armed"
    }
    suspend fun refreshUniverse():Int=instruments.refresh().size
    suspend fun refreshNews():List<NewsItem> = news.latest()

    suspend fun refreshNewListings():List<ListedSecurity>{
        val attempt=System.currentTimeMillis();val previous=prefs.listingFeedHealth()
        return try{
            val list=nseMaster.recentListings(prefs.loadSettings().newListingDays)
            newListingsCache=list; prefs.saveNewListings(list)
            prefs.saveListingFeedHealth(FeedHealth(if(list.isEmpty())FeedHealthState.EMPTY else FeedHealthState.OK,list.size,attempt,attempt,if(list.isEmpty())"Feed healthy • no listings in selected window" else "Feed healthy"))
            list
        }catch(t:Throwable){
            prefs.saveListingFeedHealth(FeedHealth(FeedHealthState.ERROR,newListingsCache.size,attempt,previous.lastSuccessAt,"NSE listing feed error: ${t.message.orEmpty().take(140)}"))
            throw t
        }
    }


    suspend fun refreshStrategyCatalog(force:Boolean=false):Int{
        val settings=prefs.loadSettings();val now=System.currentTimeMillis();val last=prefs.lastStrategyCatalogRefreshAt()
        val due=last==0L||now-last>=settings.strategyCatalogRefreshDays.coerceIn(1,30).toLong()*24*60*60*1000
        val weekend=ZonedDateTime.now(ist).dayOfWeek in setOf(DayOfWeek.SATURDAY,DayOfWeek.SUNDAY)
        if(strategyCatalog==null)strategyCatalog=strategyCatalogClient.embedded()
        if(!force&&(!due||(last>0&&!weekend)))return strategyCatalog!!.strategies.size
        val bundle=runCatching{strategyCatalogClient.remote()}.getOrElse{strategyCatalogClient.embedded()}
        strategyCatalog=bundle;prefs.setLastStrategyCatalogRefreshAt(now)
        return bundle.strategies.size
    }

    private fun activeStrategyDefinitions(settings:AppSettings):Pair<StrategyCatalogClient.Bundle,List<TradingStrategyDefinition>>{
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

    private fun nextTradingDate(from:LocalDate):LocalDate{
        var d=from.plusDays(1)
        while(d.dayOfWeek==DayOfWeek.SATURDAY||d.dayOfWeek==DayOfWeek.SUNDAY)d=d.plusDays(1)
        return d
    }

    private fun targetSessionFor(bucket:TradeCallBucket,openedAt:Long):LocalDate{
        val z=Instant.ofEpochMilli(openedAt).atZone(ist);val d=z.toLocalDate();val t=z.toLocalTime()
        return when(bucket){
            TradeCallBucket.LIVE->d
            TradeCallBucket.THREE_PM->nextTradingDate(d)
            TradeCallBucket.NEXT_SESSION->if(d.dayOfWeek !in setOf(DayOfWeek.SATURDAY,DayOfWeek.SUNDAY)&&t<LocalTime.of(9,15))d else nextTradingDate(d)
        }
    }

    private data class CallPlan(val entry:Double,val stop:Double,val target:Double,val target2:Double?=null)

    private fun candidateCallPlan(c:Candidate,section:ScannerSection,bucket:TradeCallBucket):CallPlan?{
        val entry=c.price.takeIf{it.isFinite()&&it>=ExecutionQuality.MIN_PRICE}?:return null
        return if(section==ScannerSection.UC_CONTINUATION){
            val prevClose=if(c.dayChangePercent>-95.0)entry/(1.0+c.dayChangePercent/100.0) else entry
            val inferredBand=if(prevClose>0.0&&c.upperCircuit>prevClose)((c.upperCircuit/prevClose-1.0)*100.0).coerceIn(2.0,20.0) else 5.0
            val target=when(bucket){
                TradeCallBucket.LIVE->if(c.upperCircuit>entry)c.upperCircuit else entry*(1.0+inferredBand/100.0)
                TradeCallBucket.NEXT_SESSION,TradeCallBucket.THREE_PM->entry*(1.0+inferredBand/100.0)
            }
            CallPlan(entry,entry*0.985,target)
        }else{
            val targetPct=(c.targetMovePct?:2.5).coerceIn(0.5,8.0)
            CallPlan(entry,entry*0.985,entry*(1.0+targetPct/100.0))
        }
    }

    private fun globalCallPlan(c:GlobalLeadCandidate):CallPlan?{
        val base=c.indianPrice.takeIf{it.isFinite()&&it>=ExecutionQuality.MIN_PRICE}?:return null
        val short=c.direction==GlobalLeadDirection.SHORT
        val entry=if(short)base*0.999 else base*1.001
        val openDistancePct=if(c.indianOpen>0.0)abs(c.indianOpen-entry)/entry*100.0 else 0.0
        val riskPct=(openDistancePct*0.25).takeIf{it.isFinite()&&it>0.0}?.coerceIn(0.35,1.00)?:0.50
        val targetPct=c.expectedTargetPct.takeIf{it.isFinite()&&it>0.0}?.coerceIn(0.35,3.00)?:0.50
        val target2Pct=(targetPct*1.75).coerceIn(targetPct+0.20,4.00)
        val stop=if(short)entry*(1.0+riskPct/100.0) else entry*(1.0-riskPct/100.0)
        val t1=if(short)entry*(1.0-targetPct/100.0) else entry*(1.0+targetPct/100.0)
        val t2=if(short)entry*(1.0-target2Pct/100.0) else entry*(1.0+target2Pct/100.0)
        return CallPlan(entry,stop,t1,t2)
    }

    private fun recordCandidateCalls(section:ScannerSection,bucket:TradeCallBucket,candidates:List<Candidate>,source:String,nowMs:Long=System.currentTimeMillis()):Int{
        if(candidates.isEmpty())return 0
        val engine=if(section==ScannerSection.UC_CONTINUATION)TradeCallEngine.UPPER_CIRCUIT else TradeCallEngine.PRESSURE
        val ledger=prefs.loadTradeCalls(1500).toMutableList();var added=0
        for(c in candidates){
            val plan=candidateCallPlan(c,section,bucket)?:continue
            val latest=ledger.filter{it.engine==engine&&it.bucket==bucket&&it.symbol==c.symbol&&it.outcome==TradeCallOutcome.OPEN}.maxByOrNull{it.openedAt}
            val changePct=latest?.let{if(it.entryPrice>0.0)abs(plan.entry/it.entryPrice-1.0)*100.0 else 100.0}?:100.0
            val sameThreePmDay=latest!=null&&bucket==TradeCallBucket.THREE_PM&&Instant.ofEpochMilli(latest.openedAt).atZone(ist).toLocalDate()==Instant.ofEpochMilli(nowMs).atZone(ist).toLocalDate()
            if(sameThreePmDay || (latest!=null&&changePct<0.20))continue
            val id="${engine.name}|${bucket.name}|${c.symbol}|$nowMs"
            val headroom=if(c.upperCircuit>c.price&&c.upperCircuit>0.0)(c.upperCircuit/c.price-1.0)*100.0 else 0.0
            val detail=c.companyName+" • score "+"%.0f".format(c.score)+" • "+"%.2f".format(c.dayChangePercent)+"% • vol "+"%.1f".format(c.volumeRatio)+"x • UC headroom "+"%.2f".format(headroom)+"%"
            ledger+=TradeCallRecord(id,engine,bucket,c.symbol,c.companyName,TradeDirection.LONG,c.score,plan.entry,plan.stop,plan.target,plan.target2,nowMs,targetSessionFor(bucket,nowMs).toString(),source,detail)
            added++
        }
        if(added>0){prefs.saveTradeCalls(ledger);DiagnosticLog.log(appContext,"CALL-LEDGER","opened $added ${engine.name} $bucket calls")}
        return added
    }

    private fun recordGlobalCalls(candidates:List<GlobalLeadCandidate>,indiaMarketOpen:Boolean,nowMs:Long=System.currentTimeMillis()):Int{
        val ledger=prefs.loadTradeCalls(1500).toMutableList();var added=0
        for(c in candidates){
            val bucket=when{
                indiaMarketOpen&&(c.action==GlobalLeadAction.ENTER_AFTER_OPEN||c.action==GlobalLeadAction.KEEP_NEXT_SESSION)->TradeCallBucket.LIVE
                !indiaMarketOpen&&c.action==GlobalLeadAction.NEXT_OPEN_WATCH->TradeCallBucket.NEXT_SESSION
                else->continue
            }
            val plan=globalCallPlan(c)?:continue
            val direction=if(c.direction==GlobalLeadDirection.SHORT)TradeDirection.SHORT else TradeDirection.LONG
            val latest=ledger.filter{it.engine==TradeCallEngine.GLOBAL&&it.bucket==bucket&&it.symbol==c.indianSymbol&&it.direction==direction&&it.outcome==TradeCallOutcome.OPEN}.maxByOrNull{it.openedAt}
            val changePct=latest?.let{if(it.entryPrice>0.0)abs(plan.entry/it.entryPrice-1.0)*100.0 else 100.0}?:100.0
            if(latest!=null&&changePct<0.20)continue
            val id="GLOBAL|${bucket.name}|${direction.name}|${c.indianSymbol}|$nowMs"
            val detail="Lead ${c.foreignTicker} • ${c.exchange} • foreign ${"%.2f".format(c.foreignDayPct)}%"
            ledger+=TradeCallRecord(id,TradeCallEngine.GLOBAL,bucket,c.indianSymbol,c.indianCompany,direction,c.score,plan.entry,plan.stop,plan.target,plan.target2,nowMs,targetSessionFor(bucket,nowMs).toString(),"Global ${bucket.name}",detail,globalLearningKey(c))
            added++
        }
        if(added>0){prefs.saveTradeCalls(ledger);DiagnosticLog.log(appContext,"CALL-LEDGER","opened $added GLOBAL calls")}
        return added
    }

    private fun recordRejectedCandidateShadow(section:ScannerSection,bucket:TradeCallBucket,c:Candidate,reason:String,nowMs:Long=System.currentTimeMillis()){
        val plan=candidateCallPlan(c,section,bucket)?:return
        val engine=if(section==ScannerSection.UC_CONTINUATION)TradeCallEngine.UPPER_CIRCUIT else TradeCallEngine.PRESSURE
        prefs.appendRejectedShadow(RejectedCandidateRecord(
            id="REJECT|${engine.name}|${bucket.name}|${c.symbol}|$nowMs",engineLabel=engine.name,symbol=c.symbol,direction=TradeDirection.LONG,
            score=c.score,entryPrice=plan.entry,stopPrice=plan.stop,targetPrice=plan.target,capturedAt=nowMs,
            targetSessionDate=targetSessionFor(bucket,nowMs).toString(),reason=reason
        ))
    }

    private fun recordRejectedStrategyShadow(s:StrategySetup,reason:String,nowMs:Long=System.currentTimeMillis()){
        val plan=run{
            val entry=s.entryPrice.takeIf{it.isFinite()&&it>=ExecutionQuality.MIN_PRICE}?:return
            val short=s.direction==TradeDirection.SHORT
            val stop=if(short)entry*(1+s.stopPct.coerceAtLeast(0.1)/100.0) else entry*(1-s.stopPct.coerceAtLeast(0.1)/100.0)
            val target=if(short)entry*(1-s.targetPct.coerceAtLeast(0.1)/100.0) else entry*(1+s.targetPct.coerceAtLeast(0.1)/100.0)
            CallPlan(entry,stop,target)
        }
        prefs.appendRejectedShadow(RejectedCandidateRecord(
            id="REJECT|STRATEGY|${s.direction.name}|${s.symbol}|$nowMs",engineLabel="STRATEGY",symbol=s.symbol,direction=s.direction,
            score=s.score,entryPrice=plan.entry,stopPrice=plan.stop,targetPrice=plan.target,capturedAt=nowMs,
            targetSessionDate=targetSessionFor(TradeCallBucket.LIVE,nowMs).toString(),reason=reason
        ))
    }

    private fun recordRejectedGlobalShadow(c:GlobalLeadCandidate,indiaMarketOpen:Boolean,reason:String,nowMs:Long=System.currentTimeMillis()){
        val plan=globalCallPlan(c)?:return
        val bucket=if(indiaMarketOpen)TradeCallBucket.LIVE else TradeCallBucket.NEXT_SESSION
        val direction=if(c.direction==GlobalLeadDirection.SHORT)TradeDirection.SHORT else TradeDirection.LONG
        prefs.appendRejectedShadow(RejectedCandidateRecord(
            id="REJECT|GLOBAL|${direction.name}|${c.indianSymbol}|$nowMs",engineLabel=TradeCallEngine.GLOBAL.name,symbol=c.indianSymbol,direction=direction,
            score=c.score,entryPrice=plan.entry,stopPrice=plan.stop,targetPrice=plan.target,capturedAt=nowMs,
            targetSessionDate=targetSessionFor(bucket,nowMs).toString(),reason=reason
        ))
    }

    private fun shadowReturnPct(r:RejectedCandidateRecord,exit:Double):Double{
        if(r.entryPrice<=0.0||exit<=0.0)return 0.0
        return if(r.direction==TradeDirection.LONG)(exit/r.entryPrice-1.0)*100.0 else (r.entryPrice/exit-1.0)*100.0
    }

    private fun shadowOutcome(r:RejectedCandidateRecord,candles:List<Candle>):Pair<RejectedShadowOutcome,Double>?{
        for(c in candles.sortedBy{it.epochSeconds}){
            val targetHit=if(r.direction==TradeDirection.LONG)c.high>=r.targetPrice else c.low<=r.targetPrice
            val stopHit=if(r.direction==TradeDirection.LONG)c.low<=r.stopPrice else c.high>=r.stopPrice
            if(targetHit&&stopHit)return RejectedShadowOutcome.WOULD_LOSE to r.stopPrice
            if(stopHit)return RejectedShadowOutcome.WOULD_LOSE to r.stopPrice
            if(targetHit)return RejectedShadowOutcome.WOULD_WIN to r.targetPrice
        }
        return null
    }

    suspend fun reconcileRejectedShadows():Int{
        val all=prefs.loadRejectedShadows(2500).toMutableList();if(all.none{it.outcome==RejectedShadowOutcome.PENDING})return 0
        if(!ensureAutomationAuthentication())return 0
        val token=accessToken();val now=ZonedDateTime.now(ist);val today=now.toLocalDate();var changed=0
        val candleCache=mutableMapOf<String,List<Candle>?>()
        val updated=all.map{r->
            if(r.outcome!=RejectedShadowOutcome.PENDING)return@map r
            val targetDate=runCatching{LocalDate.parse(r.targetSessionDate)}.getOrNull()?:return@map r
            if(today<targetDate||today==targetDate&&now.toLocalTime()<LocalTime.of(9,15))return@map r
            val captured=Instant.ofEpochMilli(r.capturedAt).atZone(ist)
            val startZ=if(captured.toLocalDate()==targetDate&&captured.toLocalTime()>=LocalTime.of(9,15)&&captured.toLocalTime()<LocalTime.of(15,30))captured else targetDate.atTime(9,15).atZone(ist)
            val sessionEnd=targetDate.atTime(15,31).atZone(ist);val endZ=if(today==targetDate&&now.isBefore(sessionEnd))now.plusMinutes(1) else sessionEnd
            val key="${r.symbol}|$targetDate|${startZ.toLocalTime()}|${endZ.toLocalTime()}"
            val candles=if(candleCache.containsKey(key))candleCache[key] else runCatching{groww.getHistoricalCandles(token,r.symbol,startZ.format(dateTimeFmt),endZ.format(dateTimeFmt),"5minute")}.getOrNull().also{candleCache[key]=it}
            var result=candles?.let{shadowOutcome(r,it)}
            val expired=today>targetDate||(today==targetDate&&now.toLocalTime()>=LocalTime.of(15,30))
            if(result==null&&expired&&candles!=null){val exit=candles.lastOrNull()?.close?:r.entryPrice;result=RejectedShadowOutcome.WOULD_LOSE to exit}
            if(result==null)return@map r
            val(out,exit)=result!!;changed++;r.copy(outcome=out,closedAt=System.currentTimeMillis(),exitPrice=exit,returnPct=shadowReturnPct(r,exit))
        }
        if(changed>0){prefs.saveRejectedShadows(updated);DiagnosticLog.log(appContext,"MISSED-OPPORTUNITY","resolved $changed rejected-candidate shadows")}
        return changed
    }

    private fun callReturnPct(call:TradeCallRecord,exit:Double):Double{
        if(call.entryPrice<=0.0||exit<=0.0||!exit.isFinite())return 0.0
        val raw=if(call.direction==TradeDirection.LONG)(exit/call.entryPrice-1.0)*100.0 else (call.entryPrice/exit-1.0)*100.0
        return raw.takeIf{it.isFinite()}?:0.0
    }

    private fun candleOutcome(call:TradeCallRecord,candles:List<Candle>):Pair<TradeCallOutcome,Double>?{
        for(c in candles.sortedBy{it.epochSeconds}){
            val targetHit=if(call.direction==TradeDirection.LONG)c.high>=call.targetPrice else c.low<=call.targetPrice
            val stopHit=if(call.direction==TradeDirection.LONG)c.low<=call.stopPrice else c.high>=call.stopPrice
            if(targetHit&&stopHit)return TradeCallOutcome.LOSS to call.stopPrice // conservative when order inside one 5-min candle is unknowable
            if(stopHit)return TradeCallOutcome.LOSS to call.stopPrice
            if(targetHit)return TradeCallOutcome.WIN to call.targetPrice
        }
        return null
    }

    suspend fun reconcileTradeCallLedger():Int{
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
    }

    suspend fun closeExpiredStrategyCalls():Int{
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
    }

    suspend fun scanTradingStrategies(progress:suspend(String)->Unit={}):StrategyTournamentSummary=strategyMutex.withLock{
        prefs.markStrategyAttempt()
        val settings=prefs.loadSettings();require(settings.strategyTournamentEnabled){"Strategy tournament is disabled"}
        require(ensureAutomationAuthentication()){ "Groww authentication is required. TOTP mode can renew automatically." }
        if(strategyCatalog==null)runCatching{refreshStrategyCatalog(false)}
        val(bundle,active)=activeStrategyDefinitions(settings)
        val token=accessToken();val universe=if(instruments.cached().isEmpty())instruments.refresh() else instruments.cached()

        // Intraday strategy execution is deliberately stricter than the broad UC universe.
        // EQ-only removes trade-to-trade / SME series where broker intraday products are commonly unavailable.
        val cash=universe.filter{it.exchange=="NSE"&&it.segment=="CASH"&&it.series=="EQ"&&it.buyAllowed}.distinctBy{it.tradingSymbol}
        progress("Strategies: screening ${cash.size} intraday-eligible NSE EQ stocks with ${active.size} rules")
        val movers=mutableListOf<Pair<Instrument,Double>>()
        cash.chunked(50).forEachIndexed{idx,batch->
            val map=runCatching{groww.getOhlcBatch(token,batch.map{it.tradingSymbol})}.getOrDefault(emptyMap())
            batch.forEach{i->
                val o=map[i.tradingSymbol]?:return@forEach
                // Avoid penny / ultra-low-price names before spending quote/history calls.
                if(o.close<20.0)return@forEach
                val move=if(o.open>0)kotlin.math.abs(o.close/o.open-1.0)*100 else 0.0
                movers+=i to move
            }
            if(idx%10==9)progress("Strategies: market prefilter ${minOf((idx+1)*50,cash.size)}/${cash.size}")
        }
        val carried=(lastSavedDualSummary()?.uc?.candidates.orEmpty()+lastSavedDualSummary()?.demand?.candidates.orEmpty()).map{it.symbol}.toSet()
        val selected=(movers.sortedByDescending{it.second}.map{it.first}.take(settings.strategyHistorySymbolsPerPass.coerceIn(24,40))+
            cash.filter{it.tradingSymbol in carried}).distinctBy{it.tradingSymbol}.take(48)
        val listingAge=newListingsCache.associate{it.symbol to it.daysListed}
        val now=ZonedDateTime.now(ist);val date=now.toLocalDate();val start=date.atTime(9,15).format(dateTimeFmt);val end=now.plusMinutes(1).format(dateTimeFmt)
        val quoteCache=mutableMapOf<String,Quote?>()
        suspend fun quote(symbol:String):Quote? = if(quoteCache.containsKey(symbol))quoteCache[symbol] else runCatching{groww.getQuote(token,symbol)}.getOrNull().also{quoteCache[symbol]=it}
        fun spreadPct(q:Quote)=ExecutionQuality.spreadPct(q)
        fun hasBid(q:Quote)=ExecutionQuality.hasBid(q)
        fun hasAsk(q:Quote)=ExecutionQuality.hasAsk(q)
        fun returnPct(setup:StrategySetup,exit:Double):Double{
            if(setup.entryPrice<=0.0||exit<=0.0||!exit.isFinite())return 0.0
            val raw=if(setup.direction==TradeDirection.LONG)(exit/setup.entryPrice-1.0)*100.0 else (setup.entryPrice/exit-1.0)*100.0
            return raw.takeIf{it.isFinite()}?:0.0
        }

        // First reconcile already-open recommendations. A recommendation never disappears because a later
        // scan no longer ranks it; it stays LIVE until target, stop, invalidation, or end-of-day governance.
        val existingLive=prefs.loadStrategyLive().toMutableList()
        val closed=prefs.loadStrategyClosed(500).toMutableList()
        val surviving=mutableListOf<StrategyRecommendation>()
        val durableLearningUpdates=mutableListOf<Triple<StrategySetup,Double,Boolean>>()
        for(r in existingLive){
            val openedDate=Instant.ofEpochMilli(r.openedAt).atZone(ist).toLocalDate()
            val q=quote(r.setup.symbol)
            val px=q?.lastPrice?.takeIf{it.isFinite()&&it>0.0}?:r.lastPrice
            val target=if(r.setup.direction==TradeDirection.LONG)r.setup.entryPrice*(1+r.setup.targetPct/100.0) else r.setup.entryPrice*(1-r.setup.targetPct/100.0)
            val stop=if(r.setup.direction==TradeDirection.LONG)r.setup.entryPrice*(1-r.setup.stopPct/100.0) else r.setup.entryPrice*(1+r.setup.stopPct/100.0)
            val hitTarget=if(r.setup.direction==TradeDirection.LONG)px>=target else px<=target
            val hitStop=if(r.setup.direction==TradeDirection.LONG)px<=stop else px>=stop
            val oldDay=openedDate<date
            val eod=now.toLocalTime()>=LocalTime.of(15,30)
            val status=when{
                hitTarget->StrategyRecommendationStatus.WIN
                hitStop->StrategyRecommendationStatus.LOSS
                oldDay||eod->StrategyRecommendationStatus.LOSS
                else->StrategyRecommendationStatus.LIVE
            }
            if(status==StrategyRecommendationStatus.LIVE){
                val sp=q?.let(::spreadPct)?:r.spreadPct
                surviving+=r.copy(lastSeenAt=System.currentTimeMillis(),lastPrice=px,tradedValue=q?.let{it.volume*it.lastPrice}?:r.tradedValue,volume=q?.volume?:r.volume,spreadPct=sp)
            }else{
                val ret=returnPct(r.setup,px)
                val reason=when(status){
                    StrategyRecommendationStatus.WIN->"Target reached"
                    StrategyRecommendationStatus.LOSS->if(hitStop)"Stop reached" else "Target not reached by session close"
                    StrategyRecommendationStatus.EXPIRED->"Legacy expired call"
                    else->"Closed"
                }
                val done=r.copy(lastSeenAt=System.currentTimeMillis(),lastPrice=px,closedAt=System.currentTimeMillis(),exitPrice=px,status=status,returnPct=ret,closeReason=reason,
                    tradedValue=q?.let{it.volume*it.lastPrice}?:r.tradedValue,volume=q?.volume?:r.volume,spreadPct=q?.let(::spreadPct)?:r.spreadPct)
                closed.removeAll{it.id==done.id};closed.add(done)
                if(status==StrategyRecommendationStatus.WIN||status==StrategyRecommendationStatus.LOSS){
                    durableLearningUpdates+=Triple(r.setup,ret,status==StrategyRecommendationStatus.WIN)
                }
            }
        }

        val rawSetups=mutableListOf<Pair<StrategySetup,Quote>>();var enriched=0;var quoteRejected=0;var historyFailed=0;var candleShort=0;var rulesMatched=0
        for((idx,inst) in selected.withIndex()){
            val q=quote(inst.tradingSymbol)?:continue
            val sp=spreadPct(q);val tradedValue=q.volume*q.lastPrice
            // Execution-quality gates requested for the strategy engine.
            if(!ExecutionQuality.executableQuote(q)){quoteRejected++;continue}
            val candleResult=runCatching{groww.getHistoricalCandles(token,inst.tradingSymbol,start,end,"5minute")}
            if(candleResult.isFailure){historyFailed++;continue}
            val candles=candleResult.getOrDefault(emptyList())
            if(candles.size<4){candleShort++;continue};enriched++
            for(def in active){
                val e=strategyEngine.evaluate(def,candles)?:continue;rulesMatched++
                if(e.targetPct<ExecutionQuality.MIN_PLAN_SEPARATION_PCT||e.stopPct<ExecutionQuality.MIN_PLAN_SEPARATION_PCT)continue
                if(e.direction==TradeDirection.SHORT&&!inst.sellAllowed)continue
                if(e.direction==TradeDirection.LONG&&!hasAsk(q))continue
                if(e.direction==TradeDirection.SHORT&&!hasBid(q))continue
                val age=listingAge[inst.tradingSymbol];val boost=if(age!=null&&age<=settings.newListingDays)2.0 else 0.0
                val score=(e.score+boost).coerceAtMost(100.0)
                if(score<68.0)continue
                val liquidity="₹${"%.1f".format(tradedValue/100000.0)}L traded • vol ${q.volume} • spread ${"%.2f".format(sp)}%"
                rawSetups+=StrategySetup(inst.tradingSymbol,inst.name,def.id,def.name,e.direction,score,q.lastPrice,e.targetPct,e.stopPct,
                    e.evidence+" • "+liquidity+(if(boost>0)" • new-listing context" else ""),age) to q
            }
            if(idx%10==9)progress("Strategies: candles/liquidity ${idx+1}/${selected.size}")
        }

        // Multiple independent rules agreeing on the same side become one clearer recommendation.
        val combined=rawSetups.groupBy{it.first.symbol to it.first.direction}.map{(_,pairs)->
            val ranked=pairs.sortedByDescending{it.first.score};val primary=ranked.first();val agree=ranked.take(3)
            val names=agree.map{it.first.strategyName}.distinct()
            val boost=((names.size-1)*2.0).coerceAtMost(4.0)
            primary.first.copy(
                strategyName=names.joinToString(" + "),
                score=(primary.first.score+boost).coerceAtMost(100.0),
                evidence="${names.size} strategy confirmation • "+agree.joinToString(" | "){it.first.evidence.take(110)}
            ) to primary.second
        }
        // If both directions fire on one stock, only keep the stronger side so the UI never recommends conflicting trades.
        val top=combined.groupBy{it.first.symbol}.mapNotNull{(_,v)->v.maxByOrNull{it.first.score}}
            .sortedByDescending{it.first.score}.take(settings.strategyTopCandidates.coerceIn(10,20))
        val confirmedTop=top.filter{it.first.score>=72.0}
        top.filter{it.first.score<72.0}.take(8).forEach{(setup,_)->recordRejectedStrategyShadow(setup,"BELOW_LIVE_THRESHOLD ${"%.1f".format(setup.score)} < 72.0")}

        val existingKeys=surviving.map{"${it.setup.symbol}|${it.setup.direction.name}"}.toMutableSet()
        val newlyOpened=mutableListOf<StrategySetup>()
        // Do not open fresh intraday calls in the final 20 minutes, but continue managing existing ones.
        if(now.toLocalTime()<LocalTime.of(15,10)){
            for((setup,q) in confirmedTop){
                val key="${setup.symbol}|${setup.direction.name}";if(key in existingKeys)continue
                val sp=spreadPct(q);val id="${date}|$key|${setup.strategyId}"
                surviving+=StrategyRecommendation(id,setup,System.currentTimeMillis(),System.currentTimeMillis(),q.lastPrice,
                    tradedValue=q.volume*q.lastPrice,volume=q.volume,spreadPct=sp)
                existingKeys+=key;newlyOpened+=setup
            }
        }
        prefs.saveStrategyLedger(surviving,closed)
        durableLearningUpdates.forEach{(setup,ret,win)->
            runCatching{prefs.updateStrategyResult(setup.strategyId,setup.strategyName,ret,win)}
                .onFailure{DiagnosticLog.log(appContext,"STRATEGY","Learning update failed after durable close for ${setup.symbol}",it)}
        }
        prefs.pruneMemory(settings.memoryRetentionDays.coerceAtLeast(30))

        val perfs=prefs.strategyPerformances(bundle.strategies,settings)
        val summary=StrategyTournamentSummary(System.currentTimeMillis(),cash.size,active.size,enriched,top.map{it.first},active,perfs,bundle.version,
            "${active.size} strategies • ${selected.size} symbols • ${enriched} enriched • ${quoteRejected} liquidity rejects • ${historyFailed} history failures • ${candleShort} short histories • ${rulesMatched} rule matches • ${surviving.size} LIVE • ${newlyOpened.size} new • ${top.size} watching")
        DiagnosticLog.log(appContext,"STRATEGY","${summary.message}")
        prefs.saveStrategySummary(summary);prefs.clearStrategyError();summary
    }


    suspend fun refreshGlobalMappings(force:Boolean=false):Int{
        val settings=prefs.loadSettings();val now=System.currentTimeMillis();val last=prefs.lastGlobalMappingRefreshAt()
        val due=last==0L||now-last>=settings.globalMappingRefreshDays.coerceIn(1,30).toLong()*24*60*60*1000
        val weekend=ZonedDateTime.now(ist).dayOfWeek in setOf(DayOfWeek.SATURDAY,DayOfWeek.SUNDAY)
        if(!force&&!due){if(globalMappings==null)globalMappings=globalMarket.loadMappings(preferRemote=false);return globalMappings!!.mappings.size}
        if(!force&&last>0&&!weekend){if(globalMappings==null)globalMappings=globalMarket.loadMappings(preferRemote=false);return globalMappings!!.mappings.size}
        val bundle=globalMarket.loadMappings(preferRemote=true)
        globalMappings=bundle; prefs.setLastGlobalMappingRefreshAt(now);prefs.setGlobalMappingVersion(bundle.version)
        return bundle.mappings.size
    }

    suspend fun scanGlobalLead(progress:suspend(String)->Unit={}):GlobalLeadSummary=globalMutex.withLock{
        val settings=prefs.loadSettings()
        if(globalMappings==null)runCatching{refreshGlobalMappings(false)}
        val bundle=globalMappings?:globalMarket.loadMappings(preferRemote=false).also{globalMappings=it}
        progress("Global Lead: checking ${bundle.mappings.size} global links for LONG + SHORT")
        val benchmarks=linkedMapOf<String,GlobalQuoteSnapshot?>()
        for(t in bundle.mappings.map{it.benchmarkTicker}.filter{it.isNotBlank()}.distinct()){benchmarks[t]=runCatching{globalMarket.snapshot(t)}.getOrNull()}
        val foreign=mutableListOf<Pair<GlobalCounterpart,GlobalQuoteSnapshot>>()
        var loaded=0
        for((idx,m) in bundle.mappings.withIndex()){
            val f=runCatching{globalMarket.snapshot(m.foreignTicker)}.getOrNull()
            if(f!=null){loaded++;foreign+=m to f}
            if(idx%8==7)progress("Global Lead: foreign data ${idx+1}/${bundle.mappings.size}")
        }
        val limit=maxOf(settings.globalTopCandidates*2,16)
        val prelimLong=foreign.filter{globalLeadEngine.inferDirection(it.second,benchmarks[it.first.benchmarkTicker])==GlobalLeadDirection.LONG}
            .sortedByDescending{globalLeadEngine.foreignScore(it.first,it.second,benchmarks[it.first.benchmarkTicker],GlobalLeadDirection.LONG).score}.distinctBy{it.first.indianSymbol}.take(limit)
        val prelimShort=foreign.filter{globalLeadEngine.inferDirection(it.second,benchmarks[it.first.benchmarkTicker])==GlobalLeadDirection.SHORT}
            .sortedByDescending{globalLeadEngine.foreignScore(it.first,it.second,benchmarks[it.first.benchmarkTicker],GlobalLeadDirection.SHORT).score}.distinctBy{it.first.indianSymbol}.take(limit)
        val tokenOk=ensureAutomationAuthentication();val token=if(tokenOk)accessToken() else ""
        val globalUniverse=if(instruments.cached().isEmpty())runCatching{instruments.refresh()}.getOrDefault(emptyList()) else instruments.cached()
        val globalEligible=globalUniverse.filter{ExecutionQuality.eligibleInstrument(it)}.associateBy{it.tradingSymbol}
        val pressure=lastSavedDualSummary()?.demand?.candidates?.associate{it.symbol to it.score}.orEmpty()
        val now=ZonedDateTime.now(ist)
        val indiaDay=now.dayOfWeek !in setOf(DayOfWeek.SATURDAY,DayOfWeek.SUNDAY)
        val indiaMarketOpen=indiaDay && !now.toLocalTime().isBefore(LocalTime.of(9,15)) && now.toLocalTime().isBefore(LocalTime.of(15,31))
        val finals=mutableListOf<GlobalLeadCandidate>()
        val selections=(prelimLong.map{Triple(it.first,it.second,GlobalLeadDirection.LONG)}+prelimShort.map{Triple(it.first,it.second,GlobalLeadDirection.SHORT)})
        val quoteCache=mutableMapOf<String,Quote?>();val priorCache=mutableMapOf<String,Double?>()
        for((idx,triple) in selections.withIndex()){
            val(m,f,direction)=triple
            val inst=globalEligible[m.indianSymbol]?:continue
            if(direction==GlobalLeadDirection.SHORT&&!inst.sellAllowed)continue
            val q=quoteCache.getOrPut(m.indianSymbol){if(tokenOk)runCatching{groww.getQuote(token,m.indianSymbol)}.getOrNull() else null}
            // During NSE hours this must be an executable Indian quote. Outside NSE hours, empty depth
            // is normal; Global Lead is research-only and may proceed using the last Indian reference
            // price (or no Indian price at all) until the 09:15 live confirmation pass.
            if(indiaMarketOpen && (q==null||!ExecutionQuality.executableQuote(q)))continue
            if(!indiaMarketOpen && q!=null && (!q.lastPrice.isFinite()||q.lastPrice<ExecutionQuality.MIN_PRICE))continue
            val priorKey="${m.indianSymbol}|${f.marketTimestamp}"
            val prior=if(priorCache.containsKey(priorKey))priorCache[priorKey] else (if(tokenOk)runCatching{priorIndianReturnBefore(token,m.indianSymbol,f.marketTimestamp)}.getOrNull() else null).also{priorCache[priorKey]=it}
            finals+=globalLeadEngine.finalCandidate(m,f,benchmarks[m.benchmarkTicker],q,prior,pressure[m.indianSymbol],settings,now,direction)
            if(idx%5==4)progress("Global Lead: India confirmation ${idx+1}/${selections.size}")
        }
        val learnedFinals=finals.map{c->
            val adj=prefs.globalScoreAdjustment(globalLearningKey(c))
            if(kotlin.math.abs(adj)<0.05)c else c.copy(
                score=(c.score+adj).coerceIn(0.0,100.0),
                reasons=(c.reasons+"Local learning ${if(adj>=0)"+" else ""}${"%.1f".format(adj)} score").take(6)
            )
        }
        val perSide=settings.globalTopCandidates.coerceIn(10,20)
        fun ranked(direction:GlobalLeadDirection)=learnedFinals.filter{it.direction==direction}
            .sortedWith(compareByDescending<GlobalLeadCandidate>{actionPriority(it.action)}.thenByDescending{it.score})
            .take(perSide).mapIndexed{i,c->c.copy(rank=i+1)}
        val longs=ranked(GlobalLeadDirection.LONG);val shorts=ranked(GlobalLeadDirection.SHORT)
        val previousSummary=prefs.loadGlobalLeadSummary()
        val previousCandidates=previousSummary?.candidates.orEmpty()
        val previousLive=if(indiaMarketOpen) previousCandidates.filter{c->
            c.action==GlobalLeadAction.ENTER_AFTER_OPEN &&
                runCatching{Instant.ofEpochMilli(c.generatedAt).atZone(ist).toLocalDate()==now.toLocalDate()}.getOrDefault(false)
        } else emptyList()
        val currentTop=longs+shorts
        val currentKeys=currentTop.map{"${it.direction.name}|${it.indianSymbol}"}.toSet()
        val retained=previousLive.filter{"${it.direction.name}|${it.indianSymbol}" !in currentKeys}
        val top=(currentTop+retained).sortedWith(compareByDescending<GlobalLeadCandidate>{actionPriority(it.action)}.thenByDescending{it.score})
        val actionableLong=top.count{it.direction==GlobalLeadDirection.LONG&&(it.action==GlobalLeadAction.ENTER_AFTER_OPEN||it.action==GlobalLeadAction.KEEP_NEXT_SESSION||it.action==GlobalLeadAction.NEXT_OPEN_WATCH)}
        val actionableShort=top.count{it.direction==GlobalLeadDirection.SHORT&&(it.action==GlobalLeadAction.ENTER_AFTER_OPEN||it.action==GlobalLeadAction.KEEP_NEXT_SESSION||it.action==GlobalLeadAction.NEXT_OPEN_WATCH)}
        val previous=previousCandidates.map{"${it.direction.name} ${it.indianSymbol}"}.toSet()
        val current=top.map{"${it.direction.name} ${it.indianSymbol}"}.toSet();val dropped=(previous-current).sorted()
        fun isLiveAction(c:GlobalLeadCandidate)=c.action==GlobalLeadAction.ENTER_AFTER_OPEN||c.action==GlobalLeadAction.KEEP_NEXT_SESSION
        val currentLiveKeys=top.filter(::isLiveAction).map{"${it.direction.name}|${it.indianSymbol}"}.toSet()
        val closedNow=previousCandidates.filter(::isLiveAction).filter{"${it.direction.name}|${it.indianSymbol}" !in currentLiveKeys}.map{c->
            GlobalLeadClosedRecord(c,System.currentTimeMillis(),if(now.toLocalTime()>LocalTime.of(15,30))"Session closed" else "Signal no longer confirmed")
        }
        prefs.appendGlobalLeadClosed(closedNow)
        if(closedNow.isNotEmpty())DiagnosticLog.log(appContext,"GLOBAL","closed ${closedNow.size}: ${closedNow.joinToString{it.candidate.indianSymbol}}")
        val nextCount=top.count{it.action==GlobalLeadAction.NEXT_OPEN_WATCH}
        val liveCount=top.count{it.action==GlobalLeadAction.ENTER_AFTER_OPEN||it.action==GlobalLeadAction.KEEP_NEXT_SESSION}
        val summary=GlobalLeadSummary(System.currentTimeMillis(),bundle.version,bundle.mappings.size,loaded,top,
            "NEXT $nextCount • LIVE $liveCount • LONG $actionableLong • SHORT $actionableShort • foreign ${loaded}/${bundle.mappings.size}","09:15 IST",dropped)
        top.filter{it.action==GlobalLeadAction.WAIT_FOR_CONFIRMATION||it.action==GlobalLeadAction.OBSERVE}.take(8)
            .forEach{c->recordRejectedGlobalShadow(c,indiaMarketOpen,"GLOBAL_CONFIRMATION_GATE ${c.action.name}",summary.generatedAt)}
        recordGlobalCalls(top,indiaMarketOpen,summary.generatedAt)
        prefs.saveGlobalLeadSummary(summary);summary
    }

    private fun globalLearningKey(c:GlobalLeadCandidate)="${c.direction.name}|${c.mappingType.name}|${c.foreignTicker}"

    private fun actionPriority(a:GlobalLeadAction)=when(a){
        GlobalLeadAction.ENTER_AFTER_OPEN->6;GlobalLeadAction.KEEP_NEXT_SESSION->5;GlobalLeadAction.NEXT_OPEN_WATCH->4;
        GlobalLeadAction.WAIT_FOR_CONFIRMATION->3;GlobalLeadAction.OBSERVE->2;GlobalLeadAction.EXIT_BY_3PM->1
    }

    private suspend fun priorIndianReturnBefore(token:String,symbol:String,signalAtMs:Long):Double?{
        if(signalAtMs<=0)return null
        val signalDate=Instant.ofEpochMilli(signalAtMs).atZone(ist).toLocalDate()
        val start=signalDate.minusDays(12).atStartOfDay().format(dateTimeFmt);val end=signalDate.plusDays(2).atStartOfDay().format(dateTimeFmt)
        val candles=groww.getHistoricalCandles(token,symbol,start,end,"1day").filter{it.epochSeconds*1000L<signalAtMs}.sortedBy{it.epochSeconds}
        if(candles.size<2)return null
        val a=candles[candles.lastIndex-1].close;val b=candles.last().close
        return if(a>0)(b/a-1.0)*100.0 else null
    }

    suspend fun scanAll(progress:suspend(String)->Unit={}):DualScanSummary=scanMutex.withLock{
        val nowMs=System.currentTimeMillis();val cached=lastDualSummary
        if(cached!=null&&nowMs-lastDualScanAt<dualScanReuseMs){progress("Reusing the recent rate-safe scan snapshot");return@withLock cached}
        require(ensureAutomationAuthentication()){ "Groww authentication is required. TOTP mode can renew automatically after the first authentication." }
        val token=secureStore.accessToken()
        val settings=prefs.loadSettings();if(settings.learningEnabled)evaluateDueOutcomes(token);prefs.pruneMemory(settings.memoryRetentionDays)
        val universe=if(instruments.cached().isEmpty())instruments.refresh() else instruments.cached()
        val listings=runCatching{refreshNewListings()}.getOrDefault(newListingsCache)
        val allowedSeries=if(settings.includeSmeSeries)setOf("EQ","BE","BZ","SM","ST") else setOf("EQ","BE","BZ")
        val symbols=universe.asSequence().filter{it.exchange=="NSE"&&it.segment=="CASH"&&it.series in allowedSeries&&it.buyAllowed}.map{it.tradingSymbol}.distinct().toList()
        progress("Preparing one shared rate-safe market snapshot");groww.prefetchOhlcSnapshot(token,symbols,progress)
        progress("Section 1/2: upper-circuit continuation")
        val uc=ucScanner.scan(token,universe,listings,settings,prefs.adaptivePrecisionMap(ScannerSection.UC_CONTINUATION,SignalEngine.MODEL_VERSION),progress,
            rejectedShadow={c,reason->recordRejectedCandidateShadow(ScannerSection.UC_CONTINUATION,TradeCallBucket.LIVE,c,reason)})
        prefs.saveLastScan(uc)
        progress("Section 2/2: pre-pressure spike prediction")
        val demand=demandScanner.scan(token,universe,listings,settings,prefs.adaptivePrecisionMap(ScannerSection.DEMAND_SQUEEZE,DemandSignalEngine.MODEL_VERSION),progress,
            rejectedShadow={c,reason->recordRejectedCandidateShadow(ScannerSection.DEMAND_SQUEEZE,TradeCallBucket.LIVE,c,reason)})
        prefs.saveLastScan(demand)
        val scanNow=ZonedDateTime.now(ist);val scanNowMs=System.currentTimeMillis()
        if(!uc.message.startsWith("WATCHLIST ONLY"))recordCandidateCalls(ScannerSection.UC_CONTINUATION,TradeCallBucket.LIVE,uc.candidates,"UC live scan",scanNowMs)
        if(!demand.message.startsWith("WATCHLIST ONLY"))recordCandidateCalls(ScannerSection.DEMAND_SQUEEZE,TradeCallBucket.LIVE,demand.candidates,"Pressure live scan",scanNowMs)
        if(scanNow.toLocalTime()>=LocalTime.of(15,0)&&scanNow.toLocalTime()<=LocalTime.of(15,30)&&!uc.message.startsWith("WATCHLIST ONLY")&&uc.candidates.isNotEmpty()){
            val alreadyThreePm=prefs.loadTradeCalls(1500).any{it.engine==TradeCallEngine.UPPER_CIRCUIT&&it.bucket==TradeCallBucket.THREE_PM&&Instant.ofEpochMilli(it.openedAt).atZone(ist).toLocalDate()==scanNow.toLocalDate()}
            if(!alreadyThreePm)recordCandidateCalls(ScannerSection.UC_CONTINUATION,TradeCallBucket.THREE_PM,uc.candidates.take(settings.maxFinalCandidates.coerceAtLeast(1)),"UC 3 PM final list",scanNowMs)
        }
        DualScanSummary(uc,demand,listings).also{summary->lastDualSummary=summary;lastDualScanAt=maxOf(uc.completedAt,demand.completedAt)}
    }

    suspend fun scanUpperCircuitNextSession(progress:suspend(String)->Unit={}):ScanSummary=scanMutex.withLock{
        require(ensureAutomationAuthentication()){ "Groww authentication is required for next-session UC research" }
        val token=secureStore.accessToken();val settings=prefs.loadSettings()
        val universe=if(instruments.cached().isEmpty())instruments.refresh() else instruments.cached()
        val listings=if(newListingsCache.isEmpty())runCatching{refreshNewListings()}.getOrDefault(emptyList()) else newListingsCache
        val symbols=universe.asSequence().filter{ExecutionQuality.eligibleInstrument(it)}.map{it.tradingSymbol}.distinct().toList()
        progress("UC next-session: preparing latest completed-market snapshot")
        groww.prefetchOhlcSnapshot(token,symbols,progress)
        val uc=ucScanner.scan(token,universe,listings,settings,prefs.adaptivePrecisionMap(ScannerSection.UC_CONTINUATION,SignalEngine.MODEL_VERSION),progress,nextSessionMode=true,
            rejectedShadow={c,reason->recordRejectedCandidateShadow(ScannerSection.UC_CONTINUATION,TradeCallBucket.NEXT_SESSION,c,reason)})
        prefs.saveLastScan(uc)
        val now=ZonedDateTime.now(ist)
        var predictionDate=if(now.toLocalTime()<LocalTime.of(9,15))now.toLocalDate().minusDays(1) else now.toLocalDate()
        while(predictionDate.dayOfWeek==DayOfWeek.SATURDAY||predictionDate.dayOfWeek==DayOfWeek.SUNDAY)predictionDate=predictionDate.minusDays(1)
        prefs.saveFreezeRecord(predictionDate.toString(),ScannerSection.UC_CONTINUATION,uc.candidates,if(uc.candidates.isEmpty())FreezeOutcome.NO_SIGNAL else FreezeOutcome.PICKS,uc.completedAt,"Autonomous next-session UC research snapshot")
        if(uc.message.startsWith("NEXT SESSION •"))recordCandidateCalls(ScannerSection.UC_CONTINUATION,TradeCallBucket.NEXT_SESSION,uc.candidates,"PRE-UC next-session prediction",System.currentTimeMillis())
        val demand=prefs.loadLastScan(ScannerSection.DEMAND_SQUEEZE)?:ScanSummary(ScannerSection.DEMAND_SQUEEZE,uc.startedAt,uc.completedAt,0,0,0,emptyList(),0,"Market-hours pressure engine")
        lastDualSummary=DualScanSummary(uc,demand,listings);lastDualScanAt=uc.completedAt
        DiagnosticLog.log(appContext,"UC-NEXT","candidates=${uc.candidates.size} msg=${uc.message}")
        uc
    }

    suspend fun scanDemandOnly(progress:suspend(String)->Unit={}):ScanSummary=scanMutex.withLock{
        require(ensureAutomationAuthentication()){ "Groww authentication is required. TOTP mode can renew automatically after the first authentication." }
        val token=secureStore.accessToken()
        val settings=prefs.loadSettings();val universe=if(instruments.cached().isEmpty())instruments.refresh() else instruments.cached()
        val listings=if(newListingsCache.isEmpty())runCatching{refreshNewListings()}.getOrDefault(emptyList()) else newListingsCache
        // Frequent background passes still pre-screen the full NSE cash universe, but cap expensive
        // quote/history enrichment to 60 leaders so a 15-minute cadence remains rate-safe.
        val backgroundSettings=settings.copy(maxQuotesPerScan=minOf(settings.maxQuotesPerScan,60))
        val summary=demandScanner.scan(token,universe,listings,backgroundSettings,prefs.adaptivePrecisionMap(ScannerSection.DEMAND_SQUEEZE,DemandSignalEngine.MODEL_VERSION),progress,
            rejectedShadow={c,reason->recordRejectedCandidateShadow(ScannerSection.DEMAND_SQUEEZE,TradeCallBucket.LIVE,c,reason)})
        prefs.saveLastScan(summary);summary
    }

    suspend fun replay(symbol:String,days:Long=30):ReplayResult{
        require(ensureAutomationAuthentication()){ "Groww authentication is required" }
        return replay.replaySymbol(accessToken(),symbol.trim().uppercase(),days)
    }

    fun freezeToday(section:ScannerSection,candidates:List<Candidate>,message:String="Manual freeze"){
        val date=LocalDate.now(ist);val summary=prefs.loadLastScan(section);val sourceAt=summary?.completedAt?:System.currentTimeMillis()
        val outcome=if(candidates.isEmpty())FreezeOutcome.NO_SIGNAL else FreezeOutcome.PICKS
        prefs.saveFreezeRecord(date.toString(),section,candidates,outcome,sourceAt,message)
    }

    fun ensureTodayFreezeAudit(now:ZonedDateTime=ZonedDateTime.now(ist)){
        val session=marketSessionInfo(now);if(!session.isTradingDay)return
        val freeze=LocalTime.of(15,30)
        if(now.toLocalTime()<freeze)return
        val date=now.toLocalDate();val dateKey=date.toString()
        for(section in ScannerSection.entries){
            val existing=prefs.freezeRecord(dateKey,section)
            if(existing.recorded && existing.outcome!=FreezeOutcome.NO_DATA)continue
            val last=prefs.loadLastScan(section)
            val valid=last!=null && Instant.ofEpochMilli(last.completedAt).atZone(ist).toLocalDate()==date && Instant.ofEpochMilli(last.completedAt).atZone(ist).toLocalTime()>=LocalTime.of(14,45)
            if(valid){
                val list=last!!.candidates;val outcome=if(list.isEmpty())FreezeOutcome.NO_SIGNAL else FreezeOutcome.PICKS
                prefs.saveFreezeRecord(dateKey,section,list,outcome,last.completedAt,if(list.isEmpty())"End-of-day audit: scan completed, no qualifying signal" else "End-of-day audit: latest live scan closed")
            }else{
                // WorkManager is inexact. Allow a brief post-close grace window for the final market scan.
                if(now.toLocalTime()<LocalTime.of(15,40))continue
                prefs.saveFreezeRecord(dateKey,section,emptyList(),FreezeOutcome.NO_DATA,last?.completedAt?:0L,"End-of-day audit: no valid late-session scan was available")
            }
        }
        val pressureLast=prefs.loadLastScan(ScannerSection.DEMAND_SQUEEZE)
        if(pressureLast!=null&&pressureLast.candidates.isNotEmpty()&&pressureLast.message.startsWith("WATCHLIST ONLY")){
            recordCandidateCalls(ScannerSection.DEMAND_SQUEEZE,TradeCallBucket.NEXT_SESSION,pressureLast.candidates,"Pressure next-session watch",System.currentTimeMillis())
        }
    }

    fun frozenToday(section:ScannerSection):List<Candidate> = freezeRecordToday(section).candidates

    suspend fun runPostTradeAutopsies(limit:Int=10):Int{
        if(limit<=0||!ensureAutomationAuthentication())return 0
        val token=accessToken();val existing=prefs.loadAutopsies(1000).map{it.sourceId}.toHashSet()
        val closedCalls=prefs.loadTradeCalls(1500).filter{it.outcome!=TradeCallOutcome.OPEN&&it.id !in existing}
            .sortedWith(compareByDescending<TradeCallRecord>{it.outcome==TradeCallOutcome.LOSS}.thenByDescending{it.closedAt}).take(limit)
        val left=(limit-closedCalls.size).coerceAtLeast(0)
        val closedStrategies=prefs.loadStrategyClosed(500).filter{"STRATEGY|${it.id}" !in existing}
            .sortedWith(compareByDescending<StrategyRecommendation>{it.status==StrategyRecommendationStatus.LOSS}.thenByDescending{it.closedAt}).take(left)
        if(closedCalls.isEmpty()&&closedStrategies.isEmpty())return 0

        val nifty=runCatching{globalMarket.intradaySeries("^NSEI")}.getOrDefault(emptyList())
        val sensex=runCatching{globalMarket.intradaySeries("^BSESN")}.getOrDefault(emptyList())
        val bank=runCatching{globalMarket.intradaySeries("^NSEBANK")}.getOrDefault(emptyList())
        val indiaVix=runCatching{globalMarket.snapshot("^INDIAVIX")}.getOrNull()
        val spy=runCatching{globalMarket.snapshot("SPY")}.getOrNull()
        val globalVix=runCatching{globalMarket.snapshot("^VIX")}.getOrNull()
        val marketNews=runCatching{news.marketContext(35)}.getOrDefault(emptyList())
        var saved=0

        for(call in closedCalls){
            val targetDate=runCatching{LocalDate.parse(call.targetSessionDate)}.getOrNull()?:continue
            val opened=Instant.ofEpochMilli(call.openedAt).atZone(ist)
            val sessionStart=targetDate.atTime(9,15).atZone(ist)
            val executionStart=if(call.bucket==TradeCallBucket.LIVE&&opened.toLocalDate()==targetDate&&opened.isAfter(sessionStart))opened else sessionStart
            val end=Instant.ofEpochMilli(call.closedAt.takeIf{it>0}?:targetDate.atTime(15,31).atZone(ist).toInstant().toEpochMilli()).atZone(ist)
            val fetchStart=executionStart.minusMinutes(65);val fetchEnd=maxOf(end,executionStart.plusMinutes(30))
            val candles=runCatching{groww.getHistoricalCandles(token,call.symbol,fetchStart.format(dateTimeFmt),fetchEnd.format(dateTimeFmt),"5minute")}.getOrNull()?:continue
            val context=if(call.outcome==TradeCallOutcome.LOSS)runCatching{news.contextual(call.symbol,call.companyName,10)}.getOrDefault(emptyList()) else emptyList()
            val record=autopsyEngine.analyze(TradeAutopsyEngine.Input(
                sourceId=call.id,engineLabel=call.engine.name,symbol=call.symbol,outcome=call.outcome.name,originalReturnPct=call.returnPct,direction=call.direction,
                entryPrice=call.entryPrice,stopPrice=call.stopPrice,targetPrice=call.targetPrice,openedAt=call.openedAt,executionStartAt=executionStart.toInstant().toEpochMilli(),closedAt=call.closedAt,
                sessionDate=targetDate.toString(),stockCandles=candles,niftyBars=nifty,sensexBars=sensex,bankBars=bank,indiaVix=indiaVix,spy=spy,globalVix=globalVix,news=(context+marketNews).distinctBy{it.title}
            ))
            prefs.saveAutopsy(record);saved++
        }

        for(r in closedStrategies){
            val s=r.setup;val sourceId="STRATEGY|${r.id}";val opened=Instant.ofEpochMilli(r.openedAt).atZone(ist);val sessionDate=opened.toLocalDate();val executionStart=opened
            val end=Instant.ofEpochMilli(r.closedAt.takeIf{it>0}?:sessionDate.atTime(15,31).atZone(ist).toInstant().toEpochMilli()).atZone(ist)
            val candles=runCatching{groww.getHistoricalCandles(token,s.symbol,opened.minusMinutes(65).format(dateTimeFmt),maxOf(end,opened.plusMinutes(30)).format(dateTimeFmt),"5minute")}.getOrNull()?:continue
            val target=if(s.direction==TradeDirection.LONG)s.entryPrice*(1+s.targetPct/100.0) else s.entryPrice*(1-s.targetPct/100.0)
            val stop=if(s.direction==TradeDirection.LONG)s.entryPrice*(1-s.stopPct/100.0) else s.entryPrice*(1+s.stopPct/100.0)
            val outcome=if(r.status==StrategyRecommendationStatus.WIN)"WIN" else "LOSS"
            val context=if(outcome=="LOSS")runCatching{news.contextual(s.symbol,s.symbol,8)}.getOrDefault(emptyList()) else emptyList()
            val record=autopsyEngine.analyze(TradeAutopsyEngine.Input(sourceId,"STRATEGY",s.symbol,outcome,r.returnPct,s.direction,s.entryPrice,stop,target,r.openedAt,executionStart.toInstant().toEpochMilli(),r.closedAt,sessionDate.toString(),candles,nifty,sensex,bank,indiaVix,spy,globalVix,(context+marketNews).distinctBy{it.title}))
            prefs.saveAutopsy(record);saved++
        }
        if(saved>0)DiagnosticLog.log(appContext,"AUTOPSY","Generated $saved post-trade autopsies with regime + shadow-strategy replay")
        return saved
    }

    suspend fun runLearningCycle():Map<ScannerSection,SectionAccuracy>{
        val settings=prefs.loadSettings()
        if(settings.learningEnabled && ensureAutomationAuthentication()){
            evaluateDueOutcomes(accessToken())
            evaluatePendingStrategyOutcomes(accessToken())
            prefs.setLastLearningAt(System.currentTimeMillis())
        }
        prefs.pruneMemory(settings.memoryRetentionDays)
        return accuracies()
    }

    suspend fun runAutonomousLearningPass(force:Boolean=false):String{
        val settings=prefs.loadSettings();if(!settings.learningEnabled)return "Learning disabled"
        val now=System.currentTimeMillis();val last=prefs.lastAutonomousLearningAt()
        if(!force&&last>0&&now-last<14L*60_000L)return "Learning pass not due"
        val auth=ensureAutomationAuthentication()
        if(auth){
            runCatching{closeExpiredStrategyCalls()}.onFailure{DiagnosticLog.log(appContext,"LEARNING15M","Strategy ledger reconciliation failed",it)}
            runCatching{reconcileTradeCallLedger()}.onFailure{DiagnosticLog.log(appContext,"LEARNING15M","Trade call ledger reconciliation failed",it)}
            runCatching{reconcileRejectedShadows()}.onFailure{DiagnosticLog.log(appContext,"LEARNING15M","Rejected-candidate shadow reconciliation failed",it)}
            runCatching{runLearningCycle()}.onFailure{DiagnosticLog.log(appContext,"LEARNING15M","Outcome evaluation failed",it)}
            runCatching{runPostTradeAutopsies(10)}.onFailure{DiagnosticLog.log(appContext,"LEARNING15M","Post-trade autopsy failed",it)}
        }
        maybeAdaptDailySettings()
        val uc=prefs.sectionAccuracy(ScannerSection.UC_CONTINUATION,SignalEngine.MODEL_VERSION)
        val pressure=prefs.sectionAccuracy(ScannerSection.DEMAND_SQUEEZE,DemandSignalEngine.MODEL_VERSION)
        val strategySummary=prefs.loadStrategySummary();val live=prefs.loadStrategyLive().size;val closed=prefs.loadStrategyClosed(500)
        val globalLive=prefs.loadGlobalLeadSummary()?.candidates.orEmpty().count{it.action==GlobalLeadAction.ENTER_AFTER_OPEN||it.action==GlobalLeadAction.KEEP_NEXT_SESSION||it.action==GlobalLeadAction.NEXT_OPEN_WATCH}
        val ledger=prefs.loadTradeCalls(1500);val ucDone=ledger.filter{it.engine==TradeCallEngine.UPPER_CIRCUIT&&it.outcome!=TradeCallOutcome.OPEN};val prDone=ledger.filter{it.engine==TradeCallEngine.PRESSURE&&it.outcome!=TradeCallOutcome.OPEN};val glDone=ledger.filter{it.engine==TradeCallEngine.GLOBAL&&it.outcome!=TradeCallOutcome.OPEN}
        val champions=strategySummary?.performances?.count{it.status==StrategyStatus.CHAMPION}?:0
        fun wl(x:List<TradeCallRecord>)="${x.count{it.outcome==TradeCallOutcome.WIN}}/${x.size}"
        val autopsies=prefs.loadAutopsies(800);val lossesExplained=autopsies.count{it.originalOutcome=="LOSS"&&it.dominantCause!=AutopsyCause.NO_DOMINANT_CAUSE}
        val rejected=prefs.loadRejectedShadows(2500);val missed=rejected.count{it.outcome==RejectedShadowOutcome.WOULD_WIN}
        val msg="auth=$auth • UC calls ${wl(ucDone)} • Pressure calls ${wl(prDone)} • Strategies live=$live closed=${closed.size} champions=$champions • Global active=$globalLive calls ${wl(glDone)} • autopsies=${autopsies.size} loss-diagnostics=$lossesExplained • rejected-shadow=${rejected.size} missed-winners=$missed"
        prefs.setLastAutonomousLearningAt(now)
        DiagnosticLog.log(appContext,"LEARNING15M",msg)
        return msg
    }

    private fun maybeAdaptDailySettings(){
        val today=LocalDate.now(ist).toString();if(prefs.lastAutoTuneDate()==today)return
        val current=prefs.loadSettings();val uc=prefs.sectionAccuracy(ScannerSection.UC_CONTINUATION,SignalEngine.MODEL_VERSION);val pr=prefs.sectionAccuracy(ScannerSection.DEMAND_SQUEEZE,DemandSignalEngine.MODEL_VERSION)
        val cutoff=System.currentTimeMillis()-24L*60*60*1000;val ledger=prefs.loadTradeCalls(1500)
        fun callStats(engine:TradeCallEngine):Pair<Int,Double>{val d=ledger.filter{it.engine==engine&&it.outcome!=TradeCallOutcome.OPEN&&it.closedAt>=cutoff};return d.size to if(d.isEmpty())0.0 else d.count{it.outcome==TradeCallOutcome.WIN}*100.0/d.size}
        fun tune(base:Double,a:SectionAccuracy,engine:TradeCallEngine,lo:Double,hi:Double):Double{
            val(n,acc)=callStats(engine);val samples=if(n>0)n else a.last24hEvaluated;val accuracy=if(n>0)acc else a.last24hAccuracyPct
            return when{samples>=3&&accuracy<45.0->(base+2.0).coerceAtMost(hi);samples>=5&&accuracy>=75.0->(base-1.0).coerceAtLeast(lo);else->base}
        }
        val ucBase=tune(current.minScore,uc,TradeCallEngine.UPPER_CIRCUIT,60.0,84.0);val prBase=tune(current.demandMinScore,pr,TradeCallEngine.PRESSURE,62.0,86.0)
        val ucAutopsy=prefs.autopsyThresholdAdjustment(TradeCallEngine.UPPER_CIRCUIT.name);val prAutopsy=prefs.autopsyThresholdAdjustment(TradeCallEngine.PRESSURE.name)
        // Calibration can tighten/relax only after an unseen-period walk-forward pass is stable.
        val ucCalibration=prefs.calibrationThresholdAdjustment(TradeCallEngine.UPPER_CIRCUIT.name);val prCalibration=prefs.calibrationThresholdAdjustment(TradeCallEngine.PRESSURE.name)
        val tuned=current.copy(minScore=(ucBase+ucAutopsy+ucCalibration).coerceIn(60.0,84.0),demandMinScore=(prBase+prAutopsy+prCalibration).coerceIn(62.0,86.0))
        if(tuned!=current){prefs.saveSettings(tuned);DiagnosticLog.log(appContext,"AUTOTUNE","UC ${current.minScore}->${tuned.minScore} (autopsy ${"%+.1f".format(ucAutopsy)}, calibration ${"%+.1f".format(ucCalibration)}) • Pressure ${current.demandMinScore}->${tuned.demandMinScore} (autopsy ${"%+.1f".format(prAutopsy)}, calibration ${"%+.1f".format(prCalibration)})")}
        prefs.setLastAutoTuneDate(today)
    }

    fun weeklyLearningReport():String=buildString{
        val uc=prefs.sectionAccuracy(ScannerSection.UC_CONTINUATION,SignalEngine.MODEL_VERSION);val pr=prefs.sectionAccuracy(ScannerSection.DEMAND_SQUEEZE,DemandSignalEngine.MODEL_VERSION)
        appendLine("--- LEARNING STATE ---")
        appendLine("UC accuracy: ${uc.hits}/${uc.evaluated} = ${"%.1f".format(uc.accuracyPct)}%")
        appendLine("Pressure accuracy: ${pr.hits}/${pr.evaluated} = ${"%.1f".format(pr.accuracyPct)}%")
        appendLine("Last autonomous learning: ${prefs.lastAutonomousLearningAt()}")
        appendLine("Current settings: ${prefs.loadSettings()}")
        appendLine("Strategy LIVE: ${prefs.loadStrategyLive().size} • CLOSED: ${prefs.loadStrategyClosed(500).size}")
        prefs.loadStrategySummary()?.performances?.sortedByDescending{it.observations}?.take(20)?.forEach{appendLine("Strategy ${it.strategyId} • n=${it.observations} • win=${"%.1f".format(it.accuracyPct)}% • avg=${"%.2f".format(it.avgReturnPct)}% • ${it.status}")}
        appendLine("Global LIVE/NEXT: ${prefs.loadGlobalLeadSummary()?.candidates.orEmpty().size} • CLOSED research signals: ${prefs.loadGlobalLeadClosed(500).size}")
        for(engine in TradeCallEngine.entries){
            val calls=prefs.loadTradeCalls(1500).filter{it.engine==engine};val done=calls.filter{it.outcome!=TradeCallOutcome.OPEN};val wins=done.count{it.outcome==TradeCallOutcome.WIN}
            appendLine("${engine.name} calls: open=${calls.count{it.outcome==TradeCallOutcome.OPEN}} closed=${done.size} wins=$wins losses=${done.size-wins} accuracy=${if(done.isEmpty())"0.0" else "%.1f".format(wins*100.0/done.size)}%")
        }
        prefs.globalLearningSummary().forEach{appendLine("Global $it")}
        appendLine("--- CALIBRATION + WALK-FORWARD ---")
        for(engine in listOf(TradeCallEngine.UPPER_CIRCUIT.name,TradeCallEngine.PRESSURE.name,TradeCallEngine.GLOBAL.name,"STRATEGY")){
            val wf=prefs.walkForwardValidation(engine);val cal=prefs.confidenceCalibration(engine,80.0)
            appendLine("$engine • 80-score calibrated=${"%.1f".format(cal.calibratedPct)}% bucket=${cal.bucketLabel} n=${cal.observations} reliable=${cal.reliable} • train=${wf.trainObservations}/${"%.1f".format(wf.trainWinRatePct)}% validation=${wf.validationObservations}/${"%.1f".format(wf.validationWinRatePct)}% • ${wf.note}")
        }
        appendLine("--- REJECTED-CANDIDATE SHADOW / MISSED OPPORTUNITIES ---")
        val rejected=prefs.loadRejectedShadows(2500);appendLine("Rejected shadows stored: ${rejected.size} • pending=${rejected.count{it.outcome==RejectedShadowOutcome.PENDING}} • would-win=${rejected.count{it.outcome==RejectedShadowOutcome.WOULD_WIN}} • would-lose=${rejected.count{it.outcome==RejectedShadowOutcome.WOULD_LOSE}}")
        rejected.filter{it.outcome==RejectedShadowOutcome.WOULD_WIN}.take(30).forEach{r->appendLine("MISSED ${r.targetSessionDate} • ${r.engineLabel} • ${r.symbol} • score=${"%.1f".format(r.score)} • ${r.reason} • shadow return ${"%+.2f".format(r.returnPct)}%")}
        appendLine("--- POST-TRADE AUTOPSY ---")
        val autopsies=prefs.loadAutopsies(800);appendLine("Autopsies stored: ${autopsies.size}")
        autopsies.take(30).forEach{a->
            appendLine("${a.sessionDate} • ${a.engineLabel} • ${a.symbol} • ${a.originalOutcome} ${"%+.2f".format(a.originalReturnPct)}% • regime=${a.regime} • cause=${a.dominantCause} ${"%.0f".format(a.causeConfidencePct)}%")
            a.newsEvidence.take(2).forEach{appendLine("  news: $it")};a.shadowResults.take(5).forEach{x->appendLine("  shadow ${x.strategyId}: ${x.outcome} ${"%+.2f".format(x.returnPct)}% • ${x.evidence}")}
            appendLine("  learning: ${a.recommendedRule}")
        }
        appendLine("--- SHADOW STRATEGY LAB ---")
        prefs.shadowLearningSummary(30).forEach{appendLine(it)}
    }

    fun endOfDayDiagnosticReport():String=buildString{
        val now=ZonedDateTime.now(ist)
        fun ts(ms:Long):String=if(ms<=0L)"never" else runCatching{Instant.ofEpochMilli(ms).atZone(ist).toString()}.getOrDefault(ms.toString())
        appendLine("=== GLOBAL EDGE END-OF-DAY STATE REPORT ===")
        appendLine("Generated IST: "+now)
        appendLine("Security: credentials/TOTP secret/access token omitted by design")
        appendLine("Authenticated token present: "+accessToken().isNotBlank()+" • expiry="+tokenExpiry())
        appendLine("Market session: "+marketSessionInfo(now))
        appendLine("Settings: "+prefs.loadSettings())
        appendLine()
        appendLine("--- SCHEDULER / DATA HEALTH ---")
        appendLine("lastMarketDataSuccessAt="+ts(prefs.lastMarketDataSuccessAt()))
        appendLine("lastPressureScanAt="+ts(prefs.lastPressureScanAt()))
        appendLine("lastNearCloseAutoScanAt="+ts(prefs.lastNearCloseAutoScanAt()))
        appendLine("lastLearningAt="+ts(prefs.lastLearningAt()))
        appendLine("lastAutonomousLearningAt="+ts(prefs.lastAutonomousLearningAt()))
        appendLine("lastGlobalLeadScanAt="+ts(prefs.lastGlobalLeadScanAt()))
        appendLine("lastGlobalMappingRefreshAt="+ts(prefs.lastGlobalMappingRefreshAt())+" • mappingVersion="+prefs.globalMappingVersion())
        appendLine("lastStrategyAttemptAt="+ts(prefs.lastStrategyAttemptAt()))
        appendLine("lastStrategyScanAt="+ts(prefs.lastStrategyScanAt()))
        appendLine("lastStrategyErrorAt="+ts(prefs.lastStrategyErrorAt())+" • lastStrategyError="+prefs.lastStrategyError())
        appendLine("lastStrategyCatalogRefreshAt="+ts(prefs.lastStrategyCatalogRefreshAt())+" • catalogVersion="+prefs.strategyCatalogVersion())
        appendLine("listingFeedHealth="+prefs.listingFeedHealth())
        appendLine()
        appendLine("--- CURRENT SCAN SUMMARIES ---")
        appendLine("DUAL_SCAN="+(lastSavedDualSummary()?.toString()?:"NONE"))
        appendLine("GLOBAL="+(prefs.loadGlobalLeadSummary()?.toString()?:"NONE"))
        appendLine("STRATEGY="+(prefs.loadStrategySummary()?.toString()?:"NONE"))
        appendLine()
        appendLine("--- MODEL ACCURACY / SIGNAL METRICS ---")
        appendLine("UC="+prefs.sectionAccuracy(ScannerSection.UC_CONTINUATION,SignalEngine.MODEL_VERSION))
        appendLine("PRESSURE="+prefs.sectionAccuracy(ScannerSection.DEMAND_SQUEEZE,DemandSignalEngine.MODEL_VERSION))
        prefs.signalMetrics().forEach{appendLine(it.toString())}
        appendLine()
        appendLine("--- FREEZE HISTORY ---")
        for(section in ScannerSection.entries){
            appendLine("SECTION="+section)
            prefs.freezeHistory(section,100).forEach{appendLine(it.toString())}
        }
        appendLine()
        val calls=prefs.loadTradeCalls(1500)
        appendLine("--- TRADE CALL LEDGER ("+calls.size+") ---")
        calls.sortedBy{it.openedAt}.forEach{appendLine(it.toString())}
        appendLine()
        val rejected=prefs.loadRejectedShadows(2500)
        appendLine("--- REJECTED / SHADOW CANDIDATES ("+rejected.size+") ---")
        rejected.sortedBy{it.capturedAt}.forEach{appendLine(it.toString())}
        appendLine()
        val autopsies=prefs.loadAutopsies(800)
        appendLine("--- POST-TRADE AUTOPSIES ("+autopsies.size+") ---")
        autopsies.forEach{appendLine(it.toString())}
        appendLine()
        val liveStrategy=prefs.loadStrategyLive()
        val closedStrategy=prefs.loadStrategyClosed(2000)
        appendLine("--- STRATEGY LIVE ("+liveStrategy.size+") ---")
        liveStrategy.forEach{appendLine(it.toString())}
        appendLine("--- STRATEGY CLOSED ("+closedStrategy.size+") ---")
        closedStrategy.forEach{appendLine(it.toString())}
        appendLine()
        val globalClosed=prefs.loadGlobalLeadClosed(2000)
        appendLine("--- GLOBAL CLOSED ("+globalClosed.size+") ---")
        globalClosed.forEach{appendLine(it.toString())}
        appendLine()
        appendLine("--- NEW LISTINGS CACHE ("+newListingsCache.size+") ---")
        newListingsCache.forEach{appendLine(it.toString())}
    }

    fun trimMemory(){newListingsCache=prefs.loadNewListings();instruments.clearCache();globalMarket.clearCache()}

    private fun loadLastDualFromDisk():DualScanSummary?{val uc=prefs.loadLastScan(ScannerSection.UC_CONTINUATION)?:return null;val d=prefs.loadLastScan(ScannerSection.DEMAND_SQUEEZE)?:return null;return DualScanSummary(uc,d,prefs.loadNewListings())}

    private suspend fun evaluateDueOutcomes(token:String){
        for(section in ScannerSection.entries){for(date in prefs.pendingFrozenDates(section)){
            val key=date.toString();val arr=prefs.getFrozenCandidates(key,section)?:continue;if(arr.length()==0)continue
            val first=arr.optJSONObject(0);val storedVersion=first?.optString("modelVersion").orEmpty().ifBlank{"LEGACY_UNVERSIONED"}
            if(prefs.isOutcomeEvaluated(key,section,storedVersion))continue
            var allProcessed=true
            for(i in 0 until arr.length()){
                val item=arr.optJSONObject(i)?:continue;val symbol=item.optString("symbol");if(symbol.isBlank())continue
                val candles=runCatching{dailyWindow(token,symbol,date)}.getOrNull();if(candles==null){allProcessed=false;continue}
                val exact=selectPredictionAndNext(candles,date);if(exact==null){allProcessed=false;continue};val(predictionDay,nextDay,previousDay)=exact
                val hit=when(section){
                    ScannerSection.DEMAND_SQUEEZE->{val frozenPrice=item.optDouble("price");val target=item.optNullableDouble("targetMovePct")?:prefs.loadSettings().demandSpikeTargetPct;frozenPrice>0&&nextDay.high>=frozenPrice*(1.0+target/100.0)}
                    ScannerSection.UC_CONTINUATION->{val storedUc=item.optDouble("upperCircuit");val bandPct=if(previousDay!=null&&previousDay.close>0&&storedUc>0)(storedUc/previousDay.close-1.0)*100.0 else 0.0;if(bandPct in 1.0..25.0&&predictionDay.close>0){val expectedNextUc=predictionDay.close*(1.0+bandPct/100.0);nextDay.high>=expectedNextUc*0.999}else{val ret=if(predictionDay.close<=0)0.0 else(nextDay.close/predictionDay.close-1.0)*100.0;val closeAtHigh=nextDay.close>0&&abs(nextDay.close-nextDay.high)/nextDay.close<0.0015;ret>=1.8&&closeAtHigh}}
                }
                val idsArray=item.optJSONArray("signalIds")?:JSONArray();val ids=buildList{for(k in 0 until idsArray.length()){val v=idsArray.optString(k);if(v.isNotBlank())add(v)}}
                prefs.updateLearning(section,storedVersion,ids,hit,item.optNullableDouble("targetMovePct"))
            }
            if(allProcessed)prefs.markOutcomeEvaluated(key,section,storedVersion)
        }}
    }


    private suspend fun evaluatePendingStrategyOutcomes(token:String){
        val today=LocalDate.now(ist)
        for(date in prefs.pendingStrategyDates().filter{it<today}){
            val key=date.toString();if(prefs.strategyDateEvaluated(key))continue
            val setups=prefs.pendingStrategySetups(key);if(setups.isEmpty()){prefs.markStrategyDateEvaluated(key);continue}
            var all=true
            for(x in setups){
                val candles=runCatching{dailyWindow(token,x.symbol,date)}.getOrNull();if(candles==null){all=false;continue}
                val dated=candles.map{Instant.ofEpochSecond(it.epochSeconds).atZone(ist).toLocalDate() to it}.sortedBy{it.first}
                val next=dated.firstOrNull{it.first>date}?.second;if(next==null){all=false;continue}
                val win=if(x.direction==TradeDirection.LONG)next.high>=x.entryPrice*(1+x.targetPct/100.0) else next.low<=x.entryPrice*(1-x.targetPct/100.0)
                val ret=if(x.entryPrice<=0)0.0 else if(x.direction==TradeDirection.LONG)(next.close/x.entryPrice-1)*100 else (x.entryPrice/next.close-1)*100
                prefs.updateStrategyResult(x.strategyId,x.strategyName,ret,win)
            }
            if(all)prefs.markStrategyDateEvaluated(key)
        }
    }

    private suspend fun dailyWindow(token:String,symbol:String,date:LocalDate):List<Candle>{val start=date.minusDays(3).atStartOfDay().format(dateTimeFmt);val end=date.plusDays(10).atStartOfDay().format(dateTimeFmt);return groww.getHistoricalCandles(token,symbol,start,end,"1day")}
    private fun selectPredictionAndNext(candles:List<Candle>,date:LocalDate):Triple<Candle,Candle,Candle?>?{val dated=candles.map{Instant.ofEpochSecond(it.epochSeconds).atZone(ist).toLocalDate() to it}.sortedBy{it.first};val prediction=dated.lastOrNull{it.first==date}?:return null;val next=dated.firstOrNull{it.first>date}?:return null;return Triple(prediction.second,next.second,dated.lastOrNull{it.first<date}?.second)}
    private fun JSONObject.optNullableDouble(name:String):Double?{if(!has(name)||isNull(name))return null;val v=optDouble(name,Double.NaN);return v.takeIf{!it.isNaN()}}
}

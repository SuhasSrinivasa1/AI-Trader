#!/usr/bin/env python3
from pathlib import Path
import sys

root=Path(sys.argv[1]).resolve()

def rw(p): return (root/p).read_text(encoding="utf-8")
def wr(p,s): (root/p).write_text(s,encoding="utf-8")
def one(s,old,new,label):
    n=s.count(old)
    if n!=1: raise SystemExit(f"{label}: expected 1 found {n}")
    return s.replace(old,new,1)

# Version.
p="app/build.gradle.kts"; s=rw(p)
s=one(s,"versionCode = 151","versionCode = 152","versionCode")
s=one(s,'versionName = "1.5.1"','versionName = "1.5.2"',"versionName")
wr(p,s)

# Application: keep startup minimal. Repository becomes lazy, workers are armed explicitly
# after the Activity is visible, and the persistent FGS is no longer started in Application.onCreate.
p="app/src/main/java/com/suhas/ucsentinel/GlobalEdgeApplication.kt"; s=rw(p)
s=s.replace("import com.suhas.globaledgeai.worker.MarketScanService\n","")
old='''class GlobalEdgeApplication:Application(){
    lateinit var repository:GlobalEdgeAITraderRepository; private set
    override fun onCreate(){super.onCreate();AppNotifier.ensureChannel(this);repository=GlobalEdgeAITraderRepository(this);scheduleWorkers();runCatching{MarketScanService.start(this)}.onFailure{DiagnosticLog.log(this,"APP","Foreground scanner start failed",it)}}
    private fun scheduleWorkers(){
'''
new='''class GlobalEdgeApplication:Application(){
    private val repositoryDelegate=lazy(LazyThreadSafetyMode.SYNCHRONIZED){GlobalEdgeAITraderRepository(this)}
    val repository:GlobalEdgeAITraderRepository get()=repositoryDelegate.value
    private var workersArmed=false

    override fun onCreate(){
        super.onCreate()
        runCatching{AppNotifier.ensureChannel(this)}
            .onFailure{DiagnosticLog.log(this,"APP","Notification channel initialization failed",it)}
        installCrashRecorder()
    }

    fun armBackgroundWorkers(){
        if(workersArmed)return
        runCatching{scheduleWorkers()}.onSuccess{
            workersArmed=true
            DiagnosticLog.log(this,"APP","Background WorkManager safety net armed after UI startup")
        }.onFailure{DiagnosticLog.log(this,"APP","Background worker scheduling failed",it)}
    }

    private fun installCrashRecorder(){
        val previous=Thread.getDefaultUncaughtExceptionHandler()
        Thread.setDefaultUncaughtExceptionHandler{thread,error->
            runCatching{
                val trace=error.stackTraceToString().take(12000)
                getSharedPreferences("global_edge_crash_guard",MODE_PRIVATE).edit()
                    .putLong("last_crash_at",System.currentTimeMillis())
                    .putString("last_crash_type",error::class.java.name)
                    .putString("last_crash_message",error.message.orEmpty().take(1000))
                    .putString("last_crash_trace",trace)
                    .commit()
            }
            previous?.uncaughtException(thread,error)
        }
    }

    fun lastCrashSummary():String{
        val p=getSharedPreferences("global_edge_crash_guard",MODE_PRIVATE)
        val type=p.getString("last_crash_type","").orEmpty()
        val message=p.getString("last_crash_message","").orEmpty()
        return if(type.isBlank())"" else type.substringAfterLast('.')+(if(message.isBlank())"" else ": "+message)
    }

    private fun scheduleWorkers(){
'''
s=one(s,old,new,"application staged startup")
old='''    override fun onTrimMemory(level:Int){super.onTrimMemory(level);if(level>=ComponentCallbacks2.TRIM_MEMORY_RUNNING_LOW)repository.trimMemory()}
}
'''
new='''    override fun onTrimMemory(level:Int){
        super.onTrimMemory(level)
        if(level>=ComponentCallbacks2.TRIM_MEMORY_RUNNING_LOW && repositoryDelegate.isInitialized()){
            runCatching{repository.trimMemory()}
        }
    }
}
'''
s=one(s,old,new,"application trim guard")
wr(p,s)

# MainActivity: render a recovery-safe UI even if repository construction itself fails.
p="app/src/main/java/com/suhas/ucsentinel/MainActivity.kt"; s=rw(p)
s=s.replace("import androidx.activity.compose.setContent\n","import androidx.activity.compose.setContent\nimport androidx.compose.foundation.layout.*\nimport androidx.compose.material3.*\nimport androidx.compose.ui.Modifier\nimport androidx.compose.ui.unit.dp\nimport androidx.lifecycle.lifecycleScope\nimport kotlinx.coroutines.delay\nimport kotlinx.coroutines.launch\n")
old='''    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
            checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            notificationPermission.launch(Manifest.permission.POST_NOTIFICATIONS)
        }

        val repo = (application as GlobalEdgeApplication).repository

        setContent {
            GlobalEdgeTheme {
                val vm: MainViewModel = viewModel(factory = MainViewModel.Factory(repo))
                AppNavigation(vm)
            }
        }
    }
'''
new='''    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        val app=application as GlobalEdgeApplication
        val repoResult=runCatching{app.repository}

        setContent {
            GlobalEdgeTheme {
                val repo=repoResult.getOrNull()
                if(repo==null){
                    Surface(Modifier.fillMaxSize()){
                        Column(
                            Modifier.fillMaxSize().padding(24.dp),
                            verticalArrangement=Arrangement.Center
                        ){
                            Text("Global Edge recovery mode",style=MaterialTheme.typography.headlineSmall)
                            Spacer(Modifier.height(12.dp))
                            Text("The trading engine could not initialize. Your app data has not been deleted.")
                            Spacer(Modifier.height(8.dp))
                            Text(
                                repoResult.exceptionOrNull()?.let{it::class.java.simpleName+": "+it.message.orEmpty()}.orEmpty(),
                                color=MaterialTheme.colorScheme.error
                            )
                            val prior=app.lastCrashSummary()
                            if(prior.isNotBlank()){
                                Spacer(Modifier.height(8.dp))
                                Text("Previous crash: "+prior,style=MaterialTheme.typography.bodySmall)
                            }
                        }
                    }
                }else{
                    val vm: MainViewModel = viewModel(factory = MainViewModel.Factory(repo))
                    AppNavigation(vm)
                }
            }
        }

        lifecycleScope.launch{
            delay(1_500L)
            if(Build.VERSION.SDK_INT>=Build.VERSION_CODES.TIRAMISU &&
                checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS)!=PackageManager.PERMISSION_GRANTED){
                runCatching{notificationPermission.launch(Manifest.permission.POST_NOTIFICATIONS)}
            }
            delay(2_500L)
            app.armBackgroundWorkers()
        }
    }
'''
s=one(s,old,new,"activity recovery-safe startup")
wr(p,s)

# ViewModel: no repository reads on constructor stack. Hydrate asynchronously after first frame.
p="app/src/main/java/com/suhas/ucsentinel/ui/MainViewModel.kt"; s=rw(p)
old='''class MainViewModel(private val repo:GlobalEdgeAITraderRepository):ViewModel(){
    private val _state=MutableStateFlow(buildInitialState())
'''
new='''class MainViewModel(private val repo:GlobalEdgeAITraderRepository):ViewModel(){
    private val _state=MutableStateFlow(UiState())
'''
s=one(s,old,new,"viewmodel default boot state")

old='''    init{
        runCatching{repo.ensureTodayFreezeAudit()}
        // Keep the visible market clock and persisted background results fresh while the app is open.
'''
new='''    init{
        // First frame is independent of disk/network/research state. Hydrate only after Compose is alive.
        viewModelScope.launch{
            delay(250L)
            runCatching{
                _state.value=_state.value.copy(
                    authenticated=repo.accessToken().isNotBlank(),
                    tokenExpiry=repo.tokenExpiry(),
                    credentials=repo.credentials(),
                    staticIp=repo.tradingStaticIp(),
                    settings=repo.settings()
                )
                reliabilityRefresh(status="Ready",error=null)
            }.onFailure{t->
                _state.value=_state.value.copy(
                    status="Recovery mode • some saved state could not be loaded",
                    error=t::class.java.simpleName+": "+t.message.orEmpty()
                )
            }
        }
        // Keep the visible market clock and persisted background results fresh while the app is open.
'''
s=one(s,old,new,"viewmodel staged hydrate")

# Make reliabilityRefresh granular enough that one malformed persisted ledger does not abort all state.
start=s.index("    private fun reliabilityRefresh(status:String?=null,error:String?=_state.value.error){")
end=s.index("\n    fun updateCredentials",start)
replacement='''    private fun reliabilityRefresh(status:String?=null,error:String?=_state.value.error){
        fun <T> safe(default:T,block:()->T):T=runCatching(block).getOrDefault(default)
        runCatching{repo.ensureTodayFreezeAudit()}
        val uc=safe(FreezeRecord(ScannerSection.UC_CONTINUATION,"",false)){repo.freezeRecordToday(ScannerSection.UC_CONTINUATION)}
        val d=safe(FreezeRecord(ScannerSection.DEMAND_SQUEEZE,"",false)){repo.freezeRecordToday(ScannerSection.DEMAND_SQUEEZE)}
        _state.value=_state.value.copy(
            status=status?:_state.value.status,error=error,
            authenticated=safe(_state.value.authenticated){repo.accessToken().isNotBlank()},
            tokenExpiry=safe(_state.value.tokenExpiry){repo.tokenExpiry()},
            credentials=safe(_state.value.credentials){repo.credentials()},
            staticIp=safe(_state.value.staticIp){repo.tradingStaticIp()},
            settings=safe(_state.value.settings){repo.settings()},
            dualSummary=safe(_state.value.dualSummary){repo.lastSavedDualSummary()},
            newListings=safe(_state.value.newListings){repo.newListings()},
            frozenUc=uc.candidates,frozenDemand=d.candidates,
            marketSession=safe(_state.value.marketSession){repo.marketSessionInfo()},
            listingFeedHealth=safe(_state.value.listingFeedHealth){repo.listingFeedHealth()},
            lastMarketDataSuccessAt=safe(_state.value.lastMarketDataSuccessAt){repo.lastMarketDataSuccessAt()},
            ucFreezeRecord=uc,demandFreezeRecord=d,
            ucFreezeHistory=safe(_state.value.ucFreezeHistory){repo.freezeHistory(ScannerSection.UC_CONTINUATION)},
            demandFreezeHistory=safe(_state.value.demandFreezeHistory){repo.freezeHistory(ScannerSection.DEMAND_SQUEEZE)},
            globalLeadSummary=safe(_state.value.globalLeadSummary){repo.globalLeadSummary()},
            lastGlobalLeadScanAt=safe(_state.value.lastGlobalLeadScanAt){repo.lastGlobalLeadScanAt()},
            lastGlobalMappingRefreshAt=safe(_state.value.lastGlobalMappingRefreshAt){repo.lastGlobalMappingRefreshAt()},
            globalMappingVersion=safe(_state.value.globalMappingVersion){repo.globalMappingVersion()},
            strategyTournamentSummary=safe(_state.value.strategyTournamentSummary){repo.strategyTournamentSummary()},
            lastStrategyScanAt=safe(_state.value.lastStrategyScanAt){repo.lastStrategyScanAt()},
            lastStrategyAttemptAt=safe(_state.value.lastStrategyAttemptAt){repo.lastStrategyAttemptAt()},
            lastStrategyErrorAt=safe(_state.value.lastStrategyErrorAt){repo.lastStrategyErrorAt()},
            lastStrategyError=safe(_state.value.lastStrategyError){repo.lastStrategyError()},
            lastStrategyCatalogRefreshAt=safe(_state.value.lastStrategyCatalogRefreshAt){repo.lastStrategyCatalogRefreshAt()},
            strategyCatalogVersion=safe(_state.value.strategyCatalogVersion){repo.strategyCatalogVersion()},
            strategyLive=safe(_state.value.strategyLive){repo.strategyLiveRecommendations()},
            strategyClosed=safe(_state.value.strategyClosed){repo.strategyClosedRecommendations()},
            globalClosed=safe(_state.value.globalClosed){repo.globalLeadClosedRecommendations()},
            tradeCalls=safe(_state.value.tradeCalls){repo.tradeCalls()},
            tradeAutopsies=safe(_state.value.tradeAutopsies){repo.tradeAutopsies()},
            evidenceFabric=safe(_state.value.evidenceFabric){repo.evidenceFabricSummary()},
            pointInTimeEvidence=safe(_state.value.pointInTimeEvidence){repo.pointInTimeEvidence()},
            challengerShadows=safe(_state.value.challengerShadows){repo.challengerShadows()},
            brokerOrders=safe(_state.value.brokerOrders){repo.brokerOrders()},
            brokerPortfolio=safe(_state.value.brokerPortfolio){repo.brokerPortfolio()},
            decisionSnapshots=safe(_state.value.decisionSnapshots){repo.decisionSnapshots()}
        )
    }
'''
s=s[:start]+replacement+s[end:]
wr(p,s)

# Repository constructor: protect the two persisted reads that occur as property initializers.
p="app/src/main/java/com/suhas/ucsentinel/data/repository/UCSentinelRepository.kt"; s=rw(p)
s=one(s,
'''    private var newListingsCache:List<ListedSecurity> = prefs.loadNewListings()
''',
'''    private var newListingsCache:List<ListedSecurity> = runCatching{prefs.loadNewListings()}.getOrDefault(emptyList())
''',"safe new listings init")
s=one(s,
'''    private var lastDualSummary:DualScanSummary?=loadLastDualFromDisk()
''',
'''    private var lastDualSummary:DualScanSummary?=runCatching{loadLastDualFromDisk()}.getOrNull()
''',"safe dual summary init")
wr(p,s)

print("Global Edge v1.5.2 staged startup/recovery hotfix applied")

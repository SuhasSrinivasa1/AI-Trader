#!/usr/bin/env python3
from pathlib import Path
import sys
root=Path(sys.argv[1]).resolve()

def rw(p): return (root/p).read_text(encoding="utf-8")
def wr(p,s): (root/p).write_text(s,encoding="utf-8")
def rep(s,old,new,label,count=1):
    n=s.count(old)
    if n!=count: raise SystemExit(f"{label}: expected {count}, found {n}")
    return s.replace(old,new,count)

# Version.
p="app/build.gradle.kts";s=rw(p)
s=rep(s,"versionCode = 127","versionCode = 128","versionCode")
s=rep(s,'versionName = "1.2.7"','versionName = "1.2.8"',"versionName")
wr(p,s)

# Repository: hard-code the user's whitelisted Surfshark static IPv4 and verify the actual
# public egress address through a simple IPv4 echo endpoint. This lets the UI turn GREEN/RED
# based on the route the phone is really using, not merely what was typed into Settings.
p="app/src/main/java/com/suhas/ucsentinel/data/repository/UCSentinelRepository.kt";s=rw(p)
if "import kotlinx.coroutines.withContext" not in s:
    s=s.replace("import kotlinx.coroutines.sync.withLock\n","import kotlinx.coroutines.sync.withLock\nimport kotlinx.coroutines.Dispatchers\nimport kotlinx.coroutines.withContext\nimport java.net.HttpURLConnection\nimport java.net.URL\n")
s=rep(s,
'''    fun tradingStaticIp()=prefs.tradingStaticIp()
    fun saveTradingStaticIp(value:String)=prefs.saveTradingStaticIp(value)
''',
'''    fun tradingStaticIp()=EXPECTED_TRADING_STATIC_IP
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
''',
"repository pinned IP checker")
# Add companion constant immediately after class declaration.
s=rep(s,
'''class GlobalEdgeAITraderRepository(context:Context){
    private val appContext=context.applicationContext
''',
'''class GlobalEdgeAITraderRepository(context:Context){
    companion object{ const val EXPECTED_TRADING_STATIC_IP="169.150.209.215" }
    private val appContext=context.applicationContext
''',
"repository static IP constant")
wr(p,s)

# ViewModel: continuously verify route while app is open, expose expected/actual state,
# and allow a manual refresh from Groww Auth.
p="app/src/main/java/com/suhas/ucsentinel/ui/MainViewModel.kt";s=rw(p)
s=rep(s,
'''    val credentials:Credentials=Credentials(),val staticIp:String="",val settings:AppSettings=AppSettings(),val dualSummary:DualScanSummary?=null,
''',
'''    val credentials:Credentials=Credentials(),val staticIp:String="",val currentPublicIp:String="",val staticIpMatch:Boolean?=null,val staticIpCheckedAt:Long=0L,val settings:AppSettings=AppSettings(),val dualSummary:DualScanSummary?=null,
''',
"route state fields")
# Add periodic route checker to init after existing scheduler coroutine.
needle='''        viewModelScope.launch{
            delay(3_000L)
            while(isActive){
                runCatching{runForegroundAutomation()}
                    .onFailure{t->_state.value=_state.value.copy(error=t.message?.takeIf{it.isNotBlank()})}
                delay(15_000L)
            }
        }
'''
addition=needle+'''        viewModelScope.launch{
            delay(1_500L)
            while(isActive){
                checkTradingRoute()
                delay(60_000L)
            }
        }
'''
s=rep(s,needle,addition,"route checker init")
# Replace old editable-save function with a refresh function; keep API compatibility but pin expected IP.
old='''    fun saveTradingStaticIp(value:String){
        val ip=value.trim()
        val parts=ip.split(".")
        val valid=parts.size==4 && parts.all{p->p.isNotEmpty() && p.all{it.isDigit()} && (p.toIntOrNull()?:-1) in 0..255}
        if(!valid){
            _state.value=_state.value.copy(error="Enter a valid IPv4 address",status="Static IP not saved")
            return
        }
        repo.saveTradingStaticIp(ip)
        _state.value=_state.value.copy(staticIp=ip,error=null,status="Whitelisted static IP saved locally")
    }
'''
new='''    private suspend fun checkTradingRoute(){
        runCatching{repo.currentPublicIpv4()}.onSuccess{actual->
            val expected=repo.tradingStaticIp()
            _state.value=_state.value.copy(staticIp=expected,currentPublicIp=actual,staticIpMatch=actual==expected,staticIpCheckedAt=System.currentTimeMillis())
        }.onFailure{
            _state.value=_state.value.copy(staticIp=repo.tradingStaticIp(),currentPublicIp="",staticIpMatch=null,staticIpCheckedAt=System.currentTimeMillis())
        }
    }
    fun refreshTradingRoute()=viewModelScope.launch{checkTradingRoute()}
    fun saveTradingStaticIp(value:String){refreshTradingRoute()}
'''
s=rep(s,old,new,"viewmodel route checker")
wr(p,s)

# Groww Auth: remove editable IP field and replace it with an always-visible GREEN/RED route signal.
p="app/src/main/java/com/suhas/ucsentinel/ui/MoreScreen.kt";s=rw(p)
if "import androidx.compose.ui.graphics.Color" not in s:
    s=s.replace("import androidx.compose.ui.Modifier\n","import androidx.compose.ui.Modifier\nimport androidx.compose.ui.graphics.Color\n")
s=s.replace('    var staticIp by remember(state.staticIp){mutableStateOf(state.staticIp)}\n','')
old='''        HorizontalDivider()
        Text("Trading route",style=MaterialTheme.typography.titleMedium)
        OutlinedTextField(
            value=staticIp,onValueChange={staticIp=it.trim()},
            label={Text("Whitelisted static IPv4")},
            supportingText={Text("Saved locally for trading-route configuration. Typing an IP here does not by itself reroute Android network traffic.")},
            singleLine=true,modifier=Modifier.fillMaxWidth()
        )
        Button(onClick={vm.saveTradingStaticIp(staticIp)},modifier=Modifier.fillMaxWidth()){Text("Save static IP")}
        if(state.staticIp.isNotBlank())Text("Saved: ${state.staticIp}",style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.primary)
'''
new='''        HorizontalDivider()
        Text("Trading route",style=MaterialTheme.typography.titleMedium)
        val routeColor=when(state.staticIpMatch){true->Color(0xFF2E7D32);false->Color(0xFFC62828);null->MaterialTheme.colorScheme.onSurfaceVariant}
        val routeTitle=when(state.staticIpMatch){true->"● GREEN • STATIC IP MATCH";false->"● RED • STATIC IP MISMATCH";null->"● CHECKING STATIC IP ROUTE"}
        ElevatedCard(Modifier.fillMaxWidth()){
            Column(Modifier.padding(14.dp),verticalArrangement=Arrangement.spacedBy(5.dp)){
                Text(routeTitle,fontWeight=FontWeight.Bold,color=routeColor)
                Text("Expected static IPv4 • ${state.staticIp}",style=MaterialTheme.typography.bodyMedium)
                Text(
                    if(state.currentPublicIp.isNotBlank())"Current public IPv4 • ${state.currentPublicIp}"
                    else "Current public IPv4 • unavailable / checking",
                    style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant
                )
                Text(
                    if(state.staticIpMatch==true)"Surfshark static route is active."
                    else if(state.staticIpMatch==false)"Turn on the whitelisted Surfshark static-IP route before trading."
                    else "Unable to verify the public route yet. Tap Check route now.",
                    style=MaterialTheme.typography.bodySmall,color=routeColor
                )
            }
        }
        OutlinedButton(onClick=vm::refreshTradingRoute,modifier=Modifier.fillMaxWidth()){Text("Check route now")}
'''
s=rep(s,old,new,"auth hardcoded route status")
# MoreScreen needs FontWeight for status.
if "import androidx.compose.ui.text.font.FontWeight" not in s:
    s=s.replace("import androidx.compose.ui.platform.LocalContext\n","import androidx.compose.ui.platform.LocalContext\nimport androidx.compose.ui.text.font.FontWeight\n")
wr(p,s)

# Trading Strategies: dynamically identify the 5-point model-score band with the best
# observed win rate. Require >=3 closed calls before calling a band established; until then
# display the best available early sample. Tie-break by sample count and average return.
p="app/src/main/java/com/suhas/ucsentinel/ui/CompactMarketScreens.kt";s=rw(p)
anchor='''@Composable
fun StrategiesCompactScreen(state:UiState,vm:MainViewModel,padding:PaddingValues){
'''
helper='''private data class ScoreBandPerformance(
    val low:Int,val high:Int,val samples:Int,val wins:Int,val accuracy:Double,val avgReturn:Double,val established:Boolean
)
private fun bestScoreBand(records:List<StrategyRecommendation>):ScoreBandPerformance?{
    if(records.isEmpty())return null
    data class Bucket(val low:Int,val rows:MutableList<StrategyRecommendation>)
    val buckets=linkedMapOf<Int,MutableList<StrategyRecommendation>>()
    records.take(500).forEach{r->
        val raw=r.setup.score.takeIf{it.isFinite()}?.coerceIn(0.0,100.0)?:return@forEach
        val low=if(raw>=100.0)95 else (kotlin.math.floor(raw/5.0)*5.0).toInt().coerceIn(0,95)
        buckets.getOrPut(low){mutableListOf()}+=r
    }
    val all=buckets.map{(low,rows)->
        val n=rows.size
        val wins=rows.count{it.status==StrategyRecommendationStatus.WIN}
        ScoreBandPerformance(low,(low+5).coerceAtMost(100),n,wins,if(n>0)wins*100.0/n else 0.0,
            if(n>0)rows.map{it.returnPct}.average() else 0.0,n>=3)
    }
    val eligible=all.filter{it.established}.ifEmpty{all}
    return eligible.maxWithOrNull(compareBy<ScoreBandPerformance>{it.accuracy}.thenBy{it.samples}.thenBy{it.avgReturn})
}

@Composable
fun StrategiesCompactScreen(state:UiState,vm:MainViewModel,padding:PaddingValues){
'''
s=rep(s,anchor,helper,"score-band helper")
# Insert the dynamic card near the top, just after CompactHeader.
old='''        item{CompactHeader("Trading Strategies",state,state.lastStrategyScanAt,vm::refreshTradingStrategies)}
        item{
            val attempt=if(state.lastStrategyAttemptAt>0)formatIstTimestamp(state.lastStrategyAttemptAt) else "not yet"
'''
new='''        item{CompactHeader("Trading Strategies",state,state.lastStrategyScanAt,vm::refreshTradingStrategies)}
        item{
            val band=bestScoreBand(state.strategyClosed)
            if(band==null){
                Text("Best model-score band • collecting closed results",style=MaterialTheme.typography.labelMedium,color=MaterialTheme.colorScheme.onSurfaceVariant)
            }else{
                ElevatedCard(Modifier.fillMaxWidth()){
                    Column(Modifier.padding(horizontal=12.dp,vertical=9.dp),verticalArrangement=Arrangement.spacedBy(2.dp)){
                        Text("BEST MODEL-SCORE BAND • ${band.low}–${band.high}%",style=MaterialTheme.typography.labelMedium,fontWeight=FontWeight.Bold,color=MaterialTheme.colorScheme.primary)
                        Text("${band.wins}/${band.samples} wins • ${"%.1f".format(band.accuracy)}% observed hit rate • avg ${"%+.2f".format(band.avgReturn)}% return${if(band.established)"" else " • early sample"}",
                            style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
                        Text("Dynamic 5-point band from closed strategy calls • MODEL score is not a probability.",style=MaterialTheme.typography.labelSmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
            }
        }
        item{
            val attempt=if(state.lastStrategyAttemptAt>0)formatIstTimestamp(state.lastStrategyAttemptAt) else "not yet"
'''
s=rep(s,old,new,"strategy best band card")
wr(p,s)

print("Global Edge v1.2.8 pinned Surfshark route verification + dynamic winning score band applied")

#!/usr/bin/env python3
from pathlib import Path
import sys,re
root=Path(sys.argv[1]).resolve()

def rw(p): return (root/p).read_text(encoding="utf-8")
def wr(p,s): (root/p).write_text(s,encoding="utf-8")
def rep(s,old,new,label,count=1):
    n=s.count(old)
    if n!=count: raise SystemExit(f"{label}: expected {count}, found {n}")
    return s.replace(old,new,count)

p="app/build.gradle.kts";s=rw(p)
s=rep(s,"versionCode = 126","versionCode = 127","versionCode")
s=rep(s,'versionName = "1.2.6"','versionName = "1.2.7"',"versionName")
wr(p,s)

p="app/src/main/java/com/suhas/ucsentinel/data/local/AppPreferences.kt";s=rw(p)
anchor='''    fun saveSettings(s:AppSettings){prefs.edit().putFloat("min_score",s.minScore.toFloat()).putFloat("pressure_prediction_min_score",s.demandMinScore.toFloat())'''
insert='''    fun tradingStaticIp():String=prefs.getString("trading_static_ip","").orEmpty()
    fun saveTradingStaticIp(value:String){prefs.edit().putString("trading_static_ip",value.trim()).apply()}

'''
idx=s.find(anchor)
if idx<0: raise SystemExit("AppPreferences settings anchor missing")
s=s[:idx]+insert+s[idx:]
wr(p,s)

p="app/src/main/java/com/suhas/ucsentinel/data/repository/UCSentinelRepository.kt";s=rw(p)
s=rep(s,
'''    fun settings()=prefs.loadSettings()
    fun saveSettings(s:AppSettings)=prefs.saveSettings(s)
''',
'''    fun settings()=prefs.loadSettings()
    fun saveSettings(s:AppSettings)=prefs.saveSettings(s)
    fun tradingStaticIp()=prefs.tradingStaticIp()
    fun saveTradingStaticIp(value:String)=prefs.saveTradingStaticIp(value)
''',
"repository static ip")
wr(p,s)

p="app/src/main/java/com/suhas/ucsentinel/ui/MainViewModel.kt";s=rw(p)
s=rep(s,
'''    val busy:Boolean=false,val status:String="Ready",val error:String?=null,val authenticated:Boolean=false,val tokenExpiry:String="",
    val credentials:Credentials=Credentials(),val settings:AppSettings=AppSettings(),val dualSummary:DualScanSummary?=null,
''',
'''    val busy:Boolean=false,val status:String="Ready",val error:String?=null,val authenticated:Boolean=false,val tokenExpiry:String="",
    val credentials:Credentials=Credentials(),val staticIp:String="",val settings:AppSettings=AppSettings(),val dualSummary:DualScanSummary?=null,
''',
"UiState static ip")
s=rep(s,
'''        return UiState(authenticated=repo.accessToken().isNotBlank(),tokenExpiry=repo.tokenExpiry(),credentials=repo.credentials(),settings=repo.settings(),
''',
'''        return UiState(authenticated=repo.accessToken().isNotBlank(),tokenExpiry=repo.tokenExpiry(),credentials=repo.credentials(),staticIp=repo.tradingStaticIp(),settings=repo.settings(),
''',
"initial static ip")
s=rep(s,
'''    fun updateCredentials(c:Credentials){_state.value=_state.value.copy(credentials=c)}
    fun saveCredentials(){repo.saveCredentials(_state.value.credentials);_state.value=_state.value.copy(status="Credentials saved securely",error=null)}
''',
'''    fun updateCredentials(c:Credentials){_state.value=_state.value.copy(credentials=c)}
    fun saveCredentials(){repo.saveCredentials(_state.value.credentials);_state.value=_state.value.copy(status="Credentials saved securely",error=null)}
    fun saveTradingStaticIp(value:String){
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
''',
"vm save static ip")
wr(p,s)

p="app/src/main/java/com/suhas/ucsentinel/ui/MoreScreen.kt";s=rw(p)
s=rep(s,
'''    var mode by remember(state.credentials.mode){mutableStateOf(state.credentials.mode)}
    var key by remember(state.credentials.apiKeyOrTotpToken){mutableStateOf(state.credentials.apiKeyOrTotpToken)}
    var secret by remember(state.credentials.secret){mutableStateOf(state.credentials.secret)}
''',
'''    var mode by remember(state.credentials.mode){mutableStateOf(state.credentials.mode)}
    var key by remember(state.credentials.apiKeyOrTotpToken){mutableStateOf(state.credentials.apiKeyOrTotpToken)}
    var secret by remember(state.credentials.secret){mutableStateOf(state.credentials.secret)}
    var staticIp by remember(state.staticIp){mutableStateOf(state.staticIp)}
''',
"auth static ip state")
s=rep(s,
'''        Text(if(state.authenticated)"Authenticated • ${state.tokenExpiry}" else "Not authenticated",color=MaterialTheme.colorScheme.onSurfaceVariant)
''',
'''        Text(if(state.authenticated)"Authenticated • ${state.tokenExpiry}" else "Not authenticated",color=MaterialTheme.colorScheme.onSurfaceVariant)
        HorizontalDivider()
        Text("Trading route",style=MaterialTheme.typography.titleMedium)
        OutlinedTextField(
            value=staticIp,onValueChange={staticIp=it.trim()},
            label={Text("Whitelisted static IPv4")},
            supportingText={Text("Saved locally for trading-route configuration. Typing an IP here does not by itself reroute Android network traffic.")},
            singleLine=true,modifier=Modifier.fillMaxWidth()
        )
        Button(onClick={vm.saveTradingStaticIp(staticIp)},modifier=Modifier.fillMaxWidth()){Text("Save static IP")}
        if(state.staticIp.isNotBlank())Text("Saved: ${state.staticIp}",style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.primary)
''',
"auth static ip controls")
s=s.replace("UC score band 66–88 • Pressure score band 62–86","UC score band 60–84 • Pressure score band 62–86")
wr(p,s)

p="app/src/main/java/com/suhas/ucsentinel/notifications/AppNotifier.kt";s=rw(p)
s=rep(s,
'''    private const val STRATEGY_CHANNEL = "strategy_entry_alerts"
''',
'''    private const val STRATEGY_CHANNEL = "strategy_entry_alerts"
    private const val ORDER_CHANNEL = "prepared_order_tickets"
''',
"order channel constant")
s=rep(s,
'''            manager.createNotificationChannel(NotificationChannel(STRATEGY_CHANNEL,"Trading strategy entry alerts",NotificationManager.IMPORTANCE_HIGH).apply {
                description="Alerts only when a new persistent LIVE intraday strategy call clears price, volume and liquidity gates."
                enableVibration(true)
            })
''',
'''            manager.createNotificationChannel(NotificationChannel(STRATEGY_CHANNEL,"Trading strategy entry alerts",NotificationManager.IMPORTANCE_HIGH).apply {
                description="Alerts only when a new persistent LIVE intraday strategy call clears price, volume and liquidity gates."
                enableVibration(true)
            })
            manager.createNotificationChannel(NotificationChannel(ORDER_CHANNEL,"Prepared order tickets",NotificationManager.IMPORTANCE_HIGH).apply {
                description="Confirms that a model-card order ticket has been prepared for review."
                enableVibration(true)
            })
''',
"order notification channel")
insert='''

    fun notifyPreparedOrder(context:Context,symbol:String,side:String,product:String,quantity:Int,entry:Double,stop:Double,target:Double){
        if(!allowed(context))return
        ensureChannel(context)
        val text=side+" "+symbol+" • "+product+" • qty "+quantity+" • entry ₹"+String.format(Locale.US,"%.2f",entry)+" • SL ₹"+String.format(Locale.US,"%.2f",stop)+" • target ₹"+String.format(Locale.US,"%.2f",target)
        val n=NotificationCompat.Builder(context,ORDER_CHANNEL)
            .setSmallIcon(android.R.drawable.stat_notify_more)
            .setContentTitle("Order ticket prepared")
            .setContentText(text)
            .setStyle(NotificationCompat.BigTextStyle().bigText(text+"\\nReview and submit through your broker."))
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setCategory(NotificationCompat.CATEGORY_STATUS)
            .setAutoCancel(true)
            .setContentIntent(pending(context,2501))
            .build()
        runCatching{NotificationManagerCompat.from(context).notify((System.currentTimeMillis()%100000).toInt()+2500,n)}
    }
'''
pos=s.rfind("\n}")
if pos<0: raise SystemExit("AppNotifier closing brace missing")
s=s[:pos]+insert+s[pos:]
wr(p,s)

p="app/src/main/java/com/suhas/ucsentinel/ui/CompactMarketScreens.kt";s=rw(p)
s=s.replace("import androidx.compose.foundation.layout.*\n","import androidx.compose.foundation.layout.*\nimport androidx.compose.foundation.clickable\n")
s=s.replace("import androidx.compose.ui.Alignment\n","import androidx.compose.ui.Alignment\nimport androidx.compose.ui.platform.LocalContext\n")
s=s.replace("import com.suhas.globaledgeai.domain.model.*\n","import com.suhas.globaledgeai.domain.model.*\nimport com.suhas.globaledgeai.notifications.AppNotifier\nimport android.widget.Toast\nimport kotlin.math.floor\n")

old='''@Composable
private fun ScoreBadge(score:Double){
    Surface(shape=RoundedCornerShape(14.dp),color=MaterialTheme.colorScheme.secondaryContainer){
        Column(Modifier.padding(horizontal=10.dp,vertical=6.dp),horizontalAlignment=Alignment.CenterHorizontally){
            Text("${score.toInt()}%",style=MaterialTheme.typography.titleSmall,fontWeight=FontWeight.Bold,maxLines=1)
            Text("MODEL",style=MaterialTheme.typography.labelSmall,color=MaterialTheme.colorScheme.onSecondaryContainer,maxLines=1)
        }
    }
}

@Composable
private fun TradeCard(symbol:String,direction:String,score:Double,plan:SimplePlan?,detail:String,status:String?=null){
    ElevatedCard(Modifier.fillMaxWidth(),shape=RoundedCornerShape(16.dp)){
'''
new='''@Composable
private fun ScoreBadge(score:Double,onClick:(()->Unit)?=null){
    val modifier=if(onClick!=null)Modifier.clickable{onClick()} else Modifier
    Surface(modifier=modifier,shape=RoundedCornerShape(14.dp),color=MaterialTheme.colorScheme.secondaryContainer){
        Column(Modifier.padding(horizontal=10.dp,vertical=6.dp),horizontalAlignment=Alignment.CenterHorizontally){
            Text("${score.toInt()}%",style=MaterialTheme.typography.titleSmall,fontWeight=FontWeight.Bold,maxLines=1)
            Text(if(onClick!=null)"MODEL • TAP" else "MODEL",style=MaterialTheme.typography.labelSmall,color=MaterialTheme.colorScheme.onSecondaryContainer,maxLines=1)
        }
    }
}

@Composable
private fun TradeCard(symbol:String,direction:String,score:Double,plan:SimplePlan?,detail:String,status:String?=null,orderable:Boolean=false){
    val ctx=LocalContext.current
    var showOrder by remember(symbol,direction,plan?.entry){mutableStateOf(false)}
    val short=direction.contains("SHORT",true)||direction.contains("SELL",true)
    val side=if(short)"SELL" else "BUY"
    val product=if(short)"MIS" else "CNC"
    val qty=if(plan!=null&&plan.entry>0.0)floor(20000.0/plan.entry).toInt().coerceAtLeast(0) else 0
    if(showOrder&&plan!=null){
        AlertDialog(
            onDismissRequest={showOrder=false},
            title={Text("Review ₹20,000 order ticket")},
            text={Column(verticalArrangement=Arrangement.spacedBy(6.dp)){
                Text(side+" "+symbol+" • "+product)
                Text("Quantity "+qty+" • budget cap ₹20,000")
                Text("Entry ₹"+"%.2f".format(plan.entry)+" • Stop ₹"+"%.2f".format(plan.stop)+" • Target ₹"+"%.2f".format(plan.target1))
                Text("This prepares the ticket locally; it does not transmit a live broker order.",style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
            }},
            dismissButton={TextButton(onClick={showOrder=false}){Text("Cancel")}},
            confirmButton={
                Button(onClick={
                    showOrder=false
                    if(qty<=0){
                        Toast.makeText(ctx,"Budget insufficient for one share",Toast.LENGTH_LONG).show()
                    }else{
                        AppNotifier.notifyPreparedOrder(ctx,symbol,side,product,qty,plan.entry,plan.stop,plan.target1)
                        Toast.makeText(ctx,"Order ticket prepared: "+side+" "+qty+" "+symbol+" ("+product+")",Toast.LENGTH_LONG).show()
                    }
                },enabled=qty>0){Text("Prepare")}
            }
        )
    }
    ElevatedCard(Modifier.fillMaxWidth(),shape=RoundedCornerShape(16.dp)){
'''
s=rep(s,old,new,"score badge + order dialog")
s=rep(s,"                ScoreBadge(score)","                ScoreBadge(score,if(orderable&&plan!=null){{showOrder=true}}else null)","score action wiring")

s=rep(s,
'''TradeCard(c.symbol,"LONG • PRE-UC",c.score,ucPlan(c),"${c.companyName} • ${"%.2f".format(c.dayChangePercent)}% today • ${"%.1f".format(c.volumeRatio)}x volume","LIVE • each materially changed entry is logged as a separate call")''',
'''TradeCard(c.symbol,"LONG • PRE-UC",c.score,ucPlan(c),"${c.companyName} • ${"%.2f".format(c.dayChangePercent)}% today • ${"%.1f".format(c.volumeRatio)}x volume","LIVE • tap MODEL score to prepare ₹20,000 CNC ticket",orderable=true)''',
"UC live orderable")
s=rep(s,
'''TradeCard(s.symbol,"${s.direction.name} • ${s.strategyName}",s.score,strategyPlan(s),s.evidence,"LIVE • opened ${formatIstTimestamp(r.openedAt)} • spread ${"%.2f".format(r.spreadPct)}%")''',
'''TradeCard(s.symbol,"${s.direction.name} • ${s.strategyName}",s.score,strategyPlan(s),s.evidence,"LIVE • opened ${formatIstTimestamp(r.openedAt)} • spread ${"%.2f".format(r.spreadPct)}% • tap MODEL score to prepare order",orderable=true)''',
"strategy live orderable")
s=rep(s,
'''TradeCard(c.indianSymbol,c.direction.name,c.score,globalPlan(c),"Lead ${c.foreignTicker} • ${c.exchange} • foreign ${"%.2f".format(c.foreignDayPct)}% • India ${"%.2f".format(c.indianFromOpenPct)}%","LIVE • ${c.action.name.replace('_',' ')}")''',
'''TradeCard(c.indianSymbol,c.direction.name,c.score,globalPlan(c),"Lead ${c.foreignTicker} • ${c.exchange} • foreign ${"%.2f".format(c.foreignDayPct)}% • India ${"%.2f".format(c.indianFromOpenPct)}%","LIVE • ${c.action.name.replace('_',' ')} • tap MODEL score to prepare order",orderable=true)''',
"global live orderable")
wr(p,s)

print("Global Edge v1.2.7 static-IP storage + tap-score order staging applied")

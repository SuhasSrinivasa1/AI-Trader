package com.multify.autotrader.ui
import android.content.Intent
import android.provider.Settings
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.lazy.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.*
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.*
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.multify.autotrader.AppContainer
import com.multify.autotrader.ui.components.*
import java.text.SimpleDateFormat
import java.util.*

enum class Dest(val label:String,val icon:androidx.compose.ui.graphics.vector.ImageVector){OVERVIEW("Overview",Icons.Default.SpaceDashboard),SIGNALS("Signals",Icons.Default.NotificationsActive),POSITIONS("Positions",Icons.Default.ShowChart),ANALYTICS("Replay",Icons.Default.Insights),SETTINGS("Settings",Icons.Default.Settings)}

@Composable fun MultifyApp(c:AppContainer,notificationAccess:Boolean,onRefreshAccess:()->Unit){
 var dest by rememberSaveable{mutableStateOf(Dest.OVERVIEW)};val f=remember(c){VmFactory(c)}
 BoxWithConstraints(Modifier.fillMaxSize()){val wide=maxWidth>=840.dp
  if(wide)Row(Modifier.fillMaxSize()){NavigationRail(containerColor=MaterialTheme.colorScheme.surface){Spacer(Modifier.height(24.dp));Icon(Icons.Default.AutoGraph,null,tint=MaterialTheme.colorScheme.primary);Spacer(Modifier.height(20.dp));Dest.entries.forEach{NavigationRailItem(selected=dest==it,onClick={dest=it},icon={Icon(it.icon,it.label)},label={Text(it.label)},alwaysShowLabel=false)}};VerticalDivider();Screen(dest,f,notificationAccess,onRefreshAccess,Modifier.weight(1f))}
  else Scaffold(bottomBar={NavigationBar(containerColor=MaterialTheme.colorScheme.surface){Dest.entries.forEach{NavigationBarItem(selected=dest==it,onClick={dest=it},icon={Icon(it.icon,it.label)},label={Text(it.label)})}}},containerColor=MaterialTheme.colorScheme.background){p->Screen(dest,f,notificationAccess,onRefreshAccess,Modifier.padding(p))}
 }
}
@Composable private fun Screen(d:Dest,f:VmFactory,access:Boolean,onRefresh:()->Unit,modifier:Modifier){Box(modifier.fillMaxSize()){when(d){Dest.OVERVIEW->Overview(access,onRefresh,viewModel(factory=f));Dest.SIGNALS->Signals(viewModel(factory=f));Dest.POSITIONS->Positions(viewModel(factory=f));Dest.ANALYTICS->Analytics(viewModel(factory=f));Dest.SETTINGS->SettingsScreen(access,onRefresh,viewModel(factory=f))}}}

@OptIn(ExperimentalMaterial3Api::class)
@Composable private fun Overview(access:Boolean,onRefreshAccess:()->Unit,vm:OverviewVm){val s by vm.state.collectAsStateWithLifecycle();val ctx=LocalContext.current
 Scaffold(topBar={TopAppBar(title={Column{Text("Trading command center");Text("NSE cash intraday",style=MaterialTheme.typography.labelSmall,color=MaterialTheme.colorScheme.onSurfaceVariant)}},actions={IconButton(onClick=vm::refresh){Icon(Icons.Default.Refresh,"Refresh")}},colors=TopAppBarDefaults.topAppBarColors(containerColor=MaterialTheme.colorScheme.background))},containerColor=MaterialTheme.colorScheme.background){p->
  LazyColumn(Modifier.fillMaxSize().padding(p),contentPadding=PaddingValues(18.dp),verticalArrangement=Arrangement.spacedBy(14.dp)){
   item{Banner(if(access)"Notification capture ready" else "Notification access required",if(access)"Multify alerts can be captured while the app is closed." else "Grant special access so alerts reach the engine.",access,if(access)null else "Open settings",if(access)null else {{ctx.startActivity(Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS));onRefreshAccess()}})}
   item{Card(shape=RoundedCornerShape(22.dp),colors=CardDefaults.cardColors(containerColor=MaterialTheme.colorScheme.surface)){Column(Modifier.padding(18.dp)){Row(Modifier.fillMaxWidth(),verticalAlignment=Alignment.CenterVertically){Column(Modifier.weight(1f)){Text("Execution engine",style=MaterialTheme.typography.titleLarge);Text(s.health.scope,color=MaterialTheme.colorScheme.onSurfaceVariant)};StatusPill(if(s.health.ok)s.health.mode.uppercase() else "OFFLINE",s.health.ok)};Spacer(Modifier.height(16.dp));Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.SpaceBetween){Fact("Session",s.health.sessionState);Fact("Broker",if(s.health.brokerConfigured)"READY" else "NOT SET");Fact("Queue",s.pending.toString())};Spacer(Modifier.height(14.dp));FilledTonalButton(onClick={vm.kill(!s.health.killSwitch)},modifier=Modifier.fillMaxWidth(),colors=ButtonDefaults.filledTonalButtonColors(containerColor=if(s.health.killSwitch)MaterialTheme.colorScheme.primaryContainer else MaterialTheme.colorScheme.error.copy(alpha=.15f),contentColor=if(s.health.killSwitch)MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.error)){Icon(if(s.health.killSwitch)Icons.Default.PlayArrow else Icons.Default.StopCircle,null);Spacer(Modifier.width(8.dp));Text(if(s.health.killSwitch)"Resume after review" else "Emergency stop new entries")}}}}
   item{Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.spacedBy(12.dp)){MetricCard("Realised P&L",inr(s.summary.realisedPnl),s.summary.trades.toString()+" completed trades",Icons.Default.AccountBalanceWallet,if(s.summary.realisedPnl>=0)MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.error,Modifier.weight(1f));MetricCard("Open P&L",inr(s.summary.unrealisedPnl),s.summary.openPositions.toString()+" open positions",Icons.Default.ShowChart,if(s.summary.unrealisedPnl>=0)MaterialTheme.colorScheme.secondary else MaterialTheme.colorScheme.error,Modifier.weight(1f))}}
   if(s.error!=null)item{Banner("Backend attention needed",s.error?: "Unknown error",false,"Retry",vm::refresh)}
   item{Text("Recent engine events",style=MaterialTheme.typography.titleLarge)}
   if(s.events.isEmpty())item{Card(colors=CardDefaults.cardColors(containerColor=MaterialTheme.colorScheme.surface)){Box(Modifier.fillMaxWidth().padding(30.dp),contentAlignment=Alignment.Center){Text("No Multify alerts captured yet",color=MaterialTheme.colorScheme.onSurfaceVariant)}}}
   else items(s.events,key={it.id}){e->EventRow(e.symbol,e.eventType,SimpleDateFormat("HH:mm:ss",Locale.getDefault()).format(Date(e.receivedAtMs)),e.serverAction,e.serverReason?:e.lastError,e.deliveryStatus);HorizontalDivider(color=MaterialTheme.colorScheme.outline.copy(alpha=.15f))}
  }
 }}
@Composable private fun Fact(l:String,v:String){Column{Text(l,style=MaterialTheme.typography.labelSmall,color=MaterialTheme.colorScheme.onSurfaceVariant);Text(v,fontWeight=FontWeight.SemiBold)}}

@OptIn(ExperimentalMaterial3Api::class)
@Composable private fun Signals(vm:SignalsVm){val es by vm.events.collectAsStateWithLifecycle();Scaffold(topBar={TopAppBar(title={Text("Signal journal")},colors=TopAppBarDefaults.topAppBarColors(containerColor=MaterialTheme.colorScheme.background))},containerColor=MaterialTheme.colorScheme.background){p->LazyColumn(Modifier.fillMaxSize().padding(p),contentPadding=PaddingValues(horizontal=18.dp,vertical=8.dp)){items(es,key={it.id}){e->EventRow(e.symbol,e.eventType,SimpleDateFormat("dd MMM • HH:mm:ss",Locale.getDefault()).format(Date(e.receivedAtMs)),e.serverAction,e.serverReason?:e.lastError,e.deliveryStatus);HorizontalDivider(color=MaterialTheme.colorScheme.outline.copy(alpha=.15f))}}}}

@OptIn(ExperimentalMaterial3Api::class)
@Composable private fun Positions(vm:PositionsVm){val ps by vm.positions.collectAsStateWithLifecycle();val err by vm.error.collectAsStateWithLifecycle();Scaffold(topBar={TopAppBar(title={Text("Net positions")},actions={IconButton(onClick=vm::refresh){Icon(Icons.Default.Refresh,"Refresh")}},colors=TopAppBarDefaults.topAppBarColors(containerColor=MaterialTheme.colorScheme.background))},containerColor=MaterialTheme.colorScheme.background){p->if(err!=null)Box(Modifier.fillMaxSize().padding(p),contentAlignment=Alignment.Center){Text(err?: "Unable to load positions",color=MaterialTheme.colorScheme.error)} else LazyColumn(Modifier.fillMaxSize().padding(p),contentPadding=PaddingValues(18.dp),verticalArrangement=Arrangement.spacedBy(12.dp)){if(ps.isEmpty())item{Box(Modifier.fillParentMaxSize(),contentAlignment=Alignment.Center){Text("No open intraday positions",color=MaterialTheme.colorScheme.onSurfaceVariant)}};items(ps){x->Card(shape=RoundedCornerShape(20.dp),colors=CardDefaults.cardColors(containerColor=MaterialTheme.colorScheme.surface)){Column(Modifier.padding(18.dp)){Row(Modifier.fillMaxWidth()){Column(Modifier.weight(1f)){Text(x.symbol,style=MaterialTheme.typography.titleLarge);Text("Avg "+inr(x.averagePrice),color=MaterialTheme.colorScheme.onSurfaceVariant)};StatusPill(x.side,x.quantity>0)};Spacer(Modifier.height(14.dp));Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.SpaceBetween){Fact("Quantity",kotlin.math.abs(x.quantity).toString());Fact("LTP",x.ltp?.let(::inr)?:"—");Fact("Open P&L",inr(x.unrealisedPnl))}}}}}}}

@OptIn(ExperimentalMaterial3Api::class)
@Composable private fun Analytics(vm:AnalyticsVm){val es by vm.events.collectAsStateWithLifecycle();val sent=es.count{it.deliveryStatus=="SENT"};val fail=es.count{it.deliveryStatus=="FAILED"};Scaffold(topBar={TopAppBar(title={Text("Replay & quality")},colors=TopAppBarDefaults.topAppBarColors(containerColor=MaterialTheme.colorScheme.background))},containerColor=MaterialTheme.colorScheme.background){p->LazyColumn(Modifier.fillMaxSize().padding(p),contentPadding=PaddingValues(18.dp),verticalArrangement=Arrangement.spacedBy(14.dp)){item{Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.spacedBy(12.dp)){MetricCard("Captured",es.size.toString(),sent.toString()+" delivered",Icons.Default.NotificationsActive,modifier=Modifier.weight(1f));MetricCard("Delivery errors",fail.toString(),"Persistent retry queue",Icons.Default.CloudOff,if(fail==0)MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.error,Modifier.weight(1f))}};item{Card(shape=RoundedCornerShape(20.dp),colors=CardDefaults.cardColors(containerColor=MaterialTheme.colorScheme.surface)){Column(Modifier.padding(18.dp)){Text("Nightly replay contract",style=MaterialTheme.typography.titleLarge);Spacer(Modifier.height(10.dp));Text("Reconstruct signal-time data → run eligible strategies with brokerage/slippage → record MFE/MAE → update stock × strategy × regime weights only after minimum sample thresholds.",color=MaterialTheme.colorScheme.onSurfaceVariant)}}}}}}

@OptIn(ExperimentalMaterial3Api::class)
@Composable private fun SettingsScreen(access:Boolean,onRefreshAccess:()->Unit,vm:SettingsVm){val s by vm.state.collectAsStateWithLifecycle();val ctx=LocalContext.current;var url by remember(s.settings.backendUrl){mutableStateOf(s.settings.backendUrl)};var filter by remember(s.settings.packageFilter){mutableStateOf(s.settings.packageFilter)};var secret by remember{mutableStateOf("")};var show by remember{mutableStateOf(false)}
 Scaffold(topBar={TopAppBar(title={Text("Settings")},colors=TopAppBarDefaults.topAppBarColors(containerColor=MaterialTheme.colorScheme.background))},containerColor=MaterialTheme.colorScheme.background){p->Column(Modifier.fillMaxSize().padding(p).verticalScroll(rememberScrollState()).padding(18.dp),verticalArrangement=Arrangement.spacedBy(14.dp)){
  Banner(if(access)"Notification access enabled" else "Notification access is off",if(access)"Listener permission is ready." else "Android must explicitly grant this special access.",access,"Open settings",{ctx.startActivity(Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS));onRefreshAccess()})
  Card(colors=CardDefaults.cardColors(containerColor=MaterialTheme.colorScheme.surface),shape=RoundedCornerShape(20.dp)){Column(Modifier.padding(18.dp),verticalArrangement=Arrangement.spacedBy(12.dp)){Text("Secure backend",style=MaterialTheme.typography.titleLarge);OutlinedTextField(url,{url=it},label={Text("Backend URL")},singleLine=true,modifier=Modifier.fillMaxWidth(),keyboardOptions=KeyboardOptions(keyboardType=androidx.compose.ui.text.input.KeyboardType.Uri));OutlinedTextField(filter,{filter=it},label={Text("Notification app/package filter")},singleLine=true,modifier=Modifier.fillMaxWidth());OutlinedTextField(secret,{secret=it},label={Text(if(s.hasSecret)"Replace device secret" else "Device secret")},singleLine=true,modifier=Modifier.fillMaxWidth(),visualTransformation=if(show)VisualTransformation.None else PasswordVisualTransformation(),trailingIcon={IconButton({show=!show}){Icon(if(show)Icons.Default.VisibilityOff else Icons.Default.Visibility,null)}})}}
  Card(colors=CardDefaults.cardColors(containerColor=MaterialTheme.colorScheme.surface),shape=RoundedCornerShape(20.dp)){Row(Modifier.fillMaxWidth().padding(18.dp),verticalAlignment=Alignment.CenterVertically){Column(Modifier.weight(1f)){Text("Forward captured signals",fontWeight=FontWeight.SemiBold);Text("Critical AUTO_PAUSED alerts always reach the safety path.",style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant)};Switch(s.settings.forwardingEnabled,vm::forwarding)}}
  Button({vm.save(url,filter,secret.takeIf{it.isNotBlank()})},modifier=Modifier.fillMaxWidth()){Icon(Icons.Default.Save,null);Spacer(Modifier.width(8.dp));Text("Save secure configuration")}
  if(s.message!=null)Text(s.message?: "",color=MaterialTheme.colorScheme.primary)
  Card(colors=CardDefaults.cardColors(containerColor=MaterialTheme.colorScheme.surfaceVariant.copy(alpha=.5f)),shape=RoundedCornerShape(20.dp)){Column(Modifier.padding(18.dp)){Text("Live-trading policy",fontWeight=FontWeight.SemiBold);Text("The phone cannot enable LIVE mode. Broker credentials, exposure limits, static-IP policy and the paper/live switch remain server-side.",style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant)}}
 }}}

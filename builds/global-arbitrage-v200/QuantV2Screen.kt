package com.suhas.globaledgeai.ui

import android.content.Context
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.suhas.globaledgeai.BuildConfig
import com.suhas.globaledgeai.GlobalEdgeApplication
import com.suhas.globaledgeai.diagnostics.DiagnosticLog
import java.time.Instant
import java.time.ZoneId
import java.util.zip.ZipEntry
import java.util.zip.ZipOutputStream
import kotlin.math.max
import kotlin.math.min

private data class V2Strategy(val name:String,val purpose:String,val state:String)
private val strategies=listOf(
    V2Strategy("FUT ↔ SYNTHETIC","Put-call parity / futures mispricing","READY"),
    V2Strategy("FUTURES CALENDAR","Near-vs-next expiry convergence","READY"),
    V2Strategy("CROSS-MARKET","Equivalent contract spread checks","READY"),
    V2Strategy("MOMENTUM + RVOL + OI","Directional confirmation layer","ACTIVE"),
    V2Strategy("NEWS EVENT","NSE/BSE announcements + reaction confirmation","ACTIVE"),
    V2Strategy("ORDER FLOW","Bid/ask depth and imbalance","ACTIVE"),
    V2Strategy("CANDLE ENSEMBLE","Multi-pattern confirmation; never standalone","ACTIVE"),
    V2Strategy("MEAN REVERSION","VWAP/z-score overextension","CHALLENGER"),
    V2Strategy("BREAKOUT","Range expansion + volume confirmation","CHALLENGER"),
    V2Strategy("STAT ARB","Relative-value divergence / convergence","CHALLENGER"),
    V2Strategy("GLOBAL LEAD","US/Europe/Asia/FX/commodity lead signals","ACTIVE"),
    V2Strategy("VOLATILITY","IV/realized-volatility regime selection","CHALLENGER")
)

@Composable
fun QuantV2Screen(state:UiState,vm:MainViewModel,padding:PaddingValues){
    val ctx=LocalContext.current
    val prefs=remember{ctx.getSharedPreferences("quant_v2",Context.MODE_PRIVATE)}
    var liveEnabled by remember{ mutableStateOf(prefs.getBoolean("live_enabled",false)) }
    var shadowCapitalText by remember{ mutableStateOf(prefs.getInt("shadow_capital",500000).toString()) }
    var monthOpen by remember{ mutableStateOf(false) }
    var confirmLive by remember{ mutableStateOf(false) }
    var exportStatus by remember{ mutableStateOf<String?>(null) }
    val shadowCapital=shadowCapitalText.toIntOrNull()?.coerceIn(10_000,20_000_000) ?: 500_000

    val today=java.time.LocalDate.now(ZoneId.of("Asia/Kolkata"))
    val todayClosed=state.strategyClosed.filter{
        Instant.ofEpochMilli(it.closedAt).atZone(ZoneId.of("Asia/Kolkata")).toLocalDate()==today
    }
    fun estPnl(rows:List<com.suhas.globaledgeai.domain.model.StrategyRecommendation>):Double{
        if(rows.isEmpty()) return 0.0
        val allocation=min(150000.0,shadowCapital.toDouble()/max(1,min(3,rows.size)))
        return rows.sumOf{ r ->
            val gross=allocation*(r.returnPct/100.0)
            val charges=allocation*0.0012
            gross-charges
        }
    }
    val todayPnl=estPnl(todayClosed)
    val monthRows=state.strategyClosed.filter{
        val d=Instant.ofEpochMilli(it.closedAt).atZone(ZoneId.of("Asia/Kolkata")).toLocalDate()
        d.year==today.year && d.month==today.month
    }
    val monthPnl=estPnl(monthRows)

    val exporter=rememberLauncherForActivityResult(ActivityResultContracts.CreateDocument("application/zip")){uri->
        if(uri!=null){
            runCatching{
                val app=ctx.applicationContext as GlobalEdgeApplication
                val repo=app.repository
                val out=ctx.contentResolver.openOutputStream(uri)?:error("Unable to open selected file")
                ZipOutputStream(out.buffered()).use{zip->
                    fun put(name:String,text:String){zip.putNextEntry(ZipEntry(name));zip.write(text.toByteArray());zip.closeEntry()}
                    put("README.txt",buildString{
                        appendLine("Global Arbitrage AI Trader v2.0 complete diagnostic export")
                        appendLine("Live enabled: $liveEnabled")
                        appendLine("Shadow capital: $shadowCapital")
                        appendLine("Today shadow net estimate: %.2f".format(todayPnl))
                        appendLine("Month shadow net estimate: %.2f".format(monthPnl))
                        appendLine("Authenticated: ${state.authenticated}")
                        appendLine("Static IP match: ${state.staticIpMatch}")
                        appendLine("Version: ${BuildConfig.VERSION_NAME}")
                    })
                    put("shadow_strategy_closed.csv",buildString{
                        appendLine("id,strategy,symbol,status,returnPct,openedAt,closedAt")
                        state.strategyClosed.forEach{r->appendLine("${r.id},${r.setup.strategyName.replace(',',' ')},${r.setup.symbol},${r.status},${r.returnPct},${r.openedAt},${r.closedAt}")}
                    })
                    put("strategy_manifest.csv","name,purpose,state\n"+strategies.joinToString("\n"){"${it.name},${it.purpose.replace(',',' ')},${it.state}"})
                    put("decision_snapshot.txt",state.decisionSnapshots.joinToString("\n"){"${it.decisionAt}|${it.symbol}|${it.strategyId}|${it.decision}|${it.score}|${it.reason}"})
                    put("news_snapshot.txt",state.newsItems.joinToString("\n"){"${it.source}|${it.symbol}|${it.publishedAt}|${it.title}"})
                    put("broker_orders_snapshot.txt",state.brokerOrders.joinToString("\n"){"${it.submittedAt}|${it.symbol}|${it.side}|${it.product}|${it.status}|${it.filledQuantity}/${it.requestedQuantity}|${it.averageFillPrice}"})
                    put("learning_report.txt",repo.weeklyLearningReport())
                    put("diagnostic_state.txt",repo.endOfDayDiagnosticReport())
                    put("device_log.txt",DiagnosticLog.weeklySnapshot(ctx,repo.weeklyLearningReport()))
                }
            }.onSuccess{exportStatus="Complete log ZIP saved"}.onFailure{exportStatus="Export failed: ${it.message}"}
        }
    }

    if(confirmLive){
        AlertDialog(
            onDismissRequest={confirmLive=false},
            title={Text("Enable live trading?")},
            text={Text(if(state.authenticated && state.staticIpMatch==true)
                "Live order permission will be armed. Strategy and risk gates still apply."
                else "Live trading requires Groww authentication and a verified whitelisted static-IP route. Current checks are not ready.")},
            confirmButton={Button(onClick={
                if(state.authenticated && state.staticIpMatch==true){liveEnabled=true;prefs.edit().putBoolean("live_enabled",true).apply()}
                confirmLive=false
            },enabled=state.authenticated && state.staticIpMatch==true){Text("ENABLE LIVE")}},
            dismissButton={OutlinedButton(onClick={confirmLive=false}){Text("Cancel")}}
        )
    }
    if(monthOpen){
        AlertDialog(onDismissRequest={monthOpen=false},title={Text("${today.month.name.lowercase().replaceFirstChar{it.uppercase()}} ${today.year} shadow P&L")},text={
            Column(verticalArrangement=Arrangement.spacedBy(6.dp)){
                Text("Starting capital  ₹%,d".format(shadowCapital))
                Text("Closed signals      ${monthRows.size}")
                Text("Net shadow P&L      ₹%,.0f".format(monthPnl),fontWeight=FontWeight.Bold,color=if(monthPnl>=0)Color(0xFF2E7D32) else Color(0xFFC62828))
                Text("Ending shadow equity ₹%,.0f".format(shadowCapital+monthPnl))
                Text("Shadow P&L is estimated from qualified closed signals, with an execution-cost reserve. Live realized P&L is kept separate.",style=MaterialTheme.typography.bodySmall)
            }
        },confirmButton={Button(onClick={monthOpen=false}){Text("Close")}})
    }

    LazyColumn(Modifier.fillMaxSize().padding(padding).padding(horizontal=14.dp),verticalArrangement=Arrangement.spacedBy(10.dp),contentPadding=PaddingValues(bottom=28.dp)){
        item{
            ElevatedCard(Modifier.fillMaxWidth()){
                Column(Modifier.padding(16.dp),verticalArrangement=Arrangement.spacedBy(10.dp)){
                    Text("QUANT + ARBITRAGE CONTROL",style=MaterialTheme.typography.titleLarge,fontWeight=FontWeight.Bold)
                    Row(verticalAlignment=Alignment.CenterVertically,modifier=Modifier.fillMaxWidth()){
                        Column(Modifier.weight(1f)){Text("LIVE TRADING",fontWeight=FontWeight.Bold);Text(if(liveEnabled)"ARMED" else "OFF • default",color=if(liveEnabled)Color(0xFFC62828) else Color(0xFF2E7D32))}
                        Switch(checked=liveEnabled,onCheckedChange={on->if(on)confirmLive=true else {liveEnabled=false;prefs.edit().putBoolean("live_enabled",false).apply()}})
                    }
                    Text("Groww: ${if(state.authenticated)"AUTHENTICATED" else "NOT AUTHENTICATED"}  •  Static IP: ${when(state.staticIpMatch){true->"MATCH";false->"MISMATCH";null->"UNCHECKED"}}",style=MaterialTheme.typography.bodySmall)
                }
            }
        }
        item{
            ElevatedCard(Modifier.fillMaxWidth().clickable{monthOpen=true}){
                Column(Modifier.padding(16.dp)){
                    Text("TODAY'S SHADOW P&L",style=MaterialTheme.typography.labelLarge)
                    Text("₹%,.0f".format(todayPnl),style=MaterialTheme.typography.headlineMedium,fontWeight=FontWeight.Bold,color=if(todayPnl>=0)Color(0xFF2E7D32) else Color(0xFFC62828))
                    Text("Tap for monthly view • ${todayClosed.size} closed shadow signals")
                }
            }
        }
        item{
            OutlinedTextField(value=shadowCapitalText,onValueChange={v->shadowCapitalText=v.filter(Char::isDigit).take(8);shadowCapitalText.toIntOrNull()?.let{prefs.edit().putInt("shadow_capital",it).apply()}},label={Text("Shadow wallet budget (₹)")},singleLine=true,modifier=Modifier.fillMaxWidth())
        }
        item{
            val global=state.globalLeadSummary
            ElevatedCard(Modifier.fillMaxWidth()){
                Column(Modifier.padding(14.dp),verticalArrangement=Arrangement.spacedBy(4.dp)){
                    Text("GLOBAL → INDIA LEAD",fontWeight=FontWeight.Bold)
                    Text(global?.message ?: "Waiting for global-market scan")
                    Text("International markets are treated as probabilistic lead signals and must be confirmed by Indian price/volume/OI/news before a directional trade.",style=MaterialTheme.typography.bodySmall)
                }
            }
        }
        item{Text("Strategy ensemble",style=MaterialTheme.typography.titleMedium,fontWeight=FontWeight.Bold)}
        items(strategies){s->
            ElevatedCard(Modifier.fillMaxWidth()){
                Row(Modifier.padding(12.dp),verticalAlignment=Alignment.CenterVertically){
                    Column(Modifier.weight(1f)){Text(s.name,fontWeight=FontWeight.SemiBold);Text(s.purpose,style=MaterialTheme.typography.bodySmall)}
                    AssistChip(onClick={},label={Text(s.state)})
                }
            }
        }
        item{
            ElevatedCard(Modifier.fillMaxWidth()){
                Column(Modifier.padding(14.dp),verticalArrangement=Arrangement.spacedBy(5.dp)){
                    Text("DAILY LEARNING",fontWeight=FontWeight.Bold)
                    Text("Champion/challenger records: ${state.challengerShadows.size} • Decisions: ${state.decisionSnapshots.size}")
                    Text("Weekly strategy catalog refresh is retained from the existing learning engine. New candidates remain challengers until sufficient shadow evidence exists.",style=MaterialTheme.typography.bodySmall)
                }
            }
        }
        item{
            Button(onClick={exporter.launch("Global-Arbitrage-AI-v2-${today}.zip")},modifier=Modifier.fillMaxWidth()){Text("EXPORT COMPLETE LOG")}
            exportStatus?.let{Text(it,style=MaterialTheme.typography.bodySmall)}
        }
        item{
            Text("v2.0 safety: live trading is OFF after install/update. A live enable requires Groww authentication + static-IP match. Shadow analytics continue regardless of live state.",style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

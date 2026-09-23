package com.suhas.globaledgeai.ui

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.suhas.globaledgeai.domain.model.*
import kotlin.math.max

private enum class CompactView{LIVE,CLOSED}
private enum class UcCompactView{NEXT_SESSION,LIVE,THREE_PM,CLOSED}
private enum class PressureCompactView{NEXT_SESSION,LIVE,CLOSED}
private enum class GlobalCompactView{NEXT_SESSION,LIVE,CLOSED}

@Composable
private fun CompactHeader(title:String,state:UiState,lastUpdated:Long=0L,onRefresh:(()->Unit)?=null,scheduleText:String?=null){
    Column(Modifier.fillMaxWidth(),verticalArrangement=Arrangement.spacedBy(4.dp)){
        Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.SpaceBetween){
            Column(Modifier.weight(1f)){
                Text(title,style=MaterialTheme.typography.headlineSmall,fontWeight=FontWeight.Bold)
                Text(scheduleText?:"09:15–15:30 IST • ${state.marketSession.label}",style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
            }
            if(onRefresh!=null)TextButton(onClick=onRefresh,enabled=!state.busy&&state.authenticated){Text("Refresh")}
        }
        if(lastUpdated>0)Text("Updated ${formatIstTimestamp(lastUpdated)}",style=MaterialTheme.typography.labelSmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
        if(!state.authenticated)Text("Groww authentication required",style=MaterialTheme.typography.labelMedium,color=MaterialTheme.colorScheme.error)
        else Text("5 min live • 15 min learning • walk-forward validation + rejected-candidate shadow audit",style=MaterialTheme.typography.labelSmall,color=MaterialTheme.colorScheme.primary)
    }
}

@Composable
private fun ViewSwitch(view:CompactView,onChange:(CompactView)->Unit,liveCount:Int,closedCount:Int){
    Row(horizontalArrangement=Arrangement.spacedBy(8.dp)){
        FilterChip(selected=view==CompactView.LIVE,onClick={onChange(CompactView.LIVE)},label={Text("LIVE $liveCount")})
        FilterChip(selected=view==CompactView.CLOSED,onClick={onChange(CompactView.CLOSED)},label={Text("CLOSED $closedCount")})
    }
}

private data class SimplePlan(val entry:Double,val stop:Double,val target1:Double,val target2:Double?=null)
private fun tradeCallPlan(r:TradeCallRecord)=SimplePlan(r.entryPrice,r.stopPrice,r.targetPrice,r.target2Price)
private fun autopsyStatus(state:UiState,sourceId:String):String?{
    val a=state.tradeAutopsies.firstOrNull{it.sourceId==sourceId}?:return null
    val best=a.shadowResults.firstOrNull{it.outcome==ShadowOutcome.AVOIDED_LOSS||it.outcome==ShadowOutcome.WIN}
    val shadow=best?.let{" • shadow ${it.strategyName}: ${it.outcome.name.replace('_',' ')}"}.orEmpty()
    return "Autopsy • ${a.regime.name.replace('_',' ')} • ${a.dominantCause.name.replace('_',' ')} ${"%.0f".format(a.causeConfidencePct)}%$shadow"
}

private fun ucPlan(c:Candidate):SimplePlan{
    val entry=c.price.coerceAtLeast(0.01)
    val target=if(c.upperCircuit>entry)c.upperCircuit else entry*1.02
    return SimplePlan(entry,entry*0.985,target)
}
private fun pressurePlan(c:Candidate):SimplePlan{
    val entry=c.price.coerceAtLeast(0.01)
    val targetPct=(c.targetMovePct?:2.5).coerceIn(0.5,8.0)
    return SimplePlan(entry,entry*0.985,entry*(1.0+targetPct/100.0))
}
private fun strategyPlan(s:StrategySetup):SimplePlan{
    val short=s.direction==TradeDirection.SHORT
    val entry=s.entryPrice.coerceAtLeast(0.01)
    val stop=if(short)entry*(1.0+s.stopPct.coerceAtLeast(0.1)/100.0) else entry*(1.0-s.stopPct.coerceAtLeast(0.1)/100.0)
    val target=if(short)entry*(1.0-s.targetPct.coerceAtLeast(0.1)/100.0) else entry*(1.0+s.targetPct.coerceAtLeast(0.1)/100.0)
    return SimplePlan(entry,stop,target)
}
private fun globalPlan(c:GlobalLeadCandidate):SimplePlan?{
    if(!c.indianPrice.isFinite()||c.indianPrice<20.0)return null
    val short=c.direction==GlobalLeadDirection.SHORT
    val base=c.indianPrice
    val entry=if(short)base*0.999 else base*1.001
    val openDistancePct=if(c.indianOpen>0.0)kotlin.math.abs(c.indianOpen-entry)/entry*100.0 else 0.0
    val riskPct=(openDistancePct*0.25).takeIf{it.isFinite()&&it>0.0}?.coerceIn(0.35,1.00)?:0.50
    val targetPct=c.expectedTargetPct.takeIf{it.isFinite()&&it>0.0}?.coerceIn(0.35,3.00)?:0.50
    val target2Pct=(targetPct*1.75).coerceIn(targetPct+0.20,4.00)
    val stop=if(short)entry*(1.0+riskPct/100.0) else entry*(1.0-riskPct/100.0)
    val t1=if(short)entry*(1.0-targetPct/100.0) else entry*(1.0+targetPct/100.0)
    val t2=if(short)entry*(1.0-target2Pct/100.0) else entry*(1.0+target2Pct/100.0)
    return SimplePlan(entry,stop,t1,t2)
}

@Composable
private fun PlanMetric(label:String,value:String,modifier:Modifier=Modifier){
    Surface(modifier=modifier,shape=RoundedCornerShape(10.dp),color=MaterialTheme.colorScheme.surfaceVariant){
        Column(Modifier.padding(horizontal=9.dp,vertical=8.dp),verticalArrangement=Arrangement.spacedBy(2.dp)){
            Text(label,style=MaterialTheme.typography.labelSmall,color=MaterialTheme.colorScheme.onSurfaceVariant,maxLines=1)
            Text(value,style=MaterialTheme.typography.bodyMedium,fontWeight=FontWeight.Bold,maxLines=1)
        }
    }
}

@Composable
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
        Column(Modifier.padding(horizontal=13.dp,vertical=12.dp),verticalArrangement=Arrangement.spacedBy(8.dp)){
            Row(Modifier.fillMaxWidth(),verticalAlignment=Alignment.Top,horizontalArrangement=Arrangement.spacedBy(10.dp)){
                Column(Modifier.weight(1f),verticalArrangement=Arrangement.spacedBy(2.dp)){
                    Text(symbol,style=MaterialTheme.typography.titleMedium,fontWeight=FontWeight.Bold,maxLines=1)
                    Text(direction,style=MaterialTheme.typography.labelMedium,fontWeight=FontWeight.SemiBold,maxLines=2,
                        color=if(direction.contains("SHORT")||direction.contains("SELL")||direction.contains("LOSS"))MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.primary)
                }
                ScoreBadge(score)
            }
            if(plan!=null){
                Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.spacedBy(6.dp)){
                    PlanMetric("ENTRY","₹${"%.2f".format(plan.entry)}",Modifier.weight(1f))
                    PlanMetric("STOP","₹${"%.2f".format(plan.stop)}",Modifier.weight(1f))
                    PlanMetric("TARGET","₹${"%.2f".format(plan.target1)}",Modifier.weight(1f))
                }
                if(plan.target2!=null)Text("Target 2  ₹${"%.2f".format(plan.target2)}",style=MaterialTheme.typography.labelMedium,fontWeight=FontWeight.SemiBold)
            }else{
                Text("Entry / stop / targets will be set after Indian price confirmation at 09:15 IST",style=MaterialTheme.typography.bodySmall,fontWeight=FontWeight.SemiBold,color=MaterialTheme.colorScheme.tertiary)
            }
            HorizontalDivider(color=MaterialTheme.colorScheme.outlineVariant)
            Text(detail,style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant,maxLines=3)
            if(!status.isNullOrBlank()){
                val statusColor=if(status.contains("LOSS"))MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.tertiary
                Text(status,style=MaterialTheme.typography.labelSmall,color=statusColor,maxLines=3)
            }
        }
    }
}

@Composable
fun UpperCircuitCompactScreen(state:UiState,vm:MainViewModel,padding:PaddingValues){
    val shown=state.dualSummary?.uc?.candidates.orEmpty().filter{it.price>=20.0}
    val ucMessage=state.dualSummary?.uc?.message.orEmpty()
    val ucWatchOnly=ucMessage.startsWith("WATCHLIST ONLY")
    val ucNextSession=ucMessage.startsWith("NEXT SESSION")
    val live=if(ucWatchOnly||ucNextSession) emptyList() else shown
    val calls=state.tradeCalls.filter{it.engine==TradeCallEngine.UPPER_CIRCUIT}
    val nextCalls=calls.filter{it.outcome==TradeCallOutcome.OPEN&&it.bucket==TradeCallBucket.NEXT_SESSION}.sortedByDescending{it.openedAt}
    val threePmCalls=calls.filter{it.outcome==TradeCallOutcome.OPEN&&it.bucket==TradeCallBucket.THREE_PM}.sortedByDescending{it.openedAt}
    val closed=calls.filter{it.outcome!=TradeCallOutcome.OPEN}.sortedByDescending{it.closedAt}
    var view by remember(state.marketSession.phase){mutableStateOf(if(state.marketSession.isOpen)UcCompactView.LIVE else UcCompactView.NEXT_SESSION)}
    LazyColumn(Modifier.fillMaxSize().padding(padding).padding(horizontal=14.dp),verticalArrangement=Arrangement.spacedBy(10.dp),contentPadding=PaddingValues(top=12.dp,bottom=24.dp)){
        item{CompactHeader("Upper Circuit",state,state.dualSummary?.uc?.completedAt?:0L,vm::runScan,"24h NEXT SESSION research • LIVE 09:15–15:30 • 3 PM final list")}
        item{
            Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.spacedBy(4.dp)){
                FilterChip(modifier=Modifier.weight(1f),selected=view==UcCompactView.NEXT_SESSION,onClick={view=UcCompactView.NEXT_SESSION},label={Text("NEXT ${nextCalls.size}",style=MaterialTheme.typography.labelSmall,maxLines=1)})
                FilterChip(modifier=Modifier.weight(1f),selected=view==UcCompactView.LIVE,onClick={view=UcCompactView.LIVE},label={Text("LIVE ${live.size}",style=MaterialTheme.typography.labelSmall,maxLines=1)})
                FilterChip(modifier=Modifier.weight(1f),selected=view==UcCompactView.THREE_PM,onClick={view=UcCompactView.THREE_PM},label={Text("3PM ${threePmCalls.size}",style=MaterialTheme.typography.labelSmall,maxLines=1)})
                FilterChip(modifier=Modifier.weight(1f),selected=view==UcCompactView.CLOSED,onClick={view=UcCompactView.CLOSED},label={Text("DONE ${closed.size}",style=MaterialTheme.typography.labelSmall,maxLines=1)})
            }
        }
        when(view){
            UcCompactView.NEXT_SESSION->{
                if(nextCalls.isEmpty())item{EmptyState("No next-session UC call yet","The off-hours engine keeps researching. A candidate is recorded here only when an entry plan is produced.")}
                else items(nextCalls.take(100),key={it.id}){r->
                    TradeCard(r.symbol,"NEXT SESSION • UC",r.score,tradeCallPlan(r),r.detail,"Target session ${r.targetSessionDate} • call ${formatIstTimestamp(r.openedAt)}")
                }
            }
            UcCompactView.LIVE->{
                if(live.isEmpty())item{EmptyState("No live upper-circuit call","The scanner will not force a stock into LIVE. NEXT and 3 PM lists remain available separately.")}
                else items(live,key={it.symbol}){c->TradeCard(c.symbol,"LONG • UC",c.score,ucPlan(c),"${c.companyName} • ${"%.2f".format(c.dayChangePercent)}% today • ${"%.1f".format(c.volumeRatio)}x volume","LIVE • each materially changed entry is logged as a separate call")}
            }
            UcCompactView.THREE_PM->{
                if(threePmCalls.isEmpty())item{EmptyState("No 3 PM list yet","The first qualifying scan at/after 15:00 IST freezes the final 3 PM list for the next trading session.")}
                else items(threePmCalls.take(50),key={it.id}){r->
                    TradeCard(r.symbol,"3 PM • UC",r.score,tradeCallPlan(r),r.detail,"Buy window 15:00–15:30 • target session ${r.targetSessionDate}")
                }
            }
            UcCompactView.CLOSED->{
                if(closed.isEmpty())item{EmptyState("No closed UC calls yet","Every timestamped UC call will finish here as WIN or LOSS.")}
                else items(closed.take(200),key={it.id}){r->
                    val base="${"%+.2f".format(r.returnPct)}% • ${r.closeReason} • opened ${formatIstTimestamp(r.openedAt)} • closed ${formatIstTimestamp(r.closedAt)}"
                    TradeCard(r.symbol,"${r.outcome.name} • ${r.bucket.name.replace('_',' ')} • UC",r.score,tradeCallPlan(r),r.detail,listOfNotNull(base,autopsyStatus(state,r.id)).joinToString("\n"))
                }
            }
        }
    }
}

@Composable
fun PressureCompactScreen(state:UiState,vm:MainViewModel,padding:PaddingValues){
    val shown=state.dualSummary?.demand?.candidates.orEmpty().filter{it.price>=20.0}
    val pressureWatchOnly=state.dualSummary?.demand?.message?.startsWith("WATCHLIST ONLY")==true
    val live=if(pressureWatchOnly) emptyList() else shown
    val calls=state.tradeCalls.filter{it.engine==TradeCallEngine.PRESSURE}
    val next=calls.filter{it.outcome==TradeCallOutcome.OPEN&&it.bucket==TradeCallBucket.NEXT_SESSION}.sortedByDescending{it.openedAt}
    val closed=calls.filter{it.outcome!=TradeCallOutcome.OPEN}.sortedByDescending{it.closedAt}
    var view by remember(state.marketSession.phase){mutableStateOf(if(state.marketSession.isOpen)PressureCompactView.LIVE else PressureCompactView.NEXT_SESSION)}
    LazyColumn(Modifier.fillMaxSize().padding(padding).padding(horizontal=14.dp),verticalArrangement=Arrangement.spacedBy(10.dp),contentPadding=PaddingValues(top=12.dp,bottom=24.dp)){
        item{CompactHeader("Pressure Prediction",state,state.dualSummary?.demand?.completedAt?:0L,vm::runScan)}
        item{
            Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.spacedBy(6.dp)){
                FilterChip(modifier=Modifier.weight(1f),selected=view==PressureCompactView.NEXT_SESSION,onClick={view=PressureCompactView.NEXT_SESSION},label={Text("NEXT ${next.size}",maxLines=1)})
                FilterChip(modifier=Modifier.weight(1f),selected=view==PressureCompactView.LIVE,onClick={view=PressureCompactView.LIVE},label={Text("LIVE ${live.size}",maxLines=1)})
                FilterChip(modifier=Modifier.weight(1f),selected=view==PressureCompactView.CLOSED,onClick={view=PressureCompactView.CLOSED},label={Text("DONE ${closed.size}",maxLines=1)})
            }
        }
        when(view){
            PressureCompactView.NEXT_SESSION->{
                if(next.isEmpty())item{EmptyState("No next-session pressure call","After the market closes, qualifying monitored pressure setups are carried here for the next session.")}
                else items(next.take(100),key={it.id}){r->TradeCard(r.symbol,"NEXT • BUY PRESSURE",r.score,tradeCallPlan(r),r.detail,"Target session ${r.targetSessionDate} • call ${formatIstTimestamp(r.openedAt)}")}
            }
            PressureCompactView.LIVE->{
                if(live.isEmpty())item{EmptyState("No live pressure setup","No executable NSE EQ pressure setup has cleared the LIVE threshold yet.")}
                else items(live,key={it.symbol}){c->TradeCard(c.symbol,"BUY PRESSURE",c.score,pressurePlan(c),"${c.companyName} • Buy/Sell ${"%.1f".format(c.buySellRatio)}x • Vol ${"%.1f".format(c.volumeRatio)}x","LIVE")}
            }
            PressureCompactView.CLOSED->{
                if(closed.isEmpty())item{EmptyState("No closed pressure calls","Every pressure call will finish here as WIN or LOSS.")}
                else items(closed.take(200),key={it.id}){r->
                    val base="${"%+.2f".format(r.returnPct)}% • ${r.closeReason} • opened ${formatIstTimestamp(r.openedAt)}"
                    TradeCard(r.symbol,"${r.outcome.name} • PRESSURE",r.score,tradeCallPlan(r),r.detail,listOfNotNull(base,autopsyStatus(state,r.id)).joinToString("\n"))
                }
            }
        }
    }
}

@Composable
fun StrategiesCompactScreen(state:UiState,vm:MainViewModel,padding:PaddingValues){
    var view by remember{mutableStateOf(CompactView.LIVE)}
    val visibleLive=if(state.marketSession.isOpen)state.strategyLive else emptyList()
    val visibleWatch=if(state.marketSession.isOpen)state.strategyTournamentSummary?.topSetups.orEmpty().filter{w->visibleLive.none{it.setup.symbol==w.symbol&&it.setup.direction==w.direction}} else emptyList()
    LazyColumn(Modifier.fillMaxSize().padding(padding).padding(horizontal=14.dp),verticalArrangement=Arrangement.spacedBy(10.dp),contentPadding=PaddingValues(top=12.dp,bottom=24.dp)){
        item{CompactHeader("Trading Strategies",state,state.lastStrategyScanAt,vm::refreshTradingStrategies)}
        item{
            val attempt=if(state.lastStrategyAttemptAt>0)formatIstTimestamp(state.lastStrategyAttemptAt) else "not yet"
            val success=if(state.lastStrategyScanAt>0)formatIstTimestamp(state.lastStrategyScanAt) else "not yet"
            val errorSuffix=if(state.lastStrategyError.isNotBlank())" • last error ${if(state.lastStrategyErrorAt>0)formatIstTimestamp(state.lastStrategyErrorAt) else ""}: ${state.lastStrategyError.take(110)}" else ""
            Text("Scheduler • attempt $attempt • success $success$errorSuffix",style=MaterialTheme.typography.labelSmall,
                color=if(state.lastStrategyError.isNotBlank())MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.onSurfaceVariant)
        }
        state.strategyTournamentSummary?.message?.takeIf{it.isNotBlank()}?.let{msg->item{Text("Engine • $msg",style=MaterialTheme.typography.labelSmall,color=MaterialTheme.colorScheme.onSurfaceVariant)}}
        item{ViewSwitch(view,{view=it},visibleLive.size,state.strategyClosed.size)}
        if(view==CompactView.LIVE){
            if(visibleLive.isEmpty()&&visibleWatch.isEmpty())item{EmptyState(if(state.marketSession.isOpen)"No live strategy call" else "Market closed • no LIVE strategy calls",if(state.marketSession.isOpen)"Scanner is running; no liquid setup has reached the LIVE threshold yet." else "Intraday strategy calls are closed and scored after the session; they never remain LIVE overnight.")}
            else{
                if(visibleLive.isNotEmpty())items(visibleLive,key={it.id}){r->
                    val s=r.setup
                    TradeCard(s.symbol,"${s.direction.name} • ${s.strategyName}",s.score,strategyPlan(s),s.evidence,"LIVE • opened ${formatIstTimestamp(r.openedAt)} • spread ${"%.2f".format(r.spreadPct)}%")
                }
                if(visibleWatch.isNotEmpty()){
                    item{Text("WATCH ${visibleWatch.take(5).size}",style=MaterialTheme.typography.labelMedium,fontWeight=FontWeight.Bold,color=MaterialTheme.colorScheme.onSurfaceVariant)}
                    items(visibleWatch.take(5),key={"watch-${it.symbol}-${it.direction}"}){s->TradeCard(s.symbol,"WATCH • ${s.direction.name} • ${s.strategyName}",s.score,strategyPlan(s),s.evidence,"Monitoring only • not counted as a call")}
                }
            }
        }else{
            if(state.strategyClosed.isEmpty())item{EmptyState("No closed strategy calls","Every intraday strategy call will finish here as WIN or LOSS.")}
            else items(state.strategyClosed.take(200),key={it.id}){r->
                val s=r.setup;val outcome=if(r.status==StrategyRecommendationStatus.WIN)"WIN" else "LOSS"
                val base="${"%+.2f".format(r.returnPct)}% • ${r.closeReason} • opened ${formatIstTimestamp(r.openedAt)} • closed ${formatIstTimestamp(r.closedAt)}"
                TradeCard(s.symbol,"$outcome • ${s.direction.name} • ${s.strategyName}",s.score,strategyPlan(s),s.evidence,listOfNotNull(base,autopsyStatus(state,"STRATEGY|${r.id}")).joinToString("\n"))
            }
        }
    }
}

@Composable
fun GlobalCompactScreen(state:UiState,vm:MainViewModel,padding:PaddingValues){
    val summary=state.globalLeadSummary
    val all=summary?.candidates.orEmpty().sortedByDescending{it.score}
    val next=all.filter{it.action==GlobalLeadAction.NEXT_OPEN_WATCH}
    val live=all.filter{(it.action==GlobalLeadAction.ENTER_AFTER_OPEN||it.action==GlobalLeadAction.KEEP_NEXT_SESSION)&&it.indianPrice>=20.0}
    val watch=all.filter{it.action==GlobalLeadAction.WAIT_FOR_CONFIRMATION||it.action==GlobalLeadAction.OBSERVE}.take(6)
    val closed=state.tradeCalls.filter{it.engine==TradeCallEngine.GLOBAL&&it.outcome!=TradeCallOutcome.OPEN}.sortedByDescending{it.closedAt}
    val preOpen=state.marketSession.phase!=MarketPhase.OPEN
    var view by remember(state.marketSession.phase){mutableStateOf(if(preOpen)GlobalCompactView.NEXT_SESSION else GlobalCompactView.LIVE)}
    LazyColumn(Modifier.fillMaxSize().padding(padding).padding(horizontal=14.dp),verticalArrangement=Arrangement.spacedBy(10.dp),contentPadding=PaddingValues(top=12.dp,bottom=24.dp)){
        item{CompactHeader("Global Lead",state,state.lastGlobalLeadScanAt,vm::refreshGlobalLead,"24h global-market research • India confirmation from 09:15 IST")}
        item{
            Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.spacedBy(6.dp)){
                FilterChip(modifier=Modifier.weight(1f),selected=view==GlobalCompactView.NEXT_SESSION,onClick={view=GlobalCompactView.NEXT_SESSION},label={Text("NEXT ${next.size}",maxLines=1)})
                FilterChip(modifier=Modifier.weight(1f),selected=view==GlobalCompactView.LIVE,onClick={view=GlobalCompactView.LIVE},label={Text("LIVE ${live.size}",maxLines=1)})
                FilterChip(modifier=Modifier.weight(1f),selected=view==GlobalCompactView.CLOSED,onClick={view=GlobalCompactView.CLOSED},label={Text("DONE ${closed.size}",maxLines=1)})
            }
        }
        when(view){
            GlobalCompactView.NEXT_SESSION->{
                if(next.isEmpty()&&watch.isEmpty())item{EmptyState("No next-session global signal yet",summary?.message?:"Global mapping scan is running; India execution confirmation starts at 09:15 IST.")}
                else{
                    if(next.isNotEmpty())items(next,key={"next-${it.direction}-${it.indianSymbol}"}){c->
                        val indiaRef=if(c.indianPrice>=20.0)" • India ref ₹${"%.2f".format(c.indianPrice)}" else " • India reference pending"
                        TradeCard(c.indianSymbol,"NEXT SESSION • ${c.direction.name}",c.score,globalPlan(c),"Lead ${c.foreignTicker} • ${c.exchange} • foreign ${"%.2f".format(c.foreignDayPct)}%$indiaRef","Research signal • live entry revalidated after 09:15 IST")
                    }
                    if(watch.isNotEmpty()){
                        item{Text("RESEARCH WATCH ${watch.size}",style=MaterialTheme.typography.labelMedium,fontWeight=FontWeight.Bold,color=MaterialTheme.colorScheme.onSurfaceVariant)}
                        items(watch,key={"global-watch-${it.direction}-${it.indianSymbol}"}){c->TradeCard(c.indianSymbol,"WATCH • ${c.direction.name}",c.score,globalPlan(c),"Lead ${c.foreignTicker} • ${c.exchange} • foreign ${"%.2f".format(c.foreignDayPct)}%","Below NEXT confirmation threshold • not counted as a call")}
                    }
                }
            }
            GlobalCompactView.LIVE->{
                if(live.isEmpty())item{EmptyState("No confirmed live global entry","NEXT candidates move here after Indian price/liquidity confirmation. Each materially changed entry becomes a separate timestamped call.")}
                else items(live,key={"live-${it.direction}-${it.indianSymbol}"}){c->TradeCard(c.indianSymbol,c.direction.name,c.score,globalPlan(c),"Lead ${c.foreignTicker} • ${c.exchange} • foreign ${"%.2f".format(c.foreignDayPct)}% • India ${"%.2f".format(c.indianFromOpenPct)}%","LIVE • ${c.action.name.replace('_',' ')}")}
            }
            GlobalCompactView.CLOSED->{
                if(closed.isEmpty())item{EmptyState("No closed global calls","Every price-specific Global call will finish here as WIN or LOSS, including repeated calls for the same stock.")}
                else items(closed.take(250),key={it.id}){r->
                    val base="${"%+.2f".format(r.returnPct)}% • ${r.closeReason} • opened ${formatIstTimestamp(r.openedAt)} • closed ${formatIstTimestamp(r.closedAt)}"
                    TradeCard(r.symbol,"${r.outcome.name} • ${r.direction.name} • GLOBAL",r.score,tradeCallPlan(r),r.detail,listOfNotNull(base,autopsyStatus(state,r.id)).joinToString("\n"))
                }
            }
        }
    }
}

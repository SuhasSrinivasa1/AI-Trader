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
import com.suhas.globaledgeai.domain.model.StrategyStatus
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.zip.ZipEntry
import java.util.zip.ZipOutputStream

private enum class QuantSection { HOME, ARBITRAGE, HEDGING, DIRECTIONAL_FNO, LEARNING }
private data class Lane(val name:String,val detail:String,val status:String)

private val arbitrageLanes=listOf(
    Lane("Cash ↔ Futures Basis","Fair-value basis, carry, expiry and execution-cost comparison","SHADOW"),
    Lane("Future ↔ Synthetic Future","Put-call parity residual across matched strike/expiry","SHADOW"),
    Lane("Futures Calendar","Near vs next/far expiry term-structure convergence","SHADOW"),
    Lane("Conversion / Reversal","Stock/future + call + put parity structures","SHADOW"),
    Lane("Box / Option Relative Value","Defined-payoff option relationships after all costs","SHADOW"),
    Lane("Cross-Market Equivalent","NSE/BSE only when contract equivalence and depth pass","SHADOW")
)

private val hedgeLanes=listOf(
    Lane("Dynamic Partial Hedge","Adaptive 10–80% hedge ratio; never max-hedge by default","MODEL"),
    Lane("Protective Put","Tail-risk protection when premium is economically justified","MODEL"),
    Lane("Put Spread","Lower-cost downside protection with defined protection range","MODEL"),
    Lane("Collar","Put protection financed partly by capped upside","MODEL"),
    Lane("Index / Sector Hedge","Compare stock hedge vs NIFTY/BANKNIFTY/sector hedge efficiency","MODEL"),
    Lane("Profit-Lock Hedge","Increase protection as accumulated profit and event risk rise","MODEL"),
    Lane("Event Hedge","Temporary protection around earnings/regulatory/event gaps","MODEL"),
    Lane("Residual Delta Hedge","Neutralize leftover directional exposure from arbitrage legs","MODEL")
)


private val directionalLanes=listOf(
    Lane("Multi-Timeframe Momentum","1/3/5/15/30-minute trend, VWAP, breakout and ATR-normalized momentum","SHADOW"),
    Lane("Futures Price + OI","Long/short buildup, short covering and long unwinding confirmation","SHADOW"),
    Lane("Futures Basis + Spot Trend","Direction plus changing future premium/discount versus underlying","SHADOW"),
    Lane("Option Chain + Greeks","OI, volume, Delta, Gamma, Theta, Vega and strike concentration","SHADOW"),
    Lane("IV / Skew / Expected Move","Select future vs option/spread based on volatility economics","SHADOW"),
    Lane("Order Flow","Bid/ask depth, imbalance, spread, liquidity removal and quote persistence","SHADOW"),
    Lane("News + Event Reaction","Materiality + novelty + actual price/volume/OI confirmation","SHADOW"),
    Lane("Global Overnight Lead","US/Europe/Asia/FX/commodities as probabilistic opening features","SHADOW"),
    Lane("Sector + Market Breadth","Relative strength versus sector/index plus market breadth","SHADOW"),
    Lane("Candle Ensemble","Candlestick families as confirmation features, never standalone orders","SHADOW"),
    Lane("NO EDGE Gate","No trade when probability, liquidity or expected net value is insufficient","ACTIVE")
)

@Composable
fun QuantV22Screen(state:UiState,vm:MainViewModel,padding:PaddingValues){
    val ctx=LocalContext.current
    val zone=remember{ZoneId.of("Asia/Kolkata")}
    val prefs=remember{ctx.getSharedPreferences("quant_v22",Context.MODE_PRIVATE)}
    var section by remember{ mutableStateOf(QuantSection.HOME) }
    var shadowCapitalText by remember{ mutableStateOf(prefs.getInt("shadow_capital",500000).toString()) }
    var monthOpen by remember{ mutableStateOf(false) }
    var exportStatus by remember{ mutableStateOf<String?>(null) }
    val shadowCapital=shadowCapitalText.toIntOrNull()?.coerceIn(10_000,20_000_000)?:500_000
    val today=LocalDate.now(zone)

    val todayRows=state.strategyClosed.filter{
        Instant.ofEpochMilli(it.closedAt).atZone(zone).toLocalDate()==today
    }
    val monthRows=state.strategyClosed.filter{
        val d=Instant.ofEpochMilli(it.closedAt).atZone(zone).toLocalDate()
        d.year==today.year&&d.month==today.month
    }
    val allArbRows=QuantGovernance.arbitrageRows(state.strategyClosed)
    val todayArbRows=QuantGovernance.arbitrageRows(todayRows)
    val monthArbRows=QuantGovernance.arbitrageRows(monthRows)
    val todayArbPnl=QuantGovernance.shadowPnl(todayArbRows,shadowCapital.toDouble())
    val monthArbPnl=QuantGovernance.shadowPnl(monthArbRows,shadowCapital.toDouble())
    val allDirectionalRows=QuantGovernance.directionalRows(state.strategyClosed)
    val todayDirectionalRows=QuantGovernance.directionalRows(todayRows)
    val monthDirectionalRows=QuantGovernance.directionalRows(monthRows)
    val todayDirectionalPnl=QuantGovernance.shadowPnl(todayDirectionalRows,shadowCapital.toDouble())
    val monthDirectionalPnl=QuantGovernance.shadowPnl(monthDirectionalRows,shadowCapital.toDouble())
    val todayHedge=QuantGovernance.hedgeShadow(todayDirectionalRows,shadowCapital.toDouble())
    val monthHedge=QuantGovernance.hedgeShadow(monthDirectionalRows,shadowCapital.toDouble())
    val combinations=QuantGovernance.combinationStats(state.strategyClosed)
    val directionalCombinations=QuantGovernance.combinationStats(allDirectionalRows)
    val hedgePolicies=QuantGovernance.hedgePolicyStats(allDirectionalRows,shadowCapital.toDouble())
    val engineChampions=QuantGovernance.engineChampions(state.strategyClosed,shadowCapital.toDouble())
    val meta=QuantGovernance.metaAllocation(state.strategyClosed,shadowCapital.toDouble())
    val perfs=state.strategyTournamentSummary?.performances.orEmpty()
    val champions=perfs.filter{it.status==StrategyStatus.CHAMPION}
    val active=perfs.filter{it.status==StrategyStatus.ACTIVE}
    val challengers=perfs.filter{it.status==StrategyStatus.CHALLENGER}
    val probation=perfs.filter{it.status==StrategyStatus.PROBATION}
    val suspended=perfs.filter{it.status==StrategyStatus.SUSPENDED}
    val currentHedgeRatio=run{
        val recent=state.strategyClosed.takeLast(20)
        val win=if(recent.size>=5)recent.count{it.status.name=="WIN"}*100.0/recent.size else null
        val avg=if(recent.size>=5)recent.map{it.returnPct}.average() else null
        val score=state.strategyLive.map{it.setup.score}.average().takeIf{it.isFinite()}?:78.0
        QuantGovernance.dynamicHedgeRatio(score,win,avg)
    }

    val exporter=rememberLauncherForActivityResult(ActivityResultContracts.CreateDocument("application/zip")){uri->
        if(uri!=null){
            runCatching{
                val app=ctx.applicationContext as GlobalEdgeApplication
                val repo=app.repository
                val out=ctx.contentResolver.openOutputStream(uri)?:error("Unable to open selected file")
                ZipOutputStream(out.buffered()).use{zip->
                    fun put(name:String,text:String){zip.putNextEntry(ZipEntry(name));zip.write(text.toByteArray());zip.closeEntry()}
                    put("README.txt",buildString{
                        appendLine("Global Quant Trader v2.2 complete export")
                        appendLine("Version: ${BuildConfig.VERSION_NAME}")
                        appendLine("Generated: ${java.time.ZonedDateTime.now(zone)}")
                        appendLine("Shadow capital: ₹$shadowCapital")
                        appendLine("Arbitrage shadow today: ${"%.2f".format(todayArbPnl)}")
                        appendLine("Hedge model benefit today: ${"%.2f".format(todayHedge.hedgeBenefit)}")
                        appendLine("Directional F&O shadow today: ${"%.2f".format(todayDirectionalPnl)}")
                        appendLine("Meta allocation: ARB ${meta.arbitragePct}% | HEDGE ${meta.hedgingPct}% | DIR ${meta.directionalPct}%")
                        appendLine("Groww authenticated: ${state.authenticated}")
                        appendLine("Static IP match: ${state.staticIpMatch}")
                        appendLine("F&O live derivative routing: LOCKED in v2.2; arbitrage, hedging and directional F&O are shadow/modelled until verified execution is wired.")
                    })
                    put("quant_governance.txt",QuantGovernance.governanceText(state.strategyClosed,shadowCapital.toDouble()))
                    put("strategy_tournament.txt",state.strategyTournamentSummary?.toString()?:"NO STRATEGY TOURNAMENT SUMMARY")
                    put("combination_champions.csv",buildString{
                        appendLine("status,combination,samples,wins,accuracyPct,avgReturnPct,maxDrawdownPct,recentAvgPct")
                        combinations.forEach{c->appendLine("${c.status},${c.label.replace(',',' ')},${c.samples},${c.wins},${c.accuracyPct},${c.avgReturnPct},${c.maxDrawdownPct},${c.recentAvgPct}")}
                    })
                    put("hedge_shadow_summary.csv",buildString{
                        appendLine("window,observations,unhedgedPnl,hedgedPnl,hedgeCost,hedgeBenefit,avgHedgeRatio")
                        appendLine("today,${todayHedge.observations},${todayHedge.unhedgedPnl},${todayHedge.hedgedPnl},${todayHedge.hedgeCost},${todayHedge.hedgeBenefit},${todayHedge.averageHedgeRatio}")
                        appendLine("month,${monthHedge.observations},${monthHedge.unhedgedPnl},${monthHedge.hedgedPnl},${monthHedge.hedgeCost},${monthHedge.hedgeBenefit},${monthHedge.averageHedgeRatio}")
                    })
                    put("engine_champions.csv",buildString{
                        appendLine("engine,status,samples,label,metric")
                        engineChampions.forEach{e->appendLine("${e.engine},${e.status},${e.samples},${e.label.replace(',',' ')},${e.metric.replace(',',' ')}")}
                    })
                    put("hedge_policy_champions.csv",buildString{
                        appendLine("status,name,observations,hedgedPnl,hedgeCost,maxDrawdown,drawdownReduction,avgHedgeRatio,utility")
                        hedgePolicies.forEach{h->appendLine("${h.status},${h.name.replace(',',' ')},${h.observations},${h.hedgedPnl},${h.hedgeCost},${h.maxDrawdown},${h.drawdownReduction},${h.avgHedgeRatio},${h.utility}")}
                    })
                    put("directional_combinations.csv",buildString{
                        appendLine("status,combination,samples,wins,accuracyPct,avgReturnPct,maxDrawdownPct,recentAvgPct")
                        directionalCombinations.forEach{c->appendLine("${c.status},${c.label.replace(',',' ')},${c.samples},${c.wins},${c.accuracyPct},${c.avgReturnPct},${c.maxDrawdownPct},${c.recentAvgPct}")}
                    })
                    put("closed_strategy_ledger.csv",buildString{
                        appendLine("id,strategy,symbol,status,score,returnPct,openedAt,closedAt,combination")
                        state.strategyClosed.forEach{r->appendLine("${r.id},${r.setup.strategyName.replace(',',' ')},${r.setup.symbol},${r.status},${r.setup.score},${r.returnPct},${r.openedAt},${r.closedAt},${r.setup.handbookCombination.replace(',',' ')}")}
                    })
                    put("challenger_shadow.txt",state.challengerShadows.joinToString("\n"){it.toString()})
                    put("decision_snapshot.txt",state.decisionSnapshots.joinToString("\n"){it.toString()})
                    put("news_snapshot.txt",state.newsItems.joinToString("\n"){"${it.source}|${it.symbol}|${it.publishedAt}|${it.title}"})
                    put("broker_orders_snapshot.txt",state.brokerOrders.joinToString("\n"){it.toString()})
                    put("weekly_learning_report.txt",repo.weeklyLearningReport())
                    put("diagnostic_state.txt",repo.endOfDayDiagnosticReport())
                    put("device_log.txt",DiagnosticLog.weeklySnapshot(ctx,repo.weeklyLearningReport()))
                }
            }.onSuccess{exportStatus="Complete v2.2 log ZIP saved"}.onFailure{exportStatus="Export failed: ${it.message}"}
        }
    }

    if(monthOpen){
        AlertDialog(
            onDismissRequest={monthOpen=false},
            title={Text("${today.month.name.lowercase().replaceFirstChar{it.uppercase()}} ${today.year} shadow analytics")},
            text={
                Column(verticalArrangement=Arrangement.spacedBy(7.dp)){
                    Text("Shadow capital  ₹%,d".format(shadowCapital))
                    Text("Arbitrage shadow net  ₹%,.0f".format(monthArbPnl),fontWeight=FontWeight.Bold)
                    Text("Directional F&O shadow net  ₹%,.0f".format(monthDirectionalPnl),fontWeight=FontWeight.Bold)
                    Text("Hedge-model economic benefit  ₹%,.0f".format(monthHedge.hedgeBenefit),fontWeight=FontWeight.Bold,
                        color=if(monthHedge.hedgeBenefit>=0)Color(0xFF2E7D32) else Color(0xFFC62828))
                    Text("Hedge cost reserve  ₹%,.0f".format(monthHedge.hedgeCost))
                    Text("Closed observations  ${monthRows.size}")
                    Text("The hedge figure is a shadow model of partial opposite exposure, not realized option/futures P&L.",style=MaterialTheme.typography.bodySmall)
                }
            },
            confirmButton={Button(onClick={monthOpen=false}){Text("Close")}}
        )
    }

    LazyColumn(
        Modifier.fillMaxSize().padding(padding).padding(horizontal=14.dp),
        verticalArrangement=Arrangement.spacedBy(10.dp),
        contentPadding=PaddingValues(bottom=28.dp)
    ){
        item{
            ElevatedCard(Modifier.fillMaxWidth()){
                Column(Modifier.padding(16.dp),verticalArrangement=Arrangement.spacedBy(8.dp)){
                    Text("GLOBAL QUANT TRADER v2.2",style=MaterialTheme.typography.titleLarge,fontWeight=FontWeight.Bold)
                    Row(Modifier.fillMaxWidth(),verticalAlignment=Alignment.CenterVertically){
                        Column(Modifier.weight(1f)){
                            Text("MASTER LIVE",fontWeight=FontWeight.Bold)
                            Text("OFF • verified F&O live route locked",color=Color(0xFF2E7D32))
                        }
                        Switch(checked=false,onCheckedChange={},enabled=false)
                    }
                    Text("Groww ${if(state.authenticated)"AUTHENTICATED" else "NOT AUTHENTICATED"} • Static IP ${when(state.staticIpMatch){true->"MATCH";false->"MISMATCH";null->"UNCHECKED"}}",style=MaterialTheme.typography.bodySmall)
                    Text("One scanner → Arbitrage + Hedging + Directional F&O → three Champions → Meta Champion.",style=MaterialTheme.typography.bodySmall)
                }
            }
        }

        item{
            Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.spacedBy(6.dp)){
                QuantSection.entries.forEach{s->
                    FilterChip(
                        selected=section==s,
                        onClick={section=s},
                        label={Text(s.name.lowercase().replaceFirstChar{it.uppercase()})},
                        modifier=Modifier.weight(1f)
                    )
                }
            }
        }

        when(section){
            QuantSection.HOME->{
                item{
                    ElevatedCard(Modifier.fillMaxWidth().clickable{monthOpen=true}){
                        Column(Modifier.padding(16.dp),verticalArrangement=Arrangement.spacedBy(4.dp)){
                            Text("TODAY • SHADOW SUMMARY",fontWeight=FontWeight.Bold)
                            Text("Arbitrage  ₹%,.0f".format(todayArbPnl),style=MaterialTheme.typography.headlineSmall)
                            Text("Directional F&O  ₹%,.0f".format(todayDirectionalPnl),style=MaterialTheme.typography.headlineSmall)
                            Text("Hedge economic benefit  ₹%,.0f".format(todayHedge.hedgeBenefit),style=MaterialTheme.typography.headlineSmall,
                                color=if(todayHedge.hedgeBenefit>=0)Color(0xFF2E7D32) else Color(0xFFC62828))
                            Text("Tap for monthly view")
                        }
                    }
                }
                item{
                    Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.spacedBy(10.dp)){
                        ElevatedCard(Modifier.weight(1f).clickable{section=QuantSection.ARBITRAGE}){
                            Column(Modifier.padding(14.dp)){Text("ARBITRAGE",fontWeight=FontWeight.Bold);Text("${arbitrageLanes.size} lanes");Text("${todayArbRows.size} genuine tagged exits today",style=MaterialTheme.typography.bodySmall)}
                        }
                        ElevatedCard(Modifier.weight(1f).clickable{section=QuantSection.HEDGING}){
                            Column(Modifier.padding(14.dp)){Text("HEDGING",fontWeight=FontWeight.Bold);Text("Dynamic ratio ${"%.0f".format(currentHedgeRatio*100)}%");Text("${todayHedge.observations} shadow exposures",style=MaterialTheme.typography.bodySmall)}
                        }
                    }
                }
                item{
                    ElevatedCard(Modifier.fillMaxWidth().clickable{section=QuantSection.DIRECTIONAL_FNO}){
                        Column(Modifier.padding(14.dp)){
                            Text("DIRECTIONAL FUTURES & OPTIONS",fontWeight=FontWeight.Bold)
                            Text("Shadow ₹%,.0f • ${todayDirectionalRows.size} closed observations".format(todayDirectionalPnl))
                            Text("UP / DOWN / NO EDGE → Future / Call / Put / defined-risk spread / NO TRADE",style=MaterialTheme.typography.bodySmall)
                        }
                    }
                }
                item{
                    ElevatedCard(Modifier.fillMaxWidth()){
                        Column(Modifier.padding(14.dp),verticalArrangement=Arrangement.spacedBy(4.dp)){
                            Text("META CHAMPION",fontWeight=FontWeight.Bold)
                            Text("Arbitrage ${meta.arbitragePct}% • Hedge reserve ${meta.hedgingPct}% • Directional F&O ${meta.directionalPct}%")
                            Text(meta.rationale,style=MaterialTheme.typography.bodySmall)
                        }
                    }
                }
                item{
                    ElevatedCard(Modifier.fillMaxWidth().clickable{section=QuantSection.LEARNING}){
                        Column(Modifier.padding(14.dp),verticalArrangement=Arrangement.spacedBy(4.dp)){
                            Text("LEARNING / CHAMPIONS",fontWeight=FontWeight.Bold)
                            Text("Core champions ${champions.size} • active ${active.size} • challengers ${challengers.size}")
                            Text("Combination champions ${combinations.count{it.status=="CHAMPION"}} • probation/suspended ${probation.size+suspended.size}")
                            Text("Daily learning + weekly catalogue refresh are retained and exposed here.",style=MaterialTheme.typography.bodySmall)
                        }
                    }
                }
                item{
                    state.globalLeadSummary?.let{g->
                        ElevatedCard(Modifier.fillMaxWidth()){Column(Modifier.padding(14.dp)){Text("GLOBAL → INDIA LEAD",fontWeight=FontWeight.Bold);Text(g.message);Text("Global movement is a probabilistic feature; Indian price/volume/news confirmation remains required.",style=MaterialTheme.typography.bodySmall)}}
                    }
                }
            }

            QuantSection.ARBITRAGE->{
                item{
                    ElevatedCard(Modifier.fillMaxWidth().clickable{monthOpen=true}){
                        Column(Modifier.padding(16.dp)){
                            Text("ARBITRAGE SHADOW P&L",fontWeight=FontWeight.Bold)
                            Text("₹%,.0f".format(todayArbPnl),style=MaterialTheme.typography.headlineMedium)
                            Text("${todayArbRows.size} tagged relative-value/arbitrage exits today • tap monthly")
                            if(allArbRows.isEmpty())Text("No genuine F&O parity/basis fills are recorded yet; this remains shadow-locked rather than fabricating arbitrage P&L.",style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                    }
                }
                item{Text("Arbitrage lanes",style=MaterialTheme.typography.titleMedium,fontWeight=FontWeight.Bold)}
                items(arbitrageLanes){l->LaneCard(l)}
                item{
                    ElevatedCard(Modifier.fillMaxWidth()){
                        Column(Modifier.padding(14.dp)){
                            Text("ENTRY GATE",fontWeight=FontWeight.Bold)
                            Text("Gross mispricing − brokerage/taxes − bid/ask slippage − hedge-leg reserve − margin cost must remain positive.")
                            Text("Any one-leg fill becomes an execution failure requiring completion or unwind; it is never treated as an arbitrage win.",style=MaterialTheme.typography.bodySmall)
                        }
                    }
                }
            }

            QuantSection.HEDGING->{
                item{
                    ElevatedCard(Modifier.fillMaxWidth().clickable{monthOpen=true}){
                        Column(Modifier.padding(16.dp),verticalArrangement=Arrangement.spacedBy(4.dp)){
                            Text("HEDGE SHADOW ECONOMIC BENEFIT",fontWeight=FontWeight.Bold)
                            Text("₹%,.0f".format(todayHedge.hedgeBenefit),style=MaterialTheme.typography.headlineMedium,
                                color=if(todayHedge.hedgeBenefit>=0)Color(0xFF2E7D32) else Color(0xFFC62828))
                            Text("Current model hedge ratio ${"%.0f".format(currentHedgeRatio*100)}%")
                            Text("Unhedged ₹%,.0f • shadow hedged ₹%,.0f • cost reserve ₹%,.0f".format(todayHedge.unhedgedPnl,todayHedge.hedgedPnl,todayHedge.hedgeCost))
                            Text("Tap for monthly comparison")
                        }
                    }
                }
                item{
                    ElevatedCard(Modifier.fillMaxWidth()){
                        Column(Modifier.padding(14.dp),verticalArrangement=Arrangement.spacedBy(4.dp)){
                            Text("DYNAMIC HEDGE POLICY",fontWeight=FontWeight.Bold)
                            Text("Target: protect downside at the lowest sensible cost while retaining economically useful upside.")
                            Text("The shadow ratio adapts from pre-entry score and prior realized strategy quality; 100% is not the default.",style=MaterialTheme.typography.bodySmall)
                        }
                    }
                }
                items(hedgeLanes){l->LaneCard(l)}
                item{
                    Text("v2.2 hedge P&L is explicitly modelled, using linear partial opposite exposure plus a cost reserve. Real protective-put/collar/futures P&L requires the verified F&O quote/margin/execution layer and is not represented as live here.",style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }

            QuantSection.DIRECTIONAL_FNO->{
                item{
                    ElevatedCard(Modifier.fillMaxWidth().clickable{monthOpen=true}){
                        Column(Modifier.padding(16.dp),verticalArrangement=Arrangement.spacedBy(4.dp)){
                            Text("DIRECTIONAL F&O SHADOW P&L",fontWeight=FontWeight.Bold)
                            Text("₹%,.0f".format(todayDirectionalPnl),style=MaterialTheme.typography.headlineMedium,
                                color=if(todayDirectionalPnl>=0)Color(0xFF2E7D32) else Color(0xFFC62828))
                            Text("${todayDirectionalRows.size} completed directional observations • tap monthly")
                            Text("Stage 1: UP / DOWN / NO EDGE. Stage 2: Future / Call / Put / defined-risk spread / NO TRADE.",style=MaterialTheme.typography.bodySmall)
                        }
                    }
                }
                item{
                    engineChampions.firstOrNull{it.engine=="DIRECTIONAL F&O"}?.let{e->
                        ElevatedCard(Modifier.fillMaxWidth()){
                            Column(Modifier.padding(14.dp)){
                                Text("DIRECTIONAL CHAMPION • ${e.status}",fontWeight=FontWeight.Bold)
                                Text(e.label)
                                Text("n=${e.samples} • ${e.metric}",style=MaterialTheme.typography.bodySmall)
                            }
                        }
                    }
                }
                item{Text("Directional signal families",style=MaterialTheme.typography.titleMedium,fontWeight=FontWeight.Bold)}
                items(directionalLanes){l->LaneCard(l)}
                item{Text("Directional combination discovery",style=MaterialTheme.typography.titleMedium,fontWeight=FontWeight.Bold)}
                if(directionalCombinations.isEmpty()) item{Text("No completed directional evidence yet. Signals remain shadow-only until outcomes accumulate.")}
                else items(directionalCombinations.take(15)){c->
                    ElevatedCard(Modifier.fillMaxWidth()){
                        Row(Modifier.padding(12.dp),verticalAlignment=Alignment.CenterVertically){
                            Column(Modifier.weight(1f)){
                                Text(c.label,fontWeight=FontWeight.SemiBold)
                                Text("n=${c.samples} • win ${"%.1f".format(c.accuracyPct)}% • avg ${"%+.2f".format(c.avgReturnPct)}% • recent ${"%+.2f".format(c.recentAvgPct)}% • DD ${"%.2f".format(c.maxDrawdownPct)}%",style=MaterialTheme.typography.bodySmall)
                            }
                            AssistChip(onClick={},label={Text(c.status)})
                        }
                    }
                }
            }

            QuantSection.LEARNING->{
                item{
                    ElevatedCard(Modifier.fillMaxWidth()){
                        Column(Modifier.padding(14.dp),verticalArrangement=Arrangement.spacedBy(5.dp)){
                            Text("THREE ENGINE CHAMPIONS + META CHAMPION",fontWeight=FontWeight.Bold)
                            Text("Champions ${champions.size} • Active ${active.size} • Challengers ${challengers.size} • Probation ${probation.size} • Suspended ${suspended.size}")
                            Text("Catalogue ${state.strategyCatalogVersion.ifBlank{"embedded"}} • closed evidence ${state.strategyClosed.size} • challenger shadows ${state.challengerShadows.size}")
                            engineChampions.forEach{e->Text("${e.engine}: ${e.status} • ${e.label}",style=MaterialTheme.typography.bodySmall)}
                            Text("Meta allocation: ARB ${meta.arbitragePct}% • HEDGE ${meta.hedgingPct}% • DIR ${meta.directionalPct}%",style=MaterialTheme.typography.bodySmall)
                            Text("Promotion uses sample size, positive expectancy, confidence floor, holdout evidence, walk-forward stability, recent-decay checks and a max-drawdown gate.",style=MaterialTheme.typography.bodySmall)
                        }
                    }
                }
                item{
                    Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.spacedBy(8.dp)){
                        Button(onClick=vm::runLearningNow,enabled=!state.busy,modifier=Modifier.weight(1f)){Text("RUN DAILY LEARNING")}
                        OutlinedButton(onClick=vm::refreshStrategyCatalog,enabled=!state.busy,modifier=Modifier.weight(1f)){Text("WEEKLY REFRESH")}
                    }
                }
                if(state.status.isNotBlank())item{Text(state.status,style=MaterialTheme.typography.bodySmall)}
                if(champions.isNotEmpty()){
                    item{Text("Core champions",style=MaterialTheme.typography.titleMedium,fontWeight=FontWeight.Bold)}
                    items(champions.take(12)){p->
                        ElevatedCard(Modifier.fillMaxWidth()){Column(Modifier.padding(12.dp)){Text(p.name,fontWeight=FontWeight.SemiBold);Text("n=${p.observations} • win ${"%.1f".format(p.accuracyPct)}% • avg ${"%+.2f".format(p.avgReturnPct)}% • maxDD ${"%.2f".format(p.maxDrawdownPct)}%",style=MaterialTheme.typography.bodySmall)}}
                    }
                }
                item{Text("Combination discovery",style=MaterialTheme.typography.titleMedium,fontWeight=FontWeight.Bold)}
                if(combinations.isEmpty())item{Text("No completed combination evidence yet. The daily learner will populate this from closed strategy observations.")}
                else items(combinations.take(20)){c->
                    ElevatedCard(Modifier.fillMaxWidth()){
                        Row(Modifier.padding(12.dp),verticalAlignment=Alignment.CenterVertically){
                            Column(Modifier.weight(1f)){
                                Text(c.label,fontWeight=FontWeight.SemiBold)
                                Text("n=${c.samples} • win ${"%.1f".format(c.accuracyPct)}% • avg ${"%+.2f".format(c.avgReturnPct)}% • recent ${"%+.2f".format(c.recentAvgPct)}% • DD ${"%.2f".format(c.maxDrawdownPct)}%",style=MaterialTheme.typography.bodySmall)
                            }
                            AssistChip(onClick={},label={Text(c.status)})
                        }
                    }
                }
                item{
                    ElevatedCard(Modifier.fillMaxWidth()){
                        Column(Modifier.padding(14.dp),verticalArrangement=Arrangement.spacedBy(4.dp)){
                            Text("AUTOMATIC LEARNING CYCLE",fontWeight=FontWeight.Bold)
                            Text("Daily: reconcile outcomes → resolve challengers → post-trade autopsy → walk-forward/calibration → update champion status.")
                            Text("Weekly: refresh the remote strategy catalogue and rotate non-champion challengers while retaining proven champions.")
                            Text("Weekly broad-web research refreshes the remote catalogue. Supported rules enter Challenger shadow testing; vague or unsupported ideas remain research-only. Discovery alone never replaces a proven Champion.",style=MaterialTheme.typography.bodySmall)
                        }
                    }
                }
            }
        }

        item{
            OutlinedTextField(
                value=shadowCapitalText,
                onValueChange={v->shadowCapitalText=v.filter(Char::isDigit).take(8);shadowCapitalText.toIntOrNull()?.let{prefs.edit().putInt("shadow_capital",it).apply()}},
                label={Text("Shared shadow wallet budget (₹)")},
                singleLine=true,
                modifier=Modifier.fillMaxWidth()
            )
        }
        item{
            Button(onClick={exporter.launch("Global-Quant-Trader-v2.2-${today}.zip")},modifier=Modifier.fillMaxWidth()){Text("EXPORT COMPLETE LOG")}
            exportStatus?.let{Text(it,style=MaterialTheme.typography.bodySmall)}
        }
    }
}

@Composable
private fun LaneCard(l:Lane){
    ElevatedCard(Modifier.fillMaxWidth()){
        Row(Modifier.padding(12.dp),verticalAlignment=Alignment.CenterVertically){
            Column(Modifier.weight(1f)){Text(l.name,fontWeight=FontWeight.SemiBold);Text(l.detail,style=MaterialTheme.typography.bodySmall)}
            AssistChip(onClick={},label={Text(l.status)})
        }
    }
}

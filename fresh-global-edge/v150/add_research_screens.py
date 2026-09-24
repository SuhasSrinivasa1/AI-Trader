#!/usr/bin/env python3
from pathlib import Path
import sys
root=Path(sys.argv[1]).resolve()
p=root/"app/src/main/java/com/suhas/ucsentinel/ui/ResearchScreens.kt"
p.parent.mkdir(parents=True,exist_ok=True)
p.write_text(r'''package com.suhas.globaledgeai.ui

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.suhas.globaledgeai.domain.model.*
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter

private val researchIst=ZoneId.of("Asia/Kolkata")
private val researchFmt=DateTimeFormatter.ofPattern("dd MMM HH:mm")
private fun researchTs(ms:Long):String=if(ms<=0L)"—" else runCatching{Instant.ofEpochMilli(ms).atZone(researchIst).format(researchFmt)}.getOrDefault("—")

@Composable
fun TradeIntelligenceScreen(state:UiState,vm:MainViewModel,padding:PaddingValues){
    val f=state.evidenceFabric
    LazyColumn(
        Modifier.fillMaxSize().padding(padding).padding(horizontal=14.dp),
        verticalArrangement=Arrangement.spacedBy(10.dp),
        contentPadding=PaddingValues(top=12.dp,bottom=24.dp)
    ){
        item{
            Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.SpaceBetween){
                Column(Modifier.weight(1f)){
                    Text("Trade Intelligence",style=MaterialTheme.typography.headlineSmall,fontWeight=FontWeight.Bold)
                    Text("Point-in-time Evidence Fabric • no historical back-fill",style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
                }
                TextButton(onClick=vm::refreshEvidenceFabric,enabled=!state.busy){Text("Refresh")}
            }
        }
        item{
            ElevatedCard(Modifier.fillMaxWidth()){
                Column(Modifier.padding(14.dp),verticalArrangement=Arrangement.spacedBy(6.dp)){
                    Text("EVIDENCE FABRIC",style=MaterialTheme.typography.labelMedium,fontWeight=FontWeight.Bold,color=MaterialTheme.colorScheme.primary)
                    Text("Evidence becomes usable only from its observed timestamp. Today's fundamentals/revisions are never inserted into older simulations.",
                        style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
                    Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.spacedBy(6.dp)){
                        IntelMetric("Evidence",f.evidenceCount.toString(),Modifier.weight(1f))
                        IntelMetric("Fund.",f.fundamentalCount.toString(),Modifier.weight(1f))
                        IntelMetric("Analyst",f.analystCount.toString(),Modifier.weight(1f))
                        IntelMetric("Events",f.earningsEventCount.toString(),Modifier.weight(1f))
                    }
                }
            }
        }
        item{
            ElevatedCard(Modifier.fillMaxWidth()){
                Column(Modifier.padding(14.dp),verticalArrangement=Arrangement.spacedBy(5.dp)){
                    Text("NSE regular-session calendar",fontWeight=FontWeight.SemiBold)
                    Text(f.calendarVersion,style=MaterialTheme.typography.labelSmall,color=MaterialTheme.colorScheme.primary)
                    Text("Remaining regular sessions • week "+f.weekSessionsRemaining+" • month "+f.monthSessionsRemaining,style=MaterialTheme.typography.bodySmall)
                    Text("09:15–15:30 IST • 2026 exchange holidays drive publication, execution and Challenger horizons.",
                        style=MaterialTheme.typography.labelSmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
        }
        item{
            ElevatedCard(Modifier.fillMaxWidth()){
                Column(Modifier.padding(14.dp),verticalArrangement=Arrangement.spacedBy(4.dp)){
                    Text("Macro / event risk",fontWeight=FontWeight.SemiBold)
                    if(f.macroRisk.isEmpty())Text("No seeded HIGH macro event is active today.",style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
                    else f.macroRisk.forEach{e->
                        Text(e.severity+" • "+e.title+" • "+e.startDateIso+" → "+e.endDateIso,style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.error)
                    }
                    Text("Company earnings/event evidence is captured prospectively from exchange announcements when discovered.",
                        style=MaterialTheme.typography.labelSmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
        }
        item{
            ElevatedCard(Modifier.fillMaxWidth()){
                Column(Modifier.padding(14.dp),verticalArrangement=Arrangement.spacedBy(4.dp)){
                    Text("Research governance",fontWeight=FontWeight.SemiBold)
                    Text("Challenger OPEN "+f.challengerOpen+" • resolved "+f.challengerResolved+" • broker orders "+f.brokerOrders+" • pending reconciliation "+f.brokerOrdersPending,
                        style=MaterialTheme.typography.bodySmall)
                    Text("100 strategies, 50 candle patterns and 50 intelligence filters remain separate layers. Hard liquidity/risk gates can force WAIT / NO TRADE regardless of score.",
                        style=MaterialTheme.typography.labelSmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
        }
        if(state.pointInTimeEvidence.isNotEmpty()){
            item{Text("Latest point-in-time evidence",style=MaterialTheme.typography.titleMedium,fontWeight=FontWeight.Bold)}
            items(state.pointInTimeEvidence.take(12),key={it.id}){e->
                ElevatedCard(Modifier.fillMaxWidth()){
                    Column(Modifier.padding(12.dp),verticalArrangement=Arrangement.spacedBy(2.dp)){
                        Text(e.kind.name.replace('_',' ')+(if(e.symbol.isBlank())"" else " • "+e.symbol),fontWeight=FontWeight.SemiBold,color=MaterialTheme.colorScheme.primary)
                        Text(e.label,maxLines=2)
                        if(e.detail.isNotBlank())Text(e.detail.take(220),style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant,maxLines=3)
                        Text("Observed "+researchTs(e.observedAt)+" • source "+e.source,style=MaterialTheme.typography.labelSmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
            }
        }
        if(state.decisionSnapshots.isNotEmpty()){
            item{Text("Decision audit trail",style=MaterialTheme.typography.titleMedium,fontWeight=FontWeight.Bold)}
            items(state.decisionSnapshots.take(15),key={it.id}){d->
                ElevatedCard(Modifier.fillMaxWidth()){
                    Column(Modifier.padding(12.dp),verticalArrangement=Arrangement.spacedBy(2.dp)){
                        Text(d.symbol+" • "+d.action.name.replace('_',' ')+" • "+d.engine,fontWeight=FontWeight.SemiBold)
                        Text(d.reason.take(220),style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
                        if(d.sectorEvidence.isNotBlank())Text(d.sectorEvidence,style=MaterialTheme.typography.labelSmall,color=MaterialTheme.colorScheme.primary)
                        if(d.eventRisk.isNotBlank())Text("Event risk • "+d.eventRisk,style=MaterialTheme.typography.labelSmall,color=MaterialTheme.colorScheme.error)
                        if(d.gates.isNotEmpty())Text("Gates • "+d.gates.joinToString(" • "),style=MaterialTheme.typography.labelSmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
                        Text("Decision "+researchTs(d.decisionAt)+" • hash "+d.decisionHash.take(12),style=MaterialTheme.typography.labelSmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
            }
        }
    }
}

@Composable
private fun IntelMetric(label:String,value:String,modifier:Modifier=Modifier){
    Surface(modifier,tonalElevation=1.dp,shape=MaterialTheme.shapes.medium){
        Column(Modifier.padding(horizontal=8.dp,vertical=7.dp)){
            Text(label,style=MaterialTheme.typography.labelSmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
            Text(value,style=MaterialTheme.typography.titleMedium,fontWeight=FontWeight.Bold)
        }
    }
}

@Composable
fun PortfolioScreen(state:UiState,vm:MainViewModel,padding:PaddingValues){
    val p=state.brokerPortfolio
    LazyColumn(
        Modifier.fillMaxSize().padding(padding).padding(horizontal=14.dp),
        verticalArrangement=Arrangement.spacedBy(10.dp),
        contentPadding=PaddingValues(top=12.dp,bottom=24.dp)
    ){
        item{
            Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.SpaceBetween){
                Column(Modifier.weight(1f)){
                    Text("Portfolio",style=MaterialTheme.typography.headlineSmall,fontWeight=FontWeight.Bold)
                    Text("Groww reconciliation • actual fills, quantities and slippage",style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
                }
                TextButton(onClick=vm::refreshBrokerReconciliation,enabled=!state.busy&&state.authenticated){Text("Reconcile")}
            }
        }
        item{
            ElevatedCard(Modifier.fillMaxWidth()){
                Column(Modifier.padding(14.dp),verticalArrangement=Arrangement.spacedBy(4.dp)){
                    Text("BROKER STATE",style=MaterialTheme.typography.labelMedium,fontWeight=FontWeight.Bold,color=MaterialTheme.colorScheme.primary)
                    Text("Holdings "+p.holdings.size+" • positions "+p.positions.size+" • tracked orders "+state.brokerOrders.size)
                    Text("Last portfolio sync "+researchTs(p.capturedAt)+(if(p.message.isBlank())"" else " • "+p.message),
                        style=MaterialTheme.typography.labelSmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
        }
        if(p.holdings.isNotEmpty()){
            item{Text("Holdings",style=MaterialTheme.typography.titleMedium,fontWeight=FontWeight.Bold)}
            items(p.holdings,key={"H-"+it.symbol}){h->
                ElevatedCard(Modifier.fillMaxWidth()){
                    Row(Modifier.padding(12.dp).fillMaxWidth(),horizontalArrangement=Arrangement.SpaceBetween){
                        Column{
                            Text(h.symbol,fontWeight=FontWeight.SemiBold)
                            Text("Qty "+h.quantity+" • avg ₹"+"%.2f".format(h.averagePrice),style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                        Column{
                            Text(if(h.lastPrice>0)"₹"+"%.2f".format(h.lastPrice) else "—")
                            if(h.currentValue>0)Text("₹"+"%.0f".format(h.currentValue),style=MaterialTheme.typography.labelSmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                    }
                }
            }
        }
        if(p.positions.isNotEmpty()){
            item{Text("Positions",style=MaterialTheme.typography.titleMedium,fontWeight=FontWeight.Bold)}
            items(p.positions,key={"P-"+it.symbol+"-"+it.product}){x->
                ElevatedCard(Modifier.fillMaxWidth()){
                    Row(Modifier.padding(12.dp).fillMaxWidth(),horizontalArrangement=Arrangement.SpaceBetween){
                        Column{
                            Text(x.symbol+" • "+x.product,fontWeight=FontWeight.SemiBold)
                            Text("Net "+x.netQuantity+" • avg ₹"+"%.2f".format(x.averagePrice),style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                        Text("P&L ₹"+"%+.2f".format(x.pnl),color=if(x.pnl<0)MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.primary)
                    }
                }
            }
        }
        item{Text("Order & fill ledger",style=MaterialTheme.typography.titleMedium,fontWeight=FontWeight.Bold)}
        if(state.brokerOrders.isEmpty())item{Text("No manual Groww orders have been recorded by this app yet.",color=MaterialTheme.colorScheme.onSurfaceVariant)}
        else items(state.brokerOrders.take(50),key={it.localId}){o->
            ElevatedCard(Modifier.fillMaxWidth()){
                Column(Modifier.padding(12.dp),verticalArrangement=Arrangement.spacedBy(3.dp)){
                    Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.SpaceBetween){
                        Text(o.symbol+" • "+o.side+"/"+o.product,fontWeight=FontWeight.SemiBold)
                        Text(o.syncState.name,color=if(o.syncState==BrokerSyncState.ERROR||o.syncState==BrokerSyncState.REJECTED)MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.primary)
                    }
                    Text(o.orderStatus+" • filled "+o.filledQty+"/"+o.requestedQty+" • remaining "+o.remainingQty,style=MaterialTheme.typography.bodySmall)
                    Text("Expected ₹"+"%.2f".format(o.expectedEntryPrice)+" • avg fill "+(if(o.averageFillPrice>0)"₹"+"%.2f".format(o.averageFillPrice) else "—")+" • slippage "+"%+.3f".format(o.slippagePct)+"%",
                        style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
                    Text("Groww "+o.growwOrderId+" • fills "+o.fills.size+" • synced "+researchTs(o.lastReconciledAt),style=MaterialTheme.typography.labelSmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
                    if(o.lastError.isNotBlank())Text(o.lastError,style=MaterialTheme.typography.labelSmall,color=MaterialTheme.colorScheme.error)
                }
            }
        }
    }
}
''',encoding="utf-8")
print("ResearchScreens.kt created")

#!/usr/bin/env python3
from pathlib import Path
import sys
root=Path(sys.argv[1]).resolve()
p=root/"app/src/main/java/com/suhas/ucsentinel/ui/CompactMarketScreens.kt"
s=p.read_text(encoding="utf-8")

# Pass frozen model entry into the permanent broker ledger.
old='''                        vm.placeManualOrder(symbol,side,product,qty){ok,message->'''
new='''                        vm.placeManualOrder(symbol,side,product,qty,plan.entry){ok,message->'''
if s.count(old)!=1: raise SystemExit("manual order UI anchor mismatch")
s=s.replace(old,new,1)

# Evidence Fabric panel in Trade Intelligence / Strategies.
anchor='''        state.strategyTournamentSummary?.let{research->
            item{
                ElevatedCard(Modifier.fillMaxWidth()){
                    Column(Modifier.padding(horizontal=12.dp,vertical=10.dp),verticalArrangement=Arrangement.spacedBy(4.dp)){
'''
i=s.index(anchor)
# insert Evidence Fabric card before Champion Research card
fabric='''        state.evidenceFabric?.let{fabric->
            item{
                ElevatedCard(Modifier.fillMaxWidth()){
                    Column(Modifier.padding(horizontal=12.dp,vertical=10.dp),verticalArrangement=Arrangement.spacedBy(4.dp)){
                        Text("TRADE INTELLIGENCE • EVIDENCE FABRIC",style=MaterialTheme.typography.labelMedium,fontWeight=FontWeight.Bold,color=MaterialTheme.colorScheme.primary)
                        Text("Calendar ${fabric.calendarVersion} • week ${fabric.remainingWeekSessions} sessions • month ${fabric.remainingMonthSessions}",
                            style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
                        Text("PIT evidence ${fabric.pointInTimeEvidenceCount} • macro next 7d ${fabric.macroEventsNext7Days} • decisions ${fabric.decisionSnapshots}",
                            style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
                        Text("Challenger pending ${fabric.challengerPending} • resolved ${fabric.challengerResolved} • broker orders ${fabric.brokerOrders}",
                            style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
                        Text("Sector map • "+fabric.sectorMapVersion.ifBlank{"awaiting first NIFTY 500 snapshot"}+" • missing evidence stays neutral; hard risk/liquidity gates can force WAIT",
                            style=MaterialTheme.typography.labelSmall,color=MaterialTheme.colorScheme.tertiary)
                    }
                }
            }
        }
'''
s=s[:i]+fabric+s[i:]

# Add broker portfolio screen before Global screen.
marker='''@Composable
fun GlobalCompactScreen'''
idx=s.index(marker)
portfolio='''@Composable
fun PortfolioCompactScreen(state:UiState,vm:MainViewModel,padding:PaddingValues){
    val orders=state.brokerOrders.sortedByDescending{it.submittedAt}
    val filled=orders.sumOf{it.filledQuantity}
    LazyColumn(Modifier.fillMaxSize().padding(padding).padding(horizontal=14.dp),verticalArrangement=Arrangement.spacedBy(10.dp),contentPadding=PaddingValues(top=12.dp,bottom=24.dp)){
        item{CompactHeader("Portfolio",state,orders.maxOfOrNull{it.lastReconciledAt}?:0L,vm::reconcileBrokerNow,"Groww order/fill reconciliation • permanent execution ledger")}
        item{
            Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.spacedBy(6.dp)){
                PlanMetric("ORDERS",orders.size.toString(),Modifier.weight(1f))
                PlanMetric("FILLED QTY",filled.toString(),Modifier.weight(1f))
                PlanMetric("PENDING",orders.count{it.remainingQuantity>0&&it.status !in setOf("REJECTED","CANCELLED")}.toString(),Modifier.weight(1f))
            }
        }
        item{
            ElevatedCard(Modifier.fillMaxWidth()){
                Column(Modifier.padding(12.dp),verticalArrangement=Arrangement.spacedBy(3.dp)){
                    Text("BROKER RECONCILIATION",style=MaterialTheme.typography.labelMedium,fontWeight=FontWeight.Bold,color=MaterialTheme.colorScheme.primary)
                    Text("Requested order data is never treated as a fill. Filled quantity, remaining quantity, average fill and individual Groww trades are reconciled into this ledger.",
                        style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
                    if(state.staticIpMatch==false)Text("Static-IP route mismatch • live submission remains blocked",style=MaterialTheme.typography.labelSmall,color=MaterialTheme.colorScheme.error)
                }
            }
        }
        if(orders.isEmpty())item{EmptyState("No broker orders yet","After a manual PLACE ORDER, the Groww order and its actual fills will appear here.")}
        else items(orders,key={it.growwOrderId+"|"+it.referenceId}){o->
            ElevatedCard(Modifier.fillMaxWidth()){
                Column(Modifier.padding(12.dp),verticalArrangement=Arrangement.spacedBy(5.dp)){
                    Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.SpaceBetween){
                        Text(o.symbol,style=MaterialTheme.typography.titleMedium,fontWeight=FontWeight.Bold)
                        Text(o.status,style=MaterialTheme.typography.labelMedium,color=if(o.status.contains("REJECT",true)||o.status.contains("UNCERTAIN",true))MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.primary)
                    }
                    Text("${o.side} • ${o.product} • requested ${o.requestedQuantity} • filled ${o.filledQuantity} • remaining ${o.remainingQuantity}",
                        style=MaterialTheme.typography.bodySmall)
                    Text("Signal ₹${"%.2f".format(o.signalEntryPrice)} • broker avg "+if(o.averageFillPrice>0)"₹${"%.2f".format(o.averageFillPrice)}" else "pending",
                        style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
                    Text("Groww ID ${o.growwOrderId} • ref ${o.referenceId}",style=MaterialTheme.typography.labelSmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
                    if(o.lastReconciledAt>0)Text("Reconciled ${formatIstTimestamp(o.lastReconciledAt)}",style=MaterialTheme.typography.labelSmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
                    if(o.reconciliationError.isNotBlank())Text(o.reconciliationError,style=MaterialTheme.typography.labelSmall,color=MaterialTheme.colorScheme.error)
                    o.fills.take(8).forEach{f->
                        Text("Fill • qty ${f.quantity} @ ₹${"%.2f".format(f.price)} • ${f.tradeStatus} • ${f.tradeDateTime}",
                            style=MaterialTheme.typography.labelSmall,color=MaterialTheme.colorScheme.tertiary)
                    }
                }
            }
        }
    }
}

'''
s=s[:idx]+portfolio+s[idx:]

p.write_text(s,encoding="utf-8")
print("Global Edge v1.5 Evidence Fabric and Portfolio UI applied")

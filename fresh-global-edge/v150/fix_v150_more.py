#!/usr/bin/env python3
from pathlib import Path
import sys
root=Path(sys.argv[1]).resolve()
p=root/"app/src/main/java/com/suhas/ucsentinel/ui/MoreScreen.kt"
s=p.read_text(encoding="utf-8")
def one(old,new,label):
    global s
    n=s.count(old)
    if n!=1: raise SystemExit(f"{label}: expected 1 found {n}")
    s=s.replace(old,new,1)

one('''        val pages=listOf("auth","settings")
        TabRow(selectedTabIndex=pages.indexOf(page).coerceAtLeast(0)){
            Tab(selected=page=="auth",onClick={onPage("auth")},text={Text("Groww Auth")})
            Tab(selected=page=="settings",onClick={onPage("settings")},text={Text("Settings")})
        }
        when(page){
            "auth"->Auth(state,vm)
            else->Settings(state,vm)
        }
''',
'''        val pages=listOf("auth","lab","portfolio","settings")
        ScrollableTabRow(selectedTabIndex=pages.indexOf(page).coerceAtLeast(0)){
            Tab(selected=page=="auth",onClick={onPage("auth")},text={Text("Groww Auth")})
            Tab(selected=page=="lab",onClick={onPage("lab")},text={Text("Strategy Lab")})
            Tab(selected=page=="portfolio",onClick={onPage("portfolio")},text={Text("Portfolio")})
            Tab(selected=page=="settings",onClick={onPage("settings")},text={Text("Settings")})
        }
        when(page){
            "auth"->Auth(state,vm)
            "lab"->StrategyLab(state,vm)
            "portfolio"->BrokerPortfolio(state,vm)
            else->Settings(state,vm)
        }
''',"More tabs")

anchor='''        item{AppHeader("Strategy Lab","Shows the exact model generation, active strategy families and learned precision")}
'''
insert=anchor+r'''        item{
            ElevatedCard(Modifier.fillMaxWidth()){
                Column(Modifier.padding(14.dp),verticalArrangement=Arrangement.spacedBy(5.dp)){
                    Text("EVIDENCE FABRIC",style=MaterialTheme.typography.titleMedium,color=MaterialTheme.colorScheme.primary)
                    Text(state.evidenceFabric.calendarLabel,style=MaterialTheme.typography.bodySmall)
                    if(state.evidenceFabric.nextMacroEvent.isNotBlank())Text("Next macro • "+state.evidenceFabric.nextMacroEvent,style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.tertiary)
                    Text("PIT fundamentals ${state.evidenceFabric.fundamentalCount} • analyst ${state.evidenceFabric.analystCount} • earnings ${state.evidenceFabric.earningsEventCount} • sector contexts ${state.evidenceFabric.sectorMappedCount}",
                        style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
                    Text("Challenger open ${state.evidenceFabric.challengerOpen} • resolved ${state.evidenceFabric.challengerResolved} • decisions ${state.evidenceFabric.decisionSnapshots}",
                        style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
                    Text("Historical validation can only read evidence whose observed_at timestamp existed at that decision time. No present-day fundamental backfill.",
                        style=MaterialTheme.typography.labelSmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
                    OutlinedButton(onClick=vm::refreshEvidenceFabric,enabled=!state.busy,modifier=Modifier.fillMaxWidth()){Text("Refresh Evidence Fabric")}
                }
            }
        }
        item{
            Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.spacedBy(8.dp)){
                Button(onClick=vm::runChallengerShadowPass,enabled=!state.busy&&state.authenticated&&state.marketSession.isOpen,modifier=Modifier.weight(1f)){Text("Shadow Run")}
                OutlinedButton(onClick=vm::resolveChallengerShadows,enabled=!state.busy&&state.authenticated,modifier=Modifier.weight(1f)){Text("Resolve")}
            }
        }
        item{
            val open=state.challengerShadows.count{it.status==ChallengerShadowStatus.OPEN}
            val wins=state.challengerShadows.count{it.status==ChallengerShadowStatus.WIN}
            val losses=state.challengerShadows.count{it.status==ChallengerShadowStatus.LOSS}
            ElevatedCard(Modifier.fillMaxWidth()){
                Column(Modifier.padding(12.dp),verticalArrangement=Arrangement.spacedBy(3.dp)){
                    Text("CHALLENGER SHADOW LANE • NON-EXECUTABLE",fontWeight=FontWeight.Bold)
                    Text("Open $open • Wins $wins • Losses $losses • promotion requires ≥12 resolved shadows across ≥4 sessions, ≥55% wins and positive average return.",
                        style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
                    state.challengerShadows.take(5).forEach{r->
                        Text("${r.status} • ${r.symbol} • ${r.direction} • ${r.strategyName.take(38)} • ${"%+.2f".format(r.returnPct)}%",
                            style=MaterialTheme.typography.labelSmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
            }
        }
'''
one(anchor,insert,"Strategy Lab evidence")

anchor='''@Composable
private fun News(state:UiState,vm:MainViewModel){
'''
portfolio=r'''@Composable
private fun BrokerPortfolio(state:UiState,vm:MainViewModel){
    LazyColumn(
        Modifier.fillMaxSize().padding(16.dp),
        verticalArrangement=Arrangement.spacedBy(10.dp),
        contentPadding=PaddingValues(bottom=24.dp)
    ){
        item{AppHeader("Portfolio / Broker Ledger","Groww order status, actual fills, average fill and permanent reconciliation")}
        item{StatusStrip(state)}
        item{
            ElevatedCard(Modifier.fillMaxWidth()){
                Column(Modifier.padding(14.dp),verticalArrangement=Arrangement.spacedBy(4.dp)){
                    Text("BROKER RECONCILIATION",style=MaterialTheme.typography.titleMedium,color=MaterialTheme.colorScheme.primary)
                    Text("Orders ${state.brokerOrders.size} • pending/reconcile ${state.evidenceFabric.unreconciledBrokerOrders}",
                        color=MaterialTheme.colorScheme.onSurfaceVariant)
                    Text("The ledger uses Groww order detail + individual trade fills. It does not assume the requested entry price was the actual fill.",
                        style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
                    Button(onClick=vm::reconcileBrokerOrders,enabled=!state.busy&&state.authenticated,modifier=Modifier.fillMaxWidth()){Text("Reconcile Groww orders + fills")}
                }
            }
        }
        if(state.brokerOrders.isEmpty()){
            item{EmptyState("No broker orders recorded yet","Orders placed from PLACE ORDER will appear here and be reconciled to Groww fills.")}
        }else items(state.brokerOrders.take(100),key={it.growwOrderId}){o->
            ElevatedCard(Modifier.fillMaxWidth()){
                Column(Modifier.padding(12.dp),verticalArrangement=Arrangement.spacedBy(3.dp)){
                    Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.SpaceBetween){
                        Text("${o.transactionType} ${o.symbol}",fontWeight=FontWeight.Bold)
                        Text(o.orderStatus,color=MaterialTheme.colorScheme.primary)
                    }
                    Text("${o.product} • requested ${o.requestedQuantity} • filled ${o.filledQuantity} • remaining ${o.remainingQuantity}",
                        style=MaterialTheme.typography.bodySmall)
                    Text("Average fill ₹${"%.2f".format(o.averageFillPrice)} • fills ${o.fills.size} • Groww ${o.growwOrderId}",
                        style=MaterialTheme.typography.labelSmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
                    o.fills.take(5).forEach{f->
                        Text("Fill • ${f.quantity} @ ₹${"%.2f".format(f.price)} • ${f.tradeStatus} • ${f.tradeDateTime}",
                            style=MaterialTheme.typography.labelSmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                    if(o.remark.isNotBlank())Text(o.remark,style=MaterialTheme.typography.labelSmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
        }
    }
}

'''+anchor
one(anchor,portfolio,"Broker portfolio UI")

p.write_text(s,encoding="utf-8")
print("v1.5 More / Strategy Lab / Portfolio UI applied")

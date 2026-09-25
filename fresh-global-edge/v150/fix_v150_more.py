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
'''        val pages=listOf("auth","lab","settings")
        TabRow(selectedTabIndex=pages.indexOf(page).coerceAtLeast(0)){
            Tab(selected=page=="auth",onClick={onPage("auth")},text={Text("Groww Auth")})
            Tab(selected=page=="lab",onClick={onPage("lab")},text={Text("Strategy Lab")})
            Tab(selected=page=="settings",onClick={onPage("settings")},text={Text("Settings")})
        }
        when(page){
            "auth"->Auth(state,vm)
            "lab"->StrategyLab(state,vm)
            else->Settings(state,vm)
        }
''',"More tabs")

anchor='''        item{AppHeader("Strategy Lab","Shows the exact model generation, active strategy families and learned precision")}
'''
insert=anchor+'''        state.evidenceFabric?.let{fabric->
            item{
                ElevatedCard(Modifier.fillMaxWidth()){
                    Column(Modifier.padding(14.dp),verticalArrangement=Arrangement.spacedBy(4.dp)){
                        Text("EVIDENCE FABRIC",style=MaterialTheme.typography.titleMedium,color=MaterialTheme.colorScheme.primary)
                        Text("Calendar §{fabric.calendarVersion} • week §{fabric.remainingWeekSessions} sessions • month §{fabric.remainingMonthSessions}",
                            style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
                        Text("PIT evidence §{fabric.pointInTimeEvidenceCount} • macro next 7d §{fabric.macroEventsNext7Days} • decisions §{fabric.decisionSnapshots}",
                            style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
                        Text("Challenger pending §{fabric.challengerPending} • resolved §{fabric.challengerResolved} • broker orders §{fabric.brokerOrders}",
                            style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
                        Text("Sector map • "+fabric.sectorMapVersion.ifBlank{"awaiting first NIFTY 500 snapshot"},
                            style=MaterialTheme.typography.labelSmall,color=MaterialTheme.colorScheme.tertiary)
                        Text("Point-in-time evidence is prospective: historical validation can only use observations captured by that historical timestamp.",
                            style=MaterialTheme.typography.labelSmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
            }
        }
        item{
            Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.spacedBy(8.dp)){
                Button(onClick=vm::runChallengerShadowNow,enabled=!state.busy&&state.authenticated&&state.marketSession.isOpen,modifier=Modifier.weight(1f)){Text("Shadow Run")}
                OutlinedButton(onClick=vm::resolveChallengerShadowsNow,enabled=!state.busy&&state.authenticated,modifier=Modifier.weight(1f)){Text("Resolve")}
            }
        }
        item{
            ElevatedCard(Modifier.fillMaxWidth()){
                Column(Modifier.padding(12.dp),verticalArrangement=Arrangement.spacedBy(3.dp)){
                    Text("CHALLENGER SHADOW LANE • NON-EXECUTABLE",fontWeight=FontWeight.Bold)
                    val pending=state.challengerShadows.count{it.outcome==ChallengerShadowOutcome.PENDING}
                    val wins=state.challengerShadows.count{it.outcome==ChallengerShadowOutcome.WIN}
                    val losses=state.challengerShadows.count{it.outcome==ChallengerShadowOutcome.LOSS}
                    Text("Pending §pending • Wins §wins • Losses §losses • prospective shadow evidence is required before promotion.",
                        style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
                    state.challengerShadows.take(5).forEach{r->
                        Text("§{r.outcome} • §{r.symbol} • §{r.direction} • §{r.strategyName.take(38)} • §{"%+.2f".format(r.returnPct)}%",
                            style=MaterialTheme.typography.labelSmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
            }
        }
'''.replace("§","§DOLLAR§")
one(anchor,insert,"Strategy Lab Evidence Fabric")
s=s.replace("§DOLLAR§","$")
p.write_text(s,encoding="utf-8")
print("v1.5 More / Strategy Lab Evidence Fabric UI applied")

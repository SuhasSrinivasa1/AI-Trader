#!/usr/bin/env python3
from pathlib import Path
import sys
root=Path(sys.argv[1]).resolve()
p=root/"app/src/main/java/com/suhas/ucsentinel/ui/MoreScreen.kt"
s=p.read_text(encoding="utf-8")

def one(old,new,label):
    global s
    n=s.count(old)
    if n!=1: raise SystemExit(f"${label}: expected 1 found ${n}")
    s=s.replace(old,new,1)

one(
'''        val pages=listOf("auth","settings")
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
''',"Expose Strategy Lab")

anchor='''        item{AppHeader("Strategy Lab","Shows the exact model generation, active strategy families and learned precision")}
'''
insert=anchor+'''        item{
            val shadows=state.challengerShadows
            val open=shadows.count{it.status==ChallengerShadowStatus.OPEN}
            val wins=shadows.count{it.status==ChallengerShadowStatus.WIN}
            val losses=shadows.count{it.status==ChallengerShadowStatus.LOSS}
            val unresolved=shadows.count{it.status==ChallengerShadowStatus.UNRESOLVED_DATA}
            ElevatedCard(Modifier.fillMaxWidth()){
                Column(Modifier.padding(14.dp),verticalArrangement=Arrangement.spacedBy(8.dp)){
                    Text("Challenger shadow lane",style=MaterialTheme.typography.titleMedium,fontWeight=FontWeight.Bold)
                    Text("Completely non-executable. Challenger signals are timestamped prospectively and can be promoted only from scheduled-horizon shadow results.",
                        color=MaterialTheme.colorScheme.onSurfaceVariant,style=MaterialTheme.typography.bodySmall)
                    Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.spacedBy(6.dp)){
                        MetricCard("OPEN",open.toString(),Modifier.weight(1f))
                        MetricCard("WIN",wins.toString(),Modifier.weight(1f))
                        MetricCard("LOSS",losses.toString(),Modifier.weight(1f))
                        MetricCard("DATA?",unresolved.toString(),Modifier.weight(1f))
                    }
                    Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.spacedBy(8.dp)){
                        OutlinedButton(onClick=vm::runChallengerShadowNow,enabled=!state.busy&&state.authenticated,modifier=Modifier.weight(1f)){Text("Shadow Run")}
                        Button(onClick=vm::resolveChallengerShadows,enabled=!state.busy&&state.authenticated,modifier=Modifier.weight(1f)){Text("Resolve")}
                    }
                    Text("Resolution uses the scheduled horizon bar, not the price observed when the app is reopened.",
                        style=MaterialTheme.typography.labelSmall,color=MaterialTheme.colorScheme.primary)
                }
            }
        }
        if(state.challengerShadows.isNotEmpty()){
            item{Text("Recent Challenger observations",style=MaterialTheme.typography.titleMedium)}
            items(state.challengerShadows.take(12),key={it.id}){r->
                ElevatedCard(Modifier.fillMaxWidth()){
                    Column(Modifier.padding(12.dp),verticalArrangement=Arrangement.spacedBy(2.dp)){
                        Text("${r.symbol} • ${r.direction} • ${r.strategyName}",fontWeight=FontWeight.SemiBold,maxLines=2)
                        Text("${r.status} • score ${"%.1f".format(r.score)} • horizon ${r.horizonMinutes}m • return ${"%+.2f".format(r.returnPct)}%",
                            style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
                        Text(r.researchSignature.replace("_"," ").take(150),style=MaterialTheme.typography.labelSmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
            }
        }
'''
one(anchor,insert,"Strategy Lab Challenger panel")

p.write_text(s,encoding="utf-8")
print("Strategy Lab shadow controls exposed")

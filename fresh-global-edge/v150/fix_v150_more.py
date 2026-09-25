#!/usr/bin/env python3
from pathlib import Path
import sys
root=Path(sys.argv[1]).resolve()
p=root/"app/src/main/java/com/suhas/ucsentinel/ui/MoreScreen.kt"
s=p.read_text(encoding="utf-8")

old='''        val pages=listOf("auth","settings")
        TabRow(selectedTabIndex=pages.indexOf(page).coerceAtLeast(0)){
            Tab(selected=page=="auth",onClick={onPage("auth")},text={Text("Groww Auth")})
            Tab(selected=page=="settings",onClick={onPage("settings")},text={Text("Settings")})
        }
        when(page){
            "auth"->Auth(state,vm)
            else->Settings(state,vm)
        }
'''
new='''        val pages=listOf("auth","lab","settings")
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
'''
if s.count(old)!=1: raise SystemExit("More tabs anchor mismatch")
s=s.replace(old,new,1)

anchor='''        item{
            OutlinedButton(
                onClick=vm::runLearningNow,
                enabled=!state.busy&&state.authenticated,
                modifier=Modifier.fillMaxWidth()
            ){Text("Run 24-hour learning cycle now")}
        }
'''
addition=anchor+'''        item{
            ElevatedCard(Modifier.fillMaxWidth()){
                Column(Modifier.padding(14.dp),verticalArrangement=Arrangement.spacedBy(8.dp)){
                    val pending=state.challengerShadows.count{it.outcome==ChallengerShadowOutcome.PENDING}
                    val resolved=state.challengerShadows.count{it.outcome!=ChallengerShadowOutcome.PENDING}
                    Text("Challenger shadow lane",style=MaterialTheme.typography.titleMedium)
                    Text("Pending $pending • resolved $resolved • completely non-executable. Promotion uses prospective shadow results and scheduled-horizon prices.",
                        style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
                    Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.spacedBy(8.dp)){
                        OutlinedButton(onClick=vm::runChallengerShadowNow,enabled=!state.busy&&state.authenticated,modifier=Modifier.weight(1f)){Text("Shadow Run")}
                        Button(onClick=vm::resolveChallengerShadowsNow,enabled=!state.busy&&state.authenticated,modifier=Modifier.weight(1f)){Text("Resolve")}
                    }
                    state.challengerShadows.take(8).forEach{x->
                        Text("${x.outcome} • ${x.symbol} • ${x.strategyName.take(35)} • horizon ${formatIstTimestamp(x.resolveAt)}"+
                            if(x.resolvedAt>0)" • ${"%+.2f".format(x.returnPct)}%" else "",
                            style=MaterialTheme.typography.labelSmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
            }
        }
'''
if s.count(anchor)!=1: raise SystemExit("StrategyLab button anchor mismatch")
s=s.replace(anchor,addition,1)

# Update diagnostics wording to explicitly include v1.5 ledgers.
s=s.replace(
'''Exports the complete retained runtime timeline plus scheduler timestamps, scan summaries, NEXT/LIVE/3PM/DONE calls, strategy/global ledgers, rejected-candidate shadows, calibration, walk-forward state and autopsies. Groww secrets/tokens are excluded.''',
'''Exports the complete retained runtime timeline plus scheduler timestamps, scans, Challenger shadows, point-in-time evidence, decision hashes, broker order/fill reconciliation, rejected candidates, calibration, walk-forward state and autopsies. Groww secrets/tokens are excluded.''')

p.write_text(s,encoding="utf-8")
print("v1.5 Strategy Lab Shadow Run/Resolve UI applied")

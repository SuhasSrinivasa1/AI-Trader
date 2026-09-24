#!/usr/bin/env python3
from pathlib import Path
import sys
root=Path(sys.argv[1]).resolve()
p=root/"app/src/main/java/com/suhas/ucsentinel/ui/CompactMarketScreens.kt"
s=p.read_text(encoding="utf-8")
anchor='''        item{
            val attempt=if(state.lastStrategyAttemptAt>0)formatIstTimestamp(state.lastStrategyAttemptAt) else "not yet"
'''
card='''        state.strategyTournamentSummary?.let{research->
            item{
                ElevatedCard(Modifier.fillMaxWidth()){
                    Column(Modifier.padding(horizontal=12.dp,vertical=10.dp),verticalArrangement=Arrangement.spacedBy(4.dp)){
                        Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.SpaceBetween,verticalAlignment=Alignment.CenterVertically){
                            Text("CHAMPION RESEARCH • PDF SYNERGY",style=MaterialTheme.typography.labelMedium,fontWeight=FontWeight.Bold,color=MaterialTheme.colorScheme.primary)
                            val champ=research.performances.count{it.status==StrategyStatus.CHAMPION}
                            val susp=research.performances.count{it.status==StrategyStatus.SUSPENDED}
                            Text("C $champ • S $susp",style=MaterialTheme.typography.labelSmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                        Text("100 handbook strategies • 50 candle patterns • 50 intelligence filters • 500-variant multiple-testing penalty",
                            style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
                        if(research.championInsights.isEmpty()){
                            Text("Collecting chronological closed calls for holdout + walk-forward Champion evidence.",
                                style=MaterialTheme.typography.labelSmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
                        }else research.championInsights.take(6).forEach{line->
                            Text(line,style=MaterialTheme.typography.labelSmall,color=if(line.startsWith("DECAY"))MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                        Text("Rejected-candidate journal • ${research.rejectedJournalCount} stored • unavailable handbook data is neutral, never guessed",
                            style=MaterialTheme.typography.labelSmall,fontWeight=FontWeight.SemiBold,color=MaterialTheme.colorScheme.tertiary)
                    }
                }
            }
        }
'''+anchor
if s.count(anchor)!=1: raise SystemExit("Strategies research-card anchor mismatch")
s=s.replace(anchor,card,1)
p.write_text(s,encoding="utf-8")
print("Global Edge v1.4.0 Champion Research UI applied")

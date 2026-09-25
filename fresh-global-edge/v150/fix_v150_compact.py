#!/usr/bin/env python3
from pathlib import Path
import sys
root=Path(sys.argv[1]).resolve()
p=root/"app/src/main/java/com/suhas/ucsentinel/ui/CompactMarketScreens.kt"
s=p.read_text(encoding="utf-8")
anchor='''        item{
            val attempt=if(state.lastStrategyAttemptAt>0)formatIstTimestamp(state.lastStrategyAttemptAt) else "not yet"
'''
insert=r'''        item{
            ElevatedCard(Modifier.fillMaxWidth()){
                Column(Modifier.padding(horizontal=12.dp,vertical=10.dp),verticalArrangement=Arrangement.spacedBy(3.dp)){
                    Text("TRADE INTELLIGENCE • EVIDENCE FABRIC",style=MaterialTheme.typography.labelMedium,fontWeight=FontWeight.Bold,color=MaterialTheme.colorScheme.primary)
                    Text(state.evidenceFabric.calendarLabel,style=MaterialTheme.typography.labelSmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
                    if(state.evidenceFabric.nextMacroEvent.isNotBlank())Text("Macro • "+state.evidenceFabric.nextMacroEvent,style=MaterialTheme.typography.labelSmall,color=MaterialTheme.colorScheme.tertiary)
                    Text("PIT F ${state.evidenceFabric.fundamentalCount} • Analyst ${state.evidenceFabric.analystCount} • Earnings ${state.evidenceFabric.earningsEventCount} • Sector ${state.evidenceFabric.sectorMappedCount}",
                        style=MaterialTheme.typography.labelSmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
                    Text("Challenger ${state.evidenceFabric.challengerOpen} open / ${state.evidenceFabric.challengerResolved} resolved • Broker ${state.evidenceFabric.brokerOrders} • Decisions ${state.evidenceFabric.decisionSnapshots}",
                        style=MaterialTheme.typography.labelSmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
                    Text("Hard risk/liquidity/event gates can force WAIT / NO TRADE regardless of MODEL score.",style=MaterialTheme.typography.labelSmall,fontWeight=FontWeight.SemiBold)
                }
            }
        }
'''.replace("$","$")+anchor
if s.count(anchor)!=1: raise SystemExit("Trade Intelligence anchor mismatch")
s=s.replace(anchor,insert,1)
p.write_text(s,encoding="utf-8")
print("v1.5 Trade Intelligence Evidence Fabric panel applied")

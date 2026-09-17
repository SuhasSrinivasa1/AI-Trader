from pathlib import Path
import sys
root=Path(sys.argv[1])

def read(rel): return (root/rel).read_text()
def write(rel,s): (root/rel).write_text(s)
def must_replace(s,old,new,label):
    if old not in s: raise SystemExit(f'missing needle: {label}')
    return s.replace(old,new,1)

# The top status strip text is produced by the repository, not the screen composable.
p='app/src/main/java/com/suhas/ucsentinel/data/repository/UCSentinelRepository.kt'
s=read(p)
s=must_replace(
    s,
    '"LONG ${longs.size} ($actionableLong actionable) • SHORT ${shorts.size} ($actionableShort actionable) • 15:00 decision deadline","15:00 IST",dropped)',
    '"LONG ${longs.size} ($actionableLong actionable) • SHORT ${shorts.size} ($actionableShort actionable) • 09:15 entry window","09:15 IST",dropped)',
    'Global Lead status deadline'
)
write(p,s)

# Make the Indian entry reference explicit on every Global Lead candidate card.
p='app/src/main/java/com/suhas/ucsentinel/ui/GlobalLeadScreen.kt'
s=read(p)
needle='''            Spacer(Modifier.height(8.dp))\n            Text("Freshness ${"%.2f".format(c.freshnessPct)}% directional • benchmark excess ${signed(c.foreignExcessPct)}% • pressure confirmation ${"%.0f".format(c.pressureConfirmationScore)}",style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant)\n'''
replacement='''            Spacer(Modifier.height(8.dp))\n            if(c.indianPrice>0){\n                Text(\n                    if(short) "SHORT entry reference: ₹${"%.2f".format(c.indianPrice)} after downside confirmation"\n                    else "LONG entry reference: ₹${"%.2f".format(c.indianPrice)} after upside confirmation",\n                    fontWeight=FontWeight.Bold,\n                    color=actionColor\n                )\n                Text("Entry reference is the current validated Indian price when this Global Lead setup was generated; revalidate live price before acting.",style=MaterialTheme.typography.labelSmall,color=MaterialTheme.colorScheme.onSurfaceVariant)\n                Spacer(Modifier.height(6.dp))\n            }\n            Text("Freshness ${"%.2f".format(c.freshnessPct)}% directional • benchmark excess ${signed(c.foreignExcessPct)}% • pressure confirmation ${"%.0f".format(c.pressureConfirmationScore)}",style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant)\n'''
s=must_replace(s,needle,replacement,'Global Lead entry price card')
# Keep 15:00 only as an explicit risk/exit reassessment, not as an entry deadline.
s=s.replace('continuation after entry; reassess before 15:00 IST.','continuation after entry; 3 PM is reassessment / exit management, not the entry deadline.')
write(p,s)
print('Global Edge v1.0.3 opening-entry UI patch applied')

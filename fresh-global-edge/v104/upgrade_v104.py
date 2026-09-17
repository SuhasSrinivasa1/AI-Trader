from pathlib import Path
import re, sys
root=Path(sys.argv[1])

def read(rel): return (root/rel).read_text()
def write(rel,s):
    p=root/rel; p.parent.mkdir(parents=True,exist_ok=True); p.write_text(s)
def must_replace(s,old,new,label):
    if old not in s: raise SystemExit(f'missing needle: {label}')
    return s.replace(old,new,1)

# Version bump.
p='app/build.gradle.kts'; s=read(p)
s=must_replace(s,'versionCode = 103','versionCode = 104','versionCode')
s=must_replace(s,'versionName = "1.0.3"','versionName = "1.0.4"','versionName')
write(p,s)

# Global Lead must be usable from 09:15, not artificially wait until 09:30.
# A strong mapped signal may become ENTER_AFTER_OPEN as soon as the Indian stock
# confirms direction from its opening print; otherwise it remains WAIT / CONFIRM.
p='app/src/main/java/com/suhas/ucsentinel/domain/engine/GlobalLeadEngine.kt'; s=read(p)
old='''            t<LocalTime.of(9,30) -> if(score>=72&&signalFreshForToday)GlobalLeadAction.WAIT_FOR_CONFIRMATION else GlobalLeadAction.OBSERVE\n'''
new='''            t<LocalTime.of(9,30) -> if(score>=76&&signalFreshForToday&&directionalFromOpen>=0.20&&foreignDirectionOk)GlobalLeadAction.ENTER_AFTER_OPEN else if(score>=72&&signalFreshForToday)GlobalLeadAction.WAIT_FOR_CONFIRMATION else GlobalLeadAction.OBSERVE\n'''
s=must_replace(s,old,new,'09:15 confirmation action')
write(p,s)

# Add a concrete execution panel to each Global Lead card. The trigger requires a
# small continuation beyond the latest validated Indian price. Stop distance is tied
# to the observed opening displacement (bounded for safety), while targets use the
# scanner's continuation objective.
p='app/src/main/java/com/suhas/ucsentinel/ui/GlobalLeadScreen.kt'; s=read(p)
old='''            if(c.indianPrice>0){\n                Text(\n                    if(short) "SHORT entry reference: ₹${"%.2f".format(c.indianPrice)} after downside confirmation"\n                    else "LONG entry reference: ₹${"%.2f".format(c.indianPrice)} after upside confirmation",\n                    fontWeight=FontWeight.Bold,\n                    color=actionColor\n                )\n                Text("Entry reference is the current validated Indian price when this Global Lead setup was generated; revalidate live price before acting.",style=MaterialTheme.typography.labelSmall,color=MaterialTheme.colorScheme.onSurfaceVariant)\n                Spacer(Modifier.height(6.dp))\n            }\n'''
new='''            if(c.indianPrice>0){\n                val plan=globalExecutionPlan(c)\n                Text("Execution plan",fontWeight=FontWeight.Bold,style=MaterialTheme.typography.titleSmall)\n                Text(\n                    if(short) "SHORT only if price trades at / below ₹${"%.2f".format(plan.trigger)}"\n                    else "LONG only if price trades at / above ₹${"%.2f".format(plan.trigger)}",\n                    fontWeight=FontWeight.Bold,\n                    color=actionColor\n                )\n                Spacer(Modifier.height(6.dp))\n                Row(horizontalArrangement=Arrangement.spacedBy(8.dp)){\n                    MetricCard("Trigger","₹${"%.2f".format(plan.trigger)}",Modifier.weight(1f))\n                    MetricCard("Model stop","₹${"%.2f".format(plan.stop)}",Modifier.weight(1f))\n                }\n                Spacer(Modifier.height(6.dp))\n                Row(horizontalArrangement=Arrangement.spacedBy(8.dp)){\n                    MetricCard("Target 1","₹${"%.2f".format(plan.target1)}",Modifier.weight(1f))\n                    MetricCard("Target 2","₹${"%.2f".format(plan.target2)}",Modifier.weight(1f))\n                }\n                Spacer(Modifier.height(6.dp))\n                Text(\n                    if(short) "Invalidation: cover / cancel the setup if price trades at or above ₹${"%.2f".format(plan.stop)}; a sustained reclaim of the India open also cancels the downside thesis."\n                    else "Invalidation: exit / cancel the setup if price trades at or below ₹${"%.2f".format(plan.stop)}; a sustained loss of the India open also cancels the upside thesis.",\n                    style=MaterialTheme.typography.labelSmall,\n                    color=MaterialTheme.colorScheme.onSurfaceVariant\n                )\n                Text("Levels are generated from the latest validated quote and session structure. Revalidate live price, spread and liquidity before acting.",style=MaterialTheme.typography.labelSmall,color=MaterialTheme.colorScheme.onSurfaceVariant)\n                Spacer(Modifier.height(6.dp))\n            }\n'''
s=must_replace(s,old,new,'Global Lead execution panel')
helper='''\nprivate data class GlobalExecutionPlan(val trigger:Double,val stop:Double,val target1:Double,val target2:Double)\n\nprivate fun globalExecutionPlan(c:GlobalLeadCandidate):GlobalExecutionPlan{\n    val short=c.direction==GlobalLeadDirection.SHORT\n    val base=c.indianPrice.coerceAtLeast(0.01)\n    val trigger=if(short)base*0.999 else base*1.001\n    val openDistancePct=if(c.indianOpen>0.0)kotlin.math.abs(c.indianOpen-trigger)/trigger*100.0 else 0.0\n    val riskPct=(openDistancePct*0.25).takeIf{it.isFinite()&&it>0.0}?.coerceIn(0.35,1.00)?:0.50\n    val targetPct=c.expectedTargetPct.takeIf{it.isFinite()&&it>0.0}?.coerceIn(0.35,3.00)?:0.50\n    val target2Pct=(targetPct*1.75).coerceIn(targetPct+0.20,4.00)\n    val stop=if(short)trigger*(1.0+riskPct/100.0) else trigger*(1.0-riskPct/100.0)\n    val target1=if(short)trigger*(1.0-targetPct/100.0) else trigger*(1.0+targetPct/100.0)\n    val target2=if(short)trigger*(1.0-target2Pct/100.0) else trigger*(1.0+target2Pct/100.0)\n    return GlobalExecutionPlan(trigger,stop,target1,target2)\n}\n\n'''
marker='private fun signed(v:Double)='
if marker not in s: raise SystemExit('missing GlobalLeadScreen helper insertion point')
s=s.replace(marker,helper+marker,1)
write(p,s)

# Notifications now carry actionable trigger, stop and target prices for Global Lead,
# and actual stop/target prices for strategy setups.
p='app/src/main/java/com/suhas/ucsentinel/notifications/AppNotifier.kt'; s=read(p)
pat=re.compile(r'    fun notifyGlobalLead\(context:Context,candidates:List<GlobalLeadCandidate>\)\{.*?\n    \}\n\n    fun notifyStrategySetups',re.S)
m=pat.search(s)
if not m: raise SystemExit('missing notifyGlobalLead function')
new_global=r'''    private data class GlobalAlertPlan(val trigger:Double,val stop:Double,val target1:Double,val target2:Double)\n\n    private fun globalAlertPlan(c:GlobalLeadCandidate):GlobalAlertPlan{\n        val short=c.direction.name.contains("SHORT")\n        val base=c.indianPrice.coerceAtLeast(0.01)\n        val trigger=if(short)base*0.999 else base*1.001\n        val openDistancePct=if(c.indianOpen>0.0)kotlin.math.abs(c.indianOpen-trigger)/trigger*100.0 else 0.0\n        val riskPct=(openDistancePct*0.25).takeIf{it.isFinite()&&it>0.0}?.coerceIn(0.35,1.00)?:0.50\n        val targetPct=c.expectedTargetPct.takeIf{it.isFinite()&&it>0.0}?.coerceIn(0.35,3.00)?:0.50\n        val target2Pct=(targetPct*1.75).coerceIn(targetPct+0.20,4.00)\n        val stop=if(short)trigger*(1.0+riskPct/100.0) else trigger*(1.0-riskPct/100.0)\n        val target1=if(short)trigger*(1.0-targetPct/100.0) else trigger*(1.0+targetPct/100.0)\n        val target2=if(short)trigger*(1.0-target2Pct/100.0) else trigger*(1.0+target2Pct/100.0)\n        return GlobalAlertPlan(trigger,stop,target1,target2)\n    }\n\n    fun notifyGlobalLead(context:Context,candidates:List<GlobalLeadCandidate>){\n        if(candidates.isEmpty()||!allowed(context))return\n        ensureChannel(context)\n        val qualified=candidates.filter{c->c.action.name.contains("ENTER")}.take(5)\n        if(qualified.isEmpty())return\n        // Dedupe by setup identity rather than every small price change.\n        val fingerprint=qualified.joinToString("|"){"${it.indianSymbol}:${it.direction.name}:${it.action.name}"}\n        if(!shouldNotify(context,"global",fingerprint))return\n        val lines=qualified.map{c->\n            val side=if(c.direction.name.contains("SHORT"))"SHORT" else "LONG"\n            val p=globalAlertPlan(c)\n            "$side ${c.indianSymbol} ${if(side=="SHORT")"≤" else "≥"} ₹${String.format(Locale.US,"%.2f",p.trigger)} • SL ₹${String.format(Locale.US,"%.2f",p.stop)} • T1 ₹${String.format(Locale.US,"%.2f",p.target1)} • T2 ₹${String.format(Locale.US,"%.2f",p.target2)}"\n        }\n        val n=NotificationCompat.Builder(context,GLOBAL_CHANNEL)\n            .setSmallIcon(android.R.drawable.stat_notify_more)\n            .setContentTitle("Global Lead: confirmed entry trigger")\n            .setContentText(lines.first())\n            .setStyle(NotificationCompat.BigTextStyle().bigText(lines.joinToString("\\n")))\n            .setPriority(NotificationCompat.PRIORITY_HIGH).setCategory(NotificationCompat.CATEGORY_RECOMMENDATION)\n            .setAutoCancel(true).setContentIntent(pending(context,2301)).build()\n        runCatching{NotificationManagerCompat.from(context).notify(2301,n)}\n    }\n\n    fun notifyStrategySetups'''.replace('\\n','\n')
s=s[:m.start()]+new_global+s[m.end():]
old_line='''        val lines=top.map{s->\n            "${s.direction.name} ${s.symbol} • buy/entry ₹${String.format(Locale.US,"%.2f",s.entryPrice)} • ${s.strategyName} • score ${s.score.toInt()}"\n        }\n'''
new_line='''        val lines=top.map{s->\n            val short=s.direction.name.contains("SHORT")\n            val stop=if(short)s.entryPrice*(1.0+s.stopPct.coerceAtLeast(0.1)/100.0) else s.entryPrice*(1.0-s.stopPct.coerceAtLeast(0.1)/100.0)\n            val target=if(short)s.entryPrice*(1.0-s.targetPct.coerceAtLeast(0.1)/100.0) else s.entryPrice*(1.0+s.targetPct.coerceAtLeast(0.1)/100.0)\n            "${s.direction.name} ${s.symbol} • entry ₹${String.format(Locale.US,"%.2f",s.entryPrice)} • SL ₹${String.format(Locale.US,"%.2f",stop)} • target ₹${String.format(Locale.US,"%.2f",target)} • ${s.strategyName}"\n        }\n'''
s=must_replace(s,old_line,new_line,'strategy notification levels')
write(p,s)

# Add dedicated opening workers so the app gets several chances to scan and notify
# around the 09:15 decision window even when the UI is not open. WorkManager remains
# inexact, so multiple nearby anchors are intentionally used and notifications dedupe.
p='app/src/main/java/com/suhas/ucsentinel/GlobalEdgeApplication.kt'; s=read(p)
needle='''        // Extra 3 PM protection. WorkManager is inexact, so several aligned 24-hour anchors are used.\n        val ist=ZoneId.of("Asia/Kolkata")\n        val now=ZonedDateTime.now(ist)\n'''
replacement='''        val ist=ZoneId.of("Asia/Kolkata")\n        val now=ZonedDateTime.now(ist)\n\n        // Opening-entry protection. WorkManager timing is inexact, so use several\n        // daily anchors around the 09:15 confirmation window.\n        listOf(LocalTime.of(9,16),LocalTime.of(9,22),LocalTime.of(9,30)).forEachIndexed{idx,t->\n            var target=now.toLocalDate().atTime(t).atZone(ist)\n            if(!target.isAfter(now))target=target.plusDays(1)\n            val delay=Duration.between(now,target).toMillis().coerceAtLeast(0L)\n            val opening=PeriodicWorkRequestBuilder<ScanWorker>(24,TimeUnit.HOURS)\n                .setInitialDelay(delay,TimeUnit.MILLISECONDS).setConstraints(network).build()\n            wm.enqueueUniquePeriodicWork("global_edge_ai_opening_$idx",ExistingPeriodicWorkPolicy.UPDATE,opening)\n        }\n\n        // Extra 3 PM protection. WorkManager is inexact, so several aligned 24-hour anchors are used.\n'''
s=must_replace(s,needle,replacement,'opening worker anchors')
write(p,s)

print('Global Edge AI Trader v1.0.4 execution-plan upgrade applied')

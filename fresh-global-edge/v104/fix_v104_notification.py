from pathlib import Path
import re, sys
root=Path(sys.argv[1])
p=root/'app/src/main/java/com/suhas/ucsentinel/notifications/AppNotifier.kt'
s=p.read_text()
pat=re.compile(r'    private data class GlobalAlertPlan.*?    fun notifyStrategySetups',re.S)
m=pat.search(s)
if not m:
    raise SystemExit('missing generated Global Lead alert block')
block='''    private data class GlobalAlertPlan(val trigger:Double,val stop:Double,val target1:Double,val target2:Double)

    private fun globalAlertPlan(c:GlobalLeadCandidate):GlobalAlertPlan{
        val short=c.direction.name.contains("SHORT")
        val base=c.indianPrice.coerceAtLeast(0.01)
        val trigger=if(short)base*0.999 else base*1.001
        val openDistancePct=if(c.indianOpen>0.0)kotlin.math.abs(c.indianOpen-trigger)/trigger*100.0 else 0.0
        val riskPct=(openDistancePct*0.25).takeIf{it.isFinite()&&it>0.0}?.coerceIn(0.35,1.00)?:0.50
        val targetPct=c.expectedTargetPct.takeIf{it.isFinite()&&it>0.0}?.coerceIn(0.35,3.00)?:0.50
        val target2Pct=(targetPct*1.75).coerceIn(targetPct+0.20,4.00)
        val stop=if(short)trigger*(1.0+riskPct/100.0) else trigger*(1.0-riskPct/100.0)
        val target1=if(short)trigger*(1.0-targetPct/100.0) else trigger*(1.0+targetPct/100.0)
        val target2=if(short)trigger*(1.0-target2Pct/100.0) else trigger*(1.0+target2Pct/100.0)
        return GlobalAlertPlan(trigger,stop,target1,target2)
    }

    fun notifyGlobalLead(context:Context,candidates:List<GlobalLeadCandidate>){
        if(candidates.isEmpty()||!allowed(context))return
        ensureChannel(context)
        val qualified=candidates.filter{c->c.action.name.contains("ENTER")}.take(5)
        if(qualified.isEmpty())return
        val fingerprint=qualified.joinToString("|"){"${it.indianSymbol}:${it.direction.name}:${it.action.name}"}
        if(!shouldNotify(context,"global",fingerprint))return
        val lines=qualified.map{c->
            val side=if(c.direction.name.contains("SHORT"))"SHORT" else "LONG"
            val plan=globalAlertPlan(c)
            "$side ${c.indianSymbol} ${if(side=="SHORT")"≤" else "≥"} ₹${String.format(Locale.US,"%.2f",plan.trigger)} • SL ₹${String.format(Locale.US,"%.2f",plan.stop)} • T1 ₹${String.format(Locale.US,"%.2f",plan.target1)} • T2 ₹${String.format(Locale.US,"%.2f",plan.target2)}"
        }
        val n=NotificationCompat.Builder(context,GLOBAL_CHANNEL)
            .setSmallIcon(android.R.drawable.stat_notify_more)
            .setContentTitle("Global Lead: confirmed entry trigger")
            .setContentText(lines.first())
            .setStyle(NotificationCompat.BigTextStyle().bigText(lines.joinToString(" • ")))
            .setPriority(NotificationCompat.PRIORITY_HIGH).setCategory(NotificationCompat.CATEGORY_RECOMMENDATION)
            .setAutoCancel(true).setContentIntent(pending(context,2301)).build()
        runCatching{NotificationManagerCompat.from(context).notify(2301,n)}
    }

    fun notifyStrategySetups'''
s=s[:m.start()]+block+s[m.end():]
p.write_text(s)
print('v1.0.4 Global Lead notification block rebuilt cleanly')

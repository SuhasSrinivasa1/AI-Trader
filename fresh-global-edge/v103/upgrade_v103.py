from pathlib import Path
import sys
root=Path(sys.argv[1])

def read(rel): return (root/rel).read_text()
def write(rel,s):
    p=root/rel; p.parent.mkdir(parents=True,exist_ok=True); p.write_text(s)
def must_replace(s,old,new,label):
    if old not in s: raise SystemExit(f'missing needle: {label}')
    return s.replace(old,new,1)

# Version bump.
p='app/build.gradle.kts'; s=read(p)
s=must_replace(s,'versionCode = 102','versionCode = 103','versionCode')
s=must_replace(s,'versionName = "1.0.2"','versionName = "1.0.3"','versionName')
write(p,s)

# Global Lead is an opening-entry tool. Keep the 3 PM audit only as an exit/reassessment aid.
p='app/src/main/java/com/suhas/ucsentinel/ui/GlobalLeadScreen.kt'; s=read(p)
s=s.replace('15:00 decision deadline','09:15 entry window • post-open confirmation')
s=s.replace(
    '3 PM rule: keep a setup for the next session only while its signal survives. Otherwise it is dropped / marked EXIT BY 3 PM. No order is placed automatically.',
    '9:15 AM entry rule: Global Lead is used to select Indian LONG/SHORT entries after the NSE open. Enter only after the mapped foreign lead and Indian post-open continuation both confirm. The 3 PM check is for reassessment / exit management, not the primary entry decision. No order is placed automatically.'
)
s=s.replace('CARRY / ENTER BEFORE CLOSE','NEXT OPEN / ENTER AFTER 09:15')
s=s.replace('KEEP SHORT SETUP / NEXT SESSION','NEXT OPEN SHORT / ENTER AFTER 09:15')
write(p,s)

# Notifications: retain the v1.0.2 UC alert and add Global Lead + strategy entry alerts.
p='app/src/main/java/com/suhas/ucsentinel/notifications/AppNotifier.kt'
write(p, r'''package com.suhas.globaledgeai.notifications

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import com.suhas.globaledgeai.MainActivity
import com.suhas.globaledgeai.domain.model.Candidate
import com.suhas.globaledgeai.domain.model.GlobalLeadCandidate
import com.suhas.globaledgeai.domain.model.StrategySetup
import java.util.Locale
import kotlin.math.abs

object AppNotifier {
    private const val UC_CHANNEL = "actionable_uc_alerts"
    private const val GLOBAL_CHANNEL = "global_lead_entry_alerts"
    private const val STRATEGY_CHANNEL = "strategy_entry_alerts"
    private const val DEDUPE_MS = 20L * 60L * 1000L

    fun ensureChannel(context: Context) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val manager = context.getSystemService(NotificationManager::class.java)
            manager.createNotificationChannel(NotificationChannel(UC_CHANNEL,"Buyable upper-circuit alerts",NotificationManager.IMPORTANCE_HIGH).apply {
                description="Alerts when the automatic scanner finds a near-upper-circuit stock with executable sellers still available."
                enableVibration(true)
            })
            manager.createNotificationChannel(NotificationChannel(GLOBAL_CHANNEL,"Global Lead entry alerts",NotificationManager.IMPORTANCE_HIGH).apply {
                description="9:15 AM Indian LONG/SHORT entry alerts confirmed by the Global Lead scanner."
                enableVibration(true)
            })
            manager.createNotificationChannel(NotificationChannel(STRATEGY_CHANNEL,"Trading strategy entry alerts",NotificationManager.IMPORTANCE_HIGH).apply {
                description="Entry-price alerts when an enabled trading strategy produces a qualified setup."
                enableVibration(true)
            })
        }
    }

    private fun allowed(context: Context):Boolean = Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU ||
        context.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED

    private fun pending(context: Context, requestCode:Int):PendingIntent = PendingIntent.getActivity(
        context, requestCode, Intent(context,MainActivity::class.java).apply {
            flags=Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
        }, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
    )

    private fun shouldNotify(context:Context,key:String,fingerprint:String):Boolean {
        val prefs=context.getSharedPreferences("global_edge_notifications",Context.MODE_PRIVATE)
        val now=System.currentTimeMillis()
        if(prefs.getString("${key}_fingerprint","")==fingerprint && now-prefs.getLong("${key}_at",0L)<DEDUPE_MS)return false
        prefs.edit().putString("${key}_fingerprint",fingerprint).putLong("${key}_at",now).apply()
        return true
    }

    fun notifyBuyableUc(context: Context, candidates: List<Candidate>) {
        if(candidates.isEmpty()||!allowed(context))return
        ensureChannel(context)
        val actionable=candidates.take(3)
        val fingerprint=actionable.joinToString("|"){"${it.symbol}:${it.score.toInt()}"}
        if(!shouldNotify(context,"uc",fingerprint))return
        val lines=actionable.map{c->
            val distance=if(c.upperCircuit>0.0)abs(c.upperCircuit-c.price)/c.upperCircuit*100.0 else 0.0
            "${c.symbol}: ${String.format(Locale.US,"%.2f",distance)}% from UC • score ${c.score.toInt()}"
        }
        val n=NotificationCompat.Builder(context,UC_CHANNEL)
            .setSmallIcon(android.R.drawable.stat_notify_more)
            .setContentTitle("Buyable upper-circuit setup")
            .setContentText(if(actionable.size==1)lines.first() else "${actionable.size} buyable near-UC setups found")
            .setStyle(NotificationCompat.BigTextStyle().bigText(lines.joinToString("\n")))
            .setPriority(NotificationCompat.PRIORITY_HIGH).setCategory(NotificationCompat.CATEGORY_RECOMMENDATION)
            .setAutoCancel(true).setContentIntent(pending(context,2201)).build()
        runCatching{NotificationManagerCompat.from(context).notify(2201,n)}
    }

    fun notifyGlobalLead(context:Context,candidates:List<GlobalLeadCandidate>){
        if(candidates.isEmpty()||!allowed(context))return
        ensureChannel(context)
        val qualified=candidates.filter{c->
            val a=c.action.name
            a.contains("ENTER") || a.contains("CARRY") || a.contains("READY")
        }.take(5)
        if(qualified.isEmpty())return
        val fingerprint=qualified.joinToString("|"){"${it.symbol}:${it.direction.name}:${String.format(Locale.US,"%.2f",it.indianPrice)}"}
        if(!shouldNotify(context,"global",fingerprint))return
        val lines=qualified.map{c->
            val side=if(c.direction.name.contains("SHORT"))"SHORT" else "LONG"
            val target=if(c.expectedTargetPct.isFinite()&&c.expectedTargetPct>0.0)" • target +${String.format(Locale.US,"%.1f",c.expectedTargetPct)}%" else ""
            "$side ${c.symbol} • entry ₹${String.format(Locale.US,"%.2f",c.indianPrice)}$target"
        }
        val n=NotificationCompat.Builder(context,GLOBAL_CHANNEL)
            .setSmallIcon(android.R.drawable.stat_notify_more)
            .setContentTitle("Global Lead: 9:15 entry signal")
            .setContentText(lines.first())
            .setStyle(NotificationCompat.BigTextStyle().bigText(lines.joinToString("\n")))
            .setPriority(NotificationCompat.PRIORITY_HIGH).setCategory(NotificationCompat.CATEGORY_RECOMMENDATION)
            .setAutoCancel(true).setContentIntent(pending(context,2301)).build()
        runCatching{NotificationManagerCompat.from(context).notify(2301,n)}
    }

    fun notifyStrategySetups(context:Context,setups:List<StrategySetup>){
        if(setups.isEmpty()||!allowed(context))return
        ensureChannel(context)
        val top=setups.filter{it.entryPrice.isFinite()&&it.entryPrice>0.0}.take(5)
        if(top.isEmpty())return
        val fingerprint=top.joinToString("|"){"${it.strategyId}:${it.symbol}:${it.direction.name}:${String.format(Locale.US,"%.2f",it.entryPrice)}"}
        if(!shouldNotify(context,"strategy",fingerprint))return
        val lines=top.map{s->
            "${s.direction.name} ${s.symbol} • buy/entry ₹${String.format(Locale.US,"%.2f",s.entryPrice)} • ${s.strategyName} • score ${s.score.toInt()}"
        }
        val n=NotificationCompat.Builder(context,STRATEGY_CHANNEL)
            .setSmallIcon(android.R.drawable.stat_notify_more)
            .setContentTitle("Trading strategy entry")
            .setContentText(lines.first())
            .setStyle(NotificationCompat.BigTextStyle().bigText(lines.joinToString("\n")))
            .setPriority(NotificationCompat.PRIORITY_HIGH).setCategory(NotificationCompat.CATEGORY_RECOMMENDATION)
            .setAutoCancel(true).setContentIntent(pending(context,2401)).build()
        runCatching{NotificationManagerCompat.from(context).notify(2401,n)}
    }
}
''')

# Background worker: notify on every newly-qualified Global Lead or strategy setup.
p='app/src/main/java/com/suhas/ucsentinel/worker/ScanWorker.kt'; s=read(p)
# v1.0.2 already imports AppNotifier.
old='''                    runCatching{repo.scanTradingStrategies()}\n'''
new='''                    runCatching{repo.scanTradingStrategies()}.onSuccess{summary->\n                        AppNotifier.notifyStrategySetups(applicationContext,summary.topSetups)\n                    }\n'''
s=must_replace(s,old,new,'strategy worker notification')
# Global Lead should stay fresh in the background and alert only for qualified ENTER/READY actions.
needle='''            // Freeze only after the near-close scan attempt, never before it.\n            repo.ensureTodayFreezeAudit(nowZ)\n'''
insert='''            if(settings.globalLeadEnabled){\n                runCatching{repo.scanGlobalLead()}.onSuccess{summary->\n                    AppNotifier.notifyGlobalLead(applicationContext,summary.longCandidates+summary.shortCandidates)\n                }\n            }\n            // Freeze only after the near-close scan attempt, never before it.\n            repo.ensureTodayFreezeAudit(nowZ)\n'''
s=must_replace(s,needle,insert,'global worker notification')
write(p,s)

# Make the Global Lead card explicitly show the actionable Indian entry reference price. This is
# intentionally a source-text patch that follows the current card's existing Indian-opportunity line.
p='app/src/main/java/com/suhas/ucsentinel/ui/GlobalLeadScreen.kt'; s=read(p)
# The screen already displays Indian opportunity data; add a clear entry-price label beside it.
replacements=[
    ('"Indian opportunity ${c.indianSymbol}"','"Indian opportunity ${c.indianSymbol} • Entry ₹${fmt(c.indianPrice)}"'),
    ('"Indian opportunity " + c.indianSymbol','"Indian opportunity " + c.indianSymbol + " • Entry ₹" + fmt(c.indianPrice)'),
]
changed=False
for old,new in replacements:
    if old in s:
        s=s.replace(old,new,1); changed=True; break
# If the exact expression changed between builds, the existing card still exposes Indian price in its
# metrics; do not make the build fail solely on this cosmetic augmentation.
write(p,s)

print('Global Edge AI Trader v1.0.3 upgrade applied')

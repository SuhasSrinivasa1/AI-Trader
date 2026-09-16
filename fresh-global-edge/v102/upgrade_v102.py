from pathlib import Path
import sys
root=Path(sys.argv[1])

def read(rel): return (root/rel).read_text()
def write(rel,s):
    p=root/rel; p.parent.mkdir(parents=True,exist_ok=True); p.write_text(s)
def must_replace(s,old,new,label):
    if old not in s: raise SystemExit(f'missing needle: {label}')
    return s.replace(old,new,1)

p='app/build.gradle.kts'; s=read(p)
s=must_replace(s,'versionCode = 101','versionCode = 102','versionCode')
s=must_replace(s,'versionName = "1.0.1"','versionName = "1.0.2"','versionName')
write(p,s)

p='app/src/main/java/com/suhas/ucsentinel/domain/engine/ScannerEngine.kt'; s=read(p)
old='''            val quote = runCatching { growwClient.getQuote(accessToken, instrument.tradingSymbol) }.getOrNull()\n                ?: continue\n\n            val distanceToUc = if (quote.upperCircuit <= 0) 999.0\n'''
new='''            val quote = runCatching { growwClient.getQuote(accessToken, instrument.tradingSymbol) }.getOrNull()\n                ?: continue\n\n            // Execution gate: strong momentum is not an actionable entry if there is nobody to sell.\n            // Keep locked names out of recommendations and let the pressure engine find them earlier.\n            val executableAsk = quote.totalSellQuantity > 0L && (\n                (quote.offerPrice > 0.0 && quote.offerQuantity > 0L) ||\n                    quote.sellDepth.any { it.price > 0.0 && it.quantity > 0L }\n                )\n            if (!executableAsk) {\n                progress("Skipped ${instrument.tradingSymbol}: UC/ask locked — no executable sellers")\n                continue\n            }\n\n            val distanceToUc = if (quote.upperCircuit <= 0) 999.0\n'''
s=must_replace(s,old,new,'Scanner quote gate')
old='''            if (distanceToUc <= 0.10) score += 5.0\n            if (quote.totalSellQuantity == 0L && quote.totalBuyQuantity > 0L) score += 4.0\n            if (Indicators.consecutiveCircuitLikeDays(daily) >= 1) score += 3.0\n'''
new='''            if (distanceToUc <= 0.10) score += 5.0\n            // Reward strong demand only while actual sell-side liquidity still exists.\n            if (quote.totalBuyQuantity > quote.totalSellQuantity && quote.offerQuantity > 0L) score += 2.0\n            if (Indicators.consecutiveCircuitLikeDays(daily) >= 1) score += 3.0\n'''
s=must_replace(s,old,new,'Scanner zero seller bonus')
write(p,s)

p='app/src/main/java/com/suhas/ucsentinel/MainActivity.kt'; s=read(p)
s=must_replace(s,'import android.os.Bundle\n','''import android.Manifest\nimport android.content.pm.PackageManager\nimport android.os.Build\nimport android.os.Bundle\n''','MainActivity android imports')
s=must_replace(s,'import androidx.activity.ComponentActivity\n','''import androidx.activity.ComponentActivity\nimport androidx.activity.result.contract.ActivityResultContracts\n''','MainActivity activity import')
old='''class MainActivity : ComponentActivity() {\n    override fun onCreate(savedInstanceState: Bundle?) {\n        super.onCreate(savedInstanceState)\n\n        val repo = (application as GlobalEdgeApplication).repository\n'''
new='''class MainActivity : ComponentActivity() {\n    private val notificationPermission = registerForActivityResult(ActivityResultContracts.RequestPermission()) { }\n\n    override fun onCreate(savedInstanceState: Bundle?) {\n        super.onCreate(savedInstanceState)\n\n        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&\n            checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {\n            notificationPermission.launch(Manifest.permission.POST_NOTIFICATIONS)\n        }\n\n        val repo = (application as GlobalEdgeApplication).repository\n'''
s=must_replace(s,old,new,'MainActivity permission')
write(p,s)

write('app/src/main/java/com/suhas/ucsentinel/notifications/AppNotifier.kt', r'''package com.suhas.globaledgeai.notifications

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
import java.util.Locale
import kotlin.math.abs

object AppNotifier {
    private const val CHANNEL_ID = "actionable_uc_alerts"
    private const val NOTIFICATION_ID = 2201
    private const val DEDUPE_MS = 20L * 60L * 1000L

    fun ensureChannel(context: Context) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val manager = context.getSystemService(NotificationManager::class.java)
            manager.createNotificationChannel(
                NotificationChannel(
                    CHANNEL_ID,
                    "Buyable upper-circuit alerts",
                    NotificationManager.IMPORTANCE_HIGH
                ).apply {
                    description = "Alerts when the automatic scanner finds a near-upper-circuit stock with executable sellers still available."
                    enableVibration(true)
                }
            )
        }
    }

    fun notifyBuyableUc(context: Context, candidates: List<Candidate>) {
        if (candidates.isEmpty()) return
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
            context.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) return

        ensureChannel(context)
        val actionable = candidates.take(3)
        val fingerprint = actionable.joinToString("|") { "${it.symbol}:${it.score.toInt()}" }
        val prefs = context.getSharedPreferences("global_edge_notifications", Context.MODE_PRIVATE)
        val now = System.currentTimeMillis()
        if (prefs.getString("last_uc_fingerprint", "") == fingerprint &&
            now - prefs.getLong("last_uc_at", 0L) < DEDUPE_MS) return

        val lines = actionable.map { c ->
            val distance = if (c.upperCircuit > 0.0) abs(c.upperCircuit - c.price) / c.upperCircuit * 100.0 else 0.0
            "${c.symbol}: ${String.format(Locale.US, "%.2f", distance)}% from UC • score ${c.score.toInt()}"
        }
        val text = if (actionable.size == 1) lines.first() else "${actionable.size} buyable near-UC setups found"
        val big = lines.joinToString("\n")

        val intent = Intent(context, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
        }
        val pending = PendingIntent.getActivity(
            context, 2201, intent, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        val notification = NotificationCompat.Builder(context, CHANNEL_ID)
            .setSmallIcon(android.R.drawable.stat_notify_more)
            .setContentTitle("Buyable upper-circuit setup")
            .setContentText(text)
            .setStyle(NotificationCompat.BigTextStyle().bigText(big))
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setCategory(NotificationCompat.CATEGORY_RECOMMENDATION)
            .setAutoCancel(true)
            .setContentIntent(pending)
            .build()
        runCatching { NotificationManagerCompat.from(context).notify(NOTIFICATION_ID, notification) }
        prefs.edit().putString("last_uc_fingerprint", fingerprint).putLong("last_uc_at", now).apply()
    }
}
''')

p='app/src/main/java/com/suhas/ucsentinel/GlobalEdgeApplication.kt'; s=read(p)
s=must_replace(s,'import com.suhas.globaledgeai.data.repository.GlobalEdgeAITraderRepository\n','''import com.suhas.globaledgeai.data.repository.GlobalEdgeAITraderRepository\nimport com.suhas.globaledgeai.notifications.AppNotifier\n''','Application notifier import')
s=must_replace(s,'override fun onCreate(){super.onCreate();repository=GlobalEdgeAITraderRepository(this);scheduleWorkers()}','''override fun onCreate(){super.onCreate();AppNotifier.ensureChannel(this);repository=GlobalEdgeAITraderRepository(this);scheduleWorkers()}''','Application onCreate notifier')
write(p,s)

p='app/src/main/java/com/suhas/ucsentinel/worker/ScanWorker.kt'; s=read(p)
s=must_replace(s,'import com.suhas.globaledgeai.GlobalEdgeApplication\n','''import com.suhas.globaledgeai.GlobalEdgeApplication\nimport com.suhas.globaledgeai.notifications.AppNotifier\n''','Worker notifier import')
old='''                if(due){\n                    repo.scanAll()\n                    repo.markPressureScanAt(nowMs)\n                    if(nearClose)repo.markNearCloseAutoScanAt(nowMs)\n                }\n'''
new='''                if(due){\n                    val dual=repo.scanAll()\n                    AppNotifier.notifyBuyableUc(applicationContext,dual.uc.candidates)\n                    repo.markPressureScanAt(nowMs)\n                    if(nearClose)repo.markNearCloseAutoScanAt(nowMs)\n                }\n'''
s=must_replace(s,old,new,'Worker scan notify')
write(p,s)

print('Global Edge AI Trader v1.0.2 upgrade applied')

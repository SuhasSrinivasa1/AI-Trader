from pathlib import Path

root = Path('android')

# Version bump for Vivo Y73 compatibility edition.
p = root / 'app/build.gradle.kts'
s = p.read_text()
s = s.replace('versionCode = 310', 'versionCode = 311')
s = s.replace('versionName = "3.1.0"', 'versionName = "3.1.1-vivo-y73"')
p.write_text(s)

# Permission required for the user-initiated battery-optimization exemption prompt.
p = root / 'app/src/main/AndroidManifest.xml'
s = p.read_text()
needle = '    <uses-permission android:name="android.permission.POST_NOTIFICATIONS" />\n'
if 'REQUEST_IGNORE_BATTERY_OPTIMIZATIONS' not in s:
    s = s.replace(needle, needle + '    <uses-permission android:name="android.permission.REQUEST_IGNORE_BATTERY_OPTIMIZATIONS" />\n')
p.write_text(s)

# Improve listener recovery on aggressive OEM background management.
p = root / 'app/src/main/java/com/multify/traderpro/service/MultifyNotificationListenerService.kt'
s = p.read_text()
needle = '''    override fun onNotificationPosted(sbn: StatusBarNotification?) {\n'''
insert = '''    override fun onListenerDisconnected() {\n        super.onListenerDisconnected()\n        auditLogger.log("RUNTIME", "NOTIFICATION_LISTENER_DISCONNECTED")\n        // Vivo/Funtouch OS can aggressively reclaim background components. Ask Android to\n        // re-bind the notification listener instead of waiting for the app to be reopened.\n        runCatching { requestRebind(android.content.ComponentName(this, MultifyNotificationListenerService::class.java)) }\n    }\n\n    override fun onNotificationPosted(sbn: StatusBarNotification?) {\n'''
assert needle in s
s = s.replace(needle, insert, 1)
p.write_text(s)

# Add Vivo-specific runtime controls/status to the System screen.
p = root / 'app/src/main/java/com/multify/traderpro/ui/screens/TraderApp.kt'
s = p.read_text()

# Imports.
s = s.replace('import android.content.Intent\n', 'import android.content.Intent\nimport android.net.Uri\nimport android.os.Build\nimport android.os.PowerManager\n')

# Runtime variables in SystemScreen.
needle = '''    val notificationAccess = notificationAccessEnabled(context)\n    val live = state.settings.liveExecutionEffective\n'''
insert = '''    val notificationAccess = notificationAccessEnabled(context)\n    val batteryUnrestricted = batteryOptimizationIgnored(context)\n    val deviceName = "${Build.MANUFACTURER.replaceFirstChar { if (it.isLowerCase()) it.titlecase(Locale.US) else it.toString() }} ${Build.MODEL}".trim()\n    val isVivo = Build.MANUFACTURER.equals("vivo", ignoreCase = true)\n    val live = state.settings.liveExecutionEffective\n'''
assert needle in s
s = s.replace(needle, insert, 1)

# Add device rows and buttons to Permissions card.
needle = '''                    KeyValueRow("Notification access", if (notificationAccess) "Enabled" else "Required", if (notificationAccess) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.error)\n                    KeyValueRow("Intraday mode", if (live) "LIVE" else "SHADOW ₹2L")\n                    KeyValueRow("Manual mode", if (state.settings.fastTrackEffective) "AUTO CNC" else "OFF")\n                    KeyValueRow("Static IP", if (state.settings.staticIpMatched) "Verified" else "Not verified", if (state.settings.staticIpMatched) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.error)\n                    Spacer(Modifier.height(12.dp))\n                    OutlinedButton(onClick = { openNotificationAccessSettings(context) }, modifier = Modifier.fillMaxWidth()) {\n                        Icon(Icons.Default.NotificationsActive, null)\n                        Spacer(Modifier.size(8.dp))\n                        Text("Open notification access")\n                    }\n'''
insert = '''                    KeyValueRow("Device", deviceName)\n                    KeyValueRow("Notification access", if (notificationAccess) "Enabled" else "Required", if (notificationAccess) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.error)\n                    KeyValueRow("Background battery mode", if (batteryUnrestricted) "Unrestricted" else "Optimized", if (batteryUnrestricted) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.error)\n                    KeyValueRow("Intraday mode", if (live) "LIVE" else "SHADOW ₹2L")\n                    KeyValueRow("Manual mode", if (state.settings.fastTrackEffective) "AUTO CNC" else "OFF")\n                    KeyValueRow("Static IP", if (state.settings.staticIpMatched) "Verified" else "Not verified", if (state.settings.staticIpMatched) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.error)\n                    if (isVivo) {\n                        Text(\n                            "Vivo/Funtouch OS can aggressively stop background apps. For reliable Multify notification capture, keep Notification Access enabled and set Multify Trader Pro to unrestricted background battery usage / allow background activity. The app also requests listener rebind if Vivo disconnects it.",\n                            style = MaterialTheme.typography.bodySmall,\n                            color = MaterialTheme.colorScheme.onSurfaceVariant\n                        )\n                    }\n                    Spacer(Modifier.height(12.dp))\n                    OutlinedButton(onClick = { openNotificationAccessSettings(context) }, modifier = Modifier.fillMaxWidth()) {\n                        Icon(Icons.Default.NotificationsActive, null)\n                        Spacer(Modifier.size(8.dp))\n                        Text("Open notification access")\n                    }\n                    Spacer(Modifier.height(8.dp))\n                    Button(onClick = { requestUnrestrictedBattery(context) }, modifier = Modifier.fillMaxWidth()) {\n                        Icon(Icons.Default.Bolt, null)\n                        Spacer(Modifier.size(8.dp))\n                        Text(if (batteryUnrestricted) "Background battery unrestricted" else "Allow unrestricted background")\n                    }\n                    if (isVivo) {\n                        Spacer(Modifier.height(8.dp))\n                        OutlinedButton(onClick = { openAppDetails(context) }, modifier = Modifier.fillMaxWidth()) {\n                            Icon(Icons.Default.Settings, null)\n                            Spacer(Modifier.size(8.dp))\n                            Text("Open Vivo app settings / Auto-start")\n                        }\n                    }\n'''
assert needle in s
s = s.replace(needle, insert, 1)

# Add compatibility info in diagnostics.
needle = '''                    KeyValueRow("Package", BuildConfig.APPLICATION_ID)\n'''
insert = '''                    KeyValueRow("Package", BuildConfig.APPLICATION_ID)\n                    KeyValueRow("Compatibility", if (isVivo) "Vivo / Funtouch background hardened" else "Standard Android")\n'''
assert needle in s
s = s.replace(needle, insert, 1)

# Helpers at bottom.
needle = '''private fun openNotificationAccessSettings(context: Context) {\n    context.startActivity(Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))\n}\n'''
insert = '''private fun openNotificationAccessSettings(context: Context) {\n    context.startActivity(Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))\n}\n\nprivate fun batteryOptimizationIgnored(context: Context): Boolean {\n    val power = context.getSystemService(Context.POWER_SERVICE) as PowerManager\n    return power.isIgnoringBatteryOptimizations(context.packageName)\n}\n\nprivate fun requestUnrestrictedBattery(context: Context) {\n    val packageUri = Uri.parse("package:${context.packageName}")\n    val direct = Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS, packageUri)\n        .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)\n    val fallback = Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS)\n        .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)\n    runCatching { context.startActivity(direct) }\n        .recoverCatching { context.startActivity(fallback) }\n        .recoverCatching { openAppDetails(context) }\n}\n\nprivate fun openAppDetails(context: Context) {\n    val intent = Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.parse("package:${context.packageName}"))\n        .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)\n    context.startActivity(intent)\n}\n'''
assert needle in s
s = s.replace(needle, insert, 1)
p.write_text(s)

print('Applied Vivo Y73 compatibility patch')
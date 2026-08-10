#!/usr/bin/env python3
from pathlib import Path
import runpy

# Start from the validated v2.4.6 build, then remove the MASTER/CHILD/LAN architecture
# completely from the shipping app. Trading behavior remains the v2.4.5/v2.4.6
# single-stock critical path: flat => BUY critical, one live stock => SELL critical.
runpy.run_path('hotfix/run_v246.py', run_name='__main__')

ROOT = Path('android-stable')
J = ROOT / 'app/src/main/java/com/suhas/multyfiautobuy/stable'


def read(p): return Path(p).read_text(encoding='utf-8')
def write(p, s): Path(p).write_text(s, encoding='utf-8')
def replace_once(p, old, new):
    p = Path(p)
    t = read(p)
    n = t.count(old)
    if n != 1:
        raise RuntimeError(f'{p}: expected one match, found {n}: {old[:140]}')
    write(p, t.replace(old, new, 1))

# One standalone APK only. The same package can be installed independently on each phone.
replace_once(ROOT / 'settings.gradle', 'include(":app")\ninclude(":child")', 'include(":app")')
replace_once(ROOT / 'app/build.gradle', 'versionCode 246', 'versionCode 247')
replace_once(ROOT / 'app/build.gradle', "versionName '2.4.6'", "versionName '2.4.7'")

# Remove LAN-only permissions and the relay service from the shipping manifest.
manifest = ROOT / 'app/src/main/AndroidManifest.xml'
t = read(manifest)
t = t.replace('    <uses-permission android:name="android.permission.ACCESS_WIFI_STATE" />\n', '')
t = t.replace('    <uses-permission android:name="android.permission.CHANGE_WIFI_MULTICAST_STATE" />\n', '')
relay = '''        <service\n            android:name=".LanMasterRelayService"\n            android:exported="false"\n            android:foregroundServiceType="specialUse"\n            android:stopWithTask="false">\n            <property\n                android:name="android.app.PROPERTY_SPECIAL_USE_FGS_SUBTYPE"\n                android:value="Local Wi-Fi/hotspot Multyfi signal relay to paired child phones" />\n        </service>\n\n'''
if relay not in t:
    raise RuntimeError('MASTER relay service block missing from generated v2.4.6 manifest')
t = t.replace(relay, '')
write(manifest, t)

# Runtime is now only the local notification listener + local position monitor.
write(J / 'AppRuntimeControl.java', '''package com.suhas.multyfiautobuy.stable;\n\nimport android.content.ComponentName;\nimport android.content.Context;\nimport android.content.Intent;\nimport android.os.Build;\nimport android.service.notification.NotificationListenerService;\n\nfinal class AppRuntimeControl {\n    private AppRuntimeControl() { }\n\n    static void sync(Context c) {\n        if (AppPrefs.isArmed(c)) activate(c); else deactivate(c);\n    }\n\n    static void activate(Context c) {\n        StrategyMonitorService.ensureRunning(c);\n        try {\n            NotificationListenerService.requestRebind(\n                    new ComponentName(c, MultyfiNotificationService.class));\n        } catch (Exception ignored) { }\n    }\n\n    static void deactivate(Context c) {\n        // A stale active strategy is the only safety exception: keep the local\n        // position monitor alive until Groww reports zero.\n        int active = StrategyStore.activeCount(c);\n        if (Build.VERSION.SDK_INT >= 34) {\n            try {\n                NotificationListenerService.requestUnbind(\n                        new ComponentName(c, MultyfiNotificationService.class));\n            } catch (Exception ignored) { }\n        }\n        if (active <= 0) c.stopService(new Intent(c, StrategyMonitorService.class));\n        else StrategyMonitorService.ensureRunning(c);\n    }\n}\n''')

# BUY and SELL share the critical priority; everything else is background.
write(J / 'PriorityExecutors.java', '''package com.suhas.multyfiautobuy.stable;\n\nimport java.util.concurrent.ExecutorService;\nimport java.util.concurrent.Executors;\nimport java.util.concurrent.ScheduledExecutorService;\nimport java.util.concurrent.ThreadFactory;\nimport java.util.concurrent.atomic.AtomicInteger;\n\n/** Broker-facing notification work always outranks UI/logging/background work. */\nfinal class PriorityExecutors {\n    static final int EARLY_EXIT_PRIORITY = -4;\n    static final int ENTRY_PRIORITY = -4;\n    static final int BACKGROUND_PRIORITY = 10;\n\n    private PriorityExecutors() { }\n\n    static ExecutorService earlyExitSingle(String name) {\n        return Executors.newSingleThreadExecutor(factory(name, EARLY_EXIT_PRIORITY));\n    }\n    static ExecutorService entrySingle(String name) {\n        return Executors.newSingleThreadExecutor(factory(name, ENTRY_PRIORITY));\n    }\n    static ExecutorService backgroundSingle(String name) {\n        return Executors.newSingleThreadExecutor(factory(name, BACKGROUND_PRIORITY));\n    }\n    static ExecutorService backgroundCached(String name) {\n        return Executors.newCachedThreadPool(factory(name, BACKGROUND_PRIORITY));\n    }\n    static ScheduledExecutorService backgroundScheduled(String name) {\n        return Executors.newSingleThreadScheduledExecutor(factory(name, BACKGROUND_PRIORITY));\n    }\n    static boolean criticalBeatsBackgroundContract() {\n        return EARLY_EXIT_PRIORITY == ENTRY_PRIORITY && ENTRY_PRIORITY < BACKGROUND_PRIORITY;\n    }\n    private static ThreadFactory factory(String prefix, int priority) {\n        AtomicInteger ids = new AtomicInteger();\n        return task -> new Thread(() -> {\n            try { android.os.Process.setThreadPriority(priority); } catch (Exception ignored) { }\n            task.run();\n        }, prefix + '-' + ids.incrementAndGet());\n    }\n}\n''')

# Notification intake is local only. Remove relay fan-out and relayed ingress entirely.
p = J / 'ProductionNotificationService.java'
t = read(p)
t = t.replace('AppPrefs.log(this, "LISTENER READY", "Multyfi listener connected for armed MASTER operation.");',
              'AppPrefs.log(this, "LISTENER READY", "Multyfi listener connected for standalone execution.");')
t = t.replace('AppPrefs.log(this, "LISTENER DISCONNECTED", "Android disconnected the listener; armed MASTER requested an immediate rebind.");',
              'AppPrefs.log(this, "LISTENER DISCONNECTED", "Android disconnected the listener; standalone runtime requested an immediate rebind.");')
replace_block = '''            if (SignalParser.containsEarlyExitPhrase(rawText) || liveTradeHint) earlyExitExecutor.execute(work);\n            else entryExecutor.execute(work);\n            if (!AppRole.isChild(this)) {\n                LanMasterRelayService.publishFast(this, rawText, postTime);\n            }\n'''
replacement = '''            if (SignalParser.containsEarlyExitPhrase(rawText) || liveTradeHint) earlyExitExecutor.execute(work);\n            else entryExecutor.execute(work);\n'''
if replace_block not in t:
    raise RuntimeError('relay publish block missing')
t = t.replace(replace_block, replacement, 1)
relayed = '''    protected final void enqueueRelayedMultyfi(String rawText, long postTime) {\n        Runnable work = () -> process(rawText, postTime);\n        if (SignalParser.containsEarlyExitPhrase(rawText) || liveTradeHint) earlyExitExecutor.execute(work);\n        else entryExecutor.execute(work);\n    }\n\n'''
if relayed not in t:
    raise RuntimeError('relayed ingress method missing')
t = t.replace(relayed, '', 1)
write(p, t)

# Standalone dashboard and readiness gates.
p = J / 'ProductionActivity.java'
t = read(p)
old = '''        if (!AppRole.isChild(this)) {\n            try {\n                NotificationListenerService.requestRebind(\n                        new ComponentName(this, MultyfiNotificationService.class));\n            } catch (Exception ignored) { }\n        }\n'''
new = '''        try {\n            NotificationListenerService.requestRebind(\n                    new ComponentName(this, MultyfiNotificationService.class));\n        } catch (Exception ignored) { }\n'''
if old not in t: raise RuntimeError('role-dependent onResume block missing')
t = t.replace(old, new, 1)
old = '''        TextView eyebrow = label(AppRole.isChild(this) ? "PRIVATE LG G7 CHILD CONSOLE" : "PRIVATE S24 EXECUTION CONSOLE", 12, GREEN, true);\n        eyebrow.setLetterSpacing(0.12f);\n        root.addView(eyebrow);\n        TextView title = label(AppRole.isChild(this) ? "Multyfi AutoBuy CHILD" : "Multyfi AutoBuy MASTER", 30, TEXT, true);\n        root.addView(title, topMargin(4));\n        String release = BuildConfig.VERSION_NAME;\n        TextView subtitle = label(AppRole.isChild(this)\n                ? "LG G7 ThinQ • local-LAN child • release " + release\n                : "Galaxy S24 Ultra • local-LAN master • release " + release,\n                14, MUTED, false);\n'''
new = '''        TextView eyebrow = label("PRIVATE STANDALONE EXECUTION CONSOLE", 12, GREEN, true);\n        eyebrow.setLetterSpacing(0.12f);\n        root.addView(eyebrow);\n        TextView title = label("Multyfi AutoBuy", 30, TEXT, true);\n        root.addView(title, topMargin(4));\n        String release = BuildConfig.VERSION_NAME;\n        TextView subtitle = label("Standalone local execution • release " + release, 14, MUTED, false);\n'''
if old not in t: raise RuntimeError('MASTER/CHILD dashboard header missing')
t = t.replace(old, new, 1)
old = '''        if (!AppRole.isChild(this)) {\n            Button openAccess = secondaryButton("OPEN NOTIFICATION ACCESS");\n            openAccess.setOnClickListener(v -> openSetting(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS));\n            networkCard.addView(openAccess, topMargin(10));\n        }\n'''
new = '''        Button openAccess = secondaryButton("OPEN NOTIFICATION ACCESS");\n        openAccess.setOnClickListener(v -> openSetting(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS));\n        networkCard.addView(openAccess, topMargin(10));\n'''
if old not in t: raise RuntimeError('role-dependent notification access button missing')
t = t.replace(old, new, 1)
t = t.replace('"Auto-Buy OFF by default • GROSS loss -₹2,000 • no daily profit cap • local LAN relay • v"',
              '"Auto-Buy OFF by default • GROSS loss -₹2,000 • no daily profit cap • standalone • v"')
t = t.replace('"Background monitor and local LAN relay enabled • Multyfi target exits • GROSS -₹2,000 emergency loss lock • no daily profit cap."',
              '"Standalone notification listener and position monitor enabled • Multyfi target exits • GROSS -₹2,000 emergency loss lock • no daily profit cap."')
t = t.replace('''            AppPrefs.log(this, "HARD OFF BY USER",\n                    "Trading monitor, MASTER/CHILD LAN relay and Multyfi listener runtime are stopped. No background relay connection remains.");\n            TradeEventNotifier.notifyTradingOff(this, "Application hard-off: trading and LAN relay stopped.");\n''',
'''            AppPrefs.log(this, "HARD OFF BY USER",\n                    "Standalone trading monitor and Multyfi listener runtime are stopped.");\n            TradeEventNotifier.notifyTradingOff(this, "Application hard-off: standalone trading stopped.");\n''')
old = '''        boolean notificationReady = AppRole.isChild(this)\n                ? RelayState.childConnected(this) : hasNotificationAccess();\n'''
if old not in t: raise RuntimeError('role-dependent notification readiness missing')
t = t.replace(old, '        boolean notificationReady = hasNotificationAccess();\n', 1)
old = '''        if (!persistentlyArmed) {\n            notificationStatus.setText("● Runtime OFF: local MASTER/CHILD relay stopped");\n            notificationStatus.setTextColor(MUTED);\n        } else {\n            notificationStatus.setText(AppRole.isChild(this)\n                    ? (notificationReady\n                        ? "● Master LAN relay: connected • " + RelayState.masterIp(this)\n                            + " • last " + Math.max(0, RelayState.latency(this)) + " ms"\n                        : "● Master LAN relay: disconnected — hotspot/Wi-Fi gateway auto-retrying")\n                    : (notificationReady\n                        ? "● Notification listener: connected • LAN children "\n                            + RelayState.masterChildren(this)\n                        : "● Notification listener: reconnecting"));\n            notificationStatus.setTextColor(notificationReady ? GREEN : AMBER);\n        }\n'''
new = '''        if (!persistentlyArmed) {\n            notificationStatus.setText("● Runtime OFF: notification listener stopped");\n            notificationStatus.setTextColor(MUTED);\n        } else {\n            notificationStatus.setText(notificationReady\n                    ? "● Notification listener: connected • standalone execution"\n                    : "● Notification listener: reconnecting");\n            notificationStatus.setTextColor(notificationReady ? GREEN : AMBER);\n        }\n'''
if old not in t: raise RuntimeError('LAN status block missing')
t = t.replace(old, new, 1)
t = t.replace('statusDetail.setText("Hard OFF • trading monitor stopped • local MASTER/CHILD relay stopped • no Multyfi background processing.");',
              'statusDetail.setText("Hard OFF • standalone trading monitor stopped • no Multyfi background processing.");')
old = '''        if (AppRole.isChild(this) && !RelayState.childConnected(this)) return "Waiting for local-LAN connection to MASTER";\n        if (!AppRole.isChild(this) && !hasNotificationAccess()) return "Grant Notification Access to Multyfi AutoBuy MASTER";\n'''
if old not in t: raise RuntimeError('LAN readiness gates missing')
t = t.replace(old, '        if (!hasNotificationAccess()) return "Grant Notification Access to Multyfi AutoBuy";\n', 1)
write(p, t)

# Delete the entire role/LAN implementation from the only shipping module.
for name in ('AppRole.java', 'LanMasterRelayService.java', 'LanChildRelayService.java',
             'LanRelayProtocol.java', 'RelayLog.java', 'RelayState.java'):
    q = J / name
    if q.exists(): q.unlink()
q = ROOT / 'app/src/test/java/com/suhas/multyfiautobuy/stable/LanRelayProtocolTest.java'
if q.exists(): q.unlink()

# Update the priority test to standalone terminology.
write(ROOT / 'app/src/test/java/com/suhas/multyfiautobuy/stable/PrimaryExecutionPriorityTest.java', '''package com.suhas.multyfiautobuy.stable;\n\nimport org.junit.Test;\nimport static org.junit.Assert.assertEquals;\nimport static org.junit.Assert.assertTrue;\n\npublic class PrimaryExecutionPriorityTest {\n    @Test public void buyAndSellAreEqualCriticalPriorityAndBeatBackground() {\n        assertTrue(PriorityExecutors.criticalBeatsBackgroundContract());\n        assertEquals(PriorityExecutors.EARLY_EXIT_PRIORITY, PriorityExecutors.ENTRY_PRIORITY);\n        assertTrue(PriorityExecutors.ENTRY_PRIORITY < PriorityExecutors.BACKGROUND_PRIORITY);\n    }\n}\n''')

# Hard build contracts: the shipping app has no relay/role runtime remaining.
for p in (ROOT / 'app/src/main').rglob('*'):
    if p.is_file() and p.suffix in ('.java', '.xml'):
        s = read(p)
        for banned in ('LanMasterRelayService', 'LanChildRelayService', 'RelayState',
                       'AppRole.isChild', 'local-LAN', 'MASTER/CHILD'):
            if banned in s:
                raise RuntimeError(f'banned standalone token {banned} in {p}')

# Preserve the critical v2.4.5/v2.4.6 trading contracts.
service = read(J / 'ProductionNotificationService.java')
parser = read(J / 'SignalParser.java')
priority = read(J / 'PriorityExecutors.java')
assert 'Groww MARKET SELL was called before audit logging.' in service
assert 'Groww order/create was called before audit logging.' in service
assert 'NEW ENTRY BLOCKED — ONE STOCK AT A TIME' in service
assert 'save|protect|secure|lock|take' in parser
assert 'EARLY_EXIT_PRIORITY = -4' in priority and 'ENTRY_PRIORITY = -4' in priority

print('Applied Multyfi AutoBuy v2.4.7 STANDALONE CRITICAL: one APK, no MASTER/CHILD/LAN relay; critical trading path retained')

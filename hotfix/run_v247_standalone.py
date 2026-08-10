#!/usr/bin/env python3
from pathlib import Path
import runpy

runpy.run_path('hotfix/run_v246.py', run_name='__main__')
ROOT=Path('android-stable')
J=ROOT/'app/src/main/java/com/suhas/multyfiautobuy/stable'

def read(p): return Path(p).read_text(encoding='utf-8')
def write(p,s): Path(p).write_text(s,encoding='utf-8')
def repl(p,a,b):
    p=Path(p); t=read(p); n=t.count(a)
    if n!=1: raise RuntimeError(f'{p}: expected 1 match, found {n}: {a[:140]}')
    write(p,t.replace(a,b,1))

# One APK / one local execution engine.
repl(ROOT/'settings.gradle','include(":app")\ninclude(":child")','include(":app")')
repl(ROOT/'app/build.gradle','versionCode 246','versionCode 247')
repl(ROOT/'app/build.gradle',"versionName '2.4.6'","versionName '2.4.7'")

# Remove LAN-only permissions and service declaration.
p=ROOT/'app/src/main/AndroidManifest.xml'; t=read(p)
t=t.replace('    <uses-permission android:name="android.permission.ACCESS_WIFI_STATE" />\n','')
t=t.replace('    <uses-permission android:name="android.permission.CHANGE_WIFI_MULTICAST_STATE" />\n','')
block='''        <service\n            android:name=".LanMasterRelayService"\n            android:exported="false"\n            android:foregroundServiceType="specialUse"\n            android:stopWithTask="false">\n            <property\n                android:name="android.app.PROPERTY_SPECIAL_USE_FGS_SUBTYPE"\n                android:value="Local Wi-Fi/hotspot Multyfi signal relay to paired child phones" />\n        </service>\n\n'''
if block not in t: raise RuntimeError('LAN relay manifest block missing')
write(p,t.replace(block,'',1))

# Local runtime only.
write(J/'AppRuntimeControl.java','''package com.suhas.multyfiautobuy.stable;\n\nimport android.content.ComponentName;\nimport android.content.Context;\nimport android.content.Intent;\nimport android.os.Build;\nimport android.service.notification.NotificationListenerService;\n\nfinal class AppRuntimeControl {\n    private AppRuntimeControl() { }\n    static void sync(Context c) { if (AppPrefs.isArmed(c)) activate(c); else deactivate(c); }\n    static void activate(Context c) {\n        StrategyMonitorService.ensureRunning(c);\n        try { NotificationListenerService.requestRebind(new ComponentName(c, MultyfiNotificationService.class)); }\n        catch (Exception ignored) { }\n    }\n    static void deactivate(Context c) {\n        int active=StrategyStore.activeCount(c);\n        if (Build.VERSION.SDK_INT>=34) {\n            try { NotificationListenerService.requestUnbind(new ComponentName(c, MultyfiNotificationService.class)); }\n            catch (Exception ignored) { }\n        }\n        if (active<=0) c.stopService(new Intent(c,StrategyMonitorService.class));\n        else StrategyMonitorService.ensureRunning(c);\n    }\n}\n''')

# BUY and SELL are equal critical CPU priority; all non-broker work is background.
write(J/'PriorityExecutors.java','''package com.suhas.multyfiautobuy.stable;\n\nimport java.util.concurrent.*;\nimport java.util.concurrent.atomic.AtomicInteger;\n\nfinal class PriorityExecutors {\n    static final int EARLY_EXIT_PRIORITY=-4;\n    static final int ENTRY_PRIORITY=-4;\n    static final int BACKGROUND_PRIORITY=10;\n    private PriorityExecutors() { }\n    static ExecutorService earlyExitSingle(String n){return Executors.newSingleThreadExecutor(factory(n,EARLY_EXIT_PRIORITY));}\n    static ExecutorService entrySingle(String n){return Executors.newSingleThreadExecutor(factory(n,ENTRY_PRIORITY));}\n    static ExecutorService backgroundSingle(String n){return Executors.newSingleThreadExecutor(factory(n,BACKGROUND_PRIORITY));}\n    static ExecutorService backgroundCached(String n){return Executors.newCachedThreadPool(factory(n,BACKGROUND_PRIORITY));}\n    static ScheduledExecutorService backgroundScheduled(String n){return Executors.newSingleThreadScheduledExecutor(factory(n,BACKGROUND_PRIORITY));}\n    static boolean criticalBeatsBackgroundContract(){return EARLY_EXIT_PRIORITY==ENTRY_PRIORITY&&ENTRY_PRIORITY<BACKGROUND_PRIORITY;}\n    private static ThreadFactory factory(String prefix,int priority){\n        AtomicInteger ids=new AtomicInteger();\n        return task->new Thread(()->{try{android.os.Process.setThreadPriority(priority);}catch(Exception ignored){} task.run();},prefix+'-'+ids.incrementAndGet());\n    }\n}\n''')

# Local notification intake only: remove relay fan-out and relayed ingress.
p=J/'ProductionNotificationService.java'; t=read(p)
t=t.replace('Multyfi listener connected for armed MASTER operation.','Multyfi listener connected for standalone execution.')
t=t.replace('Android disconnected the listener; armed MASTER requested an immediate rebind.','Android disconnected the listener; standalone runtime requested an immediate rebind.')
a='''            if (SignalParser.containsEarlyExitPhrase(rawText) || liveTradeHint) earlyExitExecutor.execute(work);\n            else entryExecutor.execute(work);\n            if (!AppRole.isChild(this)) {\n                LanMasterRelayService.publishFast(this, rawText, postTime);\n            }\n'''
b='''            if (SignalParser.containsEarlyExitPhrase(rawText) || liveTradeHint) earlyExitExecutor.execute(work);\n            else entryExecutor.execute(work);\n'''
if a not in t: raise RuntimeError('relay publish block missing')
t=t.replace(a,b,1)
a='''    protected final void enqueueRelayedMultyfi(String rawText, long postTime) {\n        Runnable work = () -> process(rawText, postTime);\n        if (SignalParser.containsEarlyExitPhrase(rawText) || liveTradeHint) earlyExitExecutor.execute(work);\n        else entryExecutor.execute(work);\n    }\n\n'''
if a not in t: raise RuntimeError('relayed intake method missing')
write(p,t.replace(a,'',1))

# Standalone dashboard/readiness.
p=J/'ProductionActivity.java'; t=read(p)
a='''        if (!AppRole.isChild(this)) {\n            try {\n                NotificationListenerService.requestRebind(\n                        new ComponentName(this, MultyfiNotificationService.class));\n            } catch (Exception ignored) { }\n        }\n'''
b='''        try {\n            NotificationListenerService.requestRebind(\n                    new ComponentName(this, MultyfiNotificationService.class));\n        } catch (Exception ignored) { }\n'''
if a not in t: raise RuntimeError('role-dependent rebind missing')
t=t.replace(a,b,1)
a='''        TextView eyebrow = label(AppRole.isChild(this) ? "PRIVATE LG G7 CHILD CONSOLE" : "PRIVATE S24 EXECUTION CONSOLE", 12, GREEN, true);\n        eyebrow.setLetterSpacing(0.12f);\n        root.addView(eyebrow);\n        TextView title = label(AppRole.isChild(this) ? "Multyfi AutoBuy CHILD" : "Multyfi AutoBuy MASTER", 30, TEXT, true);\n        root.addView(title, topMargin(4));\n        String release = installedVersionName();\n        TextView subtitle = label(AppRole.isChild(this)\n                ? "LG G7 ThinQ • local-LAN child • release " + release\n                : "Galaxy S24 Ultra • local-LAN master • release " + release,\n                14, MUTED, false);\n'''
b='''        TextView eyebrow = label("PRIVATE STANDALONE EXECUTION CONSOLE", 12, GREEN, true);\n        eyebrow.setLetterSpacing(0.12f);\n        root.addView(eyebrow);\n        TextView title = label("Multyfi AutoBuy", 30, TEXT, true);\n        root.addView(title, topMargin(4));\n        String release = installedVersionName();\n        TextView subtitle = label("Standalone local execution • release " + release, 14, MUTED, false);\n'''
if a not in t: raise RuntimeError('role dashboard header missing')
t=t.replace(a,b,1)
a='''        if (!AppRole.isChild(this)) {\n            Button openAccess = secondaryButton("OPEN NOTIFICATION ACCESS");\n            openAccess.setOnClickListener(v -> openSetting(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS));\n            networkCard.addView(openAccess, topMargin(10));\n        }\n'''
b='''        Button openAccess = secondaryButton("OPEN NOTIFICATION ACCESS");\n        openAccess.setOnClickListener(v -> openSetting(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS));\n        networkCard.addView(openAccess, topMargin(10));\n'''
if a not in t: raise RuntimeError('role notification access block missing')
t=t.replace(a,b,1)
t=t.replace('"Auto-Buy OFF by default • GROSS loss -₹2,000 • no daily profit cap • local LAN relay • v"\n                        + release,','"Auto-Buy OFF by default • GROSS loss -₹2,000 • no daily profit cap • standalone • v"\n                        + release,')
t=t.replace('Background monitor and local LAN relay enabled','Standalone notification listener and position monitor enabled')
t=t.replace('''            AppPrefs.log(this, "HARD OFF BY USER",\n                    "Trading monitor, MASTER/CHILD LAN relay and Multyfi listener runtime are stopped. No background relay connection remains.");\n            TradeEventNotifier.notifyTradingOff(this, "Application hard-off: trading and LAN relay stopped.");\n''','''            AppPrefs.log(this, "HARD OFF BY USER",\n                    "Standalone trading monitor and Multyfi listener runtime are stopped.");\n            TradeEventNotifier.notifyTradingOff(this, "Application hard-off: standalone trading stopped.");\n''')
a='''        boolean notificationReady = AppRole.isChild(this)\n                ? RelayState.childConnected(this) : hasNotificationAccess();\n'''
if a not in t: raise RuntimeError('role notification readiness missing')
t=t.replace(a,'        boolean notificationReady = hasNotificationAccess();\n',1)
a='''        if (!persistentlyArmed) {\n            notificationStatus.setText("● Runtime OFF: local MASTER/CHILD relay stopped");\n            notificationStatus.setTextColor(MUTED);\n        } else {\n            notificationStatus.setText(AppRole.isChild(this)\n                    ? (notificationReady\n                        ? "● Master LAN relay: connected • " + RelayState.masterIp(this)\n                            + " • last " + Math.max(0, RelayState.latency(this)) + " ms"\n                        : "● Master LAN relay: disconnected — hotspot/Wi-Fi gateway auto-retrying")\n                    : (notificationReady\n                        ? "● Notification listener: connected • LAN children "\n                            + RelayState.masterChildren(this)\n                        : "● Notification listener: reconnecting"));\n            notificationStatus.setTextColor(notificationReady ? GREEN : AMBER);\n        }\n'''
b='''        if (!persistentlyArmed) {\n            notificationStatus.setText("● Runtime OFF: notification listener stopped");\n            notificationStatus.setTextColor(MUTED);\n        } else {\n            notificationStatus.setText(notificationReady\n                    ? "● Notification listener: connected • standalone execution"\n                    : "● Notification listener: reconnecting");\n            notificationStatus.setTextColor(notificationReady ? GREEN : AMBER);\n        }\n'''
if a not in t: raise RuntimeError('relay status block missing')
t=t.replace(a,b,1)
t=t.replace('Hard OFF • trading monitor stopped • local MASTER/CHILD relay stopped • no Multyfi background processing.','Hard OFF • standalone trading monitor stopped • no Multyfi background processing.')
a='''        if (AppRole.isChild(this) && !RelayState.childConnected(this)) return "Waiting for local-LAN connection to MASTER";\n        if (!AppRole.isChild(this) && !hasNotificationAccess()) return "Grant Notification Access to Multyfi AutoBuy MASTER";\n'''
if a not in t: raise RuntimeError('relay readiness gates missing')
t=t.replace(a,'        if (!hasNotificationAccess()) return "Grant Notification Access to Multyfi AutoBuy";\n',1)
write(p,t)

# Delete relay/role code and relay test from the only shipping module.
for name in ('AppRole.java','LanMasterRelayService.java','LanChildRelayService.java','LanRelayProtocol.java','RelayLog.java','RelayState.java'):
    q=J/name
    if q.exists(): q.unlink()
q=ROOT/'app/src/test/java/com/suhas/multyfiautobuy/stable/LanRelayProtocolTest.java'
if q.exists(): q.unlink()
write(ROOT/'app/src/test/java/com/suhas/multyfiautobuy/stable/PrimaryExecutionPriorityTest.java','''package com.suhas.multyfiautobuy.stable;\nimport org.junit.Test;\nimport static org.junit.Assert.*;\npublic class PrimaryExecutionPriorityTest {\n @Test public void criticalTradingBeatsBackground(){\n  assertTrue(PriorityExecutors.criticalBeatsBackgroundContract());\n  assertEquals(PriorityExecutors.EARLY_EXIT_PRIORITY,PriorityExecutors.ENTRY_PRIORITY);\n  assertTrue(PriorityExecutors.ENTRY_PRIORITY<PriorityExecutors.BACKGROUND_PRIORITY);\n }\n}\n''')

# Build contracts: no shipping LAN architecture; critical trading path retained.
for p in (ROOT/'app/src/main').rglob('*'):
    if p.is_file() and p.suffix in ('.java','.xml'):
        s=read(p)
        for banned in ('LanMasterRelayService','LanChildRelayService','RelayState','AppRole.isChild','local-LAN','MASTER/CHILD'):
            if banned in s: raise RuntimeError(f'banned standalone token {banned} in {p}')
service=read(J/'ProductionNotificationService.java')
parser=read(J/'SignalParser.java')
assert 'Groww MARKET SELL was called before audit logging.' in service
assert 'Groww order/create was called before audit logging.' in service
assert 'NEW ENTRY BLOCKED — ONE STOCK AT A TIME' in service
assert 'save|protect|secure|lock|take' in parser
assert 'versionCode 247' in read(ROOT/'app/build.gradle')
assert "versionName '2.4.7'" in read(ROOT/'app/build.gradle')
assert 'installedVersionName()' in read(J/'ProductionActivity.java')
print('Applied v2.4.7 standalone critical execution: one APK, no MASTER/CHILD/LAN relay')

#!/usr/bin/env python3
from pathlib import Path
import runpy

# Start from the exact validated v2.4.9 fresh-install source.
# This release changes ONLY notification-listener health/rebind lifecycle plus version/package identity.
runpy.run_path('hotfix/run_v249_fresh_signed.py', run_name='__main__')

ROOT = Path('android-stable')
APP = ROOT / 'app'
J = APP / 'src/main/java/com/suhas/multyfiautobuy/stable'


def read(p):
    return Path(p).read_text(encoding='utf-8')


def write(p, s):
    Path(p).write_text(s, encoding='utf-8')


def replace_once(p, old, new):
    p = Path(p)
    text = read(p)
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f'{p}: expected exactly one match, found {count}: {old[:180]}')
    write(p, text.replace(old, new, 1))

# Version + distinct fresh-install package identity.
replace_once(APP/'build.gradle', 'versionCode 249', 'versionCode 250')
replace_once(APP/'build.gradle', "versionName '2.4.9'", "versionName '2.4.10'")
replace_once(APP/'build.gradle',
             "applicationId 'com.suhas.multyfiautobuy.v249fresh'",
             "applicationId 'com.suhas.multyfiautobuy.v2410fresh'")
replace_once(APP/'src/main/res/values/strings.xml',
             '<string name="app_name">Multyfi AutoBuy 2.4.9</string>',
             '<string name="app_name">Multyfi AutoBuy 2.4.10</string>')

# BUG FIX 1: requestRebindNow must never manufacture a disconnected state.
# In v2.4.9 it set connected=false even when Android had a healthy bound listener.
health = J/'NotificationListenerHealth.java'
replace_once(health,
'''    static void requestRebindNow(Context context) {\n        connected = false;\n        lastRebindAttemptAt = 0L;\n        ensureBound(context);\n    }\n''',
'''    static void requestRebindNow(Context context) {\n        // Only an actual lifecycle callback may mark the listener disconnected.\n        // If Android is already bound, do nothing; never create a false-negative health state.\n        if (connected) return;\n        lastRebindAttemptAt = 0L;\n        ensureBound(context);\n    }\n''')

# BUG FIX 2: resuming the dashboard must be a passive health check, not a forced rebind.
activity = J/'ProductionActivity.java'
replace_once(activity,
'''        NotificationListenerHealth.requestRebindNow(this);\n        AppRuntimeControl.sync(this);\n''',
'''        NotificationListenerHealth.ensureBound(this);\n        AppRuntimeControl.sync(this);\n''')

# BUG FIX 3: normal runtime activation must preserve a healthy existing listener.
runtime = J/'AppRuntimeControl.java'
replace_once(runtime,
'''        StrategyMonitorService.ensureRunning(c);\n        NotificationListenerHealth.requestRebindNow(c);\n''',
'''        StrategyMonitorService.ensureRunning(c);\n        NotificationListenerHealth.ensureBound(c);\n''')

# Actual Android disconnect handling remains unchanged:
# onListenerDisconnected() marks false, then requestRebindNow() requests immediate recovery.
# BUY, SELL, target/SL watcher, stale-state cleanup, Groww endpoints and direct early-exit path are untouched.

print('Applied v2.4.10 listener-stability fix + fresh-install package identity')

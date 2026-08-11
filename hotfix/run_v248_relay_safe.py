#!/usr/bin/env python3
from pathlib import Path
import runpy

# Return to the validated v2.4.6 MASTER/CHILD architecture. This is intentional:
# the CHILD receives authenticated Multyfi signal data over the local LAN/hotspot
# and therefore does NOT need Android Notification Listener access itself.
runpy.run_path('hotfix/run_v246.py', run_name='__main__')

ROOT = Path('android-stable')

def read(p): return Path(p).read_text(encoding='utf-8')
def write(p,s): Path(p).write_text(s,encoding='utf-8')
def repl(p,a,b):
    p=Path(p); t=read(p); n=t.count(a)
    if n != 1:
        raise RuntimeError(f'{p}: expected one match, found {n}: {a!r}')
    write(p,t.replace(a,b,1))

# Version both paired APKs together so protocol/runtime remains aligned.
for module in ('app','child'):
    g=ROOT/module/'build.gradle'
    repl(g,'versionCode 246','versionCode 248')
    repl(g,"versionName '2.4.6'","versionName '2.4.8'")

# CHILD must remain install-safe for browser/file-manager delivery: no
# NotificationListenerService declaration and no BIND_NOTIFICATION_LISTENER_SERVICE.
child_manifest = ROOT/'child/src/main/AndroidManifest.xml'
cm = read(child_manifest)
if 'android.permission.BIND_NOTIFICATION_LISTENER_SERVICE' in cm:
    raise RuntimeError('CHILD unexpectedly declares BIND_NOTIFICATION_LISTENER_SERVICE')
if 'MultyfiNotificationService' in cm:
    raise RuntimeError('CHILD unexpectedly declares local Multyfi notification listener')

# MASTER remains the only notification-intake device and keeps the local relay.
master_manifest = read(ROOT/'app/src/main/AndroidManifest.xml')
if 'MultyfiNotificationService' not in master_manifest:
    raise RuntimeError('MASTER notification listener missing')
if 'LanMasterRelayService' not in master_manifest:
    raise RuntimeError('MASTER LAN relay missing')
if 'LanChildRelayService' not in cm:
    raise RuntimeError('CHILD LAN relay service missing')

# Preserve the validated single-stock critical trading path on both devices.
for module in ('app','child'):
    j=ROOT/module/'src/main/java/com/suhas/multyfiautobuy/stable'
    service=read(j/'ProductionNotificationService.java')
    priority=read(j/'PriorityExecutors.java')
    parser=read(j/'SignalParser.java')
    assert 'Groww MARKET SELL was called before audit logging.' in service
    assert 'Groww order/create was called before audit logging.' in service
    assert 'EARLY_EXIT_PRIORITY == ENTRY_PRIORITY' in priority
    assert 'NEW ENTRY BLOCKED — ONE STOCK AT A TIME' in service
    assert 'save|protect|secure|lock|take' in parser

assert 'versionCode 248' in read(ROOT/'app/build.gradle')
assert 'versionCode 248' in read(ROOT/'child/build.gradle')
assert "versionName '2.4.8'" in read(ROOT/'app/build.gradle')
assert "versionName '2.4.8'" in read(ROOT/'child/build.gradle')

print('Applied Multyfi AutoBuy v2.4.8 relay install-safe build: MASTER notification intake + CHILD LAN execution, no CHILD notification-listener permission')

#!/usr/bin/env python3
from pathlib import Path
import runpy, re

# Start from the validated v2.4.6 build. Trading logic is intentionally retained;
# v2.4.7 removes the MASTER/CHILD relay architecture from runtime completely.
runpy.run_path('hotfix/run_v246.py', run_name='__main__')

ROOT = Path('android-stable')
APP = ROOT / 'app'
JAVA = APP / 'src/main/java/com/suhas/multyfiautobuy/stable'


def read(p): return Path(p).read_text(encoding='utf-8')
def write(p, s): Path(p).write_text(s, encoding='utf-8')
def replace_once(p, old, new):
    p = Path(p); t = read(p); n = t.count(old)
    if n != 1: raise RuntimeError(f'{p}: expected one match, found {n}: {old[:160]}')
    write(p, t.replace(old, new, 1))

# One normal standalone APK, versionCode 247.
gradle = APP / 'build.gradle'
replace_once(gradle, 'versionCode 246', 'versionCode 247')
replace_once(gradle, "versionName '2.4.6'", "versionName '2.4.7'")

# Hard-disable every relay entry point. Even if an old lifecycle call survives somewhere,
# these methods cannot start services, sockets, discovery, heartbeats, or background relay work.
write(JAVA / 'LanMasterRelayService.java', r'''package com.suhas.multyfiautobuy.stable;

import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.os.IBinder;

/** v2.4.7: legacy compatibility shell. MASTER/CHILD relay is permanently disabled. */
public final class LanMasterRelayService extends Service {
    static void ensureRunning(Context c) { }
    static void publishAsync(Context c, String raw, long post) { }
    static void publishFast(Context c, String raw, long post) { }
    @Override public int onStartCommand(Intent i, int flags, int startId) { stopSelf(); return START_NOT_STICKY; }
    @Override public IBinder onBind(Intent i) { return null; }
}
''')

# Remove relay calls from the hot trading/lifecycle source wherever they appear.
for p in JAVA.glob('*.java'):
    if p.name == 'LanMasterRelayService.java':
        continue
    t = read(p)
    original = t
    t = re.sub(r'^\s*LanMasterRelayService\.(?:ensureRunning|publishAsync|publishFast)\([^;]*;\s*\n?', '', t, flags=re.M)
    t = re.sub(r'^\s*LanChildRelayService\.ensureRunning\([^;]*;\s*\n?', '', t, flags=re.M)
    if t != original:
        write(p, t)

# Standalone identity in the dashboard. Version stays dynamic from package metadata.
activity = JAVA / 'ProductionActivity.java'
t = read(activity)
old = '''        String release = BuildConfig.VERSION_NAME;\n        TextView subtitle = label(AppRole.isChild(this)\n                ? "LG G7 ThinQ • local-LAN child • release " + release\n                : "Galaxy S24 Ultra • local-LAN master • release " + release,\n                14, MUTED, false);'''
new = '''        String release = BuildConfig.VERSION_NAME;\n        TextView subtitle = label("Standalone phone • direct Multyfi → Groww • release " + release,\n                14, MUTED, false);'''
if old in t:
    t = t.replace(old, new, 1)
else:
    # Fail loudly if the prior UI structure unexpectedly changes.
    raise RuntimeError('ProductionActivity subtitle contract not found')

t = t.replace(' • local LAN relay • v"\n                        + BuildConfig.VERSION_NAME,',
              ' • standalone direct execution • v"\n                        + BuildConfig.VERSION_NAME,')
t = t.replace('Hard OFF • trading monitor stopped • local MASTER/CHILD relay stopped • no Multyfi background processing.',
              'Hard OFF • trading monitor stopped • no Multyfi background processing.')
t = t.replace('Runtime OFF: local MASTER/CHILD relay stopped', 'Runtime OFF: standalone trading engine stopped')
t = t.replace('local-LAN master', 'standalone')
t = t.replace('local-LAN child', 'standalone')
t = t.replace('LAN children', 'Standalone mode')
t = t.replace('MASTER/CHILD relay', 'legacy relay disabled')
write(activity, t)

# Runtime contract checks: no relay launch/publish call may remain outside the disabled shell.
for p in JAVA.glob('*.java'):
    if p.name == 'LanMasterRelayService.java':
        continue
    s = read(p)
    assert 'LanMasterRelayService.ensureRunning(' not in s, p
    assert 'LanMasterRelayService.publishAsync(' not in s, p
    assert 'LanMasterRelayService.publishFast(' not in s, p
    assert 'LanChildRelayService.ensureRunning(' not in s, p

# Critical v2.4.5/v2.4.6 BUY/SELL contracts must remain intact.
service = read(JAVA / 'ProductionNotificationService.java')
priority = read(JAVA / 'PriorityExecutors.java')
parser = read(JAVA / 'SignalParser.java')
assert 'Groww MARKET SELL was called before audit logging.' in service
assert 'Groww order/create was called before audit logging.' in service
assert 'NEW ENTRY BLOCKED — ONE STOCK AT A TIME' in service
assert 'EARLY_EXIT_PRIORITY == ENTRY_PRIORITY' in priority
assert 'save|protect|secure|lock|take' in parser
assert "versionCode 247" in read(gradle)
assert "versionName '2.4.7'" in read(gradle)
assert 'Standalone phone • direct Multyfi → Groww • release ' in read(activity)
assert 'BuildConfig.VERSION_NAME' in read(activity)

print('Applied Multyfi AutoBuy v2.4.7 STANDALONE: all MASTER/CHILD relay runtime removed; direct trading path retained')

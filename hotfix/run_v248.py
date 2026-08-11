#!/usr/bin/env python3
from pathlib import Path
import runpy

# Start from the validated v2.4.6 MASTER/CHILD release.  The important
# architectural rule for v2.4.8 is deliberate: only MASTER may declare the
# Android notification-listener service.  CHILD receives authenticated local
# relay messages and therefore does not need the sensitive notification-listener
# permission/service that triggers Play Protect enhanced fraud protection for
# Internet-sideloaded APKs in supported markets.
runpy.run_path('hotfix/run_v246.py', run_name='__main__')

ROOT = Path('android-stable')


def read(path):
    return Path(path).read_text(encoding='utf-8')


def write(path, text):
    Path(path).write_text(text, encoding='utf-8')


def replace_once(path, old, new):
    path = Path(path)
    text = read(path)
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f'{path}: expected one match, found {count}: {old!r}')
    write(path, text.replace(old, new, 1))

# Bump both packages together so MASTER and CHILD present one matched release.
for module in ('app', 'child'):
    gradle = ROOT / module / 'build.gradle'
    replace_once(gradle, 'versionCode 246', 'versionCode 248')
    replace_once(gradle, "versionName '2.4.6'", "versionName '2.4.8'")

# Contract checks: CHILD must stay free of sensitive Notification Listener and
# Accessibility/SMS declarations.  MASTER retains Notification Listener because
# it is the one phone that consumes Multyfi notifications and relays the signal.
master_manifest = read(ROOT / 'app/src/main/AndroidManifest.xml')
child_manifest = read(ROOT / 'child/src/main/AndroidManifest.xml')

assert 'android.permission.BIND_NOTIFICATION_LISTENER_SERVICE' in master_manifest
assert 'MultyfiNotificationService' in master_manifest

for forbidden in (
    'android.permission.BIND_NOTIFICATION_LISTENER_SERVICE',
    'MultyfiNotificationService',
    'android.permission.READ_SMS',
    'android.permission.RECEIVE_SMS',
    'android.accessibilityservice.AccessibilityService',
    'android.permission.BIND_ACCESSIBILITY_SERVICE',
):
    assert forbidden not in child_manifest, f'CHILD still declares sensitive capability: {forbidden}'

# Preserve known-good CHILD package identity / G7 compatibility and relay path.
child_gradle = read(ROOT / 'child/build.gradle')
assert "applicationId 'com.suhas.multyfiautobuy.child'" in child_gradle
assert 'minSdk 26' in child_gradle
assert 'versionCode 248' in child_gradle
assert "versionName '2.4.8'" in child_gradle
assert 'LanChildRelayService' in child_manifest

master_gradle = read(ROOT / 'app/build.gradle')
assert "applicationId 'com.suhas.multyfiautobuy.stable'" in master_gradle
assert 'versionCode 248' in master_gradle
assert "versionName '2.4.8'" in master_gradle

print('Applied Multyfi AutoBuy v2.4.8 Play-Protect-safe CHILD: MASTER owns Notification Access; CHILD uses authenticated local relay only')

#!/usr/bin/env python3
from pathlib import Path
import runpy

# Build the exact validated v2.4.9 reliability/protection source first.
runpy.run_path('hotfix/run_v249.py', run_name='__main__')

ROOT = Path('android-stable')
APP = ROOT / 'app'


def read(p):
    return Path(p).read_text(encoding='utf-8')


def write(p, s):
    Path(p).write_text(s, encoding='utf-8')


def replace_once(p, old, new):
    p = Path(p)
    text = read(p)
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f'{p}: expected exactly one match, found {count}: {old}')
    write(p, text.replace(old, new, 1))

# This build is intentionally installable as a separate Android application.
# Keep the Java namespace/classes unchanged and only give the APK a distinct applicationId.
replace_once(APP/'build.gradle',
             "applicationId 'com.suhas.multyfiautobuy.stable'",
             "applicationId 'com.suhas.multyfiautobuy.v249fresh'")

# Because the final manifest package is now the fresh applicationId, make component class
# names explicit so Android launches the existing compiled Java classes correctly.
manifest = APP/'src/main/AndroidManifest.xml'
text = read(manifest)
for short, full in {
    'android:name=".MainActivity"': 'android:name="com.suhas.multyfiautobuy.stable.MainActivity"',
    'android:name=".MultyfiNotificationService"': 'android:name="com.suhas.multyfiautobuy.stable.MultyfiNotificationService"',
    'android:name=".StrategyMonitorService"': 'android:name="com.suhas.multyfiautobuy.stable.StrategyMonitorService"',
    'android:name=".BootReceiver"': 'android:name="com.suhas.multyfiautobuy.stable.BootReceiver"',
}.items():
    if text.count(short) != 1:
        raise RuntimeError(f'{manifest}: expected one component match for {short}')
    text = text.replace(short, full, 1)
write(manifest, text)

# Make the fresh install visually distinguishable from any older installed copy.
strings = APP/'src/main/res/values/strings.xml'
text = read(strings)
if '<string name="app_name">Multyfi AutoBuy</string>' not in text:
    raise RuntimeError('expected normalized v2.4.9 app_name')
text = text.replace('<string name="app_name">Multyfi AutoBuy</string>',
                    '<string name="app_name">Multyfi AutoBuy 2.4.9</string>', 1)
write(strings, text)

print('Applied v2.4.9 fresh-install package identity: com.suhas.multyfiautobuy.v249fresh')

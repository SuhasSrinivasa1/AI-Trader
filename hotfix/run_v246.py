#!/usr/bin/env python3
from pathlib import Path
import runpy

# Build directly on the validated v2.4.5 single-stock critical-path release.
# Trading logic is intentionally unchanged in v2.4.6. This rebuild fixes release
# identity presentation permanently by reading the version embedded in the installed APK.
runpy.run_path('hotfix/run_v245.py', run_name='__main__')

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
        raise RuntimeError(f'{path}: expected one match, found {count}: {old[:180]}')
    write(path, text.replace(old, new, 1))


# Real package identity. Increment versionCode so Android treats this as a clean
# in-place update over the installed v2.4.5 package when signed with the same key.
for module in ('app', 'child'):
    gradle = ROOT / module / 'build.gradle'
    replace_once(gradle, 'versionCode 245', 'versionCode 246')
    replace_once(gradle, "versionName '2.4.5'", "versionName '2.4.6'")

    activity = ROOT / module / 'src/main/java/com/suhas/multyfiautobuy/stable/ProductionActivity.java'

    # Never hard-code the release number again. The dashboard reads the versionName
    # from PackageManager, i.e. from the APK Android is actually executing.
    replace_once(
        activity,
        '        TextView subtitle = label(AppRole.isChild(this) ? "LG G7 ThinQ • local-LAN child • release 2.4.4" : "Galaxy S24 Ultra • local-LAN master • release 2.4.4", 14, MUTED, false);',
        '        String release = installedVersionName();\n'
        '        TextView subtitle = label(AppRole.isChild(this)\n'
        '                ? "LG G7 ThinQ • local-LAN child • release " + release\n'
        '                : "Galaxy S24 Ultra • local-LAN master • release " + release,\n'
        '                14, MUTED, false);'
    )

    replace_once(
        activity,
        '                "Auto-Buy OFF by default • GROSS loss -₹2,000 • no daily profit cap • local LAN relay • v2.4.4",',
        '                "Auto-Buy OFF by default • GROSS loss -₹2,000 • no daily profit cap • local LAN relay • v"\n'
        '                        + release,'
    )

    # Central runtime version reader. This avoids generated BuildConfig dependencies
    # and guarantees the visible label follows the package metadata installed by Android.
    replace_once(
        activity,
        '    private void loadSavedState() {',
        '''    private String installedVersionName() {\n        try {\n            String value = getPackageManager()\n                    .getPackageInfo(getPackageName(), 0).versionName;\n            return value == null || value.trim().isEmpty() ? "unknown" : value.trim();\n        } catch (Exception ignored) {\n            return "unknown";\n        }\n    }\n\n    private void loadSavedState() {'''
    )

# Build-time contracts: package metadata and visible UI must agree, and no stale
# hard-coded 2.4.4 version label may remain in either production dashboard.
for module in ('app', 'child'):
    gradle = read(ROOT / module / 'build.gradle')
    activity = read(ROOT / module / 'src/main/java/com/suhas/multyfiautobuy/stable/ProductionActivity.java')
    assert 'versionCode 246' in gradle
    assert "versionName '2.4.6'" in gradle
    assert 'installedVersionName()' in activity
    assert 'getPackageInfo(getPackageName(), 0).versionName' in activity
    assert 'release 2.4.4' not in activity
    assert '• v2.4.4' not in activity
    assert 'BuildConfig.VERSION_NAME' not in activity

# Preserve the v2.4.5 critical-path contracts unchanged.
for module in ('app', 'child'):
    java = ROOT / module / 'src/main/java/com/suhas/multyfiautobuy/stable'
    service = read(java / 'ProductionNotificationService.java')
    priority = read(java / 'PriorityExecutors.java')
    parser = read(java / 'SignalParser.java')
    assert 'Groww MARKET SELL was called before audit logging.' in service
    assert 'Groww order/create was called before audit logging.' in service
    assert 'EARLY_EXIT_PRIORITY == ENTRY_PRIORITY' in priority
    assert 'save|protect|secure|lock|take' in parser

print('Applied Multyfi AutoBuy v2.4.6 perfect rebuild: APK-derived UI version + v2.4.5 critical path preserved')

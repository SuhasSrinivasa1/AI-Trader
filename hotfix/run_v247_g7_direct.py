#!/usr/bin/env python3
from pathlib import Path
import runpy

# Start from the validated v2.4.7 standalone trading engine.
runpy.run_path('hotfix/run_v247_standalone.py', run_name='__main__')

ROOT = Path('android-stable')
G = ROOT / 'app/build.gradle'
S = ROOT / 'app/src/main/res/values/strings.xml'
A = ROOT / 'app/src/main/java/com/suhas/multyfiautobuy/stable/ProductionActivity.java'

def replace_once(path, old, new):
    p = Path(path)
    text = p.read_text(encoding='utf-8')
    if text.count(old) != 1:
        raise RuntimeError(f'{p}: expected exactly one match for {old!r}')
    p.write_text(text.replace(old, new, 1), encoding='utf-8')

# Use the same application identity that the previously installable LG G7 CHILD
# builds used. This allows a normal tap-to-install update over the old G7 child
# installation while retaining the NEW standalone v2.4.7 execution engine.
replace_once(G, "applicationId 'com.suhas.multyfiautobuy.stable'", "applicationId 'com.suhas.multyfiautobuy.child'")
replace_once(G, 'minSdk 28', 'minSdk 26')

# Remove stale MASTER wording from the Android launcher label and make the
# standalone G7 identity explicit in the dashboard.
replace_once(S, '<string name="app_name">Multyfi AutoBuy MASTER</string>', '<string name="app_name">Multyfi AutoBuy</string>')
replace_once(A, 'TextView subtitle = label("Standalone local execution • release " + release, 14, MUTED, false);',
             'TextView subtitle = label("LG G7 ThinQ • standalone local execution • release " + release, 14, MUTED, false);')

# Android API 26 does not provide NotificationManager.isNotificationListenerAccessGranted.
# Use the modern API on API 27+, and the Android secure enabled-listener setting on API 26.
# This keeps the standalone listener/readiness gate functional on older LG firmware instead
# of merely suppressing lint or raising the minSdk again.
replace_once(A,
'''    private boolean hasNotificationAccess() {
        NotificationManager manager = (NotificationManager) getSystemService(NOTIFICATION_SERVICE);
        return manager != null && manager.isNotificationListenerAccessGranted(
                new ComponentName(this, MultyfiNotificationService.class));
    }
''',
'''    private boolean hasNotificationAccess() {
        ComponentName listener = new ComponentName(this, MultyfiNotificationService.class);
        if (Build.VERSION.SDK_INT >= 27) {
            NotificationManager manager = (NotificationManager) getSystemService(NOTIFICATION_SERVICE);
            return manager != null && manager.isNotificationListenerAccessGranted(listener);
        }
        String enabled = Settings.Secure.getString(
                getContentResolver(), "enabled_notification_listeners");
        if (enabled == null || enabled.isEmpty()) return false;
        String target = listener.flattenToString();
        for (String item : enabled.split(":")) {
            if (target.equals(item)) return true;
        }
        return false;
    }
''')

# Contracts: standalone behavior stays intact; only Android packaging/compatibility
# changes for the G7 direct-install variant.
gradle = G.read_text(encoding='utf-8')
activity = A.read_text(encoding='utf-8')
manifest = (ROOT / 'app/src/main/AndroidManifest.xml').read_text(encoding='utf-8')
assert "applicationId 'com.suhas.multyfiautobuy.child'" in gradle
assert 'minSdk 26' in gradle
assert 'versionCode 247' in gradle
assert "versionName '2.4.7'" in gradle
assert 'LG G7 ThinQ • standalone local execution' in activity
assert 'Build.VERSION.SDK_INT >= 27' in activity
assert 'enabled_notification_listeners' in activity
assert '.MultyfiNotificationService' in manifest
for banned in ('LanMasterRelayService', 'LanChildRelayService', 'RelayState', 'AppRole.isChild'):
    assert banned not in activity

print('Applied v2.4.7 LG G7 DIRECT STANDALONE packaging: child app identity + minSdk26 + API26-safe notification listener check; standalone trading engine retained')

#!/usr/bin/env python3
from pathlib import Path
import runpy

runpy.run_path("hotfix/run_v240_fix4.py", run_name="__main__")
ROOT = Path("android-stable")
child_activity = ROOT / "child/src/main/java/com/suhas/multyfiautobuy/stable/ProductionActivity.java"
text = child_activity.read_text(encoding="utf-8")
old = '''    private boolean hasNotificationAccess() {
        NotificationManager manager = (NotificationManager) getSystemService(NOTIFICATION_SERVICE);
        return manager != null && manager.isNotificationListenerAccessGranted(
                new ComponentName(this, MultyfiNotificationService.class));
    }
'''
new = '''    private boolean hasNotificationAccess() {
        // CHILD never consumes Multyfi notifications locally; its intake is the
        // authenticated LAN relay. Keep API 26 compatibility for older LG G7
        // firmware and avoid calling the API-27 notification-listener helper.
        if (AppRole.isChild(this)) return RelayState.childConnected(this);
        if (android.os.Build.VERSION.SDK_INT < 27) return false;
        NotificationManager manager = (NotificationManager) getSystemService(NOTIFICATION_SERVICE);
        return manager != null && manager.isNotificationListenerAccessGranted(
                new ComponentName(this, MultyfiNotificationService.class));
    }
'''
count = text.count(old)
if count != 1:
    raise RuntimeError(f"Expected one child notification-access method, found {count}")
child_activity.write_text(text.replace(old, new, 1), encoding="utf-8")
assert "android.os.Build.VERSION.SDK_INT < 27" in child_activity.read_text(encoding="utf-8")
print("Applied v2.4.0 API-26-safe CHILD notification-access guard")

#!/usr/bin/env python3
from pathlib import Path
import runpy

runpy.run_path("hotfix/run_v241_fix.py", run_name="__main__")
ROOT = Path("android-stable")


def patch(path: Path, old: str, new: str, expected: int = 1) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != expected:
        raise RuntimeError(f"Expected {expected} matches in {path}, found {count}: {old[:180]}")
    path.write_text(text.replace(old, new, expected), encoding="utf-8")

for module in ("app", "child"):
    java = ROOT / module / "src/main/java/com/suhas/multyfiautobuy/stable"

    runtime = java / "AppRuntimeControl.java"
    patch(runtime,
          '''        if (!AppRole.isChild(c) && Build.VERSION.SDK_INT >= 24) {
            try { NotificationListenerService.requestUnbind(new ComponentName(c, MultyfiNotificationService.class)); }
            catch (Exception ignored) { }
        }
''',
          '''        if (!AppRole.isChild(c) && Build.VERSION.SDK_INT >= 34) {
            try { NotificationListenerService.requestUnbind(new ComponentName(c, MultyfiNotificationService.class)); }
            catch (Exception ignored) { }
        }
''')

    listener = java / "ProductionNotificationService.java"
    patch(listener,
          '''        if (!AppPrefs.isArmed(this)) {
            try { requestUnbind(new android.content.ComponentName(this, MultyfiNotificationService.class)); }
            catch (Exception ignored) { }
            return;
        }
''',
          '''        if (!AppPrefs.isArmed(this)) {
            try { requestUnbind(); }
            catch (Exception ignored) { }
            return;
        }
''')

    assert "Build.VERSION.SDK_INT >= 34" in runtime.read_text(encoding="utf-8")
    assert "try { requestUnbind(); }" in listener.read_text(encoding="utf-8")

print("Applied v2.4.1 API-safe notification-listener hard-off fix")

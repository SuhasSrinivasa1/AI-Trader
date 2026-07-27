#!/usr/bin/env python3
from pathlib import Path
import runpy
import tempfile

source = Path("hotfix/apply_v211.py").read_text(encoding="utf-8")
old = '''old_reject = \'\'\'    private void rejectAndDisarm(String reason, String summary) {
        AppPrefs.log(this, "REJECTED — ARMED, WAITING FOR GATE",
                summary + "\\n" + reason
                        + " Armed state remains ON; this notification was not submitted.");
    }\'\'\'
new_reject = \'\'\'    private void rejectAndDisarm(String reason, String summary) {
        AppPrefs.log(this, "REJECTED — ARMED, WAITING FOR GATE",
                summary + "\\n" + reason
                        + " Armed state remains ON; this notification was not submitted.");
        UserAlertNotifier.notifyAutoBuyUnavailable(this,
                "entry_gate_" + Integer.toHexString(reason.hashCode()), reason);
    }\'\'\'
if old_reject not in text:
    raise RuntimeError("Could not add gate alert to ProductionNotificationService")
text = text.replace(old_reject, new_reject, 1)'''
new = '''reject_pattern = re.compile(
    r"    private void rejectAndDisarm\\(String reason, String summary\\) \\{.*?\\n    \\}",
    re.S,
)
new_reject = \'\'\'    private void rejectAndDisarm(String reason, String summary) {
        AppPrefs.log(this, "REJECTED — ARMED, WAITING FOR GATE",
                summary + "\\\\n" + reason
                        + " Armed state remains ON; this notification was not submitted.");
        UserAlertNotifier.notifyAutoBuyUnavailable(this,
                "entry_gate_" + Integer.toHexString(reason.hashCode()), reason);
    }\'\'\'
text, count = reject_pattern.subn(lambda match: new_reject, text, count=1)
if count != 1:
    raise RuntimeError("Could not add gate alert to ProductionNotificationService")'''
if old not in source:
    raise RuntimeError("Could not normalize v2.1.1 gate-alert source patch")
source = source.replace(old, new, 1)

with tempfile.NamedTemporaryFile("w", suffix=".py", encoding="utf-8", delete=False) as handle:
    handle.write(source)
    fixed = handle.name
runpy.run_path(fixed, run_name="__main__")

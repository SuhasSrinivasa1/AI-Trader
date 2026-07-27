#!/usr/bin/env python3
from pathlib import Path
import runpy
import tempfile

source = Path("hotfix/apply_v211.py").read_text(encoding="utf-8")

# Preserve the Java "\\n" sequence when the generated reject method is inserted.
old_reject_patch = '''old_reject = \'\'\'    private void rejectAndDisarm(String reason, String summary) {
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
new_reject_patch = '''reject_pattern = re.compile(
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
if old_reject_patch not in source:
    raise RuntimeError("Could not normalize v2.1.1 gate-alert source patch")
source = source.replace(old_reject_patch, new_reject_patch, 1)

# The generated summary method's indentation can vary. Replace its parameter list by regex
# and fail explicitly instead of silently leaving the old six-argument signature.
old_summary_patch = '''text = text.replace(
    \'\'\'                                   String productType, int quantity,
                                   boolean freeRecommendation) {\'\'\',
    \'\'\'                                   String productType, int quantity,
                                   boolean freeRecommendation, double effectiveBudget) {\'\'\',
    1,
)'''
new_summary_patch = '''summary_signature_pattern = re.compile(
    r"(private static String summary\\(\\s*SignalParser\\.ParsedSignal signal,\\s*"
    r"AppPrefs\\.TradeWindow window,\\s*OrderPolicy\\.EntryMode entryMode,\\s*"
    r"String productType, int quantity,\\s*boolean freeRecommendation)\\) \\{",
    re.S,
)
text, count = summary_signature_pattern.subn(
    lambda match: match.group(1) + ", double effectiveBudget) {", text, count=1)
if count != 1:
    raise RuntimeError("Could not add effective FREE budget to summary signature")'''
if old_summary_patch not in source:
    raise RuntimeError("Could not normalize v2.1.1 summary signature patch")
source = source.replace(old_summary_patch, new_summary_patch, 1)

with tempfile.NamedTemporaryFile("w", suffix=".py", encoding="utf-8", delete=False) as handle:
    handle.write(source)
    fixed = handle.name
runpy.run_path(fixed, run_name="__main__")

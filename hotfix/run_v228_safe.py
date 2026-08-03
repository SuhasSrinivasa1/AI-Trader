#!/usr/bin/env python3
from pathlib import Path
import runpy
import tempfile

source = Path("hotfix/run_v228.py").read_text(encoding="utf-8")
start_marker = "# Do not accept a new Multyfi buy while any prior early exit remains unresolved.\n"
end_marker = "# Position reconciliation now precedes protection. A manual sale immediately\n"
start = source.find(start_marker)
end = source.find(end_marker, start)
if start < 0 or end < 0:
    raise RuntimeError("Could not locate the fragile v2.2.8 service patch section")

replacement = r"""# Do not accept a new Multyfi buy while any prior early exit remains unresolved.
# Insert after the existing phrase-handling block using brace matching so this
# remains stable across earlier generated-version wording changes.
text = read(service)
gate_marker = "            if (SignalParser.containsEarlyExitPhrase(rawText)) {"
if text.count(gate_marker) != 1:
    raise RuntimeError("Could not uniquely locate the early-exit phrase gate")
gate_start = text.find(gate_marker)
open_brace = text.find("{", gate_start)
depth = 0
gate_end = -1
for index in range(open_brace, len(text)):
    char = text[index]
    if char == "{":
        depth += 1
    elif char == "}":
        depth -= 1
        if depth == 0:
            gate_end = index + 1
            break
if gate_end < 0:
    raise RuntimeError("Could not locate the end of the early-exit phrase gate")

pending_gate = r'''
            if (hasPendingEarlyExit(active)) {
                AppPrefs.log(this, "NEW ENTRY BLOCKED — EARLY EXIT PENDING",
                        "A previous Multyfi exit is still awaiting broker-confirmed zero position.\n"
                                + compact(rawText));
                return;
            }
'''
text = text[:gate_end] + pending_gate + text[gate_end:]
text = text.replace(
        "An exit phrase did not identify exactly one active strategy. No sell was submitted.",
        "An exit phrase did not identify exactly one active filled strategy. No sell was submitted.")
helper = r'''    private static boolean hasPendingEarlyExit(List<Strategy> strategies) {
        if (strategies == null) return false;
        for (Strategy strategy : strategies) {
            if (strategy != null && strategy.isActive()
                    && strategy.earlyExitRequested) return true;
        }
        return false;
    }

'''
marker = "    private boolean ensureStaticPublicIp() {\n"
if text.count(marker) != 1:
    raise RuntimeError("Could not locate ProductionNotificationService helper marker")
write(service, text.replace(marker, helper + marker, 1))

"""
source = source[:start] + replacement + source[end:]

with tempfile.NamedTemporaryFile("w", suffix=".py", encoding="utf-8", delete=False) as handle:
    handle.write(source)
    safe_path = handle.name

runpy.run_path(safe_path, run_name="__main__")

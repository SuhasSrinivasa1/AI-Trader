#!/usr/bin/env python3
from pathlib import Path
import runpy
import tempfile

source = Path("hotfix/run_v223.py").read_text(encoding="utf-8")

# Replace only the named Java method body. The generated monitor contains extra
# image-import helpers between methods, so broad regex ranges are unsafe.
old_any_patch = r'''replace_regex_once(monitor,
                   r"    private boolean anyStopLegTriggered\(String token, Strategy strategy\) \{.*?(?=    private void cancelEntryRemainder)",
                   new_any_triggered)'''
new_any_patch = r'''monitor_text = read(monitor)
method_start = monitor_text.find("    private boolean anyStopLegTriggered(")
if method_start < 0:
    raise RuntimeError("Could not locate anyStopLegTriggered")
open_brace = monitor_text.find("{", method_start)
depth = 0
method_end = -1
for index in range(open_brace, len(monitor_text)):
    char = monitor_text[index]
    if char == "{":
        depth += 1
    elif char == "}":
        depth -= 1
        if depth == 0:
            method_end = index + 1
            break
if method_end < 0:
    raise RuntimeError("Could not find end of anyStopLegTriggered")
write(monitor, monitor_text[:method_start] + new_any_triggered.rstrip()
        + monitor_text[method_end:])'''
if source.count(old_any_patch) != 1:
    raise RuntimeError("Could not locate broad anyStopLegTriggered replacement")
source = source.replace(old_any_patch, new_any_patch, 1)

# Replace only the protection-cancellation loop inside executeExit.
old_exit_patch = r'''replace_regex_once(monitor,
                   r"        for \(Strategy\.StopLeg leg : strategy\.stopLegs\) \{.*?(?=        GrowwClient\.IntResult position = GrowwClient\.getNetPositionQuantity)",
                   new_exit_loop)'''
new_exit_patch = r'''monitor_text = read(monitor)
execute_start = monitor_text.find("    private void executeExit(")
if execute_start < 0:
    raise RuntimeError("Could not locate executeExit")
loop_start = monitor_text.find(
        "        for (Strategy.StopLeg leg : strategy.stopLegs) {", execute_start)
if loop_start < 0:
    raise RuntimeError("Could not locate executeExit protection loop")
open_brace = monitor_text.find("{", loop_start)
depth = 0
loop_end = -1
for index in range(open_brace, len(monitor_text)):
    char = monitor_text[index]
    if char == "{":
        depth += 1
    elif char == "}":
        depth -= 1
        if depth == 0:
            loop_end = index + 1
            break
if loop_end < 0:
    raise RuntimeError("Could not find end of executeExit protection loop")
write(monitor, monitor_text[:loop_start] + new_exit_loop.rstrip()
        + monitor_text[loop_end:])'''
if source.count(old_exit_patch) != 1:
    raise RuntimeError("Could not locate unanchored executeExit replacement")
source = source.replace(old_exit_patch, new_exit_patch, 1)

with tempfile.NamedTemporaryFile("w", suffix=".py", encoding="utf-8", delete=False) as handle:
    handle.write(source)
    safe_path = handle.name

runpy.run_path(safe_path, run_name="__main__")

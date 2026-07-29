#!/usr/bin/env python3
from pathlib import Path
import runpy
import tempfile

source = Path("hotfix/run_v223.py").read_text(encoding="utf-8")

# The first implementation used broad non-greedy ranges. The generated v2.2.x
# monitor has image-import protection helpers between neighbouring methods, so
# those ranges could remove unrelated methods. Replace only the exact legacy
# anyStopLegTriggered method and anchor the exit loop inside executeExit.
old_any_patch = r'''replace_regex_once(monitor,
                   r"    private boolean anyStopLegTriggered\(String token, Strategy strategy\) \{.*?(?=    private void cancelEntryRemainder)",
                   new_any_triggered)'''
new_any_patch = r"""old_any_method = r'''    private boolean anyStopLegTriggered(String token, Strategy strategy) {
        for (Strategy.StopLeg leg : strategy.stopLegs) {
            GrowwClient.SmartStatus status = GrowwClient.getGtt(token, leg.smartOrderId);
            if (!status.success) continue;
            leg.status = status.status;
            if (isTriggeredStatus(status.status)) {
                save(strategy);
                return true;
            }
        }
        return false;
    }

'''
monitor_text = read(monitor)
if monitor_text.count(old_any_method) != 1:
    raise RuntimeError("Could not locate the exact legacy anyStopLegTriggered method")
write(monitor, monitor_text.replace(old_any_method, new_any_triggered, 1))"""

if source.count(old_any_patch) != 1:
    raise RuntimeError("Could not locate the broad anyStopLegTriggered replacement")
source = source.replace(old_any_patch, new_any_patch, 1)

old_exit_patch = r'''replace_regex_once(monitor,
                   r"        for \(Strategy\.StopLeg leg : strategy\.stopLegs\) \{.*?(?=        GrowwClient\.IntResult position = GrowwClient\.getNetPositionQuantity)",
                   new_exit_loop)'''

new_exit_patch = r'''monitor_text = read(monitor)
execute_pattern = re.compile(
    r"(    private void executeExit\(String token, Strategy strategy,.*?\n"
    r"                             boolean staticIpReady, String exitType\) \{.*?)"
    r"        for \(Strategy\.StopLeg leg : strategy\.stopLegs\) \{.*?"
    r"(?=        GrowwClient\.IntResult position = GrowwClient\.getNetPositionQuantity)",
    re.S,
)
monitor_text, count = execute_pattern.subn(
    lambda match: match.group(1) + new_exit_loop,
    monitor_text,
    count=1,
)
if count != 1:
    raise RuntimeError("Could not replace the stop-protection loop inside executeExit")
write(monitor, monitor_text)'''

if source.count(old_exit_patch) != 1:
    raise RuntimeError("Could not locate the unanchored executeExit replacement")
source = source.replace(old_exit_patch, new_exit_patch, 1)

with tempfile.NamedTemporaryFile("w", suffix=".py", encoding="utf-8", delete=False) as handle:
    handle.write(source)
    safe_path = handle.name

runpy.run_path(safe_path, run_name="__main__")

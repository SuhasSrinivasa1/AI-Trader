#!/usr/bin/env python3
from pathlib import Path
import runpy
import tempfile

source = Path("hotfix/run_v223.py").read_text(encoding="utf-8")

old = r'''replace_regex_once(monitor,
                   r"        for \(Strategy\.StopLeg leg : strategy\.stopLegs\) \{.*?(?=        GrowwClient\.IntResult position = GrowwClient\.getNetPositionQuantity)",
                   new_exit_loop)'''

new = r'''monitor_text = read(monitor)
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

if source.count(old) != 1:
    raise RuntimeError("Could not locate the unanchored executeExit replacement")
source = source.replace(old, new, 1)

with tempfile.NamedTemporaryFile("w", suffix=".py", encoding="utf-8", delete=False) as handle:
    handle.write(source)
    safe_path = handle.name

runpy.run_path(safe_path, run_name="__main__")

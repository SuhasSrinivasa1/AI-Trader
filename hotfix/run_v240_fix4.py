#!/usr/bin/env python3
from pathlib import Path
import runpy, shutil

runpy.run_path("hotfix/run_v240_fix3.py", run_name="__main__")
ROOT = Path("android-stable")

# The CHILD module is cloned before v2.4.0 app-level tests are rewritten, so it
# can retain v2.3.5's old gross-₹5,000 assertion. Sync the fully updated app test
# suite into CHILD so both roles validate the same NET +₹5,000 / -₹2,000 rules,
# relay authentication and all legacy trading regressions.
source = ROOT / "app/src/test"
target = ROOT / "child/src/test"
if target.exists():
    shutil.rmtree(target)
shutil.copytree(source, target)

for module in ("app", "child"):
    p = ROOT / module / "src/test/java/com/suhas/multyfiautobuy/stable/ProfitTargetPolicyTest.java"
    text = p.read_text(encoding="utf-8")
    assert "netFiveThousandNeedsMoreThanFiveThousandGross" in text
    assert "zeroPriorPnlTargetsExactlyFiveThousandGross" not in text
    relay = ROOT / module / "src/test/java/com/suhas/multyfiautobuy/stable/LanRelayProtocolTest.java"
    assert relay.exists()

print("Applied v2.4.0 final test-suite synchronization for MASTER and CHILD")

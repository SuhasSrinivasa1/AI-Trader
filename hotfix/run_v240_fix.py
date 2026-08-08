#!/usr/bin/env python3
from pathlib import Path
import runpy

runpy.run_path("hotfix/run_v240_master_child.py", run_name="__main__")

ROOT = Path("android-stable")


def patch(path: Path, old: str, new: str, expected: int = 1) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != expected:
        raise RuntimeError(f"Expected {expected} matches in {path}, found {count}: {old[:160]}")
    path.write_text(text.replace(old, new, expected), encoding="utf-8")

# Java NetworkInterface#getInterfaceAddresses already returns a List. The first
# v2.4.0 candidate incorrectly wrapped it in Collections.list(), which accepts
# Enumeration only. Apply the compile-safe direct iteration in both modules.
old_discovery = "for(InterfaceAddress a:Collections.list(en.nextElement().getInterfaceAddresses()))"
new_discovery = "for(InterfaceAddress a:en.nextElement().getInterfaceAddresses())"
for module in ("app", "child"):
    p = ROOT / module / "src/main/java/com/suhas/multyfiautobuy/stable/LanChildRelayService.java"
    patch(p, old_discovery, new_discovery)

# Partial fills must never make the daily-loss guard looser than intended. Arm
# both profit/loss price calculations using the requested full quantity. This is
# conservative while a LIMIT order is partially filled and becomes exact when
# the intended quantity completes. It avoids a first partial fill calculating a
# per-share stop that would be too wide if more shares fill milliseconds later.
for module in ("app", "child"):
    p = ROOT / module / "src/main/java/com/suhas/multyfiautobuy/stable/StrategyMonitorService.java"
    patch(p,
          "strategy.entryAveragePrice, strategy.observedFilledQuantity,\n                strategy.dailyNetBeforeTrade);",
          "strategy.entryAveragePrice, strategy.requestedQuantity,\n                strategy.dailyNetBeforeTrade);",
          expected=2)

# Contract checks for this corrective layer.
for module in ("app", "child"):
    relay = (ROOT / module / "src/main/java/com/suhas/multyfiautobuy/stable/LanChildRelayService.java").read_text(encoding="utf-8")
    monitor = (ROOT / module / "src/main/java/com/suhas/multyfiautobuy/stable/StrategyMonitorService.java").read_text(encoding="utf-8")
    assert "Collections.list(en.nextElement().getInterfaceAddresses())" not in relay
    assert monitor.count("strategy.entryAveragePrice, strategy.requestedQuantity,") >= 2

print("Applied v2.4.0 compile fix and conservative partial-fill daily-risk sizing")

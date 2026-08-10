#!/usr/bin/env python3
from pathlib import Path
import runpy

runpy.run_path("hotfix/run_v242.py", run_name="__main__")

ROOT = Path("android-stable")
for module in ("app", "child"):
    path = ROOT / module / "src/main/java/com/suhas/multyfiautobuy/stable/LanChildRelayService.java"
    text = path.read_text(encoding="utf-8")
    old = "for(InterfaceAddress a:Collections.list(ni.getInterfaceAddresses()))"
    new = "for(InterfaceAddress a:ni.getInterfaceAddresses())"
    if text.count(old) != 1:
        raise RuntimeError(f"Expected one InterfaceAddress iteration in {path}, found {text.count(old)}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    fixed = path.read_text(encoding="utf-8")
    assert old not in fixed
    assert new in fixed

print("Applied v2.4.2 compile correction for interface broadcast discovery")

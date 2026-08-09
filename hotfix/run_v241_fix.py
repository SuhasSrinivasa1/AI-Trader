#!/usr/bin/env python3
from pathlib import Path
import runpy

source_path = Path("hotfix/run_v241.py")
source = source_path.read_text(encoding="utf-8")

old_python = '    patch(ns, "        if (!AppPrefs.MULTYFI_PACKAGE.equals(sbn.getPackageName())) return;\\n", "        if (!AppPrefs.MULTYFI_PACKAGE.equals(sbn.getPackageName())) return;\\n        if (!AppPrefs.isArmed(this)) return;\\n")\n'

old_java = """        if (AppPrefs.MULTYFI_PACKAGE.equals(sourcePackage)) {
            executor.execute(() -> process(rawText, postTime));
            if (!AppRole.isChild(this)) {
                LanMasterRelayService.publishAsync(this, rawText, postTime);
            }
        } else if (AppPrefs.RESEARCH360_PACKAGE.equals(sourcePackage)) {
"""

new_java = """        if (AppPrefs.MULTYFI_PACKAGE.equals(sourcePackage)) {
            if (!AppPrefs.isArmed(this)) return;
            executor.execute(() -> process(rawText, postTime));
            if (!AppRole.isChild(this)) {
                LanMasterRelayService.publishAsync(this, rawText, postTime);
            }
        } else if (AppPrefs.RESEARCH360_PACKAGE.equals(sourcePackage)) {
"""

new_python = f"    patch(ns, {old_java!r}, {new_java!r})\n"
if old_python not in source:
    raise RuntimeError("v2.4.1 obsolete notification patch line not found")
patched = source.replace(old_python, new_python, 1)

temp = Path("hotfix/.run_v241_fixed_runtime.py")
temp.write_text(patched, encoding="utf-8")
try:
    runpy.run_path(str(temp), run_name="__main__")
finally:
    try:
        temp.unlink()
    except Exception:
        pass

print("Applied v2.4.1 armed notification-routing corrective wrapper")

#!/usr/bin/env python3
from pathlib import Path
import runpy

source = Path("hotfix/run_v241.py").read_text(encoding="utf-8")
old = '''    patch(ns, "        if (!AppPrefs.MULTYFI_PACKAGE.equals(sbn.getPackageName())) return;\\n", "        if (!AppPrefs.MULTYFI_PACKAGE.equals(sbn.getPackageName())) return;\\n        if (!AppPrefs.isArmed(this)) return;\\n")
'''
new = '''    patch(ns, r'''\n        if (AppPrefs.MULTYFI_PACKAGE.equals(sourcePackage)) {\n            executor.execute(() -> process(rawText, postTime));\n            if (!AppRole.isChild(this)) {\n                LanMasterRelayService.publishAsync(this, rawText, postTime);\n            }\n        } else if (AppPrefs.RESEARCH360_PACKAGE.equals(sourcePackage)) {\n''', r'''\n        if (AppPrefs.MULTYFI_PACKAGE.equals(sourcePackage)) {\n            if (!AppPrefs.isArmed(this)) return;\n            executor.execute(() -> process(rawText, postTime));\n            if (!AppRole.isChild(this)) {\n                LanMasterRelayService.publishAsync(this, rawText, postTime);\n            }\n        } else if (AppPrefs.RESEARCH360_PACKAGE.equals(sourcePackage)) {\n''')\n'''
if old not in source:
    raise RuntimeError("v2.4.1 notification-routing patch anchor not found")
patched = source.replace(old, new, 1)
temp = Path("hotfix/.run_v241_fixed_runtime.py")
temp.write_text(patched, encoding="utf-8")
try:
    runpy.run_path(str(temp), run_name="__main__")
finally:
    try: temp.unlink()
    except Exception: pass
print("Applied v2.4.1 armed notification-routing corrective wrapper")

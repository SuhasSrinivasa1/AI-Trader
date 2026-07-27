#!/usr/bin/env python3
from pathlib import Path
import runpy
import tempfile

source_path = Path("hotfix/apply_v201.py")
source = source_path.read_text(encoding="utf-8")
for name in ("new_armed_gate", "old_reject", "new_reject"):
    old = name + " = '''"
    new = name + " = r'''"
    if old not in source:
        raise RuntimeError(f"Could not normalize raw replacement string: {name}")
    source = source.replace(old, new, 1)

with tempfile.NamedTemporaryFile("w", suffix=".py", encoding="utf-8", delete=False) as handle:
    handle.write(source)
    fixed_path = handle.name

runpy.run_path(fixed_path, run_name="__main__")

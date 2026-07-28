#!/usr/bin/env python3
from pathlib import Path
import runpy
import tempfile

source_path = Path("hotfix/run_v221.py")
source = source_path.read_text(encoding="utf-8")
old = "updated, count = re.subn(pattern, replacement, text, count=1, flags=re.S)"
new = "updated, count = re.subn(pattern, lambda _match: replacement, text, count=1, flags=re.S)"
if source.count(old) != 1:
    raise RuntimeError("Could not apply literal-safe regex replacement fix to run_v221.py")
source = source.replace(old, new, 1)

with tempfile.NamedTemporaryFile("w", suffix=".py", encoding="utf-8", delete=False) as handle:
    handle.write(source)
    safe_script = handle.name

runpy.run_path(safe_script, run_name="__main__")

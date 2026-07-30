#!/usr/bin/env python3
from pathlib import Path
import runpy
import tempfile

source = Path("hotfix/run_v225.py").read_text(encoding="utf-8")
old = '''assert 'body.put("price", 0)' not in client_text'''
new = '''mis_start = client_text.index("    static ApiResult createMisStopLossOrder(")
mis_end = client_text.index("    private static ApiResult findDurableMisStop(", mis_start)
mis_method_text = client_text[mis_start:mis_end]
assert 'body.put("price"' not in mis_method_text'''
if source.count(old) != 1:
    raise RuntimeError("Could not locate the broad MIS price assertion")
source = source.replace(old, new, 1)
with tempfile.NamedTemporaryFile("w", suffix=".py", encoding="utf-8", delete=False) as handle:
    handle.write(source)
    safe_path = handle.name
runpy.run_path(safe_path, run_name="__main__")

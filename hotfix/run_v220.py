#!/usr/bin/env python3
from pathlib import Path
import re
import runpy
import tempfile

source = Path("hotfix/apply_v220.py").read_text(encoding="utf-8")
block = re.compile(
    r"old = '''\s+String productType, int quantity,.*?text = text\.replace\(old, new, 1\)",
    re.S,
)
replacement = r'''signature_pattern = re.compile(
    r"(String productType, int quantity,\n\s*)boolean freeRecommendation\) \{"
)
text, count = signature_pattern.subn(
    r"\1boolean freeRecommendation, double freeBudget) {", text, count=1
)
if count != 1:
    raise RuntimeError("Could not update summary signature")'''
source, count = block.subn(lambda match: replacement, source, count=1)
if count != 1:
    raise RuntimeError("Could not normalize v2.2.0 summary signature patch block")

with tempfile.NamedTemporaryFile("w", suffix=".py", encoding="utf-8", delete=False) as handle:
    handle.write(source)
    fixed = handle.name

runpy.run_path(fixed, run_name="__main__")

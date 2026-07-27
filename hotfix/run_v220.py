#!/usr/bin/env python3
from pathlib import Path
import re
import runpy
import tempfile

source = Path("hotfix/apply_v220.py").read_text(encoding="utf-8")
pattern = re.compile(
    r"old = '''\s+String productType, int quantity,\n\s+boolean freeRecommendation\) \{'''"
)
replacement = """old = '''                                   String productType, int quantity,
                                   boolean freeRecommendation) {'''"""
source, count = pattern.subn(replacement, source, count=1)
if count != 1:
    raise RuntimeError("Could not normalize v2.2.0 summary signature matcher")

with tempfile.NamedTemporaryFile("w", suffix=".py", encoding="utf-8", delete=False) as handle:
    handle.write(source)
    fixed = handle.name

runpy.run_path(fixed, run_name="__main__")

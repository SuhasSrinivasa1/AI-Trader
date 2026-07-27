#!/usr/bin/env python3
from pathlib import Path
import runpy
import tempfile

source = Path("hotfix/apply_v220.py").read_text(encoding="utf-8")
old = """old = '''                                   String productType, int quantity,
                                    boolean freeRecommendation) {'''"""
new = """old = '''                                   String productType, int quantity,
                                   boolean freeRecommendation) {'''"""
if old not in source:
    raise RuntimeError("Could not normalize v2.2.0 summary signature matcher")
source = source.replace(old, new, 1)

with tempfile.NamedTemporaryFile("w", suffix=".py", encoding="utf-8", delete=False) as handle:
    handle.write(source)
    fixed = handle.name

runpy.run_path(fixed, run_name="__main__")

#!/usr/bin/env python3
from pathlib import Path
import re
import runpy
import tempfile

source = Path("hotfix/apply_v220.py").read_text(encoding="utf-8")

summary_block = re.compile(
    r"old = '''\s+String productType, int quantity,.*?text = text\.replace\(old, new, 1\)",
    re.S,
)
summary_replacement = r'''signature_pattern = re.compile(
    r"(String productType, int quantity,\n\s*)boolean freeRecommendation\) \{"
)
text, count = signature_pattern.subn(
    r"\1boolean freeRecommendation, double freeBudget) {", text, count=1
)
if count != 1:
    raise RuntimeError("Could not update summary signature")'''
source, count = summary_block.subn(lambda match: summary_replacement, source, count=1)
if count != 1:
    raise RuntimeError("Could not normalize v2.2.0 summary signature patch block")

reject_block = re.compile(
    r"old = '''    private void rejectAndDisarm\(String reason, String summary\) \{.*?text = text\.replace\(old, new, 1\)",
    re.S,
)
reject_replacement = r'''reject_pattern = re.compile(
    r"(    private void rejectAndDisarm\(String reason, String summary\) \{.*?)(\n    \})",
    re.S,
)
text, count = reject_pattern.subn(
    r"\1\n        TradeEventNotifier.notifyTradingPaused(this, reason);\2",
    text,
    count=1,
)
if count != 1:
    raise RuntimeError("Could not add intake pause notification")'''
source, count = reject_block.subn(lambda match: reject_replacement, source, count=1)
if count != 1:
    raise RuntimeError("Could not normalize v2.2.0 intake pause patch block")

with tempfile.NamedTemporaryFile("w", suffix=".py", encoding="utf-8", delete=False) as handle:
    handle.write(source)
    fixed = handle.name

runpy.run_path(fixed, run_name="__main__")

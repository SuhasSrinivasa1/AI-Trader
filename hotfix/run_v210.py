#!/usr/bin/env python3
from pathlib import Path
import runpy
import tempfile

source = Path("hotfix/apply_v210.py").read_text(encoding="utf-8")
old = '''        Matcher qty = QTY.matcher(block);
        int quantity = qty.find() ? integer(qty.group(1)) : defaultQuantity;
        addValidated(symbol, entry, target, stop, quantity, !qty.find(),
                "recommendation " + index, orders, errors);'''
new = '''        Matcher qty = QTY.matcher(block);
        boolean quantityFound = qty.find();
        int quantity = quantityFound ? integer(qty.group(1)) : defaultQuantity;
        addValidated(symbol, entry, target, stop, quantity, !quantityFound,
                "recommendation " + index, orders, errors);'''
if old not in source:
    raise RuntimeError("Could not normalize labelled quantity detection")
source = source.replace(old, new, 1)

with tempfile.NamedTemporaryFile("w", suffix=".py", encoding="utf-8", delete=False) as handle:
    handle.write(source)
    fixed = handle.name
runpy.run_path(fixed, run_name="__main__")

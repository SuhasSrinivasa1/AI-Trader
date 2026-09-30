#!/usr/bin/env python3
from pathlib import Path

path = Path("android-stable/app/src/main/java/com/suhas/multyfiautobuy/stable/ProductionNotificationService.java")
text = path.read_text(encoding="utf-8")
bad = '                                + "\n" + compact(rawText));'
good = r'                                + "\n" + compact(rawText));'
count = text.count(bad)
if count != 1:
    raise RuntimeError(f"Expected one generated newline defect, found {count}")
path.write_text(text.replace(bad, good, 1), encoding="utf-8")
print("Fixed v2.3.1 ignored-notification Java newline escape")

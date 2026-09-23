#!/usr/bin/env python3
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve()

def edit(rel, old, new, label):
    p = root / rel
    text = p.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected 1 occurrence, found {count}")
    p.write_text(text.replace(old, new, 1), encoding="utf-8")

edit(
    "app/build.gradle.kts",
    "versionCode = 122\n        versionName = \"1.2.2\"",
    "versionCode = 123\n        versionName = \"1.2.3\"",
    "version bump",
)

# The 3 PM list is a next-session UC decision, not a LIVE UC decision.
# Freeze the first non-empty candidate set between 15:00 and 15:30 even when
# the same scan is WATCHLIST ONLY for immediate/live execution.
edit(
    "app/src/main/java/com/suhas/ucsentinel/data/repository/UCSentinelRepository.kt",
    'if(scanNow.toLocalTime()>=LocalTime.of(15,0)&&scanNow.toLocalTime()<=LocalTime.of(15,30)&&!uc.message.startsWith("WATCHLIST ONLY")){',
    'if(scanNow.toLocalTime()>=LocalTime.of(15,0)&&scanNow.toLocalTime()<=LocalTime.of(15,30)&&uc.candidates.isNotEmpty()){',
    "3 PM UC freeze independent from LIVE gate",
)

# A successful strategy scan must clear a previous scheduler error. Otherwise
# the UI can keep showing an old NaN failure after the engine has recovered.
edit(
    "app/src/main/java/com/suhas/ucsentinel/data/repository/UCSentinelRepository.kt",
    "prefs.saveStrategySummary(summary);summary",
    "prefs.saveStrategySummary(summary);prefs.clearStrategyError();summary",
    "clear stale strategy scheduler error",
)

# Make the UI wording match the actual fixed contract.
edit(
    "app/src/main/java/com/suhas/ucsentinel/ui/CompactMarketScreens.kt",
    'EmptyState("No 3 PM list yet","The first qualifying scan at/after 15:00 IST freezes the final 3 PM list for the next trading session.")',
    'EmptyState("No qualified 3 PM list yet","The first non-empty UC candidate scan from 15:00–15:30 IST freezes the final next-session 3 PM list, independently of the LIVE gate.")',
    "3 PM UI contract wording",
)

print("Global Edge v1.2.3 consistency repair applied")

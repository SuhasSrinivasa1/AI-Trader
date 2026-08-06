#!/usr/bin/env python3
from pathlib import Path
import runpy

# Apply the v2.3.2 product change first.
runpy.run_path("hotfix/run_v232.py", run_name="__main__")

TEST = Path("android-stable/app/src/test/java/com/suhas/multyfiautobuy/stable")


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"Expected one match in {path}, found {count}: {old[:160]}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


signal_test = TEST / "SignalParserTest.java"
replace_once(
    signal_test,
    "public void absentIntradayLabelDefaultsToCncEntryGtt()",
    "public void absentIntradayLabelDefaultsToMisWhileSwingRemainsCnc()",
)
replace_once(
    signal_test,
    'assertEquals("CNC", unlabelled.productType);',
    'assertEquals("MIS", unlabelled.productType);',
)
replace_once(
    signal_test,
    "assertEquals(OrderPolicy.EntryMode.CNC_ENTRY_GTT,\n"
    "                NotificationRoutePolicy.entryMode(unlabelled));",
    "assertEquals(OrderPolicy.EntryMode.IMMEDIATE_MIS_LIMIT,\n"
    "                NotificationRoutePolicy.entryMode(unlabelled));",
)

budget_test = TEST / "TradeTypeBudgetPolicyTest.java"
replace_once(
    budget_test,
    "assertEquals(TradeTypeBudgetPolicy.SWING,\n"
    "                TradeTypeBudgetPolicy.type(ordinary, false));",
    "assertEquals(TradeTypeBudgetPolicy.INTRADAY,\n"
    "                TradeTypeBudgetPolicy.type(ordinary, false));",
)

assert "absentIntradayLabelDefaultsToMisWhileSwingRemainsCnc" in signal_test.read_text(encoding="utf-8")
assert "TradeTypeBudgetPolicy.type(ordinary, false)" in budget_test.read_text(encoding="utf-8")
print("Updated legacy tests for v2.3.2 blocklist-based MIS routing")

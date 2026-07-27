#!/usr/bin/env python3
from pathlib import Path
import runpy

# Start from the validated v2.0.1 persistent-arm and stop-loss-recovery source patch.
runpy.run_path("hotfix/run_v201.py", run_name="__main__")

ROOT = Path("android-stable")
JAVA = ROOT / "app/src/main/java/com/suhas/multyfiautobuy/stable"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def replace_once(path: Path, old: str, new: str) -> None:
    text = read(path)
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"Expected exactly one match in {path}: found {count}\n{old[:180]}")
    write(path, text.replace(old, new, 1))


# Release identity.
gradle = ROOT / "app/build.gradle"
replace_once(gradle, "versionCode 201", "versionCode 202")
replace_once(gradle, "versionName '2.0.1'", "versionName '2.0.2'")

# Parser: any standalone word 'free' marks a complete recommendation as fixed-quantity.
parser = JAVA / "SignalParser.java"
text = read(parser)
old = '    private static final Pattern FREE_PATTERN = Pattern.compile("(?i)\\\\bfree\\\\s+(?:equity\\\\s+)?recommendation\\\\b");'
new = old + '\n    private static final Pattern FREE_WORD_PATTERN = Pattern.compile("(?i)\\\\bfree\\\\b");'
if old not in text:
    raise RuntimeError("Could not find SignalParser FREE_PATTERN")
text = text.replace(old, new, 1)
text = text.replace(
    '        if (FREE_PATTERN.matcher(rawText).find()) return "FREE_EQUITY";',
    '        if (FREE_WORD_PATTERN.matcher(rawText).find()) return "FREE_EQUITY";',
    1,
)
marker = '''    static boolean containsEarlyExitPhrase(String rawText) {
        return rawText != null && EARLY_EXIT_PATTERN.matcher(rawText).find();
    }

'''
insert = marker + '''    static boolean isFreeRecommendation(String rawText) {
        return rawText != null && FREE_WORD_PATTERN.matcher(rawText).find();
    }

'''
if marker not in text:
    raise RuntimeError("Could not insert SignalParser.isFreeRecommendation")
text = text.replace(marker, insert, 1)
old_digest = '''        String digest = sha256(symbol + "|" + low + "|" + high + "|"
                + targetPrice + "|" + stopLossPrice + "|" + productType
                + "|" + bufferPercent + "|" + AppPrefs.istDate());'''
new_digest = '''        boolean freeRecommendation = isFreeRecommendation(rawText);
        String digest = sha256(symbol + "|" + low + "|" + high + "|"
                + targetPrice + "|" + stopLossPrice + "|" + productType
                + "|free=" + freeRecommendation
                + "|" + bufferPercent + "|" + AppPrefs.istDate());'''
if old_digest not in text:
    raise RuntimeError("Could not update SignalParser event digest")
text = text.replace(old_digest, new_digest, 1)
write(parser, text)

# Central quantity policy: free recommendations always use 10 shares; all others use budgets.
policy = JAVA / "OrderPolicy.java"
text = read(policy)
marker = '''    static boolean usesEntryGtt(AppPrefs.TradeWindow window) {
        return entryMode(window) == EntryMode.CNC_ENTRY_GTT;
    }

'''
insert = marker + '''    static int quantity(boolean freeRecommendation, double budget, double maximumBuyPrice) {
        return freeRecommendation ? 10 : AppPrefs.quantityForBudget(budget, maximumBuyPrice);
    }

    static boolean usesWindowBudget(boolean freeRecommendation) {
        return !freeRecommendation;
    }

'''
if marker not in text:
    raise RuntimeError("Could not insert OrderPolicy quantity override")
text = text.replace(marker, insert, 1)
write(policy, text)

# Notification execution: fixed 10-share quantity in any of the three active market windows.
listener = JAVA / "ProductionNotificationService.java"
text = read(listener)
old_quantity = '''            OrderPolicy.EntryMode entryMode = OrderPolicy.entryMode(window);
            String productType = OrderPolicy.productType(window);
            int quantity = AppPrefs.quantityForBudget(window.budget, signal.maxBuyPrice);
            String summary = summary(signal, window, entryMode, productType, quantity);'''
new_quantity = '''            OrderPolicy.EntryMode entryMode = OrderPolicy.entryMode(window);
            String productType = OrderPolicy.productType(window);
            boolean freeRecommendation = SignalParser.isFreeRecommendation(rawText);
            int quantity = OrderPolicy.quantity(freeRecommendation, window.budget, signal.maxBuyPrice);
            String summary = summary(signal, window, entryMode, productType, quantity,
                    freeRecommendation);'''
if old_quantity not in text:
    raise RuntimeError("Could not replace ProductionNotificationService quantity calculation")
text = text.replace(old_quantity, new_quantity, 1)
old_limit = '''            if (maximumOrderValue > window.budget + 0.01d
                    || maximumOrderValue > AppPrefs.MAX_ORDER_VALUE) {'''
new_limit = '''            if ((OrderPolicy.usesWindowBudget(freeRecommendation)
                    && maximumOrderValue > window.budget + 0.01d)
                    || maximumOrderValue > AppPrefs.MAX_ORDER_VALUE) {'''
if old_limit not in text:
    raise RuntimeError("Could not replace ProductionNotificationService value limit")
text = text.replace(old_limit, new_limit, 1)
old_summary = '''    private static String summary(SignalParser.ParsedSignal signal,
                                  AppPrefs.TradeWindow window,
                                  OrderPolicy.EntryMode entryMode,
                                  String productType, int quantity) {
        String route = entryMode == OrderPolicy.EntryMode.IMMEDIATE_MIS_LIMIT
                ? "MIS immediate LIMIT" : "CNC entry GTT";
        return signal.symbol + " | " + window.label + " | " + route
                + " | source category " + signal.category
                + " | entry ₹" + money(signal.entryLow) + "–₹" + money(signal.entryHigh)
                + " | cap ₹" + money(signal.maxBuyPrice)
                + " | target ₹" + money(signal.targetPrice)
                + " | SL ₹" + money(signal.stopLossPrice)
                + " | budget ₹" + money(window.budget)
                + " | qty " + quantity
                + " | product " + productType
                + " | planned ₹" + money(signal.maximumOrderValue(quantity));
    }'''
new_summary = '''    private static String summary(SignalParser.ParsedSignal signal,
                                  AppPrefs.TradeWindow window,
                                  OrderPolicy.EntryMode entryMode,
                                  String productType, int quantity,
                                  boolean freeRecommendation) {
        String route = entryMode == OrderPolicy.EntryMode.IMMEDIATE_MIS_LIMIT
                ? "MIS immediate LIMIT" : "CNC entry GTT";
        return signal.symbol + " | " + window.label + " | " + route
                + " | source category " + signal.category
                + (freeRecommendation
                ? " | FREE OVERRIDE: fixed 10 shares; window budget ignored"
                : " | budget ₹" + money(window.budget))
                + " | entry ₹" + money(signal.entryLow) + "–₹" + money(signal.entryHigh)
                + " | cap ₹" + money(signal.maxBuyPrice)
                + " | target ₹" + money(signal.targetPrice)
                + " | SL ₹" + money(signal.stopLossPrice)
                + " | qty " + quantity
                + " | product " + productType
                + " | planned ₹" + money(signal.maximumOrderValue(quantity));
    }'''
if old_summary not in text:
    raise RuntimeError("Could not replace ProductionNotificationService summary")
text = text.replace(old_summary, new_summary, 1)
write(listener, text)

# Dashboard and offline acceptance test visibly disclose and verify the new rule.
activity = JAVA / "ProductionActivity.java"
text = read(activity)
text = text.replace("release 2.0.1", "release 2.0.2")
text = text.replace("source-built v2.0.1", "source-built v2.0.2")
text = text.replace(
    "Amounts are saved only after pressing SAVE TRADING WINDOWS. Unsaved edits block arming.",
    "Amounts are saved only after pressing SAVE TRADING WINDOWS. Unsaved edits block arming. Any complete recommendation containing the word FREE uses exactly 10 shares in every active market window; the normal MIS/CNC time routing remains unchanged.",
    1,
)
text = text.replace(
    '                ? "● Routing policy: MIS before 09:30 • CNC GTT after 09:30"',
    '                ? "● Routing policy: MIS before 09:30 • CNC GTT after 09:30 • FREE = fixed 10 shares"',
    1,
)
old_parser_test = '''        boolean passed = signal != null && first != null && second != null && third != null
                && OrderPolicy.entryMode(first) == OrderPolicy.EntryMode.IMMEDIATE_MIS_LIMIT'''
new_parser_test = '''        String freeSample = "Today's Free Equity Recommendation\\nStock Name: TCS\\nEntry Range: 3200-3220\\nTarget: 3300\\nStop Loss: 3150";
        boolean freeDetected = SignalParser.isFreeRecommendation(freeSample);
        boolean passed = signal != null && first != null && second != null && third != null
                && freeDetected
                && OrderPolicy.quantity(true, first.budget, 6975d) == 10
                && OrderPolicy.quantity(false, first.budget, signal.maxBuyPrice)
                == AppPrefs.quantityForBudget(first.budget, signal.maxBuyPrice)
                && OrderPolicy.entryMode(first) == OrderPolicy.EntryMode.IMMEDIATE_MIS_LIMIT'''
if old_parser_test not in text:
    raise RuntimeError("Could not extend ProductionActivity offline routing test")
text = text.replace(old_parser_test, new_parser_test, 1)
text = text.replace(
    'PASS: 09:00–09:30 MIS LIMIT; 09:30 onward CNC entry GTT; three budgets; early exit matched; no order submitted.',
    'PASS: 09:00–09:30 MIS LIMIT; 09:30 onward CNC entry GTT; FREE fixed quantity 10 in every active window; three budgets; early exit matched; no order submitted.',
    1,
)
write(activity, text)

print("Applied Multyfi AutoBuy Pro v2.0.2 free fixed-quantity policy")

#!/usr/bin/env python3
from pathlib import Path
import re
import runpy

# Build only on the fully validated v2.2.3 release chain.
runpy.run_path("hotfix/run_v223_safe.py", run_name="__main__")

ROOT = Path("android-stable")
JAVA = ROOT / "app/src/main/java/com/suhas/multyfiautobuy/stable"
TEST = ROOT / "app/src/test/java/com/suhas/multyfiautobuy/stable"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def replace_once(path: Path, old: str, new: str) -> None:
    text = read(path)
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"Expected one match in {path}, found {count}: {old[:180]}")
    write(path, text.replace(old, new, 1))


def replace_regex_once(path: Path, pattern: str, replacement: str) -> None:
    text = read(path)
    updated, count = re.subn(pattern, lambda _m: replacement, text, count=1, flags=re.S)
    if count != 1:
        raise RuntimeError(f"Expected one regex match in {path}, found {count}: {pattern[:180]}")
    write(path, updated)


def replace_java_method(path: Path, signature: str, replacement: str) -> None:
    text = read(path)
    start = text.find(signature)
    if start < 0:
        raise RuntimeError(f"Could not locate Java method in {path}: {signature}")
    open_brace = text.find("{", start)
    if open_brace < 0:
        raise RuntimeError(f"Could not locate method brace in {path}: {signature}")
    depth = 0
    end = -1
    for index in range(open_brace, len(text)):
        char = text[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                end = index + 1
                break
    if end < 0:
        raise RuntimeError(f"Could not locate method end in {path}: {signature}")
    write(path, text[:start] + replacement.rstrip() + text[end:])


# Release identity.
gradle = ROOT / "app/build.gradle"
replace_once(gradle, "versionCode 223", "versionCode 224")
replace_once(gradle, "versionName '2.2.3'", "versionName '2.2.4'")


# The notification owns both route and budget category. The clock only decides
# whether execution is permitted and supplies the existing cancellation cutoff.
write(JAVA / "TradeTypeBudgetPolicy.java", r'''package com.suhas.multyfiautobuy.stable;

import android.content.Context;

/** Selects the saved amount from the Multyfi recommendation type, never from time. */
final class TradeTypeBudgetPolicy {
    static final String INTRADAY = "INTRADAY";
    static final String SWING = "SWING";
    static final String MULTIBAGGER = "MULTIBAGGER";
    static final String FREE = "FREE";

    private TradeTypeBudgetPolicy() { }

    static String type(SignalParser.ParsedSignal signal, boolean freeRecommendation) {
        if (freeRecommendation) return FREE;
        if (signal != null && signal.isIntraday()) return INTRADAY;
        if (signal != null && "MULTIBAGGER".equalsIgnoreCase(signal.category)) {
            return MULTIBAGGER;
        }
        if (signal != null && "FREE_EQUITY".equalsIgnoreCase(signal.category)) return FREE;
        // Explicit swing and ordinary/unlabelled equity calls share the swing amount.
        return SWING;
    }

    static double budget(Context context, SignalParser.ParsedSignal signal,
                         boolean freeRecommendation) {
        String type = type(signal, freeRecommendation);
        if (INTRADAY.equals(type)) return AppPrefs.intradayBudget(context);
        if (MULTIBAGGER.equals(type)) return AppPrefs.multibaggerBudget(context);
        if (FREE.equals(type)) return AppPrefs.freeBudget(context);
        return AppPrefs.swingBudget(context);
    }

    static double selectBudget(String type, double intraday, double swing,
                               double multibagger, double free) {
        if (INTRADAY.equals(type)) return intraday;
        if (MULTIBAGGER.equals(type)) return multibagger;
        if (FREE.equals(type)) return free;
        return swing;
    }

    static String displayName(String type) {
        if (INTRADAY.equals(type)) return "Intraday";
        if (MULTIBAGGER.equals(type)) return "Multibagger";
        if (FREE.equals(type)) return "Free";
        return "Swing";
    }
}
''')


# Preserve all current on-device amounts without a destructive migration:
# old window 1 -> Intraday, old window 2 -> Swing, old window 3 -> Multibagger,
# and the existing FREE amount -> Free. Fresh installs use the user's current setup.
prefs = JAVA / "AppPrefs.java"
text = read(prefs)
text = text.replace("DEFAULT_WINDOW_1_BUDGET = 10_000d", "DEFAULT_WINDOW_1_BUDGET = 40_000d", 1)
text = text.replace("DEFAULT_WINDOW_2_BUDGET = 10_000d", "DEFAULT_WINDOW_2_BUDGET = 40_000d", 1)
marker = "    // Compatibility helper used by older local tests and migration paths.\n"
if marker not in text:
    raise RuntimeError("Could not locate AppPrefs compatibility marker")
trade_type_methods = r'''    // v2.2.4 semantic aliases. Existing preference keys intentionally remain
    // unchanged so an in-place APK update preserves the four configured values.
    static double intradayBudget(Context context) {
        return window1Budget(context);
    }

    static double swingBudget(Context context) {
        return window2Budget(context);
    }

    static double multibaggerBudget(Context context) {
        return window3Budget(context);
    }

    static double freeBudget(Context context) {
        return freeRecommendationBudget(context);
    }

    static void setTradeTypeBudgets(Context context, double intraday, double swing,
                                    double multibagger, double free) {
        if (!isValidTradeBudget(intraday) || !isValidTradeBudget(swing)
                || !isValidTradeBudget(multibagger) || !isValidTradeBudget(free)) {
            throw new IllegalArgumentException(
                    "Each trade-type amount must be between ₹1,000 and ₹5,00,000.");
        }
        prefs(context).edit()
                .putLong(K_WINDOW_1_BUDGET, Double.doubleToRawLongBits(intraday))
                .putLong(K_WINDOW_2_BUDGET, Double.doubleToRawLongBits(swing))
                .putLong(K_WINDOW_3_BUDGET, Double.doubleToRawLongBits(multibagger))
                .putLong(K_FREE_RECOMMENDATION_BUDGET, Double.doubleToRawLongBits(free))
                .apply();
    }

'''
text = text.replace(marker, trade_type_methods + marker, 1)
write(prefs, text)


# Budget selection is now independent of the time window. The window remains
# only as the weekday/market-hours gate and source of entry cancellation time.
service = JAVA / "ProductionNotificationService.java"
text = read(service)
selection_pattern = re.compile(
    r"            boolean freeRecommendation = SignalParser\.isFreeRecommendation\(rawText\);.*?"
    r"(?=            if \(quantity < 1\) \{)",
    re.S,
)
selection = r'''            boolean freeRecommendation = SignalParser.isFreeRecommendation(rawText);
            String budgetType = TradeTypeBudgetPolicy.type(signal, freeRecommendation);
            double activeBudget = TradeTypeBudgetPolicy.budget(
                    this, signal, freeRecommendation);
            int quantity = AppPrefs.quantityForBudget(activeBudget, signal.maxBuyPrice);
            String summary = summary(signal, window, entryMode, productType, quantity,
                    budgetType, activeBudget);
'''
text, count = selection_pattern.subn(lambda _m: selection, text, count=1)
if count != 1:
    raise RuntimeError("Could not replace notification budget selection")
text = text.replace("REJECTED — WINDOW BUDGET BELOW ONE SHARE",
                    "REJECTED — TRADE-TYPE BUDGET BELOW ONE SHARE")
# Remove the old second declaration produced by the FREE/window policy.
text, count = re.subn(
    r"            double activeBudget = OrderPolicy\.activeBudget\(freeRecommendation,\n"
    r"                    window\.budget, freeBudget\);\n",
    "", text, count=1)
if count != 1:
    raise RuntimeError("Could not remove obsolete window/free activeBudget declaration")
write(service, text)

summary_method = r'''    private static String summary(SignalParser.ParsedSignal signal,
                                  AppPrefs.TradeWindow window,
                                  OrderPolicy.EntryMode entryMode,
                                  String productType, int quantity,
                                  String budgetType, double activeBudget) {
        String route = entryMode == OrderPolicy.EntryMode.IMMEDIATE_MIS_LIMIT
                ? "MIS immediate LIMIT" : "CNC entry GTT";
        return signal.symbol + " | " + window.label + " execution window | " + route
                + " | source category " + signal.category
                + " | budget type " + TradeTypeBudgetPolicy.displayName(budgetType)
                + " ₹" + money(activeBudget)
                + " | entry ₹" + money(signal.entryLow) + "–₹" + money(signal.entryHigh)
                + " | cap ₹" + money(signal.maxBuyPrice)
                + " | target ₹" + money(signal.targetPrice)
                + " | SL ₹" + money(signal.stopLossPrice)
                + " | qty " + quantity
                + " | product " + productType
                + " | planned ₹" + money(signal.maximumOrderValue(quantity));
    }
'''
replace_java_method(service, "    private static String summary(", summary_method)

# Keep the route-policy documentation accurate.
route_policy = JAVA / "NotificationRoutePolicy.java"
route_text = read(route_policy)
route_text = route_text.replace(
    "/** Notification-owned order routing. Trading windows select budget only. */",
    "/** Notification-owned routing. Trade type selects budget; time only gates execution. */")
write(route_policy, route_text)


# Dashboard: four trade-type fields. Internal historic field names are retained
# to minimise regression risk; only their semantics and labels change.
activity = JAVA / "ProductionActivity.java"
text = read(activity)
text = text.replace("2.2.3", "2.2.4")
text = text.replace("candidate release 2.2.4", "stable release 2.2.4")
text = text.replace('sectionTitle("TRADING WINDOWS")', 'sectionTitle("TRADE-TYPE BUDGETS")')
text = text.replace(
    "Amounts are saved only after pressing SAVE TRADING WINDOWS. Unsaved edits block arming.",
    "Amounts follow the Multyfi recommendation type, not the clock. Save all four values before arming. Ordinary or unlabelled equity calls use the Swing budget.")
text = text.replace('window1Input = moneyField("09:00–09:30 • order amount (route follows notification)");',
                    'window1Input = moneyField("Intraday maximum budget");')
text = text.replace('window2Input = moneyField("09:30–10:00 • order amount (route follows notification)");',
                    'window2Input = moneyField("Swing / ordinary equity budget");')
text = text.replace('window3Input = moneyField("10:00–15:30 • order amount (route follows notification)");',
                    'window3Input = moneyField("Multibagger budget");')
text = text.replace('freeBudgetInput = moneyField("FREE recommendation amount • default ₹5,000");',
                    'freeBudgetInput = moneyField("Free recommendation budget");')
text = text.replace('primaryButton("SAVE TRADING WINDOWS")',
                    'primaryButton("SAVE TRADE-TYPE BUDGETS")')
text = text.replace("UNSAVED CHANGES — press SAVE TRADING WINDOWS",
                    "UNSAVED CHANGES — press SAVE TRADE-TYPE BUDGETS")
text = text.replace("Save the edited trading windows", "Save the edited trade-type budgets")
text = text.replace("all three saved amount windows", "all four trade-type budgets")
text = text.replace("three amounts and early exit verified", "four trade-type budgets and early exit verified")
text = text.replace(
    "● Routing policy: notification-owned • Intraday/MIS => MIS • otherwise CNC GTT",
    "● Routing + budget policy: notification-owned • amount follows trade type")
text = text.replace(
    "Auto-Buy OFF by default • Intraday/MIS => MIS LIMIT • otherwise => CNC GTT • source-built v2.2.4",
    "Auto-Buy OFF by default • budget follows Intraday/Swing/Multibagger/Free • source-built v2.2.4")
# Semantic aliases preserve the old preference keys while making every display explicit.
text = text.replace("AppPrefs.window1Budget(this)", "AppPrefs.intradayBudget(this)")
text = text.replace("AppPrefs.window2Budget(this)", "AppPrefs.swingBudget(this)")
text = text.replace("AppPrefs.window3Budget(this)", "AppPrefs.multibaggerBudget(this)")
text = text.replace("AppPrefs.freeRecommendationBudget(this)", "AppPrefs.freeBudget(this)")
write(activity, text)

# Replace only the amount-loading part, retaining authentication/IP/test state loading.
text = read(activity)
load_pattern = re.compile(
    r"        suppressWindowWatch = true;.*?        windowSavedStatus\.setTextColor\(GREEN\);",
    re.S,
)
load_block = r'''        suppressWindowWatch = true;
        window1Input.setText(money(AppPrefs.intradayBudget(this)));
        window2Input.setText(money(AppPrefs.swingBudget(this)));
        window3Input.setText(money(AppPrefs.multibaggerBudget(this)));
        freeBudgetInput.setText(money(AppPrefs.freeBudget(this)));
        bufferInput.setText(String.format(Locale.US, "%.2f", AppPrefs.entryBufferPercent(this)));
        suppressWindowWatch = false;
        windowsDirty = false;
        windowSavedStatus.setText("Saved: Intraday ₹" + money(AppPrefs.intradayBudget(this))
                + " • Swing ₹" + money(AppPrefs.swingBudget(this))
                + " • Multibagger ₹" + money(AppPrefs.multibaggerBudget(this))
                + " • Free ₹" + money(AppPrefs.freeBudget(this))
                + " • buffer " + String.format(Locale.US, "%.2f",
                AppPrefs.entryBufferPercent(this)) + "%");
        windowSavedStatus.setTextColor(GREEN);'''
text, count = load_pattern.subn(lambda _m: load_block, text, count=1)
if count != 1:
    raise RuntimeError("Could not replace trade-type budget load block")
write(activity, text)

save_method = r'''    private void saveTradingWindows() {
        try {
            double intraday = readDouble(window1Input);
            double swing = readDouble(window2Input);
            double multibagger = readDouble(window3Input);
            double free = readDouble(freeBudgetInput);
            double buffer = readDouble(bufferInput);
            if (!AppPrefs.isValidTradeBudget(intraday)
                    || !AppPrefs.isValidTradeBudget(swing)
                    || !AppPrefs.isValidTradeBudget(multibagger)
                    || !AppPrefs.isValidTradeBudget(free)) {
                toast("Each trade-type amount must be between ₹1,000 and ₹5,00,000.");
                return;
            }
            if (!AppPrefs.isValidEntryBuffer(buffer)) {
                toast("Entry buffer must be between 0% and 2%.");
                return;
            }
            AppPrefs.setTradeTypeBudgets(this, intraday, swing, multibagger, free);
            AppPrefs.setEntryBufferPercent(this, buffer);
            windowsDirty = false;
            windowSavedStatus.setText("SAVED NOW: Intraday ₹" + money(intraday)
                    + " • Swing ₹" + money(swing)
                    + " • Multibagger ₹" + money(multibagger)
                    + " • Free ₹" + money(free)
                    + " • buffer " + String.format(Locale.US, "%.2f", buffer) + "%");
            windowSavedStatus.setTextColor(GREEN);
            AppPrefs.log(this, "TRADE-TYPE BUDGETS SAVED",
                    "Intraday ₹" + money(intraday)
                            + " • Swing/ordinary equity ₹" + money(swing)
                            + " • Multibagger ₹" + money(multibagger)
                            + " • Free ₹" + money(free)
                            + " • buffer " + String.format(Locale.US, "%.2f", buffer) + "%."
                            + " Execution hours and MIS/CNC routing are unchanged.");
            toast("All four trade-type budgets were saved.");
            refreshStatus();
        } catch (Exception e) {
            toast("Could not save trade-type budgets: " + safeMessage(e));
        }
    }
'''
replace_java_method(activity, "    private void saveTradingWindows()", save_method)

parser_method = r'''    private void runParserTest() {
        long firstTime = atIst(2026, 7, 27, 9, 10);
        long secondTime = atIst(2026, 7, 27, 9, 40);
        long thirdTime = atIst(2026, 7, 27, 10, 30);
        String fields = "\nStock Name: TCS\nEntry Range: 3200-3220\nTarget: 3300\nStop Loss: 3150";
        SignalParser.ParsedSignal intraday = SignalParser.parse(
                "Intraday Equity Recommendation" + fields, firstTime,
                AppPrefs.entryBufferPercent(this));
        SignalParser.ParsedSignal swing = SignalParser.parse(
                "Swing Recommendation" + fields, secondTime,
                AppPrefs.entryBufferPercent(this));
        SignalParser.ParsedSignal multibagger = SignalParser.parse(
                "Multibagger Recommendation" + fields, thirdTime,
                AppPrefs.entryBufferPercent(this));
        SignalParser.ParsedSignal free = SignalParser.parse(
                "Today's Free Equity Recommendation" + fields, secondTime,
                AppPrefs.entryBufferPercent(this));
        SignalParser.ParsedSignal unlabelled = SignalParser.parse(
                "Equity Recommendation" + fields, thirdTime,
                AppPrefs.entryBufferPercent(this));
        AppPrefs.TradeWindow first = AppPrefs.tradeWindow(this, firstTime);
        AppPrefs.TradeWindow second = AppPrefs.tradeWindow(this, secondTime);
        AppPrefs.TradeWindow third = AppPrefs.tradeWindow(this, thirdTime);
        boolean passed = intraday != null && swing != null && multibagger != null
                && free != null && unlabelled != null
                && first != null && second != null && third != null
                && NotificationRoutePolicy.entryMode(intraday)
                    == OrderPolicy.EntryMode.IMMEDIATE_MIS_LIMIT
                && NotificationRoutePolicy.entryMode(swing)
                    == OrderPolicy.EntryMode.CNC_ENTRY_GTT
                && NotificationRoutePolicy.entryMode(multibagger)
                    == OrderPolicy.EntryMode.CNC_ENTRY_GTT
                && NotificationRoutePolicy.entryMode(free)
                    == OrderPolicy.EntryMode.CNC_ENTRY_GTT
                && TradeTypeBudgetPolicy.INTRADAY.equals(
                    TradeTypeBudgetPolicy.type(intraday, false))
                && TradeTypeBudgetPolicy.SWING.equals(
                    TradeTypeBudgetPolicy.type(swing, false))
                && TradeTypeBudgetPolicy.MULTIBAGGER.equals(
                    TradeTypeBudgetPolicy.type(multibagger, false))
                && TradeTypeBudgetPolicy.FREE.equals(
                    TradeTypeBudgetPolicy.type(free, true))
                && TradeTypeBudgetPolicy.SWING.equals(
                    TradeTypeBudgetPolicy.type(unlabelled, false))
                && AppPrefs.quantityForBudget(AppPrefs.intradayBudget(this),
                    intraday.maxBuyPrice) >= 1;
        Strategy dummy = new Strategy("test-event", "TCS", "EQUITY", "CNC",
                3, 3300d, 3150d, 0, "TESTREF", "TESTGTT", firstTime);
        SignalParser.EarlyExitSignal exit = SignalParser.parseEarlyExit(
                "Exiting early\nStock Name: TCS", firstTime,
                Collections.singletonList(dummy));
        passed = passed && exit != null && "TCS".equals(exit.symbol);
        AppPrefs.setParserTestPassed(this, passed);
        String message = passed
                ? "PASS: route follows the Multyfi text; budget follows Intraday, Swing, Multibagger or Free; unlabelled equity uses Swing; early exit verified; no order submitted."
                : "Notification routing/trade-type budget acceptance failed. Auto-Buy remains blocked.";
        AppPrefs.log(this, passed ? "PRODUCTION ROUTING TEST PASSED"
                : "PRODUCTION ROUTING TEST FAILED", message);
        toast(message);
        refreshStatus();
    }
'''
replace_java_method(activity, "    private void runParserTest()", parser_method)

# Make the armed/status summaries self-describing without changing gate behaviour.
text = read(activity)
text = text.replace(
    '" • budgets ₹" + money(AppPrefs.intradayBudget(this))\n'
    '                                + "/₹" + money(AppPrefs.swingBudget(this))\n'
    '                                + "/₹" + money(AppPrefs.multibaggerBudget(this))',
    '" • Intraday ₹" + money(AppPrefs.intradayBudget(this))\n'
    '                                + " • Swing ₹" + money(AppPrefs.swingBudget(this))\n'
    '                                + " • Multibagger ₹" + money(AppPrefs.multibaggerBudget(this))')
text = text.replace(
    '" • saved budgets ₹" + money(AppPrefs.intradayBudget(this))',
    '" • Intraday ₹" + money(AppPrefs.intradayBudget(this))')
write(activity, text)


# Unit contract for category precedence and plain-equity fallback.
write(TEST / "TradeTypeBudgetPolicyTest.java", r'''package com.suhas.multyfiautobuy.stable;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertNotNull;

import org.junit.Test;

public class TradeTypeBudgetPolicyTest {
    private static final long SAMPLE_TIME = 1785125400000L;
    private static final String FIELDS = "\nStock Name: TCS\nEntry Range: 3200-3220"
            + "\nTarget: 3300\nStop Loss: 3150";

    @Test public void recommendationTypeSelectsBudgetNotClock() {
        SignalParser.ParsedSignal intraday = SignalParser.parse(
                "Intraday Recommendation" + FIELDS, SAMPLE_TIME, 1d);
        SignalParser.ParsedSignal swing = SignalParser.parse(
                "Swing Recommendation" + FIELDS, SAMPLE_TIME, 1d);
        SignalParser.ParsedSignal multibagger = SignalParser.parse(
                "Multibagger Recommendation" + FIELDS, SAMPLE_TIME, 1d);
        SignalParser.ParsedSignal ordinary = SignalParser.parse(
                "Equity Recommendation" + FIELDS, SAMPLE_TIME, 1d);
        assertNotNull(intraday);
        assertNotNull(swing);
        assertNotNull(multibagger);
        assertNotNull(ordinary);
        assertEquals(TradeTypeBudgetPolicy.INTRADAY,
                TradeTypeBudgetPolicy.type(intraday, false));
        assertEquals(TradeTypeBudgetPolicy.SWING,
                TradeTypeBudgetPolicy.type(swing, false));
        assertEquals(TradeTypeBudgetPolicy.MULTIBAGGER,
                TradeTypeBudgetPolicy.type(multibagger, false));
        assertEquals(TradeTypeBudgetPolicy.SWING,
                TradeTypeBudgetPolicy.type(ordinary, false));
    }

    @Test public void freeOverridesOtherBudgetCategories() {
        SignalParser.ParsedSignal intraday = SignalParser.parse(
                "Intraday Free Equity Recommendation" + FIELDS, SAMPLE_TIME, 1d);
        assertNotNull(intraday);
        assertEquals(TradeTypeBudgetPolicy.FREE,
                TradeTypeBudgetPolicy.type(intraday, true));
    }

    @Test public void selectsFourIndependentAmounts() {
        assertEquals(40_000d, TradeTypeBudgetPolicy.selectBudget(
                TradeTypeBudgetPolicy.INTRADAY, 40_000d, 20_000d, 10_000d, 5_000d), 0d);
        assertEquals(20_000d, TradeTypeBudgetPolicy.selectBudget(
                TradeTypeBudgetPolicy.SWING, 40_000d, 20_000d, 10_000d, 5_000d), 0d);
        assertEquals(10_000d, TradeTypeBudgetPolicy.selectBudget(
                TradeTypeBudgetPolicy.MULTIBAGGER, 40_000d, 20_000d, 10_000d, 5_000d), 0d);
        assertEquals(5_000d, TradeTypeBudgetPolicy.selectBudget(
                TradeTypeBudgetPolicy.FREE, 40_000d, 20_000d, 10_000d, 5_000d), 0d);
    }
}
''')

# Assertions prevent a release that silently falls back to clock-owned amounts.
assert "versionName '2.2.4'" in read(gradle)
assert "TradeTypeBudgetPolicy.budget" in read(service)
assert "OrderPolicy.activeBudget" not in read(service)
assert "window.budget, signal.maxBuyPrice" not in read(service)
assert "Intraday maximum budget" in read(activity)
assert "Swing / ordinary equity budget" in read(activity)
assert "Multibagger budget" in read(activity)
assert "Free recommendation budget" in read(activity)
assert "setTradeTypeBudgets" in read(prefs)
assert "createMisStopLossOrder" in read(JAVA / "GrowwClient.java")
assert "DailyAuthManager.ensureVerified(this)" in read(service)
print("Applied Multyfi AutoBuy Pro v2.2.4 trade-type budget policy")

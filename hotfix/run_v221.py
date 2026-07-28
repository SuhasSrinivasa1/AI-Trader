#!/usr/bin/env python3
from pathlib import Path
import re
import runpy

# Start only from the latest source-built v2.2.0 update chain.
runpy.run_path("hotfix/run_v220.py", run_name="__main__")

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
        raise RuntimeError(f"Expected exactly one match in {path}: found {count}\n{old[:240]}")
    write(path, text.replace(old, new, 1))


def replace_regex_once(path: Path, pattern: str, replacement: str) -> None:
    text = read(path)
    updated, count = re.subn(pattern, replacement, text, count=1, flags=re.S)
    if count != 1:
        raise RuntimeError(f"Expected exactly one regex match in {path}: found {count}")
    write(path, updated)


# Release identity.
gradle = ROOT / "app/build.gradle"
replace_once(gradle, "versionCode 220", "versionCode 221")
replace_once(gradle, "versionName '2.2.0'", "versionName '2.2.1'")

# A single, explicit route policy: the notification text owns the order type.
# Explicit Intraday/Intra day/MIS => MIS regular LIMIT.
# Every other complete signal, including no category => CNC entry GTT.
write(JAVA / "NotificationRoutePolicy.java", r'''package com.suhas.multyfiautobuy.stable;

/** Notification-owned order routing. Trading windows select budget only. */
final class NotificationRoutePolicy {
    private NotificationRoutePolicy() { }

    static OrderPolicy.EntryMode entryMode(SignalParser.ParsedSignal signal) {
        if (signal == null) throw new IllegalArgumentException("Parsed signal is required.");
        return signal.isIntraday()
                ? OrderPolicy.EntryMode.IMMEDIATE_MIS_LIMIT
                : OrderPolicy.EntryMode.CNC_ENTRY_GTT;
    }

    static String productType(SignalParser.ParsedSignal signal) {
        return entryMode(signal) == OrderPolicy.EntryMode.IMMEDIATE_MIS_LIMIT
                ? "MIS" : "CNC";
    }

    static boolean usesEntryGtt(SignalParser.ParsedSignal signal) {
        return entryMode(signal) == OrderPolicy.EntryMode.CNC_ENTRY_GTT;
    }

    static String description(SignalParser.ParsedSignal signal) {
        return signal.isIntraday()
                ? "Explicit Intraday/MIS • MIS immediate capped LIMIT"
                : "No explicit Intraday/MIS • CNC entry GTT";
    }
}
''')

service = JAVA / "ProductionNotificationService.java"
replace_once(
    service,
    '                "Production listener connected. 09:00–09:30 routes to MIS LIMIT; 09:30 onward routes to CNC entry GTT.");',
    '                "Production listener connected. Explicit Intraday/Intra day/MIS routes to MIS LIMIT; every other complete recommendation routes to CNC entry GTT.");'
)
replace_once(
    service,
    '''            OrderPolicy.EntryMode entryMode = OrderPolicy.entryMode(window);
            String productType = OrderPolicy.productType(window);''',
    '''            OrderPolicy.EntryMode entryMode = NotificationRoutePolicy.entryMode(signal);
            String productType = NotificationRoutePolicy.productType(signal);'''
)
replace_once(service, '"SUBMITTING 09:00–09:30 MIS ENTRY"', '"SUBMITTING MULTYFI INTRADAY MIS ENTRY"')
replace_once(service, '"SUBMITTING POST-09:30 CNC ENTRY GTT"', '"SUBMITTING MULTYFI CNC ENTRY GTT"')

# Do not silently discard an explicit intraday notification because of an old
# 14:45 parser cutoff. The service's configured weekday trading windows remain
# the execution gate.
parser = JAVA / "SignalParser.java"
replace_once(
    parser,
    '''        if ("MIS".equals(productType)
                && !isAllowedIntradayEntryTime(notificationTimeMillis)) return null;

''',
    ""
)

activity = JAVA / "ProductionActivity.java"
# The v2.2.0 source updater sets this exact release text.
replace_once(
    activity,
    '"Android 16 • source-built production release 2.2.0"',
    '"Android 16 • source-built stable release 2.2.1"'
)
replace_once(
    activity,
    'window1Input = moneyField("09:00–09:30 • MIS intraday • immediate LIMIT");',
    'window1Input = moneyField("09:00–09:30 • order amount (route follows notification)");'
)
replace_once(
    activity,
    'window2Input = moneyField("09:30–10:00 • CNC delivery • entry GTT");',
    'window2Input = moneyField("09:30–10:00 • order amount (route follows notification)");'
)
replace_once(
    activity,
    'window3Input = moneyField("10:00–15:30 • CNC delivery • entry GTT");',
    'window3Input = moneyField("10:00–15:30 • order amount (route follows notification)");'
)
replace_once(
    activity,
    '"This test validates notification parsing, all three time windows, MIS/GTT routing and strict symbol-matched early exit. It submits no broker order."',
    '"This test validates all three saved amount windows and notification-owned routing: explicit Intraday/MIS becomes MIS; every other complete call becomes CNC GTT. It submits no broker order."'
)
replace_once(
    activity,
    '"Auto-Buy OFF by default • 09:00–09:30 MIS • 09:30 onward CNC GTT • source-built v2.2.0"',
    '"Auto-Buy OFF by default • Intraday/MIS => MIS LIMIT • otherwise => CNC GTT • source-built v2.2.1"'
)

new_parser_test = r'''    private void runParserTest() {
        long firstTime = atIst(2026, 7, 27, 9, 10);
        long secondTime = atIst(2026, 7, 27, 9, 40);
        long thirdTime = atIst(2026, 7, 27, 10, 30);
        String fields = "\nStock Name: TCS\nEntry Range: 3200-3220\nTarget: 3300\nStop Loss: 3150";
        SignalParser.ParsedSignal intraday = SignalParser.parse(
                "Intraday Equity Recommendation" + fields, firstTime,
                AppPrefs.entryBufferPercent(this));
        SignalParser.ParsedSignal mis = SignalParser.parse(
                "MIS Recommendation" + fields, secondTime,
                AppPrefs.entryBufferPercent(this));
        SignalParser.ParsedSignal unlabelled = SignalParser.parse(
                "Equity Recommendation" + fields, thirdTime,
                AppPrefs.entryBufferPercent(this));
        SignalParser.ParsedSignal swing = SignalParser.parse(
                "Swing Recommendation" + fields, secondTime,
                AppPrefs.entryBufferPercent(this));
        AppPrefs.TradeWindow first = AppPrefs.tradeWindow(this, firstTime);
        AppPrefs.TradeWindow second = AppPrefs.tradeWindow(this, secondTime);
        AppPrefs.TradeWindow third = AppPrefs.tradeWindow(this, thirdTime);
        boolean passed = intraday != null && mis != null && unlabelled != null && swing != null
                && first != null && second != null && third != null
                && NotificationRoutePolicy.entryMode(intraday)
                    == OrderPolicy.EntryMode.IMMEDIATE_MIS_LIMIT
                && NotificationRoutePolicy.entryMode(mis)
                    == OrderPolicy.EntryMode.IMMEDIATE_MIS_LIMIT
                && NotificationRoutePolicy.entryMode(unlabelled)
                    == OrderPolicy.EntryMode.CNC_ENTRY_GTT
                && NotificationRoutePolicy.entryMode(swing)
                    == OrderPolicy.EntryMode.CNC_ENTRY_GTT
                && "MIS".equals(NotificationRoutePolicy.productType(intraday))
                && "MIS".equals(NotificationRoutePolicy.productType(mis))
                && "CNC".equals(NotificationRoutePolicy.productType(unlabelled))
                && "CNC".equals(NotificationRoutePolicy.productType(swing))
                && AppPrefs.quantityForBudget(first.budget, intraday.maxBuyPrice) >= 1
                && AppPrefs.quantityForBudget(second.budget, mis.maxBuyPrice) >= 1
                && AppPrefs.quantityForBudget(third.budget, unlabelled.maxBuyPrice) >= 1;
        Strategy dummy = new Strategy("test-event", "TCS", "EQUITY", "CNC",
                3, 3300d, 3150d, 0, "TESTREF", "TESTGTT", firstTime);
        SignalParser.EarlyExitSignal exit = SignalParser.parseEarlyExit(
                "Exiting early\nStock Name: TCS", firstTime,
                Collections.singletonList(dummy));
        passed = passed && exit != null && "TCS".equals(exit.symbol);
        AppPrefs.setParserTestPassed(this, passed);
        String message = passed
                ? "PASS: Intraday/Intra day/MIS => MIS LIMIT; all other or unlabelled calls => CNC entry GTT; three amounts and early exit verified; no order submitted."
                : "Notification routing/parser acceptance failed. Auto-Buy remains blocked.";
        AppPrefs.log(this, passed ? "PRODUCTION ROUTING TEST PASSED" : "PRODUCTION ROUTING TEST FAILED", message);
        toast(message);
        refreshStatus();
    }

'''
replace_regex_once(
    activity,
    r"    private void runParserTest\(\) \{.*?(?=    private void handleArmedChange)",
    new_parser_test
)
replace_once(
    activity,
    '                        "09:00–09:30 MIS immediate LIMIT • 09:30–15:30 CNC entry GTT"',
    '                        "Explicit Intraday/Intra day/MIS => MIS immediate LIMIT • all other complete calls => CNC entry GTT"'
)
replace_once(
    activity,
    '                ? "● Routing policy: MIS before 09:30 • CNC GTT after 09:30"',
    '                ? "● Routing policy: notification-owned • Intraday/MIS => MIS • otherwise CNC GTT"'
)

# Update existing unit expectations for the conservative ₹0.10 tick grid applied
# by run_v220.py, and replace the obsolete parser-time restriction test.
signal_test = TEST / "SignalParserTest.java"
replace_once(signal_test, "assertEquals(694.25d, signal.maxBuyPrice, 0.001d);",
             "assertEquals(694.20d, signal.maxBuyPrice, 0.001d);")
replace_once(signal_test, 'contains("planned ₹9719.50")', 'contains("planned ₹9718.80")')

new_intraday_test = r'''    @Test
    public void explicitIntradayOrMisRemainsMisAcrossConfiguredExecutionHours() {
        String intraday = "Equity Intraday\nStock Name: SBIN\nBuy Price: 810\n"
                + "Target: 825\nStop Loss: 802";
        String mis = "MIS Recommendation\nStock Name: SBIN\nBuy Price: 810\n"
                + "Target: 825\nStop Loss: 802";
        SignalParser.ParsedSignal morning = SignalParser.parse(intraday,
                atIst(2026, 7, 24, 9, 20), 1.5d);
        SignalParser.ParsedSignal afternoon = SignalParser.parse(intraday,
                atIst(2026, 7, 24, 15, 0), 1.5d);
        SignalParser.ParsedSignal explicitMis = SignalParser.parse(mis,
                atIst(2026, 7, 24, 10, 0), 1.5d);
        assertNotNull(morning);
        assertNotNull(afternoon);
        assertNotNull(explicitMis);
        assertEquals("INTRADAY", morning.category);
        assertEquals("MIS", morning.productType);
        assertEquals("MIS", afternoon.productType);
        assertEquals("MIS", explicitMis.productType);
        assertEquals(OrderPolicy.EntryMode.IMMEDIATE_MIS_LIMIT,
                NotificationRoutePolicy.entryMode(morning));
        assertEquals(OrderPolicy.EntryMode.IMMEDIATE_MIS_LIMIT,
                NotificationRoutePolicy.entryMode(afternoon));
        assertEquals(OrderPolicy.EntryMode.IMMEDIATE_MIS_LIMIT,
                NotificationRoutePolicy.entryMode(explicitMis));
    }

    @Test
    public void absentIntradayLabelDefaultsToCncEntryGtt() {
        String fields = "\nStock Name: SBIN\nBuy Price: 810\n"
                + "Target: 825\nStop Loss: 802";
        SignalParser.ParsedSignal unlabelled = SignalParser.parse(
                "Equity Recommendation" + fields,
                atIst(2026, 7, 24, 9, 20), 1.5d);
        SignalParser.ParsedSignal swing = SignalParser.parse(
                "Swing Recommendation" + fields,
                atIst(2026, 7, 24, 10, 0), 1.5d);
        assertNotNull(unlabelled);
        assertNotNull(swing);
        assertEquals("CNC", unlabelled.productType);
        assertEquals("CNC", swing.productType);
        assertEquals(OrderPolicy.EntryMode.CNC_ENTRY_GTT,
                NotificationRoutePolicy.entryMode(unlabelled));
        assertEquals(OrderPolicy.EntryMode.CNC_ENTRY_GTT,
                NotificationRoutePolicy.entryMode(swing));
    }

'''
replace_regex_once(
    signal_test,
    r"    @Test\s+    public void classifiesExplicitIntradayAsMisAndRestrictsItsWindow\(\) \{.*?(?=    @Test\s+    public void parsesEarlyExitOnlyForOneUniqueActiveSymbol)",
    new_intraday_test
)

# Dedicated route policy tests make the intended rule impossible to regress.
write(TEST / "NotificationRoutePolicyTest.java", r'''package com.suhas.multyfiautobuy.stable;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import org.junit.Test;

public class NotificationRoutePolicyTest {
    private static SignalParser.ParsedSignal signal(String category, String product) {
        return new SignalParser.ParsedSignal(
                "event", "reference", "TCS", category, product,
                100d, 101d, 100d, 102d, 1d,
                110d, 95d, 0L, category);
    }

    @Test public void explicitIntradayUsesMisRegularLimit() {
        SignalParser.ParsedSignal parsed = signal("INTRADAY", "MIS");
        assertEquals(OrderPolicy.EntryMode.IMMEDIATE_MIS_LIMIT,
                NotificationRoutePolicy.entryMode(parsed));
        assertEquals("MIS", NotificationRoutePolicy.productType(parsed));
        assertFalse(NotificationRoutePolicy.usesEntryGtt(parsed));
    }

    @Test public void everyNonIntradayCategoryUsesCncGtt() {
        String[] categories = {"EQUITY", "SWING", "MULTIBAGGER", "FREE_EQUITY", ""};
        for (String category : categories) {
            SignalParser.ParsedSignal parsed = signal(category, "CNC");
            assertEquals(OrderPolicy.EntryMode.CNC_ENTRY_GTT,
                    NotificationRoutePolicy.entryMode(parsed));
            assertEquals("CNC", NotificationRoutePolicy.productType(parsed));
            assertTrue(NotificationRoutePolicy.usesEntryGtt(parsed));
        }
    }
}
''')

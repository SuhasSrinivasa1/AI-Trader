#!/usr/bin/env python3
from pathlib import Path
import runpy

# Preserve the validated v2.3.1 entry, protection and authoritative early-sell chain.
runpy.run_path("hotfix/run_v231.py", run_name="__main__")

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
        raise RuntimeError(
            f"Expected one match in {path}, found {count}: {old[:180]}"
        )
    write(path, text.replace(old, new, 1))


# Release identity.
gradle = ROOT / "app/build.gradle"
replace_once(gradle, "versionCode 231", "versionCode 232")
replace_once(gradle, "versionName '2.3.1'", "versionName '2.3.2'")


# User-requested simplified intake rule:
# accept every complete Multyfi trade notification except those containing the
# words Free, Swing or Multibagger. All accepted entries are routed as MIS.
write(JAVA / "IntradayOnlyPolicy.java", r'''package com.suhas.multyfiautobuy.stable;

import java.util.Locale;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/** v2.3.2 intake rule: accept every complete Multyfi call except blocked categories. */
final class IntradayOnlyPolicy {
    private static final Pattern BLOCKED = Pattern.compile(
            "(?i)\\b(?:free|swing|multi\\s*[- ]?\\s*bagger)\\b");

    private IntradayOnlyPolicy() { }

    static boolean accepts(SignalParser.ParsedSignal signal, String rawText) {
        return signal != null
                && blockedWord(rawText).isEmpty()
                && signal.isIntraday()
                && "INTRADAY".equalsIgnoreCase(signal.category)
                && "MIS".equalsIgnoreCase(signal.productType);
    }

    static String ignoredReason(SignalParser.ParsedSignal signal, String rawText) {
        String blocked = blockedWord(rawText);
        if (!blocked.isEmpty()) {
            return blocked + " recommendations are disabled.";
        }
        if (signal == null) {
            return "The notification did not contain a complete stock name, entry, target and stop loss.";
        }
        return "The notification could not be routed as an Intraday MIS entry.";
    }

    static String blockedWord(String rawText) {
        if (rawText == null) return "";
        Matcher matcher = BLOCKED.matcher(rawText);
        if (!matcher.find()) return "";
        String word = matcher.group().toLowerCase(Locale.US).replaceAll("[^a-z]", "");
        if (word.startsWith("multi")) return "Multibagger";
        if (word.equals("swing")) return "Swing";
        return "Free";
    }
}
''')


parser = JAVA / "SignalParser.java"
replace_once(parser, r'''    private static String category(String rawText) {
        if (INTRADAY_PATTERN.matcher(rawText).find()) return "INTRADAY";
        if (MULTIBAGGER_PATTERN.matcher(rawText).find()) return "MULTIBAGGER";
        if (SWING_PATTERN.matcher(rawText).find()) return "SWING";
        if (FREE_WORD_PATTERN.matcher(rawText).find()) return "FREE_EQUITY";
        return "EQUITY";
    }
''', r'''    private static String category(String rawText) {
        // Explicitly blocked categories retain their identity so they can be
        // audited. Every other complete Multyfi equity call is routed as MIS.
        if (FREE_WORD_PATTERN.matcher(rawText).find()) return "FREE_EQUITY";
        if (MULTIBAGGER_PATTERN.matcher(rawText).find()) return "MULTIBAGGER";
        if (SWING_PATTERN.matcher(rawText).find()) return "SWING";
        return "INTRADAY";
    }
''')


write(TEST / "IntradayOnlyPolicyTest.java", r'''package com.suhas.multyfiautobuy.stable;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertNotNull;
import static org.junit.Assert.assertNull;
import static org.junit.Assert.assertTrue;

import org.junit.Test;

public class IntradayOnlyPolicyTest {
    private static final long TIME = 1785123600000L;
    private static final String FIELDS = "\nStock Name: TCS\nEntry Range: 3200-3220"
            + "\nTarget: 3300\nStop Loss: 3150";

    @Test public void acceptsPaidIntradayCall() {
        String text = "Intraday Equity Recommendation" + FIELDS;
        assertTrue(IntradayOnlyPolicy.accepts(SignalParser.parse(text, TIME), text));
    }

    @Test public void acceptsUnlabelledNewEquityTradeAsMis() {
        String text = "Released: New Equity Trade.\nStock Name: AEGISLOG"
                + "\nTarget: 1400\nEntry Range: 1365.6-1367.6\nStop Loss: 1341";
        SignalParser.ParsedSignal signal = SignalParser.parse(text, TIME);
        assertNotNull(signal);
        assertTrue(IntradayOnlyPolicy.accepts(signal, text));
        assertTrue(signal.isIntraday());
        assertEquals("INTRADAY", signal.category);
        assertEquals("MIS", signal.productType);
    }

    @Test public void rejectsOnlyFreeSwingAndMultibaggerWords() {
        String free = "FREE Intraday Equity Recommendation" + FIELDS;
        String swing = "Swing Recommendation" + FIELDS;
        String multibagger = "Multi-bagger Recommendation" + FIELDS;
        assertFalse(IntradayOnlyPolicy.accepts(SignalParser.parse(free, TIME), free));
        assertFalse(IntradayOnlyPolicy.accepts(SignalParser.parse(swing, TIME), swing));
        assertFalse(IntradayOnlyPolicy.accepts(SignalParser.parse(multibagger, TIME), multibagger));
        assertEquals("Free", IntradayOnlyPolicy.blockedWord(free));
        assertEquals("Swing", IntradayOnlyPolicy.blockedWord(swing));
        assertEquals("Multibagger", IntradayOnlyPolicy.blockedWord(multibagger));
    }

    @Test public void incompleteNotificationStillCannotTrade() {
        String text = "Released: New Equity Trade. Stock Name: TCS";
        assertNull(SignalParser.parse(text, TIME));
        assertFalse(IntradayOnlyPolicy.accepts(null, text));
    }
}
''')


# Correct the generated v2.3.1 audit newline and update the blocked-category title.
service = JAVA / "ProductionNotificationService.java"
service_text = read(service)
service_text = service_text.replace(
        'AppPrefs.log(this, "IGNORED — INTRADAY-ONLY MODE",',
        'AppPrefs.log(this, "IGNORED — BLOCKED MULTYFI CATEGORY",')
service_text = service_text.replace(
        '+ "\n" + compact(rawText));',
        '+ "\\n" + compact(rawText));')
write(service, service_text)


# Keep the UI minimal and accurately describe the new blocklist policy.
activity = JAVA / "ProductionActivity.java"
activity_text = read(activity)
replacements = {
    "Android 16 • source-built stable release 2.3.1":
        "Android 16 • source-built stable release 2.3.2",
    "This offline test confirms that paid Intraday/MIS is accepted, Swing/Multibagger/Free/unlabelled calls are blocked, and Multyfi early sell remains recognised. It submits no broker order.":
        "This offline test confirms that every complete Multyfi trade is accepted as Intraday MIS unless it contains Free, Swing or Multibagger. Multyfi early sell remains recognised. It submits no broker order.",
    "Auto-Buy OFF by default • MIS SL-M + CNC GTT protection • source-built v2.3.1":
        "Auto-Buy OFF by default • Intraday MIS only • early sell retained • source-built v2.3.2",
    "&& !IntradayOnlyPolicy.accepts(unlabelled, unlabelledText)":
        "&& IntradayOnlyPolicy.accepts(unlabelled, unlabelledText)\n                && unlabelled.isIntraday()",
    "PASS: Intraday accepted; Swing, Multibagger, Free, Free Intraday and unlabelled entries blocked; early sell recognised; no order submitted.":
        "PASS: Complete paid and unlabelled Multyfi calls accepted as MIS; Free, Swing and Multibagger blocked; early sell recognised; no order submitted.",
    "Intraday-only routing acceptance failed. Auto-Buy remains blocked.":
        "Multyfi blocklist routing acceptance failed. Auto-Buy remains blocked.",
    '"INTRADAY-ONLY ROUTING TEST PASSED"':
        '"MULTYFI BLOCKLIST ROUTING TEST PASSED"',
    '"INTRADAY-ONLY ROUTING TEST FAILED"':
        '"MULTYFI BLOCKLIST ROUTING TEST FAILED"',
    '"ARMED 24×7 — INTRADAY ONLY"':
        '"ARMED 24×7 — MULTYFI MIS"',
    "Persistent armed state enabled for paid Multyfi Intraday/MIS calls only":
        "Persistent armed state enabled for complete Multyfi calls except Free, Swing and Multibagger",
    " • Swing, Multibagger, Free and Free Intraday entries disabled":
        " • Free, Swing and Multibagger entries disabled",
    "● Intake: Intraday/MIS only • early sell retained • all other entry calls ignored":
        "● Intake: all complete Multyfi calls → MIS • Free/Swing/Multibagger blocked • early sell retained",
    "● Intraday-only policy: offline acceptance test required":
        "● Multyfi blocklist policy: offline acceptance test required",
    " • non-Intraday entry calls disabled.":
        " • Free, Swing and Multibagger entry calls disabled."
}
for old, new in replacements.items():
    count = activity_text.count(old)
    if count != 1:
        raise RuntimeError(f"Expected one activity match, found {count}: {old[:180]}")
    activity_text = activity_text.replace(old, new, 1)
write(activity, activity_text)


# Build-time contracts.
assert "versionCode 232" in read(gradle)
assert "versionName '2.3.2'" in read(gradle)
assert "return \"INTRADAY\";" in read(parser)
assert "acceptsUnlabelledNewEquityTradeAsMis" in read(TEST / "IntradayOnlyPolicyTest.java")
assert "queueEarlyExit(earlyExit)" in read(service)
assert "MULTYFI EARLY EXIT PERSISTED" in read(service)
assert "Free/Swing/Multibagger blocked" in read(activity)
print("Applied Multyfi AutoBuy Pro v2.3.2 blocklist-based Intraday MIS update")

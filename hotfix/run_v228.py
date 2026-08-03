#!/usr/bin/env python3
from pathlib import Path
import runpy

# Build on the validated v2.2.7 Multyfi + Research 360 release chain.
runpy.run_path("hotfix/run_v227.py", run_name="__main__")

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
        raise RuntimeError(f"Expected one match in {path}, found {count}: {old[:220]}")
    write(path, text.replace(old, new, 1))


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
replace_once(gradle, "versionCode 227", "versionCode 228")
replace_once(gradle, "versionName '2.2.7'", "versionName '2.2.8'")

# Match Multyfi early-exit updates by exact NSE symbol, normalized company name,
# or a safe single-filled-strategy fallback. Never select one of multiple filled
# strategies from an ambiguous notification.
parser = JAVA / "SignalParser.java"
parse_early_exit = r'''    static EarlyExitSignal parseEarlyExit(String rawText, long notificationTimeMillis,
                                          List<Strategy> activeStrategies) {
        if (rawText == null || rawText.trim().isEmpty()
                || activeStrategies == null || activeStrategies.isEmpty()) return null;
        Matcher phraseMatcher = EARLY_EXIT_PATTERN.matcher(rawText);
        if (!phraseMatcher.find()) return null;

        String labelled = labelledSymbol(rawText);
        String compactRaw = compactIdentity(rawText);
        Strategy matched = null;
        for (Strategy strategy : activeStrategies) {
            if (strategy == null || !strategy.isActive()) continue;
            boolean symbolMatches = !labelled.isEmpty()
                    ? identityMatches(labelled, strategy.symbol)
                    : containsSymbolToken(rawText, strategy.symbol)
                    || compactRaw.contains(compactIdentity(strategy.symbol));
            if (!symbolMatches) continue;
            if (matched != null && !matched.eventId.equals(strategy.eventId)) {
                return null;
            }
            matched = strategy;
        }
        if (matched != null) {
            return new EarlyExitSignal(matched.eventId, matched.symbol,
                    phraseMatcher.group(), notificationTimeMillis, rawText);
        }

        // Multyfi sometimes sends only "Update: We're choosing a disciplined
        // early exit..." without repeating the symbol. It is safe to infer only
        // when exactly one filled Multyfi strategy is active.
        Strategy onlyFilled = null;
        for (Strategy strategy : activeStrategies) {
            if (strategy == null || !strategy.isActive()
                    || strategy.observedFilledQuantity <= 0) continue;
            if (onlyFilled != null && !onlyFilled.eventId.equals(strategy.eventId)) {
                return null;
            }
            onlyFilled = strategy;
        }
        if (onlyFilled == null) return null;
        return new EarlyExitSignal(onlyFilled.eventId, onlyFilled.symbol,
                phraseMatcher.group(), notificationTimeMillis, rawText);
    }
'''
replace_java_method(parser, "    static EarlyExitSignal parseEarlyExit(", parse_early_exit)

parser_helpers = r'''    private static String compactIdentity(String value) {
        if (value == null) return "";
        return value.toUpperCase(Locale.US).replaceAll("[^A-Z0-9]", "");
    }

    private static boolean identityMatches(String first, String second) {
        String a = compactIdentity(first);
        String b = compactIdentity(second);
        return !a.isEmpty() && !b.isEmpty()
                && (a.equals(b) || a.contains(b) || b.contains(a));
    }

'''
text = read(parser)
marker = "    private static String labelledSymbol(String rawText) {\n"
if text.count(marker) != 1:
    raise RuntimeError("Could not locate SignalParser helper insertion point")
write(parser, text.replace(marker, parser_helpers + marker, 1))

# Persist the early-exit request before any network, VPN, IP, authentication or
# broker-order precheck. Temporary failures therefore delay the exit but cannot
# erase the Multyfi instruction.
service = JAVA / "ProductionNotificationService.java"
queue_early_exit = r'''    private void queueEarlyExit(SignalParser.EarlyExitSignal signal) {
        long age = System.currentTimeMillis() - signal.notificationTimeMillis;
        if (age > AppPrefs.MAX_EARLY_EXIT_AGE_MS || age < -60_000L) {
            AppPrefs.log(this, "EARLY EXIT REJECTED — STALE",
                    signal.symbol + " • age " + age + " ms");
            return;
        }
        Strategy strategy = StrategyStore.find(this, signal.eventId);
        if (strategy == null || !strategy.isActive()) {
            AppPrefs.log(this, "EARLY EXIT IGNORED — NO ACTIVE STRATEGY",
                    signal.symbol + " • " + signal.phrase);
            return;
        }

        boolean newlyQueued = !strategy.earlyExitRequested;
        strategy.requestEarlyExit("Multyfi: " + signal.phrase,
                signal.notificationTimeMillis);
        StrategyStore.upsert(this, strategy);
        if (newlyQueued) {
            AppPrefs.log(this, "MULTYFI EARLY EXIT PERSISTED",
                    signal.symbol + " • " + signal.phrase
                            + " • new entries are paused until Groww confirms the position is zero.");
        }
        StrategyMonitorService.requestImmediateTick(this, signal.eventId);
    }
'''
replace_java_method(service, "    private void queueEarlyExit(", queue_early_exit)

# Do not accept a new Multyfi buy while any prior early exit remains unresolved.
text = read(service)
old = '''            if (SignalParser.containsEarlyExitPhrase(rawText)) {
                AppPrefs.log(this, "EARLY EXIT IGNORED — SYMBOL NOT UNIQUE",
                        "An exit phrase did not identify exactly one active strategy. No sell was submitted.\n"
                                + compact(rawText));
                return;
            }

            double buffer = AppPrefs.entryBufferPercent(this);'''
new = '''            if (SignalParser.containsEarlyExitPhrase(rawText)) {
                AppPrefs.log(this, "EARLY EXIT IGNORED — SYMBOL NOT UNIQUE",
                        "An exit phrase did not identify exactly one active filled strategy. No sell was submitted.\n"
                                + compact(rawText));
                return;
            }
            if (hasPendingEarlyExit(active)) {
                AppPrefs.log(this, "NEW ENTRY BLOCKED — EARLY EXIT PENDING",
                        "A previous Multyfi exit is still awaiting broker-confirmed zero position.\n"
                                + compact(rawText));
                return;
            }

            double buffer = AppPrefs.entryBufferPercent(this);'''
if old not in text:
    raise RuntimeError("Could not locate early-exit gate in ProductionNotificationService")
text = text.replace(old, new, 1)
helper = r'''    private static boolean hasPendingEarlyExit(List<Strategy> strategies) {
        if (strategies == null) return false;
        for (Strategy strategy : strategies) {
            if (strategy != null && strategy.isActive()
                    && strategy.earlyExitRequested) return true;
        }
        return false;
    }

'''
marker = "    private boolean ensureStaticPublicIp() {\n"
if text.count(marker) != 1:
    raise RuntimeError("Could not locate ProductionNotificationService helper marker")
write(service, text.replace(marker, helper + marker, 1))

# Position reconciliation now precedes protection. A manual sale immediately
# closes the local strategy even if VPN/IP is subsequently disabled. Early exits
# remain highest priority after actual position reconciliation.
monitor = JAVA / "StrategyMonitorService.java"
process_strategy = r'''    private void processStrategy(String token, Strategy strategy,
                                 boolean staticIpReady) {
        if (Strategy.CLOSED.equals(strategy.state)
                || Strategy.ERROR.equals(strategy.state)) return;

        if (strategy.entryMode != null
                && strategy.entryMode.startsWith("PENDING_")) {
            if (!reconcilePendingEntry(token, strategy)) return;
        }

        GrowwClient.IntResult position = GrowwClient.getNetPositionQuantity(
                token, strategy.symbol, strategy.productType);
        if (!position.success) return;
        int remaining = strategy.remainingStrategyQuantity(position.value);

        if (Strategy.TARGET_SELL_PENDING.equals(strategy.state)) {
            processExitPending(token, strategy, remaining, staticIpReady);
            return;
        }

        int filled = detectFilledQuantity(token, strategy, remaining);
        if (filled > strategy.observedFilledQuantity) {
            strategy.observedFilledQuantity = Math.min(strategy.requestedQuantity, filled);
            strategy.lastMessage = "Observed " + strategy.productType + " fill: "
                    + strategy.observedFilledQuantity + " of "
                    + strategy.requestedQuantity + ".";
            AppPrefs.log(this, "ENTRY FILL OBSERVED",
                    strategy.symbol + " • " + strategy.lastMessage);
        }

        // Manual exits and already-completed broker exits must be reconciled
        // before any stop-loss or VPN gate. This fixes the LANDMARK log storm.
        if (remaining <= 0 && strategy.observedFilledQuantity > 0) {
            closeStrategy(strategy,
                    "Groww position is zero; automatic or manual exit completed.");
            return;
        }

        if (strategy.earlyExitRequested) {
            processEarlyExit(token, strategy, remaining, staticIpReady);
            return;
        }

        if (strategy.observedFilledQuantity > strategy.protectedQuantity) {
            if (!staticIpReady) {
                String message = "CRITICAL: Newly filled shares require stop-loss protection, but Surfshark/IP readiness is invalid.";
                boolean changed = !message.equals(strategy.lastMessage);
                strategy.lastMessage = message;
                save(strategy);
                if (changed) {
                    AppPrefs.log(this, "UNPROTECTED FILL — NETWORK GATE FAILED",
                            strategy.symbol + " • " + strategy.lastMessage
                                    + " Reconnect the whitelisted VPN immediately.");
                }
                return;
            }
            if (!protectNewFill(token, strategy)) return;
        }

        if (isEntryCutoffReached(strategy)
                && strategy.observedFilledQuantity < strategy.requestedQuantity
                && strategy.hasPendingEntryHandle()) {
            if (staticIpReady) cancelEntryRemainder(token, strategy);
            else strategy.lastMessage = "Entry cutoff reached, but entry cancellation is blocked by Surfshark/IP mismatch.";
        }

        if (strategy.observedFilledQuantity <= 0) {
            if (isEntryCutoffReached(strategy) && !strategy.hasPendingEntryHandle()) {
                closeStrategy(strategy, "Entry order expired/cancelled without a fill.");
            } else {
                strategy.state = Strategy.ENTRY_ACTIVE;
                save(strategy);
            }
            return;
        }

        if (strategy.protectedQuantity < strategy.observedFilledQuantity) {
            strategy.state = Strategy.ENTRY_ACTIVE;
            save(strategy);
            return;
        }

        strategy.state = Strategy.PROTECTED;
        if (anyStopLegTriggered(token, strategy)) {
            strategy.lastMessage = "Stop-loss protection has triggered; waiting for position settlement.";
            save(strategy);
            return;
        }

        if (!isMarketSession()) return;
        if (strategy.isIntraday() && isIntradayForceExitTime()) {
            executeExit(token, strategy, staticIpReady, EXIT_INTRADAY_TIME);
            return;
        }

        GrowwClient.DoubleResult ltp = GrowwClient.getLtp(token, strategy.symbol);
        if (!ltp.success) {
            save(strategy);
            return;
        }
        if (ltp.value >= strategy.targetPrice) {
            executeExit(token, strategy, staticIpReady, EXIT_TARGET);
        } else {
            strategy.lastMessage = "Protected " + strategy.protectedQuantity + " "
                    + strategy.productType + " shares • LTP ₹" + money(ltp.value)
                    + " • target ₹" + money(strategy.targetPrice) + ".";
            save(strategy);
        }
    }
'''
replace_java_method(monitor, "    private void processStrategy(", process_strategy)

# Keep the exit request durable through market closure and temporary VPN/IP
# failures. Once connectivity returns, the same persisted request is retried.
process_early_exit = r'''    private void processEarlyExit(String token, Strategy strategy, int remaining,
                                  boolean staticIpReady) {
        if (remaining <= 0) {
            closeStrategy(strategy,
                    "Groww position is zero; Multyfi early exit is complete.");
            return;
        }
        if (!isMarketSession()) {
            updateMessageIfChanged(strategy,
                    "Multyfi early exit is persisted for the next market session; no new entries are allowed meanwhile.");
            return;
        }
        if (!staticIpReady) {
            updateMessageIfChanged(strategy,
                    "Multyfi early exit is persisted but waiting for the whitelisted Surfshark IP. No new entries are allowed.");
            return;
        }

        if (!cancelEntryAndVerify(token, strategy)) {
            updateMessageIfChanged(strategy,
                    "Multyfi early exit is persisted; waiting for the entry order/remainder to become cancelled or terminal.");
            return;
        }

        GrowwClient.IntResult refreshed = GrowwClient.getNetPositionQuantity(
                token, strategy.symbol, strategy.productType);
        if (!refreshed.success) {
            updateMessageIfChanged(strategy,
                    "Multyfi early exit is persisted; Groww position reconciliation is temporarily unavailable.");
            return;
        }
        remaining = strategy.remainingStrategyQuantity(refreshed.value);
        int filled = detectFilledQuantity(token, strategy, remaining);
        strategy.observedFilledQuantity = Math.max(strategy.observedFilledQuantity,
                Math.min(strategy.requestedQuantity, filled));
        if (remaining <= 0) {
            closeStrategy(strategy,
                    "Multyfi early exit completed or the position was manually sold.");
            return;
        }
        executeExit(token, strategy, true, EXIT_MULTYFI_EARLY);
    }
'''
replace_java_method(monitor, "    private void processEarlyExit(", process_early_exit)

message_helper = r'''    private void updateMessageIfChanged(Strategy strategy, String message) {
        if (message.equals(strategy.lastMessage)) return;
        strategy.lastMessage = message;
        save(strategy);
        AppPrefs.log(this, "EARLY EXIT WAITING — WILL RETRY",
                strategy.symbol + " • " + message);
    }

'''
text = read(monitor)
marker = "    private int detectFilledQuantity(String token, Strategy strategy,\n"
if text.count(marker) != 1:
    raise RuntimeError("Could not locate monitor early-exit helper marker")
write(monitor, text.replace(marker, message_helper + marker, 1))

# Visible version wording.
activity = JAVA / "ProductionActivity.java"
write(activity, read(activity).replace("2.2.7", "2.2.8"))

# Parser and state-reconciliation regression tests.
write(TEST / "DurableEarlyExitTest.java", r'''package com.suhas.multyfiautobuy.stable;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertNotNull;
import static org.junit.Assert.assertNull;
import static org.junit.Assert.assertTrue;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

import org.junit.Test;

public class DurableEarlyExitTest {
    private Strategy strategy(String symbol, int filled) {
        Strategy strategy = new Strategy("event-" + symbol, symbol,
                "INTRADAY", "MIS", 10, 110d, 95d, 0,
                "REF" + symbol, "", "ORDER" + symbol,
                "REGULAR_LIMIT", System.currentTimeMillis(),
                System.currentTimeMillis() + 60_000L);
        strategy.observedFilledQuantity = filled;
        return strategy;
    }

    @Test public void matchesDisciplinedEarlyExitWithCompanyName() {
        Strategy landmark = strategy("LANDMARK", 10);
        SignalParser.EarlyExitSignal signal = SignalParser.parseEarlyExit(
                "Landmark Cars Update: We're choosing a disciplined early exit against the planned target",
                System.currentTimeMillis(), Arrays.asList(landmark));
        assertNotNull(signal);
        assertEquals("LANDMARK", signal.symbol);
    }

    @Test public void symbolLessUpdateSelectsOnlyFilledStrategy() {
        Strategy landmark = strategy("LANDMARK", 10);
        SignalParser.EarlyExitSignal signal = SignalParser.parseEarlyExit(
                "Update: We're choosing a disciplined early exit against the planned target",
                System.currentTimeMillis(), Arrays.asList(landmark));
        assertNotNull(signal);
        assertEquals(landmark.eventId, signal.eventId);
    }

    @Test public void ambiguousSymbolLessUpdateNeverSelectsTwoStrategies() {
        List<Strategy> active = new ArrayList<>();
        active.add(strategy("LANDMARK", 10));
        active.add(strategy("LASERPOWER", 5));
        assertNull(SignalParser.parseEarlyExit(
                "Update: We're choosing a disciplined early exit against the planned target",
                System.currentTimeMillis(), active));
    }

    @Test public void requestEarlyExitIsDurableState() {
        Strategy landmark = strategy("LANDMARK", 10);
        landmark.requestEarlyExit("disciplined early exit", System.currentTimeMillis());
        assertTrue(landmark.earlyExitRequested);
        assertTrue(landmark.lastMessage.toLowerCase().contains("queued"));
    }
}
''')

# Build-time safety contract.
parser_text = read(parser)
service_text = read(service)
monitor_text = read(monitor)
assert "versionName '2.2.8'" in read(gradle)
assert "MULTYFI EARLY EXIT PERSISTED" in service_text
assert "NEW ENTRY BLOCKED — EARLY EXIT PENDING" in service_text
assert "exactly one filled Multyfi strategy" in parser_text
assert "compactIdentity" in parser_text
assert "Groww position is zero; automatic or manual exit completed" in monitor_text
assert "EARLY EXIT WAITING — WILL RETRY" in monitor_text
assert "Reconnect the whitelisted VPN immediately" in monitor_text
assert "processResearch360" in service_text
assert "MIS STOP-LOSS ORDER CONFIRMED" in monitor_text
assert "MIS BLOCKED BY GROWW — TRYING CNC SAME-DAY FALLBACK" in service_text
print("Applied v2.2.8 durable Multyfi early-exit and reconciliation fix")

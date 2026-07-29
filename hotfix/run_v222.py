#!/usr/bin/env python3
from pathlib import Path
import re
import runpy

# Build strictly on the validated v2.2.1 notification-routing release.
runpy.run_path("hotfix/run_v221_safe.py", run_name="__main__")

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
    updated, count = re.subn(pattern, lambda _match: replacement,
                             text, count=1, flags=re.S)
    if count != 1:
        raise RuntimeError(f"Expected exactly one regex match in {path}: found {count}")
    write(path, updated)


# Release identity.
gradle = ROOT / "app/build.gradle"
replace_once(gradle, "versionCode 221", "versionCode 222")
replace_once(gradle, "versionName '2.2.1'", "versionName '2.2.2'")

# Pure retry policy: an unavailable VPN/IP must not consume the retry timer.
write(JAVA / "DailyAuthRetryPolicy.java", r'''package com.suhas.multyfiautobuy.stable;

final class DailyAuthRetryPolicy {
    private DailyAuthRetryPolicy() { }

    static boolean shouldAttempt(boolean alreadyVerified,
                                 boolean networkReady,
                                 boolean vpnReady,
                                 boolean staticIpReady,
                                 long nowMillis,
                                 long lastAttemptMillis,
                                 long retryIntervalMillis) {
        if (alreadyVerified || !networkReady || !vpnReady || !staticIpReady) return false;
        return lastAttemptMillis <= 0L
                || nowMillis - lastAttemptMillis >= retryIntervalMillis;
    }
}
''')

# One source of truth for automatic daily Groww profile/DDPI verification.
write(JAVA / "DailyAuthManager.java", r'''package com.suhas.multyfiautobuy.stable;

import android.content.Context;

/** Automatic read-only Groww verification using one-time saved credentials. */
final class DailyAuthManager {
    private DailyAuthManager() { }

    static synchronized Result ensureVerified(Context context) {
        if (context == null) return Result.failure("Application context is unavailable.");
        if (AppPrefs.isAuthVerifiedToday(context)) {
            return Result.success("Groww account and DDPI are already verified today.");
        }
        if (!SecureStore.has(context, SecureStore.API_KEY)
                || !SecureStore.has(context, SecureStore.TOTP_SECRET)) {
            return Result.failure("Saved Groww API key or TOTP secret is missing.");
        }
        if (!NetworkUtil.isNetworkAvailable(context)) {
            return Result.failure("Network is unavailable.");
        }
        if (!NetworkUtil.isVpnActive(context)) {
            return Result.failure("Surfshark Dedicated IP VPN is not active.");
        }
        String expected = AppPrefs.expectedIp(context);
        if (!AppPrefs.isStaticConfirmed(context) || expected.isEmpty()) {
            return Result.failure("The Groww-whitelisted Dedicated IP is not confirmed.");
        }
        if (!AppPrefs.isIpRecentlyVerified(context)) {
            try {
                String actual = NetworkUtil.fetchPublicIp();
                boolean match = expected.equals(actual);
                AppPrefs.setIpVerification(context, actual, match);
                if (!match) {
                    return Result.failure("Current public IP " + actual
                            + " does not match the Groww-whitelisted IP " + expected + ".");
                }
            } catch (Exception e) {
                AppPrefs.setIpVerifiedAt(context, 0L);
                return Result.failure("Dedicated IP verification failed: " + safeMessage(e));
            }
        }

        String token = TokenManager.validToken(context);
        if (token.isEmpty()) {
            AppPrefs.clearAuthVerified(context);
            return Result.failure("Groww token could not be generated from the saved credentials.");
        }
        GrowwClient.ApiResult profile = GrowwClient.verifyProfile(token);
        if (!profile.success) {
            AppPrefs.clearAuthVerified(context);
            return Result.failure(profile.message);
        }
        AppPrefs.setAuthVerified(context, profile.id);
        TradeEventNotifier.clearPause(context);
        return Result.success(profile.message);
    }

    private static String safeMessage(Exception e) {
        if (e == null) return "unknown error";
        String message = e.getMessage();
        return message == null || message.trim().isEmpty()
                ? e.getClass().getSimpleName() : message.trim();
    }

    static final class Result {
        final boolean success;
        final String message;

        private Result(boolean success, String message) {
            this.success = success;
            this.message = message == null ? "" : message;
        }

        static Result success(String message) { return new Result(true, message); }
        static Result failure(String message) { return new Result(false, message); }
    }
}
''')

# Background monitor: retry as soon as VPN + whitelisted IP become ready.
monitor = JAVA / "StrategyMonitorService.java"
replace_once(monitor,
             "private static final long AUTH_CHECK_INTERVAL_MS = 5L * 60L * 1000L;",
             "private static final long AUTH_CHECK_INTERVAL_MS = 60_000L;")
replace_once(monitor,
             "            preflightAuthenticationIfDue(networkReady);",
             "            preflightAuthenticationIfDue(networkReady, vpnReady, staticIpReady);")

new_preflight = r'''    private void preflightAuthenticationIfDue(boolean networkReady,
                                                boolean vpnReady,
                                                boolean staticIpReady) {
        if (!isPreflightWindow()) return;
        long now = System.currentTimeMillis();
        if (!DailyAuthRetryPolicy.shouldAttempt(
                AppPrefs.isAuthVerifiedToday(this), networkReady, vpnReady,
                staticIpReady, now, lastAuthCheckAt, AUTH_CHECK_INTERVAL_MS)) return;
        lastAuthCheckAt = now;
        DailyAuthManager.Result result = DailyAuthManager.ensureVerified(this);
        if (result.success) {
            AppPrefs.log(this, "AUTOMATIC DAILY GROWW READY",
                    result.message + " No manual login or read-only button was required.");
            return;
        }
        AppPrefs.log(this, "AUTOMATIC DAILY GROWW PENDING", result.message
                + " Armed state remains ON and verification will retry automatically.");
        if (isAfterNine() && AppPrefs.isArmed(this)) {
            TradeEventNotifier.notifyTradingPaused(this,
                    "Automatic Groww verification is pending: " + result.message);
        }
    }

'''
replace_regex_once(
    monitor,
    r"    private void preflightAuthenticationIfDue\(boolean networkReady\) \{.*?(?=    private void processStrategy)",
    new_preflight
)
replace_once(monitor,
             "return minute >= 8 * 60 + 35 && minute <= MARKET_END;",
             "return minute >= 8 * 60 && minute <= MARKET_END;")
replace_once(
    monitor,
    '''        String text = (AppPrefs.isArmed(this) ? "Entries armed" : "New entries off")
                + " • " + active + " active strateg" + (active == 1 ? "y" : "ies")
                + " • Surfshark " + (NetworkUtil.isVpnActive(this) ? "on" : "off")
                + " • IP " + (ip.isEmpty() ? "unchecked" : ip);''',
    '''        String text = (AppPrefs.isArmed(this) ? "Entries armed" : "New entries off")
                + " • " + active + " active strateg" + (active == 1 ? "y" : "ies")
                + " • Groww " + (AppPrefs.isAuthVerifiedToday(this) ? "ready" : "auto-check pending")
                + " • Surfshark " + (NetworkUtil.isVpnActive(this) ? "on" : "off")
                + " • IP " + (ip.isEmpty() ? "unchecked" : ip);'''
)

# Incoming Multyfi signal: one final automatic read-only verification before
# rejecting a fresh signal because the daily status has not yet been recorded.
listener = JAVA / "ProductionNotificationService.java"
auth_gate = r'''            if (!NetworkUtil.isNetworkAvailable(this)) {
                AppPrefs.log(this, "REJECTED — OFFLINE", summary);
                return;
            }
            if (!NetworkUtil.isVpnActive(this)) {
                rejectAndDisarm("Surfshark Dedicated IP VPN is not active.", summary);
                return;
            }
            if (!ensureStaticPublicIp()) {
                rejectAndDisarm(
                        "Current public IP does not match the Groww-whitelisted Surfshark Dedicated IP.",
                        summary);
                return;
            }
            if (!AppPrefs.isAuthVerifiedToday(this)) {
                DailyAuthManager.Result automatic = DailyAuthManager.ensureVerified(this);
                if (!automatic.success) {
                    rejectAndDisarm("Automatic Groww verification failed: "
                            + automatic.message, summary);
                    return;
                }
                AppPrefs.log(this, "SIGNAL-TIME GROWW VERIFICATION READY",
                        signal.symbol + " • " + automatic.message);
            }
'''
replace_regex_once(
    listener,
    r'''            if \(!AppPrefs\.isAuthVerifiedToday\(this\)\) \{.*?            if \(!ensureStaticPublicIp\(\)\) \{.*?                return;\n            \}\n''',
    auth_gate
)

# Dashboard: pending automatic verification is not presented as a daily login.
activity = JAVA / "ProductionActivity.java"
replace_once(activity,
             '"Android 16 • source-built stable release 2.2.1"',
             '"Android 16 • source-built candidate release 2.2.2"')
replace_once(activity,
             '"Auto-Buy OFF by default • Intraday/MIS => MIS LIMIT • otherwise => CNC GTT • source-built v2.2.1"',
             '"Auto-Buy OFF by default • automatic daily Groww verification • source-built v2.2.2"')
replace_once(activity,
             ': "● Groww connection + DDPI: not verified today");',
             ': "● Groww connection + DDPI: automatic verification pending");')

new_activity_auto = r'''    private void refreshAuthenticationAutomatically() {
        if (automaticAuthRunning || AppPrefs.isAuthVerifiedToday(this)) return;
        if (!SecureStore.has(this, SecureStore.API_KEY)
                || !SecureStore.has(this, SecureStore.TOTP_SECRET)) return;
        automaticAuthRunning = true;
        executor.execute(() -> {
            DailyAuthManager.Result result = DailyAuthManager.ensureVerified(this);
            AppPrefs.log(this,
                    result.success ? "AUTOMATIC DAILY AUTH READY"
                            : "AUTOMATIC DAILY AUTH WAITING",
                    result.message + (result.success
                            ? " No credential re-entry was required."
                            : " The background monitor will retry automatically."));
            runOnUiThread(() -> {
                automaticAuthRunning = false;
                refreshStatus();
            });
        });
    }

'''
replace_regex_once(
    activity,
    r"    private void refreshAuthenticationAutomatically\(\) \{.*?(?=    private void authenticateToday)",
    new_activity_auto
)

old_readiness = '''        if (!AppPrefs.isAuthVerifiedToday(this)) return "Run the read-only Groww connection test today";
        if (!NetworkUtil.isVpnActive(this)) return "Connect Surfshark Dedicated IP";
        if (!AppPrefs.isStaticConfirmed(this)) return "Confirm the exact IP is whitelisted in Groww";
        if (AppPrefs.expectedIp(this).isEmpty()) return "Enter the Groww-whitelisted Dedicated IP";
        if (!AppPrefs.isIpRecentlyVerified(this)) return "Detect and verify the current Dedicated IP";'''
new_readiness = '''        if (!NetworkUtil.isVpnActive(this)) return "Connect Surfshark Dedicated IP; automatic Groww verification will then resume";
        if (!AppPrefs.isStaticConfirmed(this)) return "Confirm the exact IP is whitelisted in Groww";
        if (AppPrefs.expectedIp(this).isEmpty()) return "Enter the Groww-whitelisted Dedicated IP";
        if (!AppPrefs.isIpRecentlyVerified(this)) return "Waiting for automatic Dedicated IP verification";
        if (!AppPrefs.isAuthVerifiedToday(this)) return "Automatic Groww verification is retrying; no manual login is required";'''
replace_once(activity, old_readiness, new_readiness)

# Regression tests for the exact failure mode observed on the S24 Ultra.
write(TEST / "DailyAuthRetryPolicyTest.java", r'''package com.suhas.multyfiautobuy.stable;

import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import org.junit.Test;

public class DailyAuthRetryPolicyTest {
    @Test public void vpnOffDoesNotConsumeRetryWindow() {
        long now = 1_000_000L;
        assertFalse(DailyAuthRetryPolicy.shouldAttempt(
                false, true, false, false, now, 0L, 60_000L));
        assertTrue(DailyAuthRetryPolicy.shouldAttempt(
                false, true, true, true, now + 1L, 0L, 60_000L));
    }

    @Test public void verifiedDayNeverRepeatsProfileCheck() {
        assertFalse(DailyAuthRetryPolicy.shouldAttempt(
                true, true, true, true, 100_000L, 0L, 60_000L));
    }

    @Test public void brokerFailureRetriesAfterOneMinute() {
        assertFalse(DailyAuthRetryPolicy.shouldAttempt(
                false, true, true, true, 159_999L, 100_000L, 60_000L));
        assertTrue(DailyAuthRetryPolicy.shouldAttempt(
                false, true, true, true, 160_000L, 100_000L, 60_000L));
    }
}
''')

# Build-time source contract.
assert "versionName '2.2.2'" in read(gradle)
assert "DailyAuthManager.ensureVerified(this)" in read(listener)
assert "DailyAuthRetryPolicy.shouldAttempt" in read(monitor)
assert "no manual login is required" in read(activity)
assert "Run the read-only Groww connection test today" not in read(activity)
assert "NotificationRoutePolicy.entryMode(signal)" in read(listener)
assert "0.10d" in read(JAVA / "GrowwClient.java")
print("Applied Multyfi AutoBuy Pro v2.2.2 automatic daily Groww verification candidate")

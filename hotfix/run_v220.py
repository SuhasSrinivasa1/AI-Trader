#!/usr/bin/env python3
from pathlib import Path
import re
import runpy
import tempfile

source = Path("hotfix/apply_v220.py").read_text(encoding="utf-8")

summary_block = re.compile(
    r"old = '''\s+String productType, int quantity,.*?text = text\.replace\(old, new, 1\)",
    re.S,
)
summary_replacement = r'''signature_pattern = re.compile(
    r"(String productType, int quantity,\n\s*)boolean freeRecommendation\) \{"
)
text, count = signature_pattern.subn(
    r"\1boolean freeRecommendation, double freeBudget) {", text, count=1
)
if count != 1:
    raise RuntimeError("Could not update summary signature")'''
source, count = summary_block.subn(lambda match: summary_replacement, source, count=1)
if count != 1:
    raise RuntimeError("Could not normalize v2.2.0 summary signature patch block")

reject_block = re.compile(
    r"old = '''    private void rejectAndDisarm\(String reason, String summary\) \{.*?text = text\.replace\(old, new, 1\)",
    re.S,
)
reject_replacement = r'''reject_pattern = re.compile(
    r"(    private void rejectAndDisarm\(String reason, String summary\) \{.*?)(\n    \})",
    re.S,
)
text, count = reject_pattern.subn(
    r"\1\n        TradeEventNotifier.notifyTradingPaused(this, reason);\2",
    text,
    count=1,
)
if count != 1:
    raise RuntimeError("Could not add intake pause notification")'''
source, count = reject_block.subn(lambda match: reject_replacement, source, count=1)
if count != 1:
    raise RuntimeError("Could not normalize v2.2.0 intake pause patch block")

with tempfile.NamedTemporaryFile("w", suffix=".py", encoding="utf-8", delete=False) as handle:
    handle.write(source)
    fixed = handle.name

runpy.run_path(fixed, run_name="__main__")

# Groww waives its own DP fee for debit values below ₹100, but the depository
# component still applies. Use the conservative male-account ₹3.50 component.
charge_file = Path("android-stable/app/src/main/java/com/suhas/multyfiautobuy/stable/DeliveryChargeCalculator.java")
charge_source = charge_file.read_text(encoding="utf-8")
old_dp = "double dp = sellValue < 100d ? 0d : DP_SELL_CHARGE;"
new_dp = "double dp = sellValue < 100d ? 3.50d : DP_SELL_CHARGE;"
if old_dp not in charge_source:
    raise RuntimeError("Could not correct low-value DP charge")
charge_file.write_text(charge_source.replace(old_dp, new_dp, 1), encoding="utf-8")

# v2.0.2 generated a fixed-10 test. Replace it with the v2.2.0 configurable-budget contract.
test = Path("android-stable/app/src/test/java/com/suhas/multyfiautobuy/stable/FreeRecommendationPolicyTest.java")
test.write_text(r'''package com.suhas.multyfiautobuy.stable;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import org.junit.Test;

public class FreeRecommendationPolicyTest {
    @Test public void detectsStandaloneFreeWordCaseInsensitively() {
        assertTrue(SignalParser.isFreeRecommendation("Today's Free Equity Recommendation"));
        assertTrue(SignalParser.isFreeRecommendation("FREE recommendation"));
        assertFalse(SignalParser.isFreeRecommendation("Equity recommendation"));
        assertFalse(SignalParser.isFreeRecommendation("freestyle equity recommendation"));
    }

    @Test public void freeRecommendationUsesConfiguredAmount() {
        assertEquals(5, OrderPolicy.quantity(true, 10_000d, 5_000d, 1_000d));
        assertEquals(0, OrderPolicy.quantity(true, 10_000d, 5_000d, 5_001d));
        assertEquals(100, OrderPolicy.quantity(true, 1_000d, 5_000d, 50d));
        assertFalse(OrderPolicy.usesWindowBudget(true));
    }

    @Test public void normalRecommendationKeepsWindowBudgetSizing() {
        assertEquals(2, OrderPolicy.quantity(false, 10_000d, 5_000d, 4_000d));
        assertTrue(OrderPolicy.usesWindowBudget(false));
    }
}
''', encoding="utf-8")

charge_test = Path("android-stable/app/src/test/java/com/suhas/multyfiautobuy/stable/DeliveryChargeCalculatorTest.java")
charge_text = charge_test.read_text(encoding="utf-8")
needle = '''    @Test public void largerQuantityStillMeetsTarget() {
        double target = DeliveryChargeCalculator.requiredSellPrice(500d, 20, 6d);
        assertTrue(DeliveryChargeCalculator.estimatedNetProfit(500d, target, 20) >= 600d - 1e-6d);
    }
}'''
replacement = '''    @Test public void largerQuantityStillMeetsTarget() {
        double target = DeliveryChargeCalculator.requiredSellPrice(500d, 20, 6d);
        assertTrue(DeliveryChargeCalculator.estimatedNetProfit(500d, target, 20) >= 600d - 1e-6d);
    }

    @Test public void lowValueSaleStillIncludesDepositoryComponent() {
        double target = DeliveryChargeCalculator.requiredSellPrice(40d, 1, 6d);
        assertTrue(DeliveryChargeCalculator.estimatedNetProfit(40d, target, 1) >= 2.4d - 1e-6d);
    }
}'''
if needle not in charge_text:
    raise RuntimeError("Could not extend low-value charge test")
charge_test.write_text(charge_text.replace(needle, replacement, 1), encoding="utf-8")

# Tick-size hotfix r1. NSE CASH instruments currently use ₹0.01, ₹0.05 or
# ₹0.10 price grids. Normalising generated order prices to ₹0.10 keeps them
# valid on all three grids and prevents rejections such as STYRENIX ₹2,573.45.
tick_files = [
    "DeliveryChargeCalculator.java",
    "GrowwClient.java",
    "ImageBatchExecutor.java",
    "ImageOrderParser.java",
    "ProductionActivity.java",
    "SignalParser.java",
]
java_root = Path("android-stable/app/src/main/java/com/suhas/multyfiautobuy/stable")
for filename in tick_files:
    path = java_root / filename
    text = path.read_text(encoding="utf-8")
    count = text.count("0.05d")
    if count < 1:
        raise RuntimeError(f"No ₹0.05 tick constant found in {filename}")
    path.write_text(text.replace("0.05d", "0.10d"), encoding="utf-8")

# One-time credentials and automatic daily token/profile refresh. Blank secure
# fields preserve their stored value; users only re-enter credentials to change them.
activity = java_root / "ProductionActivity.java"
text = activity.read_text(encoding="utf-8")
ui_replacements = {
    "Credentials remain encrypted by Android Keystore. The connection test is read-only. The one-share test creates a real CNC GTT approximately 10% below LTP and immediately cancels it.":
        "Credentials are stored once in Android Keystore and the daily Groww token is generated automatically. The connection test is read-only. Re-enter credentials only when changing them.",
    "Groww API key — leave blank to keep saved value":
        "Groww API key — saved once; only edit to change",
    "Groww Base32 TOTP secret — leave blank to keep saved value":
        "Groww TOTP secret — securely saved; only edit to change it",
    "Today’s access token — optional":
        "Today’s token — automatic daily",
    "AUTHENTICATE TODAY":
        "REFRESH TOKEN NOW",
    "API key saved securely":
        "API key saved one-time",
    "TOTP secret saved securely":
        "TOTP stored for auto-auth",
    "Access token saved for today":
        "Daily token auto-refreshed",
    "Today’s access token (optional)":
        "Today’s token auto-generated",
}
for old, new in ui_replacements.items():
    if old not in text:
        raise RuntimeError(f"Could not update one-time credential UI: {old}")
    text = text.replace(old, new, 1)

field_marker = "    private boolean windowsDirty;\n"
if field_marker not in text:
    raise RuntimeError("Could not add automaticAuthRunning field")
text = text.replace(field_marker, field_marker + "    private boolean automaticAuthRunning;\n", 1)

resume_marker = "        StrategyMonitorService.ensureRunning(this);\n        refreshStatus();"
if text.count(resume_marker) != 2:
    raise RuntimeError("Expected onCreate and onResume monitor/status markers")
text = text.replace(resume_marker,
                    "        StrategyMonitorService.ensureRunning(this);\n"
                    "        refreshAuthenticationAutomatically();\n"
                    "        refreshStatus();", 2)

auth_marker = "    private void authenticateToday(Button button) {\n"
auto_method = '''    private void refreshAuthenticationAutomatically() {
        if (automaticAuthRunning || AppPrefs.isAuthVerifiedToday(this)) return;
        if (!SecureStore.has(this, SecureStore.API_KEY)
                || !SecureStore.has(this, SecureStore.TOTP_SECRET)) return;
        if (!NetworkUtil.isNetworkAvailable(this) || !NetworkUtil.isVpnActive(this)) return;
        automaticAuthRunning = true;
        executor.execute(() -> {
            String token = TokenManager.validToken(this);
            GrowwClient.ApiResult result = token.isEmpty()
                    ? GrowwClient.ApiResult.failure("", "Automatic Groww token refresh failed.", 0)
                    : GrowwClient.verifyProfile(token);
            if (result.success) {
                AppPrefs.setAuthVerified(this, result.id);
                AppPrefs.log(this, "AUTOMATIC DAILY AUTH READY",
                        result.message + " No credential re-entry was required.");
            } else {
                AppPrefs.clearAuthVerified(this);
                AppPrefs.log(this, "AUTOMATIC DAILY AUTH FAILED", result.message);
            }
            runOnUiThread(() -> {
                automaticAuthRunning = false;
                refreshStatus();
            });
        });
    }

'''
if auth_marker not in text:
    raise RuntimeError("Could not insert automatic daily authentication method")
text = text.replace(auth_marker, auto_method + auth_marker, 1)
activity.write_text(text, encoding="utf-8")

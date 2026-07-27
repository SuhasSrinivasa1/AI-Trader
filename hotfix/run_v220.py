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

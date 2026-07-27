package com.suhas.multyfiautobuy.stable;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import org.junit.Test;

public class FreeRecommendationPolicyTest {
    @Test
    public void detectsStandaloneFreeWordCaseInsensitively() {
        assertTrue(SignalParser.isFreeRecommendation("Today's Free Equity Recommendation"));
        assertTrue(SignalParser.isFreeRecommendation("FREE recommendation"));
        assertFalse(SignalParser.isFreeRecommendation("Equity recommendation"));
        assertFalse(SignalParser.isFreeRecommendation("freestyle equity recommendation"));
    }

    @Test
    public void freeRecommendationAlwaysUsesTenShares() {
        assertEquals(10, OrderPolicy.quantity(true, 1_000d, 6_975d));
        assertEquals(10, OrderPolicy.quantity(true, 500_000d, 50d));
        assertFalse(OrderPolicy.usesWindowBudget(true));
    }

    @Test
    public void normalRecommendationKeepsBudgetSizing() {
        assertEquals(2, OrderPolicy.quantity(false, 10_000d, 4_000d));
        assertTrue(OrderPolicy.usesWindowBudget(false));
    }
}

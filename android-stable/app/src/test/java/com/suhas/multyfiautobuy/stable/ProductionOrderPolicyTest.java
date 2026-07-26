package com.suhas.multyfiautobuy.stable;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import org.junit.Test;

public final class ProductionOrderPolicyTest {
    @Test
    public void earlyWindowAlwaysUsesImmediateMisLimit() {
        AppPrefs.TradeWindow window = new AppPrefs.TradeWindow(
                1, "09:00–09:30", 10_000d, true, 0L);

        assertEquals(OrderPolicy.EntryMode.IMMEDIATE_MIS_LIMIT,
                OrderPolicy.entryMode(window));
        assertEquals("MIS", OrderPolicy.productType(window));
        assertFalse(OrderPolicy.usesEntryGtt(window));
    }

    @Test
    public void allLaterWindowsAlwaysUseCncEntryGtt() {
        AppPrefs.TradeWindow middle = new AppPrefs.TradeWindow(
                2, "09:30–10:00", 10_000d, false, 0L);
        AppPrefs.TradeWindow late = new AppPrefs.TradeWindow(
                3, "10:00–15:30", 5_000d, false, 0L);

        assertEquals(OrderPolicy.EntryMode.CNC_ENTRY_GTT,
                OrderPolicy.entryMode(middle));
        assertEquals(OrderPolicy.EntryMode.CNC_ENTRY_GTT,
                OrderPolicy.entryMode(late));
        assertEquals("CNC", OrderPolicy.productType(middle));
        assertEquals("CNC", OrderPolicy.productType(late));
        assertTrue(OrderPolicy.usesEntryGtt(middle));
        assertTrue(OrderPolicy.usesEntryGtt(late));
    }

    @Test
    public void sizingAlwaysRoundsDownToSavedBudget() {
        assertEquals(3, AppPrefs.quantityForBudget(10_000d, 3_100d));
        assertEquals(0, AppPrefs.quantityForBudget(1_000d, 1_001d));
    }
}

package com.suhas.multyfiautobuy.stable;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertNotNull;
import static org.junit.Assert.assertNull;
import static org.junit.Assert.assertTrue;

import org.junit.Test;

import java.time.ZoneId;
import java.time.ZonedDateTime;

public class SignalParserTest {
    @Test
    public void parsesCompleteSignalAndAppliesProtection() {
        String sample = "Today’s Free Equity Recommendation\n"
                + "Stock Name : SGFIN\n"
                + "Target: ₹700\n"
                + "Entry Range: ₹681-684\n"
                + "Stop Loss: ₹676";
        SignalParser.ParsedSignal signal = SignalParser.parse(sample, atIst(2026, 7, 24, 9, 0));
        assertNotNull(signal);
        assertEquals("SGFIN", signal.symbol);
        assertEquals(681.00d, signal.entryLow, 0.001d);
        assertEquals(684.00d, signal.entryHigh, 0.001d);
        assertEquals(681.00d, signal.triggerPrice, 0.001d);
        assertEquals(690.80d, signal.maxBuyPrice, 0.001d);
        assertEquals(700.00d, signal.targetPrice, 0.001d);
        assertEquals(676.00d, signal.stopLossPrice, 0.001d);
        assertEquals(6_908d, signal.maximumOrderValue(10), 0.01d);
        assertTrue(signal.summary(10).contains("target ₹700"));
        assertTrue(signal.summary(10).contains("SL ₹676"));
        assertTrue(signal.referenceId.length() >= 8 && signal.referenceId.length() <= 20);
    }

    @Test
    public void supportsSellPriceAliasWithoutTreatingItAsSellAction() {
        String sample = "Equity Recommendation\nStock: TCS\nBuy Price: 3000-3010\n"
                + "Sell Price: 3100\nSL: 2975";
        SignalParser.ParsedSignal signal = SignalParser.parse(sample, atIst(2026, 7, 24, 10, 0));
        assertNotNull(signal);
        assertEquals(3100d, signal.targetPrice, 0.001d);
        assertEquals(2975d, signal.stopLossPrice, 0.001d);
    }

    @Test
    public void rejectsIncompleteAndInconsistentSignals() {
        assertNull(SignalParser.parse(
                "Stock Name: TCS\nEntry Range: 100-110\nTarget: 120", 1L));
        assertNull(SignalParser.parse(
                "Stock Name: TCS\nEntry Range: 100-110\nStop Loss: 95", 1L));
        assertNull(SignalParser.parse(
                "Stock Name: TCS\nEntry Range: 100-110\nTarget: 108\nStop Loss: 95", 1L));
        assertNull(SignalParser.parse(
                "Stock Name: TCS\nEntry Range: 100-110\nTarget: 120\nStop Loss: 105", 1L));
    }

    @Test
    public void rejectsSellActionAndDerivatives() {
        String protectedFields = "\nStock Name: TCS\nEntry Range: 100-110\nTarget: 120\nStop Loss: 95";
        assertNull(SignalParser.parse("SELL NOW" + protectedFields, 1L));
        assertNull(SignalParser.parse("Futures Buy" + protectedFields, 1L));
    }

    @Test
    public void acceptsOnlyConfiguredWeekdaySignalWindow() {
        assertTrue(SignalParser.isAllowedSignalTime(atIst(2026, 7, 24, 8, 45)));
        assertTrue(SignalParser.isAllowedSignalTime(atIst(2026, 7, 24, 15, 25)));
        assertTrue(!SignalParser.isAllowedSignalTime(atIst(2026, 7, 24, 8, 44)));
        assertTrue(!SignalParser.isAllowedSignalTime(atIst(2026, 7, 24, 15, 26)));
        assertTrue(!SignalParser.isAllowedSignalTime(atIst(2026, 7, 25, 10, 0)));
    }

    @Test
    public void validatesQuantityBounds() {
        assertTrue(AppPrefs.isValidQuantity(1));
        assertTrue(AppPrefs.isValidQuantity(10));
        assertTrue(AppPrefs.isValidQuantity(10_000));
        assertTrue(!AppPrefs.isValidQuantity(0));
        assertTrue(!AppPrefs.isValidQuantity(10_001));
    }

    private static long atIst(int year, int month, int day, int hour, int minute) {
        return ZonedDateTime.of(year, month, day, hour, minute, 0, 0,
                ZoneId.of("Asia/Kolkata")).toInstant().toEpochMilli();
    }
}

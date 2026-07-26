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
    public void parsesCompleteSignalWithDefaultOnePointFivePercentBuffer() {
        String sample = "Today’s Free Equity Recommendation\n"
                + "Stock Name : SGFIN\n"
                + "Target: ₹720\n"
                + "Entry Range: ₹681-684\n"
                + "Stop Loss: ₹676";
        SignalParser.ParsedSignal signal = SignalParser.parse(sample,
                atIst(2026, 7, 24, 9, 0));
        assertNotNull(signal);
        assertEquals("SGFIN", signal.symbol);
        assertEquals("FREE_EQUITY", signal.category);
        assertEquals("CNC", signal.productType);
        assertEquals(681.00d, signal.entryLow, 0.001d);
        assertEquals(684.00d, signal.entryHigh, 0.001d);
        assertEquals(681.00d, signal.triggerPrice, 0.001d);
        assertEquals(694.25d, signal.maxBuyPrice, 0.001d);
        assertEquals(720.00d, signal.targetPrice, 0.001d);
        assertEquals(676.00d, signal.stopLossPrice, 0.001d);
        assertEquals(6_942.5d, signal.maximumOrderValue(10), 0.01d);
        assertTrue(signal.summary(10).contains("buffer 1.50%"));
        assertTrue(signal.referenceId.length() >= 8
                && signal.referenceId.length() <= 20);
    }

    @Test
    public void supportsConfiguredTwoPercentBuffer() {
        String sample = "Swing Call\nStock: TCS\nBuy Price: 3000-3010\n"
                + "Sell Price: 3100\nSL: 2975";
        SignalParser.ParsedSignal signal = SignalParser.parse(sample,
                atIst(2026, 7, 24, 10, 0), 2.0d);
        assertNotNull(signal);
        assertEquals("SWING", signal.category);
        assertEquals("CNC", signal.productType);
        assertEquals(3070.20d, signal.maxBuyPrice, 0.001d);
    }

    @Test
    public void classifiesExplicitIntradayAsMis() {
        String sample = "Equity Intraday\nStock Name: SBIN\nBuy Price: 810\n"
                + "Target: 825\nStop Loss: 802";
        SignalParser.ParsedSignal signal = SignalParser.parse(sample,
                atIst(2026, 7, 24, 9, 20), 1.5d);
        assertNotNull(signal);
        assertEquals("INTRADAY", signal.category);
        assertEquals("MIS", signal.productType);
        assertTrue(signal.isIntraday());
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
        String fields = "\nStock Name: TCS\nEntry Range: 100-110\nTarget: 120\nStop Loss: 95";
        assertNull(SignalParser.parse("SELL NOW" + fields, 1L));
        assertNull(SignalParser.parse("Futures Buy" + fields, 1L));
    }

    @Test
    public void acceptsConfiguredWeekdayWindows() {
        assertTrue(SignalParser.isAllowedSignalTime(
                atIst(2026, 7, 24, 8, 45)));
        assertTrue(SignalParser.isAllowedSignalTime(
                atIst(2026, 7, 24, 15, 25)));
        assertTrue(!SignalParser.isAllowedSignalTime(
                atIst(2026, 7, 24, 8, 44)));
        assertTrue(!SignalParser.isAllowedSignalTime(
                atIst(2026, 7, 24, 15, 26)));
        assertTrue(!SignalParser.isAllowedSignalTime(
                atIst(2026, 7, 25, 10, 0)));
        assertTrue(SignalParser.isAllowedIntradayEntryTime(
                atIst(2026, 7, 24, 14, 45)));
        assertTrue(!SignalParser.isAllowedIntradayEntryTime(
                atIst(2026, 7, 24, 14, 46)));
    }

    @Test
    public void validatesQuantityAndBufferBounds() {
        assertTrue(AppPrefs.isValidQuantity(1));
        assertTrue(AppPrefs.isValidQuantity(10));
        assertTrue(AppPrefs.isValidQuantity(10_000));
        assertTrue(!AppPrefs.isValidQuantity(0));
        assertTrue(!AppPrefs.isValidQuantity(10_001));
        assertTrue(AppPrefs.isValidEntryBuffer(0d));
        assertTrue(AppPrefs.isValidEntryBuffer(1.5d));
        assertTrue(AppPrefs.isValidEntryBuffer(2d));
        assertTrue(!AppPrefs.isValidEntryBuffer(-0.01d));
        assertTrue(!AppPrefs.isValidEntryBuffer(2.01d));
    }

    private static long atIst(int year, int month, int day,
                              int hour, int minute) {
        return ZonedDateTime.of(year, month, day, hour, minute, 0, 0,
                ZoneId.of("Asia/Kolkata")).toInstant().toEpochMilli();
    }
}

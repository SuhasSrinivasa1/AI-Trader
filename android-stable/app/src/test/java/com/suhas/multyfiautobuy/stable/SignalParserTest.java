package com.suhas.multyfiautobuy.stable;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertNotNull;
import static org.junit.Assert.assertNull;
import static org.junit.Assert.assertTrue;

import org.junit.Test;

public class SignalParserTest {
    @Test
    public void parsesSampleAndAppliesOnePercentCap() {
        String sample = "Today’s Free Equity Recommendation\n"
                + "Stock Name : SGFIN\n"
                + "Target: ₹700\n"
                + "Entry Range: ₹681-684\n"
                + "Stop Loss: ₹676";
        SignalParser.ParsedSignal signal = SignalParser.parse(sample, 1_700_000_000_000L);
        assertNotNull(signal);
        assertEquals("SGFIN", signal.symbol);
        assertEquals(681.00d, signal.entryLow, 0.001d);
        assertEquals(684.00d, signal.entryHigh, 0.001d);
        assertEquals(681.00d, signal.triggerPrice, 0.001d);
        assertEquals(690.80d, signal.maxBuyPrice, 0.001d);
        assertEquals(69_080d, signal.maximumOrderValue(), 0.01d);
        assertTrue(signal.referenceId.length() >= 8 && signal.referenceId.length() <= 20);
    }

    @Test
    public void rejectsSellAndDerivativeNotifications() {
        assertNull(SignalParser.parse("SELL\nStock Name: TCS\nEntry Range: 100-110", 1L));
        assertNull(SignalParser.parse("Futures Buy\nStock Name: TCS\nEntry Range: 100-110", 1L));
    }

    @Test
    public void requiresStockAndEntryRange() {
        assertNull(SignalParser.parse("Stock Name: TCS", 1L));
        assertNull(SignalParser.parse("Entry Range: 100-110", 1L));
    }
}

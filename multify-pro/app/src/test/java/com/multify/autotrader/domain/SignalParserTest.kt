package com.multify.autotrader.domain

import org.junit.Assert.*
import org.junit.Test

class SignalParserTest {
    @Test fun parsesReleasedTrade() {
        val s = SignalParser.parse(
            "Multyfi",
            "Released: Equity Intraday Trade",
            "✅ Released: Equity Intraday Trade\n🔶 Stock Name: VIJAYA\n🔶 Target: 1540\n🔶 Entry Range: 1487.2-1489.2\n🔶 Stop Loss: 1470"
        )
        assertEquals(EventType.TRADE_RELEASE, s.type)
        assertEquals("VIJAYA", s.symbol)
        assertEquals(1487.2, s.entryLow!!, 0.0001)
        assertEquals(1489.2, s.entryHigh!!, 0.0001)
        assertEquals(1540.0, s.target!!, 0.0001)
        assertEquals(1470.0, s.stopLoss!!, 0.0001)
    }

    @Test fun parsesBookProfit() {
        val s = SignalParser.parse(
            "Multyfi", "Book Profit : SHADOWFAX",
            "✅ Book Profit : SHADOWFAX\nExit Price: 251.05\nReturns 🚀 : 0.11% on capital"
        )
        assertEquals(EventType.BOOK_PROFIT, s.type)
        assertEquals("SHADOWFAX", s.symbol)
        assertEquals(251.05, s.exitPrice!!, 0.0001)
    }

    @Test fun detectsSafetyPause() {
        val s = SignalParser.parse(
            "Auto trading paused",
            "VIJAYA has an unprotected filled quantity. Open Multyfi AutoBuy Pro.",
            null
        )
        assertEquals(EventType.AUTO_PAUSED, s.type)
        assertTrue(s.isCritical)
    }

    @Test fun ignoresDerivativesAndCommodities() {
        assertEquals(EventType.UNKNOWN, SignalParser.parse("F&O trade","NIFTY option",null).type)
        assertEquals(EventType.UNKNOWN, SignalParser.parse("MCX","Commodity intraday",null).type)
    }
}

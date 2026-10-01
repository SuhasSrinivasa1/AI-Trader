package com.multify.autotrader.domain

import java.util.Locale

object SignalParser {
    private val stock = Regex("STOCK\\s*NAME\\s*[:\\-]\\s*([A-Z0-9&._-]+)", RegexOption.IGNORE_CASE)
    private val target = Regex("TARGET\\s*[:\\-]\\s*([0-9]+(?:\\.[0-9]+)?)", RegexOption.IGNORE_CASE)
    private val stop = Regex("STOP\\s*LOSS\\s*[:\\-]\\s*([0-9]+(?:\\.[0-9]+)?)", RegexOption.IGNORE_CASE)
    private val range = Regex("ENTRY\\s*RANGE\\s*[:\\-]\\s*([0-9]+(?:\\.[0-9]+)?)\\s*(?:-|–|TO)\\s*([0-9]+(?:\\.[0-9]+)?)", RegexOption.IGNORE_CASE)
    private val book = Regex("BOOK\\s*PROFIT\\s*[:\\-]\\s*([A-Z0-9&._-]+)", RegexOption.IGNORE_CASE)
    private val exit = Regex("EXIT\\s*PRICE\\s*[:\\-]\\s*([0-9]+(?:\\.[0-9]+)?)", RegexOption.IGNORE_CASE)
    private val returns = Regex("RETURNS[^0-9-]*(-?[0-9]+(?:\\.[0-9]+)?)\\s*%", RegexOption.IGNORE_CASE)
    private val qty = Regex("QTY\\s*([0-9]+)", RegexOption.IGNORE_CASE)

    fun parse(title: String?, text: String?, bigText: String?): ParsedSignal {
        val raw = listOf(title.orEmpty(), text.orEmpty(), bigText.orEmpty()).joinToString("\n")
        val normalized = raw.replace("✅"," ").replace("🔶"," ").replace("◆"," ").replace("🚀"," ")
            .replace("⏳"," ").replace("📢"," ").replace("•","\n").uppercase(Locale.ROOT)
        if (listOf("FUTURE","OPTION","F&O","COMMODITY","MCX").any(normalized::contains))
            return ParsedSignal(EventType.UNKNOWN, confidence=0.99, rawText=raw)
        if (normalized.contains("EQUITY INTRADAY TRADE") && normalized.contains("STOCK NAME")) {
            val symbol=stock.find(normalized)?.groupValues?.getOrNull(1)
            val r=range.find(normalized)
            val t=target.find(normalized)?.groupValues?.getOrNull(1)?.toDoubleOrNull()
            val sl=stop.find(normalized)?.groupValues?.getOrNull(1)?.toDoubleOrNull()
            val a=r?.groupValues?.getOrNull(1)?.toDoubleOrNull()
            val b=r?.groupValues?.getOrNull(2)?.toDoubleOrNull()
            if(symbol!=null && a!=null && b!=null && t!=null && sl!=null)
                return ParsedSignal(EventType.TRADE_RELEASE,symbol,t,minOf(a,b),maxOf(a,b),sl,confidence=0.995,rawText=raw)
        }
        if(normalized.contains("BOOK PROFIT"))
            return ParsedSignal(EventType.BOOK_PROFIT,book.find(normalized)?.groupValues?.getOrNull(1),
                exitPrice=exit.find(normalized)?.groupValues?.getOrNull(1)?.toDoubleOrNull(),
                returnsPct=returns.find(normalized)?.groupValues?.getOrNull(1)?.toDoubleOrNull(),confidence=0.98,rawText=raw)
        if(normalized.contains("EQUITY INTRADAY TRADE IN") && normalized.contains("MIN"))
            return ParsedSignal(EventType.PRE_ALERT,confidence=0.98,rawText=raw)
        if(normalized.contains("BUY SUBMITTED") && normalized.contains("INTRADAY"))
            return ParsedSignal(EventType.BUY_SUBMITTED,quantity=qty.find(normalized)?.groupValues?.getOrNull(1)?.toIntOrNull(),confidence=0.90,rawText=raw)
        if(normalized.contains("AUTO TRADING PAUSED") || normalized.contains("UNPROTECTED FILLED QUANTITY"))
            return ParsedSignal(EventType.AUTO_PAUSED,confidence=0.99,rawText=raw)
        return ParsedSignal(EventType.UNKNOWN,confidence=0.10,rawText=raw)
    }
}

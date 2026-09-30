package com.multify.autotrader;

import java.util.Locale;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public final class SignalParser {
    private static final Pattern STOCK = Pattern.compile("STOCK\\s*NAME\\s*[:\\-]\\s*([A-Z0-9&._-]+)", Pattern.CASE_INSENSITIVE);
    private static final Pattern TARGET = Pattern.compile("TARGET\\s*[:\\-]\\s*([0-9]+(?:\\.[0-9]+)?)", Pattern.CASE_INSENSITIVE);
    private static final Pattern STOP = Pattern.compile("STOP\\s*LOSS\\s*[:\\-]\\s*([0-9]+(?:\\.[0-9]+)?)", Pattern.CASE_INSENSITIVE);
    private static final Pattern RANGE = Pattern.compile("ENTRY\\s*RANGE\\s*[:\\-]\\s*([0-9]+(?:\\.[0-9]+)?)\\s*(?:-|–|TO)\\s*([0-9]+(?:\\.[0-9]+)?)", Pattern.CASE_INSENSITIVE);
    private static final Pattern BOOK = Pattern.compile("BOOK\\s*PROFIT\\s*[:\\-]\\s*([A-Z0-9&._-]+)", Pattern.CASE_INSENSITIVE);
    private static final Pattern EXIT = Pattern.compile("EXIT\\s*PRICE\\s*[:\\-]\\s*([0-9]+(?:\\.[0-9]+)?)", Pattern.CASE_INSENSITIVE);
    private static final Pattern RETURNS = Pattern.compile("RETURNS[^0-9-]*(-?[0-9]+(?:\\.[0-9]+)?)\\s*%", Pattern.CASE_INSENSITIVE);
    private static final Pattern QTY = Pattern.compile("QTY\\s*([0-9]+)", Pattern.CASE_INSENSITIVE);

    private SignalParser() {}

    private static String norm(String x) {
        if (x == null) return "";
        return x.replace("✅", " ").replace("🔶", " ").replace("◆", " ")
                .replace("🚀", " ").replace("⏳", " ").replace("📢", " ")
                .replace("•", "\n").replace('\r', '\n');
    }

    private static Double number(Pattern p, String text) {
        Matcher m = p.matcher(text);
        return m.find() ? Double.valueOf(m.group(1)) : null;
    }

    public static TradeSignal parse(String title, String text, String bigText) {
        String raw = (title == null ? "" : title) + "\n" + (text == null ? "" : text) + "\n" + (bigText == null ? "" : bigText);
        String n = norm(raw);
        String u = n.toUpperCase(Locale.ROOT);
        TradeSignal s = new TradeSignal();
        s.rawText = raw;

        if (u.contains("FUTURE") || u.contains("OPTION") || u.contains("F&O") || u.contains("COMMODITY") || u.contains("MCX")) {
            s.confidence = 0.95;
            return s;
        }

        if (u.contains("EQUITY INTRADAY TRADE") && u.contains("STOCK NAME")) {
            Matcher sm = STOCK.matcher(u);
            Matcher rm = RANGE.matcher(u);
            Double target = number(TARGET, u);
            Double stop = number(STOP, u);
            if (sm.find() && rm.find() && target != null && stop != null) {
                s.type = TradeSignal.Type.TRADE_RELEASE;
                s.symbol = sm.group(1);
                double a = Double.parseDouble(rm.group(1));
                double b = Double.parseDouble(rm.group(2));
                s.entryLow = Math.min(a, b);
                s.entryHigh = Math.max(a, b);
                s.target = target;
                s.stopLoss = stop;
                s.confidence = 0.99;
                return s;
            }
        }

        if (u.contains("BOOK PROFIT")) {
            Matcher bm = BOOK.matcher(u);
            if (bm.find()) s.symbol = bm.group(1);
            s.exitPrice = number(EXIT, u);
            s.returnsPct = number(RETURNS, u);
            s.type = TradeSignal.Type.BOOK_PROFIT;
            s.confidence = s.symbol != null ? 0.98 : 0.70;
            return s;
        }

        if (u.contains("EQUITY INTRADAY TRADE IN") && u.contains("MIN")) {
            s.type = TradeSignal.Type.PRE_ALERT;
            s.confidence = 0.98;
            return s;
        }

        if (u.contains("BUY SUBMITTED") && u.contains("INTRADAY")) {
            s.type = TradeSignal.Type.BUY_SUBMITTED;
            Matcher qm = QTY.matcher(u);
            if (qm.find()) s.quantity = Integer.valueOf(qm.group(1));
            s.confidence = 0.85;
            return s;
        }

        if (u.contains("AUTO TRADING PAUSED") || u.contains("UNPROTECTED FILLED QUANTITY")) {
            s.type = TradeSignal.Type.AUTO_PAUSED;
            s.confidence = 0.95;
            return s;
        }

        s.confidence = 0.10;
        return s;
    }
}

package com.multify.autotrader;

public class TradeSignal {
    public enum Type { TRADE_RELEASE, BOOK_PROFIT, PRE_ALERT, BUY_SUBMITTED, AUTO_PAUSED, UNKNOWN }

    public Type type = Type.UNKNOWN;
    public String symbol = null;
    public Double target = null;
    public Double entryLow = null;
    public Double entryHigh = null;
    public Double stopLoss = null;
    public Double exitPrice = null;
    public Double returnsPct = null;
    public Integer quantity = null;
    public String rawText = "";
    public double confidence = 0.0;

    public boolean actionable() {
        return type == Type.TRADE_RELEASE || type == Type.BOOK_PROFIT || type == Type.AUTO_PAUSED;
    }

    public String summary() {
        StringBuilder s = new StringBuilder(type.name());
        if (symbol != null) s.append(" ").append(symbol);
        if (entryLow != null && entryHigh != null) s.append(" entry ").append(entryLow).append("-").append(entryHigh);
        if (target != null) s.append(" target ").append(target);
        if (stopLoss != null) s.append(" SL ").append(stopLoss);
        if (exitPrice != null) s.append(" exit ").append(exitPrice);
        return s.toString();
    }
}

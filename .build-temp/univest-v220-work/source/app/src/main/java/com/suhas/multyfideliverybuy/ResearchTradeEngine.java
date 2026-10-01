package com.suhas.multyfideliverybuy;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.os.Build;

import org.json.JSONArray;
import org.json.JSONObject;

import java.text.NumberFormat;
import java.util.ArrayList;
import java.util.Calendar;
import java.util.List;
import java.util.Locale;
import java.util.TimeZone;

final class ResearchTradeEngine {
    static final double MIN_NET_WIN_PCT = 0.50;
    static final int ENTRY_SCORE_MIN = 80;
    static final int ENTRY_CONSENSUS_MIN = 2;
    private static final String CHANNEL = "research_trade_signals";

    private ResearchTradeEngine() {}

    static boolean isMarketHoursIst() {
        Calendar c = Calendar.getInstance(TimeZone.getTimeZone("Asia/Kolkata"));
        int d = c.get(Calendar.DAY_OF_WEEK);
        if (d == Calendar.SATURDAY || d == Calendar.SUNDAY) return false;
        int m = c.get(Calendar.HOUR_OF_DAY) * 60 + c.get(Calendar.MINUTE);
        return m >= 555 && m < 930; // 09:15 <= now < 15:30 IST
    }

    static void evaluateLive(Context context) {
        Context c = context.getApplicationContext();
        if (!isMarketHoursIst()) return;
        try {
            monitorOpenPositions(c);
            JSONArray predictions = ResearchStore.predictions(c);
            int maxPositions = AppPrefs.getResearchMaxPositions(c);
            int active = activeCount(c);
            for (int i = 0; i < predictions.length() && i < 20 && active < maxPositions; i++) {
                JSONObject p = predictions.optJSONObject(i);
                if (p == null) continue;
                String symbol = p.optString("symbol", "").trim().toUpperCase(Locale.US);
                if (symbol.isEmpty() || findOpen(c, symbol) != null) continue;
                int score = p.optInt("similarity", p.optInt("bestScore", 0));
                int consensus = p.optInt("consensus", 0);
                if (score < ENTRY_SCORE_MIN || consensus < ENTRY_CONSENSUS_MIN) continue;

                double ltp;
                try { ltp = GrowwClient.getLtpForAutomation(c, symbol); }
                catch (Throwable t) { continue; }
                if (!(ltp > 0)) continue;

                double low = p.optDouble("buyLow", 0);
                double chase = p.optDouble("chaseLimit", 0);
                if (!(low > 0) || !(chase > 0) || ltp < low || ltp > chase) continue;

                JSONObject pos = openShadow(c, p, ltp, i + 1);
                active++;
                postEntryReady(c, pos);

                if (AppPrefs.isResearchAutoTradeEnabled(c)
                        && AppPrefs.isLiveMode(c)
                        && AppPrefs.isReadyForBuy(c)) {
                    executeBuy(c, symbol, true);
                }
            }
        } catch (Throwable t) {
            DiagnosticsStore.error(c, "RESEARCH_LIVE_EVALUATION_FAILED", "",
                    "Research live evaluation failed.", t);
        }
    }

    static String executeBuy(Context context, String symbol, boolean automatic) {
        Context c = context.getApplicationContext();
        symbol = cleanSymbol(symbol);
        if (symbol.isEmpty()) return "No Research symbol selected.";
        if (!AppPrefs.isLiveMode(c)) return "Research broker BUY requires LIVE mode.";
        if (!AppPrefs.isReadyForBuy(c)) return "Groww/static-IP readiness is not current. Test connection first.";
        int budget = AppPrefs.getUnivestBudget(c);
        if (budget <= 0) return "Initial entry budget is ₹0.";

        JSONObject p = findOpen(c, symbol);
        if (p != null && "LIVE_OPEN".equals(p.optString("state"))) return symbol + " already has an active Research LIVE lot.";
        if (p == null) {
            JSONObject prediction = findPrediction(c, symbol);
            if (prediction == null) return "No current frozen Research prediction for " + symbol + ".";
            try {
                double ltp = GrowwClient.getLtpForAutomation(c, symbol);
                if (!(ltp > 0)) return "No valid LTP for " + symbol + ".";
                p = openShadow(c, prediction, ltp, rankOf(c, symbol));
            } catch (Throwable t) {
                return "Unable to establish Research entry price: " + safe(t);
            }
        }

        double current;
        try { current = GrowwClient.getLtpForAutomation(c, symbol); }
        catch (Throwable t) { return "Unable to refresh LTP before BUY: " + safe(t); }
        double chase = p.optDouble("chaseLimit", 0);
        if (chase > 0 && current > chase) {
            return "BUY blocked: " + symbol + " moved above the frozen chase ceiling ₹" + money(chase) + ".";
        }

        GrowwClient.Result pending = GrowwClient.checkForActiveCncBuyOrder(c, symbol);
        if (pending.unknown) return "BUY blocked because open-order status is unknown: " + pending.message;
        if (pending.success) return "BUY blocked: broker already has an active CNC BUY for " + symbol + ".";

        String ref = UnivestManager.stableRef("RB", symbol,
                p.optString("strategy") + "|" + p.optLong("predictionAt"), System.currentTimeMillis());
        GrowwClient.ExecutionResult r = GrowwClient.placeUnivestCncMarketBuy(c, symbol, budget, ref);
        if (!r.submitted) {
            DiagnosticsStore.trade(c, "RESEARCH_BUY_FAILED", symbol, r.message, r);
            return "Research BUY not submitted: " + r.message;
        }

        try {
            p.put("state", r.filled && r.filledQuantity > 0 ? "LIVE_OPEN" : "LIVE_PENDING");
            p.put("live", true);
            p.put("automaticEntry", automatic);
            p.put("budget", budget);
            p.put("orderId", r.orderId);
            p.put("entryAt", System.currentTimeMillis());
            if (r.filled && r.averagePrice > 0) {
                p.put("entryPrice", r.averagePrice);
                p.put("lastPrice", r.averagePrice);
                p.put("minPrice", r.averagePrice);
                p.put("maxPrice", r.averagePrice);
                p.put("quantity", r.filledQuantity);
                p.put("mfePct", 0.0);
                p.put("maePct", 0.0);
                armResearchAveraging(c, p);
            }
            p.put("lastReason", automatic ? "Research AutoTrade entry executed." : "Manual Research BUY executed.");
            replacePosition(c, p);
        } catch (Exception ignored) {}

        DiagnosticsStore.trade(c, r.filled ? "RESEARCH_BUY_EXECUTED" : "RESEARCH_BUY_PENDING",
                symbol, r.message, r);
        AppPrefs.setResearchAction(c, symbol, "HOLD");
        return "Research BUY " + (r.filled ? "executed" : "submitted") + " • " + symbol
                + " • " + rupees(budget) + " • " + r.message;
    }

    static String executeSell(Context context, String symbol, boolean automatic, String reason) {
        Context c = context.getApplicationContext();
        symbol = cleanSymbol(symbol);
        JSONObject p = findOpen(c, symbol);
        if (p == null) return "No open Research trade for " + symbol + ".";

        boolean live = p.optBoolean("live", false);
        if (!live) {
            double exit = p.optDouble("lastPrice", p.optDouble("entryPrice", 0));
            closePosition(c, p, exit, automatic ? "SHADOW_MODEL_EXIT" : "SHADOW_MANUAL_EXIT", reason);
            return "Shadow Research trade closed for " + symbol + ".";
        }
        if (!AppPrefs.isLiveMode(c)) return "Research SELL requires LIVE mode.";
        int qty = Math.max(0, p.optInt("quantity", 0));
        if (qty <= 0) return "Research lot quantity is not confirmed; no SELL sent.";

        cancelResearchAveraging(c, p);
        String ref = UnivestManager.stableRef("RX", symbol,
                p.optString("strategy") + "|" + p.optLong("entryAt"), System.currentTimeMillis());
        GrowwClient.ExecutionResult r = GrowwClient.placeCncMarketSell(c, symbol, qty, ref);
        if (!r.submitted) {
            DiagnosticsStore.trade(c, "RESEARCH_SELL_FAILED", symbol, r.message, r);
            return "Research SELL not submitted: " + r.message;
        }
        double exit = r.averagePrice > 0 ? r.averagePrice : p.optDouble("lastPrice", p.optDouble("entryPrice", 0));
        closePosition(c, p, exit, automatic ? "MODEL_AUTO_EXIT" : "MANUAL_RESEARCH_EXIT", reason);
        DiagnosticsStore.trade(c, r.filled ? "RESEARCH_SELL_EXECUTED" : "RESEARCH_SELL_SUBMITTED",
                symbol, reason + " • " + r.message, r);
        return "Research SELL " + (r.filled ? "executed" : "submitted") + " • " + symbol
                + " • qty " + qty + " • " + r.message;
    }

    static void onOfficialSignal(Context context, UnivestParser.Signal signal, long at) {
        if (signal == null) return;
        Context c = context.getApplicationContext();
        try {
            ResearchStore.captureSignal(c, signal, at);
            String symbol = cleanSymbol(signal.symbol);
            JSONObject p = findOpen(c, symbol);
            if (p != null && signal.type == UnivestParser.Type.ENTRY) {
                long entryAt = p.optLong("entryAt", p.optLong("predictionAt", 0));
                p.put("univestConfirmedAt", at > 0 ? at : System.currentTimeMillis());
                p.put("preUnivestHit", entryAt > 0 && entryAt <= (at > 0 ? at : System.currentTimeMillis()));
                p.put("dualConfirmed", p.optBoolean("live", false));
                p.put("lastReason", "Official Univest ENTRY confirmed an earlier Research call.");
                replacePosition(c, p);
                DiagnosticsStore.runtime(c, "RESEARCH_PRE_UNIVEST_HIT", symbol,
                        "Research call existed before official Univest ENTRY. Lead time "
                                + leadTime(entryAt, at) + ".");
            } else if (p != null && signal.type == UnivestParser.Type.EXIT) {
                p.put("univestExitObservedAt", at > 0 ? at : System.currentTimeMillis());
                p.put("lastReason", "Official Univest EXIT observed while Research trade was active.");
                replacePosition(c, p);
            }
        } catch (Throwable t) {
            DiagnosticsStore.error(c, "RESEARCH_OFFICIAL_SIGNAL_LINK_FAILED", signal.symbol,
                    "Unable to link official signal to Research lifecycle.", t);
        }
    }

    static void onOfficialExitExecuted(Context context, String symbol, double exitPrice) {
        JSONObject p = findOpen(context, cleanSymbol(symbol));
        if (p == null) return;
        double px = exitPrice > 0 ? exitPrice : p.optDouble("lastPrice", p.optDouble("entryPrice", 0));
        closePosition(context, p, px, "OFFICIAL_UNIVEST_EXIT",
                "Official Univest exit closed the broker holding; Research lifecycle closed at the same event.");
    }

    static boolean hasResearchLivePosition(Context c, String symbol) {
        JSONObject p = findOpen(c, cleanSymbol(symbol));
        return p != null && p.optBoolean("live", false)
                && ("LIVE_OPEN".equals(p.optString("state")) || "LIVE_PENDING".equals(p.optString("state")));
    }

    static void monitorOpenPositions(Context c) {
        JSONArray a = ResearchStore.positions(c);
        boolean changed = false;
        for (int i = 0; i < a.length(); i++) {
            JSONObject p = a.optJSONObject(i);
            if (p == null || "CLOSED".equals(p.optString("state"))) continue;
            String symbol = p.optString("symbol", "");
            if (symbol.isEmpty()) continue;
            double ltp;
            try { ltp = GrowwClient.getLtpForAutomation(c, symbol); }
            catch (Throwable t) { continue; }
            if (!(ltp > 0)) continue;

            double entry = p.optDouble("entryPrice", 0);
            if (!(entry > 0)) entry = p.optDouble("shadowEntryPrice", 0);
            if (!(entry > 0)) continue;
            double min = p.optDouble("minPrice", entry);
            double max = p.optDouble("maxPrice", entry);
            min = Math.min(min > 0 ? min : entry, ltp);
            max = Math.max(max > 0 ? max : entry, ltp);
            double mae = (min / entry - 1.0) * 100.0;
            double mfe = (max / entry - 1.0) * 100.0;
            double netPct = estimatedNetPct(p, ltp);
            try {
                p.put("lastPrice", ltp);
                p.put("lastUpdate", System.currentTimeMillis());
                p.put("minPrice", min);
                p.put("maxPrice", max);
                p.put("maePct", mae);
                p.put("mfePct", mfe);
                p.put("netPct", netPct);
            } catch (Exception ignored) {}
            changed = true;

            boolean weakening = shouldExit(c, p, ltp, netPct, mfe);
            if (weakening && netPct >= MIN_NET_WIN_PCT) {
                String reason = "Net +" + one(netPct) + "% • move weakening after MFE +" + one(mfe)
                        + "%. Minimum +0.5% net condition satisfied.";
                if (p.optBoolean("live", false)) {
                    if (AppPrefs.isResearchAutoTradeEnabled(c)) {
                        replaceInArray(a, i, p); ResearchStore.savePositions(c, a);
                        executeSell(c, symbol, true, reason);
                        a = ResearchStore.positions(c);
                    } else {
                        AppPrefs.setResearchAction(c, symbol, "SELL");
                        postExitReady(c, p, reason);
                    }
                } else {
                    closePositionInArray(c, a, i, p, ltp, "SHADOW_MODEL_EXIT", reason);
                }
            }
        }
        if (changed) ResearchStore.savePositions(c, a);
    }

    private static boolean shouldExit(Context c, JSONObject p, double ltp, double netPct, double mfe) {
        if (netPct < MIN_NET_WIN_PCT) return false;
        double entry = p.optDouble("entryPrice", p.optDouble("shadowEntryPrice", 0));
        if (!(entry > 0)) return false;
        double max = p.optDouble("maxPrice", ltp);
        double retracePct = max > 0 ? (max - ltp) / max * 100.0 : 0.0;
        boolean trailingWeakness = mfe >= 1.25 && retracePct >= Math.max(0.60, mfe * 0.28);
        boolean technicalWeakness = false;
        try {
            long now = System.currentTimeMillis();
            List<GrowwClient.Candle> candles = GrowwClient.getHistoricalCandles(c, p.optString("symbol"),
                    now - 3L * 24L * 60L * 60L * 1000L, now, "5minute");
            ResearchMath.Features f = ResearchMath.fromCandles(candles);
            technicalWeakness = f.dataPoints >= 15 && f.return5Pct < 0
                    && ((f.sma20 > 0 && f.close < f.sma20) || f.rsi14 > 76);
            p.put("exitRsi14", f.rsi14);
            p.put("exitReturn5Pct", f.return5Pct);
        } catch (Throwable ignored) {}
        return trailingWeakness || technicalWeakness;
    }

    static void replayAndScore(Context c) {
        try {
            JSONArray a = ResearchStore.positions(c);
            for (int i = 0; i < a.length(); i++) {
                JSONObject p = a.optJSONObject(i);
                if (p == null) continue;
                if ("CLOSED".equals(p.optString("state"))) {
                    double net = p.optDouble("netPct", 0);
                    double mae = p.optDouble("maePct", 0);
                    double mfe = p.optDouble("mfePct", 0);
                    double capture = mfe > 0 ? Math.max(0, Math.min(100, net / mfe * 100.0)) : 0;
                    p.put("mfeCapturePct", capture);
                    String replay;
                    if (net >= MIN_NET_WIN_PCT && capture >= 55) replay = "WIN • profitable move captured efficiently.";
                    else if (net >= MIN_NET_WIN_PCT) replay = "WIN • profitable, but exit captured a smaller share of the available move.";
                    else if (mfe >= MIN_NET_WIN_PCT) replay = "EXIT TIMING MISS • trade offered >=0.5% net opportunity before closure.";
                    else if (mae <= -2.0) replay = "ENTRY STRESS • material adverse excursion; compare repeated failure signatures.";
                    else replay = "UNRESOLVED EDGE • no >=0.5% net opportunity captured.";
                    p.put("replaySummary", replay);
                } else {
                    p.put("replaySummary", "OPEN • not scored as win/loss until the trade closes.");
                }
            }
            ResearchStore.savePositions(c, a);
            AppPrefs.setResearchAccuracyText(c, accuracyText(c));
        } catch (Throwable t) {
            DiagnosticsStore.error(c, "RESEARCH_REPLAY_FAILED", "", "Post-market Research replay failed.", t);
        }
    }

    static String accuracyText(Context c) {
        JSONArray a = ResearchStore.positions(c);
        int closed = 0, wins = 0, sameDay = 0, sameDayWins = 0, pre = 0, open = 0;
        double mae = 0, mfe = 0, capture = 0;
        for (int i = 0; i < a.length(); i++) {
            JSONObject p = a.optJSONObject(i); if (p == null) continue;
            if (!"CLOSED".equals(p.optString("state"))) { open++; continue; }
            closed++;
            double net = p.optDouble("netPct", 0);
            if (net >= MIN_NET_WIN_PCT) wins++;
            if ("SAME_DAY".equals(p.optString("horizon"))) {
                sameDay++;
                if (net >= MIN_NET_WIN_PCT) sameDayWins++;
            }
            if (p.optBoolean("preUnivestHit", false)) pre++;
            mae += p.optDouble("maePct", 0);
            mfe += p.optDouble("mfePct", 0);
            capture += p.optDouble("mfeCapturePct", 0);
        }
        double winRate = closed == 0 ? 0 : wins * 100.0 / closed;
        StringBuilder b = new StringBuilder();
        b.append("Closed ").append(closed).append(" • Wins ≥0.5% net ").append(wins)
                .append(" • Win rate ").append(one(winRate)).append("%")
                .append("\nOpen / unresolved ").append(open)
                .append(" • Pre-Univest hits ").append(pre);
        if (sameDay > 0) b.append("\nSame-day ").append(sameDayWins).append("/").append(sameDay)
                .append(" • ").append(one(sameDayWins * 100.0 / sameDay)).append("%");
        if (closed > 0) b.append("\nAvg MAE ").append(one(mae / closed)).append("% • Avg MFE +")
                .append(one(mfe / closed)).append("% • Avg MFE captured ").append(one(capture / closed)).append("%");
        return b.toString();
    }

    static String activePositionsText(Context c) {
        JSONArray a = ResearchStore.positions(c);
        StringBuilder b = new StringBuilder();
        for (int i = a.length() - 1; i >= 0; i--) {
            JSONObject p = a.optJSONObject(i);
            if (p == null || "CLOSED".equals(p.optString("state"))) continue;
            if (b.length() > 0) b.append("\n\n");
            b.append(p.optString("symbol")).append(" • ").append(p.optString("state"))
                    .append(p.optBoolean("dualConfirmed", false) ? " • DUAL CONFIRMED" : "")
                    .append("\nEntry ₹").append(money(p.optDouble("entryPrice", p.optDouble("shadowEntryPrice", 0))))
                    .append(" • Last ₹").append(money(p.optDouble("lastPrice", 0)))
                    .append(" • Net ").append(one(p.optDouble("netPct", 0))).append("%")
                    .append("\nMAE ").append(one(p.optDouble("maePct", 0))).append("% • MFE +")
                    .append(one(p.optDouble("mfePct", 0))).append("%")
                    .append("\n").append(p.optString("lastReason", "Monitoring entry/exit conditions."));
        }
        return b.length() == 0 ? "No active Research trades. Entry-ready candidates will appear here." : b.toString();
    }

    static String actionSymbol(Context c) { return AppPrefs.getResearchActionSymbol(c); }
    static String actionType(Context c) { return AppPrefs.getResearchActionType(c); }

    private static JSONObject openShadow(Context c, JSONObject prediction, double ltp, int rank) {
        JSONObject p = new JSONObject();
        try {
            long now = System.currentTimeMillis();
            p.put("id", "R" + now + prediction.optString("symbol"));
            p.put("symbol", prediction.optString("symbol"));
            p.put("companyName", prediction.optString("companyName"));
            p.put("state", "SHADOW_OPEN");
            p.put("live", false);
            p.put("predictionAt", prediction.optLong("scannedAt", now));
            p.put("entryAt", now);
            p.put("shadowEntryPrice", ltp);
            p.put("entryPrice", ltp);
            p.put("lastPrice", ltp);
            p.put("minPrice", ltp);
            p.put("maxPrice", ltp);
            p.put("maePct", 0.0);
            p.put("mfePct", 0.0);
            p.put("netPct", 0.0);
            p.put("rank", rank);
            p.put("strategy", prediction.optString("strategy"));
            p.put("score", prediction.optInt("similarity"));
            p.put("consensus", prediction.optInt("consensus"));
            p.put("buyLow", prediction.optDouble("buyLow"));
            p.put("buyHigh", prediction.optDouble("buyHigh"));
            p.put("chaseLimit", prediction.optDouble("chaseLimit"));
            p.put("sellLow", prediction.optDouble("sellLow"));
            p.put("sellHigh", prediction.optDouble("sellHigh"));
            p.put("entryReasons", prediction.optString("reasons"));
            p.put("entryCounterSignals", prediction.optString("counterSignals"));
            p.put("lastReason", "Entry trigger reached inside frozen Research buy/chase range.");
        } catch (Exception ignored) {}
        JSONArray a = ResearchStore.positions(c); a.put(p); ResearchStore.savePositions(c, a);
        AppPrefs.setResearchAction(c, p.optString("symbol"), "BUY");
        DiagnosticsStore.runtime(c, "RESEARCH_SHADOW_ENTRY", p.optString("symbol"),
                "Frozen Research entry triggered at ₹" + money(ltp) + ".");
        return p;
    }

    private static void armResearchAveraging(Context c, JSONObject p) {
        if (!AppPrefs.isAveragingEnabled(c)) return;
        int budget = AppPrefs.getUnivestAddBudget(c);
        if (budget <= 0) return;
        double anchor = p.optDouble("entryPrice", 0);
        int qtyHeld = p.optInt("quantity", 0);
        if (!(anchor > 0) || qtyHeld <= 0) return;
        InstrumentRepository.Instrument ins = InstrumentRepository.resolve(InstrumentRepository.load(c), p.optString("symbol"));
        double tick = ins == null ? 0.05 : ins.tickSize;
        for (int level = 1; level <= 3; level++) {
            try {
                double trigger = GrowwClient.roundTarget(anchor * (1.0 - level * 0.02), tick, false);
                int qty = (int)Math.floor(budget / trigger);
                if (qty < 1) continue;
                String ref = UnivestManager.stableRef("RA" + level, p.optString("symbol"),
                        p.optString("id") + "|" + level, p.optLong("entryAt"));
                GrowwClient.GttResult g = GrowwClient.createUnivestCncBuyGtt(c, p.optString("symbol"), qty, trigger, ref);
                if (g.success) {
                    p.put("avgGtt" + level + "Id", g.smartOrderId);
                    p.put("avgGtt" + level + "Price", trigger);
                    p.put("avgGtt" + level + "Budget", budget);
                }
                DiagnosticsStore.broker(c, "RESEARCH_AVERAGING_LEVEL_" + level, p.optString("symbol"),
                        g.success || g.unknown, g.message);
            } catch (Throwable ignored) {}
        }
        replacePosition(c, p);
    }

    private static void cancelResearchAveraging(Context c, JSONObject p) {
        for (int level = 1; level <= 3; level++) {
            String id = p.optString("avgGtt" + level + "Id", "");
            if (id.isEmpty()) continue;
            GrowwClient.Result r = GrowwClient.cancelCashGtt(c, id);
            DiagnosticsStore.broker(c, "CANCEL_RESEARCH_AVERAGING_" + level, p.optString("symbol"),
                    r.success || r.unknown, r.message);
            if (r.success) try { p.put("avgGtt" + level + "Id", ""); } catch (Exception ignored) {}
        }
        replacePosition(c, p);
    }

    private static double estimatedNetPct(JSONObject p, double sellPrice) {
        double entry = p.optDouble("entryPrice", p.optDouble("shadowEntryPrice", 0));
        int qty = p.optInt("quantity", 0);
        if (qty > 0 && entry > 0) {
            double net = DeliveryNetTarget.estimatedNetProfit(entry, qty, sellPrice);
            double buy = entry * qty;
            return buy > 0 && Double.isFinite(net) ? net / buy * 100.0 : 0;
        }
        return entry > 0 ? (sellPrice / entry - 1.0) * 100.0 : 0;
    }

    private static void closePosition(Context c, JSONObject p, double exitPrice, String exitType, String reason) {
        JSONArray a = ResearchStore.positions(c);
        for (int i = 0; i < a.length(); i++) {
            JSONObject x = a.optJSONObject(i);
            if (x != null && x.optString("id").equals(p.optString("id"))) {
                closePositionInArray(c, a, i, x, exitPrice, exitType, reason);
                ResearchStore.savePositions(c, a);
                break;
            }
        }
    }

    private static void closePositionInArray(Context c, JSONArray a, int index, JSONObject p,
                                             double exitPrice, String exitType, String reason) {
        try {
            long now = System.currentTimeMillis();
            double net = estimatedNetPct(p, exitPrice);
            p.put("state", "CLOSED");
            p.put("exitAt", now);
            p.put("exitPrice", exitPrice);
            p.put("netPct", net);
            p.put("exitType", exitType);
            p.put("exitReason", reason);
            p.put("outcome", net >= MIN_NET_WIN_PCT ? "WIN" : "BELOW_0_5_NET");
            p.put("horizon", AppPrefs.istDayKey(p.optLong("entryAt", now)).equals(AppPrefs.istDayKey(now))
                    ? "SAME_DAY" : "MULTI_DAY");
            double mfe = p.optDouble("mfePct", 0);
            p.put("mfeCapturePct", mfe > 0 ? Math.max(0, Math.min(100, net / mfe * 100.0)) : 0);
            replaceInArray(a, index, p);
            DiagnosticsStore.runtime(c, "RESEARCH_TRADE_CLOSED", p.optString("symbol"),
                    exitType + " • net " + one(net) + "% • " + reason);
            AppPrefs.setResearchAction(c, "", "");
        } catch (Exception ignored) {}
    }

    private static JSONObject findOpen(Context c, String symbol) {
        JSONArray a = ResearchStore.positions(c);
        for (int i = a.length() - 1; i >= 0; i--) {
            JSONObject p = a.optJSONObject(i);
            if (p != null && symbol.equalsIgnoreCase(p.optString("symbol"))
                    && !"CLOSED".equals(p.optString("state"))) return p;
        }
        return null;
    }

    private static int activeCount(Context c) {
        JSONArray a = ResearchStore.positions(c); int n = 0;
        for (int i = 0; i < a.length(); i++) {
            JSONObject p = a.optJSONObject(i);
            if (p != null && !"CLOSED".equals(p.optString("state"))) n++;
        }
        return n;
    }

    private static JSONObject findPrediction(Context c, String symbol) {
        JSONArray a = ResearchStore.predictions(c);
        for (int i = 0; i < a.length(); i++) {
            JSONObject p = a.optJSONObject(i);
            if (p != null && symbol.equalsIgnoreCase(p.optString("symbol"))) return p;
        }
        return null;
    }

    private static int rankOf(Context c, String symbol) {
        JSONArray a = ResearchStore.predictions(c);
        for (int i = 0; i < a.length(); i++) {
            JSONObject p = a.optJSONObject(i);
            if (p != null && symbol.equalsIgnoreCase(p.optString("symbol"))) return i + 1;
        }
        return 0;
    }

    private static void replacePosition(Context c, JSONObject p) {
        JSONArray a = ResearchStore.positions(c);
        boolean found = false;
        for (int i = 0; i < a.length(); i++) {
            JSONObject x = a.optJSONObject(i);
            if (x != null && x.optString("id").equals(p.optString("id"))) {
                replaceInArray(a, i, p); found = true; break;
            }
        }
        if (!found) a.put(p);
        ResearchStore.savePositions(c, a);
    }

    private static void replaceInArray(JSONArray a, int i, JSONObject p) {
        try { a.put(i, p); } catch (Exception ignored) {}
    }

    private static void postEntryReady(Context c, JSONObject p) {
        String symbol = p.optString("symbol");
        String text = symbol + " • " + p.optInt("score") + "/100 • entry ₹"
                + money(p.optDouble("entryPrice")) + " • tap to review and BUY "
                + rupees(AppPrefs.getUnivestBudget(c));
        notify(c, 26001 + Math.abs(symbol.hashCode() % 1000), "Research Entry Ready", text, symbol, "BUY");
    }

    private static void postExitReady(Context c, JSONObject p, String reason) {
        String symbol = p.optString("symbol");
        notify(c, 27001 + Math.abs(symbol.hashCode() % 1000), "Research Exit Ready",
                symbol + " • " + reason + " • tap to review and SELL the Research lot.", symbol, "SELL");
    }

    private static void notify(Context c, int id, String title, String text, String symbol, String action) {
        NotificationManager nm = (NotificationManager)c.getSystemService(Context.NOTIFICATION_SERVICE);
        if (nm == null) return;
        if (Build.VERSION.SDK_INT >= 26) {
            nm.createNotificationChannel(new NotificationChannel(CHANNEL,
                    "Research trade signals", NotificationManager.IMPORTANCE_HIGH));
        }
        Intent intent = new Intent(c, DashboardActivity.class);
        intent.putExtra("open_tab", 2);
        intent.putExtra("research_symbol", symbol);
        intent.putExtra("research_action", action);
        intent.addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP | Intent.FLAG_ACTIVITY_SINGLE_TOP);
        int flags = PendingIntent.FLAG_UPDATE_CURRENT;
        if (Build.VERSION.SDK_INT >= 23) flags |= PendingIntent.FLAG_IMMUTABLE;
        PendingIntent pi = PendingIntent.getActivity(c, Math.abs((symbol + action).hashCode()), intent, flags);
        Notification.Builder b = Build.VERSION.SDK_INT >= 26 ? new Notification.Builder(c, CHANNEL) : new Notification.Builder(c);
        b.setSmallIcon(android.R.drawable.stat_notify_more)
                .setContentTitle(title)
                .setContentText(text)
                .setStyle(new Notification.BigTextStyle().bigText(text))
                .setContentIntent(pi)
                .setAutoCancel(true);
        nm.notify(id, b.build());
    }

    private static String cleanSymbol(String s) { return s == null ? "" : s.trim().toUpperCase(Locale.US); }
    private static String money(double v) { return String.format(Locale.US, "%.2f", v); }
    private static String one(double v) { return String.format(Locale.US, "%.1f", v); }
    private static String rupees(int v) { return "₹" + NumberFormat.getIntegerInstance(new Locale("en","IN")).format(Math.max(0, v)); }
    private static String safe(Throwable t) { return t == null ? "unknown error" : (t.getMessage() == null ? t.getClass().getSimpleName() : t.getMessage()); }

    private static String leadTime(long a, long b) {
        if (a <= 0 || b <= 0 || b < a) return "not available";
        long m = (b - a) / 60000L;
        if (m < 60) return m + " min";
        return (m / 60) + "h " + (m % 60) + "m";
    }
}

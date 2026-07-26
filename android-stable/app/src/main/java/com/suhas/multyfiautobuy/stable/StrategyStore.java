package com.suhas.multyfiautobuy.stable;

import android.content.Context;
import android.content.SharedPreferences;

import org.json.JSONArray;

import java.util.ArrayList;
import java.util.List;

final class StrategyStore {
    private static final String FILE = "strategy_store";
    private static final String KEY = "strategies";

    private StrategyStore() { }

    static synchronized List<Strategy> all(Context context) {
        List<Strategy> result = new ArrayList<>();
        String raw = prefs(context).getString(KEY, "[]");
        try {
            JSONArray array = new JSONArray(raw == null ? "[]" : raw);
            for (int i = 0; i < array.length(); i++) {
                try { result.add(Strategy.fromJson(array.getJSONObject(i))); }
                catch (Exception ignored) { }
            }
        } catch (Exception ignored) { }
        return result;
    }

    static synchronized List<Strategy> active(Context context) {
        List<Strategy> result = new ArrayList<>();
        for (Strategy strategy : all(context)) if (strategy.isActive()) result.add(strategy);
        return result;
    }

    static synchronized int activeCount(Context context) {
        return active(context).size();
    }

    static synchronized boolean hasActiveSymbol(Context context, String symbol) {
        return findActiveBySymbol(context, symbol) != null;
    }

    static synchronized Strategy findActiveBySymbol(Context context, String symbol) {
        if (symbol == null) return null;
        Strategy match = null;
        for (Strategy strategy : active(context)) {
            if (!strategy.symbol.equalsIgnoreCase(symbol.trim())) continue;
            if (match != null && !match.eventId.equals(strategy.eventId)) return null;
            match = strategy;
        }
        return match;
    }

    static synchronized void upsert(Context context, Strategy strategy) {
        List<Strategy> values = all(context);
        boolean replaced = false;
        for (int i = 0; i < values.size(); i++) {
            if (values.get(i).eventId.equals(strategy.eventId)) {
                values.set(i, strategy);
                replaced = true;
                break;
            }
        }
        if (!replaced) values.add(strategy);
        saveAll(context, values);
    }

    static synchronized Strategy find(Context context, String eventId) {
        for (Strategy strategy : all(context)) {
            if (strategy.eventId.equals(eventId)) return strategy;
        }
        return null;
    }

    private static void saveAll(Context context, List<Strategy> values) {
        JSONArray array = new JSONArray();
        for (Strategy strategy : values) {
            try { array.put(strategy.toJson()); }
            catch (Exception ignored) { }
        }
        prefs(context).edit().putString(KEY, array.toString()).commit();
    }

    private static SharedPreferences prefs(Context context) {
        return context.getSharedPreferences(FILE, Context.MODE_PRIVATE);
    }
}

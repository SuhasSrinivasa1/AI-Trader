package com.suhas.multyfiautobuy.stable;

/** Central source of truth for notification-time order routing. */
final class OrderPolicy {
    enum EntryMode {
        IMMEDIATE_MIS_LIMIT,
        CNC_ENTRY_GTT
    }

    private OrderPolicy() { }

    static EntryMode entryMode(AppPrefs.TradeWindow window) {
        if (window == null) throw new IllegalArgumentException("Trade window is required.");
        return window.forceMis ? EntryMode.IMMEDIATE_MIS_LIMIT : EntryMode.CNC_ENTRY_GTT;
    }

    static String productType(AppPrefs.TradeWindow window) {
        return entryMode(window) == EntryMode.IMMEDIATE_MIS_LIMIT ? "MIS" : "CNC";
    }

    static boolean usesEntryGtt(AppPrefs.TradeWindow window) {
        return entryMode(window) == EntryMode.CNC_ENTRY_GTT;
    }

    static String description(AppPrefs.TradeWindow window) {
        return entryMode(window) == EntryMode.IMMEDIATE_MIS_LIMIT
                ? "MIS intraday • immediate capped LIMIT"
                : "CNC delivery • entry GTT";
    }
}

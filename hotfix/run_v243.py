#!/usr/bin/env python3
from pathlib import Path
import runpy

runpy.run_path("hotfix/run_v242_fix.py", run_name="__main__")
ROOT = Path("android-stable")


def read(p): return Path(p).read_text(encoding="utf-8")
def write(p, s):
    p = Path(p); p.parent.mkdir(parents=True, exist_ok=True); p.write_text(s, encoding="utf-8")
def patch(p, old, new, expected=1):
    p = Path(p); text = read(p); n = text.count(old)
    if n != expected:
        raise RuntimeError(f"Expected {expected} matches in {p}, found {n}: {old[:180]}")
    write(p, text.replace(old, new, expected))
def replace_method(p, signature, replacement):
    p = Path(p); text = read(p); start = text.find(signature)
    if start < 0: raise RuntimeError(f"Method not found: {signature} in {p}")
    brace = text.find("{", start); depth = 0; end = -1
    for i in range(brace, len(text)):
        if text[i] == "{": depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                end = i + 1; break
    if end < 0: raise RuntimeError(f"Method end not found: {signature} in {p}")
    write(p, text[:start] + replacement.rstrip() + text[end:])

# v2.4.3 critical trading patch:
# - remove the +₹5,000 daily profit cap/lock entirely
# - recognize "closing early" / "close early" / "Book Profit" as authoritative exits
# - route early exits on their own executor so an entry confirmation loop cannot block them
# - submit a full-known MIS early exit directly from the notification path with no position read
#   and no protection cancellation when there is no broker-side protection to cancel
# - skip the pre-GET on the first early-exit MARKET submission; duplicate recovery remains on failure
# - prewarm an account position baseline cache so normal BUY calls can avoid a pre-order network GET
# - publish MASTER->CHILD over the already-live LAN service instead of a service-intent hop when possible
# NOTE: 100 ms is an app-side dispatch target only. Groww/network/exchange response latency is external.

DAILY_RISK = r'''package com.suhas.multyfiautobuy.stable;

final class DailyRiskPolicy {
    // Compatibility field retained for older persisted strategy JSON/tests. v2.4.3 has NO daily profit cap.
    static final double NET_PROFIT_TARGET = 0d;
    static final double GROSS_LOSS_LIMIT = 2000d;
    static final long WATCH_INTERVAL_MS = 250L;
    private static final double TICK = 0.10d;

    private DailyRiskPolicy() { }

    static boolean profitComplete(double dailyNet) { return false; }
    static double remainingNetProfit(double dailyNetBeforeTrade) { return 0d; }
    static double netProfitExitPrice(double entryPrice, int quantity, double dailyNetBeforeTrade) { return 0d; }

    static double grossOpenPnl(double ltp, double entryPrice, int quantity) {
        if (ltp <= 0d || entryPrice <= 0d || quantity <= 0) return 0d;
        return (ltp - entryPrice) * quantity;
    }

    static double remainingGrossLossRoom(double dailyRealisedGross) {
        double dailyRoom = Math.max(0d, GROSS_LOSS_LIMIT + dailyRealisedGross);
        return Math.min(GROSS_LOSS_LIMIT, dailyRoom);
    }

    static boolean grossLossThresholdHit(double currentTradeGross,
                                         double dailyRealisedGrossBeforeTrade) {
        return currentTradeGross <= -GROSS_LOSS_LIMIT + 1e-9d
                || dailyRealisedGrossBeforeTrade + currentTradeGross
                    <= -GROSS_LOSS_LIMIT + 1e-9d;
    }

    static boolean dailyGrossFloorComplete(double dailyRealisedGross) {
        return dailyRealisedGross <= -GROSS_LOSS_LIMIT + 1e-9d;
    }

    static double grossLossDisplayPrice(double entryPrice, int quantity,
                                        double dailyRealisedGrossBeforeTrade) {
        if (entryPrice <= 0d || quantity <= 0) return 0d;
        double room = remainingGrossLossRoom(dailyRealisedGrossBeforeTrade);
        return Math.max(0d, entryPrice - room / quantity);
    }

    static double firstProfitExitPrice(double multyfiTarget, double ignoredDailyTarget) {
        return multyfiTarget;
    }

    static boolean profitThresholdHit(double ltp, double threshold) {
        return ltp > 0d && threshold > 0d && ltp + 1e-9d >= threshold;
    }

    static double ceilTick(double value) {
        return Math.ceil((value - 1e-9d) / TICK) * TICK;
    }
}
'''

PROFIT_POLICY = r'''package com.suhas.multyfiautobuy.stable;

final class ProfitTargetPolicy {
    static final double DAILY_TARGET_RUPEES = 0d; // v2.4.3: no daily profit cap
    static final long POLL_INTERVAL_MS = DailyRiskPolicy.WATCH_INTERVAL_MS;
    private ProfitTargetPolicy() { }

    static double remainingDailyProfit(double dailyNetBeforeTrade) { return 0d; }
    static double dailyTargetPrice(double averageEntryPrice, int quantity,
                                   double ignored) { return 0d; }
    static double effectiveExitPrice(double multyfiTargetPrice,
                                     double ignoredDailyTargetPrice) {
        return multyfiTargetPrice;
    }
    static double openGrossProfit(double ltp, double averageEntryPrice, int quantity) {
        return (ltp - averageEntryPrice) * Math.max(0, quantity);
    }
    static boolean shouldExit(double ltp, double effectiveExitPrice) {
        return DailyRiskPolicy.profitThresholdHit(ltp, effectiveExitPrice);
    }
    static boolean dailyGoalIsFirst(double multyfiTargetPrice, double dailyTargetPrice) {
        return false;
    }
}
'''

DIRECT_EXIT_POLICY = r'''package com.suhas.multyfiautobuy.stable;

final class DirectEarlyExitPolicy {
    static final long APP_DISPATCH_TARGET_MS = 100L;
    private DirectEarlyExitPolicy() { }

    static boolean canDirectMarketSell(String productType, String state,
                                       int requestedQuantity, int observedFilledQuantity,
                                       int stopLegCount, String targetSmartOrderId) {
        return "MIS".equalsIgnoreCase(productType)
                && !Strategy.TARGET_SELL_PENDING.equals(state)
                && requestedQuantity > 0
                && observedFilledQuantity == requestedQuantity
                && stopLegCount == 0
                && (targetSmartOrderId == null || targetSmartOrderId.isEmpty());
    }

    static boolean withinAppDispatchTarget(long sourcePostTime, long now) {
        return sourcePostTime > 0L && now >= sourcePostTime
                && now - sourcePostTime <= APP_DISPATCH_TARGET_MS;
    }
}
'''

FAST_GATE = r'''package com.suhas.multyfiautobuy.stable;

import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

final class FastExitSubmissionGate {
    private static final Set<String> IN_FLIGHT = ConcurrentHashMap.newKeySet();
    private FastExitSubmissionGate() { }
    static boolean begin(String eventId) { return eventId != null && !eventId.isEmpty() && IN_FLIGHT.add(eventId); }
    static void end(String eventId) { if (eventId != null) IN_FLIGHT.remove(eventId); }
    static boolean isInFlight(String eventId) { return eventId != null && IN_FLIGHT.contains(eventId); }
}
'''

FAST_POSITION_CACHE = r'''package com.suhas.multyfiautobuy.stable;

import java.util.Collections;
import java.util.HashMap;
import java.util.Map;

final class FastPositionCache {
    static final long MAX_AGE_MS = 3500L;
    private static Map<String,Integer> quantities = Collections.emptyMap();
    private static long updatedAt;
    private FastPositionCache() { }

    static String key(String symbol, String product) {
        return (symbol == null ? "" : symbol.trim().toUpperCase(java.util.Locale.US))
                + "|" + (product == null ? "" : product.trim().toUpperCase(java.util.Locale.US));
    }

    static synchronized void update(Map<String,Integer> next, long now) {
        quantities = next == null ? Collections.emptyMap() : new HashMap<>(next);
        updatedAt = Math.max(0L, now);
    }

    static synchronized Lookup lookup(String symbol, String product, long now) {
        long age = updatedAt <= 0L ? Long.MAX_VALUE : Math.max(0L, now - updatedAt);
        if (updatedAt <= 0L || age > MAX_AGE_MS) return new Lookup(false, 0, age);
        return new Lookup(true, quantities.getOrDefault(key(symbol, product), 0), age);
    }

    static synchronized void invalidate() {
        quantities = Collections.emptyMap();
        updatedAt = 0L;
    }

    static final class Lookup {
        final boolean fresh; final int quantity; final long ageMs;
        Lookup(boolean fresh, int quantity, long ageMs) {
            this.fresh=fresh; this.quantity=quantity; this.ageMs=ageMs;
        }
    }
}
'''

PROFIT_TEST = r'''package com.suhas.multyfiautobuy.stable;

import org.junit.Test;
import static org.junit.Assert.*;

public class ProfitTargetPolicyTest {
    @Test public void dailyProfitCapIsRemoved() {
        assertEquals(0d, ProfitTargetPolicy.DAILY_TARGET_RUPEES, 0d);
        assertFalse(DailyRiskPolicy.profitComplete(1000000d));
        assertEquals(0d, ProfitTargetPolicy.remainingDailyProfit(1234d), 0d);
    }

    @Test public void multyfiTargetIsTheOnlyProfitExit() {
        assertEquals(618d, ProfitTargetPolicy.effectiveExitPrice(618d, 600d), 0d);
        assertFalse(ProfitTargetPolicy.dailyGoalIsFirst(618d, 600d));
    }

    @Test public void currentStockGrossMinusTwoThousandStillTriggersImmediately() {
        assertTrue(DailyRiskPolicy.grossLossThresholdHit(-2000d, 0d));
    }

    @Test public void priorGrossLossStillTightensDailyFloor() {
        assertTrue(DailyRiskPolicy.grossLossThresholdHit(-1200d, -800d));
    }

    @Test public void priorProfitNeverAllowsMoreThanTwoThousandLossOnOneStock() {
        assertTrue(DailyRiskPolicy.grossLossThresholdHit(-2000d, 5000d));
    }
}
'''

CRITICAL_TEST = r'''package com.suhas.multyfiautobuy.stable;

import org.junit.Test;
import java.util.HashMap;
import java.util.Map;
import static org.junit.Assert.*;

public class V243CriticalPolicyTest {
    @Test public void closingEarlyAndBookProfitAreAuthoritativePhrases() {
        assertTrue(SignalParser.containsEarlyExitPhrase("We're closing early against the planned target"));
        assertTrue(SignalParser.containsEarlyExitPhrase("Book Profit : GSPCROP"));
        assertTrue(SignalParser.containsEarlyExitPhrase("close early now"));
    }

    @Test public void fullMisWithoutBrokerProtectionUsesDirectMarketPath() {
        assertTrue(DirectEarlyExitPolicy.canDirectMarketSell(
                "MIS", Strategy.PROTECTED, 520, 520, 0, ""));
        assertFalse(DirectEarlyExitPolicy.canDirectMarketSell(
                "MIS", Strategy.PROTECTED, 520, 500, 0, ""));
        assertFalse(DirectEarlyExitPolicy.canDirectMarketSell(
                "CNC", Strategy.PROTECTED, 520, 520, 0, ""));
        assertFalse(DirectEarlyExitPolicy.canDirectMarketSell(
                "MIS", Strategy.PROTECTED, 520, 520, 1, ""));
    }

    @Test public void positionCacheProvidesFreshLocalBaseline() {
        Map<String,Integer> m = new HashMap<>();
        m.put(FastPositionCache.key("ABC", "MIS"), 7);
        FastPositionCache.update(m, 1000L);
        FastPositionCache.Lookup l = FastPositionCache.lookup("ABC", "MIS", 1200L);
        assertTrue(l.fresh); assertEquals(7, l.quantity); assertEquals(200L, l.ageMs);
        assertFalse(FastPositionCache.lookup("ABC", "MIS", 5000L).fresh);
    }
}
'''

for module in ("app", "child"):
    g = ROOT / module / "build.gradle"
    patch(g, "versionCode 242", "versionCode 243")
    patch(g, "versionName '2.4.2'", "versionName '2.4.3'")

    J = ROOT / module / "src/main/java/com/suhas/multyfiautobuy/stable"
    T = ROOT / module / "src/test/java/com/suhas/multyfiautobuy/stable"
    write(J / "DailyRiskPolicy.java", DAILY_RISK)
    write(J / "ProfitTargetPolicy.java", PROFIT_POLICY)
    write(J / "DirectEarlyExitPolicy.java", DIRECT_EXIT_POLICY)
    write(J / "FastExitSubmissionGate.java", FAST_GATE)
    write(J / "FastPositionCache.java", FAST_POSITION_CACHE)
    write(T / "ProfitTargetPolicyTest.java", PROFIT_TEST)
    write(T / "V243CriticalPolicyTest.java", CRITICAL_TEST)

    prefs = J / "AppPrefs.java"
    replace_method(prefs, "    static boolean isDailyProfitLocked(Context context)",
                   '''    static boolean isDailyProfitLocked(Context context) {\n        return false;\n    }''')
    replace_method(prefs, "    static void lockDailyProfitTarget(Context context)",
                   '''    static void lockDailyProfitTarget(Context context) {\n        // v2.4.3: daily profit cap removed. Kept only for binary/source compatibility.\n    }''')

    sp = J / "SignalParser.java"
    patch(sp,
          '"(?i)\\\\b(?:exit(?:ing)?\\\\s+early|early\\\\s+exit|disciplined\\\\s+early\\\\s+exit|',
          '"(?i)\\\\b(?:exit(?:ing)?\\\\s+early|early\\\\s+exit|clos(?:e|ing)\\\\s+(?:out\\\\s+)?(?:the\\\\s+)?(?:position|trade)?\\\\s*early|book\\\\s+profits?|disciplined\\\\s+early\\\\s+exit|')

    ns = J / "ProductionNotificationService.java"
    patch(ns,
          "    private final ExecutorService executor = Executors.newSingleThreadExecutor();",
          "    private final ExecutorService executor = Executors.newSingleThreadExecutor();\n"
          "    private final ExecutorService earlyExitExecutor = Executors.newSingleThreadExecutor();")
    patch(ns,
          '''        if (AppPrefs.MULTYFI_PACKAGE.equals(sourcePackage)) {\n            if (!AppPrefs.isArmed(this)) return;\n            executor.execute(() -> process(rawText, postTime));\n            if (!AppRole.isChild(this)) {\n                LanMasterRelayService.publishAsync(this, rawText, postTime);\n            }\n''',
          '''        if (AppPrefs.MULTYFI_PACKAGE.equals(sourcePackage)) {\n            if (!AppPrefs.isArmed(this)) return;\n            Runnable work = () -> process(rawText, postTime);\n            if (SignalParser.containsEarlyExitPhrase(rawText)) earlyExitExecutor.execute(work);\n            else executor.execute(work);\n            if (!AppRole.isChild(this)) {\n                LanMasterRelayService.publishFast(this, rawText, postTime);\n            }\n''')
    patch(ns,
          '''    protected final void enqueueRelayedMultyfi(String rawText, long postTime) {\n        executor.execute(() -> process(rawText, postTime));\n    }''',
          '''    protected final void enqueueRelayedMultyfi(String rawText, long postTime) {\n        Runnable work = () -> process(rawText, postTime);\n        if (SignalParser.containsEarlyExitPhrase(rawText)) earlyExitExecutor.execute(work);\n        else executor.execute(work);\n    }''')
    patch(ns,
          '''    public void onDestroy() {\n        executor.shutdownNow();\n        super.onDestroy();\n    }''',
          '''    public void onDestroy() {\n        earlyExitExecutor.shutdownNow();\n        executor.shutdownNow();\n        super.onDestroy();\n    }''')

    patch(ns,
          '''            if (AppPrefs.isDailyProfitLocked(this)) {\n                AppPrefs.log(this, "NEW ENTRY BLOCKED — DAILY NET ₹5,000 TARGET DONE",\n                        "The ₹5,000 NET daily profit target has already been completed. "\n                                + "No further automatic entries will be created today.\\n"\n                                + compact(rawText));\n                return;\n            }\n''', "")
    patch(ns,
          '''            double dailyNet = DailyNetPnlLedger.netRealised(this);\n            if (DailyRiskPolicy.profitComplete(dailyNet)) {\n                AppPrefs.lockDailyProfitTarget(this);\n                AppPrefs.log(this, "NEW ENTRY BLOCKED — DAILY NET ₹5,000 TARGET DONE",\n                        "Local charge-adjusted realised NET P&L ₹" + money(dailyNet)\n                                + " has reached the daily target.");\n                return;\n            }\n''', "")

    patch(ns,
          '''            GrowwClient.IntResult baseline = GrowwClient.getNetPositionQuantity(\n                    token, signal.symbol, productType);\n            if (!baseline.success) {\n                rejectAndDisarm("Could not establish the pre-trade " + productType\n                        + " position baseline: " + baseline.message, summary);\n                return;\n            }\n\n            if (entryMode == OrderPolicy.EntryMode.IMMEDIATE_MIS_LIMIT) {\n                submitImmediateMis(token, signal, window, quantity, baseline.value, summary);\n''',
          '''            FastPositionCache.Lookup cachedBaseline = FastPositionCache.lookup(\n                    signal.symbol, productType, System.currentTimeMillis());\n            GrowwClient.IntResult baseline = cachedBaseline.fresh\n                    ? GrowwClient.IntResult.success(cachedBaseline.quantity)\n                    : GrowwClient.getNetPositionQuantity(token, signal.symbol, productType);\n            if (!baseline.success) {\n                rejectAndDisarm("Could not establish the pre-trade " + productType\n                        + " position baseline: " + baseline.message, summary);\n                return;\n            }\n            if (cachedBaseline.fresh) {\n                AppPrefs.log(this, "FAST BUY BASELINE READY",\n                        signal.symbol + " • cached " + productType + " baseline " + baseline.value\n                                + " • cache age " + cachedBaseline.ageMs + " ms.");\n            }\n\n            if (entryMode == OrderPolicy.EntryMode.IMMEDIATE_MIS_LIMIT) {\n                AppPrefs.log(this, "BUY API DISPATCH", signal.symbol + " • source age "\n                        + Math.max(0L, System.currentTimeMillis() - signal.notificationTimeMillis)\n                        + " ms • no deliberate app-side wait before Groww order/create.");\n                submitImmediateMis(token, signal, window, quantity, baseline.value, summary);\n''')

    patch(ns,
          '''        if (newlyQueued) {\n            AppPrefs.log(this, "MULTYFI EARLY EXIT PERSISTED",\n                    signal.symbol + " • " + signal.phrase\n                            + " • new entries are paused until Groww confirms the position is zero.");\n        }\n        StrategyMonitorService.requestImmediateTick(this, signal.eventId);\n    }\n''',
          '''        if (newlyQueued) {\n            AppPrefs.log(this, "MULTYFI EARLY EXIT PERSISTED",\n                    signal.symbol + " • " + signal.phrase\n                            + " • new entries are paused until Groww confirms the position is zero.");\n        }\n        if (tryDirectEarlyExit(signal, strategy)) return;\n        StrategyMonitorService.requestImmediateTick(this, signal.eventId);\n    }\n\n    private boolean tryDirectEarlyExit(SignalParser.EarlyExitSignal signal, Strategy strategy) {\n        if (signal == null || strategy == null || !strategy.isActive()) return false;\n        if (!DirectEarlyExitPolicy.canDirectMarketSell(strategy.productType, strategy.state,\n                strategy.requestedQuantity, strategy.observedFilledQuantity,\n                strategy.stopLegs.size(), strategy.targetSmartOrderId)) return false;\n        if (!isMarketSessionNow() || !AppPrefs.isArmed(this)) return false;\n        if (!NetworkUtil.isNetworkAvailable(this) || !NetworkUtil.isVpnActive(this)\n                || !AppPrefs.isIpRecentlyVerified(this) || !AppPrefs.isAuthVerifiedToday(this)) return false;\n        String token = TokenManager.validToken(this);\n        if (token.isEmpty()) return false;\n        if (!FastExitSubmissionGate.begin(strategy.eventId)) return false;\n        try {\n            long dispatchAt = System.currentTimeMillis();\n            long sourceAge = Math.max(0L, dispatchAt - signal.notificationTimeMillis);\n            AppPrefs.log(this, "MULTYFI EARLY EXIT API DISPATCH",\n                    strategy.symbol + " • source age " + sourceAge + " ms • full known MIS qty "\n                            + strategy.requestedQuantity + " • direct Groww MARKET SELL path.");\n            GrowwClient.ApiResult sell = GrowwClient.placeEarlyExitMarketSell(\n                    token, strategy, strategy.requestedQuantity, strategy.earlyExitAttempt);\n            if (!sell.success) {\n                AppPrefs.log(this, "MULTYFI EARLY EXIT DIRECT SUBMIT FAILED — FALLBACK QUEUED",\n                        strategy.symbol + " • " + sell.message);\n                return false;\n            }\n            strategy.targetOrderId = sell.id;\n            strategy.targetOrderReferenceId = sell.secondaryId;\n            strategy.targetFilledQuantity = 0;\n            strategy.pendingExitLabel = "Multyfi early exit";\n            strategy.earlyExitRequested = true;\n            strategy.state = Strategy.TARGET_SELL_PENDING;\n            strategy.lastMessage = "Multyfi early exit MARKET SELL submitted directly from notification path.";\n            StrategyStore.upsert(this, strategy);\n            AppPrefs.log(this, "MULTYFI EARLY EXIT DIRECT SUBMITTED",\n                    strategy.symbol + " • qty " + strategy.requestedQuantity + " • " + sell.message);\n            StrategyMonitorService.requestImmediateTick(this, strategy.eventId);\n            return true;\n        } finally {\n            FastExitSubmissionGate.end(strategy.eventId);\n        }\n    }\n\n    private static boolean isMarketSessionNow() {\n        java.util.Calendar c = java.util.Calendar.getInstance(\n                java.util.TimeZone.getTimeZone("Asia/Kolkata"), java.util.Locale.US);\n        int d = c.get(java.util.Calendar.DAY_OF_WEEK);\n        if (d == java.util.Calendar.SATURDAY || d == java.util.Calendar.SUNDAY) return false;\n        int m = c.get(java.util.Calendar.HOUR_OF_DAY) * 60 + c.get(java.util.Calendar.MINUTE);\n        return m >= 9 * 60 + 15 && m <= 15 * 60 + 30;\n    }\n''')

    gc = J / "GrowwClient.java"
    patch(gc, "import java.util.Locale;", "import java.util.Locale;\nimport java.util.Map;\nimport java.util.HashMap;")
    replace_method(gc, "    static ApiResult placeEarlyExitMarketSell(String accessToken, Strategy strategy,\n                                              int quantity, int attempt)",
                   r'''    static ApiResult placeEarlyExitMarketSell(String accessToken, Strategy strategy,
                                              int quantity, int attempt) {
        if (strategy == null) {
            return ApiResult.failure("", "Strategy is required for early exit.", 0);
        }
        String reference = EarlyExitOrderPolicy.reference(strategy.eventId, attempt);
        // First attempt is deliberately one-request: POST MARKET immediately. If the POST
        // fails ambiguously, placeMarketSell() performs reference recovery. Retry attempts
        // may pre-read the deterministic reference to recover a prior accepted order.
        if (attempt > 0) {
            OrderStatus existing = getOrderByReference(accessToken, reference);
            if (existing.success
                    && EarlyExitOrderPolicy.canRecover(existing.status, existing.orderId)) {
                return ApiResult.success(existing.orderId, reference,
                        "Recovered existing Multyfi early-exit MARKET sell "
                                + existing.orderId + " • status " + existing.status + ".",
                        existing.httpCode);
            }
        }
        return placeMarketSell(accessToken, strategy, quantity, reference,
                "Multyfi authoritative early-exit");
    }''')

    anchor = "    static PnlResult getDailyRealisedMisPnl(String accessToken) {\n"
    position_book_method = r'''    static PositionBookResult getCashPositionBook(String accessToken) {
        try {
            HttpResult http = request("GET", API_BASE + "/positions/user?segment=CASH",
                    accessToken, null);
            if (!http.isSuccess()) return PositionBookResult.failure(http.message());
            JSONObject payload = new JSONObject(http.body).optJSONObject("payload");
            JSONArray positions = payload == null ? null : payload.optJSONArray("positions");
            Map<String,Integer> out = new HashMap<>();
            if (positions != null) {
                for (int i = 0; i < positions.length(); i++) {
                    JSONObject p = positions.optJSONObject(i);
                    if (p == null) continue;
                    String symbol = p.optString("trading_symbol", "");
                    String product = p.optString("product", p.optString("product_type", ""));
                    if (symbol.isEmpty() || product.isEmpty()) continue;
                    String key = FastPositionCache.key(symbol, product);
                    out.put(key, out.getOrDefault(key, 0) + p.optInt("quantity", 0));
                }
            }
            return PositionBookResult.success(out);
        } catch (Exception e) {
            return PositionBookResult.failure("Position-book error: " + safeMessage(e));
        }
    }

'''
    patch(gc, anchor, position_book_method + anchor)

    anchor2 = "    static final class PositionSnapshot {\n"
    result_class = r'''    static final class PositionBookResult {
        final boolean success;
        final Map<String,Integer> quantities;
        final String message;
        private PositionBookResult(boolean success, Map<String,Integer> quantities, String message) {
            this.success=success; this.quantities=quantities; this.message=message;
        }
        static PositionBookResult success(Map<String,Integer> quantities) {
            return new PositionBookResult(true, quantities, "");
        }
        static PositionBookResult failure(String message) {
            return new PositionBookResult(false, new HashMap<>(), message);
        }
    }

'''
    patch(gc, anchor2, result_class + anchor2)

    lm = J / "LanMasterRelayService.java"
    patch(lm, "    private final Set<Client> clients=ConcurrentHashMap.newKeySet();",
          "    private static volatile LanMasterRelayService live;\n"
          "    private final Set<Client> clients=ConcurrentHashMap.newKeySet();")
    insert_after_publish = '''    static void publishAsync(Context c,String raw,long post) {\n        if (AppRole.isChild(c) || !AppPrefs.isArmed(c) || raw==null || raw.trim().isEmpty()) return;\n        Intent i=new Intent(c,LanMasterRelayService.class).setAction(ACTION_PUBLISH)\n                .putExtra(EXTRA_RAW,raw).putExtra(EXTRA_POST,post);\n        try { c.startForegroundService(i); } catch(Exception e) { AppPrefs.log(c,"MASTER LAN RELAY PUBLISH FAILED",String.valueOf(e.getMessage())); }\n    }\n'''
    publish_fast = insert_after_publish + '''    static void publishFast(Context c,String raw,long post) {\n        if (AppRole.isChild(c) || !AppPrefs.isArmed(c) || raw==null || raw.trim().isEmpty()) return;\n        LanMasterRelayService s=live;\n        if(s!=null && s.running && s.io!=null){\n            try{s.io.execute(()->s.broadcast(raw,post));return;}catch(Exception ignored){}\n        }\n        publishAsync(c,raw,post);\n    }\n'''
    patch(lm, insert_after_publish, publish_fast)
    patch(lm, "    @Override public void onCreate(){ super.onCreate(); createChannel();",
          "    @Override public void onCreate(){ super.onCreate(); live=this; createChannel();")
    patch(lm, "    @Override public void onDestroy(){ RelayState.masterChildren(this,0); running=false;",
          "    @Override public void onDestroy(){ if(live==this)live=null; RelayState.masterChildren(this,0); running=false;")

    sm = J / "StrategyMonitorService.java"
    patch(sm, "    private ScheduledExecutorService profitExecutor;",
          "    private ScheduledExecutorService profitExecutor;\n    private ScheduledExecutorService prewarmExecutor;")
    patch(sm,
          '''        profitExecutor = Executors.newSingleThreadScheduledExecutor();\n        profitExecutor.scheduleWithFixedDelay(this::safeProfitTick, 0,\n                ProfitTargetPolicy.POLL_INTERVAL_MS, TimeUnit.MILLISECONDS);\n''',
          '''        profitExecutor = Executors.newSingleThreadScheduledExecutor();\n        profitExecutor.scheduleWithFixedDelay(this::safeProfitTick, 0,\n                ProfitTargetPolicy.POLL_INTERVAL_MS, TimeUnit.MILLISECONDS);\n        prewarmExecutor = Executors.newSingleThreadScheduledExecutor();\n        prewarmExecutor.scheduleWithFixedDelay(this::safePositionCacheTick, 0, 2, TimeUnit.SECONDS);\n''')
    patch(sm,
          '''        if (executor != null) executor.shutdownNow();\n        if (profitExecutor != null) profitExecutor.shutdownNow();\n''',
          '''        if (executor != null) executor.shutdownNow();\n        if (profitExecutor != null) profitExecutor.shutdownNow();\n        if (prewarmExecutor != null) prewarmExecutor.shutdownNow();\n''')
    safe_cache_method = r'''    private void safePositionCacheTick() {
        try {
            if (!AppPrefs.isArmed(this) || !isMarketSession()
                    || StrategyStore.activeCount(this) != 0) return;
            if (!NetworkUtil.isNetworkAvailable(this) || !NetworkUtil.isVpnActive(this)
                    || !AppPrefs.isIpRecentlyVerified(this) || !AppPrefs.isAuthVerifiedToday(this)) return;
            String token = TokenManager.validToken(this);
            if (token.isEmpty()) return;
            GrowwClient.PositionBookResult book = GrowwClient.getCashPositionBook(token);
            if (book.success) FastPositionCache.update(book.quantities, System.currentTimeMillis());
        } catch (Exception ignored) { }
    }

'''
    patch(sm, "    private void safeTick() {\n", safe_cache_method + "    private void safeTick() {\n")
    patch(sm, "        if (fastProfitSubmitting) return;",
          "        if (fastProfitSubmitting || FastExitSubmissionGate.isInFlight(strategy.eventId)) return;")

    patch(sm,
          '''            } else {\n                boolean dailyFirst = strategy.dailyTargetPrice > 0d\n                        && (strategy.targetPrice <= 0d || strategy.dailyTargetPrice <= strategy.targetPrice + 1e-9d);\n                boolean dailyHit = dailyFirst && ltp.value + 1e-9d >= strategy.dailyTargetPrice;\n                label = dailyHit ? "Daily NET ₹5,000 profit target" : "Multyfi target";\n                strategy.dailyProfitExitTriggered = dailyHit;\n                strategy.dailyLossExitTriggered = false;\n            }\n''',
          '''            } else {\n                label = "Multyfi target";\n                strategy.dailyProfitExitTriggered = false;\n                strategy.dailyLossExitTriggered = false;\n            }\n''')

    replace_method(sm, "    private boolean ensureFastProfitTargetArmed(String token, Strategy strategy)",
                   r'''    private boolean ensureFastProfitTargetArmed(String token, Strategy strategy) {
        if (!strategy.isIntraday()) return true;
        if (strategy.fastProfitArmed && strategy.entryAveragePrice > 0d
                && strategy.fastExitPrice > 0d
                && strategy.protectedQuantity == strategy.observedFilledQuantity) return true;
        GrowwClient.PositionSnapshot position = GrowwClient.getPositionSnapshot(token, strategy.symbol, strategy.productType);
        if (!position.success || position.quantity <= 0 || position.netPrice <= 0d) return false;
        GrowwClient.PnlResult brokerGross = GrowwClient.getDailyRealisedMisPnl(token);
        if (!brokerGross.success) return false;
        strategy.entryAveragePrice = position.netPrice;
        strategy.realisedPnlAtProfitArm = brokerGross.value;
        strategy.dailyNetBeforeTrade = DailyNetPnlLedger.netRealised(this); // reporting only
        double dailyGrossBefore = DailyGrossPnlLedger.grossRealised(this);
        strategy.dailyProfitNeeded = 0d;
        strategy.dailyTargetPrice = 0d;
        strategy.dynamicLossStopPrice = DailyRiskPolicy.grossLossDisplayPrice(
                strategy.entryAveragePrice, strategy.observedFilledQuantity, dailyGrossBefore);
        strategy.fastExitPrice = strategy.targetPrice;
        strategy.fastProfitArmed = strategy.fastExitPrice > 0d && strategy.entryAveragePrice > 0d;
        save(strategy);
        if (strategy.fastProfitArmed) {
            AppPrefs.log(this, "MULTYFI TARGET / GROSS -₹2,000 WATCH ARMED",
                    strategy.symbol + " • average entry ₹" + money(strategy.entryAveragePrice)
                            + " • qty " + strategy.observedFilledQuantity
                            + " • Multyfi target ₹" + money(strategy.targetPrice)
                            + " • gross-loss reference price ₹" + money(strategy.dynamicLossStopPrice)
                            + " • Multyfi stop ₹" + money(strategy.multyfiStopLossPrice)
                            + " is ignored for execution • NO daily profit cap • NO broker-side MIS stop by design.");
        }
        return strategy.fastProfitArmed;
    }''')

    patch(sm,
          '''        if (DailyRiskPolicy.profitComplete(dailyNet)) {\n            AppPrefs.lockDailyProfitTarget(this);\n            AppPrefs.log(this, "DAILY NET ₹5,000 TARGET COMPLETE — ENTRIES LOCKED",\n                    "Charge-adjusted daily realised NET P&L ₹" + money(dailyNet) + ". No more trades today.");\n        }\n''', "")

    text = read(sm)
    text = text.replace("Fill observed; calculating NET +₹5,000 / -₹2,000 thresholds before protection.",
                        "Fill observed; calculating Multyfi target / -₹2,000 gross-loss threshold.")
    text = text.replace(" • daily band -₹2,000 / +₹5,000.",
                        " • gross loss guard -₹2,000 • no daily profit cap.")
    text = text.replace(" MIS shares • NO broker-side stop • GROSS -₹2,000 / NET +₹5,000 rules active.",
                        " MIS shares • NO broker-side stop • GROSS -₹2,000 guard • no daily profit cap.")
    text = text.replace('strategy.dailyLossExitTriggered ? "₹2,000 GROSS LOSS MARKET SELL SUBMITTED"\n                        : strategy.dailyProfitExitTriggered ? "₹5,000 DAILY NET PROFIT EXIT SUBMITTED"\n                        : "MULTYFI TARGET EXIT SUBMITTED"',
                        'strategy.dailyLossExitTriggered ? "₹2,000 GROSS LOSS MARKET SELL SUBMITTED"\n                        : "MULTYFI TARGET EXIT SUBMITTED"')
    text = text.replace('                + " • NET band " + (AppPrefs.isDailyProfitLocked(this) ? "+₹5k DONE"\n                : AppPrefs.isDailyLossLocked(this) ? "-₹2k HALT" : "ACTIVE");',
                        '                + " • Risk " + (AppPrefs.isDailyLossLocked(this) ? "-₹2k HALT" : "Multyfi target / no profit cap");')
    write(sm, text)

    pa = J / "ProductionActivity.java"
    text = read(pa).replace("2.4.2", "2.4.3")
    text = text.replace("GROSS loss -₹2,000 / NET profit +₹5,000", "GROSS loss -₹2,000 • no daily profit cap")
    text = text.replace("Background monitor and local LAN relay enabled • NET +₹5,000 goal • GROSS -₹2,000 emergency loss lock.",
                        "Background monitor and local LAN relay enabled • Multyfi target exits • GROSS -₹2,000 emergency loss lock • no daily profit cap.")
    text = text.replace(" • NET profit goal +₹5,000 • GROSS loss emergency -₹2,000.",
                        " • Multyfi target exits • GROSS loss emergency -₹2,000 • no daily profit cap.")
    write(pa, text)

    main_text = "\n".join(read(p) for p in J.glob("*.java"))
    assert "v2.4.3" in read(pa)
    assert "closing early" not in read(sp).lower() or "clos(?:e|ing)" in read(sp)
    assert "book\\\\s+profits?" in read(sp)
    assert "MULTYFI EARLY EXIT DIRECT SUBMITTED" in read(ns)
    assert "earlyExitExecutor" in read(ns)
    assert "publishFast" in read(lm)
    assert "FastPositionCache.lookup" in read(ns)
    assert "getCashPositionBook" in read(gc)
    assert "attempt > 0" in read(gc)
    assert "NET_PROFIT_TARGET = 0d" in read(J / "DailyRiskPolicy.java")
    assert "static boolean isDailyProfitLocked(Context context) {\n        return false;" in read(prefs)
    assert "GROSS_LOSS_LIMIT = 2000d" in read(J / "DailyRiskPolicy.java")
    for banned in ("NET +₹5,000", "NET profit +₹5,000", "DAILY NET ₹5,000 TARGET", "+₹5k DONE"):
        assert banned not in main_text, (module, banned)

print("Applied Multyfi AutoBuy v2.4.3 critical early-exit + no-profit-cap + fast-dispatch patch")

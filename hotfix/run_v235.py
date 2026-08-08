#!/usr/bin/env python3
from pathlib import Path
import runpy

runpy.run_path("hotfix/run_v234.py", run_name="__main__")

ROOT = Path("android-stable")
JAVA = ROOT / "app/src/main/java/com/suhas/multyfiautobuy/stable"
TEST = ROOT / "app/src/test/java/com/suhas/multyfiautobuy/stable"


def read(path):
    return path.read_text(encoding="utf-8")


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def rep(path, old, new):
    text = read(path)
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"Expected one match in {path}, found {count}: {old[:180]}")
    write(path, text.replace(old, new, 1))


gradle = ROOT / "app/build.gradle"
rep(gradle, "versionCode 234", "versionCode 235")
rep(gradle, "versionName '2.3.4'", "versionName '2.3.5'")

write(JAVA / "ProfitTargetPolicy.java", r'''package com.suhas.multyfiautobuy.stable;

final class ProfitTargetPolicy {
    static final double DAILY_TARGET_RUPEES = 5000.00d;
    static final long POLL_INTERVAL_MS = 250L;

    private ProfitTargetPolicy() { }

    static double remainingDailyProfit(double realisedPnlBeforeTrade) {
        return Math.max(0d, DAILY_TARGET_RUPEES - realisedPnlBeforeTrade);
    }

    static double dailyTargetPrice(double averageEntryPrice,
                                   int quantity,
                                   double remainingProfit) {
        if (averageEntryPrice <= 0d || quantity <= 0) return 0d;
        if (remainingProfit <= 0d) return averageEntryPrice;
        return averageEntryPrice + (remainingProfit / quantity);
    }

    static double effectiveExitPrice(double multyfiTargetPrice,
                                     double dailyTargetPrice) {
        if (multyfiTargetPrice <= 0d) return dailyTargetPrice;
        if (dailyTargetPrice <= 0d) return multyfiTargetPrice;
        return Math.min(multyfiTargetPrice, dailyTargetPrice);
    }

    static double openGrossProfit(double ltp, double averageEntryPrice,
                                  int quantity) {
        if (ltp <= 0d || averageEntryPrice <= 0d || quantity <= 0) return 0d;
        return (ltp - averageEntryPrice) * quantity;
    }

    static boolean shouldExit(double ltp, double effectiveExitPrice) {
        return ltp > 0d && effectiveExitPrice > 0d
                && ltp + 1e-9d >= effectiveExitPrice;
    }

    static boolean dailyGoalIsFirst(double multyfiTargetPrice,
                                    double dailyTargetPrice) {
        return dailyTargetPrice > 0d
                && (multyfiTargetPrice <= 0d
                || dailyTargetPrice <= multyfiTargetPrice + 1e-9d);
    }
}
''')

app = JAVA / "AppPrefs.java"
rep(app,
    "    static final long IP_VERIFICATION_MAX_AGE_MS = 2L * 60L * 1000L;\n",
    "    static final long IP_VERIFICATION_MAX_AGE_MS = 2L * 60L * 1000L;\n"
    "    static final double DAILY_PROFIT_TARGET_RUPEES =\n"
    "            ProfitTargetPolicy.DAILY_TARGET_RUPEES;\n")
rep(app,
    '    private static final String K_COUNT_PREFIX = "count_";\n',
    '    private static final String K_COUNT_PREFIX = "count_";\n'
    '    private static final String K_DAILY_PROFIT_LOCK_DATE = "daily_profit_lock_date";\n')
rep(app,
    "    static synchronized boolean isProcessed(Context context, String eventId) {\n",
    r'''    static boolean isDailyProfitLocked(Context context) {
        return istDate().equals(prefs(context).getString(
                K_DAILY_PROFIT_LOCK_DATE, ""));
    }

    static void lockDailyProfitTarget(Context context) {
        prefs(context).edit()
                .putString(K_DAILY_PROFIT_LOCK_DATE, istDate())
                .apply();
    }

    static synchronized boolean isProcessed(Context context, String eventId) {
''')

strategy = JAVA / "Strategy.java"
rep(strategy,
    "    int earlyExitAttempt;\n    String pendingExitLabel;\n",
    "    int earlyExitAttempt;\n"
    "    double entryAveragePrice;\n"
    "    double realisedPnlAtProfitArm;\n"
    "    double dailyProfitNeeded;\n"
    "    double dailyTargetPrice;\n"
    "    double fastExitPrice;\n"
    "    boolean fastProfitArmed;\n"
    "    boolean dailyProfitExitTriggered;\n"
    "    String pendingExitLabel;\n")
rep(strategy,
    "        this.earlyExitAttempt = 0;\n        this.pendingExitLabel = \"\";\n",
    "        this.earlyExitAttempt = 0;\n"
    "        this.entryAveragePrice = 0d;\n"
    "        this.realisedPnlAtProfitArm = 0d;\n"
    "        this.dailyProfitNeeded = ProfitTargetPolicy.DAILY_TARGET_RUPEES;\n"
    "        this.dailyTargetPrice = 0d;\n"
    "        this.fastExitPrice = targetPrice;\n"
    "        this.fastProfitArmed = false;\n"
    "        this.dailyProfitExitTriggered = false;\n"
    "        this.pendingExitLabel = \"\";\n")
rep(strategy,
    "        json.put(\"early_exit_attempt\", earlyExitAttempt);\n"
    "        json.put(\"pending_exit_label\", pendingExitLabel);\n",
    "        json.put(\"early_exit_attempt\", earlyExitAttempt);\n"
    "        json.put(\"entry_average_price\", entryAveragePrice);\n"
    "        json.put(\"realised_pnl_at_profit_arm\", realisedPnlAtProfitArm);\n"
    "        json.put(\"daily_profit_needed\", dailyProfitNeeded);\n"
    "        json.put(\"daily_target_price\", dailyTargetPrice);\n"
    "        json.put(\"fast_exit_price\", fastExitPrice);\n"
    "        json.put(\"fast_profit_armed\", fastProfitArmed);\n"
    "        json.put(\"daily_profit_exit_triggered\", dailyProfitExitTriggered);\n"
    "        json.put(\"pending_exit_label\", pendingExitLabel);\n")
rep(strategy,
    "        strategy.earlyExitAttempt = json.optInt(\"early_exit_attempt\", 0);\n"
    "        strategy.pendingExitLabel = json.optString(\"pending_exit_label\", \"\");\n",
    "        strategy.earlyExitAttempt = json.optInt(\"early_exit_attempt\", 0);\n"
    "        strategy.entryAveragePrice = json.optDouble(\"entry_average_price\", 0d);\n"
    "        strategy.realisedPnlAtProfitArm =\n"
    "                json.optDouble(\"realised_pnl_at_profit_arm\", 0d);\n"
    "        strategy.dailyProfitNeeded = json.optDouble(\"daily_profit_needed\",\n"
    "                ProfitTargetPolicy.DAILY_TARGET_RUPEES);\n"
    "        strategy.dailyTargetPrice = json.optDouble(\"daily_target_price\", 0d);\n"
    "        strategy.fastExitPrice = json.optDouble(\"fast_exit_price\",\n"
    "                strategy.targetPrice);\n"
    "        strategy.fastProfitArmed = json.optBoolean(\"fast_profit_armed\", false);\n"
    "        strategy.dailyProfitExitTriggered =\n"
    "                json.optBoolean(\"daily_profit_exit_triggered\", false);\n"
    "        strategy.pendingExitLabel = json.optString(\"pending_exit_label\", \"\");\n")

client = JAVA / "GrowwClient.java"
rep(client,
    "    static IntResult getNetPositionQuantity(String accessToken, String symbol,\n",
    r'''    static PositionSnapshot getPositionSnapshot(String accessToken,
                                                String symbol,
                                                String productType) {
        try {
            String url = API_BASE + "/positions/trading-symbol?trading_symbol="
                    + enc(symbol) + "&segment=CASH";
            HttpResult http = request("GET", url, accessToken, null);
            if (!http.isSuccess()) return PositionSnapshot.failure(http.message());
            JSONObject payload = new JSONObject(http.body).optJSONObject("payload");
            JSONArray positions = payload == null ? null : payload.optJSONArray("positions");
            if (positions == null) return PositionSnapshot.success(0, 0d, 0d);
            for (int i = 0; i < positions.length(); i++) {
                JSONObject position = positions.optJSONObject(i);
                if (position == null) continue;
                String product = position.optString("product",
                        position.optString("product_type", ""));
                if (!symbol.equalsIgnoreCase(position.optString("trading_symbol", ""))
                        || !productType.equalsIgnoreCase(product)) continue;
                return PositionSnapshot.success(
                        position.optInt("quantity", 0),
                        position.optDouble("net_price", 0d),
                        position.optDouble("realised_pnl", 0d));
            }
            return PositionSnapshot.success(0, 0d, 0d);
        } catch (Exception e) {
            return PositionSnapshot.failure("Position snapshot error: " + safeMessage(e));
        }
    }

    static PnlResult getDailyRealisedMisPnl(String accessToken) {
        try {
            HttpResult http = request("GET",
                    API_BASE + "/positions/user?segment=CASH",
                    accessToken, null);
            if (!http.isSuccess()) return PnlResult.failure(http.message());
            JSONObject payload = new JSONObject(http.body).optJSONObject("payload");
            JSONArray positions = payload == null ? null : payload.optJSONArray("positions");
            if (positions == null) return PnlResult.success(0d);
            double total = 0d;
            for (int i = 0; i < positions.length(); i++) {
                JSONObject position = positions.optJSONObject(i);
                if (position == null) continue;
                String product = position.optString("product",
                        position.optString("product_type", ""));
                if ("MIS".equalsIgnoreCase(product)) {
                    total += position.optDouble("realised_pnl", 0d);
                }
            }
            return PnlResult.success(total);
        } catch (Exception e) {
            return PnlResult.failure("Daily realised P&L error: " + safeMessage(e));
        }
    }

    static IntResult getNetPositionQuantity(String accessToken, String symbol,
''')
rep(client,
    "    static final class IntResult {\n",
    r'''    static final class PositionSnapshot {
        final boolean success;
        final int quantity;
        final double netPrice;
        final double realisedPnl;
        final String message;

        private PositionSnapshot(boolean success, int quantity, double netPrice,
                                 double realisedPnl, String message) {
            this.success = success;
            this.quantity = quantity;
            this.netPrice = netPrice;
            this.realisedPnl = realisedPnl;
            this.message = message;
        }

        static PositionSnapshot success(int quantity, double netPrice,
                                        double realisedPnl) {
            return new PositionSnapshot(true, quantity, netPrice, realisedPnl, "");
        }

        static PositionSnapshot failure(String message) {
            return new PositionSnapshot(false, 0, 0d, 0d, message);
        }
    }

    static final class PnlResult {
        final boolean success;
        final double value;
        final String message;

        private PnlResult(boolean success, double value, String message) {
            this.success = success;
            this.value = value;
            this.message = message;
        }

        static PnlResult success(double value) {
            return new PnlResult(true, value, "");
        }

        static PnlResult failure(String message) {
            return new PnlResult(false, 0d, message);
        }
    }

    static final class IntResult {
''')

service = JAVA / "ProductionNotificationService.java"
rep(service,
    '''            if (hasPendingEarlyExit(active)) {
                AppPrefs.log(this, "NEW ENTRY BLOCKED — EARLY EXIT PENDING",
                        "A previous Multyfi exit is still awaiting broker-confirmed zero position.\\n"
                                + compact(rawText));
                return;
            }


            double buffer = AppPrefs.entryBufferPercent(this);
''',
    '''            if (hasPendingEarlyExit(active)) {
                AppPrefs.log(this, "NEW ENTRY BLOCKED — EARLY EXIT PENDING",
                        "A previous Multyfi exit is still awaiting broker-confirmed zero position.\\n"
                                + compact(rawText));
                return;
            }
            if (!active.isEmpty()) {
                AppPrefs.log(this, "NEW ENTRY BLOCKED — ONE STOCK AT A TIME",
                        "Exactly one stock may be active at a time. "
                                + active.get(0).symbol
                                + " is still active; this Multyfi call was ignored.\\n"
                                + compact(rawText));
                return;
            }
            if (AppPrefs.isDailyProfitLocked(this)) {
                AppPrefs.log(this, "NEW ENTRY BLOCKED — DAILY ₹5,000 TARGET DONE",
                        "The ₹5,000 daily profit target has already been completed. "
                                + "No further automatic entries will be created today.\\n"
                                + compact(rawText));
                return;
            }


            double buffer = AppPrefs.entryBufferPercent(this);
''')
rep(service,
    '''            GrowwClient.IntResult baseline = GrowwClient.getNetPositionQuantity(
                    token, signal.symbol, productType);
''',
    '''            GrowwClient.PnlResult dailyPnl = GrowwClient.getDailyRealisedMisPnl(token);
            if (!dailyPnl.success) {
                AppPrefs.log(this, "ENTRY BLOCKED — DAILY P&L UNAVAILABLE",
                        signal.symbol + " • " + dailyPnl.message
                                + " The daily ₹5,000 cap could not be verified, so no new order was submitted.");
                return;
            }
            if (dailyPnl.value >= ProfitTargetPolicy.DAILY_TARGET_RUPEES) {
                AppPrefs.lockDailyProfitTarget(this);
                AppPrefs.log(this, "NEW ENTRY BLOCKED — DAILY ₹5,000 TARGET DONE",
                        signal.symbol + " • broker-reported realised MIS P&L ₹"
                                + money(dailyPnl.value) + " has already reached the daily target.");
                return;
            }

            GrowwClient.IntResult baseline = GrowwClient.getNetPositionQuantity(
                    token, signal.symbol, productType);
''')

monitor = JAVA / "StrategyMonitorService.java"
rep(monitor,
    "    private ScheduledExecutorService executor;\n    private long lastIpCheckAt;\n",
    "    private ScheduledExecutorService executor;\n"
    "    private ScheduledExecutorService profitExecutor;\n"
    "    private volatile boolean fastProfitSubmitting;\n"
    "    private long lastFastProfitFailureLogAt;\n"
    "    private long lastIpCheckAt;\n")
rep(monitor,
    "        executor = Executors.newSingleThreadScheduledExecutor();\n"
    "        executor.scheduleWithFixedDelay(this::safeTick, 0, 2, TimeUnit.SECONDS);\n",
    "        executor = Executors.newSingleThreadScheduledExecutor();\n"
    "        executor.scheduleWithFixedDelay(this::safeTick, 0, 2, TimeUnit.SECONDS);\n"
    "        profitExecutor = Executors.newSingleThreadScheduledExecutor();\n"
    "        profitExecutor.scheduleWithFixedDelay(this::safeProfitTick, 0,\n"
    "                ProfitTargetPolicy.POLL_INTERVAL_MS, TimeUnit.MILLISECONDS);\n")
rep(monitor,
    '''    public void onDestroy() {
        if (executor != null) executor.shutdownNow();
        super.onDestroy();
    }
''',
    '''    public void onDestroy() {
        if (executor != null) executor.shutdownNow();
        if (profitExecutor != null) profitExecutor.shutdownNow();
        super.onDestroy();
    }
''')
rep(monitor,
    "    private void processStrategy(String token, Strategy strategy,\n",
    r'''    private void safeProfitTick() {
        if (fastProfitSubmitting || !isMarketSession()) return;
        try {
            List<Strategy> active = StrategyStore.active(this);
            if (active.size() != 1) return;
            Strategy strategy = active.get(0);
            if (!strategy.isIntraday()
                    || !Strategy.PROTECTED.equals(strategy.state)
                    || strategy.earlyExitRequested
                    || !strategy.fastProfitArmed
                    || strategy.protectedQuantity <= 0
                    || strategy.protectedQuantity != strategy.observedFilledQuantity) return;
            if (!NetworkUtil.isNetworkAvailable(this)
                    || !NetworkUtil.isVpnActive(this)
                    || !AppPrefs.isIpRecentlyVerified(this)
                    || !AppPrefs.isAuthVerifiedToday(this)) return;
            String token = TokenManager.validToken(this);
            if (token.isEmpty()) return;

            GrowwClient.DoubleResult ltp = GrowwClient.getLtp(token, strategy.symbol);
            if (!ltp.success || !ProfitTargetPolicy.shouldExit(
                    ltp.value, strategy.fastExitPrice)) return;

            fastProfitSubmitting = true;
            boolean dailyFirst = ProfitTargetPolicy.dailyGoalIsFirst(
                    strategy.targetPrice, strategy.dailyTargetPrice);
            boolean dailyHit = dailyFirst
                    && ltp.value + 1e-9d >= strategy.dailyTargetPrice;
            String label = dailyHit ? "Daily ₹5,000 profit target" : "Multyfi target";
            strategy.dailyProfitExitTriggered = dailyHit;
            save(strategy);

            if (!tryImmediateTrackedTargetExit(token, strategy, label, ltp.value)) {
                long now = System.currentTimeMillis();
                if (now - lastFastProfitFailureLogAt > 1000L) {
                    lastFastProfitFailureLogAt = now;
                    AppPrefs.log(this, "FAST TARGET EXIT FALLBACK",
                            strategy.symbol + " • " + label + " reached at LTP ₹"
                                    + money(ltp.value)
                                    + "; direct stop-to-MARKET conversion was unavailable. "
                                    + "Running the protected fallback.");
                }
                executeExit(token, strategy, true, EXIT_TARGET);
            }
        } catch (Exception e) {
            AppPrefs.log(this, "FAST PROFIT WATCH ERROR",
                    e.getClass().getSimpleName() + ": " + e.getMessage());
        } finally {
            fastProfitSubmitting = false;
        }
    }

    private boolean ensureFastProfitTargetArmed(String token, Strategy strategy) {
        if (!strategy.isIntraday()) return true;
        if (strategy.fastProfitArmed && strategy.entryAveragePrice > 0d
                && strategy.fastExitPrice > 0d) return true;

        GrowwClient.PositionSnapshot position = GrowwClient.getPositionSnapshot(
                token, strategy.symbol, strategy.productType);
        if (!position.success || position.quantity <= 0 || position.netPrice <= 0d) return false;
        GrowwClient.PnlResult realised = GrowwClient.getDailyRealisedMisPnl(token);
        if (!realised.success) return false;

        strategy.entryAveragePrice = position.netPrice;
        strategy.realisedPnlAtProfitArm = realised.value;
        strategy.dailyProfitNeeded = ProfitTargetPolicy.remainingDailyProfit(realised.value);
        strategy.dailyTargetPrice = ProfitTargetPolicy.dailyTargetPrice(
                strategy.entryAveragePrice, strategy.observedFilledQuantity,
                strategy.dailyProfitNeeded);
        strategy.fastExitPrice = ProfitTargetPolicy.effectiveExitPrice(
                strategy.targetPrice, strategy.dailyTargetPrice);
        strategy.fastProfitArmed = strategy.fastExitPrice > 0d;
        save(strategy);

        if (strategy.fastProfitArmed) {
            AppPrefs.log(this, "FAST PROFIT TARGET ARMED",
                    strategy.symbol + " • average entry ₹" + money(strategy.entryAveragePrice)
                            + " • qty " + strategy.observedFilledQuantity
                            + " • realised MIS P&L before this target ₹"
                            + money(strategy.realisedPnlAtProfitArm)
                            + " • daily profit still needed ₹" + money(strategy.dailyProfitNeeded)
                            + " • ₹5,000 target price ₹" + money(strategy.dailyTargetPrice)
                            + " • Multyfi target ₹" + money(strategy.targetPrice)
                            + " • first exit threshold ₹" + money(strategy.fastExitPrice)
                            + " • 250 ms LTP watch active; stop-loss remains broker-side.");
        }
        return strategy.fastProfitArmed;
    }

    private boolean tryImmediateTrackedTargetExit(String token, Strategy strategy,
                                                  String label, double triggerLtp) {
        Strategy.StopLeg candidate = null;
        int activeRegularStops = 0;
        for (Strategy.StopLeg leg : strategy.stopLegs) {
            if (!leg.isRegularMisStop()) continue;
            if (EarlyExitProtectionPolicy.isCancelled(leg.status)
                    || EarlyExitProtectionPolicy.isTriggeredOrExecuted(leg.status)) continue;
            activeRegularStops++;
            candidate = leg;
        }
        if (candidate == null || !FastEarlyExitPolicy.canConvertTrackedSingleStop(
                activeRegularStops, candidate.quantity,
                strategy.requestedQuantity, strategy.observedFilledQuantity,
                strategy.protectedQuantity)) return false;

        GrowwClient.ApiResult modified = GrowwClient.convertOpenMisStopToMarketSell(
                token, candidate.smartOrderId, candidate.referenceId,
                strategy.requestedQuantity);
        if (!modified.success) return false;

        candidate.status = "MODIFICATION_REQUESTED";
        strategy.targetOrderId = modified.id;
        strategy.targetOrderReferenceId = modified.secondaryId;
        strategy.targetFilledQuantity = 0;
        strategy.pendingExitLabel = label;
        strategy.state = Strategy.TARGET_SELL_PENDING;
        strategy.lastMessage = label + " reached at LTP ₹" + money(triggerLtp)
                + "; the full-quantity protective stop was converted directly "
                + "to MARKET SELL in one Groww request.";
        save(strategy);
        AppPrefs.log(this,
                strategy.dailyProfitExitTriggered
                        ? "₹5,000 DAILY PROFIT EXIT FAST SUBMITTED"
                        : "MULTYFI TARGET EXIT FAST SUBMITTED",
                strategy.symbol + " • full quantity " + strategy.requestedQuantity
                        + " • trigger LTP ₹" + money(triggerLtp) + " • " + modified.message);
        requestImmediateTick(this, strategy.eventId);
        return true;
    }

    private void processStrategy(String token, Strategy strategy,
''')
rep(monitor,
    '''        if (Strategy.CLOSED.equals(strategy.state)
                || Strategy.ERROR.equals(strategy.state)) return;
''',
    '''        if (Strategy.CLOSED.equals(strategy.state)
                || Strategy.ERROR.equals(strategy.state)) return;
        if (fastProfitSubmitting) return;
''')
rep(monitor,
    '''        strategy.state = Strategy.PROTECTED;
        if (anyStopLegTriggered(token, strategy)) {
''',
    '''        strategy.state = Strategy.PROTECTED;
        if (!ensureFastProfitTargetArmed(token, strategy)) {
            strategy.lastMessage = "Stop-loss is active; fast ₹5,000/Multyfi target watch is waiting for Groww entry-price/P&L data.";
            save(strategy);
        }
        if (anyStopLegTriggered(token, strategy)) {
''')
rep(monitor,
    r'''        GrowwClient.DoubleResult ltp = GrowwClient.getLtp(token, strategy.symbol);
        if (!ltp.success) {
            save(strategy);
            return;
        }
        if (ltp.value >= strategy.targetPrice) {
            executeExit(token, strategy, staticIpReady, EXIT_TARGET);
        } else {
            strategy.lastMessage = "Protected " + strategy.protectedQuantity + " "
                    + strategy.productType + " shares • LTP ₹" + money(ltp.value)
                    + " • target ₹" + money(strategy.targetPrice) + ".";
            save(strategy);
        }
''',
    r'''        // The dedicated 250 ms watcher owns profit/target exits so this
        // slower reconciliation loop does not consume the Live Data rate limit.
        if (strategy.fastProfitArmed) {
            strategy.lastMessage = "Protected " + strategy.protectedQuantity + " "
                    + strategy.productType + " shares • fast exit threshold ₹"
                    + money(strategy.fastExitPrice) + " • Multyfi target ₹"
                    + money(strategy.targetPrice) + " • daily goal ₹5,000.";
            save(strategy);
        }
''')
rep(monitor,
    '''        if (remaining <= 0) {
            closeStrategy(strategy, strategy.pendingExitLabel.isEmpty()
                    ? "Exit sell completed." : strategy.pendingExitLabel + " completed.");
            return;
        }
''',
    '''        if (remaining <= 0) {
            if (strategy.dailyProfitExitTriggered) {
                GrowwClient.PnlResult realised = GrowwClient.getDailyRealisedMisPnl(token);
                if (realised.success && realised.value >= ProfitTargetPolicy.DAILY_TARGET_RUPEES) {
                    AppPrefs.lockDailyProfitTarget(this);
                    AppPrefs.log(this, "DAILY ₹5,000 TARGET COMPLETE — ENTRIES LOCKED",
                            strategy.symbol + " • broker-reported realised MIS P&L ₹"
                                    + money(realised.value)
                                    + ". No further automatic entries will be created today.");
                } else if (realised.success) {
                    AppPrefs.log(this, "₹5,000 EXIT FILLED — DAILY TARGET NOT YET NETTED",
                            strategy.symbol + " • realised MIS P&L is ₹"
                                    + money(realised.value)
                                    + " after execution/slippage. Future calls remain eligible until broker-reported realised P&L reaches ₹5,000.");
                }
            }
            closeStrategy(strategy, strategy.pendingExitLabel.isEmpty()
                    ? "Exit sell completed." : strategy.pendingExitLabel + " completed.");
            return;
        }
''')
rep(monitor,
    '''                + " • IP " + (ip.isEmpty() ? "unchecked" : ip);
''',
    '''                + " • IP " + (ip.isEmpty() ? "unchecked" : ip)
                + " • ₹5k " + (AppPrefs.isDailyProfitLocked(this) ? "done" : "goal");
''')

activity = JAVA / "ProductionActivity.java"
write(activity, read(activity).replace("2.3.4", "2.3.5"))
activity_text = read(activity).replace(
    "Auto-Buy OFF by default • Intraday MIS only • early sell retained • source-built v2.3.5",
    "Auto-Buy OFF by default • Intraday MIS • ₹5,000 daily target • fast early sell • source-built v2.3.5")
write(activity, activity_text)

write(TEST / "ProfitTargetPolicyTest.java", r'''package com.suhas.multyfiautobuy.stable;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import org.junit.Test;

public class ProfitTargetPolicyTest {
    @Test public void zeroPriorPnlTargetsExactlyFiveThousandGross() {
        double needed = ProfitTargetPolicy.remainingDailyProfit(0d);
        double price = ProfitTargetPolicy.dailyTargetPrice(596d, 520, needed);
        assertEquals(5000d, needed, 0.0001d);
        assertEquals(596d + (5000d / 520d), price, 0.0001d);
        assertEquals(5000d, ProfitTargetPolicy.openGrossProfit(price, 596d, 520), 0.01d);
    }

    @Test public void priorProfitReducesAndPriorLossIncreasesRemainingGoal() {
        assertEquals(3000d, ProfitTargetPolicy.remainingDailyProfit(2000d), 0.0001d);
        assertEquals(6000d, ProfitTargetPolicy.remainingDailyProfit(-1000d), 0.0001d);
    }

    @Test public void whicheverComesFirstDailyGoalOrMultyfiTargetWins() {
        assertEquals(605.6153846d,
                ProfitTargetPolicy.effectiveExitPrice(618d, 605.6153846d), 0.0001d);
        assertEquals(610d, ProfitTargetPolicy.effectiveExitPrice(610d, 620d), 0.0001d);
        assertTrue(ProfitTargetPolicy.dailyGoalIsFirst(618d, 605.62d));
        assertFalse(ProfitTargetPolicy.dailyGoalIsFirst(610d, 620d));
    }

    @Test public void thresholdTriggersAtOrAbovePrice() {
        assertTrue(ProfitTargetPolicy.shouldExit(605.62d, 605.615d));
        assertFalse(ProfitTargetPolicy.shouldExit(605.60d, 605.615d));
    }
}
''')

assert "versionCode 235" in read(gradle)
assert "versionName '2.3.5'" in read(gradle)
assert "POLL_INTERVAL_MS = 250L" in read(JAVA / "ProfitTargetPolicy.java")
assert "NEW ENTRY BLOCKED — ONE STOCK AT A TIME" in read(service)
assert "NEW ENTRY BLOCKED — DAILY ₹5,000 TARGET DONE" in read(service)
assert "₹5,000 DAILY PROFIT EXIT FAST SUBMITTED" in read(monitor)
assert "MULTYFI TARGET EXIT FAST SUBMITTED" in read(monitor)
assert "convertOpenMisStopToMarketSell" in read(monitor)
assert "MULTYFI EARLY EXIT FAST SUBMITTED" in read(monitor)
assert "MIS STOP-LIMIT ORDER CONFIRMED" in read(monitor)
print("Applied Multyfi AutoBuy Pro v2.3.5 daily ₹5,000 fast-profit target")

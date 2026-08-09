#!/usr/bin/env python3
from pathlib import Path
import runpy

runpy.run_path("hotfix/run_v240_fix7.py", run_name="__main__")
ROOT = Path("android-stable")


def read(p): return Path(p).read_text(encoding="utf-8")
def write(p, s):
    p = Path(p); p.parent.mkdir(parents=True, exist_ok=True); p.write_text(s, encoding="utf-8")
def patch(p, old, new, expected=1):
    p = Path(p); text = read(p); n = text.count(old)
    if n != expected: raise RuntimeError(f"Expected {expected} matches in {p}, found {n}: {old[:180]}")
    write(p, text.replace(old, new, expected))
def replace_method(p, signature, replacement):
    p = Path(p); text = read(p); start = text.find(signature)
    if start < 0: raise RuntimeError(f"Method not found: {signature} in {p}")
    brace = text.find("{", start); depth = 0; end = -1
    for i in range(brace, len(text)):
        if text[i] == "{": depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0: end = i + 1; break
    if end < 0: raise RuntimeError(f"Method end not found: {signature}")
    write(p, text[:start] + replacement.rstrip() + text[end:])

# Version both roles.
for module in ("app", "child"):
    g = ROOT / module / "build.gradle"
    patch(g, "versionCode 240", "versionCode 241")
    patch(g, "versionName '2.4.0'", "versionName '2.4.1'")

# +₹5,000 remains charge-adjusted NET. -₹2,000 is GROSS and is checked both
# per open stock and cumulatively for the day. Previous profits never permit a
# later stock to lose more than ₹2,000 gross; previous losses tighten the room.
DAILY_RISK = r'''package com.suhas.multyfiautobuy.stable;

final class DailyRiskPolicy {
    static final double NET_PROFIT_TARGET = 5000d;
    static final double GROSS_LOSS_LIMIT = 2000d;
    static final long WATCH_INTERVAL_MS = 250L;
    private static final double TICK = 0.10d;

    private DailyRiskPolicy() { }

    static boolean profitComplete(double dailyNet) {
        return dailyNet + 1e-9d >= NET_PROFIT_TARGET;
    }

    static double remainingNetProfit(double dailyNetBeforeTrade) {
        return Math.max(0d, NET_PROFIT_TARGET - dailyNetBeforeTrade);
    }

    static double netProfitExitPrice(double entryPrice, int quantity,
                                     double dailyNetBeforeTrade) {
        double required = remainingNetProfit(dailyNetBeforeTrade);
        if (entryPrice <= 0d || quantity <= 0) return 0d;
        if (required <= 0d) return ceilTick(entryPrice);
        double lo = entryPrice;
        double hi = entryPrice + Math.max(10d, (required + 2000d) / quantity + 10d);
        while (IntradayChargeCalculator.estimatedNetPnl(entryPrice, hi, quantity) < required)
            hi = hi * 1.01d + 1d;
        for (int i = 0; i < 80; i++) {
            double mid = (lo + hi) / 2d;
            if (IntradayChargeCalculator.estimatedNetPnl(entryPrice, mid, quantity) >= required) hi = mid;
            else lo = mid;
        }
        return ceilTick(hi);
    }

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

    static double firstProfitExitPrice(double multyfiTarget, double netDailyTarget) {
        if (multyfiTarget <= 0d) return netDailyTarget;
        if (netDailyTarget <= 0d) return multyfiTarget;
        return Math.min(multyfiTarget, netDailyTarget);
    }

    static boolean profitThresholdHit(double ltp, double threshold) {
        return ltp > 0d && threshold > 0d && ltp + 1e-9d >= threshold;
    }

    static double ceilTick(double value) {
        return Math.ceil((value - 1e-9d) / TICK) * TICK;
    }
}
'''

GROSS_LEDGER = r'''package com.suhas.multyfiautobuy.stable;

import android.content.Context;
import android.content.SharedPreferences;
import org.json.JSONArray;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.HashSet;
import java.util.Locale;
import java.util.Set;
import java.util.TimeZone;

final class DailyGrossPnlLedger {
    private static final String PREF = "daily_gross_pnl_v241";
    private static final String DATE = "date";
    private static final String GROSS = "gross";
    private static final String EVENTS = "events";
    private static final TimeZone IST = TimeZone.getTimeZone("Asia/Kolkata");
    private DailyGrossPnlLedger() { }
    private static String today() { SimpleDateFormat f=new SimpleDateFormat("yyyy-MM-dd", Locale.US); f.setTimeZone(IST); return f.format(new Date()); }
    private static SharedPreferences p(Context c) {
        SharedPreferences p=c.getSharedPreferences(PREF, Context.MODE_PRIVATE); String d=today();
        if(!d.equals(p.getString(DATE,""))) p.edit().clear().putString(DATE,d).putLong(GROSS,Double.doubleToLongBits(0d)).putString(EVENTS,"[]").apply();
        return p;
    }
    static synchronized double grossRealised(Context c) { return Double.longBitsToDouble(p(c).getLong(GROSS,Double.doubleToLongBits(0d))); }
    static synchronized boolean record(Context c,String eventId,double tradeGross) {
        SharedPreferences p=p(c); Set<String> seen=new HashSet<>();
        try { JSONArray a=new JSONArray(p.getString(EVENTS,"[]")); for(int i=0;i<a.length();i++)seen.add(a.optString(i,"")); } catch(Exception ignored){}
        if(seen.contains(eventId)) return false; seen.add(eventId); JSONArray out=new JSONArray(); for(String id:seen)out.put(id);
        double next=grossRealised(c)+tradeGross; p.edit().putLong(GROSS,Double.doubleToLongBits(next)).putString(EVENTS,out.toString()).apply(); return true;
    }
}
'''

RUNTIME_POLICY = r'''package com.suhas.multyfiautobuy.stable;
final class RuntimePowerPolicy {
    private RuntimePowerPolicy() { }
    static boolean canHardPowerOff(int activeStrategies) { return activeStrategies <= 0; }
    static boolean relayShouldRun(boolean armed) { return armed; }
    static boolean monitorShouldRun(boolean armed, int activeStrategies) { return armed || activeStrategies > 0; }
}
'''

RUNTIME_CONTROL = r'''package com.suhas.multyfiautobuy.stable;

import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.os.Build;
import android.service.notification.NotificationListenerService;

final class AppRuntimeControl {
    private AppRuntimeControl() { }

    static void sync(Context c) {
        if (AppPrefs.isArmed(c)) activate(c); else deactivate(c);
    }

    static void activate(Context c) {
        StrategyMonitorService.ensureRunning(c);
        AppRole.ensureRelay(c);
        if (!AppRole.isChild(c)) {
            try { NotificationListenerService.requestRebind(new ComponentName(c, MultyfiNotificationService.class)); }
            catch (Exception ignored) { }
        }
    }

    static void deactivate(Context c) {
        // A stale active strategy is the only safety exception: keep only the
        // position monitor alive until Groww reports zero. LAN relay stays OFF.
        int active = StrategyStore.activeCount(c);
        c.stopService(new Intent(c, LanMasterRelayService.class));
        c.stopService(new Intent(c, LanChildRelayService.class));
        RelayState.masterChildren(c, 0);
        RelayState.childDisconnected(c);
        if (!AppRole.isChild(c) && Build.VERSION.SDK_INT >= 24) {
            try { NotificationListenerService.requestUnbind(new ComponentName(c, MultyfiNotificationService.class)); }
            catch (Exception ignored) { }
        }
        if (active <= 0) c.stopService(new Intent(c, StrategyMonitorService.class));
        else StrategyMonitorService.ensureRunning(c);
    }
}
'''

for module in ("app", "child"):
    J = ROOT / module / "src/main/java/com/suhas/multyfiautobuy/stable"
    write(J / "DailyRiskPolicy.java", DAILY_RISK)
    write(J / "DailyGrossPnlLedger.java", GROSS_LEDGER)
    write(J / "RuntimePowerPolicy.java", RUNTIME_POLICY)
    write(J / "AppRuntimeControl.java", RUNTIME_CONTROL)

    # Relay is strictly an ON-state facility.
    ar = J / "AppRole.java"
    patch(ar, "    static void ensureRelay(Context c) {\n        if (isChild(c))", "    static void ensureRelay(Context c) {\n        if (!AppPrefs.isArmed(c)) return;\n        if (isChild(c))")

    lm = J / "LanMasterRelayService.java"
    patch(lm, "        if (AppRole.isChild(c)) return;", "        if (AppRole.isChild(c) || !AppPrefs.isArmed(c)) return;")
    patch(lm, "        if (AppRole.isChild(c) || raw==null || raw.trim().isEmpty()) return;", "        if (AppRole.isChild(c) || !AppPrefs.isArmed(c) || raw==null || raw.trim().isEmpty()) return;")
    patch(lm, "@Override public int onStartCommand(Intent i,int f,int id){ if(i!=null&&ACTION_PUBLISH.equals(i.getAction()))", "@Override public int onStartCommand(Intent i,int f,int id){ if(!AppPrefs.isArmed(this)){stopSelf();return START_NOT_STICKY;} if(i!=null&&ACTION_PUBLISH.equals(i.getAction()))")
    patch(lm, "@Override public void onDestroy(){ running=false;", "@Override public void onDestroy(){ RelayState.masterChildren(this,0); running=false;")

    lc = J / "LanChildRelayService.java"
    patch(lc, "static void ensureRunning(Context c){ if(!AppRole.isChild(c))return;", "static void ensureRunning(Context c){ if(!AppRole.isChild(c)||!AppPrefs.isArmed(c))return;")
    patch(lc, "@Override public int onStartCommand(Intent i,int f,int id){return START_STICKY;}", "@Override public int onStartCommand(Intent i,int f,int id){if(!AppPrefs.isArmed(this)){stopSelf();return START_NOT_STICKY;}return START_STICKY;}")

    # Notification listener consumes/broadcasts nothing while OFF.
    ns = J / "ProductionNotificationService.java"
    replace_method(ns, "    public void onListenerConnected()", r'''    public void onListenerConnected() {
        super.onListenerConnected();
        if (!AppPrefs.isArmed(this)) {
            try { requestUnbind(new android.content.ComponentName(this, MultyfiNotificationService.class)); }
            catch (Exception ignored) { }
            return;
        }
        AppPrefs.log(this, "LISTENER READY", "Multyfi listener connected for armed MASTER operation.");
        StrategyMonitorService.ensureRunning(this);
    }''')
    replace_method(ns, "    public void onListenerDisconnected()", r'''    public void onListenerDisconnected() {
        if (AppPrefs.isArmed(this)) {
            AppPrefs.log(this, "LISTENER DISCONNECTED", "Android disconnected the listener; armed MASTER requested an immediate rebind.");
            try { requestRebind(new android.content.ComponentName(this, MultyfiNotificationService.class)); }
            catch (Exception ignored) { }
        }
        super.onListenerDisconnected();
    }''')
    patch(ns, "        if (!AppPrefs.MULTYFI_PACKAGE.equals(sbn.getPackageName())) return;\n", "        if (!AppPrefs.MULTYFI_PACKAGE.equals(sbn.getPackageName())) return;\n        if (!AppPrefs.isArmed(this)) return;\n")

    # Replace NET-loss gate with gross-loss gate. NET +₹5k remains unchanged.
    patch(ns, '''            if (AppPrefs.isDailyLossLocked(this)) {
                AppPrefs.log(this, "NEW ENTRY BLOCKED — DAILY NET LOSS LIMIT HIT",
                        "The daily NET loss floor of -₹2,000 has been reached. "
                                + "Trading is halted for the rest of today.\\n"
                                + compact(rawText));
                return;
            }
''', '''            if (AppPrefs.isDailyLossLocked(this)) {
                AppPrefs.log(this, "NEW ENTRY BLOCKED — ₹2,000 GROSS LOSS LOCK",
                        "The ₹2,000 GROSS loss safety lock has fired. Trading is halted for the rest of today.\\n"
                                + compact(rawText));
                return;
            }
''')
    patch(ns, '''            if (DailyRiskPolicy.lossComplete(dailyNet)) {
                AppPrefs.lockDailyLossLimit(this);
                AppPrefs.log(this, "NEW ENTRY BLOCKED — DAILY NET LOSS LIMIT HIT",
                        "Local charge-adjusted realised NET P&L ₹" + money(dailyNet)
                                + " has reached the -₹2,000 floor.");
                return;
            }
''', '''            double dailyGross = DailyGrossPnlLedger.grossRealised(this);
            if (DailyRiskPolicy.dailyGrossFloorComplete(dailyGross)) {
                AppPrefs.lockDailyLossLimit(this);
                AppPrefs.log(this, "NEW ENTRY BLOCKED — DAILY GROSS LOSS FLOOR HIT",
                        "Local realised GROSS P&L ₹" + money(dailyGross)
                                + " has reached the -₹2,000 daily floor.");
                return;
            }
''')
    write(ns, read(ns).replace("awaiting confirmed stop-loss protection", "awaiting fast risk-watcher arming").replace("filled shares awaiting confirmed stop-loss protection", "filled shares awaiting fast risk-watcher arming"))

    # Direct MARKET sell helper for the gross-loss emergency path.
    gc = J / "GrowwClient.java"
    anchor = "    static ApiResult placeTargetMarketSell(String accessToken, Strategy strategy,\n"
    risk_method = r'''    static ApiResult placeRiskMarketSell(String accessToken, Strategy strategy,
                                         int quantity, int attempt) {
        if (strategy == null) return ApiResult.failure("", "Strategy is required for risk exit.", 0);
        return placeMarketSell(accessToken, strategy, quantity,
                reference("RK", strategy.eventId, Math.max(0, attempt)),
                "₹2,000 gross-loss emergency");
    }

'''
    patch(gc, anchor, risk_method + anchor)

    sm = J / "StrategyMonitorService.java"
    replace_method(sm, "    private void safeProfitTick()", r'''    private void safeProfitTick() {
        if (fastProfitSubmitting || !isMarketSession()) return;
        try {
            List<Strategy> active = StrategyStore.active(this);
            if (active.size() != 1) return;
            Strategy strategy = active.get(0);
            if (!strategy.isIntraday() || !Strategy.PROTECTED.equals(strategy.state)
                    || strategy.earlyExitRequested || !strategy.fastProfitArmed
                    || strategy.protectedQuantity <= 0
                    || strategy.protectedQuantity != strategy.observedFilledQuantity) return;
            if (!NetworkUtil.isNetworkAvailable(this) || !NetworkUtil.isVpnActive(this)
                    || !AppPrefs.isIpRecentlyVerified(this) || !AppPrefs.isAuthVerifiedToday(this)) return;
            String token = TokenManager.validToken(this);
            if (token.isEmpty()) return;
            GrowwClient.DoubleResult ltp = GrowwClient.getLtp(token, strategy.symbol);
            if (!ltp.success) return;

            double currentGross = DailyRiskPolicy.grossOpenPnl(
                    ltp.value, strategy.entryAveragePrice, strategy.observedFilledQuantity);
            double realisedGrossBefore = DailyGrossPnlLedger.grossRealised(this);
            boolean lossHit = DailyRiskPolicy.grossLossThresholdHit(currentGross, realisedGrossBefore);
            boolean profitHit = DailyRiskPolicy.profitThresholdHit(ltp.value, strategy.fastExitPrice);
            if (!lossHit && !profitHit) return;

            fastProfitSubmitting = true;
            String label;
            if (lossHit) {
                label = "₹2,000 GROSS loss emergency";
                strategy.dailyLossExitTriggered = true;
                strategy.dailyProfitExitTriggered = false;
                strategy.earlyExitRequested = true; // authoritative retry until Groww confirms zero
                AppPrefs.lockDailyLossLimit(this);
                AppPrefs.log(this, "₹2,000 GROSS LOSS THRESHOLD HIT — DAY LOCKED",
                        strategy.symbol + " • current trade gross ₹" + money(currentGross)
                                + " • prior realised gross ₹" + money(realisedGrossBefore)
                                + " • immediate MARKET sell is being submitted; no more BUY calls today.");
            } else {
                boolean dailyFirst = strategy.dailyTargetPrice > 0d
                        && (strategy.targetPrice <= 0d || strategy.dailyTargetPrice <= strategy.targetPrice + 1e-9d);
                boolean dailyHit = dailyFirst && ltp.value + 1e-9d >= strategy.dailyTargetPrice;
                label = dailyHit ? "Daily NET ₹5,000 profit target" : "Multyfi target";
                strategy.dailyProfitExitTriggered = dailyHit;
                strategy.dailyLossExitTriggered = false;
            }
            save(strategy);
            if (!tryImmediateTrackedTargetExit(token, strategy, label, ltp.value)) {
                long now = System.currentTimeMillis();
                if (now - lastFastProfitFailureLogAt > 1000L) {
                    lastFastProfitFailureLogAt = now;
                    AppPrefs.log(this, "FAST EXIT FALLBACK", strategy.symbol + " • " + label
                            + " reached at LTP ₹" + money(ltp.value)
                            + "; direct MARKET submission unavailable. Running verified fallback now.");
                }
                executeExit(token, strategy, true, EXIT_TARGET);
            }
        } catch (Exception e) {
            AppPrefs.log(this, "FAST RISK WATCH ERROR", e.getClass().getSimpleName() + ": " + e.getMessage());
        } finally { fastProfitSubmitting = false; }
    }''')

    replace_method(sm, "    private boolean ensureFastProfitTargetArmed", r'''    private boolean ensureFastProfitTargetArmed(String token, Strategy strategy) {
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
        strategy.dailyNetBeforeTrade = DailyNetPnlLedger.netRealised(this);
        double dailyGrossBefore = DailyGrossPnlLedger.grossRealised(this);
        strategy.dailyProfitNeeded = DailyRiskPolicy.remainingNetProfit(strategy.dailyNetBeforeTrade);
        strategy.dailyTargetPrice = DailyRiskPolicy.netProfitExitPrice(
                strategy.entryAveragePrice, strategy.observedFilledQuantity, strategy.dailyNetBeforeTrade);
        strategy.dynamicLossStopPrice = DailyRiskPolicy.grossLossDisplayPrice(
                strategy.entryAveragePrice, strategy.observedFilledQuantity, dailyGrossBefore);
        strategy.fastExitPrice = DailyRiskPolicy.firstProfitExitPrice(strategy.targetPrice, strategy.dailyTargetPrice);
        strategy.fastProfitArmed = strategy.fastExitPrice > 0d && strategy.entryAveragePrice > 0d;
        save(strategy);
        if (strategy.fastProfitArmed) {
            AppPrefs.log(this, "NET +₹5,000 / GROSS -₹2,000 WATCH ARMED",
                    strategy.symbol + " • average entry ₹" + money(strategy.entryAveragePrice)
                            + " • qty " + strategy.observedFilledQuantity
                            + " • daily realised NET ₹" + money(strategy.dailyNetBeforeTrade)
                            + " • daily realised GROSS ₹" + money(dailyGrossBefore)
                            + " • NET +₹5k price ₹" + money(strategy.dailyTargetPrice)
                            + " • gross-loss reference price ₹" + money(strategy.dynamicLossStopPrice)
                            + " • Multyfi target ₹" + money(strategy.targetPrice)
                            + " • Multyfi stop ₹" + money(strategy.multyfiStopLossPrice)
                            + " is ignored for execution • NO broker-side stop by design • 250 ms watcher active.");
        }
        return strategy.fastProfitArmed;
    }''')

    replace_method(sm, "    private boolean tryImmediateTrackedTargetExit", r'''    private boolean tryImmediateTrackedTargetExit(String token, Strategy strategy,
                                                  String label, double triggerLtp) {
        // One broker request when the requested quantity is fully filled. No stop
        // cancellation exists on Multyfi intraday trades in v2.4.1.
        if (strategy.observedFilledQuantity != strategy.requestedQuantity
                || strategy.requestedQuantity <= 0) return false;
        GrowwClient.ApiResult sell = strategy.dailyLossExitTriggered
                ? GrowwClient.placeRiskMarketSell(token, strategy, strategy.requestedQuantity, strategy.earlyExitAttempt)
                : GrowwClient.placeTargetMarketSell(token, strategy, strategy.requestedQuantity);
        if (!sell.success) return false;
        strategy.targetOrderId = sell.id;
        strategy.targetOrderReferenceId = sell.secondaryId;
        strategy.targetFilledQuantity = 0;
        strategy.pendingExitLabel = label;
        strategy.earlyExitRequested = strategy.dailyLossExitTriggered;
        strategy.state = Strategy.TARGET_SELL_PENDING;
        strategy.lastMessage = label + " reached at LTP ₹" + money(triggerLtp)
                + "; full-position MARKET SELL submitted directly in one Groww order request.";
        save(strategy);
        AppPrefs.log(this,
                strategy.dailyLossExitTriggered ? "₹2,000 GROSS LOSS MARKET SELL SUBMITTED"
                        : strategy.dailyProfitExitTriggered ? "₹5,000 DAILY NET PROFIT EXIT SUBMITTED"
                        : "MULTYFI TARGET EXIT SUBMITTED",
                strategy.symbol + " • full quantity " + strategy.requestedQuantity + " • " + sell.message);
        requestImmediateTick(this, strategy.eventId);
        return true;
    }''')

    replace_method(sm, "    private boolean tryImmediateTrackedEarlyExit", r'''    private boolean tryImmediateTrackedEarlyExit(String token, Strategy strategy, boolean staticIpReady) {
        if (!isMarketSession() || !staticIpReady || !strategy.isIntraday()) return false;
        if (strategy.observedFilledQuantity != strategy.requestedQuantity || strategy.requestedQuantity <= 0) return false;
        boolean grossLoss = strategy.dailyLossExitTriggered;
        GrowwClient.ApiResult sell = grossLoss
                ? GrowwClient.placeRiskMarketSell(token, strategy, strategy.requestedQuantity, strategy.earlyExitAttempt)
                : GrowwClient.placeEarlyExitMarketSell(token, strategy, strategy.requestedQuantity, strategy.earlyExitAttempt);
        if (!sell.success) return false;
        strategy.targetOrderId = sell.id;
        strategy.targetOrderReferenceId = sell.secondaryId;
        strategy.targetFilledQuantity = 0;
        strategy.pendingExitLabel = grossLoss ? "₹2,000 GROSS loss emergency" : "Multyfi early exit";
        strategy.earlyExitRequested = true;
        strategy.state = Strategy.TARGET_SELL_PENDING;
        strategy.lastMessage = strategy.pendingExitLabel + " MARKET SELL submitted directly; no stop cancellation was required.";
        save(strategy);
        AppPrefs.log(this, grossLoss ? "₹2,000 GROSS LOSS RETRY SUBMITTED" : "MULTYFI EARLY EXIT FAST SUBMITTED",
                strategy.symbol + " • full quantity " + strategy.requestedQuantity + " • " + sell.message);
        requestImmediateTick(this, strategy.eventId);
        return true;
    }''')

    # Multyfi intraday gets NO broker-side stop. Non-intraday/image-batch protection remains unchanged.
    patch(sm, "    private boolean protectNewFill(String token, Strategy strategy) {\n        int delta = strategy.observedFilledQuantity - strategy.protectedQuantity;\n", '''    private boolean protectNewFill(String token, Strategy strategy) {
        int delta = strategy.observedFilledQuantity - strategy.protectedQuantity;
        if (strategy.isIntraday()) {
            if (delta <= 0) return true;
            strategy.protectedQuantity = strategy.observedFilledQuantity;
            strategy.state = Strategy.PROTECTED;
            strategy.lastMessage = "Fast price watcher armed for " + strategy.protectedQuantity
                    + " MIS shares • NO broker-side stop • GROSS -₹2,000 / NET +₹5,000 rules active.";
            save(strategy);
            AppPrefs.log(this, "FAST RISK WATCH ARMED — NO BROKER STOP",
                    strategy.symbol + " • " + strategy.lastMessage);
            return true;
        }
''')

    # Partial fills: cancel the BUY remainder before any threshold-driven sell.
    patch(sm, "        if (!cancelImageTargetGtt(token, strategy)) {\n", '''        if (strategy.isIntraday() && strategy.observedFilledQuantity < strategy.requestedQuantity
                && strategy.hasPendingEntryHandle()) {
            if (!cancelEntryAndVerify(token, strategy)) {
                strategy.lastMessage = label + " requested; cancelling the remaining BUY quantity before MARKET sell.";
                save(strategy);
                if (authoritativeEarly || strategy.dailyLossExitTriggered) requestImmediateTick(this, strategy.eventId);
                return;
            }
        }

        if (!cancelImageTargetGtt(token, strategy)) {
''')
    write(sm, read(sm).replace("sell failed after stop-loss cancellation. Re-creating protection.", "sell was not broker-accepted. Re-arming the fast watcher.")
                 .replace("Exit sell did not complete. Re-establishing stop-loss for ", "Exit sell did not complete. Re-arming fast watcher for ")
                 .replace("Stop-loss is active; NET risk watcher is waiting for Groww entry/P&L data.", "Fast risk watcher is waiting for Groww entry/P&L data.")
                 .replace("Stop-loss protection has triggered; waiting for position settlement.", "Broker protection triggered; waiting for position settlement."))

    replace_method(sm, "    private void reconcileClosedTradeNet", r'''    private void reconcileClosedTradeNet(String token, Strategy strategy) {
        if (!strategy.isIntraday() || strategy.observedFilledQuantity <= 0 || strategy.entryAveragePrice <= 0d) return;
        GrowwClient.PnlResult grossNow = GrowwClient.getDailyRealisedMisPnl(token);
        if (!grossNow.success) return;
        double tradeGross = grossNow.value - strategy.realisedPnlAtProfitArm;
        int qty = Math.max(1, strategy.observedFilledQuantity);
        double inferredSell = strategy.entryAveragePrice + (tradeGross / qty);
        if (inferredSell <= 0d) return;
        double charges = IntradayChargeCalculator.estimatedRoundTripCharges(
                strategy.entryAveragePrice * qty, inferredSell * qty);
        double tradeNet = tradeGross - charges;
        DailyGrossPnlLedger.record(this, strategy.eventId, tradeGross);
        DailyNetPnlLedger.record(this, strategy.eventId, tradeNet);
        double dailyGross = DailyGrossPnlLedger.grossRealised(this);
        double dailyNet = DailyNetPnlLedger.netRealised(this);
        AppPrefs.log(this, "CLOSED TRADE P&L RECORDED",
                strategy.symbol + " • trade GROSS ₹" + money(tradeGross)
                        + " • estimated charges ₹" + money(charges)
                        + " • trade NET ₹" + money(tradeNet)
                        + " • daily GROSS ₹" + money(dailyGross)
                        + " • daily NET ₹" + money(dailyNet) + ".");
        if (DailyRiskPolicy.profitComplete(dailyNet)) {
            AppPrefs.lockDailyProfitTarget(this);
            AppPrefs.log(this, "DAILY NET ₹5,000 TARGET COMPLETE — ENTRIES LOCKED",
                    "Charge-adjusted daily realised NET P&L ₹" + money(dailyNet) + ". No more trades today.");
        }
        if (strategy.dailyLossExitTriggered || tradeGross <= -DailyRiskPolicy.GROSS_LOSS_LIMIT + 1e-9d
                || DailyRiskPolicy.dailyGrossFloorComplete(dailyGross)) {
            AppPrefs.lockDailyLossLimit(this);
            AppPrefs.log(this, "₹2,000 GROSS LOSS PROTECTION — TRADING HALTED",
                    strategy.symbol + " • trade GROSS ₹" + money(tradeGross)
                            + " • daily GROSS ₹" + money(dailyGross) + ". No more trades today.");
        }
    }''')

    # UI: true hard OFF, child-specific acceptance, and corrected risk labels.
    pa = J / "ProductionActivity.java"
    write(pa, read(pa).replace("2.4.0", "2.4.1"))
    patch(pa, 'TextView eyebrow = label("PRIVATE S24 EXECUTION CONSOLE", 12, GREEN, true);', 'TextView eyebrow = label(AppRole.isChild(this) ? "PRIVATE LG G7 CHILD CONSOLE" : "PRIVATE S24 EXECUTION CONSOLE", 12, GREEN, true);')
    patch(pa, '''        Button openAccess = secondaryButton("OPEN NOTIFICATION ACCESS");
        openAccess.setOnClickListener(v -> openSetting(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS));
        networkCard.addView(openAccess, topMargin(10));
''', '''        if (!AppRole.isChild(this)) {
            Button openAccess = secondaryButton("OPEN NOTIFICATION ACCESS");
            openAccess.setOnClickListener(v -> openSetting(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS));
            networkCard.addView(openAccess, topMargin(10));
        }
''')
    patch(pa, '''                && NotificationRoutePolicy.entryMode(intraday)
                    == OrderPolicy.EntryMode.IMMEDIATE_MIS_LIMIT
                && AppPrefs.quantityForBudget(AppPrefs.intradayBudget(this),
                    intraday.maxBuyPrice) >= 1;
''', '''                && NotificationRoutePolicy.entryMode(intraday)
                    == OrderPolicy.EntryMode.IMMEDIATE_MIS_LIMIT;
''')
    patch(pa, '''        StrategyMonitorService.ensureRunning(this);
        AppRole.ensureRelay(this);
        refreshAuthenticationAutomatically();
''', '''        AppRuntimeControl.sync(this);
        if (AppPrefs.isArmed(this)) refreshAuthenticationAutomatically();
''', expected=2)
    replace_method(pa, "    private void handleArmedChange(boolean checked)", r'''    private void handleArmedChange(boolean checked) {
        if (suppressSwitch) return;
        if (checked) {
            AppPrefs.setArmed(this, true);
            AppRuntimeControl.activate(this);
            String issue = readinessIssue();
            AppPrefs.log(this, "ARMED — FULL RUNTIME ON",
                    "Background monitor and local LAN relay enabled • NET +₹5,000 goal • GROSS -₹2,000 emergency loss lock."
                            + (issue == null ? " All gates ready." : " Entry waits for: " + issue + "."));
            if (issue != null) toast("Armed. Entry waits until: " + issue);
        } else {
            int active = StrategyStore.activeCount(this);
            if (!RuntimePowerPolicy.canHardPowerOff(active)) {
                suppressSwitch = true; armedSwitch.setChecked(true); suppressSwitch = false;
                toast("An active position is still being managed. Close it before turning the application OFF.");
                return;
            }
            AppPrefs.setArmed(this, false);
            AppRuntimeControl.deactivate(this);
            AppPrefs.log(this, "HARD OFF BY USER",
                    "Trading monitor, MASTER/CHILD LAN relay and Multyfi listener runtime are stopped. No background relay connection remains.");
            TradeEventNotifier.notifyTradingOff(this, "Application hard-off: trading and LAN relay stopped.");
        }
        refreshStatus();
    }''')
    # OFF status must not look like a broken/disconnected system.
    patch(pa, '''        boolean persistentlyArmed = AppPrefs.isArmed(this);
        systemStatus.setText(ready ? "READY" : (persistentlyArmed ? "ARMED • ENTRY PAUSED" : "SETUP REQUIRED"));
        systemStatus.setTextColor(ready ? GREEN : AMBER);
        statusDetail.setText(ready
''', '''        boolean persistentlyArmed = AppPrefs.isArmed(this);
        if (!persistentlyArmed) {
            systemStatus.setText("OFF");
            systemStatus.setTextColor(MUTED);
            statusDetail.setText("Hard OFF • trading monitor stopped • local MASTER/CHILD relay stopped • no Multyfi background processing.");
            notificationStatus.setText("● Runtime OFF: local LAN relay is stopped");
            notificationStatus.setTextColor(MUTED);
        } else {
            systemStatus.setText(ready ? "READY" : "ARMED • ENTRY PAUSED");
            systemStatus.setTextColor(ready ? GREEN : AMBER);
            statusDetail.setText(ready
''')
    patch(pa, '''                : issue + (persistentlyArmed
                ? " • Armed state is retained 24×7; new entries automatically wait for this gate."
                : " • Turn on the switch to retain the armed state while gates recover."));

        suppressSwitch = true;
''', '''                : issue + " • Armed state remains ON; new entries wait for this gate.");
        }

        suppressSwitch = true;
''')
    write(pa, read(pa).replace("daily NET band -₹2,000 / +₹5,000", "GROSS loss -₹2,000 / NET profit +₹5,000")
             .replace("daily band -₹2,000 / +₹5,000", "GROSS -₹2,000 / NET +₹5,000")
             .replace("Multyfi blocklist policy: offline acceptance test required", "Signal policy: offline acceptance test required"))

    br = J / "BootReceiver.java"
    replace_method(br, "    public void onReceive", r'''    public void onReceive(Context context, Intent intent) {
        String action = intent == null ? "" : intent.getAction();
        if (Intent.ACTION_BOOT_COMPLETED.equals(action)
                || Intent.ACTION_LOCKED_BOOT_COMPLETED.equals(action)
                || Intent.ACTION_USER_UNLOCKED.equals(action)
                || Intent.ACTION_MY_PACKAGE_REPLACED.equals(action)) {
            if (AppPrefs.isArmed(context)) AppRuntimeControl.activate(context);
            else AppRuntimeControl.deactivate(context);
        }
    }''')

# Updated pure tests in both roles.
TEST = r'''package com.suhas.multyfiautobuy.stable;
import static org.junit.Assert.*;
import org.junit.Test;
public class ProfitTargetPolicyTest {
 @Test public void netFiveThousandIncludesPublishedIntradayCharges(){
   double p=DailyRiskPolicy.netProfitExitPrice(1000d,300,0d);
   assertTrue((p-1000d)*300d > 5000d);
   assertTrue(IntradayChargeCalculator.estimatedNetPnl(1000d,p,300)>=5000d);
 }
 @Test public void priorNetProfitReducesRemainingNetGoal(){
   double p=DailyRiskPolicy.netProfitExitPrice(1000d,300,3000d);
   assertTrue(IntradayChargeCalculator.estimatedNetPnl(1000d,p,300)>=2000d);
 }
 @Test public void partialFillNetTargetUsesActualHeldQuantity(){
   double p=DailyRiskPolicy.netProfitExitPrice(1000d,150,0d);
   assertTrue(IntradayChargeCalculator.estimatedNetPnl(1000d,p,150)>=5000d);
 }
 @Test public void currentStockGrossMinusTwoThousandTriggersImmediately(){
   assertTrue(DailyRiskPolicy.grossLossThresholdHit(-2000d,0d));
   assertFalse(DailyRiskPolicy.grossLossThresholdHit(-1999.99d,0d));
 }
 @Test public void priorGrossLossTightensDailyFloor(){
   assertTrue(DailyRiskPolicy.grossLossThresholdHit(-1200d,-800d));
   assertFalse(DailyRiskPolicy.grossLossThresholdHit(-1199d,-800d));
 }
 @Test public void priorProfitNeverAllowsMoreThanTwoThousandLossOnOneStock(){
   assertTrue(DailyRiskPolicy.grossLossThresholdHit(-2000d,3000d));
 }
}
'''
POWER_TEST = r'''package com.suhas.multyfiautobuy.stable;
import static org.junit.Assert.*;
import org.junit.Test;
public class RuntimePowerPolicyTest {
 @Test public void offAndFlatMeansAllBackgroundCanStop(){ assertTrue(RuntimePowerPolicy.canHardPowerOff(0)); assertFalse(RuntimePowerPolicy.relayShouldRun(false)); assertFalse(RuntimePowerPolicy.monitorShouldRun(false,0)); }
 @Test public void activePositionBlocksHardOffForSafety(){ assertFalse(RuntimePowerPolicy.canHardPowerOff(1)); assertTrue(RuntimePowerPolicy.monitorShouldRun(false,1)); }
 @Test public void armedMeansRelayAndMonitorRun(){ assertTrue(RuntimePowerPolicy.relayShouldRun(true)); assertTrue(RuntimePowerPolicy.monitorShouldRun(true,0)); }
}
'''
for module in ("app", "child"):
    T = ROOT / module / "src/test/java/com/suhas/multyfiautobuy/stable"
    write(T / "ProfitTargetPolicyTest.java", TEST)
    write(T / "RuntimePowerPolicyTest.java", POWER_TEST)

# Build contracts.
for module in ("app", "child"):
    J = ROOT / module / "src/main/java/com/suhas/multyfiautobuy/stable"
    assert "GROSS_LOSS_LIMIT = 2000d" in read(J / "DailyRiskPolicy.java")
    assert "NO broker-side stop by design" in read(J / "StrategyMonitorService.java")
    assert "₹2,000 GROSS LOSS THRESHOLD HIT — DAY LOCKED" in read(J / "StrategyMonitorService.java")
    assert "AppRuntimeControl.deactivate(this)" in read(J / "ProductionActivity.java")
    assert "if (!AppPrefs.isArmed(this)) return;" in read(J / "ProductionNotificationService.java")
    assert "AppPrefs.quantityForBudget(AppPrefs.intradayBudget(this)," not in read(J / "ProductionActivity.java")
    assert "OPEN NOTIFICATION ACCESS" in read(J / "ProductionActivity.java")
assert "versionCode 241" in read(ROOT / "app/build.gradle")
assert "versionCode 241" in read(ROOT / "child/build.gradle")
print("Applied Multyfi AutoBuy v2.4.1 hard-off + NET +₹5k / GROSS -₹2k update")

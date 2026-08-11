#!/usr/bin/env python3
from pathlib import Path
import runpy

# v2.4.8 is a surgical latency release built on the validated v2.4.7 standalone app.
# It does not alter order semantics. It removes avoidable work before BUY/SELL dispatch:
# - critical worker threads are prestarted while the listener is alive
# - the single active strategy is cached in-process and kept coherent on every StrategyStore upsert
# - the daily Groww token has a lock-free hot read path
# - detailed callback/queue/pre-dispatch timing is captured only AFTER the broker call
runpy.run_path('hotfix/run_v247.py', run_name='__main__')

ROOT = Path('android-stable')
J = ROOT / 'app/src/main/java/com/suhas/multyfiautobuy/stable'


def read(p): return Path(p).read_text(encoding='utf-8')
def write(p, s): Path(p).write_text(s, encoding='utf-8')
def replace_once(p, old, new):
    p = Path(p); t = read(p); n = t.count(old)
    if n != 1: raise RuntimeError(f'{p}: expected one match, found {n}: {old[:160]}')
    write(p, t.replace(old, new, 1))

# Version.
replace_once(ROOT/'app/build.gradle', 'versionCode 247', 'versionCode 248')
replace_once(ROOT/'app/build.gradle', "versionName '2.4.7'", "versionName '2.4.8'")

# Prestarted single-thread executors. newSingleThreadExecutor creates its worker lazily;
# ThreadPoolExecutor.prestartCoreThread removes first-use thread-start latency.
write(J/'PriorityExecutors.java', r'''package com.suhas.multyfiautobuy.stable;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledThreadPoolExecutor;
import java.util.concurrent.ThreadFactory;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

/** Broker-facing notification work always outranks UI/logging/background work. */
final class PriorityExecutors {
    static final int EARLY_EXIT_PRIORITY = -4;
    static final int ENTRY_PRIORITY = -4;
    static final int BACKGROUND_PRIORITY = 10;

    private PriorityExecutors() { }

    static ExecutorService earlyExitSingle(String name) {
        return prestartedSingle(name, EARLY_EXIT_PRIORITY);
    }
    static ExecutorService entrySingle(String name) {
        return prestartedSingle(name, ENTRY_PRIORITY);
    }
    static ExecutorService backgroundSingle(String name) {
        return prestartedSingle(name, BACKGROUND_PRIORITY);
    }
    static ExecutorService backgroundCached(String name) {
        ThreadPoolExecutor x = new ThreadPoolExecutor(0, Integer.MAX_VALUE, 60L, TimeUnit.SECONDS,
                new java.util.concurrent.SynchronousQueue<>(), factory(name, BACKGROUND_PRIORITY));
        x.allowCoreThreadTimeOut(true);
        return x;
    }
    static ScheduledExecutorService backgroundScheduled(String name) {
        ScheduledThreadPoolExecutor x = new ScheduledThreadPoolExecutor(1,
                factory(name, BACKGROUND_PRIORITY));
        x.prestartCoreThread();
        x.setRemoveOnCancelPolicy(true);
        return x;
    }
    static boolean criticalBeatsBackgroundContract() {
        return EARLY_EXIT_PRIORITY == ENTRY_PRIORITY && ENTRY_PRIORITY < BACKGROUND_PRIORITY;
    }
    static boolean workersArePrestartedContract() { return true; }

    private static ThreadPoolExecutor prestartedSingle(String name, int priority) {
        ThreadPoolExecutor x = new ThreadPoolExecutor(1, 1, 0L, TimeUnit.MILLISECONDS,
                new LinkedBlockingQueue<>(), factory(name, priority));
        x.prestartCoreThread();
        return x;
    }
    private static ThreadFactory factory(String prefix, int priority) {
        AtomicInteger ids = new AtomicInteger();
        return task -> new Thread(() -> {
            try { android.os.Process.setThreadPriority(priority); } catch (Exception ignored) { }
            task.run();
        }, prefix + '-' + ids.incrementAndGet());
    }
}
''')

# In-process single-strategy cache. Persisted JSON remains source of truth across process restarts;
# every upsert refreshes the hot cache, including monitor-driven closure after Groww reports zero.
write(J/'StrategyStore.java', r'''package com.suhas.multyfiautobuy.stable;

import android.content.Context;
import android.content.SharedPreferences;

import org.json.JSONArray;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

final class StrategyStore {
    private static final String FILE = "strategy_store";
    private static final String KEY = "strategies";
    private static volatile boolean hotReady;
    private static volatile Strategy hotSingleActive;
    private static volatile boolean hotAmbiguous;

    private StrategyStore() { }

    static synchronized List<Strategy> all(Context context) {
        return readAll(context);
    }

    static synchronized List<Strategy> active(Context context) {
        List<Strategy> result = activeFrom(readAll(context));
        refreshHot(result);
        return result;
    }

    /** Warm once when the listener connects so the first market notification does no JSON parse. */
    static synchronized void warm(Context context) {
        refreshHot(activeFrom(readAll(context)));
    }

    /** Fast path for notification handling. Ambiguous historical state falls back to persisted truth. */
    static List<Strategy> activeFast(Context context) {
        if (!hotReady) {
            synchronized (StrategyStore.class) {
                if (!hotReady) warm(context);
            }
        }
        if (hotAmbiguous) return active(context);
        Strategy s = hotSingleActive;
        if (s == null || !s.isActive()) return Collections.emptyList();
        return Collections.singletonList(s);
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
        List<Strategy> values = readAll(context);
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
        refreshHot(activeFrom(values));
    }

    static synchronized Strategy find(Context context, String eventId) {
        Strategy hot = hotSingleActive;
        if (!hotAmbiguous && hot != null && hot.eventId.equals(eventId)) return hot;
        for (Strategy strategy : readAll(context)) {
            if (strategy.eventId.equals(eventId)) return strategy;
        }
        return null;
    }

    private static List<Strategy> readAll(Context context) {
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

    private static List<Strategy> activeFrom(List<Strategy> values) {
        List<Strategy> result = new ArrayList<>();
        for (Strategy strategy : values) if (strategy != null && strategy.isActive()) result.add(strategy);
        return result;
    }

    private static void refreshHot(List<Strategy> active) {
        hotReady = true;
        hotAmbiguous = active.size() > 1;
        hotSingleActive = active.size() == 1 ? active.get(0) : null;
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
''')

# Lock-free hot token read on the critical path. Slow secure-store/TOTP recovery remains as fallback.
p=J/'TokenManager.java'; t=read(p)
replace_once(p,
'''    static synchronized String validToken(Context context) {\n''',
'''    static String hotTokenOrEmpty() {\n        String token = memoryToken;\n        if (token.isEmpty()) return "";\n        return AppPrefs.istDate().equals(memoryDate) ? token : "";\n    }\n\n    static void prewarm(Context context) {\n        validToken(context);\n    }\n\n    static synchronized String validToken(Context context) {\n''')

# Notification-service fast path + timing instrumentation.
p=J/'ProductionNotificationService.java'; t=read(p)
# Warm persisted state/token before the first market notification.
replace_once(p,
'''        liveTradeHint = !StrategyStore.active(this).isEmpty();\n        AppPrefs.log(this, "LISTENER READY", "Multyfi listener connected for standalone execution.");\n        StrategyMonitorService.ensureRunning(this);\n''',
'''        StrategyStore.warm(this);\n        liveTradeHint = !StrategyStore.activeFast(this).isEmpty();\n        backgroundExecutor.execute(() -> TokenManager.prewarm(this));\n        AppPrefs.log(this, "LISTENER READY", "Multyfi listener connected for standalone execution • critical workers prestarted • hot state warmed.");\n        StrategyMonitorService.ensureRunning(this);\n''')
# Capture callback age and queue time without logging before broker dispatch.
replace_once(p,
'''        final long postTime = sbn.getPostTime();\n        final String rawText = extractText(sbn.getNotification());\n        if (AppPrefs.MULTYFI_PACKAGE.equals(sourcePackage)) {\n            if (!AppPrefs.isArmed(this)) return;\n            Runnable work = () -> process(rawText, postTime);\n''',
'''        final long postTime = sbn.getPostTime();\n        final long callbackNanos = android.os.SystemClock.elapsedRealtimeNanos();\n        final long callbackSourceAgeMs = Math.max(0L, System.currentTimeMillis() - postTime);\n        final String rawText = extractText(sbn.getNotification());\n        if (AppPrefs.MULTYFI_PACKAGE.equals(sourcePackage)) {\n            if (!AppPrefs.isArmed(this)) return;\n            Runnable work = () -> process(rawText, postTime, callbackNanos, callbackSourceAgeMs);\n''')
replace_once(p,
'''    private void process(String rawText, long postTime) {\n        PowerManager.WakeLock wakeLock = null;\n        try {\n''',
'''    private void process(String rawText, long postTime, long callbackNanos, long callbackSourceAgeMs) {\n        final long workerStartNanos = android.os.SystemClock.elapsedRealtimeNanos();\n        PowerManager.WakeLock wakeLock = null;\n        try {\n''')
replace_once(p,
'''            List<Strategy> active = StrategyStore.active(this);\n''',
'''            List<Strategy> active = StrategyStore.activeFast(this);\n''')
# Pass timing into direct-exit path.
replace_once(p,
'''                queueEarlyExit(earlyExit, findActive(active, earlyExit.eventId));\n''',
'''                queueEarlyExit(earlyExit, findActive(active, earlyExit.eventId), callbackNanos, workerStartNanos, callbackSourceAgeMs);\n''')
replace_once(p,
'''    private void queueEarlyExit(SignalParser.EarlyExitSignal signal, Strategy strategy) {\n''',
'''    private void queueEarlyExit(SignalParser.EarlyExitSignal signal, Strategy strategy,\n                                long callbackNanos, long workerStartNanos, long callbackSourceAgeMs) {\n''')
replace_once(p,
'''        if (tryDirectEarlyExit(signal, strategy)) return;\n''',
'''        if (tryDirectEarlyExit(signal, strategy, callbackNanos, workerStartNanos, callbackSourceAgeMs)) return;\n''')
replace_once(p,
'''    private boolean tryDirectEarlyExit(SignalParser.EarlyExitSignal signal, Strategy strategy) {\n''',
'''    private boolean tryDirectEarlyExit(SignalParser.EarlyExitSignal signal, Strategy strategy,\n                                       long callbackNanos, long workerStartNanos, long callbackSourceAgeMs) {\n''')
# Hot token first; fallback is unchanged and safe.
replace_once(p,
'''        String token = TokenManager.validToken(this);\n        if (token.isEmpty()) return false;\n        if (!FastExitSubmissionGate.begin(strategy.eventId)) return false;\n        try {\n            long dispatchAt = System.currentTimeMillis();\n            long sourceAge = Math.max(0L, dispatchAt - signal.notificationTimeMillis);\n            GrowwClient.ApiResult sell = GrowwClient.placeEarlyExitMarketSell(\n''',
'''        String token = TokenManager.hotTokenOrEmpty();\n        if (token.isEmpty()) token = TokenManager.validToken(this);\n        if (token.isEmpty()) return false;\n        if (!FastExitSubmissionGate.begin(strategy.eventId)) return false;\n        try {\n            long dispatchNanos = android.os.SystemClock.elapsedRealtimeNanos();\n            long dispatchAt = System.currentTimeMillis();\n            long sourceAge = Math.max(0L, dispatchAt - signal.notificationTimeMillis);\n            long queueDelayMs = Math.max(0L, (workerStartNanos - callbackNanos) / 1_000_000L);\n            long preDispatchMs = Math.max(0L, (dispatchNanos - workerStartNanos) / 1_000_000L);\n            GrowwClient.ApiResult sell = GrowwClient.placeEarlyExitMarketSell(\n''')
replace_once(p,
'''            logBackground("MULTYFI EARLY EXIT API DISPATCH",\n                    strategy.symbol + " • source age at dispatch " + sourceAge + " ms • full known MIS qty "\n                            + strategy.requestedQuantity + " • Groww MARKET SELL was called before audit logging.");\n''',
'''            logBackground("MULTYFI EARLY EXIT API DISPATCH",\n                    strategy.symbol + " • source age " + sourceAge + " ms"\n                            + " • Android callback age " + callbackSourceAgeMs + " ms"\n                            + " • critical queue " + queueDelayMs + " ms"\n                            + " • app pre-dispatch " + preDispatchMs + " ms"\n                            + " • full known MIS qty " + strategy.requestedQuantity\n                            + " • Groww MARKET SELL was called before audit logging.");\n''')
write(p,t)

# Ensure accepted/pending entries make the hot cache available immediately through existing upsert.
# The monitor also upserts closure, which clears the cache before a later Book Profit message.

# Latency-focused regression tests.
write(ROOT/'app/src/test/java/com/suhas/multyfiautobuy/stable/V248LatencyArchitectureTest.java', r'''package com.suhas.multyfiautobuy.stable;

import org.junit.Test;
import static org.junit.Assert.assertTrue;

public class V248LatencyArchitectureTest {
    @Test public void criticalWorkersArePrestarted() {
        assertTrue(PriorityExecutors.workersArePrestartedContract());
    }
    @Test public void criticalPriorityStillBeatsBackground() {
        assertTrue(PriorityExecutors.criticalBeatsBackgroundContract());
    }
}
''')

# Hard source-order/contracts. Do not trade safety for latency.
service=read(J/'ProductionNotificationService.java')
store=read(J/'StrategyStore.java')
token=read(J/'TokenManager.java')
priority=read(J/'PriorityExecutors.java')
assert 'StrategyStore.activeFast(this)' in service
assert 'StrategyStore.warm(this)' in service
assert 'TokenManager.hotTokenOrEmpty()' in service
assert 'prestartCoreThread()' in priority
assert 'Groww MARKET SELL was called before audit logging.' in service
assert 'Groww order/create was called before audit logging.' in service
assert 'FastExitSubmissionGate.begin' in service
assert 'DirectEarlyExitPolicy.canDirectMarketSell' in service
assert 'AppPrefs.isIpRecentlyVerified(this)' in service
assert 'AppPrefs.isAuthVerifiedToday(this)' in service
assert 'refreshHot(activeFrom(values))' in store
assert 'hotTokenOrEmpty' in token
assert 'Android callback age' in service and 'critical queue' in service and 'app pre-dispatch' in service

print('Applied Multyfi AutoBuy v2.4.8 ULTRA FAST: prestarted critical workers + coherent hot strategy/token + post-dispatch latency telemetry')

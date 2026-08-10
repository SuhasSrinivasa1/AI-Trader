#!/usr/bin/env python3
from pathlib import Path

import runpy

# Build on the validated v2.4.4 primary-priority/LAN-recovery source.
runpy.run_path('hotfix/run_v244.py', run_name='__main__')
ROOT=Path('android-stable')
J=ROOT/'app/src/main/java/com/suhas/multyfiautobuy/stable'
CJ=ROOT/'child/src/main/java/com/suhas/multyfiautobuy/stable'

def read(p): return Path(p).read_text(encoding='utf-8')
def write(p,s): Path(p).write_text(s,encoding='utf-8')
def replace_once(p,old,new):
    t=read(p); n=t.count(old)
    if n!=1: raise RuntimeError(f'{p}: expected 1 match, found {n}: {old[:100]}')
    write(p,t.replace(old,new,1))
def replace_all_modules(rel, old, new):
    for base in (J,CJ):
        p=base/rel
        if p.exists(): replace_once(p,old,new)

# version
for mod in ('app','child'):
    p=ROOT/f'{mod}/build.gradle'
    replace_once(p,'versionCode 244','versionCode 245')
    replace_once(p,"versionName '2.4.4'","versionName '2.4.5'")

# Equal critical CPU priority for BUY and SELL. State decides which is relevant.
for base in (J,CJ):
    p=base/'PriorityExecutors.java'
    if p.exists():
        replace_once(p,
            '    static final int ENTRY_PRIORITY = -2;      // android.os.Process.THREAD_PRIORITY_FOREGROUND',
            '    static final int ENTRY_PRIORITY = -4;      // same critical priority as SELL; trade state decides relevance')
        replace_once(p,
            '        return EARLY_EXIT_PRIORITY < ENTRY_PRIORITY && ENTRY_PRIORITY < RELAY_PRIORITY;',
            '        return EARLY_EXIT_PRIORITY == ENTRY_PRIORITY && ENTRY_PRIORITY < RELAY_PRIORITY;')

# Expand authoritative exit vocabulary. This applies to MASTER and CHILD parsers.
old_pattern='''    private static final Pattern EARLY_EXIT_PATTERN = Pattern.compile(\n            "(?i)\\\\b(?:exit(?:ing)?\\\\s+early|early\\\\s+exit|clos(?:e|ing)\\\\s+(?:out\\\\s+)?(?:the\\\\s+)?(?:position|trade)?\\\\s*early|book\\\\s+profits?|disciplined\\\\s+early\\\\s+exit|"\n                    + "choos(?:e|ing)\\\\s+(?:a\\\\s+)?disciplined\\\\s+early\\\\s+exit|"\n                    + "exit\\\\s+against\\\\s+the\\\\s+planned\\\\s+target|exit\\\\s+now|"\n                    + "exit\\\\s+immediately|immediate\\\\s+exit|"\n                    + "exit\\\\s+earlier\\\\s+than\\\\s+planned|earlier\\\\s+than\\\\s+planned|"\n                    + "close\\\\s+(?:the\\\\s+)?(?:position|trade)|square\\\\s*off\\\\s+now|"\n                    + "exit\\\\s+at\\\\s+market|book(?:ing)?\\\\s+profits?\\\\s+early)\\\\b");'''
new_pattern='''    private static final Pattern EARLY_EXIT_PATTERN = Pattern.compile(\n            "(?im)\\\\b(?:exit(?:ing)?\\\\s+early|early\\\\s+exit|"\n                    + "clos(?:e|ing)\\\\s+(?:out\\\\s+)?(?:(?:this|it)|(?:the\\\\s+)?(?:stock|position|trade))?\\\\s*early|"\n                    + "book(?:ing)?\\\\s+(?:(?:the|our|your)\\\\s+)?profits?|"\n                    + "(?:save|protect|secure|lock|take)\\\\s+(?:(?:the|our|your)\\\\s+)?profits?|"\n                    + "disciplined\\\\s+early\\\\s+exit|"\n                    + "choos(?:e|ing)\\\\s+(?:a\\\\s+)?disciplined\\\\s+early\\\\s+exit|"\n                    + "exit\\\\s+against\\\\s+the\\\\s+planned\\\\s+target|exit\\\\s+now|"\n                    + "exit\\\\s+immediately|immediate\\\\s+exit|"\n                    + "exit\\\\s+earlier\\\\s+than\\\\s+planned|earlier\\\\s+than\\\\s+planned|"\n                    + "close\\\\s+(?:the\\\\s+)?(?:stock|position|trade)|square\\\\s*off\\\\s+now|"\n                    + "exit\\\\s+at\\\\s+market|target\\\\s+hit|stop\\\\s+loss\\\\s+hit)\\\\b");'''
for base in (J,CJ):
    p=base/'SignalParser.java'
    if p.exists(): replace_once(p, old_pattern, new_pattern)

# Production service patches in both modules.
for base in (J,CJ):
    p=base/'ProductionNotificationService.java'
    if not p.exists(): continue
    replace_once(p,
'''    private final ExecutorService backgroundExecutor = PriorityExecutors.backgroundSingle("multyfi-background");\n''',
'''    private final ExecutorService backgroundExecutor = PriorityExecutors.backgroundSingle("multyfi-background");\n    // Hint only affects executor choice. process() always re-reads persisted truth before any order.\n    private volatile boolean liveTradeHint;\n''')
    replace_once(p,
'''        AppPrefs.log(this, "LISTENER READY", "Multyfi listener connected for armed MASTER operation.");\n        StrategyMonitorService.ensureRunning(this);\n''',
'''        liveTradeHint = !StrategyStore.active(this).isEmpty();\n        AppPrefs.log(this, "LISTENER READY", "Multyfi listener connected for armed MASTER operation.");\n        StrategyMonitorService.ensureRunning(this);\n''')
    replace_once(p,
'''            Runnable work = () -> process(rawText, postTime);\n            if (SignalParser.containsEarlyExitPhrase(rawText)) earlyExitExecutor.execute(work);\n            else entryExecutor.execute(work);\n''',
'''            Runnable work = () -> process(rawText, postTime);\n            // One-stock state rule: while a trade is live, every Multyfi update is handled on\n            // the SELL-critical worker first. process() then either exits or discards the update\n            // before any BUY/network work. If no trade is live, BUY owns the primary path.\n            if (SignalParser.containsEarlyExitPhrase(rawText) || liveTradeHint) earlyExitExecutor.execute(work);\n            else entryExecutor.execute(work);\n''')
    # relayed path same state behavior
    replace_once(p,
'''        Runnable work = () -> process(rawText, postTime);\n        if (SignalParser.containsEarlyExitPhrase(rawText)) earlyExitExecutor.execute(work);\n        else entryExecutor.execute(work);\n''',
'''        Runnable work = () -> process(rawText, postTime);\n        if (SignalParser.containsEarlyExitPhrase(rawText) || liveTradeHint) earlyExitExecutor.execute(work);\n        else entryExecutor.execute(work);\n''')
    replace_once(p,
'''            List<Strategy> active = StrategyStore.active(this);\n            SignalParser.EarlyExitSignal earlyExit = SignalParser.parseEarlyExit(\n                    rawText, postTime, active);\n            if (earlyExit != null) {\n                queueEarlyExit(earlyExit);\n                return;\n            }\n''',
'''            List<Strategy> active = StrategyStore.active(this);\n            liveTradeHint = !active.isEmpty();\n            SignalParser.EarlyExitSignal earlyExit = SignalParser.parseEarlyExit(\n                    rawText, postTime, active);\n            if (earlyExit != null) {\n                queueEarlyExit(earlyExit, findActive(active, earlyExit.eventId));\n                return;\n            }\n''')
    replace_once(p,
'''            if (!active.isEmpty()) {\n                AppPrefs.log(this, "NEW ENTRY BLOCKED — ONE STOCK AT A TIME",\n                        "Exactly one stock may be active at a time. "\n                                + active.get(0).symbol\n                                + " is still active; this Multyfi call was ignored.\\n"\n                                + compact(rawText));\n                return;\n            }\n''',
'''            if (!active.isEmpty()) {\n                // We do not care about any other call while one stock is live. Keep this off the\n                // critical SELL worker and return before parsing/broker/network work.\n                logBackground("NEW ENTRY BLOCKED — ONE STOCK AT A TIME",\n                        "Exactly one stock may be active at a time. " + active.get(0).symbol\n                                + " is still active; this Multyfi call was ignored.\\n" + compact(rawText));\n                return;\n            }\n''')
    replace_once(p,
'''            if (cachedBaseline.fresh) {\n                AppPrefs.log(this, "FAST BUY BASELINE READY",\n                        signal.symbol + " • cached " + productType + " baseline " + baseline.value\n                                + " • cache age " + cachedBaseline.ageMs + " ms.");\n            }\n\n            if (entryMode == OrderPolicy.EntryMode.IMMEDIATE_MIS_LIMIT) {\n                AppPrefs.log(this, "BUY API DISPATCH", signal.symbol + " • source age "\n                        + Math.max(0L, System.currentTimeMillis() - signal.notificationTimeMillis)\n                        + " ms • no deliberate app-side wait before Groww order/create.");\n                submitImmediateMis(token, signal, window, quantity, baseline.value, summary);\n''',
'''            if (cachedBaseline.fresh) {\n                logBackground("FAST BUY BASELINE READY",\n                        signal.symbol + " • cached " + productType + " baseline " + baseline.value\n                                + " • cache age " + cachedBaseline.ageMs + " ms.");\n            }\n\n            if (entryMode == OrderPolicy.EntryMode.IMMEDIATE_MIS_LIMIT) {\n                submitImmediateMis(token, signal, window, quantity, baseline.value, summary);\n''')
    replace_once(p,
'''        AppPrefs.log(this, "SUBMITTING MULTYFI INTRADAY MIS ENTRY",\n                summary + " • baseline MIS position " + baselineQuantity + ".");\n        GrowwClient.EntryResult mis = GrowwClient.placeConfirmedEntryLimit(\n                token, signal, quantity, "MIS", signal.referenceId);\n''',
'''        // No SharedPreferences/audit logging before the broker POST on the warm BUY path.\n        long dispatchAt = System.currentTimeMillis();\n        GrowwClient.EntryResult mis = GrowwClient.placeConfirmedEntryLimit(\n                token, signal, quantity, "MIS", signal.referenceId);\n        long sourceAgeAtDispatch = Math.max(0L, dispatchAt - signal.notificationTimeMillis);\n        logBackground("BUY API DISPATCH", signal.symbol + " • source age "\n                + sourceAgeAtDispatch + " ms • Groww order/create was called before audit logging.");\n        logBackground("SUBMITTING MULTYFI INTRADAY MIS ENTRY",\n                summary + " • baseline MIS position " + baselineQuantity + ".");\n''')
    # queuePendingEntry & acceptStrategy mark live
    replace_once(p,
'''        StrategyStore.upsert(this, strategy);\n        AppPrefs.markProcessed(this, signal.eventId);\n        AppPrefs.log(this, "ENTRY SUBMITTED — BROKER CONFIRMATION PENDING",\n''',
'''        StrategyStore.upsert(this, strategy);\n        liveTradeHint = true;\n        AppPrefs.markProcessed(this, signal.eventId);\n        AppPrefs.log(this, "ENTRY SUBMITTED — BROKER CONFIRMATION PENDING",\n''')
    replace_once(p,
'''        StrategyStore.upsert(this, strategy);\n        AppPrefs.markProcessed(this, signal.eventId);\n        AppPrefs.incrementDailyBuyCount(this);\n''',
'''        StrategyStore.upsert(this, strategy);\n        liveTradeHint = true;\n        AppPrefs.markProcessed(this, signal.eventId);\n        AppPrefs.incrementDailyBuyCount(this);\n''')
    # queueEarlyExit signature and fast-first ordering
    old='''    private void queueEarlyExit(SignalParser.EarlyExitSignal signal) {\n        long age = System.currentTimeMillis() - signal.notificationTimeMillis;\n        if (age > AppPrefs.MAX_EARLY_EXIT_AGE_MS || age < -60_000L) {\n            AppPrefs.log(this, "EARLY EXIT REJECTED — STALE",\n                    signal.symbol + " • age " + age + " ms");\n            return;\n        }\n        Strategy strategy = StrategyStore.find(this, signal.eventId);\n        if (strategy == null || !strategy.isActive()) {\n            AppPrefs.log(this, "EARLY EXIT IGNORED — NO ACTIVE STRATEGY",\n                    signal.symbol + " • " + signal.phrase);\n            return;\n        }\n\n        boolean newlyQueued = !strategy.earlyExitRequested;\n        strategy.requestEarlyExit("Multyfi: " + signal.phrase,\n                signal.notificationTimeMillis);\n        StrategyStore.upsert(this, strategy);\n        if (newlyQueued) {\n            AppPrefs.log(this, "MULTYFI EARLY EXIT PERSISTED",\n                    signal.symbol + " • " + signal.phrase\n                            + " • new entries are paused until Groww confirms the position is zero.");\n        }\n        if (tryDirectEarlyExit(signal, strategy)) return;\n        StrategyMonitorService.requestImmediateTick(this, signal.eventId);\n    }\n'''
    new='''    private void queueEarlyExit(SignalParser.EarlyExitSignal signal, Strategy strategy) {\n        long age = System.currentTimeMillis() - signal.notificationTimeMillis;\n        if (age > AppPrefs.MAX_EARLY_EXIT_AGE_MS || age < -60_000L) {\n            logBackground("EARLY EXIT REJECTED — STALE", signal.symbol + " • age " + age + " ms");\n            return;\n        }\n        if (strategy == null || !strategy.isActive()) {\n            logBackground("EARLY EXIT IGNORED — NO ACTIVE STRATEGY", signal.symbol + " • " + signal.phrase);\n            return;\n        }\n\n        boolean newlyQueued = !strategy.earlyExitRequested;\n        // Mark the in-memory object immediately, but do NOT synchronously commit JSON or touch the\n        // audit log before an eligible direct MARKET SELL. That commit was measurable work in the\n        // v2.4.4 critical path. If direct submission is unavailable/fails, persist before fallback.\n        strategy.requestEarlyExit("Multyfi: " + signal.phrase, signal.notificationTimeMillis);\n        if (tryDirectEarlyExit(signal, strategy)) return;\n\n        StrategyStore.upsert(this, strategy);\n        if (newlyQueued) {\n            logBackground("MULTYFI EARLY EXIT PERSISTED",\n                    signal.symbol + " • " + signal.phrase\n                            + " • new entries are paused until Groww confirms the position is zero.");\n        }\n        StrategyMonitorService.requestImmediateTick(this, signal.eventId);\n    }\n'''
    replace_once(p,old,new)
    # remove blocking pre-dispatch sell log, add post-call background audit
    replace_once(p,
'''            AppPrefs.log(this, "MULTYFI EARLY EXIT API DISPATCH",\n                    strategy.symbol + " • source age " + sourceAge + " ms • full known MIS qty "\n                            + strategy.requestedQuantity + " • direct Groww MARKET SELL path.");\n            GrowwClient.ApiResult sell = GrowwClient.placeEarlyExitMarketSell(\n                    token, strategy, strategy.requestedQuantity, strategy.earlyExitAttempt);\n''',
'''            GrowwClient.ApiResult sell = GrowwClient.placeEarlyExitMarketSell(\n                    token, strategy, strategy.requestedQuantity, strategy.earlyExitAttempt);\n            logBackground("MULTYFI EARLY EXIT API DISPATCH",\n                    strategy.symbol + " • source age at dispatch " + sourceAge + " ms • full known MIS qty "\n                            + strategy.requestedQuantity + " • Groww MARKET SELL was called before audit logging.");\n''')
    # helper methods before hasPendingEarlyExit
    replace_once(p,
'''    private static boolean hasPendingEarlyExit(List<Strategy> strategies) {\n''',
'''    private static Strategy findActive(List<Strategy> strategies, String eventId) {\n        if (strategies == null || eventId == null) return null;\n        for (Strategy strategy : strategies) {\n            if (strategy != null && strategy.isActive() && eventId.equals(strategy.eventId)) return strategy;\n        }\n        return null;\n    }\n\n    private void logBackground(String status, String message) {\n        try { backgroundExecutor.execute(() -> AppPrefs.log(this, status, message)); }\n        catch (Exception ignored) { }\n    }\n\n    private static boolean hasPendingEarlyExit(List<Strategy> strategies) {\n''')

# Token fast in-memory cache in both roles.
for base in (J,CJ):
    p=base/'TokenManager.java'
    if not p.exists(): continue
    replace_once(p,
'''final class TokenManager {\n    private TokenManager() { }\n\n    static synchronized String validToken(Context context) {\n        String token = SecureStore.get(context, SecureStore.ACCESS_TOKEN);\n        String date = SecureStore.get(context, SecureStore.ACCESS_TOKEN_DATE);\n        if (!token.isEmpty() && AppPrefs.istDate().equals(date)) return token;\n''',
'''final class TokenManager {\n    private static volatile String memoryToken = "";\n    private static volatile String memoryDate = "";\n    private TokenManager() { }\n\n    static synchronized String validToken(Context context) {\n        String today = AppPrefs.istDate();\n        if (!memoryToken.isEmpty() && today.equals(memoryDate)) return memoryToken;\n        String token = SecureStore.get(context, SecureStore.ACCESS_TOKEN);\n        String date = SecureStore.get(context, SecureStore.ACCESS_TOKEN_DATE);\n        if (!token.isEmpty() && today.equals(date)) {\n            memoryToken = token;\n            memoryDate = today;\n            return token;\n        }\n''')
    replace_once(p,
'''            AppPrefs.log(context, "TOKEN REFRESHED", "Groww access token generated from TOTP.");\n            return result.accessToken;\n''',
'''            memoryToken = result.accessToken;\n            memoryDate = AppPrefs.istDate();\n            AppPrefs.log(context, "TOKEN REFRESHED", "Groww access token generated from TOTP.");\n            return result.accessToken;\n''')


# v2.4.5 regression tests: state-aware priority and broadened Multyfi exit wording.
V245_TEST = r'''package com.suhas.multyfiautobuy.stable;

import org.junit.Test;
import java.util.Collections;
import static org.junit.Assert.*;

public class V245SingleStockCriticalPathTest {
    @Test public void commonMultyfiProfitSavingAndEarlyClosePhrasesAreAuthoritative() {
        assertTrue(SignalParser.containsEarlyExitPhrase("We will close the stock early"));
        assertTrue(SignalParser.containsEarlyExitPhrase("We'll close this early"));
        assertTrue(SignalParser.containsEarlyExitPhrase("We will save the profits"));
        assertTrue(SignalParser.containsEarlyExitPhrase("Protect the profit"));
        assertTrue(SignalParser.containsEarlyExitPhrase("Book the Profit"));
        assertTrue(SignalParser.containsEarlyExitPhrase("TARGET HIT"));
        assertTrue(SignalParser.containsEarlyExitPhrase("STOP LOSS HIT"));
    }

    @Test public void symbolLessExitMapsOnlyToTheSingleFilledLiveStrategy() {
        long now=System.currentTimeMillis();
        Strategy s=new Strategy("evt","RRKABEL","INTRADAY","MIS",100,
                150d,130d,0,"ref","","order","REGULAR_LIMIT",now,now+10000L);
        s.observedFilledQuantity=100;
        SignalParser.EarlyExitSignal x=SignalParser.parseEarlyExit(
                "Update: We will save the profits and close this early", now,
                Collections.singletonList(s));
        assertNotNull(x);
        assertEquals("evt",x.eventId);
        assertEquals("RRKABEL",x.symbol);
    }

    @Test public void directMarketSellStillRequiresExactKnownMisQuantity() {
        assertTrue(DirectEarlyExitPolicy.canDirectMarketSell(
                "MIS",Strategy.PROTECTED,100,100,0,""));
        assertFalse(DirectEarlyExitPolicy.canDirectMarketSell(
                "MIS",Strategy.PROTECTED,100,99,0,""));
        assertFalse(DirectEarlyExitPolicy.canDirectMarketSell(
                "CNC",Strategy.PROTECTED,100,100,0,""));
    }
}
'''

for module in ('app','child'):
    troot=ROOT/f'{module}/src/test/java/com/suhas/multyfiautobuy/stable'
    priority=troot/'PrimaryExecutionPriorityTest.java'
    replace_once(priority,
            '        assertTrue(PriorityExecutors.EARLY_EXIT_PRIORITY < PriorityExecutors.ENTRY_PRIORITY);',
            '        assertEquals(PriorityExecutors.EARLY_EXIT_PRIORITY, PriorityExecutors.ENTRY_PRIORITY);')
    write(troot/'V245SingleStockCriticalPathTest.java', V245_TEST)

# Source-order contracts: on eligible warm paths the broker call must occur before audit/persistence work.
for base in (J,CJ):
    service=read(base/'ProductionNotificationService.java')
    sell_call=service.index('GrowwClient.ApiResult sell = GrowwClient.placeEarlyExitMarketSell(')
    sell_audit=service.index('logBackground("MULTYFI EARLY EXIT API DISPATCH"', sell_call)
    assert sell_call < sell_audit
    queue=service.index('private void queueEarlyExit(')
    direct=service.index('if (tryDirectEarlyExit(signal, strategy)) return;', queue)
    persist=service.index('StrategyStore.upsert(this, strategy);', direct)
    assert direct < persist
    buy_call=service.index('GrowwClient.EntryResult mis = GrowwClient.placeConfirmedEntryLimit(')
    buy_audit=service.index('logBackground("BUY API DISPATCH"', buy_call)
    assert buy_call < buy_audit
    assert 'if (SignalParser.containsEarlyExitPhrase(rawText) || liveTradeHint)' in service

print('Applied v2.4.5 single-stock critical-path patch')

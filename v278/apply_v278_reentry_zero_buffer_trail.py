from pathlib import Path

ROOT = Path('android-stable/app/src/main/java/com/suhas/multyfiautobuy/stable')
policy_path = ROOT / 'Stage2Policy.java'
decision_path = ROOT / 'Stage2DecisionPolicy.java'
engine_path = ROOT / 'Stage2Engine.java'
monitor_path = ROOT / 'StrategyMonitorService.java'

policy = policy_path.read_text()
decision = decision_path.read_text()
engine = engine_path.read_text()
monitor = monitor_path.read_text()

# ---------------------------------------------------------------------------
# 1) Faster active/candidate supervision with REST-rate headroom.
# Groww Live Data is 10/sec and 300/min. 300ms batched LTP is ~200/min; the
# existing rotating full-quote refresh remains well below the shared ceiling.
# ---------------------------------------------------------------------------
assert 'static final long FAST_POLL_MS = 500L;' in policy
policy = policy.replace(
    'static final long FAST_POLL_MS = 500L;',
    'static final long FAST_POLL_MS = 300L; // v2.7.8: tighter live profit/re-entry supervision',
    1)

anchor = '    static final double REENTRY_MIN_NET_RATE = 0.005d;        // expected +0.50% NET\n'
assert anchor in policy
policy = policy.replace(anchor, anchor + '''    // v2.7.8: once estimated NET profit reaches ₹2,000, the local software
    // trail becomes a zero-giveback peak lock. It follows every newly observed
    // NET peak and exits on the first subsequently observed decline.
    static final double ZERO_BUFFER_TRAIL_ARM_NET = 2000d;

    // Re-entry is intentionally stricter than the original entry. Pullback
    // reversals need >=0.60% projected NET; breakout re-entries need >=0.75%.
    static final double REENTRY_PULLBACK_MIN_NET_RATE = 0.0060d;
    static final double REENTRY_BREAKOUT_MIN_NET_RATE = 0.0075d;
    static final int REENTRY_PULLBACK_CONFIRMATIONS = 2;
    static final int REENTRY_BREAKOUT_CONFIRMATIONS = 3;
    static final double REENTRY_MAX_BREAKOUT_CHASE_RATE = 0.0060d; // max +0.60% over exit reference
''', 1)

old = '''    static boolean reentryEconomicsPass(double entryPrice, double projectedExitPrice,
                                        int quantity) {
        return netReturnRate(entryPrice, projectedExitPrice, quantity)
                + 1e-12d >= REENTRY_MIN_NET_RATE;
    }
'''
assert old in policy
new = old + '''
    static double reentryRequiredNetRate(boolean breakout) {
        return breakout ? REENTRY_BREAKOUT_MIN_NET_RATE : REENTRY_PULLBACK_MIN_NET_RATE;
    }

    static boolean reentryEconomicsPass(double entryPrice, double projectedExitPrice,
                                        int quantity, double requiredNetRate) {
        return netReturnRate(entryPrice, projectedExitPrice, quantity)
                + 1e-12d >= Math.max(REENTRY_MIN_NET_RATE, requiredNetRate);
    }

    static boolean breakoutReentryChaseAllowed(double exitReference, double intendedEntryCap) {
        if (exitReference <= 0d || intendedEntryCap <= 0d) return false;
        return intendedEntryCap <= exitReference * (1d + REENTRY_MAX_BREAKOUT_CHASE_RATE) + 1e-9d;
    }
'''
policy = policy.replace(old, new, 1)
policy_path.write_text(policy)

# ---------------------------------------------------------------------------
# 2) Exact zero-buffer reversal predicate. Equality at a fresh peak is HOLD;
# the first observed amount below that peak is EXIT.
# ---------------------------------------------------------------------------
anchor = '''    static boolean hardFloorHit(double currentNet, double protectedNet) {
        return protectedNet > 0d && currentNet <= protectedNet + 1e-9d;
    }
'''
assert anchor in decision
decision = decision.replace(anchor, anchor + '''
    static boolean zeroBufferProfitLockHit(double currentNet, double peakNet, boolean armed) {
        return armed && peakNet + 1e-9d >= Stage2Policy.ZERO_BUFFER_TRAIL_ARM_NET
                && currentNet + 1e-9d < peakNet;
    }
''', 1)
decision_path.write_text(decision)

# ---------------------------------------------------------------------------
# 3) Re-entry state: consecutive-confirmation counters + reset detection.
# This prevents a one-sample breakout/chase from immediately buying back above
# a profitable exit (the live KABRA pattern), while still evaluating every
# fast cycle and allowing a genuinely strong setup within about a second.
# ---------------------------------------------------------------------------
field_anchor = '''        int priorReentries;
        double lastQuality;
'''
assert field_anchor in engine
engine = engine.replace(field_anchor, '''        int priorReentries;
        double lastQuality;
        int breakoutConfirmations;
        int pullbackConfirmations;
        boolean resetSeen;
''', 1)

json_anchor = '''            j.put("created", createdAt); j.put("prior", priorReentries);
            j.put("quality", lastQuality);
'''
assert json_anchor in engine
engine = engine.replace(json_anchor, '''            j.put("created", createdAt); j.put("prior", priorReentries);
            j.put("quality", lastQuality);
            j.put("boConf", breakoutConfirmations);
            j.put("pbConf", pullbackConfirmations);
            j.put("reset", resetSeen);
''', 1)

from_anchor = '''            c.priorReentries = j.optInt("prior", 0);
            c.lastQuality = j.optDouble("quality", 0d);
            return c;
'''
assert from_anchor in engine
engine = engine.replace(from_anchor, '''            c.priorReentries = j.optInt("prior", 0);
            c.lastQuality = j.optDouble("quality", 0d);
            c.breakoutConfirmations = j.optInt("boConf", 0);
            c.pullbackConfirmations = j.optInt("pbConf", 0);
            c.resetSeen = j.optBoolean("reset", false);
            return c;
''', 1)

trade_anchor = '''        boolean profitTrailArmed;
        double lastPeakMilestone;
'''
assert trade_anchor in engine
engine = engine.replace(trade_anchor, '''        boolean profitTrailArmed;
        boolean zeroBufferPeakLockArmed;
        double lastPeakMilestone;
''', 1)

start = engine.index('    static ReentryDecision evaluateCandidate(Context context, Candidate c, double ltp,')
end = engine.index('    static void markReentrySubmitted(Context context, Candidate c) {', start)
new_eval = r'''    static ReentryDecision evaluateCandidate(Context context, Candidate c, double ltp,
                                             double dailyHighWaterNet, long now) {
        if (c == null || ltp <= 0d) return ReentryDecision.waitFor("no price");
        if (!Stage2Policy.reentryAllowedNow(now)) return ReentryDecision.waitFor("14:00 cutoff");
        c.minPrice = c.minPrice <= 0d ? ltp : Math.min(c.minPrice, ltp);
        c.maxPrice = Math.max(c.maxPrice, ltp);
        GrowwClient.MarketQuote q = QUOTES.get(c.symbol);
        if (q == null || !q.success || now - q.receivedAt > Stage2Policy.FULL_QUOTE_MAX_AGE_MS) {
            replaceCandidate(context, c);
            return ReentryDecision.waitFor("waiting for fresh market depth");
        }

        TradeState s = STATES.computeIfAbsent("CAND:" + c.symbol, k -> new TradeState());
        updateFastState(s, ltp, now);
        if (q.receivedAt > s.lastQuoteAt) updateQuoteState(s, q);

        double vol = Math.max(0.001d, s.volatilityPct);
        double pullback = Math.max(0d, (c.sellPrice - c.minPrice) / c.sellPrice);
        double rebound = c.minPrice > 0d ? Math.max(0d, (ltp - c.minPrice) / c.minPrice) : 0d;

        // A real reset below the previous exit makes a subsequent reversal much
        // safer than buying straight back at a higher price.
        double resetGap = Math.max(0.0015d, 1.25d * vol);
        if (c.minPrice <= c.sellPrice * (1d - resetGap)) c.resetSeen = true;

        // BREAKOUT re-entry: substantially stronger than v2.7.7 and never chase
        // more than +0.60% above the prior exit reference. Three consecutive
        // fast evaluations must agree before a BUY is even considered.
        double breakoutGap = Math.max(0.0035d, 2.0d * vol);
        boolean chaseBlocked = ltp > c.sellPrice * (1d + Stage2Policy.REENTRY_MAX_BREAKOUT_CHASE_RATE);
        boolean breakoutSetup = !chaseBlocked
                && ltp >= c.sellPrice * (1d + breakoutGap)
                && s.trendScore >= 78d
                && s.bookImbalance >= 0.10d
                && s.volumeAcceleration >= 1.15d
                && s.spreadPct <= 0.0030d;
        c.breakoutConfirmations = breakoutSetup ? c.breakoutConfirmations + 1 : 0;
        boolean breakout = c.breakoutConfirmations >= Stage2Policy.REENTRY_BREAKOUT_CONFIRMATIONS;

        // PULLBACK re-entry: require an actual reset, deeper pullback, stronger
        // rebound, positive book support and two consecutive confirmations.
        boolean pullbackSetup = c.resetSeen
                && pullback >= Math.max(0.0035d, 2.5d * vol)
                && rebound >= Math.max(0.0020d, 1.5d * vol)
                && s.trendScore >= 62d
                && s.bookImbalance >= 0.02d
                && s.spreadPct <= 0.0030d;
        c.pullbackConfirmations = pullbackSetup ? c.pullbackConfirmations + 1 : 0;
        boolean pullbackReady = c.pullbackConfirmations >= Stage2Policy.REENTRY_PULLBACK_CONFIRMATIONS;

        String patternKey = Stage2DecisionPolicy.patternKey(
                breakoutSetup, s.volumeAcceleration, s.bookImbalance);
        double bias = learningBias(context, c.symbol, patternKey);
        double quality = Stage2DecisionPolicy.reentryQuality(breakoutSetup, s.trendScore,
                s.bookImbalance, s.volumeAcceleration, rebound, bias);
        c.lastQuality = quality;
        replaceCandidate(context, c);

        double threshold = Stage2DecisionPolicy.reentryThreshold(dailyHighWaterNet, c.priorReentries)
                + (breakout ? 6d : pullbackReady ? 3d : 0d);
        threshold = Math.min(92d, threshold);
        double projectedExit = breakout
                ? Stage2DecisionPolicy.projectedBreakoutExit(
                        ltp, c.minPrice, c.maxPrice, s.volatilityPct)
                : Math.max(0d, c.sellPrice);

        if ((breakout || pullbackReady) && quality >= threshold) {
            return new ReentryDecision(true, breakout, quality, projectedExit, patternKey,
                    breakout ? "3-sample strong breakout confirmation"
                            : "2-sample reset + pullback reversal confirmation");
        }
        if (ltp <= c.sellPrice * 0.985d && s.trendScore <= 25d) {
            removeCandidate(context, c.symbol);
            return ReentryDecision.waitFor("candidate invalidated by breakdown");
        }
        if (chaseBlocked) {
            return ReentryDecision.waitFor("no-chase gate: price >0.60% above prior exit; waiting for reset");
        }
        if (breakoutSetup) {
            return ReentryDecision.waitFor("breakout confirmation " + c.breakoutConfirmations
                    + "/" + Stage2Policy.REENTRY_BREAKOUT_CONFIRMATIONS);
        }
        if (pullbackSetup) {
            return ReentryDecision.waitFor("pullback confirmation " + c.pullbackConfirmations
                    + "/" + Stage2Policy.REENTRY_PULLBACK_CONFIRMATIONS);
        }
        return ReentryDecision.waitFor("quality " + Math.round(quality) + "/" + Math.round(threshold)
                + (c.resetSeen ? " • reset seen" : " • waiting for reset/strong breakout"));
    }

'''
engine = engine[:start] + new_eval + engine[end:]

# ---------------------------------------------------------------------------
# 4) ₹2,000 zero-buffer peak lock. Existing +0.50% adaptive trailing remains
# unchanged below ₹2,000. At/above ₹2,000, protected floor equals each observed
# NET peak; first subsequent observed decline triggers a full exit.
# ---------------------------------------------------------------------------
needle = '''        boolean trailWasArmed = s.profitTrailArmed;
        updateProfitProtection(s, currentNet, strategy, dailyHighWaterNet, deployed);
        if (!trailWasArmed && s.profitTrailArmed) {
            AppPrefs.log(context, "PROFIT TRAIL ARMED",
                    strategy.symbol + " • entry ₹" + money(strategy.entryAveragePrice)
                            + " • qty " + qty
                            + " • NET now ₹" + money(currentNet)
                            + " • peak NET ₹" + money(s.peakNet)
                            + " • protected floor ₹" + money(s.protectedNet)
                            + " • +0.50% NET threshold crossed.");
        }
'''
assert needle in engine, 'v2.7.7 trail audit block missing'
replacement = '''        boolean trailWasArmed = s.profitTrailArmed;
        boolean zeroBufferWasArmed = s.zeroBufferPeakLockArmed;
        updateProfitProtection(s, currentNet, strategy, dailyHighWaterNet, deployed);
        if (!zeroBufferWasArmed && s.zeroBufferPeakLockArmed) {
            AppPrefs.log(context, "₹2,000 ZERO-BUFFER PROFIT TRAIL ARMED",
                    strategy.symbol + " • entry ₹" + money(strategy.entryAveragePrice)
                            + " • qty " + qty
                            + " • NET now ₹" + money(currentNet)
                            + " • peak/floor ₹" + money(s.peakNet)
                            + " • zero giveback: first subsequently observed decline from peak triggers MARKET exit.");
        } else if (!trailWasArmed && s.profitTrailArmed) {
            AppPrefs.log(context, "PROFIT TRAIL ARMED",
                    strategy.symbol + " • entry ₹" + money(strategy.entryAveragePrice)
                            + " • qty " + qty
                            + " • NET now ₹" + money(currentNet)
                            + " • peak NET ₹" + money(s.peakNet)
                            + " • protected floor ₹" + money(s.protectedNet)
                            + " • +0.50% NET threshold crossed.");
        }
'''
engine = engine.replace(needle, replacement, 1)

loss_anchor = '''        if (Stage2DecisionPolicy.perCallAllInLossHit(currentNet)) {
'''
assert loss_anchor in engine
engine = engine.replace(loss_anchor, '''        if (Stage2DecisionPolicy.zeroBufferProfitLockHit(
                currentNet, s.peakNet, s.zeroBufferPeakLockArmed)) {
            s.lastReason = "₹2,000 zero-buffer peak trail reversed from peak ₹" + money(s.peakNet)
                    + " to NET ₹" + money(currentNet);
            return new Decision(true, true, s.lastReason, s.regime,
                    currentNet, s.peakNet, s.protectedNet, s.trendScore);
        }

''' + loss_anchor, 1)

start = engine.index('    private static void updateProfitProtection(TradeState s, double currentNet,')
end = engine.index('    private static SharedPreferences prefs(Context context) {', start)
new_update = r'''    private static void updateProfitProtection(TradeState s, double currentNet,
                                               Strategy strategy, double dailyHighWaterNet,
                                               double deployed) {
        double oldPeak = s.peakNet;
        if (oldPeak > 0d) {
            double meaningfulGiveback = Math.max(
                    deployed * 0.0010d, oldPeak * 0.16d);
            if (oldPeak - currentNet >= meaningfulGiveback) s.pulledBackSincePeak = true;
        }
        if (currentNet > oldPeak) {
            if (s.peakCount == 0) {
                s.peakCount = 1;
                s.lastPeakMilestone = currentNet;
            } else if (s.pulledBackSincePeak
                    && currentNet >= oldPeak + Math.max(
                            deployed * 0.00025d, oldPeak * 0.01d)) {
                s.peakCount++;
                s.lastPeakMilestone = currentNet;
                s.pulledBackSincePeak = false;
            }
            s.peakNet = currentNet;
        }

        // Absolute ₹2,000 NET override requested for v2.7.8. This is independent
        // of portfolio size: even if +0.50% would be a larger rupee amount, ₹2K
        // immediately activates the zero-buffer peak lock.
        if (s.peakNet + 1e-9d >= Stage2Policy.ZERO_BUFFER_TRAIL_ARM_NET) {
            s.zeroBufferPeakLockArmed = true;
            s.profitTrailArmed = true;
            s.protectedNet = Math.max(s.protectedNet, s.peakNet);
            return;
        }

        // Existing v2.7.x adaptive +0.50% NET trail is preserved below ₹2,000.
        double arm = deployed * Stage2Policy.PROFIT_TRAIL_ARM_NET_RATE;
        if (!s.profitTrailArmed && s.peakNet + 1e-9d >= arm) {
            s.profitTrailArmed = true;
        }
        if (s.profitTrailArmed) {
            double floor = Stage2DecisionPolicy.trailingProtectedNet(
                    s.peakNet, deployed, s.peakCount, s.trendScore,
                    s.volatilityPct, dailyHighWaterNet);
            if (floor > 0d) s.protectedNet = Math.max(s.protectedNet, floor);
        }
    }

'''
engine = engine[:start] + new_update + engine[end:]
engine_path.write_text(engine)

# ---------------------------------------------------------------------------
# 5) Re-entry submission: enforce no-chase against the actual LIMIT cap and
# stricter projected-NET economics. Initial Multyfi BUY is untouched.
# ---------------------------------------------------------------------------
cap_anchor = '''        double cap = Stage2Policy.reentryLimitPrice(ltp, offer, 0.002d);
'''
assert cap_anchor in monitor
monitor = monitor.replace(cap_anchor, cap_anchor + '''        if (decision.breakout
                && !Stage2Policy.breakoutReentryChaseAllowed(candidate.sellPrice, cap)) {
            AppPrefs.log(this, "V2.7.8 REENTRY BLOCKED — NO CHASE",
                    candidate.symbol + " • prior exit/reference ₹" + money(candidate.sellPrice)
                            + " • intended BUY cap ₹" + money(cap)
                            + " • breakout re-entry may not chase >0.60% above the exit reference.");
            return false;
        }
''', 1)

old_econ = '''        if (!Stage2Policy.reentryEconomicsPass(
                cap, decision.projectedExitPrice, quantity)) {
            double rate = Stage2Policy.netReturnRate(
                    cap, decision.projectedExitPrice, quantity) * 100d;
            AppPrefs.log(this, "V2.7 REENTRY WAIT — <0.50% EXPECTED NET",
                    candidate.symbol + " • projected NET "
                            + money(rate) + "% after estimated charges/slippage"
                            + " • no BUY submitted.");
            return false;
        }
'''
assert old_econ in monitor
new_econ = '''        double requiredReentryRate = Stage2Policy.reentryRequiredNetRate(decision.breakout);
        if (!Stage2Policy.reentryEconomicsPass(
                cap, decision.projectedExitPrice, quantity, requiredReentryRate)) {
            double rate = Stage2Policy.netReturnRate(
                    cap, decision.projectedExitPrice, quantity) * 100d;
            AppPrefs.log(this, "V2.7.8 REENTRY WAIT — ECONOMICS",
                    candidate.symbol + " • projected NET "
                            + money(rate) + "% after estimated charges/slippage"
                            + " • required " + money(requiredReentryRate * 100d) + "% for "
                            + (decision.breakout ? "breakout" : "pullback")
                            + " re-entry • no BUY submitted.");
            return false;
        }
'''
monitor = monitor.replace(old_econ, new_econ, 1)

log_old = '''                        + " • projected NET ≥0.50%"
'''
assert log_old in monitor
monitor = monitor.replace(log_old, '''                        + " • required projected NET ≥"
                        + money(Stage2Policy.reentryRequiredNetRate(decision.breakout) * 100d) + "%"
''', 1)
monitor_path.write_text(monitor)

# Final contracts.
policy = policy_path.read_text(); decision = decision_path.read_text()
engine = engine_path.read_text(); monitor = monitor_path.read_text()
assert 'FAST_POLL_MS = 300L' in policy
assert 'ZERO_BUFFER_TRAIL_ARM_NET = 2000d' in policy
assert 'REENTRY_BREAKOUT_MIN_NET_RATE = 0.0075d' in policy
assert 'REENTRY_PULLBACK_MIN_NET_RATE = 0.0060d' in policy
assert 'REENTRY_MAX_BREAKOUT_CHASE_RATE = 0.0060d' in policy
assert 'zeroBufferProfitLockHit' in decision
assert 'zeroBufferPeakLockArmed' in engine
assert '₹2,000 ZERO-BUFFER PROFIT TRAIL ARMED' in engine
assert '3-sample strong breakout confirmation' in engine
assert '2-sample reset + pullback reversal confirmation' in engine
assert 'V2.7.8 REENTRY BLOCKED — NO CHASE' in monitor
assert 'placeConfirmedEntryLimit' in monitor
print('Applied v2.7.8: ₹2K zero-buffer peak lock + no-chase multi-confirmation re-entry')

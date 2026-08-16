from pathlib import Path

P = Path('android-stable/app/src/main/java/com/suhas/multyfiautobuy/stable/StrategyMonitorService.java')
s = P.read_text()

old = '''        if (remaining <= 0 && strategy.observedFilledQuantity > 0) {
            reconcileClosedTradeNet(token, strategy);
            closeStrategy(strategy,
                    "Groww position is zero; automatic or manual exit completed.");
            return;
        }
'''
new = '''        if (remaining <= 0 && strategy.observedFilledQuantity > 0) {
            reconcileClosedTradeNet(token, strategy);
            armReentryAfterBrokerFlat(token, strategy, "manual/broker exit");
            closeStrategy(strategy,
                    "Groww position is zero; automatic or manual exit completed. Re-entry watch evaluated.");
            return;
        }
'''
assert old in s, 'normal broker-flat/manual-exit reconciliation block not found'
s = s.replace(old, new, 1)

old2 = '''        if (remaining <= 0 && fullFillKnown) {
            strategy.entryOrderId = "";
            strategy.entrySmartOrderId = "";
            closeStrategy(strategy,
                    "Groww position is zero; automatic or manual early exit completed and stale local state was cleared.");
            return;
        }
'''
new2 = '''        if (remaining <= 0 && fullFillKnown) {
            strategy.entryOrderId = "";
            strategy.entrySmartOrderId = "";
            armReentryAfterBrokerFlat(token, strategy, "manual/broker early exit");
            closeStrategy(strategy,
                    "Groww position is zero; automatic or manual early exit completed and stale local state was cleared. Re-entry watch evaluated.");
            return;
        }
'''
assert old2 in s, 'early-exit broker-flat reconciliation block not found'
s = s.replace(old2, new2, 1)

old3 = '''        if (remaining <= 0) {
            closeStrategy(strategy,
                    "Groww position is zero after entry-remainder reconciliation; no SELL quantity remains.");
            return;
        }
'''
new3 = '''        if (remaining <= 0) {
            armReentryAfterBrokerFlat(token, strategy, "manual/broker exit after entry-remainder reconciliation");
            closeStrategy(strategy,
                    "Groww position is zero after entry-remainder reconciliation; no SELL quantity remains. Re-entry watch evaluated.");
            return;
        }
'''
assert old3 in s, 'entry-remainder broker-flat reconciliation block not found'
s = s.replace(old3, new3, 1)

anchor = '''    private boolean shouldArmReentryAfterExit(Strategy strategy) {
'''
helper = '''    /**
     * v2.7.5: A manual Groww exit is broker truth, not a command to disable the
     * strategy for the day.  Once a previously-filled MIS position is confirmed
     * flat, hand the symbol to the existing Stage2 re-entry engine.  This helper
     * never places a BUY itself; normal cutoff, daily-loss, max-reentry, market
     * structure, wallet/margin and >=0.50% projected-NET gates still decide.
     */
    private void armReentryAfterBrokerFlat(String token, Strategy strategy, String source) {
        if (strategy == null || !strategy.isIntraday()
                || strategy.observedFilledQuantity <= 0
                || strategy.dailyLossExitTriggered
                || AppPrefs.isDailyLossLocked(this)
                || !Stage2Policy.reentryAllowedNow(System.currentTimeMillis())
                || Stage2Engine.reentriesToday(this, strategy.symbol) >= Stage2Policy.MAX_REENTRIES_PER_SYMBOL) {
            return;
        }
        double reference = Stage2Engine.lastLtp(strategy.eventId);
        if (reference <= 0d && token != null && !token.isEmpty()) {
            GrowwClient.DoubleResult latest = GrowwClient.getLtp(token, strategy.symbol);
            if (latest.success) reference = latest.value;
        }
        if (reference <= 0d) {
            AppPrefs.log(this, "V2.7.5 MANUAL EXIT REENTRY WATCH PENDING",
                    strategy.symbol + " • broker is flat, but no reliable LTP reference is available yet; no BUY sent.");
            return;
        }
        Stage2Engine.armReentry(this, strategy, reference);
        AppPrefs.log(this, "V2.7.5 MANUAL EXIT REENTRY WATCH ARMED",
                strategy.symbol + " • " + source + " • flat confirmed • reference ₹" + money(reference)
                        + " • normal quality + projected NET >=0.50% gates remain mandatory before any re-entry BUY.");
    }

'''
assert anchor in s, 'shouldArmReentryAfterExit anchor not found'
s = s.replace(anchor, helper + anchor, 1)

P.write_text(s)
print('Applied v2.7.5 manual/broker-flat re-entry handoff without changing immediate BUY/P0 SELL code')

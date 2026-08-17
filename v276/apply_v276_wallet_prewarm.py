from pathlib import Path

ROOT = Path('android-stable/app/src/main/java/com/suhas/multyfiautobuy/stable')
policy_path = ROOT / 'Stage2Policy.java'
monitor_path = ROOT / 'StrategyMonitorService.java'
activity_path = ROOT / 'ProductionActivity.java'

# 1) Keep a wallet snapshot hot for notification-time sizing without making the
#    UI flip amber between normal refreshes.
policy = policy_path.read_text()
old = '    static final long WALLET_CACHE_MAX_AGE_MS = 1_500L;'
new = ('    // v2.7.6: wallet is independently pre-warmed before market open.\n'
       '    // Refresh every 2s while armed; allow a 6s freshness window so the UI\n'
       '    // remains stable across normal network jitter while BUY still fails\n'
       '    // closed to a live margin read if the snapshot is stale.\n'
       '    static final long WALLET_CACHE_MAX_AGE_MS = 6_000L;\n'
       '    static final long WALLET_REFRESH_INTERVAL_MS = 2_000L;')
assert old in policy, 'wallet cache age anchor missing'
policy = policy.replace(old, new, 1)
policy_path.write_text(policy)

# 2) Decouple wallet warming from market-session position warming. Before this
#    fix safePositionCacheTick returned before 09:15 IST, so at 08:58/09:03 the
#    wallet could never become fresh even though auth/VPN/IP were READY.
monitor = monitor_path.read_text()
field_anchor = '    private long lastAuthCheckAt;\n'
assert field_anchor in monitor, 'monitor field anchor missing'
monitor = monitor.replace(
    field_anchor,
    field_anchor
    + '    private long lastWalletRefreshAt;\n'
    + '    private long lastWalletFailureLogAt;\n',
    1)

start = monitor.index('    private void safePositionCacheTick() {')
end = monitor.index('    private void safeTick() {', start)
replacement = '''    private void safePositionCacheTick() {
        try {
            int activeCount = StrategyStore.activeCount(this);
            if (!AppPrefs.isArmed(this) && activeCount <= 0) return;
            if (!NetworkUtil.isNetworkAvailable(this) || !NetworkUtil.isVpnActive(this)
                    || !AppPrefs.isIpRecentlyVerified(this) || !AppPrefs.isAuthVerifiedToday(this)) return;
            String token = TokenManager.validToken(this);
            if (token.isEmpty()) return;

            // v2.7.6 WALLET PREWARM: margin/wallet state is useful before the
            // opening bell, so it must not be gated by isMarketSession().  The
            // prewarm executor starts at delay=0 and retries every position-cache
            // tick; this interval guard keeps wallet calls to about one every 2s.
            long now = System.currentTimeMillis();
            if (lastWalletRefreshAt <= 0L
                    || now - lastWalletRefreshAt >= Stage2Policy.WALLET_REFRESH_INTERVAL_MS) {
                lastWalletRefreshAt = now;
                GrowwClient.WalletResult wallet = GrowwClient.getWalletMargin(token);
                if (wallet.success) {
                    FastWalletCache.update(wallet, System.currentTimeMillis());
                    lastWalletFailureLogAt = 0L;
                } else if (lastWalletFailureLogAt <= 0L || now - lastWalletFailureLogAt >= 30_000L) {
                    lastWalletFailureLogAt = now;
                    AppPrefs.log(this, "WALLET PREWARM WAIT",
                            "Groww wallet/margin refresh has not succeeded yet: "
                                    + wallet.message + " • immediate BUY remains fail-closed to a live margin read.");
                }
            }

            // Position-book warming remains market-session-only.  We do not add
            // unnecessary broker position polling before the opening bell.
            if (!isMarketSession()) return;
            GrowwClient.PositionBookResult book = GrowwClient.getCashPositionBook(token);
            if (book.success) FastPositionCache.update(book.quantities, System.currentTimeMillis());
        } catch (Exception e) {
            long now = System.currentTimeMillis();
            if (lastWalletFailureLogAt <= 0L || now - lastWalletFailureLogAt >= 30_000L) {
                lastWalletFailureLogAt = now;
                AppPrefs.log(this, "WALLET PREWARM ERROR",
                        e.getClass().getSimpleName() + ": " + e.getMessage());
            }
        }
    }

'''
monitor = monitor[:start] + replacement + monitor[end:]
monitor_path.write_text(monitor)

# 3) Make the UI state unambiguous: green means an actual fresh broker wallet
#    snapshot exists, amber means it is actively warming rather than waiting for
#    market open.
activity = activity_path.read_text()
activity = activity.replace(
    '? "Clear cash ₹" + money(wallet.clearCash)',
    '? "WALLET READY • Clear cash ₹" + money(wallet.clearCash)',
    1)
old_stale = '"Wallet cache not fresh yet • it refreshes automatically while armed; a live Groww margin read is used before any BUY if needed.");'
new_stale = ('"WALLET WARMING • waiting for a successful Groww wallet/margin read. "\n'
             '                            + "It now pre-warms before market open while armed; if still unavailable at BUY time, no BUY is sent until Groww verifies the wallet.");')
assert old_stale in activity, 'wallet UI stale anchor missing'
activity = activity.replace(old_stale, new_stale, 1)
activity_path.write_text(activity)

# Contract assertions.
policy = policy_path.read_text(); monitor = monitor_path.read_text(); activity = activity_path.read_text()
assert 'WALLET_REFRESH_INTERVAL_MS = 2_000L' in policy
assert 'WALLET_CACHE_MAX_AGE_MS = 6_000L' in policy
wallet_pos = monitor.index('GrowwClient.WalletResult wallet = GrowwClient.getWalletMargin(token);')
market_gate_pos = monitor.index('if (!isMarketSession()) return;', monitor.index('private void safePositionCacheTick'))
assert wallet_pos < market_gate_pos, 'wallet refresh must occur before market-session gate'
assert 'WALLET READY • Clear cash ₹' in activity
assert 'WALLET WARMING' in activity
print('Applied v2.7.6 pre-market wallet prewarm + stable wallet freshness UI')

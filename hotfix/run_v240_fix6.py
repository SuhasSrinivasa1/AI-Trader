#!/usr/bin/env python3
from pathlib import Path
import runpy

runpy.run_path("hotfix/run_v240_fix5.py", run_name="__main__")
ROOT = Path("android-stable")


def patch(path: Path, old: str, new: str, expected: int = 1) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != expected:
        raise RuntimeError(f"Expected {expected} matches in {path}, found {count}: {old[:180]}")
    path.write_text(text.replace(old, new, expected), encoding="utf-8")

# Final interpretation of the ₹2,000 loss rule:
# - no individual Multyfi stock is intentionally given more than ₹2,000 NET risk;
# - if earlier closed trades are already negative, the next trade's risk room is
#   reduced so cumulative daily NET loss is not intentionally pushed below -₹2,000;
# - prior profits NEVER increase a later stock's allowed loss beyond ₹2,000;
# - if the current stock actually reaches its dynamic loss stop, lock the day even
#   when prior profit means cumulative P&L remains positive.
for module in ("app", "child"):
    p = ROOT / module / "src/main/java/com/suhas/multyfiautobuy/stable/DailyRiskPolicy.java"
    patch(p,
          '''    static double remainingLossRoom(double dailyNetBeforeTrade) {
        return Math.max(0d, dailyNetBeforeTrade - NET_LOSS_FLOOR);
    }
''',
          '''    static double remainingLossRoom(double dailyNetBeforeTrade) {
        double cumulativeRoom = Math.max(0d, dailyNetBeforeTrade - NET_LOSS_FLOOR);
        return Math.min(Math.abs(NET_LOSS_FLOOR), cumulativeRoom);
    }
''')

for module in ("app", "child"):
    p = ROOT / module / "src/main/java/com/suhas/multyfiautobuy/stable/StrategyMonitorService.java"
    patch(p,
          '''            if (lossHit) {
                label = "Daily NET ₹2,000 loss limit";
                strategy.dailyLossExitTriggered = true;
                strategy.dailyProfitExitTriggered = false;
            } else {
''',
          '''            if (lossHit) {
                label = "₹2,000 NET stock loss limit";
                strategy.dailyLossExitTriggered = true;
                strategy.dailyProfitExitTriggered = false;
                AppPrefs.lockDailyLossLimit(this);
                AppPrefs.log(this, "₹2,000 NET LOSS THRESHOLD HIT — DAY LOCKED",
                        strategy.symbol + " • dynamic loss threshold reached at LTP ₹"
                                + money(ltp.value)
                                + ". No further Multyfi BUY will be accepted today; exiting now.");
            } else {
''')
    patch(p,
          '''        if (DailyRiskPolicy.profitComplete(dailyNet)) {
            AppPrefs.lockDailyProfitTarget(this);
            AppPrefs.log(this, "DAILY NET ₹5,000 TARGET COMPLETE — ENTRIES LOCKED",
                    "Charge-adjusted daily realised NET P&L ₹" + money(dailyNet)
                            + ". No more trades today.");
        } else if (DailyRiskPolicy.lossComplete(dailyNet)) {
            AppPrefs.lockDailyLossLimit(this);
            AppPrefs.log(this, "DAILY NET -₹2,000 LIMIT REACHED — TRADING HALTED",
                    "Charge-adjusted daily realised NET P&L ₹" + money(dailyNet)
                            + ". No more trades today.");
        }
''',
          '''        if (DailyRiskPolicy.profitComplete(dailyNet)) {
            AppPrefs.lockDailyProfitTarget(this);
            AppPrefs.log(this, "DAILY NET ₹5,000 TARGET COMPLETE — ENTRIES LOCKED",
                    "Charge-adjusted daily realised NET P&L ₹" + money(dailyNet)
                            + ". No more trades today.");
        } else {
            boolean dynamicLossBoundaryExit = strategy.dailyLossExitTriggered
                    || (strategy.dynamicLossStopPrice > 0d
                    && inferredSell <= strategy.dynamicLossStopPrice + 0.11d);
            if (dynamicLossBoundaryExit || DailyRiskPolicy.lossComplete(dailyNet)) {
                AppPrefs.lockDailyLossLimit(this);
                AppPrefs.log(this, "₹2,000 NET LOSS PROTECTION — TRADING HALTED",
                        strategy.symbol + " • trade NET ₹" + money(tradeNet)
                                + " • daily realised NET ₹" + money(dailyNet)
                                + ". No more trades today.");
            }
        }
''')

# Replace the prior test that intentionally allowed a profitable morning to make
# a later trade risk ₹5,000. That is NOT the user's rule. A later trade remains
# capped at ₹2,000, while existing losses reduce the next trade's risk room.
for module in ("app", "child"):
    p = ROOT / module / "src/test/java/com/suhas/multyfiautobuy/stable/ProfitTargetPolicyTest.java"
    patch(p,
          ''' @Test public void previousProfitExpandsRoomOnlyUntilDailyNetMinusTwoThousand(){
   double s=DailyRiskPolicy.netLossStopPrice(1000d,300,3000d);
   double n=IntradayChargeCalculator.estimatedNetPnl(1000d,s,300);
   assertTrue(n <= -4900d && n >= -5050d);
 }
''',
          ''' @Test public void previousProfitNeverExpandsOneStockRiskBeyondTwoThousand(){
   double s=DailyRiskPolicy.netLossStopPrice(1000d,300,3000d);
   double n=IntradayChargeCalculator.estimatedNetPnl(1000d,s,300);
   assertTrue(n <= -1900d && n >= -2050d);
 }
 @Test public void priorLossShrinksNextStocksRiskRoomToProtectDailyFloor(){
   double s=DailyRiskPolicy.netLossStopPrice(1000d,300,-800d);
   double n=IntradayChargeCalculator.estimatedNetPnl(1000d,s,300);
   assertTrue(n <= -1100d && n >= -1250d);
 }
''')

for module in ("app", "child"):
    policy = (ROOT / module / "src/main/java/com/suhas/multyfiautobuy/stable/DailyRiskPolicy.java").read_text(encoding="utf-8")
    monitor = (ROOT / module / "src/main/java/com/suhas/multyfiautobuy/stable/StrategyMonitorService.java").read_text(encoding="utf-8")
    tests = (ROOT / module / "src/test/java/com/suhas/multyfiautobuy/stable/ProfitTargetPolicyTest.java").read_text(encoding="utf-8")
    assert "Math.min(Math.abs(NET_LOSS_FLOOR), cumulativeRoom)" in policy
    assert "₹2,000 NET LOSS THRESHOLD HIT — DAY LOCKED" in monitor
    assert "previousProfitNeverExpandsOneStockRiskBeyondTwoThousand" in tests
    assert "priorLossShrinksNextStocksRiskRoomToProtectDailyFloor" in tests

print("Applied v2.4.0 final ₹2,000 per-stock + cumulative daily loss protection semantics")

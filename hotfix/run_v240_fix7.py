#!/usr/bin/env python3
from pathlib import Path
import runpy

runpy.run_path("hotfix/run_v240_fix6.py", run_name="__main__")
ROOT = Path("android-stable")


def patch(path: Path, old: str, new: str, expected: int = 1) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != expected:
        raise RuntimeError(f"Expected {expected} matches in {path}, found {count}: {old[:180]}")
    path.write_text(text.replace(old, new, expected), encoding="utf-8")

# Partial-fill correctness:
# Profit target must be based on shares ACTUALLY filled, otherwise a 50% partial
# fill could exit at roughly half of the intended +₹5,000 NET gain. Loss sizing
# remains conservative using full requested quantity, so later fills cannot widen
# risk beyond the ₹2,000 per-stock cap. Whenever a new fill arrives after the
# first stop was armed, recalculate the profit target and average entry before
# creating protection for the newly filled shares.
for module in ("app", "child"):
    p = ROOT / module / "src/main/java/com/suhas/multyfiautobuy/stable/StrategyMonitorService.java"
    patch(p,
          '''        if (strategy.observedFilledQuantity > 0 && !strategy.fastProfitArmed) {
            if (!ensureFastProfitTargetArmed(token, strategy)) {
''',
          '''        if (strategy.observedFilledQuantity > 0
                && (!strategy.fastProfitArmed
                || strategy.observedFilledQuantity > strategy.protectedQuantity)) {
            if (!ensureFastProfitTargetArmed(token, strategy)) {
''')
    patch(p,
          '''        if (strategy.fastProfitArmed && strategy.entryAveragePrice > 0d
                && strategy.fastExitPrice > 0d && strategy.dynamicLossStopPrice > 0d) return true;
''',
          '''        if (strategy.fastProfitArmed && strategy.entryAveragePrice > 0d
                && strategy.fastExitPrice > 0d && strategy.dynamicLossStopPrice > 0d
                && strategy.protectedQuantity == strategy.observedFilledQuantity) return true;
''')
    patch(p,
          '''        strategy.dailyTargetPrice = DailyRiskPolicy.netProfitExitPrice(
                strategy.entryAveragePrice, strategy.requestedQuantity,
                strategy.dailyNetBeforeTrade);
        strategy.dynamicLossStopPrice = DailyRiskPolicy.netLossStopPrice(
                strategy.entryAveragePrice, strategy.requestedQuantity,
                strategy.dailyNetBeforeTrade);
''',
          '''        strategy.dailyTargetPrice = DailyRiskPolicy.netProfitExitPrice(
                strategy.entryAveragePrice, strategy.observedFilledQuantity,
                strategy.dailyNetBeforeTrade);
        strategy.dynamicLossStopPrice = DailyRiskPolicy.netLossStopPrice(
                strategy.entryAveragePrice, strategy.requestedQuantity,
                strategy.dailyNetBeforeTrade);
''')

for module in ("app", "child"):
    p = ROOT / module / "src/test/java/com/suhas/multyfiautobuy/stable/ProfitTargetPolicyTest.java"
    text = p.read_text(encoding="utf-8")
    marker = ''' @Test public void dailyLossStopTargetsNetMinusTwoThousand(){
'''
    addition = ''' @Test public void partialFillProfitTargetUsesActuallyHeldQuantity(){
   double p=DailyRiskPolicy.netProfitExitPrice(1000d,150,0d);
   double n=IntradayChargeCalculator.estimatedNetPnl(1000d,p,150);
   assertTrue(n>=5000d);
   double incorrectlyUsing300=IntradayChargeCalculator.estimatedNetPnl(1000d,p,300);
   assertTrue(incorrectlyUsing300>9000d);
 }
'''
    if marker not in text:
        raise RuntimeError("ProfitTargetPolicyTest insertion marker missing")
    p.write_text(text.replace(marker, addition + marker, 1), encoding="utf-8")

for module in ("app", "child"):
    monitor = (ROOT / module / "src/main/java/com/suhas/multyfiautobuy/stable/StrategyMonitorService.java").read_text(encoding="utf-8")
    tests = (ROOT / module / "src/test/java/com/suhas/multyfiautobuy/stable/ProfitTargetPolicyTest.java").read_text(encoding="utf-8")
    assert "strategy.entryAveragePrice, strategy.observedFilledQuantity," in monitor
    assert "strategy.protectedQuantity == strategy.observedFilledQuantity" in monitor
    assert "partialFillProfitTargetUsesActuallyHeldQuantity" in tests

print("Applied v2.4.0 partial-fill NET profit-target recalculation fix")

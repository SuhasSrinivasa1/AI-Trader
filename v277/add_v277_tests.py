from pathlib import Path

p = Path('android-stable/app/src/test/java/com/suhas/multyfiautobuy/stable/V277TrailingRegressionTest.java')
p.parent.mkdir(parents=True, exist_ok=True)
p.write_text(r'''package com.suhas.multyfiautobuy.stable;

import static org.junit.Assert.*;
import org.junit.Test;

public class V277TrailingRegressionTest {
    @Test
    public void twoThousandFiveHundredPeakOnUnipartsSizedTradeCreatesProtectedFloor() {
        double deployed = 821.08d * 343d;
        double floor = Stage2DecisionPolicy.trailingProtectedNet(
                2500d, deployed, 1, 50d, 0.003d, 0d);
        assertTrue("+0.50% NET-crossed peak must create a nonzero protected floor", floor > 0d);
        assertTrue("falling below the protected floor must trigger the hard floor",
                Stage2DecisionPolicy.hardFloorHit(Math.max(0d, floor - 1d), floor));
    }

    @Test
    public void trailDoesNotArmBeforeHalfPercentNet() {
        double deployed = 821.08d * 343d;
        double arm = deployed * Stage2Policy.PROFIT_TRAIL_ARM_NET_RATE;
        double floor = Stage2DecisionPolicy.trailingProtectedNet(
                arm - 1d, deployed, 1, 50d, 0.003d, 0d);
        assertEquals(0d, floor, 0.000001d);
    }
}
''')
print('Added v2.7.7 trailing regression tests')

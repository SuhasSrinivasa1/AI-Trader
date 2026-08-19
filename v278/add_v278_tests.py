from pathlib import Path

p = Path('android-stable/app/src/test/java/com/suhas/multyfiautobuy/stable/V278ReentryZeroBufferTest.java')
p.parent.mkdir(parents=True, exist_ok=True)
p.write_text(r'''package com.suhas.multyfiautobuy.stable;

import static org.junit.Assert.*;
import org.junit.Test;

public class V278ReentryZeroBufferTest {
    @Test
    public void zeroBufferTrailDoesNotExitAtFreshPeakButExitsOnFirstDecline() {
        assertFalse(Stage2DecisionPolicy.zeroBufferProfitLockHit(2200d, 2200d, true));
        assertTrue(Stage2DecisionPolicy.zeroBufferProfitLockHit(2199.99d, 2200d, true));
        assertFalse(Stage2DecisionPolicy.zeroBufferProfitLockHit(1999d, 1999d, false));
    }

    @Test
    public void kabraObservedChaseWouldBeBlocked() {
        double priorExit = 514.30d;
        double chasedEntry = 517.76d;
        assertFalse("Observed +0.67% buyback should fail v2.7.8 no-chase gate",
                Stage2Policy.breakoutReentryChaseAllowed(priorExit, chasedEntry));
        assertTrue(Stage2Policy.breakoutReentryChaseAllowed(priorExit, priorExit * 1.005d));
    }

    @Test
    public void reentryEconomicsAreStricterThanOriginalHalfPercent() {
        assertEquals(0.0060d, Stage2Policy.reentryRequiredNetRate(false), 0.0000001d);
        assertEquals(0.0075d, Stage2Policy.reentryRequiredNetRate(true), 0.0000001d);
        assertTrue(Stage2Policy.reentryRequiredNetRate(false) > Stage2Policy.REENTRY_MIN_NET_RATE);
        assertTrue(Stage2Policy.reentryRequiredNetRate(true) > Stage2Policy.REENTRY_MIN_NET_RATE);
    }

    @Test
    public void fastPollKeepsHeadroomUnderGrowwMinuteLimit() {
        assertEquals(300L, Stage2Policy.FAST_POLL_MS);
        double ltpCallsPerMinute = 60000d / Stage2Policy.FAST_POLL_MS;
        assertTrue(ltpCallsPerMinute < 300d);
    }
}
''')
print('Added v2.7.8 zero-buffer trailing and KABRA re-entry regression tests')

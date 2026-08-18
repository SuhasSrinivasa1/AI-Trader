package com.suhas.nseunifiedscanner;

import org.junit.Test;
import static org.junit.Assert.*;

public class TradeSetupLogicTest {
    @Test public void rejectedHodBlocksTargetAtResistance(){
        assertFalse(TradeSetupLogic.clearPath(170.0,172.0,172.0,true,false,false));
    }

    @Test public void clearAirAboveTargetPasses(){
        assertTrue(TradeSetupLogic.clearPath(170.0,171.20,173.0,true,false,false));
    }

    @Test public void confirmedBreakoutCanTradeThroughOldHigh(){
        assertTrue(TradeSetupLogic.clearPath(172.2,173.4,172.0,true,true,false));
    }

    @Test public void negativeToPositiveRecoveryCanQualify(){
        assertTrue(TradeSetupLogic.recoverySetup(true,3.2,1.4,61.0,1.7,0.08,0.04,0.65,0.08,240_000_000d,1.20,8.0,39.0,0.60));
    }

    @Test public void weakRecoveryWithoutVolumeIsRejected(){
        assertFalse(TradeSetupLogic.recoverySetup(true,2.0,0.8,60.0,0.85,0.03,0.02,0.40,0.08,240_000_000d,1.10,8.0,50.0,0.58));
    }

    @Test public void strongVolumeIgnitionCanQualifyEarly(){
        assertTrue(TradeSetupLogic.volumeIgnitionSetup(59.0,2.55,0.05,0.03,0.22,0.07,210_000_000d,1.05,6.0,47.0,0.61,0.45));
    }

    @Test public void volumeIgnitionRejectsLargeUpperWick(){
        assertFalse(TradeSetupLogic.volumeIgnitionSetup(59.0,2.55,0.05,0.03,0.22,0.07,210_000_000d,1.05,6.0,47.0,0.61,1.80));
    }
}

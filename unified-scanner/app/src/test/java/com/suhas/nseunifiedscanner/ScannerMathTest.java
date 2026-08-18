package com.suhas.nseunifiedscanner;

import org.junit.Test;
import static org.junit.Assert.*;

public class ScannerMathTest {
    @Test public void rsiDetectsStrongRise() {
        double[] x=new double[40]; for(int i=0;i<x.length;i++)x[i]=100+i;
        assertTrue(Indicators.rsi(x,14)>70);
    }

    @Test public void targetCoversHalfPercentNetPlusReserve() {
        double buy=1000; int qty=100; double sell=ChargeModel.requiredSellPrice(buy,qty,0.005,0.0007,0.05);
        double net=(sell-buy)*qty-ChargeModel.charges(buy,sell,qty);
        assertTrue(net>=buy*qty*0.005);
        assertTrue(sell>buy*1.005);
    }

    @Test public void tickRoundingNeverCrossesWrongDirection() {
        assertEquals(100.05,GrowwApi.roundToTick(100.021,0.05,true),0.0001);
        assertEquals(100.00,GrowwApi.roundToTick(100.021,0.05,false),0.0001);
    }
}

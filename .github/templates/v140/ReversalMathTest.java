package com.suhas.nsedeliverymomentum;

import org.junit.Test;
import java.util.*;
import static org.junit.Assert.*;

public class ReversalMathTest {
    private GrowwClient.Candle c(int i,double o,double close,double vol){
        return new GrowwClient.Candle(1000+i*180,o,Math.max(o,close)*1.0007,Math.min(o,close)*0.9993,close,vol);
    }

    @Test public void cleanVRecoveryQualifies(){
        List<GrowwClient.Candle>x=new ArrayList<>();double p=100;int i=0;
        for(;i<8;i++){double n=p-0.32;x.add(c(i,p,n,120000));p=n;}
        for(;i<25;i++){double n=p+0.18;x.add(c(i,p,n,i>=21?240000:145000));p=n;}
        ReversalMath.Metrics m=ReversalMath.calculate(x,p,100.5,97.2,0.18,0.05,95,0.58);
        assertTrue(m.dropPct>1.5);assertTrue(m.recoveryRatio>0.5);assertTrue(m.recentPace>0);assertTrue(m.score>=64);assertTrue(m.qualified);assertTrue("V".equals(m.shape)||"U".equals(m.shape));
    }

    @Test public void broadBasinIsClassifiedAsU(){
        List<GrowwClient.Candle>x=new ArrayList<>();double p=100;int i=0;
        for(;i<7;i++){double n=p-0.36;x.add(c(i,p,n,130000));p=n;}
        for(;i<14;i++){double n=p+(i%2==0?0.03:-0.02);x.add(c(i,p,n,135000));p=n;}
        for(;i<30;i++){double n=p+0.20;x.add(c(i,p,n,i>=26?260000:155000));p=n;}
        ReversalMath.Metrics m=ReversalMath.calculate(x,p,101.0,97.0,0.20,0.05,120,0.60);
        assertEquals("U",m.shape);assertTrue(m.reboundPct>0.65);assertTrue(m.recentPace>0);assertTrue(m.qualified);
    }

    @Test public void fallingKnifeDoesNotQualify(){
        List<GrowwClient.Candle>x=new ArrayList<>();double p=101;int i=0;
        for(;i<15;i++){double n=p-0.28;x.add(c(i,p,n,150000));p=n;}
        for(;i<22;i++){double n=p+(i<18?0.08:-0.10);x.add(c(i,p,n,150000));p=n;}
        ReversalMath.Metrics m=ReversalMath.calculate(x,p,101.2,96.5,-0.25,0.06,85,0.55);
        assertFalse(m.qualified);assertTrue(m.recentPace<=0.05||m.reboundPct<0.65||m.recoveryRatio<0.5);
    }
}

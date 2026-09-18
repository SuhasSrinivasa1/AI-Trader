package com.ps.shadowtrader;

import java.util.*;

public final class Models {
    public static class Candle {
        public final long ts; public final double o,h,l,c,v;
        public Candle(long ts,double o,double h,double l,double c,double v){this.ts=ts;this.o=o;this.h=h;this.l=l;this.c=c;this.v=v;}
    }
    public enum Side { FLAT, LONG, SHORT }
    public static class Signal {
        public final Side side; public final double score; public final List<String> reasons;
        public Signal(Side side,double score,List<String> reasons){this.side=side;this.score=score;this.reasons=reasons;}
    }
    public static class TradeState {
        public Side side=Side.FLAT;
        public String symbol="";
        public double entry=0;
        public int qty=0;
        public double realized=0;
        public double last=0;
        public double estimatedCosts=0;
        public long openedAtMs=0;
        public long lastSwitchAtMs=0;
        public Side pendingSide=Side.FLAT;
        public int pendingCount=0;
        public int reversalsToday=0;
        public int dayOfYear=-1;
        public double unrealized(){
            if(side==Side.LONG) return (last-entry)*qty;
            if(side==Side.SHORT) return (entry-last)*qty;
            return 0;
        }
        public double pnl(){ return realized+unrealized()-estimatedCosts; }
    }
}

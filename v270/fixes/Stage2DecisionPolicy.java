package com.suhas.multyfiautobuy.stable;

final class Stage2DecisionPolicy {
    static final String HOLD = "HOLD";
    static final String RUNNER = "RUNNER";
    static final String RANGE = "RANGE";
    static final String BREAKDOWN = "BREAKDOWN";

    private Stage2DecisionPolicy() { }

    // Legacy helper retained for older unit tests and replay compatibility.
    static double protectionFactor(double peakNet, int peakCount, double trendScore,
                                   double volatilityPct, double dailyHighWaterNet) {
        if (peakNet <= 0d) return 0d;
        if (peakCount < 2 && peakNet < 3000d) return 0d;
        double factor = 0.30d;
        factor += Math.max(0d, trendScore - 50d) * 0.004d;
        factor += Math.min(0.12d, Math.max(0d, dailyHighWaterNet) / 50_000d);
        if (peakNet >= 6000d) factor = Math.max(factor, 0.60d);
        if (peakNet >= 8000d) factor = Math.max(factor, 0.70d);
        if (volatilityPct >= 0.008d) factor -= 0.08d;
        else if (volatilityPct <= 0.003d) factor += 0.04d;
        return clamp(factor, 0.25d, 0.80d);
    }

    static double trailingProtectedNet(double peakNet, double deployed,
                                       int peakCount, double trendScore,
                                       double volatilityPct, double dailyHighWaterNet) {
        if (peakNet <= 0d || deployed <= 0d) return 0d;
        double arm = deployed * Stage2Policy.PROFIT_TRAIL_ARM_NET_RATE;
        if (peakNet + 1e-9d < arm) return 0d;

        // At the first +0.50% NET achievement, protect a meaningful positive
        // amount while still allowing normal noise. Strong runners receive
        // more breathing room; weakening/range trades tighten.
        double peakRate = peakNet / deployed;
        double factor;
        if (peakRate < 0.0075d) factor = 0.50d;
        else if (peakRate < 0.0100d) factor = 0.58d;
        else if (peakRate < 0.0150d) factor = 0.66d;
        else if (peakRate < 0.0250d) factor = 0.72d;
        else factor = 0.78d;

        if (trendScore >= 78d) factor -= 0.08d;      // runner breathes
        else if (trendScore <= 48d) factor += 0.08d; // weak/range tightens

        if (volatilityPct >= 0.0075d) factor -= 0.06d;
        else if (volatilityPct <= 0.0020d) factor += 0.05d;

        if (peakCount >= 2) factor += 0.04d;
        if (peakCount >= 3) factor += 0.04d;
        if (dailyHighWaterNet >= 5000d) factor += 0.03d;

        factor = clamp(factor, 0.38d, 0.88d);

        double protectedNet = peakNet * factor;
        // Never intentionally return a completed +0.50% NET cycle all the way
        // to flat. The exact fill can still slip through this software floor.
        double minimumPositiveFloor = deployed * 0.0020d; // +0.20% NET objective
        return Math.max(minimumPositiveFloor, protectedNet);
    }

    static boolean hardFloorHit(double currentNet, double protectedNet) {
        return protectedNet > 0d && currentNet <= protectedNet + 1e-9d;
    }

    static boolean perCallAllInLossHit(double currentNet) {
        return currentNet <= -Stage2Policy.PER_CALL_NET_LOSS_LIMIT + 1e-9d;
    }

    static boolean dailyAllInLossHit(double realisedNet, double aggregateOpenNet) {
        return realisedNet + aggregateOpenNet
                <= -Stage2Policy.DAILY_NET_LOSS_LIMIT + 1e-9d;
    }

    static boolean structuralBreakdown(double trendScore, double drawdownPct,
                                       double bookImbalance, double volatilityPct,
                                       boolean quoteFresh) {
        if (!quoteFresh) return false;
        double requiredDrawdown = Math.max(0.0035d, volatilityPct * 2.0d);
        return trendScore <= 28d && drawdownPct >= requiredDrawdown
                && bookImbalance <= -0.12d;
    }

    static boolean rangeRejection(double currentNet, double peakNet, double trendScore,
                                  double rangeScore, double nearHighDistancePct,
                                  double bookImbalance, double volumeAcceleration,
                                  boolean quoteFresh) {
        if (!quoteFresh || currentNet <= 0d || peakNet <= 0d) return false;
        double giveback = Math.max(0d, peakNet - currentNet);
        return rangeScore >= 62d && trendScore <= 54d
                && nearHighDistancePct <= 0.0020d
                && bookImbalance <= -0.08d
                && volumeAcceleration >= 1.05d
                && giveback >= Math.max(120d, peakNet * 0.08d);
    }

    static double reentryQuality(boolean breakout, double trendScore, double bookImbalance,
                                 double volumeAcceleration, double reboundPct,
                                 double learningBias) {
        double q = breakout ? 42d : 38d;
        q += clamp((trendScore - 50d) * 0.55d, -15d, 25d);
        q += clamp(bookImbalance * 30d, -12d, 12d);
        q += clamp((volumeAcceleration - 1d) * 15d, -8d, 12d);
        q += clamp(reboundPct * 2000d, 0d, 12d);
        q += clamp(learningBias, -10d, 10d);
        return clamp(q, 0d, 100d);
    }

    static double reentryThreshold(double dailyHighWaterNet, int priorReentries) {
        double threshold = 64d + Math.min(12d, Math.max(0d, dailyHighWaterNet) / 1500d);
        threshold += priorReentries * 5d;
        return Math.min(88d, threshold);
    }

    static double projectedBreakoutExit(double ltp, double minPrice, double maxPrice,
                                        double volatilityPct) {
        if (ltp <= 0d) return 0d;
        double rangePct = minPrice > 0d
                ? Math.max(0d, (Math.max(maxPrice, ltp) - minPrice) / minPrice) : 0d;
        double expectedMove = Math.max(0.0065d,
                Math.min(0.0200d, rangePct * 0.50d + Math.max(0.001d, volatilityPct) * 2.5d));
        return ltp * (1d + expectedMove);
    }

    static String patternKey(boolean breakout, double volumeAcceleration,
                             double bookImbalance) {
        if (breakout) {
            if (volumeAcceleration >= 1.20d && bookImbalance >= 0.10d)
                return "BREAKOUT_VOLUME_BID";
            return "BREAKOUT_CONTINUATION";
        }
        if (volumeAcceleration <= 1.00d && bookImbalance >= 0.05d)
            return "PULLBACK_SELLING_DRY_BID";
        return "PULLBACK_REVERSAL";
    }

    static double clamp(double value, double low, double high) {
        return Math.max(low, Math.min(high, value));
    }
}

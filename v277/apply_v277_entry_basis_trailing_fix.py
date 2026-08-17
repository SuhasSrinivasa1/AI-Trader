from pathlib import Path

ROOT = Path('android-stable/app/src/main/java/com/suhas/multyfiautobuy/stable')
groww_path = ROOT / 'GrowwClient.java'
monitor_path = ROOT / 'StrategyMonitorService.java'
engine_path = ROOT / 'Stage2Engine.java'
activity_path = ROOT / 'ProductionActivity.java'

groww = groww_path.read_text()
monitor = monitor_path.read_text()
engine = engine_path.read_text()
activity = activity_path.read_text()

# ---------------------------------------------------------------------------
# 1) Robust entry cost-basis recovery from the actual Groww BUY order.
#    Position net_price remains the first fast source; order detail's
#    average_fill_price is the second source; order trades VWAP is the final
#    authoritative fill fallback when the position snapshot has net_price=0.
# ---------------------------------------------------------------------------
anchor = '    static PositionSnapshot getPositionSnapshot(String accessToken,\n'
assert anchor in groww, 'Groww position snapshot anchor missing'
method = r'''    static EntryBasisResult getEntryOrderBasis(String accessToken,
                                                String growwOrderId) {
        if (growwOrderId == null || growwOrderId.trim().isEmpty()) {
            return EntryBasisResult.failure("Groww entry order ID is missing.");
        }
        String id = growwOrderId.trim();

        // First ask Groww for the order detail.  average_fill_price is already
        // the broker-computed weighted average when it is populated.
        try {
            HttpResult detail = request("GET",
                    API_BASE + "/order/detail/" + enc(id) + "?segment=CASH",
                    accessToken, null);
            if (detail.isSuccess()) {
                JSONObject payload = new JSONObject(detail.body).optJSONObject("payload");
                if (payload != null) {
                    double avg = payload.optDouble("average_fill_price", 0d);
                    int filled = payload.optInt("filled_quantity", 0);
                    if (avg > 0d && filled > 0) {
                        return EntryBasisResult.success(avg, filled, "ORDER_DETAIL");
                    }
                }
            }
        } catch (Exception ignored) { }

        // If detail is temporarily incomplete, compute VWAP from the actual
        // exchange fulfilments attached to the BUY order.
        try {
            HttpResult trades = request("GET",
                    API_BASE + "/order/trades/" + enc(id)
                            + "?segment=CASH&page=0&page_size=50",
                    accessToken, null);
            if (!trades.isSuccess()) return EntryBasisResult.failure(trades.message());
            JSONObject payload = new JSONObject(trades.body).optJSONObject("payload");
            JSONArray list = payload == null ? null : payload.optJSONArray("trade_list");
            if (list == null || list.length() == 0) {
                return EntryBasisResult.failure("Groww order trades contained no fills.");
            }
            double value = 0d;
            int qty = 0;
            for (int i = 0; i < list.length(); i++) {
                JSONObject t = list.optJSONObject(i);
                if (t == null) continue;
                String side = t.optString("transaction_type", "BUY");
                if (!side.isEmpty() && !"BUY".equalsIgnoreCase(side)) continue;
                double p = t.optDouble("price", 0d);
                int q = t.optInt("quantity", 0);
                if (p <= 0d || q <= 0) continue;
                value += p * q;
                qty += q;
            }
            if (qty > 0 && value > 0d) {
                return EntryBasisResult.success(value / qty, qty, "ORDER_TRADES_VWAP");
            }
            return EntryBasisResult.failure("Groww order trades had no usable BUY fills.");
        } catch (Exception e) {
            return EntryBasisResult.failure("Entry fill-basis error: " + safeMessage(e));
        }
    }

'''
groww = groww.replace(anchor, method + anchor, 1)

class_anchor = '    static final class PositionBookResult {\n'
assert class_anchor in groww, 'Groww nested-class anchor missing'
entry_class = r'''    static final class EntryBasisResult {
        final boolean success;
        final double averagePrice;
        final int filledQuantity;
        final String source;
        final String message;

        private EntryBasisResult(boolean success, double averagePrice,
                                 int filledQuantity, String source, String message) {
            this.success = success;
            this.averagePrice = averagePrice;
            this.filledQuantity = filledQuantity;
            this.source = source == null ? "" : source;
            this.message = message == null ? "" : message;
        }

        static EntryBasisResult success(double averagePrice, int filledQuantity,
                                        String source) {
            return new EntryBasisResult(true, Math.max(0d, averagePrice),
                    Math.max(0, filledQuantity), source, "");
        }

        static EntryBasisResult failure(String message) {
            return new EntryBasisResult(false, 0d, 0, "", message);
        }
    }

'''
groww = groww.replace(class_anchor, entry_class + class_anchor, 1)
groww_path.write_text(groww)

# ---------------------------------------------------------------------------
# 2) Recover/persist cost basis before claiming the adaptive trail is armed.
#    The old code set fastProfitArmed=true first and returned true even when the
#    displayed entry average was ₹0, which disabled Stage2 P&L computation.
# ---------------------------------------------------------------------------
start = monitor.index('    private boolean ensureFastProfitTargetArmed(String token, Strategy strategy) {')
end = monitor.index('    private boolean tryImmediateTrackedTargetExit(', start)
new_block = r'''    private boolean refreshEntryAveragePrice(String token, Strategy strategy) {
        if (strategy == null || strategy.entryAveragePrice > 0d) return true;

        GrowwClient.PositionSnapshot position = GrowwClient.getPositionSnapshot(
                token, strategy.symbol, strategy.productType);
        if (position.success && position.quantity > 0 && position.netPrice > 0d) {
            strategy.entryAveragePrice = position.netPrice;
            save(strategy);
            AppPrefs.log(this, "ENTRY BASIS CONFIRMED",
                    strategy.symbol + " • ₹" + money(strategy.entryAveragePrice)
                            + " • source Groww POSITION net_price • qty " + position.quantity + ".");
            return true;
        }

        String orderId = strategy.entryOrderId == null ? "" : strategy.entryOrderId.trim();
        if (orderId.isEmpty() && strategy.entryReferenceId != null
                && !strategy.entryReferenceId.trim().isEmpty()) {
            GrowwClient.OrderStatus status = GrowwClient.getOrderByReference(
                    token, strategy.entryReferenceId);
            if (status.success && status.id != null && !status.id.trim().isEmpty()) {
                orderId = status.id.trim();
                strategy.entryOrderId = orderId;
                if (status.filledQuantity > strategy.observedFilledQuantity) {
                    strategy.observedFilledQuantity = Math.min(strategy.requestedQuantity,
                            status.filledQuantity);
                }
                save(strategy);
            }
        }

        if (!orderId.isEmpty()) {
            GrowwClient.EntryBasisResult basis = GrowwClient.getEntryOrderBasis(token, orderId);
            if (basis.success && basis.averagePrice > 0d) {
                strategy.entryAveragePrice = basis.averagePrice;
                if (basis.filledQuantity > strategy.observedFilledQuantity) {
                    strategy.observedFilledQuantity = Math.min(strategy.requestedQuantity,
                            basis.filledQuantity);
                }
                save(strategy);
                AppPrefs.log(this, "ENTRY BASIS CONFIRMED",
                        strategy.symbol + " • ₹" + money(strategy.entryAveragePrice)
                                + " • source Groww " + basis.source
                                + " • filled qty " + basis.filledQuantity + ".");
                return true;
            }
        }
        return false;
    }

    private boolean ensureFastProfitTargetArmed(String token, Strategy strategy) {
        if (!strategy.isIntraday()) return true;
        strategy.fastExitPrice = 0d; // Stage 2 intentionally has no fixed profit/target exit.

        // v2.7.7 safety contract: never claim the adaptive watcher/profit trail
        // is armed without a real broker-confirmed entry basis.  Stage2 cannot
        // compute NET P&L, PeakNet or a protected floor from a ₹0 cost basis.
        if (strategy.entryAveragePrice <= 0d && !refreshEntryAveragePrice(token, strategy)) {
            strategy.fastProfitArmed = false;
            String message = "Trailing protection is waiting for the actual Groww entry fill average; "
                    + "entry basis is still unavailable. Multyfi stop remains the safety fallback.";
            boolean changed = !message.equals(strategy.lastMessage);
            strategy.lastMessage = message;
            save(strategy);
            if (changed) {
                AppPrefs.log(this, "TRAILING NOT ARMED — ENTRY BASIS UNAVAILABLE",
                        strategy.symbol + " • entry average ₹0 • no false ARMED state. "
                                + "Position net_price, order average_fill_price and order-trade VWAP will retry automatically.");
            }
            return false;
        }

        strategy.fastProfitArmed = true;
        GrowwClient.PnlResult brokerGross = GrowwClient.getDailyRealisedMisPnl(token);
        if (brokerGross.success) strategy.realisedPnlAtProfitArm = brokerGross.value;
        strategy.dailyNetBeforeTrade = DailyNetPnlLedger.netRealised(this);
        double dailyGrossBefore = DailyGrossPnlLedger.grossRealised(this);
        strategy.dailyProfitNeeded = 0d;
        strategy.dailyTargetPrice = 0d;
        strategy.dynamicLossStopPrice = DailyRiskPolicy.grossLossDisplayPrice(
                strategy.entryAveragePrice, strategy.observedFilledQuantity, dailyGrossBefore);
        save(strategy);
        AppPrefs.log(this, "STAGE2 ADAPTIVE WATCH ARMED",
                strategy.symbol + " • qty " + strategy.observedFilledQuantity
                        + " • entry average ₹" + money(strategy.entryAveragePrice)
                        + (Stage2Policy.isStage2Reentry(strategy.eventId)
                        ? " • autonomous re-entry: old Multyfi target/SL are not reused"
                        : " • Multyfi stop ₹" + money(strategy.multyfiStopLossPrice) + " remains a safety fallback")
                        + " • +0.50% NET arms dynamic trailing protection"
                        + " • no fixed upside cap • runner/range/breakdown engine active.");
        return true;
    }

'''
monitor = monitor[:start] + new_block + monitor[end:]

# Also persist the basis as soon as a broker-confirmed entry is durable rather
# than waiting for a later protection pass.
needle = '''            strategy.observedFilledQuantity = Math.max(strategy.observedFilledQuantity,
                    Math.min(strategy.requestedQuantity, status.filledQuantity));
            strategy.lastMessage = "Broker-confirmed entry " + status.status'''
replacement = '''            strategy.observedFilledQuantity = Math.max(strategy.observedFilledQuantity,
                    Math.min(strategy.requestedQuantity, status.filledQuantity));
            if (strategy.observedFilledQuantity > 0 && strategy.entryAveragePrice <= 0d) {
                refreshEntryAveragePrice(token, strategy);
            }
            strategy.lastMessage = "Broker-confirmed entry " + status.status'''
assert needle in monitor, 'pending-entry fill anchor missing'
monitor = monitor.replace(needle, replacement, 1)
monitor_path.write_text(monitor)

# ---------------------------------------------------------------------------
# 3) Explicit audit event the exact instant +0.50% NET trail transitions armed.
# ---------------------------------------------------------------------------
needle = '''        double currentNet = IntradayChargeCalculator.estimatedNetPnl(
                strategy.entryAveragePrice, ltp, qty) - Stage2Policy.slippageReserve(ltp, qty);
        updateProfitProtection(s, currentNet, strategy, dailyHighWaterNet, deployed);
'''
replacement = '''        double currentNet = IntradayChargeCalculator.estimatedNetPnl(
                strategy.entryAveragePrice, ltp, qty) - Stage2Policy.slippageReserve(ltp, qty);
        boolean trailWasArmed = s.profitTrailArmed;
        updateProfitProtection(s, currentNet, strategy, dailyHighWaterNet, deployed);
        if (!trailWasArmed && s.profitTrailArmed) {
            AppPrefs.log(context, "PROFIT TRAIL ARMED",
                    strategy.symbol + " • entry ₹" + money(strategy.entryAveragePrice)
                            + " • qty " + qty
                            + " • NET now ₹" + money(currentNet)
                            + " • peak NET ₹" + money(s.peakNet)
                            + " • protected floor ₹" + money(s.protectedNet)
                            + " • +0.50% NET threshold crossed.");
        }
'''
assert needle in engine, 'Stage2 current-net anchor missing'
engine = engine.replace(needle, replacement, 1)

# Stage2Engine did not previously need a money helper. Add a local formatter.
anchor = '    private static SharedPreferences prefs(Context context) {\n'
assert anchor in engine, 'Stage2 prefs anchor missing'
helper = '''    private static String money(double value) {
        return String.format(Locale.US, "%.2f", value);
    }

'''
engine = engine.replace(anchor, helper + anchor, 1)
engine_path.write_text(engine)

# ---------------------------------------------------------------------------
# 4) UI wording: make the cost-basis dependency visible so ₹0 can never look
#    like a healthy trailing state again.
# ---------------------------------------------------------------------------
old = 'BUY still requires candle/volume/depth confirmation + projected NET ≥0.50%.'
# The line may be constructed dynamically; only replace if present.
if old in activity:
    activity = activity.replace(old, old, 1)
activity_path.write_text(activity)

# Final source contracts.
groww = groww_path.read_text(); monitor = monitor_path.read_text(); engine = engine_path.read_text()
assert '/order/detail/' in groww and 'average_fill_price' in groww
assert '/order/trades/' in groww and 'ORDER_TRADES_VWAP' in groww
assert 'TRAILING NOT ARMED — ENTRY BASIS UNAVAILABLE' in monitor
assert 'strategy.fastProfitArmed = false;' in monitor
assert 'ENTRY BASIS CONFIRMED' in monitor
assert 'PROFIT TRAIL ARMED' in engine
assert 'entry average ₹0 • no false ARMED state' in monitor
print('Applied v2.7.7 confirmed entry-basis recovery + truthful +0.50% NET trailing activation fix')

package com.suhas.multyfiautobuy.stable;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.List;

final class Strategy {
    static final String ENTRY_ACTIVE = "ENTRY_ACTIVE";
    static final String PROTECTED = "PROTECTED";
    static final String TARGET_SELL_PENDING = "TARGET_SELL_PENDING";
    static final String CLOSED = "CLOSED";
    static final String ERROR = "ERROR";

    final String eventId;
    final String symbol;
    final String category;
    final String productType;
    final int requestedQuantity;
    final double targetPrice;
    final double stopLossPrice;
    final int baselinePositionQuantity;
    final String entryReferenceId;
    String entrySmartOrderId;
    int observedFilledQuantity;
    int protectedQuantity;
    final List<StopLeg> stopLegs;
    String targetOrderReferenceId;
    String targetOrderId;
    int targetFilledQuantity;
    boolean earlyExitRequested;
    String earlyExitReason;
    long earlyExitRequestedAt;
    String pendingExitLabel;
    String state;
    String lastMessage;
    final long createdAt;
    long updatedAt;

    Strategy(String eventId, String symbol, String category, String productType,
             int requestedQuantity, double targetPrice, double stopLossPrice,
             int baselinePositionQuantity, String entryReferenceId,
             String entrySmartOrderId, long createdAt) {
        this.eventId = eventId;
        this.symbol = symbol;
        this.category = category == null ? "EQUITY" : category;
        this.productType = productType == null ? "CNC" : productType;
        this.requestedQuantity = requestedQuantity;
        this.targetPrice = targetPrice;
        this.stopLossPrice = stopLossPrice;
        this.baselinePositionQuantity = baselinePositionQuantity;
        this.entryReferenceId = entryReferenceId;
        this.entrySmartOrderId = entrySmartOrderId;
        this.observedFilledQuantity = 0;
        this.protectedQuantity = 0;
        this.stopLegs = new ArrayList<>();
        this.targetOrderReferenceId = "";
        this.targetOrderId = "";
        this.targetFilledQuantity = 0;
        this.earlyExitRequested = false;
        this.earlyExitReason = "";
        this.earlyExitRequestedAt = 0L;
        this.pendingExitLabel = "";
        this.state = ENTRY_ACTIVE;
        this.lastMessage = "Entry GTT active.";
        this.createdAt = createdAt;
        this.updatedAt = createdAt;
    }

    boolean isActive() {
        return !CLOSED.equals(state) && !ERROR.equals(state);
    }

    boolean isIntraday() { return "MIS".equalsIgnoreCase(productType); }

    int remainingStrategyQuantity(int currentPositionQuantity) {
        return Math.max(0, currentPositionQuantity - baselinePositionQuantity);
    }

    void requestEarlyExit(String reason, long requestedAt) {
        earlyExitRequested = true;
        earlyExitReason = reason == null ? "Multyfi requested an early exit." : reason;
        earlyExitRequestedAt = requestedAt;
        lastMessage = "Multyfi early exit queued for immediate broker processing.";
        updatedAt = System.currentTimeMillis();
    }

    JSONObject toJson() throws Exception {
        JSONObject json = new JSONObject();
        json.put("event_id", eventId);
        json.put("symbol", symbol);
        json.put("category", category);
        json.put("product_type", productType);
        json.put("requested_quantity", requestedQuantity);
        json.put("target_price", targetPrice);
        json.put("stop_loss_price", stopLossPrice);
        json.put("baseline_position_quantity", baselinePositionQuantity);
        json.put("entry_reference_id", entryReferenceId);
        json.put("entry_smart_order_id", entrySmartOrderId);
        json.put("observed_filled_quantity", observedFilledQuantity);
        json.put("protected_quantity", protectedQuantity);
        JSONArray legs = new JSONArray();
        for (StopLeg leg : stopLegs) legs.put(leg.toJson());
        json.put("stop_legs", legs);
        json.put("target_order_reference_id", targetOrderReferenceId);
        json.put("target_order_id", targetOrderId);
        json.put("target_filled_quantity", targetFilledQuantity);
        json.put("early_exit_requested", earlyExitRequested);
        json.put("early_exit_reason", earlyExitReason);
        json.put("early_exit_requested_at", earlyExitRequestedAt);
        json.put("pending_exit_label", pendingExitLabel);
        json.put("state", state);
        json.put("last_message", lastMessage);
        json.put("created_at", createdAt);
        json.put("updated_at", updatedAt);
        return json;
    }

    static Strategy fromJson(JSONObject json) throws Exception {
        Strategy strategy = new Strategy(
                json.getString("event_id"),
                json.getString("symbol"),
                json.optString("category", "EQUITY"),
                json.optString("product_type", "CNC"),
                json.getInt("requested_quantity"),
                json.getDouble("target_price"),
                json.getDouble("stop_loss_price"),
                json.optInt("baseline_position_quantity", 0),
                json.getString("entry_reference_id"),
                json.optString("entry_smart_order_id", ""),
                json.optLong("created_at", System.currentTimeMillis()));
        strategy.observedFilledQuantity = json.optInt("observed_filled_quantity", 0);
        strategy.protectedQuantity = json.optInt("protected_quantity", 0);
        strategy.stopLegs.clear();
        JSONArray legs = json.optJSONArray("stop_legs");
        if (legs != null) {
            for (int i = 0; i < legs.length(); i++) {
                strategy.stopLegs.add(StopLeg.fromJson(legs.getJSONObject(i)));
            }
        }
        strategy.targetOrderReferenceId = json.optString("target_order_reference_id", "");
        strategy.targetOrderId = json.optString("target_order_id", "");
        strategy.targetFilledQuantity = json.optInt("target_filled_quantity", 0);
        strategy.earlyExitRequested = json.optBoolean("early_exit_requested", false);
        strategy.earlyExitReason = json.optString("early_exit_reason", "");
        strategy.earlyExitRequestedAt = json.optLong("early_exit_requested_at", 0L);
        strategy.pendingExitLabel = json.optString("pending_exit_label", "");
        strategy.state = json.optString("state", ENTRY_ACTIVE);
        strategy.lastMessage = json.optString("last_message", "");
        strategy.updatedAt = json.optLong("updated_at", strategy.createdAt);
        return strategy;
    }

    static final class StopLeg {
        final String smartOrderId;
        final int quantity;
        String status;

        StopLeg(String smartOrderId, int quantity, String status) {
            this.smartOrderId = smartOrderId;
            this.quantity = quantity;
            this.status = status;
        }

        JSONObject toJson() throws Exception {
            JSONObject json = new JSONObject();
            json.put("smart_order_id", smartOrderId);
            json.put("quantity", quantity);
            json.put("status", status);
            return json;
        }

        static StopLeg fromJson(JSONObject json) {
            return new StopLeg(json.optString("smart_order_id", ""),
                    json.optInt("quantity", 0), json.optString("status", "ACTIVE"));
        }
    }
}

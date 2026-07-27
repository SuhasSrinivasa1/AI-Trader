#!/usr/bin/env python3
from pathlib import Path
import re

ROOT = Path("android-stable")
JAVA = ROOT / "app/src/main/java/com/suhas/multyfiautobuy/stable"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def replace_once(path: Path, old: str, new: str) -> None:
    text = read(path)
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"Expected exactly one match in {path}: found {count}\n{old[:160]}")
    write(path, text.replace(old, new, 1))


# Version and visible release identity.
gradle = ROOT / "app/build.gradle"
replace_once(gradle, "versionCode 200", "versionCode 201")
replace_once(gradle, "versionName '2.0.0'", "versionName '2.0.1'")

activity = JAVA / "ProductionActivity.java"
text = read(activity)
text = text.replace("release 2.0.0", "release 2.0.1")
text = text.replace("source-built v2.0.0", "source-built v2.0.1")

armed_pattern = re.compile(
    r"    private void handleArmedChange\(boolean checked\) \{.*?\n    \}\n\n    private void refreshStatus\(\) \{",
    re.S,
)
armed_replacement = '''    private void handleArmedChange(boolean checked) {
        if (suppressSwitch) return;
        if (checked) {
            String issue = readinessIssue();
            AppPrefs.setArmed(this, true);
            AppPrefs.log(this, "ARMED 24×7 — PRODUCTION POLICY",
                    "Persistent armed state enabled. 09:00–09:30 MIS immediate LIMIT"
                            + " • 09:30–15:30 CNC entry GTT"
                            + " • budgets ₹" + money(AppPrefs.window1Budget(this))
                            + "/₹" + money(AppPrefs.window2Budget(this))
                            + "/₹" + money(AppPrefs.window3Budget(this))
                            + (issue == null ? " • all gates ready."
                            : " • entry intake is paused until this gate recovers: " + issue + "."));
            StrategyMonitorService.ensureRunning(this);
            if (issue != null) toast("Armed state saved. New entries wait until: " + issue);
        } else {
            AppPrefs.setArmed(this, false);
            AppPrefs.log(this, "DISARMED BY USER",
                    "New automatic entries disabled; existing strategies remain monitored and protected.");
        }
        refreshStatus();
    }

    private void refreshStatus() {'''
text, count = armed_pattern.subn(armed_replacement, text, count=1)
if count != 1:
    raise RuntimeError("Could not replace ProductionActivity.handleArmedChange")

old_status = '''        systemStatus.setText(ready ? "READY" : "SETUP REQUIRED");
        systemStatus.setTextColor(ready ? GREEN : AMBER);
        statusDetail.setText(ready
                ? "All production gates passed • active strategies " + active
                + " • saved budgets ₹" + money(AppPrefs.window1Budget(this))
                + " / ₹" + money(AppPrefs.window2Budget(this))
                + " / ₹" + money(AppPrefs.window3Budget(this)) + "."
                : issue + " • Auto-Buy remains blocked.");

        if (AppPrefs.isArmed(this) && !ready) {
            AppPrefs.setArmed(this, false);
            AppPrefs.log(this, "AUTO-DISARMED", issue);
        }
        suppressSwitch = true;
        armedSwitch.setChecked(AppPrefs.isArmed(this) && ready);
        suppressSwitch = false;'''
new_status = '''        boolean persistentlyArmed = AppPrefs.isArmed(this);
        systemStatus.setText(ready ? "READY" : (persistentlyArmed ? "ARMED • ENTRY PAUSED" : "SETUP REQUIRED"));
        systemStatus.setTextColor(ready ? GREEN : AMBER);
        statusDetail.setText(ready
                ? "All production gates passed • armed state " + (persistentlyArmed ? "ON" : "OFF")
                + " • active strategies " + active
                + " • saved budgets ₹" + money(AppPrefs.window1Budget(this))
                + " / ₹" + money(AppPrefs.window2Budget(this))
                + " / ₹" + money(AppPrefs.window3Budget(this)) + "."
                : issue + (persistentlyArmed
                ? " • Armed state is retained 24×7; new entries automatically wait for this gate."
                : " • Turn on the switch to retain the armed state while gates recover."));

        suppressSwitch = true;
        armedSwitch.setChecked(persistentlyArmed);
        suppressSwitch = false;'''
if old_status not in text:
    raise RuntimeError("Could not find ProductionActivity refresh-status block")
text = text.replace(old_status, new_status, 1)
write(activity, text)

# Notification intake remains armed, but pauses whenever an existing fill is unprotected.
listener = JAVA / "ProductionNotificationService.java"
text = read(listener)
old_armed_gate = '''            if (!AppPrefs.isArmed(this)) {
                AppPrefs.log(this, "COMPLETE SIGNAL — DISARMED", summary);
                return;
            }
            long age = System.currentTimeMillis() - signal.notificationTimeMillis;'''
new_armed_gate = '''            if (!AppPrefs.isArmed(this)) {
                AppPrefs.log(this, "COMPLETE SIGNAL — DISARMED BY USER", summary);
                return;
            }
            for (Strategy existing : active) {
                if (existing.observedFilledQuantity > existing.protectedQuantity) {
                    AppPrefs.log(this, "ENTRY PAUSED — UNPROTECTED POSITION",
                            summary + "\n" + existing.symbol + " has "
                                    + (existing.observedFilledQuantity - existing.protectedQuantity)
                                    + " filled shares awaiting confirmed stop-loss protection. Armed state remains ON.");
                    return;
                }
            }
            long age = System.currentTimeMillis() - signal.notificationTimeMillis;'''
if old_armed_gate not in text:
    raise RuntimeError("Could not find ProductionNotificationService armed gate")
text = text.replace(old_armed_gate, new_armed_gate, 1)
old_reject = '''    private void rejectAndDisarm(String reason, String summary) {
        AppPrefs.setArmed(this, false);
        AppPrefs.log(this, "REJECTED — AUTO-DISARMED", summary + "\n" + reason);
    }'''
new_reject = '''    private void rejectAndDisarm(String reason, String summary) {
        AppPrefs.log(this, "REJECTED — ARMED, WAITING FOR GATE",
                summary + "\n" + reason
                        + " Armed state remains ON; this notification was not submitted.");
    }'''
if old_reject not in text:
    raise RuntimeError("Could not find ProductionNotificationService rejectAndDisarm")
text = text.replace(old_reject, new_reject, 1)
write(listener, text)

# Stop-loss protection: recover an already-created matching GTT after an idempotency duplicate.
client = JAVA / "GrowwClient.java"
text = read(client)
method_pattern = re.compile(
    r"    static ApiResult createStopLossGtt\(String accessToken, Strategy strategy,.*?\n    \}\n\n    static ApiResult cancelGtt",
    re.S,
)
method_replacement = '''    static ApiResult createStopLossGtt(String accessToken, Strategy strategy,
                                       int quantity, int legNumber) {
        try {
            String reference = reference("SL", strategy.eventId, legNumber);
            JSONObject order = new JSONObject();
            order.put("order_type", "MARKET");
            order.put("price", JSONObject.NULL);
            order.put("transaction_type", "SELL");
            JSONObject body = gttBase(reference, strategy.symbol, quantity,
                    strategy.stopLossPrice, "DOWN", order, strategy.productType);
            HttpResult http = request("POST", API_BASE + "/order-advance/create",
                    accessToken, body);
            if (!http.isSuccess()) {
                ApiResult failure = apiFailure(http);
                if (isDuplicateSmartReference(failure)) {
                    ApiResult recovered = recoverActiveStopLossGtt(
                            accessToken, reference, strategy, quantity);
                    if (recovered.success) return recovered;
                    return ApiResult.failure(failure.errorCode,
                            failure.message + " Existing-order recovery: " + recovered.message,
                            failure.httpCode);
                }
                return failure;
            }
            JSONObject payload = new JSONObject(http.body).optJSONObject("payload");
            String id = payload == null ? "" : payload.optString("smart_order_id", "");
            String responseStatus = payload == null ? "" : payload.optString("status", "");
            if (id.isEmpty()) {
                return ApiResult.failure("STOP_NO_ID",
                        "Groww accepted stop-loss GTT but returned no ID.", http.code);
            }
            if (isLiveSmartStatus(responseStatus)) {
                return ApiResult.success(id, "Stop-loss GTT confirmed " + responseStatus
                        + " for " + quantity + " " + strategy.productType
                        + " shares: " + id + ".", http.code);
            }
            SmartStatus confirmed = confirmGtt(accessToken, id);
            if (confirmed.success && isLiveSmartStatus(confirmed.status)) {
                return ApiResult.success(id, "Stop-loss GTT confirmed " + confirmed.status
                        + " for " + quantity + " " + strategy.productType
                        + " shares: " + id + ".", http.code);
            }
            ApiResult recovered = recoverActiveStopLossGtt(
                    accessToken, reference, strategy, quantity);
            if (recovered.success) return recovered;
            return ApiResult.failure("STOP_NOT_CONFIRMED",
                    "Stop-loss request returned smart-order ID " + id
                            + " but ACTIVE status was not confirmed. The app will recover the same"
                            + " idempotent GTT instead of creating a second sell order. "
                            + recovered.message, http.code);
        } catch (Exception e) {
            return ApiResult.failure("", "Stop-loss GTT error: " + safeMessage(e), 0);
        }
    }

    private static boolean isDuplicateSmartReference(ApiResult failure) {
        if (failure == null) return false;
        if ("GA007".equalsIgnoreCase(failure.errorCode)) return true;
        String message = failure.message == null ? "" : failure.message.toLowerCase(Locale.US);
        return message.contains("duplicate") && message.contains("reference");
    }

    private static ApiResult recoverActiveStopLossGtt(String accessToken, String reference,
                                                       Strategy strategy, int quantity) {
        try {
            String url = API_BASE + "/order-advance/list?segment=CASH"
                    + "&smart_order_type=GTT&status=ACTIVE&page=0&page_size=50";
            HttpResult http = request("GET", url, accessToken, null);
            if (!http.isSuccess()) return apiFailure(http);
            JSONObject root = new JSONObject(http.body);
            JSONObject payload = root.optJSONObject("payload");
            JSONArray orders = payload == null ? null : payload.optJSONArray("orders");
            if (orders == null) orders = root.optJSONArray("orders");
            if (orders == null) {
                return ApiResult.failure("STOP_RECOVERY_NO_LIST",
                        "Groww smart-order list returned no orders array.", http.code);
            }
            String matchId = "";
            int matches = 0;
            for (int i = 0; i < orders.length(); i++) {
                JSONObject item = orders.optJSONObject(i);
                if (item == null) continue;
                String listedReference = item.optString("reference_id", "");
                if (!listedReference.isEmpty() && !reference.equalsIgnoreCase(listedReference)) continue;
                if (!"GTT".equalsIgnoreCase(item.optString("smart_order_type", "GTT"))) continue;
                if (!isLiveSmartStatus(item.optString("status", ""))) continue;
                if (!strategy.symbol.equalsIgnoreCase(item.optString("trading_symbol", ""))) continue;
                if (quantity != item.optInt("quantity", -1)) continue;
                if (!strategy.productType.equalsIgnoreCase(item.optString("product_type", ""))) continue;
                if (!"DOWN".equalsIgnoreCase(item.optString("trigger_direction", ""))) continue;
                double trigger = item.optDouble("trigger_price", Double.NaN);
                if (Double.isNaN(trigger)
                        || Math.abs(trigger - strategy.stopLossPrice) > 0.011d) continue;
                JSONObject listedOrder = item.optJSONObject("order");
                if (listedOrder == null
                        || !"SELL".equalsIgnoreCase(listedOrder.optString("transaction_type", ""))) continue;
                String orderType = listedOrder.optString("order_type", "");
                if (!("MARKET".equalsIgnoreCase(orderType)
                        || "SL_M".equalsIgnoreCase(orderType))) continue;
                String id = item.optString("smart_order_id", "");
                if (id.isEmpty()) continue;
                matchId = id;
                matches++;
            }
            if (matches == 1) {
                return ApiResult.success(matchId,
                        "Recovered the already-active stop-loss GTT after Groww reported a duplicate reference: "
                                + matchId + ".", http.code);
            }
            if (matches > 1) {
                return ApiResult.failure("STOP_RECOVERY_AMBIGUOUS",
                        "Multiple matching active stop-loss GTTs exist for " + strategy.symbol
                                + ". New entries remain paused until Groww Trigger Orders are reviewed.", http.code);
            }
            return ApiResult.failure("STOP_RECOVERY_NOT_FOUND",
                    "No matching ACTIVE stop-loss GTT is visible yet for reference " + reference
                            + "; the monitor will retry recovery without changing the armed state.", http.code);
        } catch (Exception e) {
            return ApiResult.failure("STOP_RECOVERY_ERROR",
                    "Stop-loss recovery error: " + safeMessage(e), 0);
        }
    }

    static ApiResult cancelGtt'''
text, count = method_pattern.subn(method_replacement, text, count=1)
if count != 1:
    raise RuntimeError("Could not replace GrowwClient.createStopLossGtt")
write(client, text)

# Monitor keeps the user-selected armed preference and throttles repeated critical logging.
monitor = JAVA / "StrategyMonitorService.java"
text = read(monitor)
protect_pattern = re.compile(
    r"    private boolean protectNewFill\(String token, Strategy strategy\) \{.*?\n    \}\n\n    private boolean anyStopLegTriggered",
    re.S,
)
protect_replacement = '''    private boolean protectNewFill(String token, Strategy strategy) {
        int delta = strategy.observedFilledQuantity - strategy.protectedQuantity;
        if (delta <= 0) return true;
        if (strategy.lastMessage != null
                && strategy.lastMessage.startsWith("CRITICAL: ")
                && System.currentTimeMillis() - strategy.updatedAt < 15_000L) {
            return false;
        }
        int legNumber = strategy.stopLegs.size() + 1;
        GrowwClient.ApiResult stop = GrowwClient.createStopLossGtt(
                token, strategy, delta, legNumber);
        if (!stop.success) {
            String failure = "CRITICAL: " + delta
                    + " newly filled shares are awaiting confirmed protection. " + stop.message;
            boolean changed = !failure.equals(strategy.lastMessage);
            strategy.lastMessage = failure;
            save(strategy);
            if (changed) {
                AppPrefs.log(this, "STOP-LOSS RETRY PENDING — ARMED RETAINED",
                        strategy.symbol + " • " + strategy.lastMessage
                                + " New entries are paused, but the 24×7 armed preference remains ON.");
            }
            return false;
        }
        strategy.stopLegs.add(new Strategy.StopLeg(stop.id, delta, "ACTIVE"));
        strategy.protectedQuantity += delta;
        strategy.state = Strategy.PROTECTED;
        strategy.lastMessage = "Stop-loss GTT confirmed for "
                + strategy.protectedQuantity + " filled "
                + strategy.productType + " shares.";
        save(strategy);
        AppPrefs.log(this, "STOP-LOSS CONFIRMED ACTIVE",
                strategy.symbol + " • " + stop.message);
        return true;
    }

    private boolean anyStopLegTriggered'''
text, count = protect_pattern.subn(protect_replacement, text, count=1)
if count != 1:
    raise RuntimeError("Could not replace StrategyMonitorService.protectNewFill")
removed = text.count("AppPrefs.setArmed(this, false);")
if removed < 4:
    raise RuntimeError(f"Expected monitor auto-disarm sites, found {removed}")
text = text.replace("AppPrefs.setArmed(this, false);", "// Persistent 24×7 armed preference retained; readiness gates pause new entries.")
text = text.replace("SURFSHARK VPN LOST — AUTO-DISARMED", "SURFSHARK VPN LOST — ARMED, ENTRY PAUSED")
text = text.replace("AUTH LOST — AUTO-DISARMED", "AUTH LOST — ARMED, ENTRY PAUSED")
text = text.replace("DAILY APPROVAL REQUIRED — AUTO-DISARMED", "DAILY APPROVAL REQUIRED — ARMED, ENTRY PAUSED")
text = text.replace("BROKER PREFLIGHT FAILED — AUTO-DISARMED", "BROKER PREFLIGHT FAILED — ARMED, ENTRY PAUSED")
text = text.replace("PUBLIC IP CHANGED — AUTO-DISARMED", "PUBLIC IP CHANGED — ARMED, ENTRY PAUSED")
write(monitor, text)

# Build-time assertions: no critical auto-disarm loop may remain.
assert "versionName '2.0.1'" in read(gradle)
assert "recoverActiveStopLossGtt" in read(client)
assert "ENTRY PAUSED — UNPROTECTED POSITION" in read(listener)
assert "STOP-LOSS RETRY PENDING — ARMED RETAINED" in read(monitor)
assert "STOP-LOSS CREATION FAILED — AUTO-DISARMED" not in read(monitor)
assert "source-built v2.0.1" in read(activity)
print("Applied Multyfi AutoBuy Pro v2.0.1 persistent-arm and stop-loss recovery hotfix")

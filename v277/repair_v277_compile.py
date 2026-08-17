from pathlib import Path

root = Path('android-stable/app/src/main/java/com/suhas/multyfiautobuy/stable')
mon_path = root / 'StrategyMonitorService.java'
eng_path = root / 'Stage2Engine.java'

mon = mon_path.read_text()
old = '''        String orderId = strategy.entryOrderId == null ? "" : strategy.entryOrderId.trim();
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

'''
new = '''        // Normal accepted entries persist the Groww order ID on Strategy.
        // OrderStatus intentionally has no order-id field, so do not invent one
        // from a reference lookup here. If this ID is absent we keep retrying the
        // broker position net_price rather than compiling against a nonexistent field.
        String orderId = strategy.entryOrderId == null ? "" : strategy.entryOrderId.trim();

'''
assert old in mon, 'invalid OrderStatus.id fallback block not found'
mon = mon.replace(old, new, 1)
mon_path.write_text(mon)

eng = eng_path.read_text()
old_fmt = 'return String.format(Locale.US, "%.2f", value);'
if old_fmt in eng:
    eng = eng.replace(old_fmt, 'return String.format(java.util.Locale.US, "%.2f", value);', 1)
eng_path.write_text(eng)

# Compile-safety assertions.
assert 'status.id' not in mon
assert 'String orderId = strategy.entryOrderId' in mon
assert 'java.util.Locale.US' in eng
print('Repaired v2.7.7 compile: removed nonexistent OrderStatus.id fallback and qualified Locale')

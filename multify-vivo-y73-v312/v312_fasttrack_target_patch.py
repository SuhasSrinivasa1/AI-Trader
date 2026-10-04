from pathlib import Path

root = Path("android")

# Version bump.
p = root / "app/build.gradle.kts"
s = p.read_text()
s = s.replace("versionCode = 311", "versionCode = 312")
s = s.replace('versionName = "3.1.1-vivo-y73"', 'versionName = "3.1.2-vivo-y73"')
p.write_text(s)

# Add explicit Fast Track target math helper.
engine_dir = root / "app/src/main/java/com/multify/traderpro/engine"
(engine_dir / "FastTrackMath.kt").write_text(r'''package com.multify.traderpro.engine

import kotlin.math.max

object FastTrackMath {
    const val RETRACEMENT_FRACTION = 0.50

    fun capturedLongMove(longEntry: Double, longExit: Double): Double =
        max(0.0, longExit - longEntry)

    fun postSellShortTarget(shortEntry: Double, longEntry: Double, longExit: Double): Double {
        val targetDistance = capturedLongMove(longEntry, longExit) * RETRACEMENT_FRACTION
        return (shortEntry - targetDistance).coerceAtLeast(0.01)
    }
}
''')

# Replace the old fixed 0.5% Fast Track short target with 50% of the preceding long price gain.
p = root / "app/src/main/java/com/multify/traderpro/data/repository/TradingRepository.kt"
s = p.read_text()

import_needle = "import com.multify.traderpro.engine.BudgetAllocator\n"
if "import com.multify.traderpro.engine.FastTrackMath\n" not in s:
    assert import_needle in s
    s = s.replace(import_needle, import_needle + "import com.multify.traderpro.engine.FastTrackMath\n")

old_block = '''        val shortEntry = closed.exitPrice
        val target = shortEntry * (1.0 - FAST_SHORT_TARGET_PCT)
        val stop = shortEntry * (1.0 + FAST_SHORT_STOP_PCT)
        val longProfit = max(0.0, closed.netPnl)
        if (longProfit <= 0.0) return
        val allocation = BudgetAllocator.allocate(
            settings.fastTrackBudgetRupees.toDouble(), .82, shortEntry,
            stop - shortEntry, shortEntry - target, 0
        )
        if (!allocation.allowed) return
        val ref = stableRef("MFS", "$eventId-$symbol-S")
        val order = placeMarket(token, symbol, "SELL", allocation.quantity, "MIS", ref)
        val qty = order.filledQuantity?.takeIf { it > 0 } ?: allocation.quantity
        val entry = order.averageFillPrice?.takeIf { it > 0 } ?: shortEntry
        managedDao.insertPosition(
            ManagedPositionEntity(
                engine = ENGINE_FAST_SHORT, symbol = symbol, product = "MIS", side = "SHORT", quantity = qty,
                entryPrice = entry, stopPrice = entry * (1.0 + FAST_SHORT_STOP_PCT), targetPrice = entry * (1.0 - FAST_SHORT_TARGET_PCT),
                strategy = "Post-Multify-sell 0.5% overlay", regime = "FAST_TRACK", confidence = .82,
                sourceEventId = eventId, openOrderId = order.growwOrderId, openReferenceId = ref,
                openedAtMs = System.currentTimeMillis(), lastPrice = entry, maxFavourablePrice = entry,
                maxAdversePrice = entry, lastEvaluatedAtMs = System.currentTimeMillis()
            )
        )
'''
new_block = '''        val shortEntry = closed.exitPrice
        val longMove = FastTrackMath.capturedLongMove(holding.entryPrice, closed.exitPrice)
        if (longMove <= 0.0) {
            auditLogger.log(
                "FAST_TRACK", "POST_SELL_SHORT_SKIPPED",
                mapOf("symbol" to symbol, "reason" to "preceding_long_had_no_positive_price_gain",
                    "long_entry" to holding.entryPrice, "long_exit" to closed.exitPrice)
            )
            return
        }
        val target = FastTrackMath.postSellShortTarget(shortEntry, holding.entryPrice, closed.exitPrice)
        val stop = shortEntry * (1.0 + FAST_SHORT_STOP_PCT)
        auditLogger.log(
            "FAST_TRACK", "POST_SELL_SHORT_PLAN",
            mapOf(
                "symbol" to symbol,
                "long_entry" to holding.entryPrice,
                "long_exit" to closed.exitPrice,
                "long_price_gain_per_share" to longMove,
                "target_capture_fraction" to FastTrackMath.RETRACEMENT_FRACTION,
                "planned_short_entry" to shortEntry,
                "planned_short_target" to target,
                "planned_target_distance" to (shortEntry - target)
            )
        )
        val allocation = BudgetAllocator.allocate(
            settings.fastTrackBudgetRupees.toDouble(), .82, shortEntry,
            stop - shortEntry, shortEntry - target, 0
        )
        if (!allocation.allowed) return
        val ref = stableRef("MFS", "$eventId-$symbol-S")
        val order = placeMarket(token, symbol, "SELL", allocation.quantity, "MIS", ref)
        val qty = order.filledQuantity?.takeIf { it > 0 } ?: allocation.quantity
        val entry = order.averageFillPrice?.takeIf { it > 0 } ?: shortEntry
        val actualTarget = FastTrackMath.postSellShortTarget(entry, holding.entryPrice, closed.exitPrice)
        managedDao.insertPosition(
            ManagedPositionEntity(
                engine = ENGINE_FAST_SHORT, symbol = symbol, product = "MIS", side = "SHORT", quantity = qty,
                entryPrice = entry, stopPrice = entry * (1.0 + FAST_SHORT_STOP_PCT), targetPrice = actualTarget,
                strategy = "Post-Multify-sell 50% long-gain retracement", regime = "FAST_TRACK", confidence = .82,
                sourceEventId = eventId, openOrderId = order.growwOrderId, openReferenceId = ref,
                openedAtMs = System.currentTimeMillis(), lastPrice = entry, maxFavourablePrice = entry,
                maxAdversePrice = entry, lastEvaluatedAtMs = System.currentTimeMillis()
            )
        )
'''
assert old_block in s
s = s.replace(old_block, new_block)

s = s.replace("        private const val FAST_SHORT_TARGET_PCT = 0.005\n", "")

p.write_text(s)

# Update Manual/Fast Track UI text so the rule is unambiguous.
p = root / "app/src/main/java/com/multify/traderpro/ui/screens/TraderApp.kt"
s = p.read_text()
old = 'Text("After the Multify Book Profit sell is filled, an optional protected intraday short targets 0.5% with a 0.35% protective stop. It is always closed intraday.", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)'
new = 'Text("After the Multify Book Profit sell is filled, an optional protected intraday short targets 50% of the preceding long price gain. Example: ₹100 → ₹110 long move means short near ₹110 with an initial cover target near ₹105. A 0.35% protective stop remains, and the short is always closed intraday.", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)'
assert old in s
s = s.replace(old, new)
old2 = 'Text("3. If the short overlay is enabled and the market window is safe → open a separate MIS short with broker-side OCO protection.", style = MaterialTheme.typography.bodyMedium)'
new2 = 'Text("3. If the short overlay is enabled and the market window is safe → open a separate MIS short. Its cover target is 50% of the preceding long price gain, calculated from actual app fill prices, with broker-side OCO protection.", style = MaterialTheme.typography.bodyMedium)'
assert old2 in s
s = s.replace(old2, new2)
p.write_text(s)

# Unit tests for the clarified rule.
test = root / "app/src/test/java/com/multify/traderpro/engine/FastTrackMathTest.kt"
test.parent.mkdir(parents=True, exist_ok=True)
test.write_text(r'''package com.multify.traderpro.engine

import org.junit.Assert.assertEquals
import org.junit.Test

class FastTrackMathTest {
    @Test
    fun hundredToHundredTenTargetsHundredFive() {
        assertEquals(105.0, FastTrackMath.postSellShortTarget(110.0, 100.0, 110.0), 0.0001)
    }

    @Test
    fun targetUsesActualShortFillButSameHalfLongMove() {
        assertEquals(104.8, FastTrackMath.postSellShortTarget(109.8, 100.0, 110.0), 0.0001)
    }

    @Test
    fun noPositiveLongMoveCreatesNoTargetDistance() {
        assertEquals(99.0, FastTrackMath.postSellShortTarget(99.0, 100.0, 99.0), 0.0001)
    }
}
''')

print("Applied Vivo Y73 v3.1.2 Fast Track 50%-of-long-gain short-target update.")

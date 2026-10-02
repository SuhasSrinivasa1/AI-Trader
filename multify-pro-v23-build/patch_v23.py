from pathlib import Path
root = Path('/mnt/data/v23work/android')

# Version 2.3
p=root/'app/build.gradle.kts'; s=p.read_text(); s=s.replace('versionCode = 220','versionCode = 230').replace('versionName = "2.2.0"','versionName = "2.3.0"'); p.write_text(s)

# New Room entities and DAO
local=root/'app/src/main/java/com/multify/traderpro/data/local'
(local/'ShadowPositionEntity.kt').write_text(r'''package com.multify.traderpro.data.local

import androidx.room.Entity
import androidx.room.Index
import androidx.room.PrimaryKey

@Entity(
    tableName = "shadow_positions",
    indices = [Index(value = ["symbol", "status"]), Index(value = ["openedAtMs"])]
)
data class ShadowPositionEntity(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val symbol: String,
    val side: String,
    val quantity: Int,
    val entryPrice: Double,
    val stopPrice: Double,
    val targetPrice: Double,
    val strategy: String,
    val regime: String,
    val confidence: Double,
    val sourceEventId: Long?,
    val openedAtMs: Long,
    val lastPrice: Double,
    val maxFavourablePrice: Double,
    val maxAdversePrice: Double,
    val lastEvaluatedAtMs: Long,
    val status: String = "OPEN"
)
''')
(local/'ShadowTradeEntity.kt').write_text(r'''package com.multify.traderpro.data.local

import androidx.room.Entity
import androidx.room.Index
import androidx.room.PrimaryKey

@Entity(
    tableName = "shadow_trades",
    indices = [Index(value = ["symbol", "closedAtMs"]), Index(value = ["closedAtMs"])]
)
data class ShadowTradeEntity(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val symbol: String,
    val side: String,
    val quantity: Int,
    val entryPrice: Double,
    val exitPrice: Double,
    val grossPnl: Double,
    val estimatedCosts: Double,
    val netPnl: Double,
    val exitReason: String,
    val strategy: String,
    val regime: String,
    val confidence: Double,
    val mfeRupees: Double,
    val maeRupees: Double,
    val sourceEventId: Long?,
    val openedAtMs: Long,
    val closedAtMs: Long
)
''')
(local/'ShadowDao.kt').write_text(r'''package com.multify.traderpro.data.local

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import androidx.room.Update

@Dao
interface ShadowDao {
    @Insert(onConflict = OnConflictStrategy.ABORT)
    suspend fun insertPosition(position: ShadowPositionEntity): Long

    @Update
    suspend fun updatePosition(position: ShadowPositionEntity)

    @Query("SELECT * FROM shadow_positions WHERE status='OPEN' ORDER BY openedAtMs ASC")
    suspend fun openPositions(): List<ShadowPositionEntity>

    @Query("SELECT * FROM shadow_positions WHERE status='OPEN' AND symbol=:symbol LIMIT 1")
    suspend fun openPosition(symbol: String): ShadowPositionEntity?

    @Query("DELETE FROM shadow_positions WHERE id=:id")
    suspend fun deletePosition(id: Long)

    @Insert(onConflict = OnConflictStrategy.ABORT)
    suspend fun insertTrade(trade: ShadowTradeEntity): Long

    @Query("SELECT * FROM shadow_trades WHERE closedAtMs >= :sinceMs ORDER BY closedAtMs DESC")
    suspend fun tradesSince(sinceMs: Long): List<ShadowTradeEntity>

    @Query("SELECT COUNT(*) FROM shadow_trades WHERE symbol=:symbol AND closedAtMs >= :sinceMs")
    suspend fun tradeCountSince(symbol: String, sinceMs: Long): Int
}
''')

# Database and migration
p=local/'AppDatabase.kt'; p.write_text(r'''package com.multify.traderpro.data.local

import androidx.room.Database
import androidx.room.RoomDatabase
import androidx.room.migration.Migration
import androidx.sqlite.db.SupportSQLiteDatabase

@Database(
    entities = [SignalEventEntity::class, ShadowPositionEntity::class, ShadowTradeEntity::class],
    version = 2,
    exportSchema = false
)
abstract class AppDatabase : RoomDatabase() {
    abstract fun signalEventDao(): SignalEventDao
    abstract fun shadowDao(): ShadowDao

    companion object {
        val MIGRATION_1_2 = object : Migration(1, 2) {
            override fun migrate(db: SupportSQLiteDatabase) {
                db.execSQL("""CREATE TABLE IF NOT EXISTS shadow_positions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    entryPrice REAL NOT NULL,
                    stopPrice REAL NOT NULL,
                    targetPrice REAL NOT NULL,
                    strategy TEXT NOT NULL,
                    regime TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    sourceEventId INTEGER,
                    openedAtMs INTEGER NOT NULL,
                    lastPrice REAL NOT NULL,
                    maxFavourablePrice REAL NOT NULL,
                    maxAdversePrice REAL NOT NULL,
                    lastEvaluatedAtMs INTEGER NOT NULL,
                    status TEXT NOT NULL
                )""")
                db.execSQL("CREATE INDEX IF NOT EXISTS index_shadow_positions_symbol_status ON shadow_positions(symbol, status)")
                db.execSQL("CREATE INDEX IF NOT EXISTS index_shadow_positions_openedAtMs ON shadow_positions(openedAtMs)")
                db.execSQL("""CREATE TABLE IF NOT EXISTS shadow_trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    entryPrice REAL NOT NULL,
                    exitPrice REAL NOT NULL,
                    grossPnl REAL NOT NULL,
                    estimatedCosts REAL NOT NULL,
                    netPnl REAL NOT NULL,
                    exitReason TEXT NOT NULL,
                    strategy TEXT NOT NULL,
                    regime TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    mfeRupees REAL NOT NULL,
                    maeRupees REAL NOT NULL,
                    sourceEventId INTEGER,
                    openedAtMs INTEGER NOT NULL,
                    closedAtMs INTEGER NOT NULL
                )""")
                db.execSQL("CREATE INDEX IF NOT EXISTS index_shadow_trades_symbol_closedAtMs ON shadow_trades(symbol, closedAtMs)")
                db.execSQL("CREATE INDEX IF NOT EXISTS index_shadow_trades_closedAtMs ON shadow_trades(closedAtMs)")
            }
        }
    }
}
''')

p=root/'app/src/main/java/com/multify/traderpro/di/AppModule.kt'; s=p.read_text();
s=s.replace('import com.multify.traderpro.data.local.SignalEventDao\n','import com.multify.traderpro.data.local.SignalEventDao\nimport com.multify.traderpro.data.local.ShadowDao\n')
s=s.replace('.fallbackToDestructiveMigration()\n            .build()', '.addMigrations(AppDatabase.MIGRATION_1_2)\n            .fallbackToDestructiveMigration()\n            .build()')
s=s.replace('    fun provideSignalEventDao(db: AppDatabase): SignalEventDao = db.signalEventDao()\n','    fun provideSignalEventDao(db: AppDatabase): SignalEventDao = db.signalEventDao()\n\n    @Provides\n    fun provideShadowDao(db: AppDatabase): ShadowDao = db.shadowDao()\n')
p.write_text(s)

# Adaptive interval support in local strategy engine.
p=root/'app/src/main/java/com/multify/traderpro/engine/LocalStrategyEngine.kt'; s=p.read_text()
s=s.replace('fun buildFeatures(quote: QuotePayload, historical: HistoricalPayload): FeatureSnapshot {','fun buildFeatures(quote: QuotePayload, historical: HistoricalPayload, intervalMinutes: Int = historical.intervalInMinutes ?: 5): FeatureSnapshot {')
s=s.replace('val (o5h, o5l) = openingRange(candles, 5)\n        val (o15h, o15l) = openingRange(candles, 15)', 'val (o5h, o5l) = openingRange(candles, 5, intervalMinutes)\n        val (o15h, o15l) = openingRange(candles, 15, intervalMinutes)')
s=s.replace('private fun openingRange(c: List<Candle>, minutes: Int): Pair<Double?, Double?> {\n        if (c.isEmpty()) return null to null\n        val count = max(1, minutes / 5)', 'private fun openingRange(c: List<Candle>, minutes: Int, intervalMinutes: Int): Pair<Double?, Double?> {\n        if (c.isEmpty()) return null to null\n        val count = max(1, kotlin.math.ceil(minutes.toDouble() / max(1, intervalMinutes)).toInt())')
p.write_text(s)

# Repository shadow engine + auto-auth + paper dashboard.
p=root/'app/src/main/java/com/multify/traderpro/data/repository/TradingRepository.kt'; s=p.read_text()
s=s.replace('import com.multify.traderpro.data.local.SignalEventEntity\n', 'import com.multify.traderpro.data.local.SignalEventEntity\nimport com.multify.traderpro.data.local.ShadowDao\nimport com.multify.traderpro.data.local.ShadowPositionEntity\nimport com.multify.traderpro.data.local.ShadowTradeEntity\n')
s=s.replace('    private val dao: SignalEventDao,\n    private val preferences: AppPreferences,', '    private val dao: SignalEventDao,\n    private val shadowDao: ShadowDao,\n    private val preferences: AppPreferences,')

# Replace dashboard internals with paper-aware summaries while preserving live broker positions.
old='''            val positions = positionsPayload.positions.filter { it.product.equals("MIS", true) || it.quantity != 0 }
            val mapped = positions.filter { it.quantity != 0 }.map { mapPosition(token, it) }
            val realised = positions.sumOf { it.realisedPnl }
            val unrealised = mapped.sumOf { it.pnl }
            val gross = mapped.sumOf { abs(it.quantity) * (it.ltp ?: it.averagePrice) }
            val recent = dao.recentNow(8).mapNotNull { e ->
                e.backendAction?.let {
                    RecentDecisionDto(
                        at = formatEventTime(e.receivedAtMs), symbol = e.symbol, action = it,
                        reason = e.backendReason.orEmpty(), strategy = null, quantity = 0
                    )
                }
            }
'''
new='''            val positions = positionsPayload.positions.filter { it.product.equals("MIS", true) || it.quantity != 0 }
            val brokerMapped = positions.filter { it.quantity != 0 }.map { mapPosition(token, it) }
            val brokerRealised = positions.sumOf { it.realisedPnl }
            val brokerUnrealised = brokerMapped.sumOf { it.pnl }
            val brokerGross = brokerMapped.sumOf { abs(it.quantity) * (it.ltp ?: it.averagePrice) }
            val paper = paperSnapshot(settings)
            val mapped = if (settings.liveExecutionEffective) brokerMapped else paper.positions
            val realised = if (settings.liveExecutionEffective) brokerRealised else paper.realised
            val unrealised = if (settings.liveExecutionEffective) brokerUnrealised else paper.unrealised
            val gross = if (settings.liveExecutionEffective) brokerGross else paper.grossExposure
            val eventRecent = dao.recentNow(8).mapNotNull { e ->
                e.backendAction?.let {
                    RecentDecisionDto(
                        at = formatEventTime(e.receivedAtMs), symbol = e.symbol, action = it,
                        reason = e.backendReason.orEmpty(), strategy = null, quantity = 0
                    )
                }
            }
            val tradeRecent = if (settings.liveExecutionEffective) emptyList() else paper.recentTrades
            val recent = (tradeRecent + eventRecent).sortedByDescending { it.at }.take(10)
'''
assert old in s
s=s.replace(old,new)
s=s.replace('                    trades = recent.count { it.action.contains("LIVE_", true) },\n                    wins = 0, losses = 0, grossExposure = gross', '                    trades = if (settings.liveExecutionEffective) recent.count { it.action.contains("LIVE_", true) } else paper.tradeCount,\n                    wins = if (settings.liveExecutionEffective) 0 else paper.wins, losses = if (settings.liveExecutionEffective) 0 else paper.losses, grossExposure = gross')

# Auto-auth when signal arrives.
old='''        val settings = preferences.settings.first()
        val token = secretStore.getAccessToken()
        if (!settings.brokerAuthenticated || token.isNullOrBlank()) {
            dao.updateForwarding(eventId, "CAPTURED", "AUTH_REQUIRED", "Signal stored. Use Refresh & Authenticate to enable market analysis.", null)
            return
        }
'''
new='''        var settings = preferences.settings.first()
        var token = secretStore.getAccessToken()
        if (!settings.brokerAuthenticated || token.isNullOrBlank()) {
            if (hasBrokerCredentials()) {
                val autoAuth = runCatching { authenticate() }
                if (autoAuth.isSuccess) {
                    settings = preferences.settings.first()
                    token = secretStore.getAccessToken()
                } else {
                    dao.updateForwarding(eventId, "CAPTURED", "AUTO_AUTH_FAILED", "Signal stored. Automatic Groww TOTP refresh failed: ${autoAuth.exceptionOrNull()?.message.orEmpty()}", null)
                    return
                }
            } else {
                dao.updateForwarding(eventId, "CAPTURED", "AUTH_REQUIRED", "Signal stored. Save Groww TOTP credentials to enable market analysis.", null)
                return
            }
        }
        val accessToken = token ?: return
'''
assert old in s
s=s.replace(old,new)
s=s.replace('handleBuyRelease(eventId, parsed, token, settings)', 'handleBuyRelease(eventId, parsed, accessToken, settings)')
s=s.replace('handleBookProfit(eventId, parsed, token, settings)', 'handleBookProfit(eventId, parsed, accessToken, settings)')

# Paper buy creates virtual position.
old='''        if (!settings.liveExecutionEffective) {
            dao.updateForwarding(eventId, "ANALYZED", "PAPER_BUY", "$reason · live execution is OFF", null)
            return
        }
'''
new='''        if (!settings.liveExecutionEffective) {
            val existingShadow = shadowDao.openPosition(symbol)
            if (existingShadow != null && existingShadow.side == "SHORT") {
                closeShadow(existingShadow, f.ltp, "MULTIFY_LONG_REVERSAL")
            }
            if (shadowDao.openPosition(symbol) == null) {
                openShadow(symbol, "LONG", allocation.quantity, f.ltp, stop, target, analysis, eventId)
                dao.updateForwarding(eventId, "ANALYZED", "PAPER_BUY_OPEN", "$reason · virtual ${allocation.quantity} shares @ ₹${fmt(f.ltp)} · SL ₹${fmt(stop)} · target ₹${fmt(target)}", null)
            } else {
                dao.updateForwarding(eventId, "ANALYZED", "PAPER_HOLD_LONG", "Existing virtual long remains open · $reason", null)
            }
            return
        }
'''
# only replace first occurrence (buy block)
idx=s.find(old); assert idx>=0; s=s[:idx]+new+s[idx+len(old):]

# Book profit paper mode: close paper long before short, then create short.
anchor='''        var existing = currentPosition(token, symbol)
        if (settings.liveExecutionEffective && existing.quantity > 0) {
'''
replacement='''        var existing = currentPosition(token, symbol)
        if (!settings.liveExecutionEffective) {
            shadowDao.openPosition(symbol)?.takeIf { it.side == "LONG" }?.let { paperLong ->
                val quote = apiFactory.groww.quote(bearer(token), tradingSymbol = symbol).requirePayload("Quote $symbol")
                closeShadow(paperLong, quote.lastPrice ?: paperLong.lastPrice, "MULTIFY_BOOK_PROFIT")
            }
        }
        if (settings.liveExecutionEffective && existing.quantity > 0) {
'''
assert anchor in s; s=s.replace(anchor,replacement,1)
# replace next paper short block
old2='''        if (!settings.liveExecutionEffective) {
            dao.updateForwarding(eventId, "ANALYZED", "PAPER_SHORT", "$reason · live execution is OFF", null)
            return
        }
'''
new2='''        if (!settings.liveExecutionEffective) {
            val existingShadow = shadowDao.openPosition(symbol)
            if (existingShadow != null && existingShadow.side == "LONG") closeShadow(existingShadow, f.ltp, "SHORT_REVERSAL")
            if (shadowDao.openPosition(symbol) == null && paperRiskAllowsNewTrade(settings, symbol)) {
                openShadow(symbol, "SHORT", allocation.quantity, f.ltp, stop, target, analysis, eventId)
                dao.updateForwarding(eventId, "ANALYZED", "PAPER_SHORT_OPEN", "$reason · virtual ${allocation.quantity} shares short @ ₹${fmt(f.ltp)} · SL ₹${fmt(stop)} · target ₹${fmt(target)}", null)
            } else {
                dao.updateForwarding(eventId, "ANALYZED", "PAPER_WAIT_SHORT", "Paper risk/trade-frequency gate blocked a new short · $reason", null)
            }
            return
        }
'''
assert old2 in s; s=s.replace(old2,new2,1)

# Adaptive 1m/5m analyzer.
old='''        val historical = apiFactory.groww.historicalCandles(
            authorization = auth,
            growwSymbol = "NSE-$symbol",
            startTime = start,
            endTime = end,
            candleInterval = "5minute"
        ).requirePayload("Historical candles $symbol")
        require(historical.candles.size >= 5) { "Not enough intraday candles for a validated decision" }
        val features = LocalStrategyEngine.buildFeatures(quote, historical)
'''
new='''        var intervalMinutes = 5
        var historical = apiFactory.groww.historicalCandles(
            authorization = auth,
            growwSymbol = "NSE-$symbol",
            startTime = start,
            endTime = end,
            candleInterval = "5minute"
        ).requirePayload("Historical candles $symbol")
        if (now.toLocalTime().isBefore(LocalTime.of(9, 40)) || historical.candles.size < 5) {
            intervalMinutes = 1
            historical = apiFactory.groww.historicalCandles(
                authorization = auth,
                growwSymbol = "NSE-$symbol",
                startTime = start,
                endTime = end,
                candleInterval = "1minute"
            ).requirePayload("1-minute historical candles $symbol")
        }
        require(historical.candles.size >= 3) { "Not enough intraday candles yet; signal retained for the shadow monitor" }
        val features = LocalStrategyEngine.buildFeatures(quote, historical, intervalMinutes)
'''
assert old in s; s=s.replace(old,new)

# Insert shadow engine helper functions before placeMarket.
marker='''    private suspend fun placeMarket(token: String, symbol: String, transaction: String, qty: Int, reference: String = referenceId("MF")): com.multify.traderpro.data.network.OrderPayload {
'''
helpers=r'''    suspend fun monitorShadowPositions(): Int {
        val settings = preferences.settings.first()
        if (settings.liveExecutionEffective) return 0
        val open = shadowDao.openPositions()
        if (open.isEmpty()) return 0
        var token = secretStore.getAccessToken()
        if (!settings.brokerAuthenticated || token.isNullOrBlank()) {
            if (!hasBrokerCredentials()) return open.size
            token = runCatching { authenticate(); secretStore.getAccessToken() }.getOrNull()
        }
        val authToken = token ?: return open.size
        val now = ZonedDateTime.now(INDIA)
        for (position in open) {
            runCatching { monitorOneShadow(position, authToken, settings, now) }
                .recoverCatching { t ->
                    if (t.message?.contains("401") == true || t.message?.contains("author", true) == true) {
                        authenticate()
                        val refreshed = secretStore.getAccessToken() ?: throw t
                        monitorOneShadow(position, refreshed, preferences.settings.first(), ZonedDateTime.now(INDIA))
                    } else throw t
                }
        }
        return shadowDao.openPositions().size
    }

    private suspend fun monitorOneShadow(position: ShadowPositionEntity, token: String, settings: AppSettings, now: ZonedDateTime) {
        val quote = apiFactory.groww.quote(bearer(token), tradingSymbol = position.symbol).requirePayload("Quote ${position.symbol}")
        val ltp = quote.lastPrice ?: return
        val favourable = if (position.side == "LONG") max(position.maxFavourablePrice, ltp) else minOf(position.maxFavourablePrice, ltp)
        val adverse = if (position.side == "LONG") minOf(position.maxAdversePrice, ltp) else max(position.maxAdversePrice, ltp)
        val updated = position.copy(lastPrice = ltp, maxFavourablePrice = favourable, maxAdversePrice = adverse, lastEvaluatedAtMs = System.currentTimeMillis())
        shadowDao.updatePosition(updated)

        val forceFlat = now.dayOfWeek.value >= 6 || !now.toLocalTime().isBefore(LocalTime.of(15, 20))
        val stopHit = if (position.side == "LONG") ltp <= position.stopPrice else ltp >= position.stopPrice
        val targetHit = if (position.side == "LONG") ltp >= position.targetPrice else ltp <= position.targetPrice
        when {
            forceFlat -> { closeShadow(updated, ltp, "FORCE_FLAT_15_20"); return }
            stopHit -> { closeShadow(updated, ltp, "STOP_LOSS"); return }
            targetHit -> { closeShadow(updated, ltp, "TARGET"); return }
        }
        if (System.currentTimeMillis() - position.openedAtMs < 90_000L) return
        if (!paperRiskAllowsNewTrade(settings, position.symbol, countCurrent = false)) return

        val synthetic = ParsedSignal(SignalType.TRADE_RELEASE, symbol = position.symbol, rawText = "shadow-monitor", confidence = 1.0)
        val opposite = analyze(position.symbol, token, longSide = position.side == "SHORT", signal = synthetic)
        if (opposite.confidence < PAPER_REVERSAL_CONFIDENCE || opposite.directionalScore < .12) return

        closeShadow(updated, ltp, "STRATEGY_REVERSAL")
        if (!paperRiskAllowsNewTrade(settings, position.symbol)) return
        val atr = opposite.features.atr14 ?: max(ltp * .004, .05)
        val side = if (position.side == "LONG") "SHORT" else "LONG"
        val stop = if (side == "LONG") ltp - atr * .95 else ltp + atr * .95
        val target = if (side == "LONG") ltp + atr * 1.55 else max(.05, ltp - atr * 1.55)
        val allocation = BudgetAllocator.allocate(
            settings.dailyBudgetRupees.toDouble(), opposite.confidence, ltp,
            abs(ltp - stop), abs(target - ltp), 0
        )
        if (allocation.allowed) openShadow(position.symbol, side, allocation.quantity, ltp, stop, target, opposite, position.sourceEventId)
    }

    private suspend fun openShadow(
        symbol: String,
        side: String,
        quantity: Int,
        entry: Double,
        stop: Double,
        target: Double,
        analysis: StrategyEvaluation,
        sourceEventId: Long?
    ) {
        if (quantity <= 0 || shadowDao.openPosition(symbol) != null) return
        val now = System.currentTimeMillis()
        shadowDao.insertPosition(
            ShadowPositionEntity(
                symbol = symbol, side = side, quantity = quantity, entryPrice = entry,
                stopPrice = stop, targetPrice = target, strategy = analysis.strategy,
                regime = analysis.regime, confidence = analysis.confidence, sourceEventId = sourceEventId,
                openedAtMs = now, lastPrice = entry, maxFavourablePrice = entry,
                maxAdversePrice = entry, lastEvaluatedAtMs = now
            )
        )
    }

    private suspend fun closeShadow(position: ShadowPositionEntity, exit: Double, reason: String) {
        val gross = if (position.side == "LONG") (exit - position.entryPrice) * position.quantity
                    else (position.entryPrice - exit) * position.quantity
        val entryNotional = position.entryPrice * position.quantity
        val exitNotional = exit * position.quantity
        val brokerage = minOf(20.0, max(1.0, entryNotional * .001)) + minOf(20.0, max(1.0, exitNotional * .001))
        val costs = brokerage + (entryNotional + exitNotional) * .00045
        val net = gross - costs
        val mfe = if (position.side == "LONG") (position.maxFavourablePrice - position.entryPrice) * position.quantity
                  else (position.entryPrice - position.maxFavourablePrice) * position.quantity
        val mae = if (position.side == "LONG") (position.maxAdversePrice - position.entryPrice) * position.quantity
                  else (position.entryPrice - position.maxAdversePrice) * position.quantity
        shadowDao.insertTrade(
            ShadowTradeEntity(
                symbol = position.symbol, side = position.side, quantity = position.quantity,
                entryPrice = position.entryPrice, exitPrice = exit, grossPnl = gross,
                estimatedCosts = costs, netPnl = net, exitReason = reason,
                strategy = position.strategy, regime = position.regime, confidence = position.confidence,
                mfeRupees = mfe, maeRupees = mae, sourceEventId = position.sourceEventId,
                openedAtMs = position.openedAtMs, closedAtMs = System.currentTimeMillis()
            )
        )
        shadowDao.deletePosition(position.id)
    }

    private suspend fun paperRiskAllowsNewTrade(settings: AppSettings, symbol: String, countCurrent: Boolean = true): Boolean {
        val since = startOfIndiaDayMs()
        val trades = shadowDao.tradesSince(since)
        val realised = trades.sumOf { it.netPnl }
        if (realised >= DAILY_PROFIT_LOCK || realised <= -dailyLossCap(settings)) return false
        val count = shadowDao.tradeCountSince(symbol, since) + if (countCurrent && shadowDao.openPosition(symbol) != null) 1 else 0
        return count < MAX_PAPER_TRADES_PER_SYMBOL
    }

    private data class PaperSnapshot(
        val realised: Double,
        val unrealised: Double,
        val grossExposure: Double,
        val tradeCount: Int,
        val wins: Int,
        val losses: Int,
        val positions: List<PositionDto>,
        val recentTrades: List<RecentDecisionDto>
    )

    private suspend fun paperSnapshot(settings: AppSettings): PaperSnapshot {
        val open = shadowDao.openPositions()
        val trades = shadowDao.tradesSince(startOfIndiaDayMs())
        val positions = open.map { p ->
            val pnl = if (p.side == "LONG") (p.lastPrice - p.entryPrice) * p.quantity else (p.entryPrice - p.lastPrice) * p.quantity
            PositionDto(
                symbol = p.symbol, side = p.side, quantity = p.quantity, averagePrice = p.entryPrice,
                ltp = p.lastPrice, pnl = pnl, stopPrice = p.stopPrice, targetPrice = p.targetPrice,
                strategy = "PAPER · ${p.strategy} · ${(p.confidence * 100).toInt()}%"
            )
        }
        val recent = trades.take(6).map { t ->
            RecentDecisionDto(
                at = formatEventTime(t.closedAtMs), symbol = t.symbol,
                action = "PAPER_${t.side}_CLOSED",
                reason = "${t.exitReason} · net ₹${fmt(t.netPnl)} · costs ₹${fmt(t.estimatedCosts)}",
                strategy = t.strategy, quantity = t.quantity
            )
        }
        return PaperSnapshot(
            realised = trades.sumOf { it.netPnl },
            unrealised = positions.sumOf { it.pnl },
            grossExposure = positions.sumOf { it.quantity * (it.ltp ?: it.averagePrice) },
            tradeCount = trades.size,
            wins = trades.count { it.netPnl > 0 }, losses = trades.count { it.netPnl < 0 },
            positions = positions, recentTrades = recent
        )
    }

    private fun startOfIndiaDayMs(): Long = LocalDate.now(INDIA).atStartOfDay(INDIA).toInstant().toEpochMilli()

'''
assert marker in s; s=s.replace(marker,helpers+marker)

# disconnected dashboard should still show paper data would require suspend; leave as-is for no-network scenario.
s=s.replace('private const val DAILY_PROFIT_LOCK = 5_000.0', 'private const val DAILY_PROFIT_LOCK = 5_000.0\n        private const val PAPER_REVERSAL_CONFIDENCE = 0.76\n        private const val MAX_PAPER_TRADES_PER_SYMBOL = 8')
p.write_text(s)

# Listener gets continuous shadow monitor coroutine every 30 sec.
p=root/'app/src/main/java/com/multify/traderpro/service/MultifyNotificationListenerService.kt'; s=p.read_text()
s=s.replace('import kotlinx.coroutines.cancel\nimport kotlinx.coroutines.launch', 'import kotlinx.coroutines.cancel\nimport kotlinx.coroutines.delay\nimport kotlinx.coroutines.isActive\nimport kotlinx.coroutines.Job\nimport kotlinx.coroutines.launch')
s=s.replace('    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)\n', '    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)\n    private var shadowMonitorJob: Job? = null\n')
s=s.replace('''    override fun onListenerConnected() {
        super.onListenerConnected()
        notifyStatus("Signal capture active", "Listening for Multify equity intraday notifications · direct Groww mode")
    }
''','''    override fun onListenerConnected() {
        super.onListenerConnected()
        notifyStatus("Signal capture active", "Listening for Multify equity intraday notifications · continuous paper monitor ready")
        if (shadowMonitorJob?.isActive != true) {
            shadowMonitorJob = scope.launch {
                while (isActive) {
                    runCatching { repository.monitorShadowPositions() }
                    delay(30_000L)
                }
            }
        }
    }
''')
p.write_text(s)

# ViewModel refresh dashboard every 15 sec while authenticated.
p=root/'app/src/main/java/com/multify/traderpro/ui/screens/TraderViewModel.kt'; s=p.read_text()
s=s.replace('import kotlinx.coroutines.launch\n', 'import kotlinx.coroutines.launch\nimport kotlinx.coroutines.delay\nimport kotlinx.coroutines.isActive\n')
old='''    init {
        viewModelScope.launch {
            repository.settings.collect { settings ->
                if (settings.brokerAuthenticated) refresh(silent = true)
            }
        }
    }
'''
new='''    init {
        viewModelScope.launch {
            repository.settings.collect { settings ->
                if (settings.brokerAuthenticated) refresh(silent = true)
            }
        }
        viewModelScope.launch {
            while (isActive) {
                delay(15_000L)
                if (repository.settings.stateIn(viewModelScope, SharingStarted.Eagerly, AppSettings()).value.brokerAuthenticated) {
                    refresh(silent = true)
                }
            }
        }
    }
'''
# The stateIn in loop is ugly and creates flow each iteration; use first() instead.
new=new.replace('if (repository.settings.stateIn(viewModelScope, SharingStarted.Eagerly, AppSettings()).value.brokerAuthenticated) {','if (repository.settings.first().brokerAuthenticated) {')
s=s.replace('import kotlinx.coroutines.flow.combine\n', 'import kotlinx.coroutines.flow.combine\nimport kotlinx.coroutines.flow.first\n')
assert old in s; s=s.replace(old,new)
p.write_text(s)

# UI wording for actual shadow simulator.
p=root/'app/src/main/java/com/multify/traderpro/ui/screens/TraderApp.kt'; s=p.read_text()
s=s.replace('"Paper analysis · live off"', '"Continuous shadow trading · live off"')
s=s.replace('"The engine is flat. Paper analysis continues even when live execution is off."', '"The shadow engine is flat. A Multify release can open a virtual position; it is then monitored every 30 seconds for target, stop or strategy reversal."')
s=s.replace('"Signals are analyzed on-device; real orders require the live toggle, confidence gate and all safety checks."', '"Paper trades include virtual quantity, target/stop monitoring, estimated costs and reversal exits. Real orders still require LIVE to be explicitly enabled."')
s=s.replace('"The on-device live engine uses a small validated ensemble; the larger catalogue remains reserved for replay and challenger research."', '"The same validated ensemble now runs continuously in shadow mode after a Multify signal, including automatic long/short reversals while LIVE remains off."')
s=s.replace('"Nightly challenger replay"', '"Shadow learning & replay"')
s=s.replace('"All candidate patterns remain available for after-market replay/research. Live rules are intentionally limited to repeatable, explainable strategy families rather than hindsight-fitting a single session."', '"Each closed paper trade records net P&L after estimated costs, MFE/MAE, strategy, regime and exit reason. These observations are the evidence base for deciding when a setup is mature enough for LIVE."')
p.write_text(s)

# README note
readme=Path('/mnt/data/v23work/README.md')
if readme.exists():
    txt=readme.read_text()
    txt='''# Multify Trader Pro v2.3\n\nThis build adds continuous paper/shadow trading: virtual positions, 30-second monitoring, target/stop/reversal exits, after-cost paper P&L, adaptive 1-minute analysis near the open, and automatic TOTP session refresh on incoming signals. LIVE execution remains opt-in only.\n\n'''+txt
    readme.write_text(txt)

print('v2.3 patch applied')
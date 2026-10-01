package com.multify.autotrader.domain

enum class EventType { TRADE_RELEASE, BOOK_PROFIT, PRE_ALERT, BUY_SUBMITTED, AUTO_PAUSED, UNKNOWN }
enum class DeliveryStatus { PENDING, SENT, FAILED, IGNORED }

data class ParsedSignal(
    val type: EventType,
    val symbol: String? = null,
    val target: Double? = null,
    val entryLow: Double? = null,
    val entryHigh: Double? = null,
    val stopLoss: Double? = null,
    val exitPrice: Double? = null,
    val returnsPct: Double? = null,
    val quantity: Int? = null,
    val confidence: Double = 0.0,
    val rawText: String = ""
) {
    val isRelevant: Boolean get() = type != EventType.UNKNOWN
    val isCritical: Boolean get() = type == EventType.AUTO_PAUSED
}

data class EngineHealth(
    val ok: Boolean = false,
    val mode: String = "offline",
    val brokerConfigured: Boolean = false,
    val scope: String = "NSE CASH MIS",
    val sessionState: String = "UNKNOWN",
    val killSwitch: Boolean = false
)

data class DashboardSummary(
    val realisedPnl: Double = 0.0,
    val unrealisedPnl: Double = 0.0,
    val trades: Int = 0,
    val wins: Int = 0,
    val losses: Int = 0,
    val openPositions: Int = 0,
    val dailyProfitLock: Double = 5000.0,
    val dailyLossLimit: Double = 2500.0
) { val winRate: Double get() = if (trades == 0) 0.0 else wins * 100.0 / trades }

data class PositionSnapshot(
    val symbol: String,
    val quantity: Int,
    val averagePrice: Double,
    val ltp: Double? = null,
    val unrealisedPnl: Double = 0.0,
    val realisedPnl: Double = 0.0,
    val side: String = if (quantity >= 0) "LONG" else "SHORT"
)

#!/usr/bin/env python3
from pathlib import Path
import sys

root=Path(sys.argv[1])

def rep(rel, old, new, count=None):
    p=root/rel
    s=p.read_text()
    if old not in s:
        raise SystemExit(f'missing pattern in {rel}: {old[:100]!r}')
    s=s.replace(old,new) if count is None else s.replace(old,new,count)
    p.write_text(s)

rep('app/build.gradle.kts','versionCode = 114','versionCode = 115')
rep('app/build.gradle.kts','versionName = "1.1.4"','versionName = "1.1.5"')

rep('app/src/main/java/com/suhas/ucsentinel/domain/engine/ExecutionQuality.kt',
'''    const val MIN_PLAN_SEPARATION_PCT = 0.25
''',
'''    const val MIN_PLAN_SEPARATION_PCT = 0.25
    const val MIN_DISCOVERY_VOLUME = 10_000L
    const val MIN_DISCOVERY_TRADED_VALUE = 500_000.0 // ₹5 lakh: discovery only, not LIVE execution
''')
rep('app/src/main/java/com/suhas/ucsentinel/domain/engine/ExecutionQuality.kt',
'''    fun executableQuote(q: Quote, requireTwoSided: Boolean = true): Boolean {''',
'''    /** Broad discovery gate. UC/Pressure may legitimately have an asymmetric book, so
     * two-sided depth is evaluated only when a candidate is promoted to LIVE. */
    fun discoveryQuote(q: Quote): Boolean {
        if (!q.lastPrice.isFinite() || q.lastPrice < MIN_PRICE) return false
        if (q.volume < MIN_DISCOVERY_VOLUME) return false
        val tradedValue = q.lastPrice * q.volume
        if (!tradedValue.isFinite() || tradedValue < MIN_DISCOVERY_TRADED_VALUE) return false
        return true
    }

    fun executableQuote(q: Quote, requireTwoSided: Boolean = true): Boolean {''')

rep('app/src/main/java/com/suhas/ucsentinel/data/remote/GrowwClient.kt',
'''    private val ohlcCacheTtlMs = 3 * 60 * 1000L
''',
'''    // A synchronized market pass happens every 5 minutes. Keep OHLC just under that so the
    // next cycle must refresh, while all engines inside one cycle reuse the same snapshot.
    private val ohlcCacheTtlMs = 4 * 60 * 1000L + 30_000L

    private data class QuoteCacheEntry(val atMs: Long, val value: Quote)
    private val quoteCache = ConcurrentHashMap<String, QuoteCacheEntry>()
    private val quoteCacheTtlMs = 2 * 60 * 1000L

    private data class CandleCacheEntry(val atMs: Long, val value: List<Candle>)
    private val candleCache = ConcurrentHashMap<String, CandleCacheEntry>()
    private val intradayCandleCacheTtlMs = 4 * 60 * 1000L + 30_000L
    private val dailyCandleCacheTtlMs = 6 * 60 * 60 * 1000L
''')
rep('app/src/main/java/com/suhas/ucsentinel/data/remote/GrowwClient.kt',
'''    suspend fun getQuote(accessToken: String, symbol: String): Quote =
        withContext(Dispatchers.IO) {
            val url = HttpUrl.Builder()
''',
'''    suspend fun getQuote(accessToken: String, symbol: String): Quote =
        withContext(Dispatchers.IO) {
            val now = System.currentTimeMillis()
            quoteCache[symbol]?.takeIf { now - it.atMs <= quoteCacheTtlMs }?.let { return@withContext it.value }
            val url = HttpUrl.Builder()
''')
rep('app/src/main/java/com/suhas/ucsentinel/data/remote/GrowwClient.kt',
'''            val payload = JSONObject(raw).optJSONObject("payload")
                ?: throw IOException("Missing quote payload for $symbol")
            parseQuote(symbol, payload)
        }
''',
'''            val payload = JSONObject(raw).optJSONObject("payload")
                ?: throw IOException("Missing quote payload for $symbol")
            parseQuote(symbol, payload).also { quoteCache[symbol] = QuoteCacheEntry(System.currentTimeMillis(), it) }
        }
''',1)
rep('app/src/main/java/com/suhas/ucsentinel/data/remote/GrowwClient.kt',
'''    ): List<Candle> = withContext(Dispatchers.IO) {
        val url = HttpUrl.Builder()
''',
'''    ): List<Candle> = withContext(Dispatchers.IO) {
        val cacheKey = "$symbol|$startTime|$endTime|$interval"
        val now = System.currentTimeMillis()
        val ttl = if (interval.equals("1day", true)) dailyCandleCacheTtlMs else intradayCandleCacheTtlMs
        candleCache[cacheKey]?.takeIf { now - it.atMs <= ttl }?.let { return@withContext it.value }
        if (candleCache.size > 1500) candleCache.clear()
        val url = HttpUrl.Builder()
''',1)
rep('app/src/main/java/com/suhas/ucsentinel/data/remote/GrowwClient.kt',
'''                )
            }
        }
    }

    private data class HttpResult(''',
'''                )
            }
        }.also { candleCache[cacheKey] = CandleCacheEntry(System.currentTimeMillis(), it) }
    }

    private data class HttpResult(''',1)

rep('app/src/main/java/com/suhas/ucsentinel/domain/engine/ScannerEngine.kt','val candidate = pct >= 3.5 || closeLike >= 3.5','val candidate = pct >= 2.0 || closeLike >= 2.0')
rep('app/src/main/java/com/suhas/ucsentinel/domain/engine/ScannerEngine.kt',
'''            if (!ExecutionQuality.executableQuote(quote)) {
                progress("Skipped ${instrument.tradingSymbol}: price/liquidity/spread not executable")
                continue
            }

            // Execution gate: strong momentum is not an actionable entry if there is nobody to sell.
            // Keep locked names out of recommendations and let the pressure engine find them earlier.
            val executableAsk = quote.totalSellQuantity > 0L && (
                (quote.offerPrice > 0.0 && quote.offerQuantity > 0L) ||
                    quote.sellDepth.any { it.price > 0.0 && it.quantity > 0L }
                )
            if (!executableAsk) {
                progress("Skipped ${instrument.tradingSymbol}: UC/ask locked — no executable sellers")
                continue
            }
''',
'''            // Discovery is deliberately broader than execution. A developing UC setup can have an
            // asymmetric book; rejecting it before scoring was starving the scanner.
            if (!ExecutionQuality.discoveryQuote(quote)) {
                progress("Skipped ${instrument.tradingSymbol}: insufficient discovery price/turnover")
                continue
            }
            val executableAsk = quote.totalSellQuantity > 0L && (
                (quote.offerPrice > 0.0 && quote.offerQuantity > 0L) ||
                    quote.sellDepth.any { it.price > 0.0 && it.quantity > 0L }
                )
            val executionReady = ExecutionQuality.executableQuote(quote) && executableAsk
''')
rep('app/src/main/java/com/suhas/ucsentinel/domain/engine/ScannerEngine.kt',
'''if (distanceToUc > 1.0) continue
            if (quote.dayChangePercent < 4.0) continue''',
'''if (distanceToUc > 3.0) continue
            if (quote.dayChangePercent < 2.0) continue''')
rep('app/src/main/java/com/suhas/ucsentinel/domain/engine/ScannerEngine.kt',
'''            val strategies = results.filter { it.passed }
                .groupBy { it.category }
                .mapValues { (_, list) -> list.sumOf { it.weight } }
                .entries.sortedByDescending { it.value }.take(5).map { it.key }
''',
'''            val strategies = buildList {
                if (executionReady) add("EXECUTION_READY")
                addAll(results.filter { it.passed }
                    .groupBy { it.category }
                    .mapValues { (_, list) -> list.sumOf { it.weight } }
                    .entries.sortedByDescending { it.value }.take(5).map { it.key })
            }
''')
rep('app/src/main/java/com/suhas/ucsentinel/domain/engine/ScannerEngine.kt',
'''        val qualified = candidates
            .filter { it.score >= effectiveThreshold }''',
'''        val qualified = candidates
            .filter { it.score >= effectiveThreshold && "EXECUTION_READY" in it.activeStrategies }''')

rep('app/src/main/java/com/suhas/ucsentinel/domain/engine/DemandScannerEngine.kt',
'''            if(!ExecutionQuality.executableQuote(quote)){
                progress("Skipped ${instrument.tradingSymbol}: price/liquidity/spread not executable")
                continue
            }
''',
'''            if(!ExecutionQuality.discoveryQuote(quote)){
                progress("Skipped ${instrument.tradingSymbol}: insufficient discovery price/turnover")
                continue
            }
''')
rep('app/src/main/java/com/suhas/ucsentinel/domain/engine/DemandScannerEngine.kt',
'''            // Hard anti-late-entry gates: v1.2 wants the stock BEFORE the obvious buy-pressure lock.
            if(ucDistance < 0.50) continue
            val absoluteLateRatio = if(settings.adaptiveRangesEnabled) 15.0 else settings.demandPressureMaxBuySellRatio * 1.5
            if(ratio > absoluteLateRatio) continue
            if(quote.totalSellQuantity<=0L && quote.offerQuantity<=0L) continue
            if(quote.dayChangePercent > 12.0 && isNew==null) continue
''',
'''            // Discovery keeps asymmetric/near-lock books visible; those conditions affect whether a
            // candidate can become LIVE rather than deleting it from the model entirely.
            val absoluteLateRatio = if(settings.adaptiveRangesEnabled) 15.0 else settings.demandPressureMaxBuySellRatio * 1.5
            val hardLocked = quote.totalSellQuantity<=0L && quote.offerQuantity<=0L && quote.sellDepth.none{it.price>0.0&&it.quantity>0L}
            var executionReady = ExecutionQuality.executableQuote(quote) && ucDistance>=0.35 && ratio<=absoluteLateRatio && !hardLocked && (quote.dayChangePercent<=12.0 || isNew!=null)
''')
rep('app/src/main/java/com/suhas/ucsentinel/domain/engine/DemandScannerEngine.kt',
'''            if(independentFamilies<2 && listingAge==null) continue
''',
'''            if(independentFamilies<1 && listingAge==null) continue
            executionReady = executionReady && (independentFamilies>=2 || listingAge!=null)
''')
rep('app/src/main/java/com/suhas/ucsentinel/domain/engine/DemandScannerEngine.kt',
'''            if(phase==PredictionPhase.ALREADY_SQUEEZED) continue
''',
'''            if(phase==PredictionPhase.ALREADY_SQUEEZED) executionReady=false
''')
rep('app/src/main/java/com/suhas/ucsentinel/domain/engine/DemandScannerEngine.kt',
'''                activeStrategies=signalEngine.activeStrategies(results),
''',
'''                activeStrategies=buildList { if(executionReady)add("EXECUTION_READY"); addAll(signalEngine.activeStrategies(results)) },
''')
rep('app/src/main/java/com/suhas/ucsentinel/domain/engine/DemandScannerEngine.kt',
'''        val qualified=candidates.filter{it.score>=effectiveThreshold}.sortedWith(''',
'''        val qualified=candidates.filter{it.score>=effectiveThreshold && "EXECUTION_READY" in it.activeStrategies}.sortedWith(''')

rep('app/src/main/java/com/suhas/ucsentinel/data/repository/UCSentinelRepository.kt','private val dualScanReuseMs=45_000L','private val dualScanReuseMs=4L*60_000L')
rep('app/src/main/java/com/suhas/ucsentinel/worker/MarketScanService.kt','nowMs-lastMarketPass >= 3L*60_000L','nowMs-lastMarketPass >= 5L*60_000L')
rep('app/src/main/java/com/suhas/ucsentinel/ui/CompactMarketScreens.kt',
'Background engine • 1 min heartbeat • works with app closed • 15 min WorkManager safety net',
'5 min synchronized scans • 1 min local heartbeat • works with app closed • 15 min safety net')
rep('app/src/main/java/com/suhas/ucsentinel/ui/CompactMarketScreens.kt',
'Monitoring only • executable but below confirmation threshold',
'Monitoring only • discovery candidate below LIVE execution/confirmation gate')

print('Global Edge AI Trader v1.1.5 upgrade applied')

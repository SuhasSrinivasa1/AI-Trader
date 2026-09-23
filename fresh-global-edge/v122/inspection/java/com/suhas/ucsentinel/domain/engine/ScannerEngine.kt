package com.suhas.globaledgeai.domain.engine

import com.suhas.globaledgeai.data.remote.GrowwClient
import com.suhas.globaledgeai.domain.model.*
import java.time.*
import java.time.format.DateTimeFormatter
import kotlin.math.abs

class ScannerEngine(
    private val growwClient: GrowwClient,
    private val signalEngine: SignalEngine = SignalEngine()
) {
    private val ist = ZoneId.of("Asia/Kolkata")
    private val fmt = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss")

    suspend fun scan(
        accessToken: String,
        universe: List<Instrument>,
        newListings: List<ListedSecurity> = emptyList(),
        settings: AppSettings,
        adaptivePrecision: Map<String, Double> = emptyMap(),
        progress: suspend (String) -> Unit = {},
        nextSessionMode: Boolean = false,
        rejectedShadow: suspend (Candidate, String) -> Unit = { _, _ -> }
    ): ScanSummary {
        val started = System.currentTimeMillis()

        // Actionable UC candidates are NSE EQ only. BE/BZ/SM/ST can be visible on exchanges but
        // are frequently non-intraday / trade-to-trade / illiquid, so they are research-only and
        // must never occupy a LIVE/WATCH execution slot.
        val cash = universe
            .filter { ExecutionQuality.eligibleInstrument(it) }
            .filterNot { looksLikeEtf(it) }

        progress("Batch OHLC screening ${cash.size} NSE cash instruments")

        val prelim = mutableListOf<Pair<Instrument, Ohlc>>()

        cash.chunked(50).forEachIndexed { index, batch ->
            val map = growwClient.getOhlcBatch(accessToken, batch.map { it.tradingSymbol })
            batch.forEach { instrument ->
                val o = map[instrument.tradingSymbol] ?: return@forEach
                if (o.close <= 0.0 || o.high <= 0.0) return@forEach
                val pct = (o.high / o.close - 1.0) * 100.0
                val closeLike = (o.open / o.close - 1.0) * 100.0
                val closeFromOpen = if (o.open > 0.0) (o.close / o.open - 1.0) * 100.0 else 0.0
                val candidate = if (nextSessionMode) closeFromOpen >= 0.5 || pct >= 1.5 else pct >= 2.0 || closeLike >= 2.0
                if (candidate) prelim += instrument to o
            }
            progress("Screened ${((index + 1) * 50).coerceAtMost(cash.size)}/${cash.size}")
        }

        val rankedPrelim = prelim
            .sortedByDescending { (_, o) -> if (o.close <= 0) 0.0 else (o.high / o.close - 1.0) * 100.0 }
            .take(settings.maxQuotesPerScan)

        progress("Confirming ${rankedPrelim.size} shortlisted stocks with full quote/depth")

        val candidates = mutableListOf<Candidate>()

        for ((idx, pair) in rankedPrelim.withIndex()) {
            val instrument = pair.first
            val quote = runCatching { growwClient.getQuote(accessToken, instrument.tradingSymbol) }.getOrNull()
                ?: continue

            // Discovery is deliberately broader than execution. A developing UC setup can have an
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

            val distanceToUc = if (quote.upperCircuit <= 0) {
                if (nextSessionMode) 6.0 else 999.0
            } else abs(quote.upperCircuit - quote.lastPrice) / quote.upperCircuit * 100.0

            val maxDistanceToUc = if (nextSessionMode) 8.0 else 3.0
            val minDayMove = if (nextSessionMode) 0.5 else 2.0
            if (distanceToUc > maxDistanceToUc) continue
            if (quote.dayChangePercent < minDayMove) continue

            val now = ZonedDateTime.now(ist)
            val dailyStart = now.minusDays(100).toLocalDate().atStartOfDay().format(fmt)
            val dailyEnd = now.plusDays(1).toLocalDate().atStartOfDay().format(fmt)
            val intradayStart = now.toLocalDate().atTime(9, 15).format(fmt)
            val intradayEnd = now.toLocalDate().atTime(15, 30).format(fmt)

            val daily = runCatching {
                growwClient.getHistoricalCandles(
                    accessToken,
                    instrument.tradingSymbol,
                    dailyStart,
                    dailyEnd,
                    "1day"
                )
            }.getOrDefault(emptyList())

            val intraday = runCatching {
                growwClient.getHistoricalCandles(
                    accessToken,
                    instrument.tradingSymbol,
                    intradayStart,
                    intradayEnd,
                    "5minute"
                )
            }.getOrDefault(emptyList())

            val isPostListing = daily.size in 1..25
            val results = signalEngine.evaluate(
                SignalEngine.Context(
                    quote = quote,
                    daily = daily,
                    intraday = intraday,
                    isPostListing = isPostListing
                )
            )
            var score = signalEngine.score(results, adaptivePrecision)

            // Hard UC-continuation gates carry additional impact.
            if (distanceToUc <= 0.10) score += 5.0
            // Reward strong demand only while actual sell-side liquidity still exists.
            if (quote.totalBuyQuantity > quote.totalSellQuantity && quote.offerQuantity > 0L) score += 2.0
            if (Indicators.consecutiveCircuitLikeDays(daily) >= 1) score += 3.0
            score = score.coerceIn(0.0, 100.0)

            val avgVol = Indicators.avgVolume(daily.dropLast(1), 20)
            val volumeRatio = if (avgVol <= 0.0) 0.0 else quote.volume / avgVol
            val buySellRatio = if (quote.totalSellQuantity <= 0L) {
                if (quote.totalBuyQuantity > 0) 99.0 else 0.0
            } else {
                quote.totalBuyQuantity.toDouble() / quote.totalSellQuantity
            }

            val confidence = when {
                score >= 90 -> ConfidenceBand.VERY_HIGH
                score >= 82 -> ConfidenceBand.HIGH
                score >= 72 -> ConfidenceBand.MEDIUM
                else -> ConfidenceBand.LOW
            }

            val listingAge = newListings.firstOrNull { it.symbol == instrument.tradingSymbol }?.daysListed
                ?: daily.size.takeIf { it in 1..45 }?.toLong()
            val strategies = buildList {
                if (executionReady) add("EXECUTION_READY")
                if (nextSessionMode) add("NEXT_SESSION")
                addAll(results.filter { it.passed }
                    .groupBy { it.category }
                    .mapValues { (_, list) -> list.sumOf { it.weight } }
                    .entries.sortedByDescending { it.value }.take(5).map { it.key })
            }

            candidates += Candidate(
                symbol = instrument.tradingSymbol,
                companyName = instrument.name,
                kind = if (isPostListing || listingAge != null) CandidateKind.POST_LISTING else CandidateKind.SEASONED,
                section = ScannerSection.UC_CONTINUATION,
                price = quote.lastPrice,
                upperCircuit = quote.upperCircuit,
                dayChangePercent = quote.dayChangePercent,
                score = score,
                confidence = confidence,
                passedSignals = results.count { it.passed },
                totalSignals = results.size,
                buySellRatio = buySellRatio,
                volumeRatio = volumeRatio,
                consecutiveCircuitLikeDays = Indicators.consecutiveCircuitLikeDays(daily),
                signals = results,
                activeStrategies = strategies,
                listingAgeDays = listingAge,
                modelVersion = SignalEngine.MODEL_VERSION,
                predictionHorizonHours = 24
            )

            progress("Analyzed ${idx + 1}/${rankedPrelim.size}: ${instrument.tradingSymbol}")
        }

        val thresholdDecision = if (settings.adaptiveRangesEnabled) {
            AdaptiveRangeEngine.ucThreshold(settings.minScore, candidates.map { it.score }, settings.maxFinalCandidates)
        } else null
        val effectiveThreshold = thresholdDecision?.threshold ?: settings.minScore
        val qualifiedAll = candidates
            .filter { it.score >= effectiveThreshold && (nextSessionMode || "EXECUTION_READY" in it.activeStrategies) }
            .sortedWith(
                compareByDescending<Candidate> { it.score }
                    .thenByDescending { it.buySellRatio }
                    .thenByDescending { it.volumeRatio }
            )
        val qualified = qualifiedAll.take(settings.maxFinalCandidates)
        // False-negative learning: keep the strongest candidates that the production gate rejected.
        // These are paper/shadow observations only and never become recommendations.
        candidates.filterNot { c -> qualified.any { it.symbol==c.symbol } }
            .sortedByDescending { it.score }.take(8).forEach { c ->
                val reason=when{
                    c.score<effectiveThreshold->"BELOW_THRESHOLD ${"%.1f".format(c.score)} < ${"%.1f".format(effectiveThreshold)}"
                    !nextSessionMode && "EXECUTION_READY" !in c.activeStrategies->"EXECUTION_GATE"
                    else->"RANK_CAP"
                }
                rejectedShadow(c,reason)
            }
        // Keep the UI informative even on a quiet day. These fallback names are explicitly
        // WATCHLIST ONLY and are never sent through the actionable UC notification path.
        val final = if(qualified.isNotEmpty()) qualified else candidates
            .sortedWith(
                compareByDescending<Candidate> { it.score }
                    .thenByDescending { it.buySellRatio }
                    .thenByDescending { it.volumeRatio }
            )
            .take(3)

        val completed = System.currentTimeMillis()

        return ScanSummary(
            section = ScannerSection.UC_CONTINUATION,
            startedAt = started,
            completedAt = completed,
            universeCount = cash.size,
            preliminaryCount = rankedPrelim.size,
            quotedCount = rankedPrelim.size,
            candidates = final,
            newListingsScanned = newListings.size,
            message = when {
                nextSessionMode && qualified.isNotEmpty() -> "NEXT SESSION • ${qualified.size} UC candidate(s) passed research threshold ${"%.1f".format(effectiveThreshold)}"
                nextSessionMode && final.isNotEmpty() -> "NEXT SESSION WATCH • best ${"%.1f".format(final.first().score)} vs threshold ${"%.1f".format(effectiveThreshold)}"
                qualified.isNotEmpty() -> "${qualified.size} candidate(s) passed UC threshold ${"%.1f".format(effectiveThreshold)}${if(settings.adaptiveRangesEnabled) " • adaptive" else ""}"
                final.isNotEmpty() -> "WATCHLIST ONLY • no qualified UC candidate • best ${"%.1f".format(final.first().score)} vs threshold ${"%.1f".format(effectiveThreshold)}"
                settings.adaptiveRangesEnabled -> "NO QUALIFIED UC CANDIDATE • adaptive floor ${thresholdDecision?.floor?.toInt() ?: 66}"
                else -> "NO QUALIFIED UC CANDIDATE"
            }
        )
    }

    private fun looksLikeEtf(i: Instrument): Boolean {
        val text = "${i.name} ${i.instrumentType} ${i.tradingSymbol}".uppercase()
        return listOf(" ETF", "ETF ", "BEES", "GOLD", "SILVER").any { text.contains(it) } &&
                !text.contains("LIMITED")
    }
}

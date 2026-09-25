package com.suhas.globaledgeai.data.remote

import com.suhas.globaledgeai.domain.model.*
import com.suhas.globaledgeai.domain.model.Credentials as AppCredentials
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.withContext
import okhttp3.*
import okhttp3.logging.HttpLoggingInterceptor
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONArray
import org.json.JSONObject
import java.io.IOException
import java.security.MessageDigest
import java.time.LocalTime
import java.time.ZoneId
import java.time.ZonedDateTime
import java.util.concurrent.TimeUnit
import java.util.concurrent.ConcurrentHashMap
import javax.crypto.Mac
import javax.crypto.spec.SecretKeySpec
import kotlin.math.pow
import kotlin.math.min

class GrowwClient {

    private fun finiteNumber(value:Double,fallback:Double=0.0):Double =
        if(value.isFinite()) value else fallback

    private fun jsonDouble(obj:JSONObject,name:String,fallback:Double=0.0):Double =
        finiteNumber(obj.optDouble(name,fallback),fallback)

    companion object {
        const val API_BASE = "https://api.groww.in"
        const val INSTRUMENT_URL = "https://growwapi-assets.groww.in/instruments/instrument.csv"
    }

    private val client: OkHttpClient = OkHttpClient.Builder()
        .connectTimeout(20, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .writeTimeout(20, TimeUnit.SECONDS)
        .addInterceptor(
            HttpLoggingInterceptor().apply {
                level = HttpLoggingInterceptor.Level.BASIC
            }
        )
        .build()

    // Groww live-data calls share a conservative process-local gate. 350 ms ~= 171/minute,
    // intentionally below the documented ceiling so dual-model scans do not self-throttle.
    private val liveLimiter = ApiRateLimiter(350L)
    private val historicalLimiter = ApiRateLimiter(300L)
    private val authLimiter = ApiRateLimiter(250L)

    private data class OhlcCacheEntry(val atMs: Long, val value: Ohlc)
    private val ohlcCache = ConcurrentHashMap<String, OhlcCacheEntry>()
    // A synchronized market pass happens every 5 minutes. Keep OHLC just under that so the
    // next cycle must refresh, while all engines inside one cycle reuse the same snapshot.
    private val ohlcCacheTtlMs = 4 * 60 * 1000L + 30_000L

    private data class QuoteCacheEntry(val atMs: Long, val value: Quote)
    private val quoteCache = ConcurrentHashMap<String, QuoteCacheEntry>()
    private val quoteCacheTtlMs = 2 * 60 * 1000L
    private val closedMarketLiveCacheTtlMs = 60 * 60 * 1000L

    private fun indianMarketHot():Boolean{
        val t=ZonedDateTime.now(ZoneId.of("Asia/Kolkata")).toLocalTime()
        return t>=LocalTime.of(9,0)&&t<=LocalTime.of(15,30)
    }

    private data class CandleCacheEntry(val atMs: Long, val value: List<Candle>)
    private val candleCache = ConcurrentHashMap<String, CandleCacheEntry>()
    private val intradayCandleCacheTtlMs = 4 * 60 * 1000L + 30_000L
    private val dailyCandleCacheTtlMs = 6 * 60 * 60 * 1000L

    suspend fun authenticate(credentials: AppCredentials): Pair<String, String> = withContext(Dispatchers.IO) {
        require(credentials.apiKeyOrTotpToken.isNotBlank()) { "API/TOTP token is empty" }
        require(credentials.secret.isNotBlank()) { "Secret is empty" }

        val body = when (credentials.mode) {
            AuthMode.TOTP -> JSONObject()
                .put("key_type", "totp")
                .put("totp", Totp.generate(credentials.secret))
            AuthMode.APPROVAL -> {
                val timestamp = (System.currentTimeMillis() / 1000L).toString()
                val checksum = sha256(credentials.secret + timestamp)
                JSONObject()
                    .put("key_type", "approval")
                    .put("checksum", checksum)
                    .put("timestamp", timestamp)
            }
        }

        val request = Request.Builder()
            .url("$API_BASE/v1/token/api/access")
            .header("Authorization", "Bearer ${credentials.apiKeyOrTotpToken}")
            .header("Content-Type", "application/json")
            .post(body.toString().toRequestBody("application/json".toMediaType()))
            .build()

        val raw = executeWithRetry(request, authLimiter, "Authentication", maxAttempts = 3)
        val json = JSONObject(raw)
        val token = json.optString("token")
            .ifBlank { json.optJSONObject("payload")?.optString("token").orEmpty() }
        val expiry = json.optString("expiry")
            .ifBlank { json.optJSONObject("payload")?.optString("expiry").orEmpty() }

        require(token.isNotBlank()) { "Groww response did not contain an access token" }
        token to expiry
    }

    suspend fun downloadInstrumentCsv(): String = withContext(Dispatchers.IO) {
        val request = Request.Builder().url(INSTRUMENT_URL).get().build()
        client.newCall(request).execute().use { response ->
            if (!response.isSuccessful) {
                throw IOException("Instrument download failed: HTTP ${response.code}")
            }
            response.body?.string() ?: throw IOException("Empty instrument CSV")
        }
    }

    suspend fun placeMarketOrder(
        accessToken:String,
        tradingSymbol:String,
        quantity:Int,
        product:String,
        transactionType:String
    ):String=withContext(Dispatchers.IO){
        val symbol=tradingSymbol.trim().uppercase()
        val prod=product.trim().uppercase()
        val side=transactionType.trim().uppercase()
        require(symbol.matches(Regex("""^[A-Z0-9&._-]{1,40}$"""))){"Invalid trading symbol"}
        require(quantity>0){"Quantity must be greater than zero"}
        require(prod in setOf("CNC","MIS")){"Unsupported product: $prod"}
        require(side in setOf("BUY","SELL")){"Unsupported transaction type: $side"}
        require((side=="BUY"&&prod=="CNC")||(side=="SELL"&&prod=="MIS")){
            "Manual mapping rejected: LONG must be BUY/CNC and SHORT must be SELL/MIS"
        }
        val referenceId="GE-"+System.currentTimeMillis().toString().takeLast(13)
        val body=JSONObject()
            .put("trading_symbol",symbol)
            .put("quantity",quantity)
            .put("validity","DAY")
            .put("exchange","NSE")
            .put("segment","CASH")
            .put("product",prod)
            .put("order_type","MARKET")
            .put("transaction_type",side)
            .put("order_reference_id",referenceId)

        val request=Request.Builder()
            .url("$API_BASE/v1/order/create")
            .header("Authorization","Bearer $accessToken")
            .header("Accept","application/json")
            .header("Content-Type","application/json")
            .header("X-API-VERSION","1.0")
            .post(body.toString().toRequestBody("application/json".toMediaType()))
            .build()

        val raw=client.newCall(request).execute().use{response->
            val text=response.body?.string().orEmpty()
            if(!response.isSuccessful)throw IOException("Groww order failed (${response.code}): ${safeMessage(text)}")
            text
        }
        val json=runCatching{JSONObject(raw)}.getOrElse{throw IOException("Groww returned an unreadable order response")}
        if(!json.optString("status").equals("SUCCESS",true)){
            throw IOException("Groww order rejected: ${safeMessage(raw)}")
        }
        val payload=json.optJSONObject("payload")?:JSONObject()
        val orderId=payload.optString("groww_order_id")
        val orderStatus=payload.optString("order_status").ifBlank{"ACCEPTED"}
        val remark=payload.optString("remark")
        val idText=orderId.ifBlank{referenceId}
        "Groww order $idText • $orderStatus"+if(remark.isBlank())"" else " • $remark"
    }

    suspend fun getOhlcBatch(accessToken: String, symbols: List<String>): Map<String, Ohlc> =
        withContext(Dispatchers.IO) {
            if (symbols.isEmpty()) return@withContext emptyMap()
            require(symbols.size <= 50) { "Groww OHLC accepts a maximum of 50 symbols per call" }

            val now = System.currentTimeMillis()
            val result = linkedMapOf<String, Ohlc>()
            val missing = mutableListOf<String>()
            symbols.forEach { symbol ->
                val cached = ohlcCache[symbol]
                val ttl=if(indianMarketHot())ohlcCacheTtlMs else closedMarketLiveCacheTtlMs
                if (cached != null && now - cached.atMs <= ttl) {
                    result[symbol] = cached.value
                } else {
                    missing += symbol
                }
            }

            if (missing.isNotEmpty()) {
                val joined = missing.joinToString(",") { "NSE_$it" }
                val url = HttpUrl.Builder()
                    .scheme("https")
                    .host("api.groww.in")
                    .addPathSegments("v1/live-data/ohlc")
                    .addQueryParameter("segment", "CASH")
                    .addQueryParameter("exchange_symbols", joined)
                    .build()

                val request = authedGet(url, accessToken)
                val raw = executeWithRetry(request, liveLimiter, "OHLC")
                val fetched = parseOhlcPayload(JSONObject(raw).optJSONObject("payload") ?: JSONObject())
                val at = System.currentTimeMillis()
                fetched.forEach { (symbol, value) ->
                    ohlcCache[symbol] = OhlcCacheEntry(at, value)
                    result[symbol] = value
                }
            }

            result
        }

    suspend fun prefetchOhlcSnapshot(
        accessToken: String,
        symbols: List<String>,
        progress: suspend (String) -> Unit = {}
    ) {
        val unique = symbols.distinct()
        unique.chunked(50).forEachIndexed { index, batch ->
            getOhlcBatch(accessToken, batch)
            progress("Market snapshot ${((index + 1) * 50).coerceAtMost(unique.size)}/${unique.size}")
        }
    }

    suspend fun getQuote(accessToken: String, symbol: String): Quote =
        withContext(Dispatchers.IO) {
            val now = System.currentTimeMillis()
            val ttl=if(indianMarketHot())quoteCacheTtlMs else closedMarketLiveCacheTtlMs
            quoteCache[symbol]?.takeIf { now - it.atMs <= ttl }?.let { return@withContext it.value }
            val url = HttpUrl.Builder()
                .scheme("https")
                .host("api.groww.in")
                .addPathSegments("v1/live-data/quote")
                .addQueryParameter("exchange", "NSE")
                .addQueryParameter("segment", "CASH")
                .addQueryParameter("trading_symbol", symbol)
                .build()

            val request = authedGet(url, accessToken)
            val raw = executeWithRetry(request, liveLimiter, "Quote for $symbol")
            val payload = JSONObject(raw).optJSONObject("payload")
                ?: throw IOException("Missing quote payload for $symbol")
            parseQuote(symbol, payload).also { quoteCache[symbol] = QuoteCacheEntry(System.currentTimeMillis(), it) }
        }

    suspend fun getHistoricalCandles(
        accessToken: String,
        symbol: String,
        startTime: String,
        endTime: String,
        interval: String
    ): List<Candle> = withContext(Dispatchers.IO) {
        val cacheKey = "$symbol|$startTime|$endTime|$interval"
        val now = System.currentTimeMillis()
        val nowIst=ZonedDateTime.now(ZoneId.of("Asia/Kolkata")).toLocalTime()
        val marketOpen=nowIst>=LocalTime.of(9,15)&&nowIst<=LocalTime.of(15,30)
        val ttl = when {
            interval.equals("1day", true) -> dailyCandleCacheTtlMs
            !marketOpen -> 6 * 60 * 60 * 1000L
            else -> intradayCandleCacheTtlMs
        }
        candleCache[cacheKey]?.takeIf { now - it.atMs <= ttl }?.let { return@withContext it.value }
        if (candleCache.size > 1500) candleCache.clear()
        val url = HttpUrl.Builder()
            .scheme("https")
            .host("api.groww.in")
            .addPathSegments("v1/historical/candles")
            .addQueryParameter("exchange", "NSE")
            .addQueryParameter("segment", "CASH")
            .addQueryParameter("groww_symbol", "NSE-$symbol")
            .addQueryParameter("start_time", startTime)
            .addQueryParameter("end_time", endTime)
            .addQueryParameter("candle_interval", interval)
            .build()

        val request = authedGet(url, accessToken)
        val raw = executeWithRetry(request, historicalLimiter, "Historical candles for $symbol")
        val payload = JSONObject(raw).optJSONObject("payload") ?: JSONObject()
        val candles = payload.optJSONArray("candles") ?: JSONArray()
        buildList {
            for (i in 0 until candles.length()) {
                val row = candles.optJSONArray(i) ?: continue
                if (row.length() < 6) continue
                val open=finiteNumber(row.optDouble(1))
                val high=finiteNumber(row.optDouble(2))
                val low=finiteNumber(row.optDouble(3))
                val close=finiteNumber(row.optDouble(4))
                if(open<=0.0||high<=0.0||low<=0.0||close<=0.0)continue
                add(
                    Candle(
                        epochSeconds = row.optLong(0),
                        open = open,
                        high = high,
                        low = low,
                        close = close,
                        volume = row.optLong(5).coerceAtLeast(0L)
                    )
                )
            }
        }.also { candleCache[cacheKey] = CandleCacheEntry(System.currentTimeMillis(), it) }
    }

    private data class HttpResult(
        val code: Int,
        val successful: Boolean,
        val body: String,
        val retryAfterSeconds: Long?
    )

    private suspend fun executeWithRetry(
        request: Request,
        limiter: ApiRateLimiter,
        operation: String,
        maxAttempts: Int = 5
    ): String {
        var lastCode = 0
        var lastBody = ""
        repeat(maxAttempts) { attempt ->
            limiter.awaitPermit()
            val result = try {
                withContext(Dispatchers.IO) {
                    client.newCall(request).execute().use { response ->
                        HttpResult(
                            code = response.code,
                            successful = response.isSuccessful,
                            body = response.body?.string().orEmpty(),
                            retryAfterSeconds = response.header("Retry-After")?.toLongOrNull()
                        )
                    }
                }
            } catch(io:IOException) {
                if(attempt==maxAttempts-1){
                    val dns=io.message.orEmpty().contains("Unable to resolve host",true)||io.message.orEmpty().contains("hostname",true)
                    if(dns) throw IOException("Groww network/DNS lookup failed after automatic retries. The official API host is api.groww.in; Global Edge AI Trader will retry again in the background. If this persists, check Private DNS, VPN, Wi-Fi/mobile-data DNS, or network filtering.",io)
                    throw io
                }
                delay(min(15_000L,1_500L*(attempt+1)*(attempt+1)))
                return@repeat
            }
            lastCode = result.code
            lastBody = result.body
            if (result.successful) return result.body

            if (result.code == 429) {
                val serverMs = result.retryAfterSeconds?.times(1000L)
                val exponentialMs = min(30_000L, 2_000L * (1L shl attempt.coerceAtMost(4)))
                delay((serverMs ?: exponentialMs).coerceAtLeast(1_500L))
            } else {
                throw IOException("$operation failed (${result.code}): ${safeMessage(result.body)}")
            }
        }

        if (lastCode == 429) {
            throw IOException(
                "Groww live-data rate limit is still active. Global Edge AI Trader already slowed down and retried automatically. " +
                    "Please wait about one minute before the next manual scan."
            )
        }
        throw IOException("$operation failed ($lastCode): ${safeMessage(lastBody)}")
    }

    private fun authedGet(url: HttpUrl, token: String): Request =
        Request.Builder()
            .url(url)
            .header("Authorization", "Bearer $token")
            .header("Accept", "application/json")
            .header("X-API-VERSION", "1.0")
            .get()
            .build()

    private fun parseOhlcPayload(payload: JSONObject): Map<String, Ohlc> {
        val result = linkedMapOf<String, Ohlc>()
        val keys = payload.keys()
        while (keys.hasNext()) {
            val key = keys.next()
            val value = payload.opt(key)
            val obj = when (value) {
                is JSONObject -> value
                is String -> parseLooseOhlc(value)
                else -> null
            } ?: continue

            val symbol = key.substringAfter("NSE_")
            result[symbol] = Ohlc(
                open = jsonDouble(obj,"open"),
                high = jsonDouble(obj,"high"),
                low = jsonDouble(obj,"low"),
                close = jsonDouble(obj,"close")
            )
        }
        return result
    }

    private fun parseLooseOhlc(raw: String): JSONObject? {
        val clean = raw.trim().removePrefix("{").removeSuffix("}")
        if (clean.isBlank()) return null
        val obj = JSONObject()
        clean.split(",").forEach { token ->
            val parts = token.split(":", limit = 2)
            if (parts.size == 2) {
                val parsed=parts[1].trim().toDoubleOrNull();obj.put(parts[0].trim().trim('"'),parsed?.takeIf{it.isFinite()}?:0.0)
            }
        }
        return obj
    }

    private fun parseQuote(symbol: String, p: JSONObject): Quote {
        val o = when (val raw = p.opt("ohlc")) {
            is JSONObject -> raw
            is String -> parseLooseOhlc(raw) ?: JSONObject()
            else -> JSONObject()
        }

        val depth = p.optJSONObject("depth") ?: JSONObject()

        fun levels(name: String): List<DepthLevel> {
            val arr = depth.optJSONArray(name) ?: JSONArray()
            return buildList {
                for (i in 0 until arr.length()) {
                    val x = arr.optJSONObject(i) ?: continue
                    val price=jsonDouble(x,"price");if(price>0.0)add(DepthLevel(price,x.optLong("quantity").coerceAtLeast(0L)))
                }
            }
        }

        return Quote(
            symbol = symbol,
            lastPrice = jsonDouble(p,"last_price"),
            previousClose = jsonDouble(o,"close"),
            dayChangePercent = jsonDouble(p,"day_change_perc"),
            upperCircuit = jsonDouble(p,"upper_circuit_limit"),
            lowerCircuit = jsonDouble(p,"lower_circuit_limit"),
            volume = p.optLong("volume"),
            totalBuyQuantity = p.optLong("total_buy_quantity"),
            totalSellQuantity = p.optLong("total_sell_quantity"),
            bidPrice = jsonDouble(p,"bid_price"),
            bidQuantity = p.optLong("bid_quantity"),
            offerPrice = jsonDouble(p,"offer_price"),
            offerQuantity = p.optLong("offer_quantity"),
            marketCap = jsonDouble(p,"market_cap"),
            week52High = jsonDouble(p,"week_52_high"),
            week52Low = jsonDouble(p,"week_52_low"),
            ohlc = Ohlc(
                open = jsonDouble(o,"open"),
                high = jsonDouble(o,"high"),
                low = jsonDouble(o,"low"),
                close = jsonDouble(o,"close")
            ),
            buyDepth = levels("buy"),
            sellDepth = levels("sell"),
            lastTradeTime = p.optLong("last_trade_time")
        )
    }

    private fun sha256(input: String): String {
        val bytes = MessageDigest.getInstance("SHA-256").digest(input.toByteArray())
        return bytes.joinToString("") { "%02x".format(it) }
    }

    private fun safeMessage(raw: String): String =
        runCatching {
            val j = JSONObject(raw)
            j.optString("message")
                .ifBlank { j.optString("error") }
                .ifBlank { raw.take(220) }
        }.getOrElse { raw.take(220) }
}

object Totp {
    fun generate(base32Secret: String, timeMillis: Long = System.currentTimeMillis()): String {
        val key = decodeBase32(base32Secret.replace(" ", "").uppercase())
        val counter = timeMillis / 1000L / 30L
        val data = ByteArray(8)
        var value = counter
        for (i in 7 downTo 0) {
            data[i] = (value and 0xff).toByte()
            value = value shr 8
        }
        val mac = Mac.getInstance("HmacSHA1")
        mac.init(SecretKeySpec(key, "HmacSHA1"))
        val hash = mac.doFinal(data)
        val offset = hash.last().toInt() and 0x0f
        val binary = ((hash[offset].toInt() and 0x7f) shl 24) or
                ((hash[offset + 1].toInt() and 0xff) shl 16) or
                ((hash[offset + 2].toInt() and 0xff) shl 8) or
                (hash[offset + 3].toInt() and 0xff)
        val otp = binary % 1_000_000
        return otp.toString().padStart(6, '0')
    }

    private fun decodeBase32(input: String): ByteArray {
        val alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"
        var buffer = 0
        var bitsLeft = 0
        val out = ArrayList<Byte>()
        input.trimEnd('=').forEach { ch ->
            val value = alphabet.indexOf(ch)
            if (value < 0) return@forEach
            buffer = (buffer shl 5) or value
            bitsLeft += 5
            if (bitsLeft >= 8) {
                out.add(((buffer shr (bitsLeft - 8)) and 0xff).toByte())
                bitsLeft -= 8
            }
        }
        return out.toByteArray()
    }
}

from pathlib import Path

root = Path("android")

p = root / "app/build.gradle.kts"
s = p.read_text().replace('versionCode = 210', 'versionCode = 220').replace('versionName = "2.1.0"', 'versionName = "2.2.0"')
p.write_text(s)

p = root / "app/src/main/java/com/multify/traderpro/data/network/GrowwModels.kt"
s = p.read_text()
old = '''data class TokenRequest(
    @SerializedName("key_type") val keyType: String = "approval",
    val checksum: String,
    val timestamp: String
)'''
new = '''data class TokenRequest(
    @SerializedName("key_type") val keyType: String = "totp",
    val totp: String? = null,
    val checksum: String? = null,
    val timestamp: String? = null
)'''
assert old in s
p.write_text(s.replace(old, new))

p = root / "app/src/main/java/com/multify/traderpro/data/preferences/SecretStore.kt"
s = p.read_text()
s = s.replace('fun hasApiSecret(): Boolean = prefs.contains(key("api_secret", "ciphertext"))',
              'fun hasTotpSecret(): Boolean = prefs.contains(key("api_secret", "ciphertext"))')
s = s.replace('fun hasBrokerCredentials(): Boolean = hasApiKey() && (hasApiSecret() || hasAccessToken())',
              'fun hasBrokerCredentials(): Boolean = hasApiKey() && (hasTotpSecret() || hasAccessToken())')
s = s.replace('fun putApiSecret(value: String) = put("api_secret", value)',
              'fun putTotpSecret(value: String) = put("api_secret", value)')
s = s.replace('fun getApiSecret(): String? = get("api_secret")',
              'fun getTotpSecret(): String? = get("api_secret")')
p.write_text(s)

sec = root / "app/src/main/java/com/multify/traderpro/data/security"
sec.mkdir(parents=True, exist_ok=True)
(sec / "TotpGenerator.kt").write_text(r'''package com.multify.traderpro.data.security

import java.nio.ByteBuffer
import java.util.Locale
import javax.crypto.Mac
import javax.crypto.spec.SecretKeySpec

object TotpGenerator {
    private const val STEP_SECONDS = 30L

    fun generate(base32Secret: String, epochSeconds: Long = System.currentTimeMillis() / 1000L): String {
        val key = decodeBase32(base32Secret)
        require(key.isNotEmpty()) { "Groww TOTP secret is empty or invalid" }
        val counter = epochSeconds / STEP_SECONDS
        val data = ByteBuffer.allocate(8).putLong(counter).array()
        val mac = Mac.getInstance("HmacSHA1")
        mac.init(SecretKeySpec(key, "HmacSHA1"))
        val hash = mac.doFinal(data)
        val offset = hash.last().toInt() and 0x0f
        val binary = ((hash[offset].toInt() and 0x7f) shl 24) or
            ((hash[offset + 1].toInt() and 0xff) shl 16) or
            ((hash[offset + 2].toInt() and 0xff) shl 8) or
            (hash[offset + 3].toInt() and 0xff)
        return String.format(Locale.US, "%06d", binary % 1_000_000)
    }

    private fun decodeBase32(value: String): ByteArray {
        val clean = value.uppercase(Locale.US).filter { !it.isWhitespace() && it != '-' && it != '=' }
        require(clean.isNotBlank()) { "Groww TOTP secret is empty" }
        var buffer = 0
        var bitsLeft = 0
        val out = ArrayList<Byte>(clean.length * 5 / 8)
        for (c in clean) {
            val v = when (c) {
                in 'A'..'Z' -> c.code - 'A'.code
                in '2'..'7' -> c.code - '2'.code + 26
                else -> throw IllegalArgumentException("Groww TOTP secret is not valid Base32")
            }
            buffer = (buffer shl 5) or v
            bitsLeft += 5
            if (bitsLeft >= 8) {
                bitsLeft -= 8
                out.add(((buffer shr bitsLeft) and 0xff).toByte())
                buffer = buffer and ((1 shl bitsLeft) - 1)
            }
        }
        return out.toByteArray()
    }
}
''')

p = root / "app/src/main/java/com/multify/traderpro/data/repository/TradingRepository.kt"
s = p.read_text()
s = s.replace('import com.multify.traderpro.engine.StrategyEvaluation\n',
              'import com.multify.traderpro.engine.StrategyEvaluation\nimport com.multify.traderpro.data.security.TotpGenerator\nimport com.google.gson.JsonParser\nimport retrofit2.HttpException\n')
s = s.replace('        apiSecret: String,\n', '        totpSecret: String,\n')
s = s.replace('if (apiSecret.isNotBlank()) secretStore.putApiSecret(apiSecret)',
              'if (totpSecret.isNotBlank()) secretStore.putTotpSecret(totpSecret)')
s = s.replace('if (apiKeyOrToken.isNotBlank() || apiSecret.isNotBlank()) {',
              'if (apiKeyOrToken.isNotBlank() || totpSecret.isNotBlank()) {')
s = s.replace('fun hasBrokerCredentials(): Boolean = secretStore.hasApiKey() && secretStore.hasApiSecret()',
              'fun hasBrokerCredentials(): Boolean = secretStore.hasApiKey() && secretStore.hasTotpSecret()')

old = '''        val apiKey = secretStore.getApiKey() ?: error("Groww API key/token is not configured")
        val secret = secretStore.getApiSecret() ?: error("Groww API secret is not configured")
        val publicIp = runCatching { apiFactory.publicIp.currentIp().ip.trim() }.getOrDefault("")
        val staticMatched = settings.expectedStaticIp.isNotBlank() && publicIp.isNotBlank() && normalizeIp(publicIp) == normalizeIp(settings.expectedStaticIp)

        val timestamp = (System.currentTimeMillis() / 1000L).toString()
        val checksum = sha256(secret + timestamp)
        val tokenResponse = apiFactory.groww.createAccessToken(
            authorization = "Bearer $apiKey",
            request = TokenRequest(checksum = checksum, timestamp = timestamp)
        )
'''
new = '''        val apiKey = secretStore.getApiKey() ?: error("Groww TOTP token is not configured")
        val totpSecret = secretStore.getTotpSecret() ?: error("Groww TOTP secret is not configured")
        val publicIp = runCatching { apiFactory.publicIp.currentIp().ip.trim() }.getOrDefault("")
        val staticMatched = settings.expectedStaticIp.isNotBlank() && publicIp.isNotBlank() && normalizeIp(publicIp) == normalizeIp(settings.expectedStaticIp)

        val totp = TotpGenerator.generate(totpSecret)
        val tokenResponse = try {
            apiFactory.groww.createAccessToken(
                authorization = "Bearer $apiKey",
                request = TokenRequest(keyType = "totp", totp = totp)
            )
        } catch (e: HttpException) {
            error(growwAuthError(e))
        }
'''
assert old in s
s = s.replace(old, new)

old = '''        val token = tokenResponse.token?.takeIf { it.isNotBlank() }
            ?: error(tokenResponse.error?.message ?: "Groww did not return an access token. Daily API-key approval may be required.")
'''
new = '''        val token = tokenResponse.token?.takeIf { it.isNotBlank() }
            ?: error(buildString {
                append("Groww did not return an access token")
                tokenResponse.error?.code?.takeIf { it.isNotBlank() }?.let { append(" ($it)") }
                tokenResponse.error?.message?.takeIf { it.isNotBlank() }?.let { append(": $it") }
                append(". Verify the TOTP token/secret and keep Automatic date & time enabled.")
            })
'''
assert old in s
s = s.replace(old, new)

needle = '''    private fun bearer(token: String) = "Bearer $token"
'''
helper = '''    private fun growwAuthError(e: HttpException): String {
        val raw = runCatching { e.response()?.errorBody()?.string().orEmpty() }.getOrDefault("")
        val parsed = runCatching { JsonParser.parseString(raw).asJsonObject }.getOrNull()
        val error = parsed?.getAsJsonObject("error")
        val code = error?.get("code")?.asString.orEmpty()
        val message = error?.get("message")?.asString.orEmpty()
        val detail = when {
            message.isNotBlank() && code.isNotBlank() -> "$code · $message"
            message.isNotBlank() -> message
            raw.isNotBlank() -> raw.take(180)
            else -> "Bad request"
        }
        return "Groww TOTP authentication failed (HTTP " + e.code() + "): " + detail +
            ". Verify the TOTP token and TOTP secret, and keep Automatic date & time enabled."
    }

    private fun bearer(token: String) = "Bearer $token"
'''
assert needle in s
p.write_text(s.replace(needle, helper))

p = root / "app/src/main/java/com/multify/traderpro/ui/screens/TraderViewModel.kt"
s = p.read_text()
s = s.replace('fun saveBrokerSettings(apiKey: String, apiSecret: String, staticIp: String, packageFilter: String, budgetText: String)',
              'fun saveBrokerSettings(apiKey: String, totpSecret: String, staticIp: String, packageFilter: String, budgetText: String)')
s = s.replace('repository.saveBrokerSettings(apiKey, apiSecret, staticIp, packageFilter, budget)',
              'repository.saveBrokerSettings(apiKey, totpSecret, staticIp, packageFilter, budget)')
p.write_text(s)

p = root / "app/src/main/java/com/multify/traderpro/ui/screens/TraderApp.kt"
s = p.read_text()
replacements = {
    'Save your Groww API key/token, API secret, static IP and daily budget in System.':
        'Save your Groww TOTP token, TOTP secret, static IP and daily budget in System.',
    'var apiSecret by remember { mutableStateOf("") }':
        'var totpSecret by remember { mutableStateOf("") }',
    'No custom backend URL is required. The app authenticates directly with Groww and keeps broker credentials in Android Keystore.':
        'No custom backend URL is required. Enter the TOTP token and TOTP secret generated on Groww. The app creates the rotating code locally and authenticates directly with Groww.',
    'Text("Groww API credentials", fontWeight = FontWeight.SemiBold)':
        'Text("Groww TOTP credentials", fontWeight = FontWeight.SemiBold)',
    'Text("API key + secret → daily access token"':
        'Text("TOTP token + TOTP secret → access token"',
    'label = { Text("Groww API key / token") }':
        'label = { Text("Groww TOTP token") }',
    '"Paste Groww API key"':
        '"Paste Groww TOTP token"',
    'value = apiSecret,':
        'value = totpSecret,',
    'onValueChange = { apiSecret = it },':
        'onValueChange = { totpSecret = it },',
    'label = { Text("Groww API secret") }':
        'label = { Text("Groww TOTP secret") }',
    '"Paste Groww API secret"':
        '"Paste Groww TOTP secret"',
    'supportingText = { Text("Used locally to create the Groww checksum/access token. It is never written to Room or logs.") },':
        'supportingText = { Text("Used only on-device to generate the current 6-digit TOTP code. The secret stays in Android Keystore and is never logged.") },',
    'onSave(apiKey, apiSecret, staticIp, packageFilter, budget)':
        'onSave(apiKey, totpSecret, staticIp, packageFilter, budget)',
}
for a, b in replacements.items():
    assert a in s, a
    s = s.replace(a, b)
p.write_text(s)

test = root / "app/src/test/java/com/multify/traderpro/TotpGeneratorTest.kt"
test.parent.mkdir(parents=True, exist_ok=True)
test.write_text(r'''package com.multify.traderpro

import com.multify.traderpro.data.security.TotpGenerator
import org.junit.Assert.assertEquals
import org.junit.Test

class TotpGeneratorTest {
    @Test
    fun rfc6238SixDigitVectorAt59Seconds() {
        assertEquals("287082", TotpGenerator.generate("GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ", 59L))
    }
}
''')

print("v2.2 patch applied")

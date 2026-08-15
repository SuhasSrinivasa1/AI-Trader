from pathlib import Path

ROOT = Path('android-stable')
JAVA = ROOT / 'app/src/main/java/com/suhas/multyfiautobuy/stable'
TEST = ROOT / 'app/src/test/java/com/suhas/multyfiautobuy/stable'

# Repair the v2.7.0 generated Stage2 source. `protected` is a Java keyword.
d = JAVA / 'Stage2DecisionPolicy.java'
ds = d.read_text()
old_decl = 'double protected = peakNet * factor;'
old_use = 'Math.max(minimumPositiveFloor, protected)'
assert old_decl in ds, 'Stage2DecisionPolicy protected declaration not found'
assert old_use in ds, 'Stage2DecisionPolicy protected use not found'
ds = ds.replace(old_decl, 'double protectedNetFloor = peakNet * factor;', 1)
ds = ds.replace(old_use, 'Math.max(minimumPositiveFloor, protectedNetFloor)', 1)
d.write_text(ds)

# Add transient Smart Order create retries to every GTT/Smart Order create path.
p = JAVA / 'GrowwClient.java'
s = p.read_text()
base = '    private static final String API_BASE = "https://api.groww.in/v1";\n'
assert base in s
s = s.replace(base, base + '    private static final int SMART_CREATE_MAX_ATTEMPTS = 3;\n', 1)

old_create = 'HttpResult http = request("POST", API_BASE + "/order-advance/create",\n                    accessToken, body);'
count = s.count(old_create)
assert count == 3, f'expected 3 Smart Order create paths, got {count}'
s = s.replace(old_create, 'HttpResult http = createSmartOrderWithRetry(accessToken, body);')

# The controlled 1-share GTT path used the generic failure message. Make exhausted
# transient service failures explicit while keeping the two specialised handlers intact.
old_simple_failure = ('HttpResult http = createSmartOrderWithRetry(accessToken, body);\n'
                      '            if (!http.isSuccess()) return apiFailure(http);')
count = s.count(old_simple_failure)
assert count == 1, f'expected 1 simple Smart Order failure handler, got {count}'
s = s.replace(old_simple_failure,
              'HttpResult http = createSmartOrderWithRetry(accessToken, body);\n'
              '            if (!http.isSuccess()) return smartCreateFailure(http);', 1)

marker = '    private static JSONObject gttBase(String reference, String symbol, int quantity,\n'
assert marker in s
helper = '''    static boolean isTransientSmartCreateHttpCode(int code) {
        return code == 429 || code == 500 || code == 502 || code == 503 || code == 504;
    }

    private static HttpResult createSmartOrderWithRetry(String accessToken,
                                                         JSONObject body) throws Exception {
        HttpResult last = null;
        long[] backoffMs = new long[]{0L, 250L, 750L};
        for (int attempt = 0; attempt < SMART_CREATE_MAX_ATTEMPTS; attempt++) {
            if (backoffMs[attempt] > 0L) {
                try {
                    Thread.sleep(backoffMs[attempt]);
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    break;
                }
            }
            // Retry only transient Smart Order create failures and reuse the exact
            // same JSON body/reference_id for every attempt.
            last = request("POST", API_BASE + "/order-advance/create", accessToken, body);
            if (!isTransientSmartCreateHttpCode(last.code)) return last;
        }
        return last == null
                ? new HttpResult(0, "Smart-order create was not attempted.") : last;
    }

    private static ApiResult smartCreateFailure(HttpResult http) {
        ApiResult baseFailure = apiFailure(http);
        if (!isTransientSmartCreateHttpCode(http.code)) return baseFailure;
        return ApiResult.failure(baseFailure.errorCode,
                "Groww Smart Order service remained unavailable after "
                        + SMART_CREATE_MAX_ATTEMPTS
                        + " safe same-reference attempts (HTTP " + http.code + "). "
                        + baseFailure.message,
                http.code);
    }

'''
s = s.replace(marker, helper + marker, 1)
p.write_text(s)

# Focused policy tests: retry server/rate-limit failures, never validation/auth errors.
t = TEST / 'GrowwSmartOrderRetryPolicyTest.java'
t.write_text('''package com.suhas.multyfiautobuy.stable;

import org.junit.Test;
import static org.junit.Assert.*;

public class GrowwSmartOrderRetryPolicyTest {
    @Test public void server5xxCodesAreTransient() {
        assertTrue(GrowwClient.isTransientSmartCreateHttpCode(500));
        assertTrue(GrowwClient.isTransientSmartCreateHttpCode(502));
        assertTrue(GrowwClient.isTransientSmartCreateHttpCode(503));
        assertTrue(GrowwClient.isTransientSmartCreateHttpCode(504));
    }

    @Test public void rateLimitIsTransient() {
        assertTrue(GrowwClient.isTransientSmartCreateHttpCode(429));
    }

    @Test public void clientAndAuthErrorsAreNotBlindlyRetried() {
        assertFalse(GrowwClient.isTransientSmartCreateHttpCode(400));
        assertFalse(GrowwClient.isTransientSmartCreateHttpCode(401));
        assertFalse(GrowwClient.isTransientSmartCreateHttpCode(403));
        assertFalse(GrowwClient.isTransientSmartCreateHttpCode(422));
    }
}
''')

print('Applied v2.7.1 Groww GTT transient retry + Stage2 Java keyword repair')

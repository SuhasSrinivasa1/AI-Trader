from pathlib import Path

TEST = Path('android-stable/app/src/test/java/com/suhas/multyfiautobuy/stable/GrowwSmartOrderRetryPolicyTest.java')
TEST.write_text('''package com.suhas.multyfiautobuy.stable;

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

    @Test public void duplicateSmartOrderMessageIsRecognised() {
        assertTrue(GrowwClient.isDuplicateSmartCreateBody(
                "Duplicate smart order. Order with this reference id already exists."));
    }

    @Test public void duplicateGrowwCodeIsRecognised() {
        assertTrue(GrowwClient.isDuplicateSmartCreateBody(
                "{\\\"error\\\":{\\\"code\\\":\\\"GA007\\\"}}"));
    }

    @Test public void ordinaryValidationMessageIsNotDuplicate() {
        assertFalse(GrowwClient.isDuplicateSmartCreateBody(
                "Trigger price must be below last traded price."));
    }
}
''')
print('Repaired v2.7.2 host-JVM tests: no Android org.json runtime dependency')

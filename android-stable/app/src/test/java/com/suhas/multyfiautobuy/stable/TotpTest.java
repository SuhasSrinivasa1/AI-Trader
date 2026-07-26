package com.suhas.multyfiautobuy.stable;

import static org.junit.Assert.assertEquals;

import org.junit.Test;

public class TotpTest {
    @Test
    public void matchesRfc6238SixDigitVectorAt59Seconds() throws Exception {
        String secret = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ";
        assertEquals("287082", Totp.generateAt(secret, 59_000L, 6));
    }
}

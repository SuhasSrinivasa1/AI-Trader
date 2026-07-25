package com.suhas.multyfiautobuy.stable;

import java.nio.ByteBuffer;
import java.util.Locale;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

final class Totp {
    private static final String ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";

    private Totp() { }

    static String generate(String base32Secret) throws Exception {
        return generateAt(base32Secret, System.currentTimeMillis(), 6);
    }

    static String generateAt(String base32Secret, long timeMillis, int digits) throws Exception {
        byte[] key = decodeBase32(base32Secret);
        if (key.length == 0) throw new IllegalArgumentException("TOTP secret is empty");
        long counter = timeMillis / 30_000L;
        byte[] counterBytes = ByteBuffer.allocate(8).putLong(counter).array();
        Mac mac = Mac.getInstance("HmacSHA1");
        mac.init(new SecretKeySpec(key, "HmacSHA1"));
        byte[] hash = mac.doFinal(counterBytes);
        int offset = hash[hash.length - 1] & 0x0F;
        int binary = ((hash[offset] & 0x7F) << 24)
                | ((hash[offset + 1] & 0xFF) << 16)
                | ((hash[offset + 2] & 0xFF) << 8)
                | (hash[offset + 3] & 0xFF);
        int modulo = 1;
        for (int i = 0; i < digits; i++) modulo *= 10;
        int otp = binary % modulo;
        return String.format(Locale.US, "%0" + digits + "d", otp);
    }

    static byte[] decodeBase32(String input) {
        if (input == null) return new byte[0];
        String clean = input.toUpperCase(Locale.US)
                .replace(" ", "")
                .replace("-", "")
                .replace("=", "");
        if (clean.isEmpty()) return new byte[0];

        java.io.ByteArrayOutputStream output = new java.io.ByteArrayOutputStream();
        int buffer = 0;
        int bitsLeft = 0;
        for (int i = 0; i < clean.length(); i++) {
            int value = ALPHABET.indexOf(clean.charAt(i));
            if (value < 0) throw new IllegalArgumentException("Invalid Base32 TOTP secret");
            buffer = (buffer << 5) | value;
            bitsLeft += 5;
            if (bitsLeft >= 8) {
                bitsLeft -= 8;
                output.write((buffer >> bitsLeft) & 0xFF);
            }
        }
        return output.toByteArray();
    }
}

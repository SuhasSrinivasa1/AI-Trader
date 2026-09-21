package com.ps.shadowtrader;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import java.util.Locale;

public final class TotpUtil {
    private static final String ALPHABET="ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
    private TotpUtil(){}

    public static String now(String base32Secret)throws Exception{
        return generate(base32Secret,System.currentTimeMillis()/1000L);
    }

    static String generate(String base32Secret,long epochSeconds)throws Exception{
        byte[] key=decodeBase32(base32Secret);
        long counter=epochSeconds/30L;
        byte[] msg=new byte[8];
        for(int i=7;i>=0;i--){msg[i]=(byte)(counter&0xff);counter>>>=8;}
        Mac mac=Mac.getInstance("HmacSHA1");
        mac.init(new SecretKeySpec(key,"HmacSHA1"));
        byte[] h=mac.doFinal(msg);
        int off=h[h.length-1]&0x0f;
        int bin=((h[off]&0x7f)<<24)|((h[off+1]&0xff)<<16)|((h[off+2]&0xff)<<8)|(h[off+3]&0xff);
        int otp=bin%1000000;
        return String.format(Locale.US,"%06d",otp);
    }

    private static byte[] decodeBase32(String input){
        String s=input==null?"":input.toUpperCase(Locale.US).replace("=","").replace(" ","").replace("-","");
        if(s.isEmpty())throw new IllegalArgumentException("TOTP secret is empty");
        java.io.ByteArrayOutputStream out=new java.io.ByteArrayOutputStream();
        int buffer=0,bits=0;
        for(int i=0;i<s.length();i++){
            int val=ALPHABET.indexOf(s.charAt(i));
            if(val<0)throw new IllegalArgumentException("Invalid Base32 TOTP secret");
            buffer=(buffer<<5)|val;bits+=5;
            if(bits>=8){bits-=8;out.write((buffer>>bits)&0xff);}
        }
        return out.toByteArray();
    }
}

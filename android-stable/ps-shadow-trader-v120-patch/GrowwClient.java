package com.ps.shadowtrader;

import org.json.*;
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.text.*;
import java.util.*;
import static com.ps.shadowtrader.Models.*;

public class GrowwClient {
    public JSONObject user(String token)throws Exception{return request("GET","https://api.groww.in/v1/user/detail",token,null);}

    public String generateAccessTokenTotp(String totpToken,String totpCode)throws Exception{
        JSONObject body=new JSONObject().put("key_type","totp").put("totp",totpCode);
        JSONObject r=request("POST","https://api.groww.in/v1/token/api/access",totpToken,body.toString());
        String token=r.optString("token","");
        if(token.isEmpty()){JSONObject p=r.optJSONObject("payload");if(p!=null)token=p.optString("token","");}
        if(token.isEmpty())throw new IOException("Groww did not return an access token");
        return token;
    }

    public double ltp(String token,String symbol)throws Exception{
        Map<String,Double>m=ltps(token,Arrays.asList(symbol));Double x=m.get(symbol);return x==null?Double.NaN:x;
    }

    public Map<String,Double> ltps(String token,List<String> symbols)throws Exception{
        LinkedHashMap<String,Double> out=new LinkedHashMap<>();if(symbols==null||symbols.isEmpty())return out;
        StringBuilder q=new StringBuilder();
        for(String s:symbols){if(s==null||s.trim().isEmpty())continue;if(q.length()>0)q.append(",");q.append("NSE_").append(URLEncoder.encode(s.trim().toUpperCase(Locale.ROOT),"UTF-8"));}
        if(q.length()==0)return out;
        String u="https://api.groww.in/v1/live-data/ltp?segment=CASH&exchange_symbols="+q;
        JSONObject r=request("GET",u,token,null),p=r.optJSONObject("payload");if(p==null)return out;
        for(String s:symbols){String k="NSE_"+s.trim().toUpperCase(Locale.ROOT);if(p.has(k))out.put(s.trim().toUpperCase(Locale.ROOT),p.optDouble(k,Double.NaN));}
        return out;
    }

    public List<Candle> candles(String token,String symbol,long startEpoch,long endEpoch,String interval)throws Exception{
        String growwSymbol="NSE-"+symbol;
        String u="https://api.groww.in/v1/historical/candles?exchange=NSE&segment=CASH&groww_symbol="+URLEncoder.encode(growwSymbol,"UTF-8")+
                "&start_time="+startEpoch+"&end_time="+endEpoch+"&candle_interval="+URLEncoder.encode(interval,"UTF-8");
        JSONObject r=request("GET",u,token,null),p=r.optJSONObject("payload");JSONArray a=p==null?null:p.optJSONArray("candles");List<Candle> out=new ArrayList<>();if(a==null)return out;
        SimpleDateFormat f=new SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss",Locale.US);f.setTimeZone(TimeZone.getTimeZone("Asia/Kolkata"));
        for(int i=0;i<a.length();i++){
            JSONArray z=a.getJSONArray(i);long ts;Object t=z.get(0);
            if(t instanceof Number)ts=((Number)t).longValue();else{try{ts=f.parse(String.valueOf(t)).getTime()/1000L;}catch(Exception e){ts=0;}}
            out.add(new Candle(ts,z.optDouble(1),z.optDouble(2),z.optDouble(3),z.optDouble(4),z.optDouble(5)));
        }
        return out;
    }

    public String downloadInstrumentCsv()throws Exception{
        HttpURLConnection c=(HttpURLConnection)new URL("https://growwapi-assets.groww.in/instruments/instrument.csv").openConnection();
        c.setConnectTimeout(10000);c.setReadTimeout(20000);c.setRequestProperty("Accept","text/csv");
        InputStream in=c.getInputStream();ByteArrayOutputStream bos=new ByteArrayOutputStream();byte[] b=new byte[8192];int n;while((n=in.read(b))!=-1)bos.write(b,0,n);return new String(bos.toByteArray(),StandardCharsets.UTF_8);
    }

    private JSONObject request(String method,String url,String bearer,String body)throws Exception{
        HttpURLConnection c=(HttpURLConnection)new URL(url).openConnection();c.setRequestMethod(method);c.setConnectTimeout(9000);c.setReadTimeout(15000);
        c.setRequestProperty("Accept","application/json");c.setRequestProperty("X-API-VERSION","1.0");c.setRequestProperty("Authorization","Bearer "+bearer);
        if(body!=null){c.setDoOutput(true);c.setRequestProperty("Content-Type","application/json");try(OutputStream os=c.getOutputStream()){os.write(body.getBytes(StandardCharsets.UTF_8));}}
        int code=c.getResponseCode();InputStream in=(code>=200&&code<300)?c.getInputStream():c.getErrorStream();ByteArrayOutputStream bos=new ByteArrayOutputStream();
        if(in!=null){byte[] buf=new byte[4096];int n;while((n=in.read(buf))!=-1)bos.write(buf,0,n);}
        String s=new String(bos.toByteArray(),StandardCharsets.UTF_8);if(code>=300)throw new IOException("HTTP "+code+": "+s);return new JSONObject(s);
    }
}

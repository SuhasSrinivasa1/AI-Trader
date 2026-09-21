package com.ps.shadowtrader;

import org.json.*;
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.text.*;
import java.util.*;
import static com.ps.shadowtrader.Models.*;

public class GrowwClient {
    private static final TimeZone IST=TimeZone.getTimeZone("Asia/Kolkata");

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
        for(String s:symbols){
            if(s==null||s.trim().isEmpty())continue;
            if(q.length()>0)q.append(",");
            q.append("NSE_").append(URLEncoder.encode(s.trim().toUpperCase(Locale.ROOT),"UTF-8"));
        }
        if(q.length()==0)return out;
        String u="https://api.groww.in/v1/live-data/ltp?segment=CASH&exchange_symbols="+q;
        JSONObject r=request("GET",u,token,null),p=r.optJSONObject("payload");if(p==null)return out;
        for(String s:symbols){
            String k="NSE_"+s.trim().toUpperCase(Locale.ROOT);
            if(p.has(k))out.put(s.trim().toUpperCase(Locale.ROOT),p.optDouble(k,Double.NaN));
        }
        return out;
    }

    public List<Candle> candles(String token,String symbol,long startEpoch,long endEpoch,String interval)throws Exception{
        if("1day".equalsIgnoreCase(interval))return dailyCandles(token,symbol,startEpoch,endEpoch);

        String growwSymbol="NSE-"+symbol;
        String u="https://api.groww.in/v1/historical/candles?exchange=NSE&segment=CASH&groww_symbol="+URLEncoder.encode(growwSymbol,"UTF-8")+
                "&start_time="+startEpoch+"&end_time="+endEpoch+"&candle_interval="+URLEncoder.encode(interval,"UTF-8");
        return parseCandles(request("GET",u,token,null));
    }

    public List<Candle> dailyCandles(String token,String symbol,long startEpoch,long endEpoch)throws Exception{
        long[] bounds=normalizeDailyBounds(startEpoch,endEpoch);
        String start=formatIst(bounds[0]);
        String end=formatIst(bounds[1]);
        String growwSymbol="NSE-"+symbol;

        String modern="https://api.groww.in/v1/historical/candles?exchange=NSE&segment=CASH&groww_symbol="+
                URLEncoder.encode(growwSymbol,"UTF-8")+
                "&start_time="+URLEncoder.encode(start,"UTF-8")+
                "&end_time="+URLEncoder.encode(end,"UTF-8")+
                "&candle_interval=1day";

        try{
            return parseCandles(request("GET",modern,token,null));
        }catch(IOException modernError){
            String legacy="https://api.groww.in/v1/historical/candle/range?exchange=NSE&segment=CASH&trading_symbol="+
                    URLEncoder.encode(symbol,"UTF-8")+
                    "&start_time="+URLEncoder.encode(start,"UTF-8")+
                    "&end_time="+URLEncoder.encode(end,"UTF-8")+
                    "&interval_in_minutes=1440";
            try{
                List<Candle> fallback=parseCandles(request("GET",legacy,token,null));
                if(!fallback.isEmpty())return fallback;
                throw new IOException("Daily history fallback returned no candles. Modern error: "+modernError.getMessage());
            }catch(Exception fallbackError){
                throw new IOException("Daily history failed. Modern: "+modernError.getMessage()+" | Fallback: "+fallbackError.getMessage(),fallbackError);
            }
        }
    }

    private long[] normalizeDailyBounds(long startEpoch,long endEpoch){
        Calendar s=Calendar.getInstance(IST);s.setTimeInMillis(startEpoch*1000L);
        s.set(Calendar.HOUR_OF_DAY,0);s.set(Calendar.MINUTE,0);s.set(Calendar.SECOND,0);s.set(Calendar.MILLISECOND,0);

        Calendar e=Calendar.getInstance(IST);e.setTimeInMillis(endEpoch*1000L);
        Calendar now=Calendar.getInstance(IST);
        if(e.after(now))e.setTimeInMillis(now.getTimeInMillis());

        // Daily history is most reliable on completed/closed sessions. Before 16:00 IST,
        // end at the previous calendar day to avoid requesting an unfinished daily bar.
        if(e.get(Calendar.YEAR)==now.get(Calendar.YEAR)&&e.get(Calendar.DAY_OF_YEAR)==now.get(Calendar.DAY_OF_YEAR)
                && now.get(Calendar.HOUR_OF_DAY)<16){
            e.add(Calendar.DAY_OF_YEAR,-1);
        }
        e.set(Calendar.HOUR_OF_DAY,23);e.set(Calendar.MINUTE,59);e.set(Calendar.SECOND,59);e.set(Calendar.MILLISECOND,0);

        // Groww documents a 1080-day maximum for daily candles. Keep a small margin.
        long maxSpan=1075L*86400L;
        long end=e.getTimeInMillis()/1000L;
        long start=s.getTimeInMillis()/1000L;
        if(end-start>maxSpan)start=end-maxSpan;
        if(start>=end)start=end-86400L;
        return new long[]{start,end};
    }

    private String formatIst(long epochSeconds){
        SimpleDateFormat f=new SimpleDateFormat("yyyy-MM-dd HH:mm:ss",Locale.US);
        f.setTimeZone(IST);
        return f.format(new Date(epochSeconds*1000L));
    }

    private List<Candle> parseCandles(JSONObject r)throws Exception{
        JSONObject p=r.optJSONObject("payload");
        JSONArray a=p==null?null:p.optJSONArray("candles");
        List<Candle> out=new ArrayList<>();
        if(a==null)return out;

        SimpleDateFormat iso=new SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss",Locale.US);iso.setTimeZone(IST);
        SimpleDateFormat plain=new SimpleDateFormat("yyyy-MM-dd HH:mm:ss",Locale.US);plain.setTimeZone(IST);

        for(int i=0;i<a.length();i++){
            JSONArray z=a.getJSONArray(i);long ts=0;
            Object t=z.get(0);
            if(t instanceof Number)ts=((Number)t).longValue();
            else{
                String v=String.valueOf(t);
                try{ts=iso.parse(v).getTime()/1000L;}
                catch(Exception e1){try{ts=plain.parse(v).getTime()/1000L;}catch(Exception ignored){}}
            }
            if(ts>0)out.add(new Candle(ts,z.optDouble(1),z.optDouble(2),z.optDouble(3),z.optDouble(4),z.optDouble(5)));
        }
        Collections.sort(out,(a1,b1)->Long.compare(a1.ts,b1.ts));
        return out;
    }

    public String downloadInstrumentCsv()throws Exception{
        HttpURLConnection c=(HttpURLConnection)new URL("https://growwapi-assets.groww.in/instruments/instrument.csv").openConnection();
        c.setConnectTimeout(10000);c.setReadTimeout(20000);c.setRequestProperty("Accept","text/csv");
        InputStream in=c.getInputStream();ByteArrayOutputStream bos=new ByteArrayOutputStream();byte[] b=new byte[8192];int n;
        while((n=in.read(b))!=-1)bos.write(b,0,n);
        return new String(bos.toByteArray(),StandardCharsets.UTF_8);
    }

    private JSONObject request(String method,String url,String bearer,String body)throws Exception{
        HttpURLConnection c=(HttpURLConnection)new URL(url).openConnection();
        c.setRequestMethod(method);c.setConnectTimeout(9000);c.setReadTimeout(20000);
        c.setRequestProperty("Accept","application/json");
        c.setRequestProperty("X-API-VERSION","1.0");
        c.setRequestProperty("Authorization","Bearer "+bearer);
        if(body!=null){
            c.setDoOutput(true);c.setRequestProperty("Content-Type","application/json");
            try(OutputStream os=c.getOutputStream()){os.write(body.getBytes(StandardCharsets.UTF_8));}
        }
        int code=c.getResponseCode();
        InputStream in=(code>=200&&code<300)?c.getInputStream():c.getErrorStream();
        ByteArrayOutputStream bos=new ByteArrayOutputStream();
        if(in!=null){byte[] buf=new byte[4096];int n;while((n=in.read(buf))!=-1)bos.write(buf,0,n);}
        String s=new String(bos.toByteArray(),StandardCharsets.UTF_8);
        if(code>=300)throw new IOException("HTTP "+code+": "+s);
        return new JSONObject(s);
    }
}

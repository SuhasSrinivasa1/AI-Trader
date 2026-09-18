package com.ps.shadowtrader;

import java.util.*;
import java.util.regex.*;

public class NotificationParser {
    public static class Pick { public final String symbol,raw; Pick(String s,String r){symbol=s;raw=r;} }
    private static final Pattern[] SYMBOL_PATTERNS=new Pattern[]{
            Pattern.compile("(?:NSE|STOCK|SYMBOL|SCRIP)\\s*[:\\-]\\s*([A-Z][A-Z0-9&-]{1,18})"),
            Pattern.compile("\\b([A-Z][A-Z0-9&-]{1,14})\\b")};
    private static final Set<String> STOP=new HashSet<>(Arrays.asList("BUY","SELL","NSE","BSE","INTRADAY","EQUITY","TARGET","STOPLOSS","SL","CMP","CALL","CASH","ENTRY","EXIT","MULTIFY","STOCK","SYMBOL","SCRIP","NOW","ABOVE","BELOW"));
    private static final String[] REJECT={"SWING","MULTIBAGGER","MULTI BAGGER","FUTURE","FUTURES","OPTION","OPTIONS","F&O","FNO","COMMODITY","MCX","DELIVERY","POSITIONAL","LONG TERM","LONG-TERM","INVESTMENT","CRYPTO","FOREX"};
    public Pick parse(String text){
        if(text==null)return null;String u=text.toUpperCase(Locale.ROOT);
        for(String x:REJECT)if(u.contains(x))return null;
        if(!u.contains("EQUITY")||!u.contains("INTRADAY"))return null;
        for(Pattern p:SYMBOL_PATTERNS){Matcher m=p.matcher(u);while(m.find()){String s=m.group(1);if(!STOP.contains(s)&&s.length()>=2)return new Pick(s,text);}}
        return null;
    }
}

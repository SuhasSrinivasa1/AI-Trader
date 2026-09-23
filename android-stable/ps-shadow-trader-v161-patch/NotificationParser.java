package com.ps.shadowtrader;

import java.util.*;
import java.util.regex.*;

public final class NotificationParser {
    public enum Kind { NEW_CALL, UPDATE, EXIT }
    public static final class Pick {
        public final String symbol,raw; public final Kind kind;
        Pick(String symbol,String raw,Kind kind){this.symbol=symbol;this.raw=raw;this.kind=kind;}
    }

    private static final Set<String> STOP=new HashSet<>(Arrays.asList(
            "BUY","SELL","LONG","SHORT","NSE","BSE","INTRADAY","EQUITY","TARGET","STOPLOSS","STOP","LOSS","SL","CMP",
            "CALL","CASH","ENTRY","EXIT","MULTIFY","STOCK","SYMBOL","SCRIP","NOW","ABOVE","BELOW","UPDATE","BOOK",
            "PROFIT","TRADE","TRADES","RELEASED","RELEASING","SOON","NEW","EARLY","HOLD","ALERT","PRICE","RETURNS",
            "CAPITAL","DURATION","ROCKET","WE","WERE","CHOOSING","DISCIPLINED","PLANNED","SECURING","GAINS","RIGHT",
            "TIME","STRONG","STRATEGY"
    ));

    private static final String[] REJECT={
            "SWING","MULTIBAGGER","MULTI BAGGER","FUTURE","FUTURES","OPTION","OPTIONS","F&O","FNO",
            "COMMODITY","MCX","DELIVERY","POSITIONAL","LONG TERM","LONG-TERM","INVESTMENT","CRYPTO","FOREX"
    };

    private static final Pattern BOOK_PROFIT=Pattern.compile("\\bBOOK\\s+PROFIT\\s*[:\\-]\\s*([A-Z][A-Z0-9&.-]{1,18})\\b");
    private static final Pattern SYMBOL_UPDATE=Pattern.compile("^\\s*([A-Z][A-Z0-9&.-]{1,18})\\s+UPDATE\\b");
    private static final Pattern LABELED=Pattern.compile("(?:NSE|STOCK(?:\\s+NAME)?|SYMBOL|SCRIP)\\s*[:\\-]\\s*([A-Z][A-Z0-9&.-]{1,18})\\b");
    private static final Pattern ACTION_SYMBOL=Pattern.compile("\\b(?:BUY|SELL|LONG|SHORT)\\s*[:\\-]?\\s*([A-Z][A-Z0-9&.-]{1,18})\\b");
    private static final Pattern INTRADAY_SYMBOL=Pattern.compile("\\bINTRADAY(?:\\s+EQUITY)?\\s*[:\\-]?\\s*([A-Z][A-Z0-9&.-]{1,18})\\b");
    private static final Pattern FIRST_TOKEN=Pattern.compile("^\\s*([A-Z][A-Z0-9&.-]{1,18})\\b");

    public Pick parse(String title,String body,Set<String> knownSymbols){
        String t=title==null?"":title.trim();
        String b=body==null?"":body.trim();
        String raw=(t+" "+b).trim();
        String u=raw.toUpperCase(Locale.ROOT);
        String ut=t.toUpperCase(Locale.ROOT);

        for(String x:REJECT)if(u.contains(x))return null;

        Matcher m=BOOK_PROFIT.matcher(u);
        if(m.find())return pick(m.group(1),raw,Kind.EXIT);

        m=SYMBOL_UPDATE.matcher(ut);
        if(m.find()){
            String s=m.group(1);
            return pick(s,raw,isExitText(u)?Kind.EXIT:Kind.UPDATE);
        }

        if(knownSymbols!=null){
            for(String known:knownSymbols){
                if(known==null||known.isEmpty())continue;
                String s=known.toUpperCase(Locale.ROOT);
                if(containsSymbol(u,s) && isLifecycleText(u))
                    return pick(s,raw,isExitText(u)?Kind.EXIT:Kind.UPDATE);
            }
        }

        // A fresh call remains strict: it must be an intraday call from Multify.
        if(!u.contains("INTRADAY"))return null;

        m=LABELED.matcher(u);
        while(m.find()){Pick p=safe(m.group(1),raw,Kind.NEW_CALL);if(p!=null)return p;}

        m=ACTION_SYMBOL.matcher(u);
        while(m.find()){Pick p=safe(m.group(1),raw,Kind.NEW_CALL);if(p!=null)return p;}

        m=INTRADAY_SYMBOL.matcher(u);
        while(m.find()){Pick p=safe(m.group(1),raw,Kind.NEW_CALL);if(p!=null)return p;}

        // Some Multify titles are simply "SYMBOL" or "SYMBOL Intraday". Use title only,
        // never a generic body token such as TRADE/RELEASED.
        m=FIRST_TOKEN.matcher(ut);
        if(m.find())return safe(m.group(1),raw,Kind.NEW_CALL);

        return null;
    }

    private Pick safe(String s,String raw,Kind k){
        if(s==null)return null;s=s.toUpperCase(Locale.ROOT).trim();
        if(s.length()<2||STOP.contains(s))return null;
        return new Pick(s,raw,k);
    }
    private Pick pick(String s,String raw,Kind k){return safe(s,raw,k);}

    private boolean containsSymbol(String text,String symbol){
        return Pattern.compile("(^|[^A-Z0-9&.-])"+Pattern.quote(symbol)+"([^A-Z0-9&.-]|$)").matcher(text).find();
    }
    private boolean isLifecycleText(String u){
        return u.contains("UPDATE")||u.contains("BOOK PROFIT")||u.contains("TARGET")||u.contains("STOP LOSS")||
                u.contains("STOPLOSS")||u.contains("SL HIT")||u.contains("EXIT")||u.contains("EARLY EXIT")||
                u.contains("SECURING GAINS")||u.contains("HOLD")||u.contains("TRAIL");
    }
    private boolean isExitText(String u){
        return u.contains("BOOK PROFIT")||u.contains("EARLY EXIT")||u.contains("EXIT PRICE")||u.contains("EXIT AGAINST")||
                u.contains("SECURING GAINS")||u.contains("TARGET HIT")||u.contains("STOP LOSS HIT")||
                u.contains("STOPLOSS HIT")||u.contains("SL HIT")||u.contains("CLOSE POSITION");
    }
}

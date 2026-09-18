package com.ps.shadowtrader;

import android.content.*;
import java.io.*;
import java.util.*;

public final class UniverseRepository {
    private static final String CACHE="nse_equity_universe.txt";
    public static List<String> load(Context c,GrowwClient api)throws Exception{
        File f=new File(c.getFilesDir(),CACHE);long age=System.currentTimeMillis()-f.lastModified();
        if(!f.exists()||age>24L*3600L*1000L){
            String csv=api.downloadInstrumentCsv();List<String> symbols=parse(csv);
            try(PrintWriter w=new PrintWriter(new OutputStreamWriter(new FileOutputStream(f),"UTF-8"))){for(String s:symbols)w.println(s);}
        }
        List<String> out=new ArrayList<>();try(BufferedReader r=new BufferedReader(new InputStreamReader(new FileInputStream(f),"UTF-8"))){String s;while((s=r.readLine())!=null){s=s.trim();if(!s.isEmpty())out.add(s);}}
        return out;
    }
    static List<String> parse(String csv){
        ArrayList<String> out=new ArrayList<>();if(csv==null||csv.isEmpty())return out;String[] lines=csv.split("\\r?\\n");if(lines.length<2)return out;
        List<String> h=row(lines[0]);Map<String,Integer> m=new HashMap<>();for(int i=0;i<h.size();i++)m.put(h.get(i).trim().toLowerCase(Locale.ROOT),i);
        for(int i=1;i<lines.length;i++){
            List<String> r=row(lines[i]);String ex=get(r,m,"exchange"),seg=get(r,m,"segment"),type=get(r,m,"instrument_type"),series=get(r,m,"series"),sym=get(r,m,"trading_symbol"),buy=get(r,m,"buy_allowed"),sell=get(r,m,"sell_allowed"),reserved=get(r,m,"is_reserved");
            if(!"NSE".equalsIgnoreCase(ex)||!"CASH".equalsIgnoreCase(seg)||!"EQ".equalsIgnoreCase(type)||!"EQ".equalsIgnoreCase(series))continue;
            if(!truthy(buy)||!truthy(sell)||truthy(reserved)||sym.isEmpty())continue;out.add(sym);
        }
        Collections.sort(out);return out;
    }
    private static String get(List<String> r,Map<String,Integer> m,String k){Integer i=m.get(k);return i==null||i<0||i>=r.size()?"":r.get(i).trim();}
    private static boolean truthy(String s){return "1".equals(s)||"true".equalsIgnoreCase(s)||"yes".equalsIgnoreCase(s);}
    private static List<String> row(String line){ArrayList<String> r=new ArrayList<>();StringBuilder b=new StringBuilder();boolean q=false;for(int i=0;i<line.length();i++){char ch=line.charAt(i);if(ch=='\"'){if(q&&i+1<line.length()&&line.charAt(i+1)=='\"'){b.append('\"');i++;}else q=!q;}else if(ch==','&&!q){r.add(b.toString());b.setLength(0);}else b.append(ch);}r.add(b.toString());return r;}
}

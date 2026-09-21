package com.ps.shadowtrader;

import android.content.*;
import java.io.*;
import java.util.*;

public final class InstrumentMetadataRepository {
    private static final String FILE="nse_sector_map.txt";

    public static Map<String,String> sectors(Context c,GrowwClient api)throws Exception{
        File f=new File(c.getFilesDir(),FILE);
        if(!f.exists()||System.currentTimeMillis()-f.lastModified()>24L*3600000L){
            String csv=api.downloadInstrumentCsv();
            Map<String,String> m=parse(csv);
            try(PrintWriter w=new PrintWriter(new OutputStreamWriter(new FileOutputStream(f),"UTF-8"))){
                for(Map.Entry<String,String>e:m.entrySet())w.println(e.getKey()+"|"+e.getValue().replace("|","/"));
            }
        }
        LinkedHashMap<String,String> out=new LinkedHashMap<>();
        if(f.exists())try(BufferedReader r=new BufferedReader(new InputStreamReader(new FileInputStream(f),"UTF-8"))){
            String s;while((s=r.readLine())!=null){int k=s.indexOf('|');if(k>0)out.put(s.substring(0,k),s.substring(k+1));}
        }
        return out;
    }

    static Map<String,String> parse(String csv){
        LinkedHashMap<String,String> out=new LinkedHashMap<>();
        if(csv==null||csv.isEmpty())return out;
        String[] lines=csv.split("\r?\n");if(lines.length<2)return out;
        List<String> h=row(lines[0]);Map<String,Integer> m=new HashMap<>();
        for(int i=0;i<h.size();i++)m.put(h.get(i).trim().toLowerCase(Locale.ROOT),i);
        Integer sectorIndex=first(m,"sector","industry","sector_name","industry_name");
        Integer symbolIndex=first(m,"trading_symbol","groww_symbol","symbol");
        if(symbolIndex==null)return out;
        for(int i=1;i<lines.length;i++){
            List<String> r=row(lines[i]);if(symbolIndex>=r.size())continue;
            String sym=r.get(symbolIndex).trim();if(sym.startsWith("NSE-"))sym=sym.substring(4);
            String sector=(sectorIndex!=null&&sectorIndex<r.size())?r.get(sectorIndex).trim():"UNKNOWN";
            if(!sym.isEmpty())out.put(sym,sector.isEmpty()?"UNKNOWN":sector);
        }
        return out;
    }
    private static Integer first(Map<String,Integer>m,String...keys){for(String k:keys)if(m.containsKey(k))return m.get(k);return null;}
    private static List<String> row(String line){ArrayList<String> r=new ArrayList<>();StringBuilder b=new StringBuilder();boolean q=false;for(int i=0;i<line.length();i++){char ch=line.charAt(i);if(ch=='"'){if(q&&i+1<line.length()&&line.charAt(i+1)=='"'){b.append('"');i++;}else q=!q;}else if(ch==','&&!q){r.add(b.toString());b.setLength(0);}else b.append(ch);}r.add(b.toString());return r;}
}

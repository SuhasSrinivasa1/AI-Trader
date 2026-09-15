#!/usr/bin/env python3
import csv, io, json, sys, urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SEED=ROOT/'global-lead-mappings-v1.json'
RULES=Path(__file__).with_name('proxy_rules.json')
OUT=ROOT/'global-lead-mappings-v2.json'
URL='https://nsearchives.nseindia.com/content/indices/ind_nifty500list.csv'
ALIASES={'Oil, Gas & Consumable Fuels':'Oil Gas & Consumable Fuels','Media, Entertainment & Publication':'Media Entertainment & Publication'}

def get_csv():
    req=urllib.request.Request(URL,headers={'User-Agent':'Mozilla/5.0','Accept':'text/csv,*/*'})
    with urllib.request.urlopen(req,timeout=30) as r: text=r.read().decode('utf-8-sig',errors='replace')
    if text.count('\n')<300 or 'Company Name' not in text: raise RuntimeError('Nifty 500 constituent download is incomplete')
    return text

def main():
    seed=json.loads(SEED.read_text())['mappings']; rules=json.loads(RULES.read_text()); rows=list(csv.DictReader(io.StringIO(get_csv())))
    out=[]; seen=set()
    for m in seed:
        m=dict(m); k=(m['indianSymbol'].upper(),m['foreignTicker'].upper()); seen.add(k); out.append(m)
    for r in rows:
        symbol=(r.get('Symbol') or '').strip().upper(); series=(r.get('Series') or '').strip().upper()
        if not symbol or symbol.startswith('DUMMY') or series not in {'EQ','BE','BZ'}: continue
        industry=' '.join((r.get('Industry') or '').split()); industry=ALIASES.get(industry,industry)
        for ticker,name,exchange,region,benchmark,weight in rules.get(industry,rules['__default__']):
            k=(symbol,ticker.upper())
            if k in seen: continue
            seen.add(k)
            out.append({'indianSymbol':symbol,'indianCompany':(r.get('Company Name') or symbol).strip(),'foreignTicker':ticker,'foreignCompany':name,'exchange':exchange,'region':region,'benchmarkTicker':benchmark,'mappingType':'FRANCHISE_PROXY','relationshipWeight':weight,'officialSource':URL,'notes':'Weekly global proxy; not the same company. Indian confirmation required.'})
    symbols={m['indianSymbol'] for m in out}; feeds={m['foreignTicker'] for m in out}
    if len(symbols)<350 or len(out)<800: raise RuntimeError(f'Coverage too small: {len(symbols)} stocks / {len(out)} links')
    now=datetime.now(timezone.utc); obj={'version':f"GLM-{now:%Y.%m.%d}-WEEKLY",'generatedAt':now.isoformat(),'coverage':{'indianStocks':len(symbols),'mappingLinks':len(out),'uniqueForeignFeeds':len(feeds),'seedDirectLinks':len(seed)},'mappings':out}
    OUT.write_text(json.dumps(obj,indent=2,ensure_ascii=False)+'\n'); print(json.dumps(obj['coverage'],sort_keys=True))
if __name__=='__main__': main()

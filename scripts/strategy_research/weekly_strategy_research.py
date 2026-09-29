#!/usr/bin/env python3
import datetime as dt, json, os, re, urllib.parse, urllib.request, xml.etree.ElementTree as ET

ROOT=os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CAT=os.path.join(ROOT,"android-stable","strategy-catalog-v2.json")
REPORT=os.path.join(ROOT,"android-stable","strategy-research-latest.json")
TOKEN=os.environ.get("GITHUB_TOKEN","")
UA={"User-Agent":"Global-Quant-Trader-Weekly-Research/2.2"}

QUERIES={
 "ARBITRAGE":[
  "cash futures arbitrage trading strategy fair value basis",
  "put call parity conversion reversal arbitrage strategy",
  "futures calendar spread statistical arbitrage strategy",
  "options relative value box spread arbitrage research"
 ],
 "HEDGING":[
  "dynamic hedging strategy delta hedge portfolio drawdown",
  "protective put collar hedge optimization strategy",
  "index futures hedge ratio portfolio beta optimization",
  "options tail risk hedging strategy research"
 ],
 "DIRECTIONAL_FNO":[
  "futures open interest price momentum trading strategy",
  "options implied volatility skew directional trading strategy",
  "VWAP relative volume futures breakout trading strategy",
  "order flow market depth futures trading strategy",
  "news sentiment event driven options trading strategy",
  "global markets overnight lead Indian market trading strategy"
 ]
}

KIND_RULES=[
 (r"\bopening range\b|\borb\b","ORB_RVOL"),
 (r"\bvwap\b.{0,30}\breclaim\b|\breclaim\b.{0,30}\bvwap\b","VWAP_RECLAIM"),
 (r"\bvwap\b.{0,30}\bpullback\b|\bpullback\b.{0,30}\bvwap\b","VWAP_PULLBACK"),
 (r"\bbollinger\b|\bvolatility squeeze\b","BOLL_SQUEEZE"),
 (r"\bdonchian\b","DONCHIAN"),
 (r"\b(?:ema|exponential moving average)\b.{0,35}\b(?:cross|crossover)\b","EMA_CROSS"),
 (r"\btrend\b.{0,25}\bpullback\b|\bpullback\b.{0,25}\btrend\b","TREND_PULLBACK"),
 (r"\bmacd\b","MACD"),
 (r"\brsi\s*\(?2\)?\b","RSI2_TREND"),
 (r"\brsi\b|\brelative strength index\b","RSI14_REVERSAL"),
 (r"\bstochastic oscillator\b|\bstochastic reversal\b","STOCH_REVERSAL"),
 (r"\binside[- ]bar\b","INSIDE_BAR"),
 (r"\bengulf(?:ing)?\b","ENGULFING"),
 (r"\bhammer candl|\bshooting star candl","HAMMER"),
 (r"\bmorning star\b|\bevening star\b","MORNING_STAR"),
 (r"\bthree white soldiers\b|\bthree black crows\b","THREE_SOLDIERS"),
 (r"\bgap[- ]and[- ]go\b|\bgap continuation\b","GAP_GO"),
 (r"\bnr7\b|\bnarrow range 7\b","NR7_EXPANSION"),
 (r"\bvolume breakout\b|\brelative volume\b.{0,30}\bbreakout\b|\brvol\b.{0,30}\bbreakout\b","VOLUME_BREAKOUT"),
 (r"\batr\b.{0,30}\bbreakout\b|\baverage true range\b.{0,30}\bbreakout\b","ATR_BREAKOUT"),
 (r"\bsupport (?:and|&|/) resistance\b|\bsupport level\b.{0,30}\bresistance level\b|\bresistance level\b.{0,30}\bsupport level\b","SUPPORT_RESISTANCE"),
 (r"\badx\b|\baverage directional index\b","ADX_TREND"),
]

def get(url,headers=None,timeout=20):
    h=dict(UA); h.update(headers or {})
    req=urllib.request.Request(url,headers=h)
    with urllib.request.urlopen(req,timeout=timeout) as r:
        return r.read().decode("utf-8","replace")

def clean(s):
    return re.sub(r"\s+"," ",re.sub(r"<[^>]+>"," ",s or "")).strip()

def bing(engine,q):
    url="https://www.bing.com/search?format=rss&q="+urllib.parse.quote(q)
    out=[]
    try:
        root=ET.fromstring(get(url))
        for item in root.findall(".//item")[:8]:
            out.append({"engine":engine,"source":"web_search","query":q,
                        "title":clean(item.findtext("title")),"url":clean(item.findtext("link")),
                        "summary":clean(item.findtext("description"))})
    except Exception as e:
        out.append({"engine":engine,"source":"web_search_error","query":q,"title":str(e),"url":"","summary":""})
    return out

def arxiv():
    q='all:"algorithmic trading" OR all:"statistical arbitrage" OR all:"options hedging" OR all:"market microstructure"'
    url="https://export.arxiv.org/api/query?search_query="+urllib.parse.quote(q)+"&start=0&max_results=20&sortBy=submittedDate&sortOrder=descending"
    out=[]
    try:
        root=ET.fromstring(get(url))
        ns={"a":"http://www.w3.org/2005/Atom"}
        for e in root.findall("a:entry",ns):
            t=clean(e.findtext("a:title",default="",namespaces=ns))
            summ=clean(e.findtext("a:summary",default="",namespaces=ns))
            link=clean(e.findtext("a:id",default="",namespaces=ns))
            low=(t+" "+summ).lower()
            engine="HEDGING" if "hedg" in low else ("ARBITRAGE" if "arbitrage" in low or "relative value" in low else "DIRECTIONAL_FNO")
            out.append({"engine":engine,"source":"arxiv","query":"quant research","title":t,"url":link,"summary":summ})
    except Exception as e:
        out.append({"engine":"RESEARCH","source":"arxiv_error","query":"quant research","title":str(e),"url":"","summary":""})
    return out

def github_search():
    queries=["quant trading strategy futures options","statistical arbitrage options","dynamic hedging options","order flow trading strategy"]
    out=[]
    for q in queries:
        try:
            headers={"Accept":"application/vnd.github+json"}
            if TOKEN: headers["Authorization"]="Bearer "+TOKEN
            url="https://api.github.com/search/repositories?q="+urllib.parse.quote(q)+"&sort=updated&order=desc&per_page=8"
            data=json.loads(get(url,headers))
            for x in data.get("items",[]):
                text=(x.get("name","")+" "+(x.get("description") or "")).lower()
                engine="HEDGING" if "hedg" in text else ("ARBITRAGE" if "arbitrage" in text else "DIRECTIONAL_FNO")
                out.append({"engine":engine,"source":"github","query":q,"title":x.get("full_name",""),
                            "url":x.get("html_url",""),"summary":clean(x.get("description") or "")})
        except Exception as e:
            out.append({"engine":"RESEARCH","source":"github_error","query":q,"title":str(e),"url":"","summary":""})
    return out

def dedupe(items):
    seen=set(); out=[]
    for x in items:
        key=(x.get("url") or x.get("title","")).lower().strip()
        if not key or key in seen: continue
        seen.add(key); out.append(x)
    return out

def supported_kind(item):
    text=(item.get("title","")+" "+item.get("summary","")).lower()
    reject=r"\bkalshi\b|\bpolymarket\b|\belectricity market\b|\benergy market\b|\bsports betting\b|\bprediction market\b"
    if re.search(reject,text): return None
    context=r"\btrading\b|\btrader\b|\bstock\b|\bequity\b|\bfutures?\b|\boptions?\b|\btechnical analysis\b|\bprice action\b|\bmarket price\b"
    if not re.search(context,text): return None
    for pat,kind in KIND_RULES:
        if re.search(pat,text): return kind
    return None

def slug(s):
    s=re.sub(r"[^a-z0-9]+","_",s.lower()).strip("_")
    return s[:36] or "candidate"

def main():
    with open(CAT,encoding="utf-8") as f: cat=json.load(f)
    findings=[]
    for engine,qs in QUERIES.items():
        for q in qs: findings.extend(bing(engine,q))
    findings.extend(arxiv())
    findings.extend(github_search())
    findings=dedupe(findings)

    today=dt.datetime.now(dt.timezone.utc).date().isoformat()
    candidates=[]
    for x in findings:
        k=supported_kind(x)
        x["supported_kind"]=k
        x["disposition"]="challenger_shadow" if (x["engine"]=="DIRECTIONAL_FNO" and k) else "research_only"
        if x["disposition"]=="challenger_shadow" and len(candidates)<16:
            candidates.append({
                "id":"web_"+slug(x["title"])+"_"+str(len(candidates)+1),
                "name":"Web Challenger: "+x["title"][:90],
                "kind":k,
                "family":"Weekly Web Research",
                "description":("Discovered via weekly broad-web research; encoded using supported "+k+
                               ". Must earn promotion through shadow evidence; source: "+x["url"])[:600],
                "source":x["url"] or x["source"],
                "priority":60
            })

    base=[x for x in cat.get("strategies",[]) if not str(x.get("id","")).startswith("web_")]
    cat["strategies"]=base+candidates
    cat["version"]="STRAT-WEB-"+today
    cat["research"]={
        "mode":"broad_web_weekly",
        "last_research_at":dt.datetime.now(dt.timezone.utc).isoformat(),
        "finding_count":len(findings),
        "challenger_count":len(candidates),
        "engine_counts":{e:sum(1 for x in findings if x.get("engine")==e) for e in ["ARBITRAGE","HEDGING","DIRECTIONAL_FNO"]},
        "policy":"Discovery never promotes directly. Supported encodings enter Challenger shadow tests; unsupported or vague ideas remain research-only. Existing Champions remain until evidence-based demotion."
    }
    with open(CAT,"w",encoding="utf-8") as f: json.dump(cat,f,indent=2,ensure_ascii=False); f.write("\n")
    with open(REPORT,"w",encoding="utf-8") as f:
        json.dump({"generated_at":dt.datetime.now(dt.timezone.utc).isoformat(),"findings":findings},f,indent=2,ensure_ascii=False); f.write("\n")
    print(json.dumps(cat["research"],indent=2))

if __name__=="__main__":
    main()

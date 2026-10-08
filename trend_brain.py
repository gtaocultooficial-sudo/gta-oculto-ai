import json, math, os, re, time, threading
from pathlib import Path

class TrendBrain:
    """V57 editorial memory. It ranks radar topics and learns from YouTube Analytics."""
    def __init__(self, workspace=None):
        self.root=Path(workspace or os.getenv("GTA_WORKSPACE","workspace"))
        self.root.mkdir(parents=True, exist_ok=True)
        self.path=self.root/"trend_brain.json"
        self.lock=threading.RLock()
        if not self.path.exists():
            self._write({"topics":{},"videos":{},"patterns":{}})

    def _read(self):
        try: return json.loads(self.path.read_text(encoding="utf-8"))
        except Exception: return {"topics":{},"videos":{},"patterns":{}}

    def _write(self,d):
        tmp=self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding="utf-8")
        os.replace(tmp,self.path)

    def _key(self,t):
        words=re.findall(r"[a-z0-9áéíóúãõç]+",str(t.get("title","")).lower())
        return " ".join([w for w in words if len(w)>3][:10]) or str(t.get("id","unknown"))

    def observe(self,topics):
        with self.lock:
            d=self._read()
            for t in topics or []:
                k=self._key(t); x=d["topics"].setdefault(k,{"seen":0,"best":0})
                x["seen"]+=1; x["best"]=max(x["best"],float(t.get("score",0) or 0))
            self._write(d)

    def rank(self,topics):
        topics=[dict(t) for t in (topics or [])]
        if not topics: return topics
        self.observe(topics)
        d=self._read()
        ranked=[]
        for t in topics:
            mem=d["topics"].get(self._key(t),{})
            base=float(t.get("score",0) or 0)
            conf=float(t.get("confidence",70) or 70)
            mentions=float(t.get("mentions",1) or 1)
            seen=float(mem.get("seen",1) or 1)
            novelty=100 if seen<=1 else max(25,100-(seen-1)*10)
            demand=min(100,base*.55+mentions*10)
            history=0
            for v in d["videos"].values():
                if v.get("topic_key")==self._key(t):
                    history=max(history,float(v.get("performance_score",0) or 0))
            score=base*.42+conf*.14+demand*.18+novelty*.10+history*.16
            t["trend_score"]=int(max(0,min(100,round(score))))
            t["trend_signal"]="FORTE" if t["trend_score"]>=78 else ("MÉDIO" if t["trend_score"]>=60 else "FRACO")
            t["trend_reason"]=f"Radar {int(base)}/100; demanda {int(demand)}; novidade {int(novelty)}; histórico {int(history)}."
            ranked.append(t)
        return sorted(ranked,key=lambda x:(x.get("trend_score",0),x.get("score",0)),reverse=True)

    def learn(self,result,publications=None):
        if not result or not result.get("ok"): return result or {"ok":False}
        headers=[str(x.get("name","")).lower() for x in result.get("headers",[])]
        rows=result.get("rows",[]) or []
        def ix(n):
            try:return headers.index(n)
            except ValueError:return -1
        vi,vw,vl,vs=ix("video"),ix("views"),ix("likes"),ix("subscribersgained")
        with self.lock:
            d=self._read()
            pubs=publications or {}
            for row in rows:
                if vi<0 or vi>=len(row): continue
                vid=str(row[vi]); views=float(row[vw] or 0) if 0<=vw<len(row) else 0
                likes=float(row[vl] or 0) if 0<=vl<len(row) else 0
                subs=float(row[vs] or 0) if 0<=vs<len(row) else 0
                like_rate=(likes/views*100) if views else 0
                perf=min(100,math.log10(max(1,views))*18+min(20,like_rate*4)+min(15,subs*3))
                p=pubs.get(vid,{})
                d["videos"][vid]={"topic_key":p.get("topic_key",""),"performance_score":round(perf,2),"views":views,"likes":likes,"subscribers":subs,"updated":time.time()}
            d["videos"]=dict(list(d["videos"].items())[-500:])
            self._write(d)
        return {"ok":True,"videos_learned":len(rows)}

    def status(self):
        d=self._read()
        return {"version":"V57","topics_seen":len(d["topics"]),"videos_tracked":len(d["videos"])}

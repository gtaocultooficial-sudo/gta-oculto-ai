import json, math, os, re, time, threading
from pathlib import Path

class TrendBrain:
    """V58 editorial memory. It ranks radar topics and learns from YouTube Analytics."""
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

    def _fingerprint(self,t):
        words=re.findall(r"[a-z0-9áéíóúãõç]+",str(t.get("title","")).lower())
        stop={"gta","gta6","gtaiv","rockstar","games","novo","jogo","detalhes","confirmou","confirmados"}
        core=[w for w in words if len(w)>3 and w not in stop]
        return " ".join(sorted(core[:14]))

    def _repetition_penalty(self,t,d):
        key=self._key(t); fp=self._fingerprint(t); now=time.time(); penalty=0
        for v in d.get("videos",{}).values():
            age_days=(now-float(v.get("updated",now) or now))/86400
            if age_days>14: continue
            if v.get("topic_key")==key:
                penalty=max(penalty,35 if age_days<3 else 20)
            oldfp=str(v.get("fingerprint",""))
            if fp and oldfp and fp==oldfp:
                penalty=max(penalty,45 if age_days<7 else 25)
        return penalty

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
            repetition=self._repetition_penalty(t,d)
            score=base*.42+conf*.14+demand*.18+novelty*.10+history*.16-repetition
            t["trend_score"]=int(max(0,min(100,round(score))))
            t["repetition_penalty"]=repetition
            t["trend_signal"]="FORTE" if t["trend_score"]>=78 else ("MÉDIO" if t["trend_score"]>=60 else "FRACO")
            t["trend_reason"]=f"Radar {int(base)}/100; demanda {int(demand)}; novidade {int(novelty)}; histórico {int(history)}; repetição -{int(repetition)}."
            ranked.append(t)
        return sorted(ranked,key=lambda x:(x.get("trend_score",0),x.get("score",0)),reverse=True)

    def record_publication(self, topic, metadata=None, video_id=None):
        if not video_id:
            return
        with self.lock:
            d=self._read()
            k=self._key(topic or {})
            old=d["videos"].get(str(video_id),{})
            d["videos"][str(video_id)]={"topic_key":k,"title":str((topic or {}).get("title","")),"hook":str((topic or {}).get("editorial_hook","")),"angle":str((topic or {}).get("editorial_angle","")),"performance_score":old.get("performance_score",0),"updated":time.time()}
            self._write(d)

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
                d["videos"][vid]={"topic_key":p.get("topic_key",d["videos"].get(vid,{}).get("topic_key","")),"performance_score":round(perf,2),"views":views,"likes":likes,"subscribers":subs,"updated":time.time()}
            d["videos"]=dict(list(d["videos"].items())[-500:])
            self._write(d)
        return {"ok":True,"videos_learned":len(rows)}

    def record_production(self, topic, metadata=None, quality=0):
        """Store editorial quality before publication so the brain can learn even without platform APIs."""
        with self.lock:
            d=self._read(); k=self._key(topic or {})
            x=d["topics"].setdefault(k,{"seen":0,"best":0})
            x["productions"]=int(x.get("productions",0))+1
            x["quality_sum"]=float(x.get("quality_sum",0))+float(quality or 0)
            x["last_quality"]=float(quality or 0)
            if metadata:
                x["last_title"]=str(metadata.get("title",""))
                x["last_hook"]=str(metadata.get("hook",metadata.get("editorial_hook","")))
                fp=self._fingerprint({"title":metadata.get("title","")})
                if fp:
                    d.setdefault("videos",{})[f"production:{int(time.time()*1000)}"]={
                        "topic_key":k,"fingerprint":fp,"performance_score":float(quality or 0),"updated":time.time()
                    }
            self._write(d)

    def recommend_publish_slot(self, now=None):
        """Free baseline scheduler: choose a strong BR publishing window, then learn later from slot metrics."""
        from datetime import datetime
        n=now or datetime.now()
        slots=[(12,30),(18,30),(20,30),(22,0)]
        # Prefer evening for GTA audience; once slot scores exist, use learned winners.
        d=self._read(); scores=d.get("patterns",{}).get("publish_slots",{})
        if scores:
            best=max(scores.items(), key=lambda kv:float(kv[1]))[0]
            h,m=map(int,best.split(':')); return {"time":best,"reason":"aprendido","timezone":"America/Sao_Paulo"}
        h,m=min(slots,key=lambda x:abs((x[0]*60+x[1])-(n.hour*60+n.minute)))
        return {"time":f"{h:02d}:{m:02d}","reason":"baseline","timezone":"America/Sao_Paulo"}

    def record_slot_performance(self, slot, score):
        if not slot: return
        with self.lock:
            d=self._read(); p=d.setdefault("patterns",{}).setdefault("publish_slots",{})
            old=p.get(slot,{"sum":0,"n":0}) if isinstance(p.get(slot),dict) else {"sum":0,"n":0}
            old["sum"]+=float(score or 0); old["n"]+=1; p[slot]=old["sum"]/old["n"]
            self._write(d)

    def status(self):
        d=self._read()
        return {"version":"V58","topics_seen":len(d["topics"]),"videos_tracked":len(d["videos"])}

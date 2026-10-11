import json, math, os, re, time, threading
from pathlib import Path

class TrendBrain:
    """V59 editorial memory. It ranks radar topics and learns from YouTube Analytics."""
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

    def tracked_video_ids(self):
        """Return published YouTube IDs already associated with the editorial memory."""
        with self.lock:
            d=self._read()
            return [str(k) for k,v in d.get("videos",{}).items()
                    if not str(k).startswith("production:") and str(k).strip() and
                    str(v.get("title","") or "").strip()]

    def record_publication(self, topic, metadata=None, video_id=None, publish_slot=None):
        if not video_id:
            return
        with self.lock:
            d=self._read()
            k=self._key(topic or {})
            old=d["videos"].get(str(video_id),{})
            hook=str((metadata or {}).get("hook",(topic or {}).get("editorial_hook","")) or "")
            d["videos"][str(video_id)]={"topic_key":k,"title":str((topic or {}).get("title","")),"hook":hook,"hook_type":self._hook_type(hook),"content_type":str((topic or {}).get("content_type","CURIOSIDADE") or "CURIOSIDADE").upper(),"angle":str((metadata or {}).get("editorial_angle",(topic or {}).get("editorial_angle","")) or ""),"duration_bucket":self._duration_bucket((metadata or {}).get("duration_seconds",0)),"performance_score":old.get("performance_score",0),"publish_slot":str(publish_slot or old.get("publish_slot","")),"updated":time.time()}
            self._write(d)

    def learn(self,result,publications=None):
        if not result or not result.get("ok"): return result or {"ok":False}
        headers=[str(x.get("name","")).lower() for x in result.get("headers",[])]
        rows=result.get("rows",[]) or []
        def ix(n):
            try:return headers.index(n)
            except ValueError:return -1
        vi,vw,vl,vs,vd,vm=ix("video"),ix("views"),ix("likes"),ix("subscribersgained"),ix("averageviewduration"),ix("estimatedminuteswatched")
        with self.lock:
            d=self._read()
            pubs=publications or {}
            for row in rows:
                if vi<0 or vi>=len(row): continue
                vid=str(row[vi]); views=float(row[vw] or 0) if 0<=vw<len(row) else 0
                likes=float(row[vl] or 0) if 0<=vl<len(row) else 0
                subs=float(row[vs] or 0) if 0<=vs<len(row) else 0
                avg_duration=float(row[vd] or 0) if 0<=vd<len(row) else 0
                watched_minutes=float(row[vm] or 0) if 0<=vm<len(row) else 0
                like_rate=(likes/views*100) if views else 0
                # Retention matters more than raw views for Shorts. Use bounded Analytics signals.
                retention_signal=min(30,avg_duration*2.0)
                watch_signal=min(15,math.log10(max(1,watched_minutes+1))*5)
                engagement=min(20,like_rate*4)
                subscriber_signal=min(15,subs*3)
                view_signal=min(40,math.log10(max(1,views))*10)
                perf=min(100,view_signal+retention_signal+watch_signal+engagement+subscriber_signal)
                p=pubs.get(vid,{})
                existing=d["videos"].get(vid,{})
                d["videos"][vid]={"topic_key":p.get("topic_key",existing.get("topic_key","")),"title":existing.get("title",p.get("title","")),"hook":existing.get("hook",p.get("hook","")),"angle":existing.get("angle",p.get("angle","")),"fingerprint":existing.get("fingerprint",""),"duration_bucket":existing.get("duration_bucket",p.get("duration_bucket","")),"hook_type":existing.get("hook_type",self._hook_type(existing.get("hook",""))),"content_type":existing.get("content_type",p.get("content_type","CURIOSIDADE")),"publish_slot":existing.get("publish_slot",p.get("publish_slot","")),"performance_score":round(perf,2),"views":views,"likes":likes,"subscribers":subs,"average_view_duration":avg_duration,"estimated_minutes_watched":watched_minutes,"like_rate":round(like_rate,3),"updated":time.time()}
                slot=existing.get("publish_slot",p.get("publish_slot",""))
                if slot:
                    sp=d.setdefault("patterns",{}).setdefault("publish_slots",{})
                    oldslot=sp.get(slot,{"sum":0,"n":0}) if isinstance(sp.get(slot),dict) else {"sum":0,"n":0}
                    oldslot["sum"]+=float(perf); oldslot["n"]+=1
                    sp[slot]=round(oldslot["sum"]/max(1,oldslot["n"]),2)
            d["videos"]=dict(list(d["videos"].items())[-500:])
            self._write(d)
        return {"ok":True,"videos_learned":len(rows)}

    @staticmethod
    def _hook_type(hook):
        h=str(hook or "").lower()
        if "confirm" in h or "revelou" in h: return "CONFIRMACAO"
        if "rumor" in h or "não foi confirmado" in h: return "RUMOR"
        if "detalhe" in h or "pista" in h: return "DETALHE"
        if "percebeu" in h or "vale a pena ver" in h: return "CURIOSIDADE"
        return "OUTRO"

    @staticmethod
    def _duration_bucket(seconds):
        s=float(seconds or 0)
        if s <= 0: return "UNKNOWN"
        if s < 30: return "24-29s"
        # Learn only inside the range that the current evaluator considers healthy.
        # Sub-24s and 39s+ outputs are treated as unsupported for editorial learning.
        if s < 39: return "30-38s"
        return "UNSUPPORTED"

    def recommend_editorial_profile(self):
        d=self._read()
        rows=[v for v in d.get("videos",{}).values() if float(v.get("performance_score",0) or 0)>0 and v.get("hook_type")]
        if len(rows)<3: return {"learned":False,"sample_size":len(rows)}
        stats={}
        type_stats={}
        for v in rows:
            k=str(v.get("hook_type"))
            if k!="OUTRO":
                x=stats.setdefault(k,{"sum":0.0,"n":0}); x["sum"]+=float(v.get("performance_score",0) or 0); x["n"]+=1
            ct=str(v.get("content_type","CURIOSIDADE") or "CURIOSIDADE").upper()
            x2=type_stats.setdefault(ct,{"sum":0.0,"n":0}); x2["sum"]+=float(v.get("performance_score",0) or 0); x2["n"]+=1
        eligible={k:v for k,v in stats.items() if v["n"]>=2}
        type_eligible={k:v for k,v in type_stats.items() if v["n"]>=2}
        if not eligible: return {"learned":False,"sample_size":len(rows)}
        k,v=max(eligible.items(),key=lambda kv:kv[1]["sum"]/kv[1]["n"])
        duration_stats={}
        for row in rows:
            b=str(row.get("duration_bucket",""))
            if b not in ("24-29s","30-38s"): continue
            x=duration_stats.setdefault(b,{"sum":0.0,"n":0}); x["sum"]+=float(row.get("performance_score",0) or 0); x["n"]+=1
        duration_eligible={a:b for a,b in duration_stats.items() if b["n"]>=2}
        preferred_duration=None
        if duration_eligible:
            dk,dv=max(duration_eligible.items(),key=lambda kv:kv[1]["sum"]/kv[1]["n"])
            preferred_duration={"bucket":dk,"score":round(dv["sum"]/dv["n"],2),"samples":dv["n"]}
        by_style={a:round(b["sum"]/b["n"],2) for a,b in stats.items()}
        best_score=round(v["sum"]/v["n"],2)
        # Keep the learning signal conservative: it only influences editorial
        # ranking after at least two videos of the same hook style exist.
        preferred_content_type=None
        if type_eligible:
            ck,cv=max(type_eligible.items(),key=lambda kv:kv[1]["sum"]/kv[1]["n"])
            preferred_content_type={"type":ck,"score":round(cv["sum"]/cv["n"],2),"samples":cv["n"]}
        return {"learned":True,"preferred_hook_type":k,"score":best_score,
                "sample_size":len(rows),"by_style":by_style,
                "preferred_content_type":preferred_content_type,
                "by_content_type":{a:round(b["sum"]/b["n"],2) for a,b in type_stats.items()},
                "preferred_duration":preferred_duration,
                "confidence":min(1.0, max(0.0, (v["n"]-1)/4.0))}

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
        """Reserve the next strong publishing window in Brazil time; learn from performance over time."""
        from datetime import datetime, timedelta
        from zoneinfo import ZoneInfo
        tz=ZoneInfo("America/Sao_Paulo")
        n=now or datetime.now(tz)
        if n.tzinfo is None:
            n=n.replace(tzinfo=tz)
        else:
            n=n.astimezone(tz)
        base_slots=[("12:30",62),("18:30",100),("20:30",96),("22:00",68)]
        d=self._read()
        learned=d.get("patterns",{}).get("publish_slots",{})
        reserved=d.setdefault("scheduled_slots",{})
        # Drop old reservations so failed jobs cannot block the calendar forever.
        cutoff=(n-timedelta(hours=2)).isoformat()
        reserved={k:v for k,v in reserved.items() if k>cutoff}
        d["scheduled_slots"]=reserved
        candidates=[]
        for day_offset in range(0,8):
            day=(n+timedelta(days=day_offset)).date()
            for slot,baseline in base_slots:
                hh,mm=map(int,slot.split(":"))
                dt=datetime(day.year,day.month,day.day,hh,mm,tzinfo=tz)
                if dt <= n+timedelta(minutes=30):
                    continue
                if dt.isoformat() in reserved:
                    continue
                # Learned score is used when available; otherwise use the GTA-friendly baseline.
                learned_score=learned.get(slot)
                score=float(learned_score) if learned_score is not None else float(baseline)
                score-=day_offset*12  # favor the strongest available slot without waiting needlessly
                candidates.append((score,dt,slot,"aprendido" if learned_score is not None else "baseline"))
        if not candidates:
            dt=n+timedelta(days=1)
            dt=dt.replace(hour=18,minute=30,second=0,microsecond=0)
            return {"time":"18:30","date":dt.date().isoformat(),"publish_at":dt.isoformat(),"reason":"baseline","timezone":"America/Sao_Paulo"}
        score,dt,slot,reason=max(candidates,key=lambda x:(x[0],-x[1].timestamp()))
        return {"time":slot,"date":dt.date().isoformat(),"publish_at":dt.isoformat(),"reason":reason,"timezone":"America/Sao_Paulo"}

    def reserve_publish_slot(self, job_id, now=None):
        """Reserve a unique future slot for a finished job so the queue cannot collide."""
        from datetime import timedelta
        with self.lock:
            slot=self.recommend_publish_slot(now=now)
            if slot.get("publish_at"):
                d=self._read()
                reserved=d.setdefault("scheduled_slots",{})
                reserved[slot["publish_at"]]=str(job_id)
                self._write(d)
            return slot

    def record_slot_performance(self, slot, score):
        if not slot: return
        with self.lock:
            d=self._read(); p=d.setdefault("patterns",{}).setdefault("publish_slots",{})
            old=p.get(slot,{"sum":0,"n":0}) if isinstance(p.get(slot),dict) else {"sum":0,"n":0}
            old["sum"]+=float(score or 0); old["n"]+=1; p[slot]=old["sum"]/old["n"]
            self._write(d)

    def status(self):
        d=self._read()
        return {"version":"V59","topics_seen":len(d["topics"]),"videos_tracked":len(d["videos"]),"editorial_learning":self.recommend_editorial_profile()}

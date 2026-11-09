import json, math, os, re, time, threading
from pathlib import Path

import requests


class TrendBrain:
    """Editorial memory with a local fallback and optional durable Supabase storage."""
    def __init__(self, workspace=None):
        self.root=Path(workspace or os.getenv("GTA_WORKSPACE","workspace"))
        self.root.mkdir(parents=True, exist_ok=True)
        self.path=self.root/"trend_brain.json"
        self.lock=threading.RLock()
        self.supabase_url=os.getenv("GTA_SUPABASE_URL","").strip().rstrip("/")
        self.supabase_key=os.getenv("GTA_SUPABASE_SERVICE_ROLE_KEY","").strip()
        self.remote_configured=bool(self.supabase_url and self.supabase_key)
        self.remote_connected=False
        self.remote_last_error=""
        if not self.path.exists():
            self._write({"topics":{},"videos":{},"patterns":{}})
        elif self.remote_configured:
            # On first connection, seed the durable store with the existing
            # local history only when the remote singleton row does not exist.
            try:
                remote=self._remote_read()
                if remote is None:
                    self._write(self._read_local())
            except Exception as exc:
                self.remote_connected=False
                self.remote_last_error=f"{type(exc).__name__}: {str(exc)[:180]}"

    def _remote_headers(self):
        # Supabase's modern opaque API keys (sb_secret_ / sb_publishable_)
        # are not JWTs. Send them only through apikey; putting an sb_ key
        # in Authorization: Bearer makes Supabase reject it as an invalid JWT.
        headers={
            "apikey":self.supabase_key,
            "Content-Type":"application/json",
            "Prefer":"resolution=merge-duplicates,return=minimal"
        }
        # Legacy anon/service_role keys are JWTs and still require Bearer auth.
        if not self.supabase_key.startswith("sb_"):
            headers["Authorization"]=f"Bearer {self.supabase_key}"
        return headers

    def _remote_read(self):
        response=requests.get(
            f"{self.supabase_url}/rest/v1/gta_oculto_editorial_memory",
            params={"id":"eq.primary","select":"data"},
            headers=self._remote_headers(),
            timeout=5
        )
        response.raise_for_status()
        rows=response.json()
        self.remote_connected=True
        self.remote_last_error=""
        if not rows:
            return None
        data=rows[0].get("data")
        return data if isinstance(data,dict) else None

    def _read_local(self):
        try:
            value=json.loads(self.path.read_text(encoding="utf-8"))
            return value if isinstance(value,dict) else {"topics":{},"videos":{},"patterns":{}}
        except Exception:
            return {"topics":{},"videos":{},"patterns":{}}

    def _read(self):
        if self.remote_configured:
            try:
                remote=self._remote_read()
                if remote is not None:
                    return remote
            except Exception as exc:
                self.remote_connected=False
                self.remote_last_error=f"{type(exc).__name__}: {str(exc)[:180]}"
        return self._read_local()

    def _write(self,d):
        payload=json.dumps(d,ensure_ascii=False,indent=2)
        tmp=self.path.with_suffix(".tmp")
        tmp.write_text(payload,encoding="utf-8")
        os.replace(tmp,self.path)
        if self.remote_configured:
            try:
                response=requests.post(
                    f"{self.supabase_url}/rest/v1/gta_oculto_editorial_memory",
                    json={"id":"primary","data":d},
                    headers=self._remote_headers(),
                    timeout=7
                )
                response.raise_for_status()
                self.remote_connected=True
                self.remote_last_error=""
            except Exception as exc:
                self.remote_connected=False
                self.remote_last_error=f"{type(exc).__name__}: {str(exc)[:180]}"
                print(f"[TREND_BRAIN] Supabase write failed; local fallback active: {self.remote_last_error}",flush=True)

    def _key(self,t):
        words=re.findall(r"[a-z0-9áéíóúãõç]+",str(t.get("title","")).lower())
        return " ".join([w for w in words if len(w)>3][:10]) or str(t.get("id","unknown"))

    def _fingerprint(self,t):
        """Fingerprint editorial que considera a pauta e o conteúdo efetivamente narrado."""
        if isinstance(t,dict):
            parts=[t.get(k,"") for k in (
                "title","selected_topic_title","story_text","narration",
                "description","editorial_text"
            )]
        else:
            parts=[t]
        text=" ".join(str(x or "") for x in parts).lower()
        words=re.findall(r"[a-z0-9áéíóúãõç]+",text)
        stop={
            "gta","gta6","gtaiv","grand","theft","auto","rockstar","games",
            "novo","nova","novos","novas","jogo","jogos","detalhe","detalhes",
            "confirmou","confirmados","confirmada","revelou","revela","sobre",
            "pode","ser","sera","será","para","como","mais","muito","ainda"
        }
        core=[w for w in words if len(w)>3 and w not in stop]
        return " ".join(sorted(set(core[:40])))

    def _story_similarity(self,a,b):
        """Compara a pauta por conceitos e palavras, não só pela manchete literal."""
        def signature(value):
            low=str(value or "").lower()
            words=set(
                w for w in re.findall(r"[a-z0-9áéíóúãõç]+",low)
                if len(w)>3 and w not in {
                    "gta","gta6","gtaiv","grand","theft","auto","rockstar","games",
                    "novo","nova","novos","novas","jogo","jogos","detalhe","detalhes",
                    "confirmou","confirmados","confirmada","revelou","revela","sobre",
                    "pode","ser","sera","será","para","como","mais","muito","ainda",
                    "the","and","for","with","from","this","that"
                }
            )
            concepts=set()
            if "jason" in low and "lucia" in low: concepts.add("jason-lucia")
            if "vice city" in low or "miami" in low: concepts.add("vice-city")
            if "leonida" in low: concepts.add("leonida")
            if any(x in low for x in ("cloud gaming","xbox cloud","jogar na nuvem","jogos na nuvem")): concepts.add("cloud-gaming")
            if any(x in low for x in ("tamanho do mapa","mapa de gta 6","mapa gta 6","mapa maior")): concepts.add("mapa-tamanho")
            if any(x in low for x in ("pré-venda","pre-venda","pre-order","preorder")): concepts.add("pre-venda")
            if any(x in low for x in ("trilha sonora","soundtrack","álbum","album")): concepts.add("trilha-sonora")
            if "ps5 pro" in low: concepts.add("ps5-pro")
            if "discord" in low: concepts.add("discord")
            return concepts,words

        ca,wa=signature(a); cb,wb=signature(b)
        if ca and cb and (ca & cb):
            similarity=len(ca & cb)/max(1,len(ca | cb))
            if similarity >= 0.5:
                return max(0.72,similarity)
            return 0.58
        if not wa or not wb:
            return 0.0
        return len(wa & wb)/max(1,len(wa | wb))

    def _repetition_penalty(self,t,d):
        """Bloqueia por 14 dias histórias já produzidas, mesmo com outra manchete."""
        key=self._key(t); fp=self._fingerprint(t); now=time.time(); penalty=0
        story_text=" ".join(str(t.get(k,"") or "") for k in (
            "title","selected_topic_title","story_text","narration",
            "description","editorial_text"
        )) if isinstance(t,dict) else str(t or "")
        for v in d.get("videos",{}).values():
            age_days=(now-float(v.get("updated",now) or now))/86400
            if age_days>30: continue
            old_key=str(v.get("topic_key","") or "")
            oldfp=str(v.get("fingerprint","") or "")
            old_story=str(v.get("story_text","") or v.get("title","") or oldfp)
            similarity=self._story_similarity(story_text,old_story)
            if key and old_key==key:
                penalty=max(penalty,100 if age_days<14 else 65)
            elif (fp and oldfp and fp==oldfp) or similarity>=0.55:
                penalty=max(penalty,100 if age_days<14 else 70)
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
            history_samples=0
            for v in d["videos"].values():
                if v.get("topic_key")==self._key(t):
                    history_samples+=1
                    history=max(history,float(v.get("performance_score",0) or 0))
            # Exploração controlada: temas pouco testados recebem um pequeno bônus,
            # enquanto temas repetidos perdem prioridade. Histórico só influencia
            # exploração depois de haver amostra suficiente para evitar overfitting.
            if history_samples < 2:
                learned_history=0
                exploration_bonus=8 if seen<=1 else (4 if seen<=3 else (0 if seen<=5 else -3))
            else:
                learned_history=history
                exploration_bonus=2 if seen<=2 else 0
            repetition=self._repetition_penalty(t,d)
            score=base*.40+conf*.14+demand*.18+novelty*.12+learned_history*.14+exploration_bonus-repetition
            t["trend_score"]=int(max(0,min(100,round(score))))
            t["repetition_penalty"]=repetition
            t["exploration_bonus"]=exploration_bonus
            t["history_samples"]=history_samples
            t["trend_signal"]="FORTE" if t["trend_score"]>=78 else ("MÉDIO" if t["trend_score"]>=60 else "FRACO")
            t["trend_reason"]=f"Radar {int(base)}/100; demanda {int(demand)}; novidade {int(novelty)}; histórico {int(learned_history)} ({history_samples} amostras); exploração {int(exploration_bonus):+d}; repetição -{int(repetition)}."
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
            story_text=" ".join(str(x or "") for x in (
                (topic or {}).get("title",""),(topic or {}).get("selected_topic_title",""),
                (metadata or {}).get("title",""),(metadata or {}).get("description",""),
                (metadata or {}).get("editorial_text","")
            ))[:12000]
            d["videos"][str(video_id)]={
                "topic_key":k,"fingerprint":self._fingerprint({"title":(topic or {}).get("title",""),"story_text":story_text}),
                "story_text":story_text,"title":str((topic or {}).get("title","")),"hook":hook,
                "hook_type":self._hook_type(hook),
                "content_type":str((topic or {}).get("content_type","CURIOSIDADE") or "CURIOSIDADE").upper(),
                "angle":str((metadata or {}).get("editorial_angle",(topic or {}).get("editorial_angle","")) or ""),
                "angle_type":self._angle_type((metadata or {}).get("editorial_angle",(topic or {}).get("editorial_angle","")) or ""),
                "title_pattern":self._title_pattern((topic or {}).get("title","")),
                "duration_bucket":self._duration_bucket((metadata or {}).get("duration_seconds",0)),
                "performance_score":old.get("performance_score",0),
                "publish_slot":str(publish_slot or old.get("publish_slot","")),"updated":time.time()
            }
            self._write(d)

    def learn(self,result,publications=None):
        if not result or not result.get("ok"): return result or {"ok":False}
        headers=[str(x.get("name","")).lower() for x in result.get("headers",[])]
        rows=result.get("rows",[]) or []
        def ix(n):
            try:return headers.index(n)
            except ValueError:return -1
        vi,vw,vl,vc,vs,vd,vm,vp=ix("video"),ix("views"),ix("likes"),ix("comments"),ix("subscribersgained"),ix("averageviewduration"),ix("estimatedminuteswatched"),ix("publishedat")
        with self.lock:
            d=self._read()
            pubs=publications or {}
            for row in rows:
                if vi<0 or vi>=len(row): continue
                vid=str(row[vi]); views=float(row[vw] or 0) if 0<=vw<len(row) else 0
                likes=float(row[vl] or 0) if 0<=vl<len(row) else 0
                comments=float(row[vc] or 0) if 0<=vc<len(row) else 0
                subs=float(row[vs] or 0) if 0<=vs<len(row) else 0
                avg_duration=float(row[vd] or 0) if 0<=vd<len(row) else 0
                published_at=str(row[vp] or "") if 0<=vp<len(row) else ""
                watched_minutes=float(row[vm] or 0) if 0<=vm<len(row) else 0
                like_rate=(likes/views*100) if views else 0
                # Retention matters more than raw views for Shorts. Use bounded Analytics signals.
                retention_signal=min(30,avg_duration*2.0)
                watch_signal=min(15,math.log10(max(1,watched_minutes+1))*5)
                comment_rate=(comments/views*100) if views else 0
                engagement=min(20,like_rate*4)
                comment_signal=min(5,comment_rate*10)
                subscriber_signal=min(15,subs*3)
                age_days=1.0
                if published_at:
                    try:
                        from datetime import datetime, timezone
                        dt=datetime.fromisoformat(published_at.replace("Z","+00:00"))
                        age_days=max(1/24, (datetime.now(timezone.utc)-dt).total_seconds()/86400)
                    except Exception:
                        age_days=1.0
                view_velocity=views/age_days
                view_signal=min(40,math.log10(max(1,view_velocity))*10)
                perf=min(100,view_signal+retention_signal+watch_signal+engagement+comment_signal+subscriber_signal)
                p=pubs.get(vid,{})
                existing=d["videos"].get(vid,{})
                d["videos"][vid]={"topic_key":p.get("topic_key",existing.get("topic_key","")),"title":existing.get("title",p.get("title","")),"title_pattern":existing.get("title_pattern",self._title_pattern(existing.get("title",p.get("title","")))),"hook":existing.get("hook",p.get("hook","")),"angle":existing.get("angle",p.get("angle","")),"angle_type":existing.get("angle_type",self._angle_type(existing.get("angle",p.get("angle","")))),"fingerprint":existing.get("fingerprint",""),"story_text":existing.get("story_text",p.get("story_text","")),"duration_bucket":existing.get("duration_bucket",p.get("duration_bucket","")),"hook_type":existing.get("hook_type",self._hook_type(existing.get("hook",""))),"content_type":existing.get("content_type",p.get("content_type","CURIOSIDADE")),"publish_slot":existing.get("publish_slot",p.get("publish_slot","")),"performance_score":round(perf,2),"views":views,"likes":likes,"comments":comments,"subscribers":subs,"average_view_duration":avg_duration,"estimated_minutes_watched":watched_minutes,"like_rate":round(like_rate,3),"comment_rate":round(comment_rate,3),"view_velocity":round(view_velocity,2),"analytics_observed":True,"updated":time.time()}
            # Recompute slot averages from one latest record per video. Analytics
            # can return the same video every day; counting each poll as a new sample
            # would artificially inflate sample sizes and overweight older results.
            slot_totals={}
            for video in d["videos"].values():
                slot=str(video.get("publish_slot","") or "")
                if not slot or not video.get("analytics_observed"):
                    continue
                bucket=slot_totals.setdefault(slot,{"sum":0.0,"n":0})
                bucket["sum"]+=float(video.get("performance_score",0) or 0)
                bucket["n"]+=1
            patterns=d.setdefault("patterns",{})
            patterns["publish_slots"]={slot:round(v["sum"]/v["n"],2) for slot,v in slot_totals.items() if v["n"]}
            patterns["publish_slot_samples"]={slot:v["n"] for slot,v in slot_totals.items() if v["n"]}
            d["videos"]=dict(list(d["videos"].items())[-500:])
            self._write(d)
        return {"ok":True,"videos_learned":len(rows)}

    @staticmethod
    def _title_pattern(title):
        """Classifica a embalagem do título para aprender formatos vencedores."""
        t=str(title or "").lower().strip()
        if not t: return "OUTRO"
        if re.search(r"\b\d{1,3}\s+(novidades|detalhes|segredos|curiosidades|fatos|mistérios|misterios)\b",t): return "LISTA_NUMERICA"
        if "?" in t: return "PERGUNTA"
        if any(x in t for x in ("o detalhe","o segredo","a pista","detalhe escondido")): return "DETALHE_CURIOSO"
        if any(x in t for x in ("confirmou","confirmado","oficialmente","revelou","revelado")): return "CONFIRMACAO"
        if any(x in t for x in ("como","por que","porque","o que significa")): return "EXPLICATIVO"
        if any(x in t for x in ("pode mudar","vai mudar","pode revelar","pode indicar")): return "IMPACTO"
        return "DECLARATIVO"

    @staticmethod
    def _angle_type(angle):
        a=str(angle or "").lower()
        if any(x in a for x in ("verdade ou","fato de especulação","rumor")): return "FATO_VS_RUMOR"
        if any(x in a for x in ("pista","detalhe","escondido")): return "PISTA_DETALHE"
        if any(x in a for x in ("impacto","mudar","consequ")): return "IMPACTO"
        if any(x in a for x in ("explicar","por que","significa")): return "EXPLICATIVO"
        return "INFORMATIVO"

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
        title_stats={}
        angle_stats={}
        for row in rows:
            tp=str(row.get("title_pattern","") or self._title_pattern(row.get("title","")))
            at=str(row.get("angle_type","") or self._angle_type(row.get("angle","")))
            if tp:
                x=title_stats.setdefault(tp,{"sum":0.0,"n":0}); x["sum"]+=float(row.get("performance_score",0) or 0); x["n"]+=1
            if at:
                x=angle_stats.setdefault(at,{"sum":0.0,"n":0}); x["sum"]+=float(row.get("performance_score",0) or 0); x["n"]+=1
        preferred_title=None
        eligible_titles={a:b for a,b in title_stats.items() if b["n"]>=2}
        if eligible_titles:
            tk,tv=max(eligible_titles.items(),key=lambda kv:kv[1]["sum"]/kv[1]["n"])
            preferred_title={"pattern":tk,"score":round(tv["sum"]/tv["n"],2),"samples":tv["n"]}
        preferred_angle=None
        eligible_angles={a:b for a,b in angle_stats.items() if b["n"]>=2}
        if eligible_angles:
            ak,av=max(eligible_angles.items(),key=lambda kv:kv[1]["sum"]/kv[1]["n"])
            preferred_angle={"type":ak,"score":round(av["sum"]/av["n"],2),"samples":av["n"]}
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
                "preferred_title_pattern":preferred_title,
                "preferred_angle_type":preferred_angle,
                "by_title_pattern":{a:round(b["sum"]/b["n"],2) for a,b in title_stats.items()},
                "by_angle_type":{a:round(b["sum"]/b["n"],2) for a,b in angle_stats.items()},
                "confidence":min(1.0, max(0.0, (v["n"]-1)/4.0))}

    def record_production(self, topic, metadata=None, quality=0):
        """Registra toda produção concluída, mesmo quando o upload do YouTube está desligado."""
        with self.lock:
            d=self._read(); k=self._key(topic or {})
            x=d["topics"].setdefault(k,{"seen":0,"best":0})
            x["productions"]=int(x.get("productions",0))+1
            x["quality_sum"]=float(x.get("quality_sum",0))+float(quality or 0)
            x["last_quality"]=float(quality or 0)
            meta=metadata or {}
            topic_title=str((topic or {}).get("title","") or "")
            story_text=" ".join(str(x or "") for x in (
                topic_title,(topic or {}).get("selected_topic_title",""),
                meta.get("title",""),meta.get("description",""),
                meta.get("editorial_text","")
            ))[:12000]
            x["last_title"]=str(meta.get("title","") or topic_title)
            x["last_hook"]=str(meta.get("hook",meta.get("editorial_hook","")))
            fp=self._fingerprint({"title":topic_title,"story_text":story_text})
            if fp:
                d.setdefault("videos",{})[f"production:{int(time.time()*1000)}"]={
                    "topic_key":k,"fingerprint":fp,"story_text":story_text,
                    "title":topic_title,"performance_score":float(quality or 0),"updated":time.time()
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
                # Blend learned performance with the baseline until enough real samples exist.
                learned_score=learned.get(slot)
                samples=int(d.get("patterns",{}).get("publish_slot_samples",{}).get(slot,0) or 0)
                if learned_score is not None and samples>0:
                    confidence=min(1.0,samples/5.0)
                    score=float(baseline)*(1.0-confidence)+float(learned_score)*confidence
                    reason="aprendido" if samples>=5 else "misto"
                else:
                    score=float(baseline)
                    reason="baseline"
                score-=day_offset*12  # favor the strongest available slot without waiting needlessly
                candidates.append((score,dt,slot,reason))
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

    def release_publish_slot(self, job_id, publish_at=None):
        """Release a reservation when upload fails so another job can use that time."""
        with self.lock:
            d=self._read()
            reserved=d.setdefault("scheduled_slots",{})
            target=str(job_id)
            removed=[]
            for when, owner in list(reserved.items()):
                if str(owner)==target and (not publish_at or when==str(publish_at)):
                    removed.append(when)
                    reserved.pop(when,None)
            if removed:
                d["scheduled_slots"]=reserved
                self._write(d)
            return {"ok":True,"released":removed}

    def record_slot_performance(self, slot, score):
        if not slot: return
        with self.lock:
            d=self._read()
            patterns=d.setdefault("patterns",{})
            averages=patterns.setdefault("publish_slots",{})
            counts=patterns.setdefault("publish_slot_samples",{})
            n=int(counts.get(slot,0) or 0)
            avg=float(averages.get(slot,0) or 0)
            counts[slot]=n+1
            averages[slot]=round((avg*n+float(score or 0))/(n+1),2)
            self._write(d)

    def status(self):
        d=self._read()
        return {
            "version":"V60",
            "topics_seen":len(d.get("topics",{})),
            "videos_tracked":len(d.get("videos",{})),
            "persistent_storage":{
                "provider":"supabase" if self.remote_configured else "local",
                "configured":self.remote_configured,
                "connected":self.remote_connected,
                "last_error":self.remote_last_error or None
            },
            "editorial_learning":self.recommend_editorial_profile()
        }

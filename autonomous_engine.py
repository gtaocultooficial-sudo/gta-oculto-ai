import os, time, traceback
from pathlib import Path
from memory_store import MemoryStore
from repair_engine import RepairEngine
from deploy_manager import DeployManager
from youtube_publisher import YouTubePublisher
try:
    from social_publishers import SocialPublisher
except Exception:
    SocialPublisher = None
from analytics_engine import YouTubeAnalytics
from safe_code_repair import SafeCodeRepair
try:
    from trend_brain import TrendBrain
except Exception:
    TrendBrain = None

class AutonomousEngine:
    def __init__(self, root=None):
        self.root=Path(root or Path(__file__).resolve().parent)
        self.memory=MemoryStore(self.root/'workspace'/'autonomy_memory.json')
        self.repair=RepairEngine(self.root)
        self.deploy=DeployManager()
        self.publisher=YouTubePublisher()
        self.analytics=YouTubeAnalytics()
        self.social=SocialPublisher() if SocialPublisher else None
        self.max_recoveries=int(os.getenv('GTA_MAX_AUTONOMOUS_RECOVERIES','4'))
        self.code_repair=SafeCodeRepair(self.root/'app.py')
        self.trend_brain=TrendBrain(self.root/'workspace') if TrendBrain else None
    def on_error(self, jid, error, app_module):
        """Return action: RETRY, SWITCH_TOPIC, QUARANTINE or CODE_REPAIR_PENDING."""
        plan=self.repair.plan(error); self.memory.event('production_error',error,plan)
        try: job=app_module.load_jobs().get(jid,{})
        except Exception: job={}
        count=int(job.get('autonomous_recovery_count',0))+1
        if count>self.max_recoveries: return {'action':'QUARANTINE','reason':'max_recoveries','plan':plan}
        # Source failures are best recovered by changing the editorial opportunity.
        if plan['code'] in ('BLOCKED_NO_BODY','FEED_CANDIDATE','RESOLVER_DEADLINE'):
            try:
                topics,_,_,_,_=app_module.current_opportunities()
                current=(job.get('opportunity') or {}).get('id')
                # Never select an obviously non-direct/feed candidate as a recovery topic.
                # If the Radar returns no safe alternative, retry the Radar once rather than
                # converting a recoverable source problem into a terminal ERROR.
                def _safe_topic(t):
                    u=str(t.get('url','')).lower()
                    src=str(t.get('source','')).lower()
                    return (t.get('id')!=current and u and 'news.google.com' not in u
                            and 'rss' not in src and 'feed' not in src)
                candidates=[t for t in topics if _safe_topic(t)]
                if not candidates:
                    # Use a direct official article candidate when available.
                    for t in getattr(app_module,'FALLBACK_TOPICS',[]) or []:
                        if _safe_topic(t): candidates.append(t)
                if candidates:
                    candidate=sorted(candidates,key=lambda x:float(x.get('score',0)),reverse=True)[0]
                    app_module.update_job(jid,status='QUEUED',stage='AUTO-RECUPERAÇÃO',progress=2,log=f'🤖 AUTO-RECUPERAÇÃO: fonte não validada. Mudando para outra pauta automaticamente: {candidate.get("title")}.',opportunity=candidate,autonomous_recovery_count=count)
                    self.memory.strategy('source_recovery','switch_topic',success=True,details={'from':current,'to':candidate.get('id')})
                    return {'action':'SWITCH_TOPIC','topic':candidate,'plan':plan}
            except Exception as e: self.memory.event('recovery_error',str(e))
        # Known code failures can receive a deterministic, tested patch. Unknown code is quarantined.
        if plan['code'] in ('VARIANT_UNBOUND','RESOLVER_DEADLINE') and os.getenv('GTA_AUTO_CODE_REPAIR','1').lower() in ('1','true','yes','on'):
            ok,log=self.code_repair.apply(plan['code'])
            self.memory.event('code_repair',plan['code'],{'log':log},ok)
            if ok:
                if self.deploy.auto:
                    self.deploy.deploy_candidate(self.root/'app.py', 'app.py', f'GTA OCULTO AI safe repair: {plan["code"]}')
                app_module.update_job(jid,status='QUEUED',stage='AUTO-REPARO-CÓDIGO',progress=2,log=f'🤖 AUTO-REPARO DE CÓDIGO: {plan["code"]} corrigido, compilado e retentando.',autonomous_recovery_count=count)
                return {'action':'CODE_REPAIR_RETRY','plan':plan}
        # Known technical failures: retry once after recording the strategy.
        if plan['code'] in ('WORKER_TIMEOUT','VARIANT_UNBOUND'):
            app_module.update_job(jid,status='QUEUED',stage='AUTO-RECUPERAÇÃO',progress=2,log=f'🤖 AUTO-RECUPERAÇÃO: erro técnico conhecido ({plan["code"]}). Retentando automaticamente.',autonomous_recovery_count=count)
            self.memory.strategy('technical_recovery',plan['code'],success=True)
            return {'action':'RETRY','plan':plan}
        return {'action':'QUARANTINE','plan':plan}
    def on_done(self, jid, app_module):
        job=app_module.load_jobs().get(jid,{})
        meta=job.get('metadata') or {}; video=job.get('video')
        result={'published':False,'analytics':None}
        if video:
            path=app_module.WORK/video
            if path.exists():
                pub=self.publisher.upload(path,meta); result['published']=bool(pub.get('ok')); result['publish']=pub
                self.memory.event('publish',f'job {jid}',pub,pub.get('ok'))
                if pub.get('ok'):
                    if self.trend_brain:
                        try: self.trend_brain.record_publication(job.get('opportunity') or {}, meta, pub.get('video_id'))
                        except Exception: pass
                    app_module.update_job(jid,stage='PUBLICAÇÃO',log=f'▶️ YouTube: vídeo enviado ({pub.get("video_id")}).',youtube=pub)
        # Optional social adapters use the public Render output URL and stay disabled without credentials.
        if self.social:
            try:
                base=os.getenv('PUBLIC_BASE_URL','https://gta-oculto-ai.onrender.com').rstrip('/')
                video_url=f"{base}/output/{str(video).replace('/', '%2F')}"
                social=self.social.publish(video_url,meta)
                result['social']=social
                app_module.update_job(jid,log='📡 Redes opcionais: '+json.dumps(social,ensure_ascii=False)[:1200],social=social)
                self.memory.event('social_publish',f'job {jid}',social,any(x.get('ok') for x in social.values() if isinstance(x,dict)))
            except Exception as e:
                self.memory.event('social_publish_error',str(e))
        return result
    def collect_analytics(self):
        r=self.analytics.collect(7)
        self.memory.event('analytics','weekly_collection',r,r.get('ok'))
        if r.get('ok'):
            self.memory.metric('latest_analytics',r)
            if self.trend_brain:
                try: self.trend_brain.learn(r)
                except Exception as e: self.memory.event('trend_brain_error',str(e))
        return r
    def status(self):
        return {'mode':'AUTONOMOUS','max_recoveries':self.max_recoveries,'deploy':self.deploy.status(),'youtube_publish':self.publisher.enabled,'youtube_analytics':self.analytics.enabled,'social_publish':self.social.status() if self.social else {},'trend_brain':self.trend_brain.status() if self.trend_brain else {'enabled':False},'memory':self.memory.summary()}

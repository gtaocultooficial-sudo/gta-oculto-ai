import os, time, traceback, json
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
        self.last_analytics_result=None
    def on_error(self, jid, error, app_module):
        """Return action: RETRY, SWITCH_TOPIC, QUARANTINE or CODE_REPAIR_PENDING."""
        plan=self.repair.plan(error); self.memory.event('production_error',error,plan)
        try: job=app_module.load_jobs().get(jid,{})
        except Exception: job={}
        count=int(job.get('autonomous_recovery_count',0))+1
        if count>self.max_recoveries: return {'action':'QUARANTINE','reason':'max_recoveries','plan':plan}
        if 'GATE EDITORIAL FINAL' in str(error):
            # A low score is not fixed by rendering the same topic again.
            # Switch to a distinct direct GTA 6 opportunity; if none exists,
            # quarantine instead of looping or releasing a weak Short.
            try:
                topics,_,_,_,_=app_module.current_opportunities()
                current=job.get('opportunity') or {}
                current_id=current.get('id')
                current_title=str(current.get('title','')).strip().lower()
                def _editorial_candidate(t):
                    u=str(t.get('url','')).lower()
                    src=str(t.get('source','')).lower()
                    title=str(t.get('title','')).strip().lower()
                    gta_topic=any(k in (title+' '+u) for k in ('gta 6','gta vi','grand theft auto vi','rockstar games'))
                    return bool(t.get('id') != current_id and title and title != current_title
                                and u and 'news.google.com' not in u
                                and 'rss' not in src and 'feed' not in src and gta_topic)
                candidates=[t for t in topics if _editorial_candidate(t)]
                # The live radar may return no safe alternatives; use curated direct-source
                # GTA VI fallback topics rather than repeating the same failed production.
                if not candidates:
                    candidates=[t for t in (getattr(app_module,'FALLBACK_TOPICS',[]) or [])
                                if _editorial_candidate(t)]
                if candidates and count <= 2:
                    candidate=sorted(candidates,key=lambda x:float(x.get('score',0)),reverse=True)[0]
                    app_module.update_job(jid,status='QUEUED',stage='AUTO-RECUPERAÇÃO EDITORIAL',progress=2,
                        log=f'🤖 Short reprovado na avaliação editorial. Mudando a pauta para melhorar variedade e correspondência visual: {candidate.get("title")}. Nota mínima 75/100 mantida.',
                        opportunity=candidate,autonomous_recovery_count=count)
                    self.memory.strategy('editorial_score_gate','switch_topic_and_retry',success=True,
                        details={'attempt':count,'from':current.get('title'),'to':candidate.get('title')})
                    return {'action':'SWITCH_TOPIC','topic':candidate,'plan':plan}
            except Exception as recovery_error:
                self.memory.event('editorial_recovery_error',str(recovery_error))
            return {'action':'QUARANTINE','reason':'editorial_score_below_threshold_no_safe_alternative','plan':plan}
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
        print(f'[AUTONOMY {jid}] on_done start video={bool(video)} publisher_enabled={self.publisher.enabled} token_configured={bool(self.publisher.token_json)}', flush=True)
        if video:
            # Do not reserve a future public release slot while YouTube auto-publishing
            # is disabled. A stale publishAt value could otherwise schedule visibility
            # unexpectedly if publishing is enabled again later.
            if self.trend_brain and self.publisher.enabled:
                try:
                    quality=float(job.get('score',0) or job.get('audit_score',0) or 0)
                    if isinstance(job.get('media_validation'),dict):
                        meta['duration_seconds']=float(job['media_validation'].get('duration',0) or 0)
                    self.trend_brain.record_production(job.get('opportunity') or {}, meta, quality)
                    job['recommended_publish_slot']=self.trend_brain.reserve_publish_slot(jid)
                    if isinstance(job['recommended_publish_slot'],dict):
                        meta['publish_at']=job['recommended_publish_slot'].get('publish_at','')
                        meta['publish_slot']=job['recommended_publish_slot'].get('time','')
                    app_module.update_job(jid,recommended_publish_slot=job['recommended_publish_slot'],metadata=meta)
                except Exception as e: self.memory.event('publish_slot_error',str(e))
            elif not self.publisher.enabled:
                meta.pop('publish_at',None)
                job['recommended_publish_slot']={}
                app_module.update_job(jid,recommended_publish_slot=None,metadata=meta)
            path=app_module.WORK/video
            if path.exists():
                print(f'[AUTONOMY {jid}] YouTube upload start bytes={path.stat().st_size}', flush=True)
                pub=self.publisher.upload(path,meta); result['published']=bool(pub.get('ok')); result['publish']=pub
                print(f'[AUTONOMY {jid}] YouTube upload result ok={pub.get("ok")} reason={str(pub.get("reason",""))[:500]} video_id={pub.get("video_id","")}', flush=True)
                self.memory.event('publish',f'job {jid}',pub,pub.get('ok'))
                if pub.get('ok'):
                    if self.trend_brain:
                        try:
                            slot=(job.get('recommended_publish_slot') or {}).get('time','') if isinstance(job.get('recommended_publish_slot'),dict) else ''
                            self.trend_brain.record_publication(job.get('opportunity') or {}, meta, pub.get('video_id'), slot)
                        except Exception: pass
                    if pub.get('scheduled'):
                        slot=job.get('recommended_publish_slot') or {}
                        when=f"{slot.get('date','')} às {slot.get('time','')} (horário de Brasília)"
                        app_module.update_job(jid,stage='PUBLICAÇÃO AGENDADA',log=f'🗓️ YouTube: Short enviado e agendado para {when}.',youtube=pub)
                    else:
                        app_module.update_job(jid,stage='PUBLICAÇÃO',log=f'▶️ YouTube: vídeo enviado ({pub.get("video_id")}).',youtube=pub)
                else:
                    if self.trend_brain:
                        try:
                            reserved=(job.get('recommended_publish_slot') or {}).get('publish_at','') if isinstance(job.get('recommended_publish_slot'),dict) else ''
                            self.trend_brain.release_publish_slot(jid, reserved)
                        except Exception as e:
                            self.memory.event('publish_slot_release_error',str(e))
                    reason=str(pub.get("reason","erro desconhecido"))
                    if 'YOUTUBE_DAILY_UPLOAD_LIMIT' in reason:
                        log=f'⏸️ Limite diário de envio do YouTube atingido. O MP4 continua salvo no servidor; não será feito loop de tentativas. Aguarde até 24 horas e tente novamente.'
                    else:
                        log=f'⚠️ Vídeo pronto, mas o envio ao YouTube falhou: {reason[:500]}'
                    app_module.update_job(jid,stage='PUBLICAÇÃO PENDENTE',log=log,youtube=pub)
            else:
                if self.trend_brain:
                    try:
                        reserved=(job.get('recommended_publish_slot') or {}).get('publish_at','') if isinstance(job.get('recommended_publish_slot'),dict) else ''
                        self.trend_brain.release_publish_slot(jid, reserved)
                    except Exception as e:
                        self.memory.event('publish_slot_release_error',str(e))
                pub={'ok':False,'reason':'FINAL_MP4_MISSING','path':str(path)}
                print(f'[AUTONOMY {jid}] YouTube upload skipped: final MP4 missing path={path}', flush=True)
                app_module.update_job(jid,stage='PUBLICAÇÃO PENDENTE',log='⚠️ Vídeo pronto, mas o MP4 final não foi encontrado para envio.',youtube=pub)
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
        print('[AUTONOMY] analytics collection start', flush=True)
        video_ids=[]
        if self.trend_brain:
            try: video_ids=self.trend_brain.tracked_video_ids()
            except Exception: video_ids=[]
        r=self.analytics.collect(7, video_ids=video_ids)
        print(f'[AUTONOMY] analytics collection result ok={r.get("ok")} reason={str(r.get("reason",""))[:400]}', flush=True)
        learned={'videos_learned':0}
        if r.get('ok'):
            self.memory.metric('latest_analytics',r)
            if self.trend_brain:
                try: learned=self.trend_brain.learn(r) or learned
                except Exception as e: self.memory.event('trend_brain_error',str(e))
        self.last_analytics_result={'ok':bool(r.get('ok')),'reason':str(r.get('reason',''))[:400],'rows_received':len(r.get('rows',[]) or []),'videos_learned':int(learned.get('videos_learned',0) or 0),'checked_at':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())}
        self.memory.event('analytics','weekly_collection',r,r.get('ok'))
        return r
    def status(self):
        return {'mode':'AUTONOMOUS','max_recoveries':self.max_recoveries,'deploy':self.deploy.status(),'youtube_publish':self.publisher.enabled,'youtube_analytics':self.analytics.enabled,'social_publish':self.social.status() if self.social else {},'trend_brain':self.trend_brain.status() if self.trend_brain else {'enabled':False},'analytics_last_result':self.last_analytics_result,'memory':self.memory.summary()}

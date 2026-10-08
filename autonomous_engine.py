import os, time, threading, traceback
from pathlib import Path
from memory_store import MemoryStore
from audit_engine import AuditEngine
from repair_engine import RepairEngine

class AutonomousEngine:
    def __init__(self, legacy):
        self.legacy=legacy; self.memory=MemoryStore(); self.audit=AuditEngine(); self.repairs=RepairEngine(); self.max_attempts=int(os.getenv('GTA_MAX_REPAIR_ATTEMPTS','3')); self.lock=threading.RLock(); self.running=False

    def _job(self,jid): return self.legacy.load_jobs().get(jid,{})
    def _update(self,jid,**kw): return self.legacy.update_job(jid,**kw)
    def _set(self,jid,msg,**kw): self._update(jid,log=msg,**kw)

    def produce(self,jid):
        with self.lock:
            if self.running: return False
            self.running=True
        try:
            self._set(jid,'🤖 AGENTE AUTÔNOMO: iniciando produção.',status='RUNNING',stage='PESQUISA',progress=2)
            # Use the already validated rendering pipeline rather than replacing it.
            self.legacy.produce_job(jid)
            j=self._job(jid)
            if j.get('status')!='DONE': return False
            attempts=[]
            for attempt in range(self.max_attempts+1):
                j=self._job(jid); video=(self.legacy.WORK/j.get('video')) if j.get('video') else None
                script=j.get('script') or {}; caps=[]
                result=self.audit.audit_video(video,script,caps)
                self._set(jid,f'🔍 AUDITOR IA: {result["score"]}/100 — '+(', '.join(result['issues']) if result['issues'] else 'sem problemas críticos'),score=result['score'])
                if result['ok']:
                    self.memory.record('post_render_quality','none','accepted',j.get('score',0),result['score'],True,{'issues':result['issues']})
                    self._set(jid,f'✅ AUDITOR IA APROVOU: {result["score"]}/100.',status='DONE',stage='PRONTO',progress=100)
                    return True
                if attempt>=self.max_attempts: break
                strategy=self.repairs.plan(result['issues'],[x['strategy'] for x in attempts])
                if not strategy: break
                before=result['score']; attempts.append({'strategy':strategy,'score_before':before})
                self.memory.record('post_render_quality',strategy,'attempt',before,before,False,{'issues':result['issues']})
                self._set(jid,f'🛠️ AUTO-REPARO {attempt+1}/{self.max_attempts}: {strategy}.',status='RUNNING',stage='EDIÇÃO',progress=75)
                # Safe repair: rerun the complete deterministic production. No arbitrary code edits.
                self.legacy.produce_job(jid)
                j=self._job(jid)
                if j.get('status')!='DONE': break
            self._set(jid,'⛔ Auditor não aprovou após o limite de tentativas. Mantendo último resultado seguro.',status='ERROR',stage='ERRO',progress=100)
            return False
        except Exception as e:
            self._set(jid,'🤖 AGENTE ERRO: '+str(e)+'\n'+traceback.format_exc()[-2500:],status='ERROR',stage='ERRO',progress=100)
            return False
        finally:
            self.running=False

    def loop(self):
        while True:
            try:
                jobs=self.legacy.load_jobs(); target=next((j for j in jobs.values() if j.get('status')=='QUEUED'),None)
                if target: self.produce(target['id'])
                time.sleep(2)
            except Exception: time.sleep(5)

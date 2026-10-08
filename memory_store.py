import json, os, time, threading
from pathlib import Path

class MemoryStore:
    def __init__(self, path=None):
        self.path = Path(path or os.getenv('GTA_MEMORY_FILE','workspace/autonomy_memory.json'))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        if not self.path.exists(): self._write({'events': [], 'strategies': {}, 'metrics': {}, 'experiments': []})

    def _read(self):
        try: return json.loads(self.path.read_text(encoding='utf-8'))
        except Exception: return {'events': [], 'strategies': {}, 'metrics': {}, 'experiments': []}
    def _write(self, data):
        tmp=self.path.with_suffix(self.path.suffix+'.tmp')
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        os.replace(tmp,self.path)
    def event(self, kind, message, data=None, success=None):
        with self.lock:
            d=self._read(); d.setdefault('events',[]).append({'ts':time.time(),'kind':kind,'message':message,'data':data or {},'success':success})
            d['events']=d['events'][-1000:]; self._write(d)
    def strategy(self, key, name, score_delta=0, success=None, details=None):
        with self.lock:
            d=self._read(); s=d.setdefault('strategies',{}).setdefault(key,{'tries':0,'wins':0,'losses':0,'score':0,'history':[]})
            s['tries']+=1; s['score']+=score_delta
            if success is True: s['wins']+=1
            if success is False: s['losses']+=1
            s['history'].append({'ts':time.time(),'name':name,'score_delta':score_delta,'success':success,'details':details or {}})
            s['history']=s['history'][-50:]; self._write(d)
    def metric(self, key, value):
        with self.lock:
            d=self._read(); d.setdefault('metrics',{})[key]=value; self._write(d)
    def experiment(self, name, before, after, accepted, details=None):
        with self.lock:
            d=self._read(); d.setdefault('experiments',[]).append({'ts':time.time(),'name':name,'before':before,'after':after,'accepted':accepted,'details':details or {}})
            d['experiments']=d['experiments'][-500:]; self._write(d)
    def summary(self):
        d=self._read(); return {'events':len(d.get('events',[])),'strategies':d.get('strategies',{}),'metrics':d.get('metrics',{}),'experiments':len(d.get('experiments',[]))}

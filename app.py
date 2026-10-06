import os, re, json, uuid, threading
from pathlib import Path
from datetime import datetime
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup
from flask import Flask, request, jsonify, render_template_string, send_from_directory

APP = Flask(__name__)
app = APP
BASE = Path(__file__).resolve().parent
WORK = BASE / "workspace"
WORK.mkdir(exist_ok=True)
STATE_FILE = WORK / "jobs.json"
LOCK = threading.Lock()
UA = "GTA-Oculto-AI/4.0"
WORKER_TOKEN = os.environ.get("WORKER_TOKEN", "")

OPPORTUNITIES = [
 {"id":"leonida","score":94,"priority":"ALTA","title":"GTA 6: o detalhe de Leonida que pode mudar a história","source":"Rockstar Games","url":"https://www.rockstargames.com/VI","status":"PRODUZIR"},
 {"id":"jason-lucia","score":92,"priority":"ALTA","title":"Jason e Lucia: o que a Rockstar já confirmou oficialmente","source":"Rockstar Games","url":"https://www.rockstargames.com/VI","status":"PRODUZIR"},
 {"id":"fora-vice-city","score":88,"priority":"ALTA","title":"GTA 6 pode esconder pistas fora de Vice City","source":"Análise editorial","url":"https://www.rockstargames.com/VI","status":"ANALISAR"},
 {"id":"gta5","score":74,"priority":"MÉDIA","title":"Um detalhe antigo de GTA V que voltou a chamar atenção","source":"Arquivo GTA","url":"https://www.rockstargames.com/gta-v","status":"RESERVAR"}
]

PAGE='''<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>GTA OCULTO AI</title><style>
*{box-sizing:border-box}body{margin:0;background:#08090c;color:#eee;font-family:Arial,Helvetica,sans-serif}.wrap{max-width:1320px;margin:auto;padding:20px}.top{display:flex;justify-content:space-between;align-items:center;padding:10px 4px 18px}.brand{font-size:28px;font-weight:900}.brand span{color:#e31a28}.status{padding:9px 13px;border:1px solid #2b3038;border-radius:9px;background:#111318;color:#70e28b;font-size:12px;font-weight:800}.hero,.panel,.stat{background:#101217;border:1px solid #292e37;border-radius:14px;margin-bottom:16px}.hero{padding:20px;display:flex;justify-content:space-between;gap:20px}.eyebrow{color:#e21a2a;font-size:12px;font-weight:900}.hero h1{margin:7px 0;font-size:25px}.muted{color:#8e96a3}.buttons{display:flex;gap:10px;align-items:center}.btn{border:0;border-radius:9px;padding:13px 17px;font-weight:900;cursor:pointer;background:#20242c;color:#fff}.btn.red{background:#d91624}.control{padding:14px;display:flex;gap:10px}.control input{flex:1;background:#181b21;border:1px solid #2b3038;border-radius:8px;color:white;padding:13px}.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}.stat{padding:18px}.stat small{color:#9aa2af}.stat b{display:block;font-size:29px;margin-top:7px}.pipeline,.opp,.jobs{padding:18px}.steps{display:grid;grid-template-columns:repeat(8,1fr);gap:7px}.step{padding:12px 5px;text-align:center;background:#1a1d23;border-radius:8px;font-size:11px;font-weight:900;color:#9da5b2}.row{display:grid;grid-template-columns:55px 1fr 140px 95px 95px;gap:12px;align-items:center;padding:14px 0;border-bottom:1px solid #252932}.score{font-size:21px;font-weight:900}.title{font-weight:800}.source{font-size:12px;color:#858d99;margin-top:4px}.pill{border:1px solid #353b45;border-radius:20px;padding:7px;text-align:center;font-size:11px}.produce{background:#242933;border:0;color:white;border-radius:8px;padding:10px;font-weight:900;cursor:pointer}.job{background:#15181e;border:1px solid #2b3038;border-radius:10px;padding:13px;margin-top:9px}.bar{height:7px;background:#272c34;border-radius:10px;overflow:hidden;margin-top:10px}.bar i{display:block;height:100%;background:#d91624}.result{margin-top:10px}.result a{color:#ff5965;text-decoration:none;font-weight:800}.log{font-family:monospace;color:#aeb6c2;font-size:12px;white-space:pre-wrap;margin-top:9px}.worker{padding:14px;background:#0d1014;border:1px dashed #343b45;border-radius:10px;margin-bottom:16px;font-size:12px}@media(max-width:900px){.stats{grid-template-columns:repeat(2,1fr)}.steps{grid-template-columns:repeat(4,1fr)}.hero{display:block}.buttons{margin-top:15px}.row{grid-template-columns:45px 1fr 90px}.row .pill{display:none}}
</style></head><body><div class="wrap"><div class="top"><div class="brand">GTA <span>OCULTO</span> AI</div><div class="status">● PAINEL ONLINE</div></div>
<div class="hero"><div><div class="eyebrow">PRODUTOR AUTÔNOMO</div><h1>A IA pesquisa, escolhe e produz.</h1><div class="muted">Render = painel e fila · PC = produção pesada</div></div><div class="buttons"><button class="btn red" onclick="createShort()">⚡ CRIAR SHORT</button><button class="btn" onclick="research()">🔎 PESQUISAR OPORTUNIDADES</button></div></div>
<div class="worker">🖥️ <b>FÁBRICA LOCAL</b> — o vídeo é renderizado no PC local. Se o PC estiver desligado, a tarefa permanece na fila.</div>
<div class="control"><input id="topic" placeholder="Digite um assunto ou deixe a IA decidir"><button class="btn" onclick="createShort()">PRODUZIR</button></div>
<div class="stats"><div class="stat"><small>ASSUNTOS</small><b id="assuntos">4</b></div><div class="stat"><small>OPORTUNIDADES</small><b id="opps">4</b></div><div class="stat"><small>PRODUZIDOS</small><b id="produzidos">0</b></div><div class="stat"><small>FILA</small><b id="fila">0</b></div></div>
<div class="panel pipeline"><h3>PIPELINE DE PRODUÇÃO</h3><div class="steps">''' + ''.join(f'<div class="step">{x}</div>' for x in ["PESQUISA","ANÁLISE","ROTEIRO","VISUAIS","NARRAÇÃO","EDIÇÃO","AVALIAÇÃO","PRONTO"]) + '''</div></div>
<div class="panel opp"><h3>OPORTUNIDADES ENCONTRADAS</h3><div id="oppList"></div></div><div class="panel jobs"><h3>PRODUÇÕES</h3><div id="jobs">Nenhuma produção iniciada.</div></div></div>
<script>function esc(s){return String(s??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[m]))}async function load(){try{let d=await(await fetch('/api/state')).json();document.getElementById('opps').textContent=d.opportunities.length;document.getElementById('assuntos').textContent=d.opportunities.length;document.getElementById('produzidos').textContent=d.produced;document.getElementById('fila').textContent=d.queue;document.getElementById('oppList').innerHTML=d.opportunities.map(o=>`<div class="row"><div class="score">${o.score}</div><div><div class="title">${esc(o.title)}</div><div class="source">${esc(o.source)}</div></div><div class="pill">${esc(o.priority)}</div><div class="pill">${esc(o.status)}</div><button class="produce" onclick="createShort('${o.id}')">PRODUZIR</button></div>`).join('');renderJobs(d.jobs)}catch(e){}}function renderJobs(js){if(!js.length){document.getElementById('jobs').textContent='Nenhuma produção iniciada.';return}document.getElementById('jobs').innerHTML=js.map(j=>{let p=Math.round(j.progress||0);return `<div class="job"><b>${esc(j.title)}</b><div class="muted">${esc(j.stage)} — ${p}% — ${esc(j.status)}</div><div class="bar"><i style="width:${p}%"></i></div><div class="log">${esc(j.log||'')}</div>${j.video?`<div class="result"><a href="/output/${encodeURIComponent(j.video)}" target="_blank">▶ ABRIR SHORT</a> &nbsp; <a href="/api/job/${j.id}" target="_blank">JSON</a></div>`:''}</div>`}).join('')}async function createShort(id){let topic=document.getElementById('topic').value;let r=await fetch('/api/produce',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:id||null,topic})});let d=await r.json();if(!r.ok){alert(d.error||'Erro');return}load()}async function research(){let r=await fetch('/api/research',{method:'POST'});let d=await r.json();alert(d.message);load()}load();setInterval(load,2500);</script></body></html>'''

def load_jobs():
    if not STATE_FILE.exists(): return {}
    try:return json.loads(STATE_FILE.read_text(encoding='utf8'))
    except:return {}

def save_jobs(jobs):
    tmp=STATE_FILE.with_suffix('.tmp'); tmp.write_text(json.dumps(jobs,ensure_ascii=False,indent=2),encoding='utf8'); tmp.replace(STATE_FILE)

def choose(data):
    if data.get('id'):
        for o in OPPORTUNITIES:
            if o['id']==data['id']: return o
    topic=(data.get('topic') or '').strip()
    return {'id':'custom','score':90,'priority':'ALTA','title':topic or OPPORTUNITIES[0]['title'],'source':'Rockstar Games','url':'https://www.rockstargames.com/VI','status':'PRODUZIR'}

def auth_worker():
    if not WORKER_TOKEN: return False
    return request.headers.get('X-Worker-Token','') == WORKER_TOKEN

@APP.get('/')
def home(): return render_template_string(PAGE)
@APP.get('/health')
def health(): return jsonify(ok=True,app='GTA Oculto AI',version='4.0',worker_configured=bool(WORKER_TOKEN))
@APP.get('/api/state')
def state():
    with LOCK:
        jobs=load_jobs(); js=list(jobs.values())[-30:]
        return jsonify(opportunities=OPPORTUNITIES,jobs=js,produced=sum(x.get('status')=='DONE' for x in js),queue=sum(x.get('status') in ('QUEUED','RUNNING') for x in js))
@APP.post('/api/research')
def research(): return jsonify(ok=True,message='Pesquisa oficial pronta.')
@APP.post('/api/produce')
def produce():
    data=request.get_json(silent=True) or {}; o=choose(data); jid=uuid.uuid4().hex[:10]
    job={'id':jid,'title':o['title'],'opportunity':o,'status':'QUEUED','stage':'FILA','progress':0,'log':'Aguardando o PC produtor...','video':None,'created_at':datetime.utcnow().isoformat()+'Z'}
    with LOCK:
        jobs=load_jobs(); jobs[jid]=job; save_jobs(jobs)
    return jsonify(ok=True,job_id=jid)

@APP.post('/api/worker/claim')
def worker_claim():
    if not auth_worker(): return jsonify(error='worker não autorizado'),401
    with LOCK:
        jobs=load_jobs()
        # recuperar tarefa presa em RUNNING há mais de 30 min
        for j in jobs.values():
            if j.get('status')=='RUNNING':
                try:
                    t=datetime.fromisoformat(j.get('heartbeat','').replace('Z','+00:00'))
                    if (datetime.now(t.tzinfo)-t).total_seconds()>1800: j['status']='QUEUED'; j['stage']='FILA'; j['log']='Tarefa recuperada após perda do produtor.'
                except: pass
        target=next((j for j in jobs.values() if j.get('status')=='QUEUED'),None)
        if not target: save_jobs(jobs); return jsonify(job=None)
        target['status']='RUNNING'; target['stage']='PESQUISA'; target['progress']=2; target['log']='PC produtor conectado e iniciou a tarefa.'; target['heartbeat']=datetime.utcnow().isoformat()+'Z'; save_jobs(jobs)
        return jsonify(job=target)

@APP.post('/api/worker/update')
def worker_update():
    if not auth_worker(): return jsonify(error='worker não autorizado'),401
    data=request.get_json(silent=True) or {}; jid=data.get('id')
    with LOCK:
        jobs=load_jobs(); j=jobs.get(jid)
        if not j:return jsonify(error='job not found'),404
        for k in ('status','stage','progress','log','video','score'):
            if k in data:j[k]=data[k]
        j['heartbeat']=datetime.utcnow().isoformat()+'Z'; save_jobs(jobs)
    return jsonify(ok=True)

@APP.post('/api/worker/complete')
def worker_complete():
    if not auth_worker(): return jsonify(error='worker não autorizado'),401
    data=request.get_json(silent=True) or {}; jid=data.get('id')
    with LOCK:
        jobs=load_jobs(); j=jobs.get(jid)
        if not j:return jsonify(error='job not found'),404
        j.update(status='DONE',stage='PRONTO',progress=100,log=data.get('log','PRONTO — revisão humana recomendada.'),video=data.get('video'),score=data.get('score',0),heartbeat=datetime.utcnow().isoformat()+'Z'); save_jobs(jobs)
    return jsonify(ok=True)

@APP.post('/api/worker/error')
def worker_error():
    if not auth_worker(): return jsonify(error='worker não autorizado'),401
    data=request.get_json(silent=True) or {}; jid=data.get('id')
    with LOCK:
        jobs=load_jobs(); j=jobs.get(jid)
        if not j:return jsonify(error='job not found'),404
        j.update(status='ERROR',stage='ERRO',progress=j.get('progress',0),log=data.get('error','Erro desconhecido'),heartbeat=datetime.utcnow().isoformat()+'Z'); save_jobs(jobs)
    return jsonify(ok=True)

@APP.get('/api/job/<jid>')
def one(jid):
    j=load_jobs().get(jid)
    if not j:return jsonify(error='not found'),404
    return jsonify(j)

@APP.post('/api/worker/upload/<jid>')
def worker_upload(jid):
    if not auth_worker(): return jsonify(error='worker não autorizado'),401
    f=request.files.get('video')
    if not f:return jsonify(error='video ausente'),400
    jobdir=WORK/jid; jobdir.mkdir(exist_ok=True); dest=jobdir/'GTA_OCULTO_SHORT.mp4'; f.save(dest)
    return jsonify(ok=True,video=f'{jid}/GTA_OCULTO_SHORT.mp4')

@APP.get('/output/<path:p>')
def output(p):
    full=(WORK/p).resolve()
    if not str(full).startswith(str(WORK.resolve())) or not full.exists():return 'Not found',404
    return send_from_directory(full.parent,full.name,as_attachment=False)

if __name__=='__main__': APP.run(host='0.0.0.0',port=int(os.environ.get('PORT',5000)))

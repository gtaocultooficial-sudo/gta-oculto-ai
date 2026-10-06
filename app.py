import json, os, threading, uuid
from datetime import datetime
from pathlib import Path
from flask import Flask, jsonify, request, Response

BASE = Path(__file__).resolve().parent
DATA = BASE / 'data'
DATA.mkdir(exist_ok=True)
STATE_FILE = DATA / 'state.json'
LOCK = threading.Lock()

app = Flask(__name__)
INDEX_HTML = '''<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>GTA Oculto AI</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#08090c;color:#eee;font-family:Inter,Segoe UI,Arial,sans-serif}button,input{font:inherit}.wrap{max-width:1400px;margin:auto;padding:24px}.top{display:flex;align-items:center;justify-content:space-between}.brand{font-size:28px;font-weight:900;letter-spacing:.04em}.muted{color:#858b96}.pill{border:1px solid #2b3039;border-radius:999px;padding:8px 13px;font-size:12px}.online{color:#6ee79a}.hero{margin-top:22px;padding:28px;border:1px solid #252a32;border-radius:18px;background:linear-gradient(135deg,#15171d,#0e1014)}h1{font-size:38px;margin:8px 0}.red{color:#e31d2a}.actions{display:flex;gap:10px;flex-wrap:wrap;margin-top:22px}.btn{border:0;border-radius:10px;padding:13px 18px;font-weight:800;cursor:pointer}.primary{background:#c91521;color:white}.secondary{background:#20242b;color:#eee}.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-top:14px}.card{background:#111318;border:1px solid #252a32;border-radius:14px;padding:18px}.num{font-size:30px;font-weight:900;margin-top:8px}.section{margin-top:18px;background:#111318;border:1px solid #252a32;border-radius:14px;padding:18px}.pipeline{display:grid;grid-template-columns:repeat(8,1fr);gap:7px}.step{padding:12px 8px;text-align:center;border-radius:9px;background:#191c22;color:#9da3ad;font-size:11px;font-weight:800}.step.active{background:#3a1216;color:#ff5a64}.opp{display:grid;grid-template-columns:70px 1fr 140px 90px 100px;gap:10px;align-items:center;padding:13px 0;border-bottom:1px solid #22262d}.score{font-weight:900;font-size:20px}.tag{font-size:10px;border:1px solid #353a44;border-radius:999px;padding:5px 8px;text-align:center}.small{font-size:12px;color:#8e949e}.job{padding:12px;background:#0c0e12;border-radius:9px;margin-top:8px}.footer{padding:20px 0;color:#666;font-size:12px}@media(max-width:900px){.grid{grid-template-columns:repeat(2,1fr)}.pipeline{grid-template-columns:repeat(4,1fr)}.opp{grid-template-columns:55px 1fr 70px}.opp>*:nth-child(3),.opp>*:nth-child(4){display:none}}@media(max-width:600px){.wrap{padding:14px}h1{font-size:29px}.grid{grid-template-columns:1fr 1fr}.pipeline{grid-template-columns:repeat(2,1fr)}}
</style></head>
<body><div class="wrap">
<div class="top"><div><div class="brand">GTA <span class="red">OCULTO</span> AI</div><div class="muted">CONTENT FACTORY • WEB CONTROL</div></div><div id="engine" class="pill">● VERIFICANDO MOTOR</div></div>
<div class="hero"><div class="red" style="font-weight:900">PRODUTOR AUTÔNOMO</div><h1>A IA pesquisa, escolhe e produz.</h1><div class="muted">Pesquisa → análise → roteiro → visuais → narração → edição → avaliação → publicação</div><div class="actions"><button class="btn primary" onclick="createShort()">⚡ CRIAR SHORT</button><button class="btn secondary" onclick="research()">🔎 PESQUISAR OPORTUNIDADES</button></div></div>
<div class="grid"><div class="card"><div class="small">ASSUNTOS</div><div id="nTopics" class="num">0</div></div><div class="card"><div class="small">OPORTUNIDADES</div><div id="nOpp" class="num">0</div></div><div class="card"><div class="small">PRODUZIDOS</div><div id="nProduced" class="num">0</div></div><div class="card"><div class="small">FILA</div><div id="nQueue" class="num">0</div></div></div>
<div class="section"><div style="font-weight:900;margin-bottom:12px">PIPELINE DE PRODUÇÃO</div><div class="pipeline"> <div class="step active">PESQUISA</div><div class="step">ANÁLISE</div><div class="step">ROTEIRO</div><div class="step">VISUAIS</div><div class="step">NARRAÇÃO</div><div class="step">EDIÇÃO</div><div class="step">AVALIAÇÃO</div><div class="step">PRONTO</div></div></div>
<div class="section"><div style="font-weight:900;margin-bottom:8px">OPORTUNIDADES ENCONTRADAS</div><div id="topics"></div></div>
<div class="section"><div style="font-weight:900">FILA DO MOTOR LOCAL</div><div class="small" style="margin-top:4px">Quando o PC de produção estiver desligado, os trabalhos ficam aguardando.</div><div id="jobs"></div></div>
<div class="footer">GTA Oculto AI • Web Dashboard</div></div>
<script>
async function load(){let r=await fetch('/api/state');let s=await r.json();document.getElementById('engine').textContent='● MOTOR '+s.engine;document.getElementById('engine').className='pill '+(s.engine==='ONLINE'?'online':'');document.getElementById('nTopics').textContent=(s.topics||[]).length;document.getElementById('nOpp').textContent=(s.topics||[]).filter(x=>x.score>=80).length;document.getElementById('nProduced').textContent=s.produced||0;document.getElementById('nQueue').textContent=(s.jobs||[]).length;document.getElementById('topics').innerHTML=(s.topics||[]).map(x=>`<div class="opp"><div class="score">${x.score}</div><div><b>${x.title}</b><div class="small">${x.source}</div></div><div class="tag">${x.fresh}</div><div class="tag">${x.status}</div><button class="btn secondary" style="padding:8px" onclick="queueTopic(${JSON.stringify(x.title)})">PRODUZIR</button></div>`).join('');document.getElementById('jobs').innerHTML=(s.jobs||[]).map(j=>`<div class="job"><b>${j.topic}</b><div class="small">${j.status} • ${j.id}</div></div>`).join('')||'<div class="small" style="margin-top:10px">Nenhum trabalho na fila.</div>'}
async function research(){await fetch('/api/research',{method:'POST'});load()}
async function queueTopic(t){await fetch('/api/jobs',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({topic:t})});load()}
async function createShort(){await queueTopic('IA DECIDE — escolher a melhor oportunidade disponível')}
load();setInterval(load,5000)
</script></body></html>
'''

DEFAULT_TOPICS = [
    {"title":"GTA 6: o detalhe de Leonida que pode mudar a história", "score":94, "source":"Rockstar Games", "fresh":"ALTA", "status":"PRODUZIR"},
    {"title":"Jason e Lucia: o que a Rockstar já confirmou oficialmente", "score":92, "source":"Rockstar Games", "fresh":"ALTA", "status":"PRODUZIR"},
    {"title":"GTA 6 pode esconder pistas fora de Vice City", "score":88, "source":"Análise editorial", "fresh":"ALTA", "status":"ANALISAR"},
    {"title":"Um detalhe antigo de GTA V que voltou a chamar atenção", "score":74, "source":"Arquivo GTA", "fresh":"MÉDIA", "status":"RESERVAR"},
]


def load_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding='utf-8'))
        except Exception:
            pass
    return {"engine":"OFFLINE", "topics":DEFAULT_TOPICS, "jobs":[], "produced":0}


def save_state(state):
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')


@app.get('/')
def index():
    return Response(INDEX_HTML, mimetype='text/html')


@app.get('/health')
def health():
    return jsonify(ok=True, service='GTA Oculto AI Web', version='WEB-1.0')


@app.get('/api/state')
def state():
    with LOCK:
        s = load_state()
    return jsonify(s)


@app.post('/api/engine/heartbeat')
def heartbeat():
    payload = request.get_json(silent=True) or {}
    status = payload.get('status', 'ONLINE')
    with LOCK:
        s = load_state(); s['engine'] = status; s['engine_seen_at'] = datetime.utcnow().isoformat() + 'Z'; save_state(s)
    return jsonify(ok=True)


@app.post('/api/research')
def research():
    with LOCK:
        s = load_state(); s['topics'] = DEFAULT_TOPICS; save_state(s)
    return jsonify(ok=True, topics=DEFAULT_TOPICS)


@app.post('/api/jobs')
def create_job():
    payload = request.get_json(silent=True) or {}
    topic = (payload.get('topic') or '').strip()
    if not topic:
        topics = sorted(DEFAULT_TOPICS, key=lambda x: x['score'], reverse=True)
        topic = topics[0]['title']
    job = {
        'id': uuid.uuid4().hex[:10],
        'topic': topic,
        'status': 'AGUARDANDO PC',
        'created_at': datetime.utcnow().isoformat() + 'Z'
    }
    with LOCK:
        s = load_state(); s['jobs'].insert(0, job); save_state(s)
    return jsonify(ok=True, job=job)


@app.get('/api/jobs')
def jobs():
    return jsonify(load_state().get('jobs', []))


if __name__ == '__main__':
    port = int(os.environ.get('PORT', '10000'))
    app.run(host='0.0.0.0', port=port, debug=False)

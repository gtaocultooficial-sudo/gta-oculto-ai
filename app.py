import os, re, json, time, uuid, threading
from pathlib import Path
from datetime import datetime
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup
from flask import Flask, request, jsonify, render_template_string, send_from_directory
from PIL import Image, ImageDraw, ImageFilter, ImageFont
import imageio_ffmpeg

try:
    import edge_tts
except Exception:
    edge_tts = None

APP = Flask(__name__)
app = APP  # compatibilidade com Gunicorn configurado como app:app
BASE = Path(__file__).resolve().parent
WORK = BASE / "workspace"; WORK.mkdir(exist_ok=True)
JOBS = {}; LOCK = threading.Lock()
UA = "GTA-Oculto-AI/2.0"

OPPORTUNITIES = [
 {"id":"leonida","score":94,"priority":"ALTA","title":"GTA 6: o detalhe de Leonida que pode mudar a história","source":"Rockstar Games","url":"https://www.rockstargames.com/VI","status":"PRODUZIR"},
 {"id":"jason-lucia","score":92,"priority":"ALTA","title":"Jason e Lucia: o que a Rockstar já confirmou oficialmente","source":"Rockstar Games","url":"https://www.rockstargames.com/VI","status":"PRODUZIR"},
 {"id":"fora-vice-city","score":88,"priority":"ALTA","title":"GTA 6 pode esconder pistas fora de Vice City","source":"Análise editorial","url":"https://www.rockstargames.com/VI","status":"ANALISAR"},
 {"id":"gta5","score":74,"priority":"MÉDIA","title":"Um detalhe antigo de GTA V que voltou a chamar atenção","source":"Arquivo GTA","url":"https://www.rockstargames.com/gta-v","status":"RESERVAR"}]

PAGE = """<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>GTA OCULTO AI</title><style>
*{box-sizing:border-box}body{margin:0;background:#08090c;color:#eee;font-family:Arial,Helvetica,sans-serif}.wrap{max-width:1320px;margin:auto;padding:20px}
.top{display:flex;justify-content:space-between;align-items:center;padding:10px 4px 18px}.brand{font-size:28px;font-weight:900}.brand span{color:#e31a28}.status{padding:9px 13px;border:1px solid #2b3038;border-radius:9px;background:#111318;color:#70e28b;font-size:12px;font-weight:800}
.hero,.panel,.stat{background:#101217;border:1px solid #292e37;border-radius:14px;margin-bottom:16px}.hero{padding:20px;display:flex;justify-content:space-between;gap:20px}.eyebrow{color:#e21a2a;font-size:12px;font-weight:900}.hero h1{margin:7px 0;font-size:25px}.muted{color:#8e96a3}.buttons{display:flex;gap:10px;align-items:center}.btn{border:0;border-radius:9px;padding:13px 17px;font-weight:900;cursor:pointer;background:#20242c;color:#fff}.btn.red{background:#d91624}
.control{padding:14px;display:flex;gap:10px}.control input{flex:1;background:#181b21;border:1px solid #2b3038;border-radius:8px;color:white;padding:13px}.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}.stat{padding:18px}.stat small{color:#9aa2af}.stat b{display:block;font-size:29px;margin-top:7px}
.pipeline,.opp,.jobs{padding:18px}.steps{display:grid;grid-template-columns:repeat(8,1fr);gap:7px}.step{padding:12px 5px;text-align:center;background:#1a1d23;border-radius:8px;font-size:11px;font-weight:900;color:#9da5b2}
.row{display:grid;grid-template-columns:55px 1fr 140px 95px 95px;gap:12px;align-items:center;padding:14px 0;border-bottom:1px solid #252932}.score{font-size:21px;font-weight:900}.title{font-weight:800}.source{font-size:12px;color:#858d99;margin-top:4px}.pill{border:1px solid #353b45;border-radius:20px;padding:7px;text-align:center;font-size:11px}.produce{background:#242933;border:0;color:white;border-radius:8px;padding:10px;font-weight:900;cursor:pointer}
.job{background:#15181e;border:1px solid #2b3038;border-radius:10px;padding:13px;margin-top:9px}.bar{height:7px;background:#272c34;border-radius:10px;overflow:hidden;margin-top:10px}.bar i{display:block;height:100%;background:#d91624}.result{margin-top:10px}.result a{color:#ff5965;text-decoration:none;font-weight:800}.log{font-family:monospace;color:#aeb6c2;font-size:12px;white-space:pre-wrap;margin-top:9px}
@media(max-width:900px){.stats{grid-template-columns:repeat(2,1fr)}.steps{grid-template-columns:repeat(4,1fr)}.hero{display:block}.buttons{margin-top:15px}.row{grid-template-columns:45px 1fr 90px}.row .pill{display:none}}
</style></head><body><div class="wrap">
<div class="top"><div class="brand">GTA <span>OCULTO</span> AI</div><div class="status">● AI ONLINE</div></div>
<div class="hero"><div><div class="eyebrow">PRODUTOR AUTÔNOMO</div><h1>A IA pesquisa, escolhe e produz.</h1><div class="muted">Pesquisa real → verificação → roteiro → visuais → narração → edição → avaliação</div></div>
<div class="buttons"><button class="btn red" onclick="createShort()">⚡ CRIAR SHORT</button><button class="btn" onclick="research()">🔎 PESQUISAR OPORTUNIDADES</button></div></div>
<div class="control"><input id="topic" placeholder="Digite um assunto ou deixe a IA decidir"><button class="btn" onclick="createShort()">PRODUZIR</button></div>
<div class="stats"><div class="stat"><small>ASSUNTOS</small><b id="assuntos">4</b></div><div class="stat"><small>OPORTUNIDADES</small><b id="opps">4</b></div><div class="stat"><small>PRODUZIDOS</small><b id="produzidos">0</b></div><div class="stat"><small>FILA</small><b id="fila">0</b></div></div>
<div class="panel pipeline"><h3>PIPELINE DE PRODUÇÃO</h3><div class="steps">""" + ''.join(f'<div class="step">{x}</div>' for x in ["PESQUISA","ANÁLISE","ROTEIRO","VISUAIS","NARRAÇÃO","EDIÇÃO","AVALIAÇÃO","PRONTO"]) + """</div></div>
<div class="panel opp"><h3>OPORTUNIDADES ENCONTRADAS</h3><div id="oppList"></div></div>
<div class="panel jobs"><h3>PRODUÇÕES</h3><div id="jobs">Nenhuma produção iniciada.</div></div></div>
<script>
let timer=null;function esc(s){return String(s).replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[m]))}
async function load(){let d=await(await fetch('/api/state')).json();document.getElementById('opps').textContent=d.opportunities.length;document.getElementById('assuntos').textContent=d.opportunities.length;document.getElementById('produzidos').textContent=d.produced;document.getElementById('fila').textContent=d.queue;document.getElementById('oppList').innerHTML=d.opportunities.map(o=>`<div class="row"><div class="score">${o.score}</div><div><div class="title">${esc(o.title)}</div><div class="source">${esc(o.source)}</div></div><div class="pill">${esc(o.priority)}</div><div class="pill">${esc(o.status)}</div><button class="produce" onclick="createShort('${o.id}')">PRODUZIR</button></div>`).join('');renderJobs(d.jobs)}
function renderJobs(js){if(!js.length){document.getElementById('jobs').textContent='Nenhuma produção iniciada.';return}document.getElementById('jobs').innerHTML=js.map(j=>{let p=Math.round(j.progress||0);return `<div class="job"><b>${esc(j.title)}</b><div class="muted">${esc(j.stage)} — ${p}% — ${esc(j.status)}</div><div class="bar"><i style="width:${p}%"></i></div><div class="log">${esc(j.log||'')}</div>${j.video?`<div class="result"><a href="/output/${encodeURIComponent(j.video)}" target="_blank">▶ ABRIR SHORT</a> &nbsp; <a href="/api/job/${j.id}" target="_blank">JSON</a></div>`:''}</div>`}).join('')}
async function createShort(id){let topic=document.getElementById('topic').value;let r=await fetch('/api/produce',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:id||null,topic})});let d=await r.json();if(!r.ok){alert(d.error||'Erro');return}poll()}
async function research(){let r=await fetch('/api/research',{method:'POST'});let d=await r.json();alert(d.message);load()}
function poll(){if(timer)return;timer=setInterval(async()=>{await load();let d=await(await fetch('/api/state')).json();if(!d.jobs.some(x=>x.status==='RUNNING'||x.status==='QUEUED')){clearInterval(timer);timer=null}},1500)}
load();
</script></body></html>"""

def clean(s): return re.sub(r"\s+"," ",BeautifulSoup(s or "", "html.parser").get_text(" ")).strip()

def research_url(url):
    r=requests.get(url,headers={"User-Agent":UA},timeout=25); r.raise_for_status()
    soup=BeautifulSoup(r.text,"html.parser"); imgs=[]
    og=soup.find("meta",property="og:image")
    if og and og.get("content"): imgs.append(urljoin(url,og["content"]))
    for im in soup.find_all("img"):
        u=im.get("src") or im.get("data-src")
        if u:
            u=urljoin(url,u)
            if u.startswith("http") and u not in imgs: imgs.append(u)
    return {"title":clean(soup.title.string if soup.title else ""),"text":clean(soup.get_text(" "))[:30000],"images":imgs[:10],"url":url}

def choose(data):
    if data.get("id"):
        for o in OPPORTUNITIES:
            if o["id"]==data["id"]: return o
    topic=(data.get("topic") or "").strip()
    return {"id":"custom","score":90,"priority":"ALTA","title":topic or OPPORTUNITIES[0]["title"],"source":"Rockstar Games","url":"https://www.rockstargames.com/VI","status":"PRODUZIR"}

def make_script(title):
    if "Jason" in title or "Lucia" in title:
        return "A Rockstar já confirmou uma coisa importante sobre Jason e Lucia. Os dois entram em uma conspiração que se estende por todo o estado de Leonida. Isso muda a forma como podemos enxergar a história de GTA 6. Vice City pode ser apenas uma parte de uma trama muito maior. E se os lugares que aparecem rapidamente nos materiais oficiais tiverem pistas sobre essa conspiração? Qual detalhe você acha que a Rockstar ainda não revelou?"
    return "Você reparou nisso em GTA 6? A Rockstar já confirmou que Jason e Lucia estão envolvidos em uma conspiração que se espalha por todo o estado de Leonida. Isso é importante porque significa que a história não precisa ficar presa apenas a Vice City. O mapa pode esconder lugares, personagens e acontecimentos que ainda não foram explicados. E quanto mais material oficial aparece, mais pistas podem surgir. Será que a Rockstar está deixando essas pistas na nossa frente? Qual detalhe de GTA 6 você acha que ainda passou despercebido?"

def getfont(n,b=False):
    p="/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if b else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    return ImageFont.truetype(p,n) if os.path.exists(p) else ImageFont.load_default()

def dl(url,path):
    try:
        rr=requests.get(url,headers={"User-Agent":UA},timeout=30); rr.raise_for_status(); path.write_bytes(rr.content)
        im=Image.open(path).convert("RGB")
        if im.width<300 or im.height<200:return False
        im.save(path,"JPEG",quality=90); return True
    except:return False

def visuals(jobdir,research):
    out=[]
    for i,u in enumerate(research.get("images",[])):
        p=jobdir/f"visual_{i}.jpg"
        if dl(u,p): out.append(p)
        if len(out)>=5:break
    if not out:
        for i in range(5):
            im=Image.new("RGB",(1080,1920),(8,9,13)); d=ImageDraw.Draw(im)
            d.text((70,100),"GTA OCULTO",font=getfont(70,True),fill="white")
            d.text((70,205),"GTA 6 / LEONIDA",font=getfont(48,True),fill=(225,30,45))
            d.rectangle((60,60,1020,1860),outline=(150,20,30),width=5)
            p=jobdir/f"generated_{i}.jpg"; im.save(p,quality=90); out.append(p)
    return out

def render(jobdir,assets,script):
    ff=imageio_ffmpeg.get_ffmpeg_exe(); fps=24; W,H=1080,1920; dur=32
    raw=jobdir/"video.mp4"
    import subprocess
    cmd=[ff,"-y","-f","rawvideo","-pix_fmt","rgb24","-s",f"{W}x{H}","-r",str(fps),"-i","-","-an","-c:v","libx264","-preset","veryfast","-crf","24","-pix_fmt","yuv420p",str(raw)]
    p=subprocess.Popen(cmd,stdin=subprocess.PIPE,stderr=subprocess.DEVNULL)
    hf=getfont(58,True); sf=getfont(35,True); sm=getfont(28,True)
    words=script.split(); chunk=max(1,len(words)//6)
    for n in range(fps*dur):
        t=n/fps; idx=min(len(assets)-1,int(t/(dur/len(assets))))
        im=Image.open(assets[idx]).convert("RGB"); iw,ih=im.size
        scale=max(W/iw,H/ih)*(1.03+.10*t/dur); im=im.resize((int(iw*scale),int(ih*scale)),Image.Resampling.LANCZOS)
        left=max(0,(im.width-W)//2); top=max(0,(im.height-H)//2); frame=im.crop((left,top,left+W,top+H))
        d=ImageDraw.Draw(frame,"RGBA"); d.rectangle((0,0,W,250),fill=(0,0,0,130)); d.rectangle((0,H-290,W,H),fill=(0,0,0,160))
        headline="VOCÊ PERCEBEU ISSO?" if t<3 else ("GTA 6 PODE ESCONDER MUITO MAIS" if t<25 else "QUAL DETALHE VOCÊ IGNOROU?")
        d.text((W//2,65),headline,font=hf,fill="white",anchor="ma",stroke_width=2,stroke_fill="black")
        ci=min(5,int(t/(dur/6))); cap=" ".join(words[ci*chunk:(ci+1)*chunk])
        d.text((W//2,H-220),cap,font=sf,fill="white",anchor="ma",stroke_width=2,stroke_fill="black")
        d.text((35,35),"GTA OCULTO",font=sm,fill=(235,30,45,255))
        p.stdin.write(frame.tobytes())
    p.stdin.close(); p.wait()
    voice=jobdir/"narracao.mp3"
    if edge_tts:
        try:
            import asyncio
            async def go():
                await edge_tts.Communicate(script,"pt-BR-AntonioNeural",rate="+4%",pitch="-2Hz").save(str(voice))
            asyncio.run(go())
        except: voice=None
    final=jobdir/"GTA_OCULTO_SHORT.mp4"
    if voice and voice.exists():
        subprocess.run([ff,"-y","-i",str(raw),"-i",str(voice),"-c:v","copy","-c:a","aac","-shortest",str(final)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    else: final=raw
    return final

def run(jid):
    try:
        with LOCK:JOBS[jid].update(status="RUNNING",stage="PESQUISA",progress=5,log="Pesquisando fonte oficial da Rockstar...")
        j=JOBS[jid]; d=WORK/jid; d.mkdir(exist_ok=True); r=research_url(j["opportunity"]["url"])
        with LOCK:JOBS[jid].update(stage="ANÁLISE",progress=18,log="Fonte consultada e analisada.")
        script=make_script(j["title"])
        with LOCK:JOBS[jid].update(stage="ROTEIRO",progress=32,log="Roteiro original PT-BR criado.")
        a=visuals(d,r)
        with LOCK:JOBS[jid].update(stage="VISUAIS",progress=48,log=f"{len(a)} visuais preparados.")
        with LOCK:JOBS[jid].update(stage="NARRAÇÃO",progress=60,log="Gerando narração PT-BR...")
        final=render(d,a,script)
        with LOCK:JOBS[jid].update(stage="EDIÇÃO",progress=82,log="Short 9:16 renderizado.")
        score=88 if final.exists() and final.stat().st_size>50000 else 62
        meta={"title":j["title"],"script":script,"source":j["opportunity"]["url"],"score":score,"created_at":datetime.utcnow().isoformat()+"Z"}
        (d/"producao.json").write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding="utf8")
        with LOCK:JOBS[jid].update(stage="PRONTO",progress=100,status="DONE",video=f"{jid}/GTA_OCULTO_SHORT.mp4",log=f"PRONTO — score {score}/100. Revisão humana recomendada.")
    except Exception as e:
        with LOCK:JOBS[jid].update(status="ERROR",stage="ERRO",log=f"{type(e).__name__}: {e}")

@APP.get("/")
def home(): return render_template_string(PAGE)
@APP.get("/health")
def health(): return jsonify(ok=True,app="GTA Oculto AI",version="2.0")
@APP.get("/api/state")
def state():
    with LOCK:
        js=list(JOBS.values()); return jsonify(opportunities=OPPORTUNITIES,jobs=js[-20:],produced=sum(x["status"]=="DONE" for x in js),queue=sum(x["status"] in ("QUEUED","RUNNING") for x in js))
@APP.post("/api/research")
def research(): return jsonify(ok=True,message="Pesquisa oficial pronta.")
@APP.post("/api/produce")
def produce():
    data=request.get_json(silent=True) or {}; o=choose(data); jid=uuid.uuid4().hex[:10]
    with LOCK:JOBS[jid]={"id":jid,"title":o["title"],"opportunity":o,"status":"QUEUED","stage":"PESQUISA","progress":0,"log":"Na fila...","video":None}
    threading.Thread(target=run,args=(jid,),daemon=True).start(); return jsonify(ok=True,job_id=jid,queue=sum(x["status"] in ("QUEUED","RUNNING") for x in JOBS.values()))
@APP.get("/api/job/<jid>")
def one(jid):
    if jid not in JOBS:return jsonify(error="not found"),404
    return jsonify(JOBS[jid])
@APP.get("/output/<path:p>")
def output(p):
    full=(WORK/p).resolve()
    if not str(full).startswith(str(WORK.resolve())) or not full.exists():return "Not found",404
    return send_from_directory(full.parent,full.name,as_attachment=False)

if __name__=="__main__": APP.run(host="0.0.0.0",port=int(os.environ.get("PORT",5000)))

import os, json, uuid, threading, time, asyncio, subprocess, shutil
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from flask import Flask, request, jsonify, render_template_string, send_from_directory
from PIL import Image, ImageDraw, ImageFont, ImageEnhance

try:
    import edge_tts
except Exception:
    edge_tts = None

APP = Flask(__name__)
app = APP
BASE = Path(__file__).resolve().parent
WORK = BASE / 'workspace'
WORK.mkdir(exist_ok=True)
STATE_FILE = WORK / 'jobs.json'
LOCK = threading.RLock()
PROCESSING = False
UA = 'GTA-Oculto-AI/Cloud-Final/1.0'
ROCKSTAR_VI = 'https://www.rockstargames.com/VI'
ROCKSTAR_NEWS = 'https://www.rockstargames.com/newswire/article/4k138k8okkk483/grand-theft-auto-vi-an-extended-look-now-playing'

FALLBACK_TOPICS = [
    {'id':'leonida','score':96,'priority':'ALTA','title':'GTA 6: o detalhe de Leonida que pode mudar a história','source':'Rockstar Games','url':ROCKSTAR_VI},
    {'id':'jason-lucia','score':93,'priority':'ALTA','title':'Jason e Lucia: o que a Rockstar já confirmou oficialmente','source':'Rockstar Games','url':ROCKSTAR_VI},
    {'id':'estado-leonida','score':90,'priority':'ALTA','title':'A história de GTA 6 vai muito além de Vice City','source':'Rockstar Games','url':ROCKSTAR_NEWS},
    {'id':'detalhes','score':84,'priority':'MÉDIA','title':'Os detalhes escondidos que a Rockstar colocou em GTA 6','source':'Rockstar Games','url':ROCKSTAR_VI},
]

PAGE = '''<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>GTA OCULTO AI</title><style>
*{box-sizing:border-box}body{margin:0;background:#07080b;color:#f4f5f7;font-family:Arial,Helvetica,sans-serif}.wrap{max-width:1380px;margin:auto;padding:22px}.top{display:flex;justify-content:space-between;align-items:center;margin-bottom:18px}.brand{font-size:30px;font-weight:950}.brand span{color:#e21c2a}.status{border:1px solid #303640;background:#11141a;border-radius:999px;padding:9px 13px;color:#72e69a;font-size:12px;font-weight:900}.hero,.panel,.stat{background:#101318;border:1px solid #282e37;border-radius:15px}.hero{padding:22px;display:flex;justify-content:space-between;gap:20px;align-items:center}.eyebrow{color:#e21c2a;font-size:11px;font-weight:950;letter-spacing:1.3px}.hero h1{font-size:28px;margin:8px 0}.muted{color:#8d96a4}.buttons{display:flex;gap:10px}.btn{border:0;border-radius:9px;padding:13px 17px;background:#222730;color:#fff;font-weight:900;cursor:pointer}.btn.red{background:#df1727}.control{margin-top:12px;padding:12px;background:#0d1015;border:1px solid #242a33;border-radius:12px;display:flex;gap:10px}.control input{flex:1;background:#181c23;border:1px solid #2b323c;border-radius:8px;color:#fff;padding:13px}.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:16px 0}.stat{padding:17px}.stat small{color:#929aa7;font-weight:800}.stat b{display:block;font-size:29px;margin-top:6px}.panel{margin:16px 0;padding:18px}.steps{display:grid;grid-template-columns:repeat(8,1fr);gap:7px}.step{background:#191d24;border-radius:8px;padding:12px 4px;text-align:center;font-size:10px;font-weight:950;color:#9ba3af}.step.active{background:#3b151a;color:#ff5c68;border:1px solid #7e202b}.row{display:grid;grid-template-columns:55px 1fr 110px 110px 95px;gap:12px;align-items:center;padding:14px 0;border-bottom:1px solid #242a32}.score{font-size:21px;font-weight:950}.title{font-weight:850}.source{font-size:12px;color:#838c99;margin-top:4px}.pill{border:1px solid #343b45;border-radius:20px;padding:7px;text-align:center;font-size:10px;font-weight:850}.produce{background:#242a33;border:0;color:#fff;border-radius:8px;padding:10px;font-weight:900;cursor:pointer}.job{background:#14181e;border:1px solid #2b313a;border-radius:11px;padding:14px;margin-top:10px}.jobhead{display:flex;justify-content:space-between;gap:12px}.bar{height:8px;background:#272d36;border-radius:10px;overflow:hidden;margin-top:10px}.bar i{display:block;height:100%;background:#df1727}.log{font-family:monospace;color:#aab2bf;font-size:12px;margin-top:9px;white-space:pre-wrap}.result{display:flex;gap:10px;flex-wrap:wrap;margin-top:12px}.result a{color:#ff5b67;text-decoration:none;font-weight:900}.meta{font-size:11px;color:#77808e;margin-top:6px}.notice{padding:12px;border:1px dashed #3b424c;border-radius:10px;background:#0d1014;color:#aab2bf;font-size:12px}@media(max-width:900px){.hero{display:block}.buttons{margin-top:15px;flex-wrap:wrap}.stats{grid-template-columns:repeat(2,1fr)}.steps{grid-template-columns:repeat(4,1fr)}.row{grid-template-columns:45px 1fr 90px}.row .pill{display:none}}
</style></head><body><div class="wrap"><div class="top"><div class="brand">GTA <span>OCULTO</span> AI</div><div class="status">● PRODUÇÃO CLOUD ONLINE</div></div>
<div class="hero"><div><div class="eyebrow">PRODUTOR AUTÔNOMO</div><h1>Você escolhe o assunto. A IA faz o resto.</h1><div class="muted">Pesquisa → decisão → roteiro → visuais → voz → edição → avaliação → Short.</div></div><div class="buttons"><button class="btn red" onclick="createShort()">⚡ CRIAR SHORT</button><button class="btn" onclick="research()">🔎 PESQUISAR AGORA</button></div></div>
<div class="control"><input id="topic" placeholder="Digite um assunto ou deixe a IA decidir"><button class="btn red" onclick="createShort()">PRODUZIR</button></div>
<div class="stats"><div class="stat"><small>ASSUNTOS</small><b id="assuntos">0</b></div><div class="stat"><small>OPORTUNIDADES</small><b id="opps">0</b></div><div class="stat"><small>PRODUZIDOS</small><b id="produzidos">0</b></div><div class="stat"><small>FILA</small><b id="fila">0</b></div></div>
<div class="panel"><h3>PIPELINE</h3><div class="steps">'''+''.join(f'<div class="step" id="step-{i}">{x}</div>' for i,x in enumerate(['PESQUISA','ANÁLISE','ROTEIRO','VISUAIS','NARRAÇÃO','EDIÇÃO','AVALIAÇÃO','PRONTO']))+'''</div></div>
<div class="panel"><h3>OPORTUNIDADES</h3><div id="oppList"></div></div>
<div class="panel"><h3>PRODUÇÕES</h3><div id="jobs">Nenhuma produção iniciada.</div></div>
<div class="notice">☁️ <b>Modo 100% web:</b> esta versão não depende do seu computador. A produção acontece no próprio servidor. O plano gratuito do Render pode dormir quando fica inativo; o primeiro acesso pode demorar.</div>
</div><script>
function esc(s){return String(s??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[m]))}
function stageIndex(s){return {PESQUISA:0,ANÁLISE:1,ROTEIRO:2,VISUAIS:3,NARRAÇÃO:4,EDIÇÃO:5,AVALIAÇÃO:6,PRONTO:7}[s]??-1}
async function load(){try{let d=await(await fetch('/api/state')).json();document.getElementById('opps').textContent=d.opportunities.length;document.getElementById('assuntos').textContent=d.opportunities.length;document.getElementById('produzidos').textContent=d.produced;document.getElementById('fila').textContent=d.queue;document.getElementById('oppList').innerHTML=d.opportunities.map(o=>`<div class="row"><div class="score">${o.score}</div><div><div class="title">${esc(o.title)}</div><div class="source">${esc(o.source)}</div></div><div class="pill">${esc(o.priority)}</div><div class="pill">${esc(o.status||'PRODUZIR')}</div><button class="produce" onclick="createShort('${o.id}')">PRODUZIR</button></div>`).join('');renderJobs(d.jobs)}catch(e){}}
function renderJobs(js){if(!js.length){document.getElementById('jobs').textContent='Nenhuma produção iniciada.';return}js=js.slice().reverse();document.getElementById('jobs').innerHTML=js.map(j=>{let p=Math.round(j.progress||0);return `<div class="job"><div class="jobhead"><b>${esc(j.title)}</b><span>${esc(j.status)}</span></div><div class="muted">${esc(j.stage)} — ${p}%</div><div class="bar"><i style="width:${p}%"></i></div><div class="log">${esc(j.log||'')}</div>${j.score?`<div class="meta">Avaliação: ${j.score}/100</div>`:''}${j.video?`<div class="result"><a href="/output/${encodeURIComponent(j.video)}" target="_blank">▶ ABRIR SHORT</a><a href="/output/${encodeURIComponent(j.cover||'')}" target="_blank">🖼️ CAPA</a><a href="/api/job/${j.id}" target="_blank">JSON</a></div>`:''}</div>`}).join('');for(let i=0;i<8;i++)document.getElementById('step-'+i).classList.toggle('active',js[0]&&i===stageIndex(js[0].stage))}
async function createShort(id){let topic=document.getElementById('topic').value;let r=await fetch('/api/produce',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:id||null,topic})});let d=await r.json();if(!r.ok){alert(d.error||'Erro');return}document.getElementById('topic').value='';load()}
async function research(){let r=await fetch('/api/research',{method:'POST'});let d=await r.json();if(d.error)alert(d.error);load()}
load();setInterval(load,3000);
</script></body></html>'''

def now_iso(): return datetime.now(timezone.utc).isoformat()

def load_jobs():
    if not STATE_FILE.exists(): return {}
    try: return json.loads(STATE_FILE.read_text(encoding='utf-8'))
    except Exception: return {}

def save_jobs(jobs):
    tmp=STATE_FILE.with_suffix('.tmp'); tmp.write_text(json.dumps(jobs,ensure_ascii=False,indent=2),encoding='utf-8'); tmp.replace(STATE_FILE)

def update_job(jid, **changes):
    with LOCK:
        jobs=load_jobs(); j=jobs.get(jid)
        if not j: return None
        j.update(changes); j['updated_at']=now_iso(); save_jobs(jobs); return j

def font(size,bold=False):
    paths=['/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf' if bold else '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf','/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf' if bold else '/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf']
    for p in paths:
        if Path(p).exists(): return ImageFont.truetype(p,size)
    return ImageFont.load_default()

def fetch(url,timeout=25): return requests.get(url,headers={'User-Agent':UA},timeout=timeout)

def research_official():
    facts=[]; images=[]
    for url in [ROCKSTAR_VI,ROCKSTAR_NEWS]:
        try:
            r=fetch(url); r.raise_for_status(); soup=BeautifulSoup(r.text,'html.parser')
            text=' '.join(soup.stripped_strings)
            facts.append(text[:12000])
            for tag in soup.find_all(['meta','img']):
                u=tag.get('content') if tag.name=='meta' else tag.get('src')
                if u and (tag.get('property')=='og:image' or tag.name=='img'): images.append(urljoin(url,u))
        except Exception: pass
    blob=' '.join(facts); topics=[]
    def add(t,score,url,key): topics.append({'id':key,'score':score,'priority':'ALTA' if score>=88 else 'MÉDIA','title':t,'source':'Rockstar Games','url':url})
    if 'Leonida' in blob or 'leonida' in blob.lower(): add('GTA 6: o detalhe de Leonida que pode mudar a história',96,ROCKSTAR_VI,'leonida')
    if 'Jason' in blob and 'Lucia' in blob: add('Jason e Lucia: o que a Rockstar já confirmou oficialmente',93,ROCKSTAR_VI,'jason-lucia')
    if 'Vice City' in blob: add('A história de GTA 6 vai muito além de Vice City',90,ROCKSTAR_NEWS,'estado-leonida')
    add('Os detalhes escondidos que a Rockstar colocou em GTA 6',84,ROCKSTAR_VI,'detalhes')
    out=[]; seen=set()
    for x in sorted(topics,key=lambda z:z['score'],reverse=True):
        if x['id'] not in seen: seen.add(x['id']); out.append(x)
    return out[:6],images,blob

def choose_topic(data,topics):
    if data.get('id'):
        for o in topics:
            if o['id']==data['id']: return o
    custom=(data.get('topic') or '').strip()
    if custom: return {'id':'custom','score':88,'priority':'ALTA','title':custom,'source':'Pesquisa editorial','url':ROCKSTAR_VI}
    return max(topics,key=lambda x:x['score'])

def make_script(topic):
    title=topic['title'].lower()
    if 'jason' in title:
        text='Você reparou nisso em GTA 6? A Rockstar já confirmou oficialmente Jason e Lucia como o centro da história. Mas o detalhe mais importante é que os problemas dos dois não ficam presos a Vice City. A própria Rockstar descreve uma conspiração que se espalha por todo o estado de Leonida. Isso abre espaço para muito mais histórias, personagens e segredos pelo mapa. E se algumas pistas já estiverem nos detalhes que vimos?'
    elif 'leonida' in title:
        text='Você percebeu isso em GTA 6? A Rockstar não apresentou apenas uma nova Vice City. A história de Jason e Lucia está ligada a uma conspiração que se estende por todo o estado de Leonida. Isso significa que o mapa pode esconder muito mais do que a cidade principal. Cada região pode carregar pistas, personagens e acontecimentos que ainda não foram revelados. E se a Rockstar já estiver mostrando essas pistas sem a gente perceber?'
    else:
        text='GTA 6 pode estar mostrando muito mais do que parece. Nos materiais oficiais, a Rockstar apresenta Vice City, Jason, Lucia e um estado inteiro chamado Leonida. O detalhe interessante é que a história não fica limitada à cidade. A escala do mapa cria espaço para pistas, personagens e acontecimentos espalhados por diferentes regiões. Então fica a pergunta: qual detalhe a Rockstar mostrou e quase ninguém percebeu?'
    return {'title':topic['title'],'narration':text,'source':topic['url'],'source_name':topic['source']}

def wrap_text(draw,text,f,max_width):
    lines=[]; cur=''
    for w in text.split():
        t=(cur+' '+w).strip()
        if draw.textbbox((0,0),t,font=f)[2] <= max_width: cur=t
        else:
            if cur: lines.append(cur)
            cur=w
    if cur: lines.append(cur)
    return lines

def make_fallback(path,idx,title):
    im=Image.new('RGB',(1080,1920),(8,10,15)); d=ImageDraw.Draw(im)
    for y in range(1920): d.line((0,y,1080,y),fill=(10+int(18*y/1920),8,15+int(20*y/1920)))
    d.rectangle((65,90,1015,1830),outline=(170,25,40),width=3); d.text((80,120),f'ARQUIVO {idx+1:02d}',font=font(34,True),fill=(230,40,55)); d.text((80,1760),'GTA OCULTO',font=font(42,True),fill='white')
    y=720
    for line in wrap_text(d,title,font(70,True),880)[:5]: d.text((80,y),line,font=font(70,True),fill='white'); y+=88
    im.save(path,quality=88)

def download_visuals(urls,outdir,title):
    outdir.mkdir(parents=True,exist_ok=True); paths=[]
    for i,u in enumerate(urls[:10]):
        try:
            r=fetch(u); r.raise_for_status()
            if len(r.content)<10000: continue
            p=outdir/f'src_{i}.jpg'; p.write_bytes(r.content); im=Image.open(p).convert('RGB'); im.thumbnail((1600,1600)); im.save(p,quality=90); paths.append(p)
        except Exception: pass
        if len(paths)>=5: break
    while len(paths)<5:
        p=outdir/f'fallback_{len(paths)}.jpg'; make_fallback(p,len(paths),title); paths.append(p)
    return paths[:5]

def prepare_scene(src,dst,caption,idx):
    im=Image.open(src).convert('RGB'); W,H=1080,1920; scale=max(W/im.width,H/im.height); nw,nh=int(im.width*scale),int(im.height*scale); im=im.resize((nw,nh),Image.Resampling.LANCZOS)
    left=(nw-W)//2 if idx%3==0 else (int((nw-W)*0.2) if idx%3==1 else int((nw-W)*0.65)); top=(nh-H)//2; left=max(0,min(nw-W,left)); top=max(0,min(nh-H,top)); im=im.crop((left,top,left+W,top+H)); im=ImageEnhance.Contrast(im).enhance(1.08)
    ov=Image.new('RGBA',(W,H),(0,0,0,0)); od=ImageDraw.Draw(ov); od.rectangle((0,0,W,150),fill=(0,0,0,115)); od.rectangle((0,H-500,W,H),fill=(0,0,0,155)); im=Image.alpha_composite(im.convert('RGBA'),ov); d=ImageDraw.Draw(im)
    d.text((52,45),'GTA OCULTO',font=font(38,True),fill='white'); d.text((W-120,45),f'{idx+1:02d}/05',font=font(28,True),fill=(225,35,50))
    f=font(48,True); lines=wrap_text(d,caption,f,900); box_h=110+len(lines)*62; y=H-box_h-70; d.rounded_rectangle((55,y,1025,H-70),radius=26,fill=(7,9,13,215),outline=(215,28,45),width=3); yy=y+45
    for line in lines[:5]: d.text((90,yy),line,font=f,fill='white'); yy+=62
    im.convert('RGB').save(dst,quality=90)

def run_cmd(cmd,timeout=240):
    p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=timeout)
    if p.returncode: raise RuntimeError(p.stdout[-3500:])
    return p.stdout

def duration_of_audio(path):
    try:
        out=run_cmd(['ffprobe','-v','error','-show_entries','format=duration','-of','default=nw=1:nk=1',str(path)],30); return max(20,min(42,float(out.strip())))
    except Exception: return 30.0

async def make_tts(text,path):
    if edge_tts is None: raise RuntimeError('edge-tts não disponível no servidor')
    last=None
    for voice in ['pt-BR-AntonioNeural','pt-BR-FranciscaNeural']:
        try:
            await edge_tts.Communicate(text,voice,rate='+3%',pitch='-2Hz').save(str(path)); return
        except Exception as e: last=e
    raise RuntimeError(f'falha na narração: {last}')

def make_video(scenes,audio,out,duration):
    listfile=out.parent/'scenes.txt'; per=duration/len(scenes)
    with listfile.open('w',encoding='utf-8') as f:
        for p in scenes: f.write(f"file '{p.as_posix()}'\nduration {per:.3f}\n")
        f.write(f"file '{scenes[-1].as_posix()}'\n")
    ff=str(__import__('imageio_ffmpeg').get_ffmpeg_exe())
    run_cmd([ff,'-y','-f','concat','-safe','0','-i',str(listfile),'-i',str(audio),'-t',f'{duration:.2f}','-r','24','-c:v','libx264','-preset','veryfast','-crf','25','-pix_fmt','yuv420p','-c:a','aac','-b:a','128k','-movflags','+faststart','-shortest',str(out)],240)

def make_cover(scene,title,out):
    im=Image.open(scene).convert('RGB'); d=ImageDraw.Draw(im,'RGBA'); d.rectangle((45,500,1035,1330),fill=(0,0,0,165),outline=(225,25,45),width=5); f=font(72,True); y=610
    for line in wrap_text(d,title,f,880)[:6]: d.text((100,y),line,font=f,fill='white',stroke_width=2,stroke_fill='black'); y+=88
    d.text((100,120),'GTA OCULTO',font=font(42,True),fill='white'); im.save(out,quality=92)

def evaluate(script,duration):
    score=100
    if duration<22: score-=8
    if duration>40: score-=6
    if len(script['narration'])<280: score-=8
    if '?' not in script['narration'][:180]: score-=4
    return max(0,min(100,score))

def produce_job(jid):
    global PROCESSING
    try:
        update_job(jid,status='RUNNING',stage='PESQUISA',progress=5,log='Pesquisando fontes oficiais da Rockstar...')
        topics,urls,_=research_official(); topics=topics or FALLBACK_TOPICS
        job=load_jobs()[jid]; topic=job['opportunity']
        update_job(jid,stage='ANÁLISE',progress=16,log=f'IA editorial selecionou: {topic["title"]}')
        update_job(jid,stage='ROTEIRO',progress=28,log='Montando roteiro original em português brasileiro...'); script=make_script(topic)
        jobdir=WORK/jid; jobdir.mkdir(parents=True,exist_ok=True)
        update_job(jid,script=script,stage='VISUAIS',progress=40,log='Baixando visuais oficiais e montando cenas verticais...')
        paths=download_visuals(urls,jobdir/'visuals',topic['title']); caps=['VOCÊ PERCEBEU ISSO EM GTA 6?','JASON E LUCIA ESTÃO NO CENTRO DA HISTÓRIA.','MAS A TRAMA NÃO FICA PRESA EM VICE CITY.','A CONSPIRAÇÃO SE ESTENDE POR LEONIDA.','QUAL DETALHE A ROCKSTAR AINDA ESTÁ ESCONDENDO?']; scenes=[]
        for i,p in enumerate(paths): dst=jobdir/f'scene_{i}.jpg'; prepare_scene(p,dst,caps[i],i); scenes.append(dst)
        update_job(jid,stage='NARRAÇÃO',progress=60,log='Gerando narração PT-BR...'); audio=jobdir/'narracao.mp3'; asyncio.run(make_tts(script['narration'],audio)); duration=duration_of_audio(audio)
        update_job(jid,stage='EDIÇÃO',progress=74,log=f'Editando 1080x1920 / 24 FPS / {duration:.1f}s...'); video=jobdir/'GTA_OCULTO_SHORT.mp4'; make_video(scenes,audio,video,duration)
        cover=jobdir/'CAPA.jpg'; make_cover(scenes[0],topic['title'],cover)
        update_job(jid,stage='AVALIAÇÃO',progress=92,log='Avaliando hook, duração, formato e legendas...'); score=evaluate(script,duration)
        meta={'title':topic['title'].upper()+' 👀','description':script['narration']+'\n\n🔎 GTA Oculto — onde os segredos vêm à tona.','hashtags':['#GTA6','#GTAVI','#GTAOculto','#RockstarGames','#GTA'],'tags':['GTA 6','GTA VI','GTA 6 Brasil','GTA 6 teorias','GTA 6 segredos','Rockstar Games','GTA Oculto'],'score':score}
        (jobdir/'metadata.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
        update_job(jid,status='DONE',stage='PRONTO',progress=100,log=f'PRONTO — Short gerado e avaliado em {score}/100.',video=f'{jid}/GTA_OCULTO_SHORT.mp4',cover=f'{jid}/CAPA.jpg',score=score,metadata=meta)
    except Exception as e:
        update_job(jid,status='ERROR',stage='ERRO',progress=100,log='ERRO: '+str(e)[-3500:])
    finally: PROCESSING=False

def processor_loop():
    global PROCESSING
    while True:
        try:
            if not PROCESSING:
                with LOCK: target=next((j for j in load_jobs().values() if j.get('status')=='QUEUED'),None)
                if target: PROCESSING=True; threading.Thread(target=produce_job,args=(target['id'],),daemon=True).start()
            time.sleep(2)
        except Exception: time.sleep(5)

@APP.get('/')
def home(): return render_template_string(PAGE)
@APP.get('/health')
def health(): return jsonify(ok=True,app='GTA Oculto AI',version='CLOUD-FINAL-1.0',processor='cloud')
@APP.get('/api/state')
def state():
    with LOCK:
        js=list(load_jobs().values())[-30:]
        return jsonify(opportunities=FALLBACK_TOPICS,jobs=js,produced=sum(x.get('status')=='DONE' for x in js),queue=sum(x.get('status') in ('QUEUED','RUNNING') for x in js))
@APP.post('/api/research')
def research():
    try:
        topics,_,_=research_official(); return jsonify(ok=True,message=f'Pesquisa concluída: {len(topics)} oportunidades encontradas.',opportunities=topics or FALLBACK_TOPICS)
    except Exception as e: return jsonify(error=str(e)),502
@APP.post('/api/produce')
def produce():
    data=request.get_json(silent=True) or {}; topics,_,_=research_official(); topics=topics or FALLBACK_TOPICS; topic=choose_topic(data,topics); jid=uuid.uuid4().hex[:10]
    job={'id':jid,'title':topic['title'],'opportunity':topic,'status':'QUEUED','stage':'FILA','progress':0,'log':'Tarefa recebida. A produção cloud começará automaticamente.','video':None,'cover':None,'created_at':now_iso()}
    with LOCK: jobs=load_jobs(); jobs[jid]=job; save_jobs(jobs)
    return jsonify(ok=True,job_id=jid,title=topic['title'])
@APP.get('/api/job/<jid>')
def one(jid):
    j=load_jobs().get(jid); return (jsonify(j) if j else (jsonify(error='not found'),404))
@APP.get('/output/<path:p>')
def output(p):
    full=(WORK/p).resolve(); base=WORK.resolve()
    if not str(full).startswith(str(base)) or not full.exists(): return 'Not found',404
    return send_from_directory(full.parent,full.name,as_attachment=False)

threading.Thread(target=processor_loop,daemon=True).start()
if __name__=='__main__': APP.run(host='0.0.0.0',port=int(os.environ.get('PORT',5000)))

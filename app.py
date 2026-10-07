import os, json, uuid, threading, time, asyncio, subprocess, shutil, re, sys
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
ROCKSTAR_VIDEO_ZIP = 'https://media-rockstargames-com.akamaized.net/VI/downloads/videos/GTAVI_Videos.zip'

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
    # Também coleta a galeria oficial de downloads da Rockstar para aumentar a variedade visual.
    try:
        r=fetch('https://www.rockstargames.com/VI/downloads/videos'); r.raise_for_status()
        soup=BeautifulSoup(r.text,'html.parser')
        for tag in soup.find_all(['meta','img']):
            u=tag.get('content') if tag.name=='meta' else tag.get('src')
            if u and (tag.get('property')=='og:image' or tag.name=='img'):
                images.append(urljoin('https://www.rockstargames.com/VI/downloads/videos',u))
    except Exception:
        pass
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
    """Cria roteiro adaptado ao assunto, sem reutilizar um roteiro fixo."""
    title=str(topic.get('title','GTA 6')).strip()
    t=title.lower()
    if any(k in t for k in ('rumor','leak','vazamento','suposto')):
        kind='RUMOR'
    elif any(k in t for k in ('teoria','theory','pista','mistério','misterio','segredo','detalhe','escond')):
        kind='MISTÉRIO'
    elif any(k in t for k in ('confirm','revel','anunci','news','notícia','noticia','atualização','update')):
        kind='NOTÍCIA'
    else:
        kind='CURIOSIDADE'

    if kind=='RUMOR':
        narration=(f'Existe uma informação circulando sobre GTA 6 que chamou atenção: {title}. '
        'Mas existe uma diferença importante entre rumor e confirmação oficial. '
        'Até aqui, o que podemos tratar como fato é apenas o que foi apresentado ou confirmado pela Rockstar. '
        'O restante precisa ser analisado com cuidado. Mesmo assim, o detalhe mais curioso dessa história é o que ele pode significar para o jogo. '
        'Se essa informação se confirmar, ela pode mudar a forma como enxergamos GTA 6. Você acha que isso faz sentido ou é só mais um rumor?')
    elif kind=='MISTÉRIO':
        narration=(f'Existe um detalhe em GTA 6 que merece muito mais atenção: {title}. '
        'A Rockstar costuma esconder informações importantes nos próprios materiais do jogo, e esse ponto pode ter passado despercebido. '
        'O mais interessante é que ele pode se conectar com outros elementos já apresentados oficialmente. '
        'Isso não prova uma teoria, mas cria uma possibilidade muito curiosa. '
        'E se esse detalhe estiver apontando para algo maior dentro de Leonida? Qual é a sua teoria?')
    elif kind=='NOTÍCIA':
        narration=(f'A Rockstar trouxe uma novidade que merece atenção em GTA 6: {title}. '
        'O ponto mais importante é entender exatamente o que foi confirmado e o que ainda é interpretação. '
        'Essa informação ajuda a revelar como a Rockstar está construindo o mundo de GTA 6 e pode ter impacto em personagens, mapa ou gameplay. '
        'E existe um detalhe nessa novidade que pode ter passado despercebido. Agora fica a pergunta: o que essa informação pode significar para GTA 6?')
    else:
        narration=(f'Você reparou neste detalhe de GTA 6? {title}. '
        'À primeira vista parece apenas mais uma informação sobre o jogo, mas existe algo interessante por trás disso. '
        'Quando juntamos esse detalhe com o que a Rockstar já mostrou oficialmente, surgem novas possibilidades para o mundo de Leonida. '
        'Não significa que uma teoria esteja confirmada, mas é exatamente esse tipo de detalhe que faz GTA 6 gerar tanta discussão. Você tinha percebido isso?')

    return {'title':title,'narration':narration,'source':topic.get('url',ROCKSTAR_VI),
            'source_name':topic.get('source','Pesquisa editorial'),'content_type':kind}


def build_dynamic_captions(script, topic, count=9):
    """Editor-chefe: reescreve chamadas curtas a partir do sentido do roteiro.
    Não corta palavras arbitrariamente; cada bloco é uma chamada editorial completa.
    """
    narration=str(script.get('narration','')).strip()
    title=str(topic.get('title','')).strip()
    kind=str(script.get('content_type','CURIOSIDADE')).upper()

    # Normalização e limpeza: evita emojis, pontuação estranha e frases quebradas.
    def clean(s):
        s=re.sub(r'[^\wÀ-ÿ0-9\s?!.,\'-]', ' ', str(s), flags=re.UNICODE)
        return re.sub(r'\s+',' ',s).strip()

    title=clean(title)
    narration=clean(narration)

    stop={
        'a','o','e','de','do','da','dos','das','em','no','na','nos','nas',
        'que','um','uma','uns','umas','os','as','isso','isto','para','com',
        'por','mais','mas','como','esse','essa','esses','essas','ele','ela',
        'eles','elas','se','não','sim','foi','ser','são','tem','ter','pode',
        'podem','sobre','entre','muito','muita','também','já','até','quando'
    }

    def meaningful_words(s):
        return [w for w in re.findall(r"[A-Za-zÀ-ÿ0-9']+",s)
                if w.lower() not in stop and len(w)>=3]

    # Extrai termos realmente ligados ao assunto, priorizando título.
    tw=meaningful_words(title)
    topic_terms=[]
    for w in tw:
        u=w.upper()
        if u not in topic_terms:
            topic_terms.append(u)
    sentences=[clean(s) for s in re.split(r'[.!?]+',narration) if len(clean(s))>=12]

    sentence_terms=[]
    for s in sentences:
        ws=meaningful_words(s)
        vals=[]
        for w in ws:
            u=w.upper()
            if u not in vals:
                vals.append(u)
        if vals:
            sentence_terms.append((s,vals))

    def pick_terms(i, limit=3):
        # Alterna título e roteiro para não repetir sempre a mesma expressão.
        if sentence_terms:
            vals=sentence_terms[i % len(sentence_terms)][1]
            if vals:
                return vals[:limit]
        return topic_terms[:limit]

    subject=' '.join(topic_terms[:3]) if topic_terms else 'ESSE DETALHE'

    # Chamadas editoriais completas. Cada tipo tem uma linguagem diferente.
    if kind == 'NOTÍCIA':
        first=[
            f"A ROCKSTAR ACABOU DE REVELAR ISSO",
            f"ESSA NOVIDADE MEXE COM {subject}",
            "MAS O DETALHE MAIS IMPORTANTE ESTÁ AQUI",
        ]
        middle_templates=[
            "OLHA O QUE ISSO PODE MUDAR",
            "ESSA PARTE PASSOU QUASE DESPERCEBIDA",
            "AGORA TUDO FAZ MAIS SENTIDO",
            "E ISSO NÃO PARECE POR ACASO",
            "O QUE ISSO SIGNIFICA PARA GTA 6?",
        ]
        final="ESSA NOVIDADE PODE MUDAR TUDO"
    elif kind == 'MISTÉRIO':
        first=[
            "NINGUÉM ESTÁ FALANDO DESSE DETALHE",
            f"ESSE DETALHE ESCONDIDO CHAMA ATENÇÃO",
            "OLHE BEM PARA ESSA CENA",
        ]
        middle_templates=[
            "A PISTA ESTÁ JUSTAMENTE AQUI",
            "POR QUE A ROCKSTAR FARIA ISSO?",
            "ISSO PODE NÃO SER COINCIDÊNCIA",
            "TEM ALGO ESTRANHO NESSA CENA",
            "E SE A PISTA ESTIVER AQUI?",
        ]
        final="E SE ISSO NÃO FOR COINCIDÊNCIA?"
    elif kind == 'RUMOR':
        first=[
            "ESSE RUMOR ESTÁ GANHANDO FORÇA",
            "MAS ISSO AINDA NÃO FOI CONFIRMADO",
            f"ESSA PISTA ENVOLVE {subject}",
        ]
        middle_templates=[
            "A FONTE DIZ UMA COISA",
            "MAS EXISTE UM DETALHE IMPORTANTE",
            "ATÉ AGORA, NADA FOI CONFIRMADO",
            "ISSO É PISTA OU APENAS RUMOR?",
            "PRECISAMOS OLHAR ISSO COM CUIDADO",
        ]
        final="RUMOR OU PISTA REAL?"
    elif kind == 'TEORIA':
        first=[
            "ESSA TEORIA COMEÇA COM UM DETALHE",
            f"{subject} PODE ESCONDER UMA PISTA",
            "E SE ISSO TIVER SIDO PLANEJADO?",
        ]
        middle_templates=[
            "A PRIMEIRA PISTA ESTÁ AQUI",
            "ISSO COMEÇA A FAZER SENTIDO",
            "MAS EXISTE OUTRO DETALHE",
            "A TEORIA FICA AINDA MAIS ESTRANHA",
            "NADA DISSO FOI CONFIRMADO",
        ]
        final="COINCIDÊNCIA OU PISTA?"
    else:
        first=[
            "VOCÊ PERCEBEU ESSE DETALHE?",
            f"ESSE DETALHE DE {subject} PASSOU BATIDO",
            "QUASE NINGUÉM REPAROU NISSO",
        ]
        middle_templates=[
            "OLHA BEM PARA ESSA PARTE",
            "A DIFERENÇA ESTÁ AQUI",
            "ESSE DETALHE MUDA A CENA",
            "E TEM MAIS UMA COISA",
            "AGORA VOCÊ VAI PERCEBER",
        ]
        final="VOCÊ JÁ TINHA PERCEBIDO?"

    caps=[]
    def add(s):
        s=clean(s).upper()
        s=re.sub(r'\s+',' ',s).strip()
        if not s or s in caps:
            return
        # Não permite chamadas quebradas: precisam terminar com conteúdo suficiente.
        if len(s.split()) >= 3:
            caps.append(s)

    for x in first:
        add(x)

    # Insere termos específicos do roteiro em chamadas completas.
    for i in range(max(0, count-4)):
        terms=pick_terms(i, 2)
        if terms:
            if i % 3 == 0:
                add(f"OLHE BEM PARA {' '.join(terms)}")
            elif i % 3 == 1:
                add(f"ESSE DETALHE ENVOLVE {' '.join(terms)}")
            else:
                add(f"POR QUE {' '.join(terms)} APARECE AQUI?")
        if len(caps)>=count-1:
            break

    for x in middle_templates:
        add(x)
        if len(caps)>=count-1:
            break

    add(final)

    # Garante variedade sem repetir uma chamada só para preencher a timeline.
    fallback=[
        "TEM UM DETALHE QUE VOCÊ NÃO VIU",
        "OLHE NOVAMENTE PARA ESSA CENA",
        "ESSA PISTA MERECE ATENÇÃO",
        "AGORA TUDO COMEÇA A FAZER SENTIDO",
    ]
    for x in fallback:
        if len(caps)>=count:
            break
        add(x)

    return caps[:count]
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

def _image_quality(path):
    """Return a conservative quality score and reject web UI/blank images."""
    try:
        im=Image.open(path).convert('RGB')
        w,h=im.size
        if w < 640 or h < 360:
            return -1
        # Sample a small version for cheap quality checks.
        sm=im.copy(); sm.thumbnail((180,180)); pix=list(sm.getdata()); n=len(pix)
        white=sum(1 for r,g,b in pix if r>242 and g>242 and b>242)/n
        green=sum(1 for r,g,b in pix if g>r*1.18 and g>b*1.12 and g>55)/n
        lightgray=sum(1 for r,g,b in pix if abs(r-g)<5 and abs(g-b)<5 and 150<r<242)/n
        black=sum(1 for r,g,b in pix if r<12 and g<12 and b<12)/n
        # Mean channel spread is a cheap proxy for visual information/color.
        spread=sum(max(px)-min(px) for px in pix)/n
        # Blank pages, logos, CSS placeholders and mostly-white screenshots are bad assets.
        # Also reject obvious green-screen/blank-color frames.
        if white > 0.34 or (white + lightgray) > 0.58 or green > 0.48:
            return -1
        # Quantized dominant-color ratio catches flat placeholder panels.
        buckets={}
        for r,g,b in pix:
            k=(r//24,g//24,b//24); buckets[k]=buckets.get(k,0)+1
        if max(buckets.values())/n > 0.55:
            return -1
        if black > 0.72:
            return -1
        if spread < 10:
            return -1
        # Prefer reasonably large, colorful/cinematic assets.
        score=0
        score += min(w*h/1_000_000, 4)*8
        score += min(spread/35, 2)*15
        score += max(0, 1-white)*20
        if 0.55 <= w/h <= 2.2: score += 8
        return score
    except Exception:
        return -1


def _candidate_urls(page_url, soup):
    found=[]; seen=set()
    def add(u,label=''):
        if not u or u.startswith('data:'): return
        u=urljoin(page_url,u)
        if u not in seen:
            seen.add(u); found.append({'url':u,'label':(label or '').strip()[:180]})
    for tag in soup.find_all('meta'):
        prop=(tag.get('property') or tag.get('name') or '').lower()
        if prop in ('og:image','twitter:image','twitter:image:src'):
            add(tag.get('content'), tag.get('content',''))
    for tag in soup.find_all('img'):
        label=' '.join(filter(None,[tag.get('alt'),tag.get('title'),tag.get('aria-label')]))
        for key in ('src','data-src','data-lazy-src','data-original'):
            add(tag.get(key),label)
        srcset=tag.get('srcset') or tag.get('data-srcset')
        if srcset:
            parts=[x.strip().split(' ')[0] for x in srcset.split(',') if x.strip()]
            if parts: add(parts[-1],label)
    return found

def _asset_text(asset):
    if isinstance(asset,dict):
        return f"{asset.get('label','')} {asset.get('url','')}".lower()
    return str(asset).lower()

def _scene_keywords(topic_title):
    t=topic_title.lower()
    if 'jason' in t and 'lucia' in t:
        return [
            ['jason','lucia'],['jason'],['lucia'],['vice city'],['leonida'],['map'],
            ['jason','car'],['lucia','car'],['vice city','night'],['leonida','road'],['gta vi'],['gta 6']
        ]
    if 'leonida' in t or 'vice city' in t:
        return [
            ['gta 6'],['jason','lucia'],['vice city'],['vice city','night'],['leonida'],['map'],
            ['road'],['jason'],['lucia'],['leonida','city'],['gta vi'],['rockstar']
        ]
    return [['gta 6'],['jason'],['lucia'],['vice city'],['leonida'],['map'],['rockstar'],['jason','lucia'],['city'],['road'],['gta vi'],['gta 6']]

def select_visuals(paths, topic_title, count=12):
    if not paths: return []
    plans=_scene_keywords(topic_title)
    chosen=[]; used=set()
    for kws in plans:
        ranked=[]
        for idx,item in enumerate(paths):
            p=item['path'] if isinstance(item,dict) else item
            if idx in used: continue
            txt=_asset_text(item)
            hits=sum(1 for k in kws if k in txt)
            ranked.append((hits, _image_quality(p), idx))
        if ranked:
            ranked.sort(key=lambda x:(x[0],x[1]),reverse=True)
            chosen.append(ranked[0][2]); used.add(ranked[0][2])
    # Fill only after unique assets are exhausted; avoid adjacent repeats.
    if len(chosen)<count:
        for idx in range(len(paths)):
            if idx not in used:
                chosen.append(idx); used.add(idx)
                if len(chosen)>=count: break
    while len(chosen)<count:
        for idx in range(len(paths)):
            if not chosen or idx!=chosen[-1]:
                chosen.append(idx)
                if len(chosen)>=count: break
    return [paths[i]['path'] if isinstance(paths[i],dict) else paths[i] for i in chosen[:count]]


def research_official():
    facts=[]; images=[]
    for url in [ROCKSTAR_VI,ROCKSTAR_NEWS,'https://www.rockstargames.com/VI/downloads/videos']:
        try:
            r=fetch(url); r.raise_for_status(); soup=BeautifulSoup(r.text,'html.parser')
            text=' '.join(soup.stripped_strings)
            facts.append(text[:16000])
            images.extend(_candidate_urls(url,soup))
        except Exception: pass
    # Também coleta a galeria oficial de downloads da Rockstar para aumentar a variedade visual.
    try:
        r=fetch('https://www.rockstargames.com/VI/downloads/videos'); r.raise_for_status()
        soup=BeautifulSoup(r.text,'html.parser')
        for tag in soup.find_all(['meta','img']):
            u=tag.get('content') if tag.name=='meta' else tag.get('src')
            if u and (tag.get('property')=='og:image' or tag.name=='img'):
                images.append(urljoin('https://www.rockstargames.com/VI/downloads/videos',u))
    except Exception:
        pass
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
    """Cria roteiro adaptado ao assunto, sem reutilizar um roteiro fixo."""
    title=str(topic.get('title','GTA 6')).strip()
    t=title.lower()
    if any(k in t for k in ('rumor','leak','vazamento','suposto')):
        kind='RUMOR'
    elif any(k in t for k in ('teoria','theory','pista','mistério','misterio','segredo','detalhe','escond')):
        kind='MISTÉRIO'
    elif any(k in t for k in ('confirm','revel','anunci','news','notícia','noticia','atualização','update')):
        kind='NOTÍCIA'
    else:
        kind='CURIOSIDADE'

    if kind=='RUMOR':
        narration=(f'Existe uma informação circulando sobre GTA 6 que chamou atenção: {title}. '
        'Mas existe uma diferença importante entre rumor e confirmação oficial. '
        'Até aqui, o que podemos tratar como fato é apenas o que foi apresentado ou confirmado pela Rockstar. '
        'O restante precisa ser analisado com cuidado. Mesmo assim, o detalhe mais curioso dessa história é o que ele pode significar para o jogo. '
        'Se essa informação se confirmar, ela pode mudar a forma como enxergamos GTA 6. Você acha que isso faz sentido ou é só mais um rumor?')
    elif kind=='MISTÉRIO':
        narration=(f'Existe um detalhe em GTA 6 que merece muito mais atenção: {title}. '
        'A Rockstar costuma esconder informações importantes nos próprios materiais do jogo, e esse ponto pode ter passado despercebido. '
        'O mais interessante é que ele pode se conectar com outros elementos já apresentados oficialmente. '
        'Isso não prova uma teoria, mas cria uma possibilidade muito curiosa. '
        'E se esse detalhe estiver apontando para algo maior dentro de Leonida? Qual é a sua teoria?')
    elif kind=='NOTÍCIA':
        narration=(f'A Rockstar trouxe uma novidade que merece atenção em GTA 6: {title}. '
        'O ponto mais importante é entender exatamente o que foi confirmado e o que ainda é interpretação. '
        'Essa informação ajuda a revelar como a Rockstar está construindo o mundo de GTA 6 e pode ter impacto em personagens, mapa ou gameplay. '
        'E existe um detalhe nessa novidade que pode ter passado despercebido. Agora fica a pergunta: o que essa informação pode significar para GTA 6?')
    else:
        narration=(f'Você reparou neste detalhe de GTA 6? {title}. '
        'À primeira vista parece apenas mais uma informação sobre o jogo, mas existe algo interessante por trás disso. '
        'Quando juntamos esse detalhe com o que a Rockstar já mostrou oficialmente, surgem novas possibilidades para o mundo de Leonida. '
        'Não significa que uma teoria esteja confirmada, mas é exatamente esse tipo de detalhe que faz GTA 6 gerar tanta discussão. Você tinha percebido isso?')

    return {'title':title,'narration':narration,'source':topic.get('url',ROCKSTAR_VI),
            'source_name':topic.get('source','Pesquisa editorial'),'content_type':kind}


def build_dynamic_captions(script, topic, count=9):
    """Cria textos de tela a partir do assunto e do roteiro, variando por conteúdo."""
    narration=str(script.get('narration','')).strip()
    title=str(topic.get('title','')).strip()
    kind=script.get('content_type','CURIOSIDADE')
    openers={
        'RUMOR':'⚠️ ISSO AINDA NÃO FOI CONFIRMADO',
        'MISTÉRIO':'👁️ NINGUÉM ESTÁ FALANDO DESSE DETALHE',
        'NOTÍCIA':'🚨 A ROCKSTAR ACABOU DE REVELAR ISSO',
        'CURIOSIDADE':'😳 VOCÊ PERCEBEU ESSE DETALHE?'
    }
    endings={
        'RUMOR':'RUMOR OU PISTA REAL?',
        'MISTÉRIO':'E SE ISSO NÃO FOR COINCIDÊNCIA?',
        'NOTÍCIA':'O QUE ISSO MUDA NO GTA 6?',
        'CURIOSIDADE':'VOCÊ JÁ TINHA PERCEBIDO?'
    }
    caps=[openers.get(kind,openers['CURIOSIDADE'])]
    title_words=[w for w in re.findall(r"[A-Za-zÀ-ÿ0-9']+",title) if len(w)>=4]
    if title_words:
        caps.append(' '.join(title_words[:5]).upper())
    stop={'a','o','e','de','do','da','em','no','na','que','um','uma','os','as','isso','para','com','por','mais','mas','como','esse','essa'}
    sentences=[s.strip(' .!?') for s in re.split(r'[.!?]+',narration) if len(s.strip())>8]
    for s in sentences:
        words=re.findall(r"[A-Za-zÀ-ÿ0-9']+",s)
        meaningful=[w for w in words if w.lower() not in stop]
        if len(meaningful)>=2:
            phrase=' '.join(meaningful[:5]).upper()
            if phrase not in caps:
                caps.append(phrase)
        if len(caps)>=count-1:
            break
    caps.append(endings.get(kind,endings['CURIOSIDADE']))
    out=[]; seen=set()
    for c in caps:
        c=re.sub(r'\s+',' ',c).strip()
        if c and c not in seen:
            seen.add(c); out.append(c)
    while len(out)<count:
        out.append(out[-1])
    return out[:count]


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
    im.save(path,quality=90)


def download_visuals(urls,outdir,title):
    """Download images in streaming chunks so a single large response cannot consume Render RAM."""
    outdir.mkdir(parents=True,exist_ok=True); candidates=[]; seen=set()
    for i,item in enumerate(urls[:24]):
        u=item.get('url') if isinstance(item,dict) else item
        label=item.get('label','') if isinstance(item,dict) else ''
        raw=None
        try:
            raw=outdir/f'raw_{i}'
            with requests.get(u,headers={'User-Agent':UA,'Accept-Encoding':'identity'},timeout=(10,25),stream=True) as r:
                r.raise_for_status()
                ctype=(r.headers.get('content-type') or '').lower()
                if 'image' not in ctype and not u.lower().split('?')[0].endswith(('.jpg','.jpeg','.png','.webp','.avif')):
                    continue
                total=0
                with raw.open('wb') as f:
                    for chunk in r.iter_content(256*1024):
                        if not chunk: continue
                        total += len(chunk)
                        if total > 8*1024*1024:
                            raise RuntimeError('imagem excede 8 MB')
                        f.write(chunk)
            if raw.stat().st_size<15000: raw.unlink(missing_ok=True); continue
            score=_image_quality(raw)
            if score < 0: raw.unlink(missing_ok=True); continue
            im=Image.open(raw).convert('RGB')
            if max(im.size)<900: raw.unlink(missing_ok=True); continue
            im.thumbnail((1600,1600),Image.Resampling.BILINEAR)
            p=outdir/f'good_{len(candidates):02d}.jpg'; im.save(p,quality=88)
            im.close(); raw.unlink(missing_ok=True)
            key=(p.stat().st_size,label[:80])
            if key in seen: p.unlink(missing_ok=True); continue
            seen.add(key); candidates.append({'score':score,'path':p,'label':label,'url':u})
        except Exception:
            if raw:
                try: raw.unlink(missing_ok=True)
                except Exception: pass
    candidates.sort(key=lambda x:x['score'],reverse=True)
    paths=candidates[:12]
    if len(paths)<3:
        while len(paths)<3:
            p=outdir/f'fallback_{len(paths)}.jpg'; make_fallback(p,len(paths),title); paths.append({'score':60,'path':p,'label':title,'url':''})
    return paths


def _smart_crop(im,W,H,variant=0):
    im=im.convert('RGB')
    # Work out the 9:16 crop and choose among several horizontal/vertical positions
    # using a simple visual-information score, avoiding white/flat areas.
    scale=max(W/im.width,H/im.height); nw,nh=int(im.width*scale),int(im.height*scale)
    big=im.resize((nw,nh),Image.Resampling.LANCZOS)
    max_left=max(0,nw-W); max_top=max(0,nh-H)
    positions=[0.08,0.28,0.50,0.72,0.90]
    best=None
    for frac in positions:
        left=int(max_left*frac); top=int(max_top*0.50)
        crop=big.crop((left,top,left+W,top+H)); sm=crop.resize((90,160),Image.Resampling.BILINEAR)
        px=list(sm.getdata()); n=len(px)
        white=sum(1 for r,g,b in px if r>242 and g>242 and b>242)/n
        gray=sum(1 for r,g,b in px if abs(r-g)<5 and abs(g-b)<5 and 150<r<242)/n
        spread=sum(max(p)-min(p) for p in px)/n
        score=(1-white-gray)*80 + min(spread/35,2)*20
        if best is None or score>best[0]: best=(score,crop)
    return best[1] if best else big.crop((max(0,max_left//2),max(0,max_top//2),max(0,max_left//2)+W,max(0,max_top//2)+H))


def prepare_scene(src,dst,caption,idx,total):
    """Prepare a clean background image for the final editor overlay.
    No scene counter and no baked-in caption: the final timeline draws captions once.
    """
    W,H=360,640
    im=Image.open(src).convert('RGB')
    im=_smart_crop(im,W,H,idx)
    zooms=[1.00,1.035,1.065,1.02,1.055,1.085,1.015,1.045,1.075,1.025,1.06,1.09]
    z=zooms[idx % len(zooms)]
    nw,nh=int(W*z),int(H*z)
    im=im.resize((nw,nh),Image.Resampling.BILINEAR)
    max_l=max(0,nw-W); max_t=max(0,nh-H)
    x=int(max_l*((idx*0.23)%1.0)); y=int(max_t*(0.28+0.44*((idx*0.37)%1.0)))
    im=im.crop((x,y,x+W,y+H))
    ov=Image.new('RGBA',(W,H),(0,0,0,0)); od=ImageDraw.Draw(ov)
    od.rectangle((0,0,W,42),fill=(0,0,0,120))
    od.text((12,10),'GTA OCULTO',font=font(15,True),fill='white')
    im=Image.alpha_composite(im.convert('RGBA'),ov).convert('RGB')
    im.save(dst,quality=84,optimize=True)
    im.close(); ov.close()


def run_cmd(cmd,timeout=240):
    # Render Free has only 512 MB. Never retain FFmpeg's stderr in Python memory.
    err_path=WORK/'ffmpeg_last_error.log'
    try:
        with err_path.open('w',encoding='utf-8',errors='ignore') as ef:
            p=subprocess.run(cmd,stdout=subprocess.DEVNULL,stderr=ef,text=True,timeout=timeout)
        if p.returncode:
            try:
                msg=err_path.read_text(encoding='utf-8',errors='ignore')[-3500:]
            except Exception:
                msg=f'FFmpeg terminou com código {p.returncode}'
            raise RuntimeError(msg)
        return ''
    finally:
        try: err_path.unlink()
        except Exception: pass


def duration_of_audio(path):
    try:
        out=run_cmd(['ffprobe','-v','error','-show_entries','format=duration','-of','default=nw=1:nk=1',str(path)],30); return max(20,min(42,float(out.strip())))
    except Exception: return 30.0

async def make_tts(text,path):
    if edge_tts is None: raise RuntimeError('edge-tts não disponível no servidor')
    last=None
    for voice in ['pt-BR-AntonioNeural','pt-BR-FranciscaNeural']:
        try: await edge_tts.Communicate(text,voice,rate='+3%',pitch='-2Hz').save(str(path)); return
        except Exception as e: last=e
    raise RuntimeError(f'falha na narração: {last}')


def _safe_filename(name):
    return re.sub(r'[^a-zA-Z0-9._-]+','_',name).strip('_')[:100]


def _http_total_size(url):
    headers={'User-Agent':UA,'Accept-Encoding':'identity'}
    try:
        r=requests.head(url,headers=headers,timeout=20,allow_redirects=True)
        n=int(r.headers.get('content-length','0') or 0)
        if n: return n
    except Exception:
        pass
    try:
        r=requests.get(url,headers={**headers,'Range':'bytes=0-0'},timeout=(15,30),stream=True)
        cr=r.headers.get('content-range','')
        m=re.search(r'/([0-9]+)$',cr)
        if r.status_code==206 and m: return int(m.group(1))
    except Exception:
        pass
    return 0


def _http_range(url,start,end):
    if end < start: return b''
    headers={'User-Agent':UA,'Accept-Encoding':'identity','Range':f'bytes={start}-{end}'}
    r=requests.get(url,headers=headers,timeout=(20,90))
    if r.status_code != 206:
        raise RuntimeError(f'CDN não aceitou Range HTTP (status {r.status_code}).')
    return r.content


def _remote_zip_entries(url):
    """Read only the ZIP directory from Rockstar CDN; never download the whole ZIP."""
    total=_http_total_size(url)
    if total <= 0: raise RuntimeError('Não foi possível descobrir o tamanho da mídia oficial.')
    tail_start=max(0,total-131072)
    tail=_http_range(url,tail_start,total-1)
    pos=tail.rfind(b'PK\x05\x06')
    if pos<0: raise RuntimeError('Assinatura ZIP oficial não encontrada.')
    eocd=tail[pos:pos+22]
    if len(eocd)<22: raise RuntimeError('Cabeçalho ZIP incompleto.')
    _,disk,cd_disk,n_disk,n_total,cd_size,cd_offset,comment=struct.unpack('<4s4H2LH',eocd)
    if cd_size<=0 or n_total<=0: raise RuntimeError('ZIP oficial sem arquivos utilizáveis.')
    cd=_http_range(url,cd_offset,cd_offset+cd_size-1)
    entries=[]; p=0
    while p+46<=len(cd):
        if cd[p:p+4] != b'PK\x01\x02': break
        vals=struct.unpack('<4s6H3L5H2L',cd[p:p+46])
        comp=vals[8]; csize=vals[8]; usize=vals[9]; fn=vals[10]; extra=vals[11]; comm=vals[12]; local=vals[16]
        nameb=cd[p+46:p+46+fn]
        try: name=nameb.decode('utf-8')
        except Exception: name=nameb.decode('cp437','replace')
        entries.append({'name':name,'compression':comp,'compressed':csize,'size':usize,'local':local})
        p += 46+fn+extra+comm
    if len(entries)<3: raise RuntimeError(f'ZIP oficial expôs apenas {len(entries)} arquivos.')
    return total,entries


def _remote_zip_extract(url,entry,target):
    """Download one selected ZIP member by byte ranges and decompress locally."""
    local=_http_range(url,entry['local'],entry['local']+29)
    if local[:4] != b'PK\x03\x04': raise RuntimeError(f'Cabeçalho local inválido: {entry["name"]}')
    _,ver,flags,method,mtime,mdate,crc,csize,usize,fn,extra=struct.unpack('<4s5H3L2H',local)
    data_start=entry['local']+30+fn+extra
    data_end=data_start+entry['compressed']-1
    comp=_http_range(url,data_start,data_end)
    if method==0:
        raw=comp
    elif method==8:
        try: raw=zlib.decompress(comp,-15)
        except Exception as e: raise RuntimeError(f'Falha ao descompactar {entry["name"]}: {e}')
    else:
        raise RuntimeError(f'Compressão ZIP não suportada em {entry["name"]}: {method}')
    if entry['size'] and len(raw)!=entry['size']:
        raise RuntimeError(f'Tamanho inesperado em {entry["name"]}: {len(raw)} de {entry["size"]} bytes.')
    target.write_bytes(raw)


def download_official_video_clips(outdir, jid=None):
    """Download Rockstar's official 9-clip ZIP once, extract three real clips, cache them.
    This deliberately avoids the fragile HTTP-Range ZIP parser. The ZIP is streamed to
    disk (never loaded into RAM) and deleted after the three normalized clips are cached.
    """
    import zipfile
    outdir.mkdir(parents=True, exist_ok=True)
    cache=WORK/'official_video_cache'; cache.mkdir(parents=True, exist_ok=True)
    clips=sorted([p for p in cache.glob('rockstar_real_*.mp4') if p.stat().st_size>20000])
    if len(clips)>=6:
        return clips[:6]

    zip_path=cache/'GTAVI_Videos_full.zip'
    part=cache/'GTAVI_Videos_full.zip.part'
    try:
        if not zip_path.exists() or zip_path.stat().st_size<100000:
            if jid: update_job(jid,log='Baixando o pacote oficial de vídeos da Rockstar (1 vez, em cache)...')
            if part.exists():
                try: part.unlink()
                except Exception: pass
            total=0; done=0
            with requests.get(ROCKSTAR_VIDEO_ZIP, stream=True, timeout=(20,120), headers={'User-Agent':UA,'Accept-Encoding':'identity'}) as r:
                r.raise_for_status()
                total=int(r.headers.get('content-length','0') or 0)
                with part.open('wb') as f:
                    for chunk in r.iter_content(chunk_size=1024*1024):
                        if not chunk: continue
                        f.write(chunk); done += len(chunk)
                        if jid and total and (done % (20*1024*1024) < len(chunk)):
                            update_job(jid,log=f'Mídia oficial: {done/1048576:.0f}/{total/1048576:.0f} MB baixados...')
            if not part.exists() or part.stat().st_size<100000:
                raise RuntimeError('Download do pacote oficial terminou vazio ou incompleto.')
            part.replace(zip_path)

        if jid: update_job(jid,log='Lendo os 9 clipes oficiais da Rockstar...')
        with zipfile.ZipFile(zip_path,'r') as zf:
            names=[n for n in zf.namelist() if n.lower().endswith(('.mp4','.mov','.m4v'))]
            if len(names)<3:
                raise RuntimeError(f'O pacote oficial retornou apenas {len(names)} vídeos.')
            preferred=[]
            for key in ('Jason','Lucia','Cal','Boobie','Raul','Brian','Real','Dre'):
                preferred += [n for n in names if key.lower() in Path(n).stem.lower() and n not in preferred]
            chosen=(preferred+[n for n in names if n not in preferred])[:6]
            if len(chosen)<6:
                raise RuntimeError(f'A mídia oficial possui apenas {len(chosen)} vídeos utilizáveis.')
            ff=str(__import__('imageio_ffmpeg').get_ffmpeg_exe())
            for i,name in enumerate(chosen):
                target=cache/f'rockstar_real_{i}.mp4'
                if target.exists() and target.stat().st_size>20000: continue
                raw=cache/f'raw_{i}.mp4'
                if jid: update_job(jid,log=f'Preparando clipe oficial {i+1}/3: {Path(name).stem}...')
                with zf.open(name) as src, raw.open('wb') as dst:
                    while True:
                        chunk=src.read(1024*1024)
                        if not chunk: break
                        dst.write(chunk)
                run_cmd([ff,'-y','-i',str(raw),'-t','5',
                         '-vf','scale=160:284:force_original_aspect_ratio=increase,crop=160:284,setsar=1,fps=12',
                         '-an','-c:v','libx264','-preset','ultrafast','-crf','32','-threads','1','-filter_threads','1','-filter_complex_threads','1','-x264-params','threads=1:lookahead-threads=1',
                         '-pix_fmt','yuv420p','-movflags','+faststart',str(target)],90)
                try: raw.unlink()
                except Exception: pass
        clips=sorted([p for p in cache.glob('rockstar_real_*.mp4') if p.stat().st_size>20000])
        if len(clips)<6:
            raise RuntimeError(f'Apenas {len(clips)} clipes reais foram preparados.')
        try: zip_path.unlink()
        except Exception: pass
        return clips[:6]
    except Exception as e:
        try:
            if part.exists(): part.unlink()
        except Exception: pass
        raise RuntimeError('Não foi possível obter os vídeos oficiais da Rockstar: '+str(e)[:1800])

def _video_relevance(path,title):
    text=(path.stem+' '+title).lower()
    score=0
    groups=[('jason',12),('lucia',12),('vice',8),('leonida',8),('cal',4),('boobie',4),('raul',4),('brian',4),('real',4),('dre',4),('cover',1)]
    for k,v in groups:
        if k in text: score+=v
    return score


def select_video_clips(videos,title,count=5):
    ranked=sorted(videos,key=lambda p:_video_relevance(p,title),reverse=True)
    return ranked[:count]


def _caption_overlay(path,caption,idx,total,W=240,H=426):
    # Single clean overlay. No scene counter and no baked duplicate caption.
    im=Image.new('RGBA',(W,H),(0,0,0,0)); d=ImageDraw.Draw(im)
    d.rectangle((0,0,W,42),fill=(0,0,0,125))
    d.text((12,10),'GTA OCULTO',font=font(15,True),fill='white')
    f=font(18,True); lines=wrap_text(d,str(caption),f,W-34)[:3]
    box_h=18+len(lines)*24; y=H-box_h-16
    d.rounded_rectangle((10,y,W-10,H-16),radius=10,fill=(7,9,13,215),outline=(215,28,45),width=1)
    yy=y+8
    for line in lines:
        d.text((17,yy),line,font=f,fill='white',stroke_width=1,stroke_fill='black'); yy+=24
    im.save(path)


def _ffmpeg_text(s):
    return s.replace('\\','\\\\').replace(':','\\:').replace("'","\\'").replace('%','\\%').replace('\n',' ')


def make_multimedia_video(video_clips, image_paths, audio, out, duration, captions):
    """Ultra-low-memory editor for Render Free 512 MB.
    Builds one 240x426 scene at a time and produces a 540x960 vertical MP4.
    540x960 is the quality target; scenes are built sequentially at 240x426 to stay within the free RAM limit.
    """
    ff=str(__import__('imageio_ffmpeg').get_ffmpeg_exe())
    work=out.parent/'timeline'; work.mkdir(exist_ok=True)
    if len(video_clips)<3: raise RuntimeError('A edição precisa de pelo menos 3 vídeos reais.')
    # Alterna movimento e imagens, mas termina com vídeo real para evitar
    # sensação de quadro congelado no encerramento.
    assets=[]
    order=[('video',0),('image',0),('video',1),('image',1),('video',2),('image',2),('video',3),('video',4),('video',5)]
    for kind,idx in order:
        if kind=='video' and idx < len(video_clips):
            assets.append(('video',video_clips[idx]))
        elif kind=='image' and idx < len(image_paths):
            assets.append(('image',image_paths[idx]))
    per=max(2.5,duration/len(assets)); scene_files=[]
    for i,(kind,src) in enumerate(assets):
        scene=work/f'scene_{i:02d}.mp4'; overlay=work/f'overlay_{i:02d}.png'
        _caption_overlay(overlay,captions[i % len(captions)],i,len(assets),240,426)
        if kind=='video':
            vf='scale=240:426:force_original_aspect_ratio=increase,crop=240:426,setsar=1,fps=15'
            inp=['-stream_loop','-1','-i',str(src)]
        else:
            vf="scale=240:426:force_original_aspect_ratio=increase,crop=240:426,setsar=1,zoompan=z='min(zoom+0.0015,1.02)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s=240x426:fps=15"
            inp=['-loop','1','-i',str(src)]
        cmd=[ff,'-loglevel','error','-y']+inp+['-loop','1','-i',str(overlay),'-t',f'{per:.3f}',
             '-filter_complex',f'[0:v]{vf}[v];[1:v]format=rgba[o];[v][o]overlay=0:0:shortest=1[outv]',
             '-map','[outv]','-an','-c:v','libx264','-preset','ultrafast','-crf','29',
             '-threads','1','-filter_threads','1','-filter_complex_threads','1',
             '-x264-params','threads=1:lookahead-threads=1','-pix_fmt','yuv420p','-movflags','+faststart',str(scene)]
        run_cmd(cmd,75)
        scene_files.append(scene)
        try: overlay.unlink()
        except Exception: pass
    listfile=work/'timeline.txt'
    with listfile.open('w',encoding='utf-8') as f:
        for sf in scene_files: f.write(f"file '{sf.as_posix()}'\n")
    # Final encode at 480x854: conservative 9:16 output for Render Free 512 MB.
    run_cmd([ff,'-loglevel','error','-y','-f','concat','-safe','0','-i',str(listfile),'-i',str(audio),
             '-t',f'{duration:.2f}','-vf','scale=540:960:flags=fast_bilinear,format=yuv420p','-r','15',
             '-c:v','libx264','-preset','ultrafast','-crf','27','-threads','1','-filter_threads','1','-filter_complex_threads','1',
             '-x264-params','threads=1:lookahead-threads=1','-c:a','aac','-b:a','96k',
             '-movflags','+faststart','-shortest',str(out)],180)
    for p in scene_files:
        try: p.unlink()
        except Exception: pass
    try: listfile.unlink()
    except Exception: pass

def make_video(scenes,audio,out,duration):
    # Corte mais rápido: 12 cenas em ~2–3 s cada. A troca de enquadramento já foi
    # preparada nas imagens; o concat continua leve o bastante para o Render Free.
    listfile=out.parent/'scenes.txt'; per=duration/len(scenes)
    with listfile.open('w',encoding='utf-8') as f:
        for p in scenes:
            f.write(f"file '{p.as_posix()}'\nduration {per:.3f}\n")
        f.write(f"file '{scenes[-1].as_posix()}'\n")
    ff=str(__import__('imageio_ffmpeg').get_ffmpeg_exe())
    run_cmd([ff,'-y','-f','concat','-safe','0','-i',str(listfile),'-i',str(audio),
             '-t',f'{duration:.2f}','-r','24','-c:v','libx264','-preset','ultrafast',
             '-crf','22','-threads','2','-profile:v','high','-pix_fmt','yuv420p',
             '-c:a','aac','-b:a','128k','-movflags','+faststart','-shortest',str(out)],300)

def make_cover(scene,title,out):
    im=Image.open(scene).convert('RGB'); d=ImageDraw.Draw(im,'RGBA'); d.rectangle((45,500,1035,1330),fill=(0,0,0,165),outline=(225,25,45),width=5); f=font(72,True); y=610
    for line in wrap_text(d,title,f,880)[:6]: d.text((100,y),line,font=f,fill='white',stroke_width=2,stroke_fill='black'); y+=88
    d.text((100,120),'GTA OCULTO',font=font(42,True),fill='white'); im.save(out,quality=92)

def evaluate(script,duration,scene_count,visual_quality):
    score=100
    if duration<24: score-=5
    if duration>38: score-=5
    if len(script['narration'])<300: score-=5
    if '?' not in script['narration'][:190]: score-=4
    if scene_count<8: score-=15
    elif scene_count<10: score-=6
    score += max(-15,min(5,int((visual_quality-70)/4)))
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
        paths=download_visuals(urls,jobdir/'visuals',topic['title'])
        caps=build_dynamic_captions(script, topic, 9)
        image_order=select_visuals(paths,topic['title'],3)
        image_scenes=[]
        for i,src in enumerate(image_order):
            dst=jobdir/f'image_{i}.jpg'; prepare_scene(src,dst,caps[min(i,len(caps)-1)],i,9); image_scenes.append(dst)
        update_job(jid,stage='NARRAÇÃO',progress=60,log='Gerando narração PT-BR...'); audio=jobdir/'narracao.mp3'; asyncio.run(make_tts(script['narration'],audio)); duration=duration_of_audio(audio)
        update_job(jid,stage='EDIÇÃO',progress=74,log=f'Obtendo vídeos oficiais da Rockstar e montando timeline com movimento real / {duration:.1f}s...')
        official_videos=download_official_video_clips(jobdir/'official_videos', jid)
        selected_videos=select_video_clips(official_videos,topic['title'],6)
        update_job(jid,log=f'{len(selected_videos)} vídeos oficiais disponíveis. Editando cortes reais em 9:16 / {duration:.1f}s...')
        video=jobdir/'GTA_OCULTO_SHORT.mp4'; make_multimedia_video(selected_videos,image_scenes,audio,video,duration,caps)
        cover=jobdir/'CAPA.jpg'; make_cover(image_scenes[0],topic['title'],cover)
        update_job(jid,stage='AVALIAÇÃO',progress=92,log='Avaliando hook, ritmo, visuais, duração, formato e legendas...'); visual_quality=100
        for sp in image_scenes:
            q=_image_quality(sp); visual_quality=min(visual_quality, max(0,q))
        score=evaluate(script,duration,9,visual_quality)
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
            with LOCK:
                jobs=load_jobs()
                # If Render restarts after a long encode, a previous RUNNING job
                # is recovered instead of disappearing from the queue.
                now=time.time()
                for j in jobs.values():
                    if j.get('status')=='RUNNING':
                        try:
                            age=now-datetime.fromisoformat(j.get('updated_at','')).timestamp()
                        except Exception:
                            age=0
                        if age>1800:
                            j['status']='QUEUED'; j['stage']='FILA'; j['progress']=0
                            j['log']='Produção recuperada após reinício do servidor. Retomando automaticamente.'
                save_jobs(jobs)
                target=next((j for j in jobs.values() if j.get('status')=='QUEUED'),None)
            if target and not PROCESSING:
                PROCESSING=True
                threading.Thread(target=produce_job,args=(target['id'],),daemon=True).start()
            time.sleep(2)
        except Exception:
            time.sleep(5)

@APP.get('/')
def home(): return render_template_string(PAGE)
@APP.get('/health')
def health(): return jsonify(ok=True,app='GTA Oculto AI',version='CLOUD-VIDEO-REAL-RAM-ULTIMATE',processor='cloud')
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

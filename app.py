import struct, zlib
import os, json, uuid, threading, time, asyncio, subprocess, shutil, re, sys, math
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse, quote, quote_plus, parse_qs

# V42 bounded auditor: optional module, preserving the proven V41.3 pipeline.
try:
    from audit_engine import full_audit as v42_full_audit, caption_audit as v42_caption_audit, repair_captions as v42_repair_captions
except Exception:
    v42_full_audit = v42_caption_audit = v42_repair_captions = None

import requests
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
from flask import Flask, request, jsonify, render_template_string, send_from_directory
from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageChops, ImageStat

try:
    import edge_tts
except Exception:
    edge_tts = None

# Google News URL decoder: Google News RSS uses encoded redirect URLs that plain requests
# may not resolve. We install/use the maintained decoder only for resolving the source URL.
try:
    from googlenewsdecoder import gnewsdecoder as _gnewsdecoder
except Exception:
    _gnewsdecoder = None

APP = Flask(__name__)
app = APP
BASE = Path(__file__).resolve().parent
WORK = Path(os.getenv('GTA_WORKSPACE', str(BASE / 'workspace')))
WORK.mkdir(parents=True, exist_ok=True)
try:
    from autonomous_engine import AutonomousEngine
    AUTONOMOUS_ENGINE = AutonomousEngine(BASE)
except Exception:
    AUTONOMOUS_ENGINE = None
WORK.mkdir(parents=True, exist_ok=True)
STATE_FILE = WORK / 'jobs.json'
LOCK = threading.RLock()
PROCESSING = False
# V43: autonomous recovery is ON by default. It may switch to another validated Radar topic
# when a source cannot be resolved, so a transient resolver failure never requires the owner
# to intervene manually. Set GTA_AUTONOMOUS_MODE=0 only to disable this behavior.
AUTONOMOUS_MODE = os.getenv('GTA_AUTONOMOUS_MODE','1').strip().lower() not in ('0','false','off','no')
AUTONOMOUS_MAX_TOPIC_RECOVERY = max(1, min(6, int(os.getenv('GTA_AUTONOMOUS_MAX_TOPIC_RECOVERY','5'))))
_last_gnews_diagnostics = []
UA = 'GTA-Oculto-AI/Cloud-Final/V55-SOURCE-RECOVERY-3' 
ROCKSTAR_VI = 'https://www.rockstargames.com/VI'
ROCKSTAR_NEWS = 'https://www.rockstargames.com/newswire/article/4k138k8okkk483/grand-theft-auto-vi-an-extended-look-now-playing'
ROCKSTAR_VIDEO_ZIP = 'https://media-rockstargames-com.akamaized.net/VI/downloads/videos/GTAVI_Videos.zip'
BUILD_VERSION = 'V56-VISUAL-DIVERSITY-RETENTION-20261008'

FALLBACK_TOPICS = [
    {'id':'leonida','score':96,'priority':'ALTA','title':'GTA 6: o detalhe de Leonida que pode mudar a história','source':'Rockstar Games','url':ROCKSTAR_VI,
     'recovery_urls':[ROCKSTAR_NEWS,'https://gamenoticias.com.br/gta-6-50-novidades-incriveis-confirmadas-no-novo-jogo-da-rockstar/']},
    {'id':'jason-lucia','score':93,'priority':'ALTA','title':'Jason e Lucia: o que a Rockstar já confirmou oficialmente','source':'Rockstar Games','url':ROCKSTAR_VI,
     'recovery_urls':[ROCKSTAR_NEWS,'https://leonidainteractive.com/wiki/pt-br/trailers/trailer-3/']},
    {'id':'estado-leonida','score':90,'priority':'ALTA','title':'A história de GTA 6 vai muito além de Vice City','source':'Rockstar Games','url':ROCKSTAR_NEWS,
     'recovery_urls':[ROCKSTAR_NEWS,'https://gamenoticias.com.br/gta-6-50-novidades-incriveis-confirmadas-no-novo-jogo-da-rockstar/']},
    {'id':'detalhes','score':84,'priority':'MÉDIA','title':'Os detalhes escondidos que a Rockstar colocou em GTA 6','source':'Rockstar Games','url':ROCKSTAR_VI,
     'recovery_urls':['https://gamenoticias.com.br/gta-6-50-novidades-incriveis-confirmadas-no-novo-jogo-da-rockstar/',ROCKSTAR_NEWS,'https://leonidainteractive.com/wiki/pt-br/trailers/trailer-3/']},
    {'id':'extended-look','score':88,'priority':'ALTA','title':'GTA 6: 50 novidades confirmadas no novo jogo da Rockstar','source':'Game Notícias','url':'https://gamenoticias.com.br/gta-6-50-novidades-incriveis-confirmadas-no-novo-jogo-da-rockstar/',
     'recovery_urls':['https://gamenoticias.com.br/gta-6-50-novidades-incriveis-confirmadas-no-novo-jogo-da-rockstar/','https://www.omelete.com.br/games/gta-6-revela-detalhes-da-historia-confira']},
]


RADAR_FILE = WORK / 'radar.json'
LEARNING_FILE = WORK / 'learning.json'
LEARNING_LOCK = threading.RLock()
RESOLVER_MEMORY_FILE = WORK / 'resolver_memory.json'
RESOLVER_LOCK = threading.RLock()
RADAR_LOCK = threading.RLock()
RADAR_FEEDS = [
    ('Google News — GTA VI', 'https://news.google.com/rss/search?q=GTA+VI&hl=pt-BR&gl=BR&ceid=BR:pt-419'),
    ('Google News — GTA 6 Rockstar', 'https://news.google.com/rss/search?q=GTA+6+Rockstar&hl=pt-BR&gl=BR&ceid=BR:pt-419'),
    ('Google News — GTA 6 trailer', 'https://news.google.com/rss/search?q=GTA+6+trailer&hl=pt-BR&gl=BR&ceid=BR:pt-419'),
    ('Google News — GTA 6 Vice City', 'https://news.google.com/rss/search?q=GTA+6+Vice+City&hl=pt-BR&gl=BR&ceid=BR:pt-419'),
]
RADAR_KEYWORDS = {
    'gta 6':18,'gta vi':18,'grand theft auto vi':18,'rockstar':10,'trailer':12,'revel':10,'anunci':9,
    'lançamento':9,'release':9,'jason':7,'lucia':7,'leonida':7,'vice city':7,'gameplay':9,'álbum':7,
    'album':7,'pré-venda':6,'pre-order':6,'collector':6,'colecion':6,'vazamento':4,'rumor':4,'teaser':8
}

PAGE = '''<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>GTA OCULTO AI</title><style>
*{box-sizing:border-box}
:root{--bg:#07090d;--panel:#0d1118;--panel2:#111722;--line:#202938;--line2:#2a3444;--text:#f4f7fb;--muted:#8d98a8;--purple:#8b4dff;--cyan:#34c8ff;--green:#25e28c;--yellow:#f4c44e;--red:#ff5266}
body{margin:0;background:radial-gradient(circle at 50% -10%,#11152a 0,#07090d 42%);color:var(--text);font-family:Inter,Arial,Helvetica,sans-serif}
.wrap{max-width:1480px;margin:auto;padding:18px}
.top{display:flex;justify-content:space-between;align-items:center;margin-bottom:14px}.brand{font-size:24px;font-weight:950;letter-spacing:-.5px}.brand span{color:#ff3348}.status{border:1px solid #254a3b;background:#0c1714;border-radius:999px;padding:8px 12px;color:#62e9a1;font-size:11px;font-weight:900}
.hero{background:linear-gradient(135deg,#101522,#0c1018);border:1px solid #263143;border-radius:16px;padding:20px;display:flex;justify-content:space-between;gap:18px;align-items:center}.eyebrow{color:#a66cff;font-size:10px;font-weight:950;letter-spacing:1.5px}.hero h1{font-size:25px;margin:7px 0}.muted{color:var(--muted)}.buttons{display:flex;gap:8px}.btn{border:1px solid #2b3545;border-radius:9px;padding:11px 14px;background:#151c27;color:#fff;font-weight:900;cursor:pointer}.btn.red{background:linear-gradient(135deg,#ff4058,#a92fff);border:0;box-shadow:0 8px 24px #6e2cff30}
.control{margin-top:10px;padding:10px;background:#0b0f15;border:1px solid var(--line);border-radius:12px;display:flex;gap:8px}.control input{flex:1;background:#111721;border:1px solid #273244;border-radius:8px;color:#fff;padding:12px}.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:13px 0}.stat{background:linear-gradient(145deg,#101722,#0d121a);border:1px solid #263142;border-radius:13px;padding:14px}.stat small{color:#7f8a9b;font-weight:900;letter-spacing:.6px}.stat b{display:block;font-size:28px;margin-top:4px}.panel{margin:12px 0;padding:15px;background:rgba(13,17,24,.92);border:1px solid #222d3d;border-radius:15px;box-shadow:0 8px 30px #00000020}.panel h3{font-size:12px;margin:0 0 10px;letter-spacing:.7px}.notice{padding:10px 12px;border:1px dashed #303b4b;border-radius:9px;background:#0a0e14;color:#aeb8c7;font-size:11px}
.steps{display:grid;grid-template-columns:repeat(8,1fr);gap:6px}.step{background:#141b25;border:1px solid #202a38;border-radius:7px;padding:9px 4px;text-align:center;font-size:9px;font-weight:950;color:#758195}.step.active{background:#21162d;color:#c58cff;border-color:#7446a8;box-shadow:0 0 18px #873cff18}
/* Editor-Chefe */
.editor-shell{position:relative;border:1px solid #7547e8;border-radius:15px;background:radial-gradient(circle at 25% 10%,#211737 0,#0d121b 42%,#0b1017 100%);padding:16px;overflow:hidden}.editor-shell:before{content:"";position:absolute;inset:-1px;background:linear-gradient(90deg,#6f35ff20,transparent 45%,#2f8dff12);pointer-events:none}.editor-head{position:relative;display:flex;justify-content:space-between;align-items:center;gap:14px;margin-bottom:13px}.editor-brand{display:flex;align-items:center;gap:10px}.editor-icon{width:38px;height:38px;border-radius:11px;display:grid;place-items:center;background:linear-gradient(145deg,#7d38ff,#bd4cff);font-size:20px;box-shadow:0 0 22px #8a43ff55}.editor-head h2{margin:0;font-size:19px}.editor-head p{margin:2px 0 0;color:#8e9aac;font-size:10px}.editor-actions{display:flex;gap:8px}.editor-status{padding:9px 12px;border:1px solid #1e6c55;background:#0d1d18;border-radius:9px;color:#51e7a4;font-size:10px;font-weight:900}.editor-grid-main{position:relative;display:grid;grid-template-columns:180px minmax(0,1fr) 165px;gap:14px}.editor-cover{border-radius:12px;border:1px solid #2a3547;background:linear-gradient(145deg,#182338,#111724);min-height:180px;display:flex;align-items:flex-end;padding:12px;overflow:hidden;position:relative}.editor-cover:before{content:"GTA VI";position:absolute;right:-10px;top:18px;font-size:52px;font-weight:950;color:#ffffff10;transform:rotate(-12deg)}.editor-cover-icon{font-size:54px;filter:drop-shadow(0 5px 12px #000)}.editor-content{min-width:0}.editor-tag{display:inline-block;padding:5px 8px;border-radius:7px;background:#173b88;color:#7dc7ff;font-size:9px;font-weight:950}.editor-title{font-size:21px;font-weight:950;line-height:1.18;margin:9px 0 11px}.editor-metrics{display:grid;grid-template-columns:repeat(5,1fr);gap:7px}.editor-metric{background:#111824;border:1px solid #263244;border-radius:9px;padding:8px}.editor-metric small{display:block;color:#7e8a9d;font-size:8px;font-weight:900}.editor-metric b{display:block;font-size:14px;margin-top:4px}.metric-green{color:#56e8a4}.metric-purple{color:#b98cff}.editor-copy{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:9px}.editor-hook,.editor-angle{background:#101722;border:1px solid #34405a;border-radius:10px;padding:10px;min-height:66px}.editor-hook{border-color:#5c37ad}.editor-hook b,.editor-angle b{display:block;color:#e8ebf1;font-size:9px;margin-bottom:5px}.editor-copy span{font-size:11px;color:#dce1ea;line-height:1.35}.editor-decision{border:1px solid #246a52;border-radius:12px;background:#0c1b16;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;padding:14px;min-height:180px}.decision-check{font-size:31px;color:#36e29a}.decision-word{font-size:18px;font-weight:950;color:#43e6a1;margin:8px 0}.decision-reason{font-size:10px;color:#91a0af;line-height:1.4}.editor-produce{margin-top:10px;width:100%;padding:11px;border:0;border-radius:9px;background:linear-gradient(135deg,#9b4cff,#5c3bff);color:white;font-weight:950;cursor:pointer;box-shadow:0 8px 24px #6c3cff35}
/* Roteiro V28 */
.script-preview{margin-top:9px;background:linear-gradient(145deg,#101722,#0c121a);border:1px solid #2a3650;border-radius:11px;padding:10px}.script-head{display:flex;justify-content:space-between;align-items:center;gap:10px;margin-bottom:8px}.script-head b{display:block;font-size:9px;color:#e8ebf1}.script-head span{display:block;color:#7e8b9f;font-size:8px;margin-top:2px}.script-stats{padding:5px 8px;border:1px solid #29364b;border-radius:7px;color:#a98cff;font-size:8px;font-weight:900;white-space:nowrap}.script-flow{display:grid;grid-template-columns:repeat(5,1fr);gap:6px}.script-flow>div{min-width:0;padding:8px;background:#0c121a;border:1px solid #202c3e;border-radius:8px}.script-flow small{display:block;color:#9e6cff;font-size:7px;font-weight:950;margin-bottom:4px}.script-flow span{display:block;color:#cdd5df;font-size:8px;line-height:1.35}.editor-title{max-width:100%}
@media(max-width:1050px){.script-flow{grid-template-columns:1fr 1fr}.editor-grid-main{grid-template-columns:150px minmax(0,1fr)}.editor-decision{grid-column:1/-1;min-height:auto}.editor-produce{width:auto;min-width:220px}}
@media(max-width:700px){.script-flow{grid-template-columns:1fr}.editor-grid-main{grid-template-columns:1fr}.editor-cover{min-height:100px}.editor-metrics{grid-template-columns:repeat(2,1fr)}.editor-copy{grid-template-columns:1fr}.script-head{align-items:flex-start;flex-direction:column}.script-stats{white-space:normal}}
/* Radar */
.radar-head{display:flex;justify-content:space-between;align-items:center;gap:10px;margin-bottom:11px}.radar-head h3{margin:0}.filters{display:flex;gap:6px;flex-wrap:wrap}.filter{border:1px solid #293447;background:#111823;color:#9da8b7;border-radius:8px;padding:7px 10px;font-size:9px;font-weight:950;cursor:pointer}.filter.active{background:linear-gradient(135deg,#7e3cff,#a33fff);border-color:#9e5cff;color:#fff}.table-head,.row{display:grid;grid-template-columns:34px 62px minmax(260px,1fr) 78px 66px 104px 74px 86px;gap:9px;align-items:center}.table-head{padding:8px 10px;color:#687487;font-size:8px;font-weight:950;border-bottom:1px solid #222d3b}.row{padding:10px;border-bottom:1px solid #1d2633}.row:last-child{border-bottom:0}.rank{color:#718096;font-size:10px;font-weight:950}.scorebox{width:40px;height:34px;border-radius:9px;display:grid;place-items:center;font-size:16px;font-weight:950;background:#12281f;color:#46e49b;border:1px solid #1d6248}.scorebox.mid{background:#112438;color:#54bfff;border-color:#24577c}.scorebox.low{background:#2a1719;color:#ff7884;border-color:#6a2b32}.title{font-size:11px;font-weight:900;line-height:1.25}.source{font-size:8px;color:#778496;margin-top:4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.tags{display:flex;gap:4px;flex-wrap:wrap;margin-top:5px}.tag{font-size:7px;padding:3px 5px;border-radius:5px;background:#182230;color:#8fa4bd}.type{justify-self:start;padding:5px 7px;border-radius:6px;font-size:7px;font-weight:950;background:#183c80;color:#82caff}.type.rumor{background:#4a350b;color:#f7c95c}.type.cur{background:#3d2370;color:#cfabff}.conf{font-size:10px;font-weight:900}.confbar{height:4px;background:#202b39;border-radius:9px;margin-top:4px;overflow:hidden}.confbar i{display:block;height:100%;background:#31b8ef}.relevance{padding:5px 6px;border-radius:6px;text-align:center;font-size:7px;font-weight:950;background:#4a390d;color:#f4c64e}.relevance.high{background:#103e2e;color:#4ce7a0}.relevance.low{background:#4a191e;color:#ff7a84}.produce{background:#182333;border:1px solid #2b3a50;color:#dce4ef;border-radius:8px;padding:8px 7px;font-size:8px;font-weight:950;cursor:pointer}.observe{background:#111822}
.job{background:#10161f;border:1px solid #253143;border-radius:10px;padding:12px;margin-top:8px}.jobhead{display:flex;justify-content:space-between;gap:12px}.bar{height:6px;background:#202a37;border-radius:10px;overflow:hidden;margin-top:9px}.bar i{display:block;height:100%;background:linear-gradient(90deg,#8b4dff,#34c8ff)}.log{font-family:monospace;color:#aab5c4;font-size:10px;margin-top:8px;white-space:pre-wrap}.result{display:flex;gap:10px;flex-wrap:wrap;margin-top:10px}.result a{color:#a976ff;text-decoration:none;font-weight:900}.meta{font-size:9px;color:#778496;margin-top:6px}
@media(max-width:1100px){.editor-grid-main{grid-template-columns:1fr}.editor-cover{min-height:110px}.editor-decision{min-height:110px}.table-head{display:none}.row{grid-template-columns:30px 52px 1fr 70px 80px}.row>*:nth-child(4),.row>*:nth-child(5),.row>*:nth-child(6){display:none}}
@media(max-width:800px){.hero{display:block}.buttons{margin-top:12px;flex-wrap:wrap}.stats{grid-template-columns:repeat(2,1fr)}.steps{grid-template-columns:repeat(4,1fr)}.editor-copy{grid-template-columns:1fr}.editor-metrics{grid-template-columns:repeat(2,1fr)}.row{grid-template-columns:28px 48px 1fr 72px}.row .relevance{display:none}.top{align-items:flex-start;gap:10px;flex-direction:column}}
</style></head><body><div class="wrap"><div class="top"><div class="brand">GTA <span>OCULTO</span> AI</div><div class="status">● PRODUÇÃO CLOUD ONLINE</div></div>
<div class="hero"><div><div class="eyebrow">PRODUTOR AUTÔNOMO</div><h1>A IA encontra o assunto. Você decide se quer produzir.</h1><div class="muted">Radar → score → Editor-Chefe → hook → roteiro → visuais → voz → edição → avaliação → Short.</div></div><div class="buttons"><button class="btn red" onclick="createShort()">⚡ CRIAR SHORT</button><button class="btn" onclick="research()">🔥 ATUALIZAR RADAR</button></div></div>
<div class="control"><input id="topic" placeholder="Digite um assunto ou deixe a IA decidir"><button class="btn red" onclick="createShort()">PRODUZIR</button></div>
<div class="stats"><div class="stat"><small>ASSUNTOS</small><b id="assuntos">4</b></div><div class="stat"><small>OPORTUNIDADES</small><b id="opps">4</b></div><div class="stat"><small>PRODUZIDOS</small><b id="produzidos">0</b></div><div class="stat"><small>FILA</small><b id="fila">0</b></div></div>
<div class="panel"><div class="radar-head"><h3>🔥 RADAR GTA VI</h3><div class="filters"><button class="filter active">ATUAL</button><button class="filter" onclick="research()">↻ ATUALIZAR</button></div></div><div id="radarStatus" class="notice">Carregando radar…</div></div><div class="panel"><div id="editorPick" class="notice">Aguardando o Radar.</div></div><div class="panel"><h3>PIPELINE</h3><div class="steps">'''+''.join(f'<div class="step" id="step-{i}">{x}</div>' for i,x in enumerate(['PESQUISA','ANÁLISE','ROTEIRO','VISUAIS','NARRAÇÃO','EDIÇÃO','AVALIAÇÃO','PRONTO']))+'''</div></div>
<div class="panel"><div class="radar-head"><div><h3>OPORTUNIDADES DO RADAR</h3><div class="muted" style="font-size:10px">Assuntos encontrados, agrupados e ranqueados pelo Radar + Editor-Chefe.</div></div><div class="filters"><button class="filter active">TODAS</button><button class="filter">PRODUZIR</button><button class="filter">OBSERVAR</button><button class="filter">BAIXA</button></div></div><div id="oppList">__OPPORTUNITIES__</div></div>
<div class="panel"><h3>PRODUÇÕES</h3><div id="jobs">Nenhuma produção iniciada.</div></div>
<div class="notice">☁️ <b>Modo 100% web:</b> esta versão não depende do seu computador. A produção acontece no próprio servidor. O plano gratuito do Render pode dormir quando fica inativo; o primeiro acesso pode demorar.</div>
</div><script>
function esc(s){return String(s??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[m]))}
function stageIndex(s){return {PESQUISA:0,ANÁLISE:1,ROTEIRO:2,VISUAIS:3,NARRAÇÃO:4,EDIÇÃO:5,AVALIAÇÃO:6,PRONTO:7}[s]??-1}
const LOCAL_OPPORTUNITIES=[
{id:'leonida',score:96,priority:'ALTA',title:'GTA 6: o detalhe de Leonida que pode mudar a história',source:'Rockstar Games'},
{id:'jason-lucia',score:93,priority:'ALTA',title:'Jason e Lucia: o que a Rockstar já confirmou oficialmente',source:'Rockstar Games'},
{id:'estado-leonida',score:90,priority:'ALTA',title:'A história de GTA 6 vai muito além de Vice City',source:'Rockstar Games'},
{id:'detalhes',score:84,priority:'MÉDIA',title:'Os detalhes escondidos que a Rockstar colocou em GTA 6',source:'Rockstar Games'}
];
function drawState(d){
  const opportunities=(d&&Array.isArray(d.opportunities)&&d.opportunities.length)?d.opportunities:LOCAL_OPPORTUNITIES;
  document.getElementById('opps').textContent=opportunities.length;
  document.getElementById('assuntos').textContent=opportunities.length;
  document.getElementById('produzidos').textContent=(d&&d.produced)||0;
  document.getElementById('fila').textContent=(d&&d.queue)||0;
  let rs=(d&&d.radar_status)||'WAITING';
  let msg=(d&&d.radar_updated)?('Última varredura: '+new Date(d.radar_updated).toLocaleString('pt-BR')+' — '+opportunities.length+' oportunidades.'): 'Radar aguardando primeira varredura real.';
  if(rs==='STALE') msg='⚠️ '+msg+' '+((d&&d.radar_error)||'Nenhuma fonte nova respondeu.')+' Os dados exibidos são os últimos válidos.';
  if(rs==='WAITING') msg='⏳ '+((d&&d.radar_error)||'Radar aguardando primeira varredura real.');
  if(rs==='OK') msg='🔥 '+msg+' Fontes respondendo: '+((d&&d.radar_sources_ok)||0)+'.';
  document.getElementById('radarStatus').textContent=msg;
  document.getElementById('oppList').innerHTML=`<div class="table-head"><div>#</div><div>SCORE</div><div>TÍTULO / ASSUNTO</div><div>TIPO</div><div>MATÉRIAS</div><div>CONFIANÇA</div><div>RELEVÂNCIA</div><div>AÇÃO</div></div>`+opportunities.map((o,idx)=>{let s=Number(o.score||0);let cls=s>=75?'':(s>=60?'mid':'low');let typ=String(o.content_type||'CURIOSIDADE').toUpperCase();let typcls=typ==='RUMOR'?'rumor':(typ==='CURIOSIDADE'?'cur':'');let rel=String(o.priority||'MÉDIA').toUpperCase();let relcls=rel==='ALTA'?'high':(rel==='BAIXA'?'low':'');let conf=Math.max(0,Math.min(100,Number(o.confidence||0)));let mats=Number(o.mentions||1);let status=String(o.status||'PRODUZIR').toUpperCase();let action=status==='OBSERVAR'?'OBSERVAR':'PRODUZIR';return `<div class="row"><div class="rank">${idx+1}</div><div><div class="scorebox ${cls}">${s}</div></div><div><div class="title">${esc(o.title)}</div><div class="tags"><span class="tag">${esc(o.source||'Fonte')}</span><span class="tag">${mats} matéria${mats===1?'':'s'}</span>${o.radar?'<span class="tag">RADAR</span>':''}</div></div><div class="type ${typcls}">${esc(typ)}</div><div class="conf">${mats}</div><div><div class="conf">${conf}%</div><div class="confbar"><i style="width:${conf}%"></i></div></div><div class="relevance ${relcls}">${esc(rel)}</div><button class="produce ${action==='OBSERVAR'?'observe':''}" onclick="createShort('${o.id}')">${action}</button></div>`}).join('');
  const ep=d&&d.editor_pick;
  if(ep){
    const decision=String(ep.editorial_decision||'PRODUZIR');
    const cls=decision==='PRODUZIR AGORA'?'now':(decision==='OBSERVAR'?'obs':'');
    let epType=String(ep.content_type||'CURIOSIDADE').toUpperCase();let epMats=Number(ep.mentions||1);let epSources=Number(ep.source_count||1);let epConf=Math.max(0,Math.min(100,Number(ep.confidence||0)));let epScore=Number(ep.score||0);let epEd=Number(ep.editorial_score||0);let decisionClass=decision==='OBSERVAR'?'obs':'';let icon=epType==='RUMOR'?'⚠️':(epType==='NOTÍCIA'?'📰':'🔎');document.getElementById('editorPick').innerHTML=`<div class="editor-shell"><div class="editor-head"><div class="editor-brand"><div class="editor-icon">🧠</div><div><h2>EDITOR-CHEFE</h2><p>Analisa o Radar, escolhe a melhor pauta e prepara a produção.</p></div></div><div class="editor-actions"><div class="editor-status">✓ PAUTA SELECIONADA</div></div></div><div class="editor-grid-main"><div class="editor-cover"><div class="editor-cover-icon">${icon}</div></div><div class="editor-content"><span class="editor-tag">${esc(epType)}</span><div class="editor-title">${esc(ep.title)}</div><div class="editor-metrics"><div class="editor-metric"><small>SCORE RADAR</small><b class="metric-green">${epScore}/100</b></div><div class="editor-metric"><small>SCORE EDITORIAL</small><b class="metric-purple">${epEd}/100</b></div><div class="editor-metric"><small>CONFIANÇA</small><b>${epConf}%</b></div><div class="editor-metric"><small>MATÉRIAS</small><b>${epMats}</b></div><div class="editor-metric"><small>FONTES</small><b>${epSources}</b></div></div><div class="editor-copy"><div class="editor-hook"><b>⚡ HOOK DO VÍDEO</b><span>${esc(ep.editorial_hook||'')}</span></div><div class="editor-angle"><b>🎯 ÂNGULO EDITORIAL</b><span>${esc(ep.editorial_angle||'')}</span></div></div><div class="script-preview"><div class="script-head"><div><b>📝 ROTEIRO AUTOMÁTICO</b><span>V31.0 · fatos → roteiro → voz → legendas</span></div><div class="script-stats">${Number((ep.script_preview||{}).word_count||0)} palavras · ~${Number((ep.script_preview||{}).estimated_seconds||0)}s</div></div><div class="script-flow"><div><small>HOOK</small><span>${esc(((ep.script_preview||{}).sections||{}).hook||ep.editorial_hook||'')}</span></div><div><small>CONTEXTO</small><span>${esc(((ep.script_preview||{}).sections||{}).context||'')}</span></div><div><small>FATO / VERIFICAÇÃO</small><span>${esc(((ep.script_preview||{}).sections||{}).proof||'')}</span></div><div><small>PAYOFF</small><span>${esc(((ep.script_preview||{}).sections||{}).payoff||ep.editorial_angle||'')}</span></div><div><small>CTA</small><span>${esc(((ep.script_preview||{}).sections||{}).cta||'')}</span></div></div></div><div class="meta">${esc(ep.editorial_reason||'')}</div></div><div class="editor-decision ${decisionClass}"><div class="decision-check">${decision==='OBSERVAR'?'◌':'✓'}</div><div class="decision-word">${esc(decision)}</div><div class="decision-reason">${esc(ep.editorial_reason||'Pauta selecionada pelo Editor-Chefe.')}</div><button class="editor-produce" onclick="createShort('${ep.id||''}')">⚡ PRODUZIR AGORA</button></div></div></div>`;
  } else { document.getElementById('editorPick').innerHTML='Aguardando o Radar.'; }
  renderJobs((d&&d.jobs)||[]);
}
function load(){
  fetch('/api/state?ts='+Date.now(),{cache:'no-store'})
    .then(function(r){ if(!r.ok) throw new Error('API /api/state retornou '+r.status); return r.json(); })
    .then(function(d){ drawState(d); })
    .catch(function(){ document.getElementById('radarStatus').textContent='⚠️ Não foi possível consultar o servidor agora. Recarregando automaticamente…'; });
}
function renderJobs(js){if(!js.length){document.getElementById('jobs').textContent='Nenhuma produção iniciada.';return}js=js.slice().reverse();document.getElementById('jobs').innerHTML=js.map(j=>{let p=Math.round(j.progress||0);return `<div class="job"><div class="jobhead"><b>${esc(j.title)}</b><span>${esc(j.status)}</span></div><div class="muted">${esc(j.stage)} — ${p}%</div><div class="bar"><i style="width:${p}%"></i></div><div class="log">${esc(j.log||'')}</div>${j.score?`<div class="meta">Avaliação: ${j.score}/100</div>`:''}${j.video?`<div class="result"><a href="/output/${encodeURIComponent(j.video)}" target="_blank">▶ ABRIR SHORT</a><a href="/output/${encodeURIComponent(j.cover||'')}" target="_blank">🖼️ CAPA</a><a href="/api/job/${j.id}" target="_blank">JSON</a></div>`:''}</div>`}).join('');for(let i=0;i<8;i++)document.getElementById('step-'+i).classList.toggle('active',js[0]&&i===stageIndex(js[0].stage))}
async function createShort(id){
  try{
    let topic=document.getElementById('topic').value;
    let r=await fetch('/api/produce',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:id||null,topic})});
    let d=await r.json();
    if(!r.ok){alert(d.error||'Erro ao iniciar produção');return}
    document.getElementById('topic').value='';
    load();
  }catch(e){alert('Não foi possível iniciar a produção. Verifique se o servidor terminou de iniciar e tente novamente.')}
}
async function research(){try{let r=await fetch('/api/research',{method:'POST'});let d=await r.json();if(!r.ok||d.error){alert(d.error||'Falha no radar');return}drawState(d);alert('Radar atualizado: '+(d.opportunities||[]).length+' oportunidades encontradas.')}catch(e){alert('Não foi possível atualizar o radar agora. O fallback continua disponível.')}}
load();setInterval(load,3000);
</script></body></html>'''
PAGE = PAGE.replace('__OPPORTUNITIES__', ''.join(f'<div class="row"><div class="score">{o["score"]}</div><div><div class="title">{o["title"]}</div><div class="source">{o["source"]} · {o.get("content_type","CURIOSIDADE")} · confiança {o.get("confidence","-")} % · {o.get("reason","")}</div></div><div class="pill">{o["priority"]}</div><div class="pill">{o.get("status","PRODUZIR")}</div><button class="produce" onclick="createShort(\'{o["id"]}\')">PRODUZIR</button></div>' for o in FALLBACK_TOPICS))

def now_iso(): return datetime.now(timezone.utc).isoformat()

def load_jobs():
    if not STATE_FILE.exists(): return {}
    try: return json.loads(STATE_FILE.read_text(encoding='utf-8'))
    except Exception: return {}

def _atomic_write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f'{path.name}.{uuid.uuid4().hex}.tmp')
    try:
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        os.replace(tmp, path)
    finally:
        try:
            if tmp.exists(): tmp.unlink()
        except Exception:
            pass

def save_jobs(jobs):
    _atomic_write_json(STATE_FILE, jobs)

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

def _load_radar():
    with RADAR_LOCK:
        if not RADAR_FILE.exists(): return {'updated_at':None,'opportunities':[]}
        try:
            d=json.loads(RADAR_FILE.read_text(encoding='utf-8'))
            if isinstance(d,dict): return d
        except Exception: pass
        return {'updated_at':None,'opportunities':[]}


def _save_radar(opportunities, updated_at=None, status='OK', error=None, sources_ok=0):
    data={'updated_at':updated_at or now_iso(),'opportunities':opportunities[:12], 'status':status, 'error':error, 'sources_ok':sources_ok}
    with RADAR_LOCK:
        _atomic_write_json(RADAR_FILE, data)
    return data


def _source_name_from_link(link, fallback='Fonte'):
    try:
        host=urlparse(link).netloc.lower().replace('www.','')
        return host.split('.')[0].replace('-',' ').title() or fallback
    except Exception:
        return fallback


def _parse_rss(url, feed_name):
    items=[]
    try:
        r=fetch(url,timeout=18); r.raise_for_status()
        root=ET.fromstring(r.content)
        for item in root.findall('.//item')[:12]:
            title=(item.findtext('title') or '').strip()
            link=(item.findtext('link') or '').strip()
            pub=(item.findtext('pubDate') or '').strip()
            desc=(item.findtext('description') or '').strip()
            # ElementTree considera alguns elementos sem filhos como False; por isso
            # não usamos "a or b" aqui, senão o <source> real do Google News pode ser perdido.
            source_el=item.find('source')
            if source_el is None:
                source_el=item.find('{http://search.yahoo.com/mrss/}source')
            source=(source_el.text or '').strip() if source_el is not None else ''
            if title and link:
                items.append({'title':BeautifulSoup(title,'html.parser').get_text(' ',strip=True),'url':link,'published':pub,'source':source or _source_name_from_link(link,feed_name),'feed':feed_name,'description':BeautifulSoup(desc,'html.parser').get_text(' ',strip=True)[:500]})
    except Exception:
        pass
    return items


def _parse_pubdate(s):
    if not s: return None
    from email.utils import parsedate_to_datetime
    try: return parsedate_to_datetime(s).astimezone(timezone.utc)
    except Exception: return None


def _normalize_topic_text(text):
    text=(text or '').lower()
    text=BeautifulSoup(text,'html.parser').get_text(' ',strip=True)
    text=re.sub(r'https?://\S+',' ',text)
    # Remove generic editorial words so the clustering compares the actual subject.
    stop={
        'gta','gta6','vi','grand','theft','auto','rockstar','games','game',
        'confirma','confirmou','confirm','revela','revelou','revel','anuncia','anunciou','anuncia',
        'novo','nova','novas','novos','detalhes','detalhe','segundo','sobre',
        'pode','ser','será','sera','vai','agora','ainda','já','ja','que','para','com','como',
        'de','da','do','das','dos','em','no','na','nos','nas','e','ou','um','uma',
        'os','as','o','a','por','mais','se','ao','aos','é','the','of','and','to','this','that',
        'afirma','afirmam','explica','explicou','revela','revelou','mostra','mostrou','sobre'
    }
    words=[]
    for w in re.findall(r'[a-z0-9à-ÿ]{3,}',text):
        if w not in stop and not w.isdigit(): words.append(w)
    return words


def _topic_concepts(text):
    """Extrai conceitos editoriais fortes para agrupar manchetes diferentes sobre a mesma pauta."""
    t=(text or '').lower()
    concepts=[]
    aliases={
        'cloud-gaming': ('cloud gaming','xbox cloud','streaming','jogar na nuvem','jogos na nuvem'),
        'moral-relacionamentos': ('sistema de moral','sistema de relacionamento','relacionamento','moral','amizade','romance'),
        'discord-parceria': ('discord','parceria com discord'),
        '35-novidades': ('35 novidades','35 novos','35 recursos','35 detalhes'),
        'mapa-tamanho': ('tamanho do mapa','mapa de gta 6','mapa gta 6','maior que'),
        'jason-lucia': ('jason','lucia'),
        'vice-city': ('vice city','miami'),
        'leonida': ('leonida',),
        'trailer': ('trailer','extended look','teaser'),
        'pre-venda': ('pré-venda','pre-venda','pre order','pre-order','preorder'),
        'album': ('álbum','album','trilha sonora','soundtrack'),
        'lancamento': ('lançamento','release date','data de lançamento','novembro 19','19 de novembro'),
        'vazamento': ('vazamento','vazou','leak','leaked'),
        'pc': ('pc','computador'),
        'xbox': ('xbox',),
        'ps5': ('ps5','playstation 5','playstation'),
        'gameplay-realismo': ('realismo na gameplay','realismo','gameplay','jogabilidade'),
    }
    for name, terms in aliases.items():
        if any(term in t for term in terms): concepts.append(name)
    return concepts


def _topic_signature(text):
    """Assinatura compacta usada para deduplicação e agrupamento editorial."""
    words=set(_normalize_topic_text(text))
    concepts=set(_topic_concepts(text))
    # Conceitos fortes têm prioridade; palavras relevantes complementam a assinatura.
    return concepts, words


def _topic_similarity(a,b):
    ca,wa=_topic_signature(a)
    cb,wb=_topic_signature(b)
    if ca and cb:
        inter=len(ca & cb)
        union=max(1,len(ca | cb))
        concept_sim=inter/union
        if concept_sim >= 0.5: return max(0.72,concept_sim)
        # A mesma entidade forte (ex.: cloud-gaming) já é uma pista relevante.
        if ca & cb: return 0.58
    if not wa or not wb: return 0.0
    return len(wa & wb)/max(1,len(wa | wb))


def _classify_content(title):
    t=(title or '').lower()
    if any(k in t for k in ('rumor','rumour','vazamento','vazou','leak','suposto','suposta','não confirmado','nao confirmado')):
        return 'RUMOR'
    if any(k in t for k in ('mistério','misterio','segredo','teoria','pista','easter egg','detalhe escondido')):
        return 'MISTÉRIO'
    if any(k in t for k in ('confirm','revel','anunci','pré-venda','pre-order','album','álbum','lançamento','release','adiado','data')):
        return 'NOTÍCIA'
    return 'CURIOSIDADE'


def _source_trust(source):
    s=(source or '').lower()
    high=('rockstar','take-two','take two','the verge','ign','gamesradar','eurogamer','polygon','pc gamer','axios','guardian','uol','omelete','tecmundo','rolling stone')
    medium=('adrenaline','olhar digital','tudocelular','canaltech','terra','g1','forbes','gamevicio','meups','flow games')
    if any(x in s for x in high): return 14
    if any(x in s for x in medium): return 10
    return 6


def _clickbait_penalty(title):
    t=(title or '').lower()
    penalty=0
    if t.count('!')>=2: penalty+=3
    if t.count('?')>=2: penalty+=2
    if any(k in t for k in ('chocante','inacreditável','incrível','absurdo','ninguém esperava','vai mudar tudo','você não vai acreditar','bombou','surpreende')): penalty+=4
    if any(k in t for k in ('afirma','acredita','pode ser','seria','talvez','suposto')): penalty+=1
    return min(8,penalty)


def _radar_score(item, duplicate_count=1, source_count=1, concept_count=1):
    title=item.get('title','')
    dt=_parse_pubdate(item.get('published',''))
    age_hours=999
    if dt:
        age_hours=max(0,(datetime.now(timezone.utc)-dt).total_seconds()/3600)
    recency=34 if age_hours<=12 else 30 if age_hours<=24 else 26 if age_hours<=48 else 20 if age_hours<=96 else 12 if age_hours<=168 else 5
    title_low=title.lower()
    keyword_bonus=sum(v for k,v in RADAR_KEYWORDS.items() if k in title_low)
    trust=_source_trust(item.get('source',''))
    mentions=min(12,max(0,(duplicate_count-1)*3))
    diversity=min(12,max(0,(source_count-1)*5))
    concept_bonus=min(6,max(0,(concept_count-1)*2))
    content_bonus=5 if _classify_content(title) in ('NOTÍCIA','MISTÉRIO') else 3
    penalty=_clickbait_penalty(title)
    raw=recency+min(20,keyword_bonus)+trust+mentions+diversity+concept_bonus+content_bonus-penalty
    return int(min(99,max(35,raw)))


def _make_radar_title(headline):
    h=re.sub(r'\s+',' ',headline).strip(' -–—')
    return h if len(h)<=115 else h[:112].rsplit(' ',1)[0]+'…'


def _merge_radar_candidates(items):
    """Agrupa notícias da mesma pauta mesmo quando as manchetes usam palavras diferentes."""
    groups=[]
    for item in items:
        placed=False
        for group in groups:
            similarities=[_topic_similarity(item.get('title',''), x.get('title','')) for x in group]
            best_similarity=max(similarities) if similarities else 0
            if best_similarity >= 0.55:
                group.append(item); placed=True; break
        if not placed: groups.append([item])
    return groups


def _dedupe_group(group):
    """Remove a mesma matéria repetida pelo RSS sem perder fontes independentes."""
    out=[]; seen=set()
    for item in group:
        key=(str(item.get('url','')).split('?')[0].rstrip('/').lower() or re.sub(r'\W+',' ',item.get('title','').lower()).strip())
        if key in seen: continue
        seen.add(key); out.append(item)
    return out


def _canonical_source_name(name, url=''):
    """Normaliza a identificação da fonte para contar fontes independentes corretamente."""
    raw=re.sub(r'\s+',' ',str(name or '').strip())
    if raw and raw.lower() not in ('google news','google'):
        return raw
    return _source_name_from_link(url, 'Fonte')


def radar_scan():
    """Radar V26.3: coleta, agrupa e só substitui o último radar quando a coleta realmente teve sucesso."""
    raw=[]; successful_sources=0; errors=[]
    for name,url in RADAR_FEEDS:
        try:
            batch=_parse_rss(url,name)
            if batch:
                successful_sources += 1
                raw.extend(batch)
            else:
                errors.append(name+' sem resultados')
        except Exception as e:
            errors.append(name+': '+str(e)[:120])
    rockstar_ok=False
    try:
        r=fetch('https://www.rockstargames.com/br/newswire',timeout=20); r.raise_for_status()
        rockstar_ok=True; successful_sources += 1
        soup=BeautifulSoup(r.text,'html.parser')
        for a in soup.find_all('a',href=True):
            t=' '.join(a.stripped_strings).strip()
            href=urljoin('https://www.rockstargames.com/br/newswire',a['href'])
            if t and any(k in t.lower() for k in ('grand theft auto vi','gta vi','gta 6')):
                raw.append({'title':t,'url':href,'published':'','source':'Rockstar Games','feed':'Rockstar Newswire','description':''})
    except Exception as e:
        errors.append('Rockstar Newswire: '+str(e)[:160])

    # Se nenhuma fonte respondeu, preserva o último radar válido. Nunca sobrescreva com fallback.
    if successful_sources == 0 or not raw:
        last=_load_radar()
        if last.get('opportunities'):
            last['status']='STALE'
            last['error']='Nenhuma fonte respondeu. Mantendo a última varredura válida.'
            last['sources_ok']=0
            return last
        fallback=[dict(x,radar=False,status='AGUARDAR',confidence=70,reason='Aguardando primeira varredura real') for x in FALLBACK_TOPICS]
        return {'updated_at':None,'opportunities':fallback,'status':'WAITING','error':'Nenhuma fonte respondeu na primeira varredura.','sources_ok':0}

    allowed=('gta 6','gta vi','grand theft auto vi','rockstar games','rockstar','vice city','leonida','jason','lucia')
    filtered=[]; seen_urls=set()
    for x in raw:
        title=x.get('title','').strip(); url=x.get('url','').strip()
        if not title: continue
        url_key=url.split('?')[0].rstrip('/').lower()
        if url_key and url_key in seen_urls: continue
        if any(k in title.lower() for k in allowed):
            filtered.append(x)
            if url_key: seen_urls.add(url_key)

    groups=[_dedupe_group(g) for g in _merge_radar_candidates(filtered)]
    ranked=[]
    for group in groups:
        if not group: continue
        source_names={_canonical_source_name(x.get('source',''), x.get('url','')).strip().lower()
                      for x in group if x.get('source') or x.get('url')}
        concepts=set()
        for x in group: concepts.update(_topic_concepts(x.get('title','')))
        # Prefere a fonte mais confiável e a manchete mais recente dentro da pauta.
        best=max(group,key=lambda x:_radar_score(x,len(group),len(source_names),len(concepts)))
        score=_radar_score(best,len(group),len(source_names),len(concepts))
        typ=_classify_content(best.get('title',''))
        independent=max(0,len(source_names)-1)
        confidence=min(99,48 + min(24,(len(group)-1)*6) + min(20,independent*10) + (10 if best.get('source')=='Rockstar Games' else 0))
        if typ=='RUMOR': confidence=max(25,confidence-18)
        if best.get('source')=='Rockstar Games': confidence=max(confidence,85)

        # Assuntos com uma única fonte e linguagem especulativa ficam em observação.
        speculative=any(k in best.get('title','').lower() for k in ('acredita','pode ser','poderá','seria','talvez','suposto','vazamento','rumor'))
        if speculative and len(source_names)<2: confidence=min(confidence,62)
        status='PRODUZIR' if score>=68 and confidence>=55 else 'OBSERVAR'
        if score>=82 and confidence>=70: status='PRODUZIR AGORA'
        if speculative and len(source_names)<2: status='OBSERVAR'

        reason=[]
        if len(group)>=2: reason.append(f'{len(group)} matérias')
        if len(source_names)>=2: reason.append(f'{len(source_names)} fontes')
        if independent>=1: reason.append('confirmação cruzada')
        if _parse_pubdate(best.get('published','')) and score>=68: reason.append('recente')
        if best.get('source')=='Rockstar Games': reason.append('fonte oficial')
        if typ=='RUMOR': reason.append('tratar como rumor')
        if speculative and len(source_names)<2: reason.append('não confirmado')

        ranked.append({
            'id':'radar-'+uuid.uuid4().hex[:8],
            'score':score,
            'priority':'ALTA' if score>=82 else 'MÉDIA' if score>=65 else 'BAIXA',
            'status':status,
            'title':_make_radar_title(best['title']),
            'source':_canonical_source_name(best.get('source',''), best.get('url','')),
            'url':best['url'],
            'published':best.get('published',''),
            'mentions':len(group),
            'source_count':len(source_names),
            'confidence':confidence,
            'content_type':typ,
            'reason':', '.join(reason) or 'relevância editorial',
            'concepts':sorted(concepts)[:8],
            'description':best.get('description',''),
            'radar':True
        })

    ranked.sort(key=lambda x:(x['score'],x.get('confidence',0),x.get('source_count',0),x.get('mentions',1)),reverse=True)
    if not ranked:
        last=_load_radar()
        if last.get('opportunities'):
            last['status']='STALE'
            last['error']='A coleta respondeu, mas não encontrou pautas GTA VI suficientes.'
            return last
        fallback=[dict(x,radar=False,status='AGUARDAR',confidence=70,reason='Aguardando primeira varredura real') for x in FALLBACK_TOPICS]
        return {'updated_at':None,'opportunities':fallback,'status':'WAITING','error':'Coleta sem pautas utilizáveis.','sources_ok':successful_sources}

    # Não misturamos fallback com o radar real. Se o radar encontrou 4, mostramos 4.
    # Isso evita que assuntos antigos pareçam notícias atuais.
    return _save_radar(ranked[:10], status='OK', sources_ok=successful_sources)

def current_opportunities():
    d=_load_radar(); ops=d.get('opportunities') or []
    if ops:
        return ops, d.get('updated_at'), d.get('status','OK'), d.get('error'), d.get('sources_ok',0)
    fallback=[dict(x,radar=False,status='AGUARDAR',confidence=70,reason='Aguardando primeira varredura real') for x in FALLBACK_TOPICS]
    return fallback, None, 'WAITING', 'Radar ainda não realizou uma varredura válida.', 0


def research_official():
    """Pesquisa o radar e coleta os visuais oficiais usados pelo editor."""
    radar=radar_scan(); topics=radar.get('opportunities') or FALLBACK_TOPICS
    facts=[]; images=[]
    for url in [ROCKSTAR_VI,ROCKSTAR_NEWS]:
        try:
            r=fetch(url); r.raise_for_status(); soup=BeautifulSoup(r.text,'html.parser')
            facts.append(' '.join(soup.stripped_strings)[:12000])
            for tag in soup.find_all(['meta','img']):
                u=tag.get('content') if tag.name=='meta' else tag.get('src')
                if u and (tag.get('property')=='og:image' or tag.name=='img'): images.append(urljoin(url,u))
        except Exception: pass
    try:
        r=fetch('https://www.rockstargames.com/VI/downloads/videos'); r.raise_for_status()
        soup=BeautifulSoup(r.text,'html.parser')
        for tag in soup.find_all(['meta','img']):
            u=tag.get('content') if tag.name=='meta' else tag.get('src')
            if u and (tag.get('property')=='og:image' or tag.name=='img'): images.append(urljoin('https://www.rockstargames.com/VI/downloads/videos',u))
    except Exception: pass
    return topics,images,' '.join(facts)


def choose_topic(data,topics):
    if data.get('id'):
        for o in topics:
            if o.get('id')==data['id']: return o
    custom=(data.get('topic') or '').strip()
    if custom: return {'id':'custom','score':88,'priority':'ALTA','title':custom,'source':'Pesquisa editorial','url':ROCKSTAR_VI,'radar':False}
    return max(topics,key=lambda x:x.get('score',0))


def _strip_publisher_suffix(text):
    """Remove publisher/domain suffixes from a headline before narration."""
    t=re.sub(r'\s+',' ',str(text or '').strip()).strip(' -–—')
    patterns=[
        r'\s*[-–—|]\s*(?:TudoCelular(?:\.com)?|Canaltech|IGN\s*Brasil|Olhar\s+Digital|Adrenaline|Exame|UOL|TecMundo|Combo\s+Infinito|Rolling\s+Stone(?:\s+Brasil)?|Omelete)(?:\.com(?:\.br)?)?\s*$',
        r'\s*[-–—|]\s*[^\s]+\.(?:com\.br|com|net|org)(?:\s*)$',
    ]
    for pat in patterns:
        t=re.sub(pat,'',t,flags=re.I).strip(' -–—')
    return t


def _source_evidence(topic):
    """V31: reúne somente evidências da própria pauta e, quando possível, do artigo."""
    title=_strip_publisher_suffix(topic.get('title',''))
    desc=re.sub(r'\s+',' ',str(topic.get('description','') or '').strip())
    source=re.sub(r'\s+',' ',str(topic.get('source','') or '').strip())
    url=str(topic.get('url') or '').strip()
    if desc:
        desc=re.sub(r'^\s*(?:[^|]{0,180}\|\s*)','',desc).strip()
        desc=_strip_publisher_suffix(desc)
        if desc.lower()==title.lower(): desc=''
    return title,desc,source,url


def _clean_article_text(text):
    """Remove ruído de páginas e preserva frases factuais curtas para o roteiro."""
    text=BeautifulSoup(str(text or ''),'html.parser').get_text(' ', strip=True)
    text=re.sub(r'https?://\S+',' ',text)
    text=re.sub(r'\s+',' ',text).strip()
    noise=re.compile(r'^(?:publicidade|menu|início|home|leia também|compartilhe|siga-nos|newsletter|cookies?)$',re.I)
    parts=[x.strip(' -–—') for x in re.split(r'(?<=[.!?])\s+',text) if len(x.strip())>=35]
    out=[]
    for x in parts:
        if noise.match(x): continue
        x=_strip_publisher_suffix(x)
        if x and x not in out: out.append(x)
    return out


def _decode_google_news_direct(source_url, diagnostics=None):
    """V40: direct Google News decoder with explicit diagnostics."""
    def note(step, detail):
        if diagnostics is not None:
            diagnostics.append(f"{step}: {detail}")

    try:
        u=urlparse(str(source_url or '').strip())
        if 'news.google.com' not in u.netloc.lower():
            note('INPUT', 'not_google_news')
            return ''
        parts=[p for p in u.path.split('/') if p]
        if not parts:
            note('INPUT', 'empty_path')
            return ''
        data_id=parts[-1]
        if not data_id:
            note('INPUT', 'missing_article_id')
            return ''
        note('INPUT', f'google_news_article_id={data_id[:18]}...')

        # Current implementations locate the signature node by data-n-a-id,
        # then send its data-n-a-sg/data-n-a-ts to Fbv4je.
        page_candidates=[
            f'https://news.google.com/articles/{data_id}',
            f'https://news.google.com/rss/articles/{data_id}',
            str(source_url),
        ]

        html=''
        status_codes=[]
        for page_url in page_candidates:
            try:
                r=fetch(page_url, timeout=18)
                status_codes.append(str(getattr(r,'status_code','?')))
                if getattr(r,'ok',False) and getattr(r,'text',''):
                    html=r.text
                    note('GOOGLE_PAGE', f'ok status={getattr(r,"status_code","?")} url={page_url.split("?")[0]}')
                    break
            except Exception as e:
                note('GOOGLE_PAGE', f'exception={type(e).__name__}')

        if not html:
            note('GOOGLE_PAGE', 'FAILED status_chain=' + ','.join(status_codes))
            return ''

        soup=BeautifulSoup(html,'html.parser')
        node=soup.select_one(f'div[data-n-a-id="{data_id}"]')
        if node is None:
            node=soup.select_one('div[data-n-a-id][data-n-a-sg][data-n-a-ts]')
        if node is None:
            node=soup.select_one('[data-n-a-sg][data-n-a-ts]')

        if node is None:
            note('SIGNATURE', 'NOT_FOUND')
            return ''

        signature=str(node.get('data-n-a-sg') or '').strip()
        timestamp=str(node.get('data-n-a-ts') or '').strip()
        found_id=str(node.get('data-n-a-id') or '').strip()
        note('SIGNATURE', f"found ts={bool(timestamp)} sg={bool(signature)} id_match={found_id==data_id or not found_id}")

        if not signature or not timestamp:
            note('SIGNATURE', 'INCOMPLETE')
            return ''

        payload = [
            "Fbv4je",
            f'["garturlreq",[["X","X",["X","X"],null,null,1,1,"US:en",null,1,null,null,null,null,null,0,1],"X","X",1,[1,1,1],1,1,null,0,0,null,0],"{data_id}",{timestamp},"{signature}"]'
        ]
        data = "f.req=" + quote(json.dumps([[payload]], ensure_ascii=False, separators=(',',':')))

        headers={
            "Content-Type":"application/x-www-form-urlencoded;charset=UTF-8",
            "Referer":"https://news.google.com/",
            "User-Agent":UA,
        }

        try:
            rr=requests.post(
                "https://news.google.com/_/DotsSplashUi/data/batchexecute?rpcids=Fbv4je",
                headers=headers,
                data=data,
                timeout=20,
            )
        except Exception as e:
            note('BATCHEXECUTE', f'exception={type(e).__name__}:{e}')
            return ''

        note('BATCHEXECUTE', f'status={getattr(rr,"status_code","?")} bytes={len(getattr(rr,"text","") or "")}')
        body=getattr(rr,'text','') or ''
        if not rr.ok:
            note('BATCHEXECUTE', 'HTTP_ERROR')
            return ''

        header='[\\"garturlres\\",\\"'
        footer='\\",'
        if header not in body:
            note('GARTURLRES', 'HEADER_NOT_FOUND')
            # Do not expose Google's full response in the UI/log.
            sample=re.sub(r'\s+',' ',body[:300])
            note('GARTURLRES', 'response_prefix=' + sample[:180])
            return ''

        tail=body.split(header,1)[1]
        if footer not in tail:
            note('GARTURLRES', 'FOOTER_NOT_FOUND')
            return ''

        decoded=tail.split(footer,1)[0]
        decoded=decoded.replace('\\u003d','=').replace('\\u0026','&').replace('\\/','/')
        decoded=decoded.replace('\\u0025','%')
        if decoded.startswith(('http://','https://')) and not _is_google_news_url(decoded):
            note('DECODED_URL', decoded[:180])
            return decoded

        note('DECODED_URL', 'INVALID_OR_STILL_GOOGLE')
        return ''
    except Exception as e:
        note('DECODER', f'exception={type(e).__name__}:{e}')
        return ''



def _resolve_article_url(url, title='', source_name=''):
    """V40: resolve Google News links with independent fallbacks."""
    url=str(url or '').strip()
    title=str(title or '').strip()
    source_name=str(source_name or '').strip()
    if not url:
        return ''
    if not _is_google_news_url(url):
        return url

    # 1) Direct Google batchexecute decoder with diagnostics.
    global _gnewsdecoder, _last_gnews_diagnostics
    diagnostics=[]
    decoded=_decode_google_news_direct(url, diagnostics)
    _last_gnews_diagnostics = diagnostics[-8:]
    if decoded and not _is_google_news_url(decoded):
        return decoded

    # 2) Maintained Python decoder.
    if _gnewsdecoder is not None:
        for wait in (0.5, 1.0):
            try:
                result=_gnewsdecoder(url, interval=wait, timeout=15)
                if isinstance(result, dict):
                    decoded=str(result.get('decoded_url') or result.get('url') or '').strip()
                    ok=bool(result.get('success') or result.get('status'))
                    if ok and decoded and not _is_google_news_url(decoded):
                        return decoded
            except Exception:
                continue

    # 3) Normal HTTP redirect.
    try:
        r=fetch(url, timeout=15)
        final=str(getattr(r, 'url', '') or '').strip()
        if final and not _is_google_news_url(final):
            return final
    except Exception:
        pass

    # 4) Publisher-constrained search fallback.
    try:
        query=title
        if source_name:
            query += ' ' + source_name
        if query:
            qurl='https://html.duckduckgo.com/html/?q=' + quote_plus(query)
            rr=fetch(qurl, timeout=15)
            if rr.ok:
                soup=BeautifulSoup(rr.text,'html.parser')
                sn=re.sub(r'[^a-z0-9]+','',source_name.lower())
                aliases={
                    'ignbrasil': ('ign.com','br.ign.com'),
                    'ign': ('ign.com','br.ign.com'),
                    'theverge': ('theverge.com',),
                    'rockstarnewswire': ('rockstargames.com',),
                }
                allowed=aliases.get(sn, ())
                for a in soup.select('a.result__a, a[href]'):
                    href=str(a.get('href') or '').strip()
                    try:
                        qs=parse_qs(urlparse(href).query)
                        if qs.get('uddg'):
                            href=qs['uddg'][0]
                    except Exception:
                        pass
                    if not href.startswith(('http://','https://')) or _is_google_news_url(href):
                        continue
                    host=urlparse(href).netloc.lower().replace('www.','')
                    if allowed and not any(host==d or host.endswith('.'+d) for d in allowed):
                        continue
                    return href
    except Exception:
        pass

    # Keep a compact diagnostic trail for the UI/log.
    _last_gnews_diagnostics = diagnostics[-8:]
    return url

def _is_google_news_url(url):
    try:
        return 'news.google.com' in urlparse(str(url or '')).netloc.lower()
    except Exception:
        return False


def _extract_article_body_from_html(html):
    """Extract a real article body without accepting meta descriptions or generic <main>."""
    soup=BeautifulSoup(html or '', 'html.parser')

    # 1) JSON-LD articleBody.
    structured=[]
    for tag in soup.find_all('script',type='application/ld+json')[:40]:
        try:
            raw=tag.string or tag.get_text() or '{}'
            obj=json.loads(raw)
            stack=obj if isinstance(obj,list) else [obj]
            seen=set()
            while stack:
                item=stack.pop(0)
                if not isinstance(item,dict): continue
                oid=id(item)
                if oid in seen: continue
                seen.add(oid)
                graph=item.get('@graph')
                if isinstance(graph,list): stack.extend(graph)
                body=item.get('articleBody')
                typ=str(item.get('@type') or '').lower()
                if isinstance(body,str) and len(body.strip())>=180 and ('article' in typ or 'newsarticle' in typ or not typ):
                    structured.append(body)
        except Exception:
            continue
    if structured:
        body=max(structured,key=len)
        lines=_clean_article_text(body)
        if len(lines)>=2:
            return lines[:24], 'JSONLD_ARTICLE_BODY'

    # 2) Explicit article-body containers only.
    containers=[]
    selectors=(
        'article', '[itemprop="articleBody"]', '[data-testid="article-body"]',
        '[data-testid="articleBody"]', '.article-body', '.article__body',
        '.article-content', '.article-content-body', '.post-content', '.entry-content',
        '.story-body', '.story-content', '.articleBody', '.articleBodyText',
        '.td-post-content', '.tdb_single_content', '.td-post-content-wrap',
        '.jeg_inner_content', '.single-post-content', '.single-content',
        '.content-inner', '.post-single-content', '.post-entry',
        '[class*=\"article-body\"]', '[class*=\"article-content\"]'
    )
    for sel in selectors:
        for node in soup.select(sel)[:5]:
            paras=[]
            for ptag in node.find_all('p'):
                txt=ptag.get_text(' ',strip=True)
                if len(txt)<45: continue
                low=txt.lower()
                if any(b in low for b in ('leia também','publicidade','assine','newsletter','cookies','siga-nos','compartilhe')):
                    continue
                paras.append(txt)
            if len(paras)>=2:
                containers.append(paras)
    if containers:
        paras=max(containers,key=len)
        lines=_clean_article_text(' '.join(paras))
        if len(lines)>=2:
            return lines[:24], 'ARTICLE_CONTAINER'
    return [], 'BLOCKED_NO_ARTICLE_BODY'


def _resolver_memory_load():
    """Persistent bounded memory for the source resolver.

    It remembers which discovery strategies/domains actually produced a valid
    article body. It never stores article bodies, only small strategy counters.
    """
    with RESOLVER_LOCK:
        if not RESOLVER_MEMORY_FILE.exists():
            return {'version':'V42.2','domains':{},'strategies':{},'updated_at':now_iso()}
        try:
            d=json.loads(RESOLVER_MEMORY_FILE.read_text(encoding='utf-8'))
            if not isinstance(d,dict): raise ValueError('resolver memory inválida')
            d.setdefault('version','V41.3'); d.setdefault('domains',{}); d.setdefault('strategies',{})
            return d
        except Exception:
            return {'version':'V42.2','domains':{},'strategies':{},'updated_at':now_iso()}


def _resolver_memory_save(d):
    d['updated_at']=now_iso()
    with RESOLVER_LOCK:
        _atomic_write_json(RESOLVER_MEMORY_FILE,d)


def _resolver_learn(domain='', strategy='', success=False):
    try:
        d=_resolver_memory_load()
        if domain:
            x=d['domains'].setdefault(domain,{'tries':0,'success':0,'last_success':'','last_strategy':''})
            x['tries']=int(x.get('tries',0))+1
            if success:
                x['success']=int(x.get('success',0))+1
                x['last_success']=now_iso()
                x['last_strategy']=strategy
        if strategy:
            x=d['strategies'].setdefault(strategy,{'tries':0,'success':0,'last_success':''})
            x['tries']=int(x.get('tries',0))+1
            if success:
                x['success']=int(x.get('success',0))+1
                x['last_success']=now_iso()
        _resolver_memory_save(d)
    except Exception:
        pass


def _resolver_domain(url):
    try:
        return urlparse(str(url or '')).netloc.lower().replace('www.','')
    except Exception:
        return ''


def _resolver_tokens(text):
    text=re.sub(r'[^A-Za-zÀ-ÿ0-9 ]',' ',str(text or '').lower())
    stop={
        'sobre','relato','confirma','confirmado','confirmada','executivo','executiva',
        'afirma','afirmou','nega','negação','negaque','para','com','uma','um','que',
        'não','nao','pelo','pela','via','como','poderá','podera','jogado','ser','ter',
        'terá','tera','de','do','da','no','na','os','as','e','a','o','em','lançamento',
        'lancamento','segundo','diz','disse','sobre','novo','nova','detalhe','relato'
    }
    out=[]
    for w in re.findall(r'[A-Za-zÀ-ÿ0-9]{3,}',text):
        if w in stop or w in out: continue
        out.append(w)
    return out


def _resolver_query_variants(title, source_name=''):
    """Generate multiple semantic formulations automatically.

    The resolver is not dependent on one headline. It progressively removes
    editorial filler and creates entity/claim queries so another outlet can be
    found even when it used a completely different title.
    """
    short=_strip_publisher_suffix(title)
    toks=_resolver_tokens(short)
    key_priority=[w for w in toks if w in {
        'gta','gta6','vi','xbox','cloud','gaming','pc','microsoft','rockstar',
        'streaming','exclusividade','exclusivo','jason','lucia','leonida','vice',
        'city','trailer','lançamento','lancamento','gameplay','rumor','vazamento'
    }]
    queries=[]
    def add(q,kind):
        q=re.sub(r'\s+',' ',str(q or '').strip())
        if not q: return
        if not any(x['q'].lower()==q.lower() for x in queries): queries.append({'q':q,'kind':kind})
    add(short,'exact')
    if source_name: add(short+' '+source_name,'title-source')
    if key_priority: add(' '.join(key_priority[:8]),'entities')
    if len(toks)>=3: add(' '.join(toks[:8]),'semantic')
    # Claim-oriented variants: useful when outlets phrase the same story differently.
    if 'xbox' in toks and ('cloud' in toks or 'streaming' in toks):
        add('GTA 6 Xbox Cloud Gaming exclusividade streaming PC Microsoft','claim-xbox-cloud')
    if 'gta' in toks or 'gta6' in toks or 'vi' in toks:
        add('GTA 6 Rockstar notícia hoje','gta-news')
    return queries[:8]


# V44: biblioteca de recuperação de fontes conhecidas. É uma estratégia segura:
# URLs aqui servem SOMENTE para localizar a página; o corpo ainda passa pelo source-lock.
KNOWN_SOURCE_RECOVERY = [
    {
        'match': ('xbox', 'streaming', 'gta 6'),
        'urls': [
            'https://tecnoblog.net/noticias/microsoft-nega-exclusividade-de-gta-6-no-xbox-cloud-gaming/',
            'https://www.terra.com.br/gameon/plataformas-e-consoles/xbox-nega-que-tera-exclusividade-de-streaming-de-gta-6%2C0fea01483870bb256088d13abad8f66a1adrsr4t.html',
            'https://portaldopixel.com.br/xbox-nega-streaming-exclusivo-gta-6/',
            'https://antihype.com.br/c/games/gta-6-pc-xbox-cloud-gaming-microsoft-nega-streaming/'
        ]
    },
    {
        'match': ('detalhes', 'rockstar', 'gta 6'),
        'urls': [
            'https://www.rockstargames.com/newswire/article/4k138k8okkk483/grand-theft-auto-vi-an-extended-look-now-playing',
            'https://leonidainteractive.com/wiki/pt-br/trailers/trailer-3/',
            'https://gamenoticias.com.br/gta-6-50-novidades-incriveis-confirmadas-no-novo-jogo-da-rockstar/'
        ]
    },
    {
        'match': ('rockstar', 'gta 6'),
        'urls': [
            'https://www.rockstargames.com/newswire/article/4k138k8okkk483/grand-theft-auto-vi-an-extended-look-now-playing',
            'https://leonidainteractive.com/wiki/pt-br/trailers/trailer-3/'
        ]
    },
    {
        'match': ('gta 6',),
        'urls': [
            'https://gamenoticias.com.br/gta-6-50-novidades-incriveis-confirmadas-no-novo-jogo-da-rockstar/',
            'https://www.omelete.com.br/games/gta-6-revela-detalhes-da-historia-confira',
            'https://www.omelete.com.br/games/gta-6-gameplays-ineditos-novos'
        ]
    }
]

def _known_source_candidates(title):
    low=str(title or '').lower()
    out=[]
    for rule in KNOWN_SOURCE_RECOVERY:
        if all(term in low for term in rule['match']):
            out.extend(rule['urls'])
    return out


def _article_url_candidates_from_search(title, source_name=''):
    """V41.3 SELF-RESOLVER.

    This function is intentionally adaptive: it diagnoses discovery failures,
    changes the query formulation, changes the discovery channel, uses the
    resolver's successful-domain memory, and only gives up after bounded
    strategies have been exhausted. Search snippets/RSS descriptions are never
    used as factual evidence; they only discover URLs.
    """
    title=str(title or '').strip()
    source_name=str(source_name or '').strip()
    if not title: return []

    # V42.5: the resolver budget must exist inside this function because the
    # publisher-specific fallback below uses it before control returns to the caller.
    # V42.4 accidentally initialized it only in fetch_topic_evidence(), causing
    # NameError on the first resolver pass.
    resolver_deadline=time.monotonic()+22

    # V44 strategy 0: try previously validated direct URLs before spending time on search engines.
    # They are still subject to the same article-body and story-match gates later.
    known=_known_source_candidates(title)
    if known:
        for href in known:
            try:
                parsed=urlparse(href); host=_resolver_domain(href); path=(parsed.path or '').lower()
                if host and path and not any(tok in path for tok in ('/feed','/rss','/atom','/search','/tag/','/category/','/author/','/sitemap','/wp-json')):
                    # Reuse the normal candidate validation below by recording the URL.
                    pass
            except Exception:
                continue

    preferred=[
        # Official publisher first: known-source recovery must be allowed to reach
        # Rockstar Newswire instead of being discarded by the trusted-domain gate.
        'rockstargames.com','tecnoblog.net','omelete.com.br','exame.com','terra.com.br',
        'meups.com.br','criticalhits.com.br','games.gg','antihype.com.br',
        'portaldopixel.com.br','portaldovideogame.com.br','centralxbox.com.br',
        'gamevicio.com','purexbox.com','flowgames.gg','olhardigital.com.br',
        'tecmundo.com.br','tecnologiaarretada.com.br','jorgelar.com.br',
        'gamenoticias.com.br','playingvi.com','gta6noticias.com.br',
        'lootsecreto.com','culpadolag.com.br','teratime.com.br','gamenoticias.com.br'
    ]
    blocked={'br.ign.com','ign.com','theverge.com'}
    mem=_resolver_memory_load()
    domain_stats=mem.get('domains',{}) if isinstance(mem,dict) else {}
    # Successful domains move up, but only within the trusted allowlist.
    preferred=sorted(preferred,key=lambda d:(int(domain_stats.get(d,{}).get('success',0)), int(domain_stats.get(d,{}).get('tries',0))),reverse=True)

    found=[]; seen=set()
    def note(msg):
        try:
            global _last_gnews_diagnostics
            _last_gnews_diagnostics=(list(_last_gnews_diagnostics or [])+[str(msg)])[-24:]
        except Exception: pass

    def add(href, reason='', priority=0):
        href=str(href or '').strip()
        if not href: return
        # V42.7: never treat feeds/search/category/tag/author pages as article candidates.
        # Publisher RSS endpoints can legally return 200 but point their item link back
        # to the feed/search URL; accepting those URLs creates a resolver loop and burns
        # the entire production budget without ever reaching article-body extraction.
        try:
            parsed=urlparse(href)
            path=(parsed.path or '').lower().rstrip('/')
            query_keys={str(k).lower() for k in parse_qs(parsed.query).keys()}
            blocked_path_tokens=(
                '/feed','/rss','/atom','/search','/tag/','/category/','/author/',
                '/page/','/sitemap','/wp-json','/amp/feeds'
            )
            if any(tok in path for tok in blocked_path_tokens) or path in ('','/feed','/rss','/atom'):
                note('CANDIDATE_REJECTED_NONARTICLE:'+href[:140])
                return
            # A bare publisher homepage is never an article. Several RSS/search
            # fallbacks on cloud hosts return https://exame.com/ (HTTP 200) instead
            # of the requested story; accepting it causes repeated BLOCKED_NO_ARTICLE_BODY.
            if path in ('','/'):
                note('CANDIDATE_REJECTED_ROOT:'+href[:140])
                return
            if query_keys & {'s','search','feed','rss','output','format'}:
                note('CANDIDATE_REJECTED_QUERY:'+href[:140])
                return
        except Exception:
            pass
        try:
            qs=parse_qs(urlparse(href).query)
            for key in ('uddg','url','q'):
                if qs.get(key) and qs[key][0].startswith(('http://','https://')):
                    href=qs[key][0]; break
        except Exception: pass
        if not href.startswith(('http://','https://')) or _is_google_news_url(href): return
        host=_resolver_domain(href)
        if host in blocked: return
        trusted = any(host==d or host.endswith('.'+d) for d in preferred)
        # V48: adaptive public-source admission. A previously unseen publisher may be
        # accepted only when the URL looks like an article; the strict body extraction
        # and story-overlap gates below still decide whether it can become factual source.
        dynamic_ok = bool(re.search(r'/(?:20\d\d/|noticias?/|news/|article/|blog/|wiki/|games?/|posts?/|gta[-_]|gta6)', path, re.I))
        if not trusted and not dynamic_ok: return
        if href not in seen:
            seen.add(href)
            found.append((int(priority),href,reason))
            note('FALLBACK_CANDIDATE: '+host+' ['+reason+']')

    # Direct candidates are the highest-confidence recovery path. They are known
    # article URLs captured from validated source research and are tried before any
    # search-engine budget is spent.
    for href in _known_source_candidates(title):
        add(href,'known-source',120)
    if found:
        note('KNOWN_SOURCE_CANDIDATES:'+str(len(found)))
    elif known:
        note('KNOWN_SOURCE_REJECTED_BEFORE_FETCH:'+str(len(known)))
    else:
        note('KNOWN_SOURCE_NO_MATCH')

    def rss_candidates(query, reason, priority):
        # V42.3: bounded resolver. Never allow Google News decoding to consume the
        # entire production worker. RSS is discovery-only; inspect only the first
        # two entries and stop as soon as enough direct candidates are found.
        try:
            rss_url=('https://news.google.com/rss/search?q='+quote_plus(query)+
                     '&hl=pt-BR&gl=BR&ceid=BR:pt-419')
            rr=fetch(rss_url,timeout=8)
            note('FALLBACK_RSS:'+str(getattr(rr,'status_code','?'))+' '+reason)
            if not rr.ok: return
            root=ET.fromstring(rr.content)
            for item in root.findall('.//item')[:2]:
                link_el=item.find('link'); link=(link_el.text or '').strip() if link_el is not None else ''
                if not link: continue
                # Discovery only. One short redirect attempt is enough here; the
                # independent search-engine strategy below is the real fallback.
                decoded=''
                try:
                    ar=fetch(link,timeout=6)
                    final=str(getattr(ar,'url','') or '').strip()
                    if final and not _is_google_news_url(final): decoded=final
                except Exception as e:
                    note('RSS_REDIRECT_TIMEOUT:'+type(e).__name__)
                if decoded: add(decoded,reason,priority)
                if len(found)>=6: break
        except Exception as e:
            note('FALLBACK_RSS_ERROR:'+reason+':'+type(e).__name__+':'+str(e)[:100])

    # Strategy 1: query variants through Google News RSS.
    variants=_resolver_query_variants(title,source_name)[:4]
    for idx,item in enumerate(variants):
        rss_candidates(item['q'],item['kind'],80-idx*4)
        if len(found)>=6: break

    # Strategy 2: publisher-constrained Google News queries. Only the best trusted domains
    # are used here to keep Render latency bounded.
    if len(found)<4 and time.monotonic() < resolver_deadline:
        for domain in preferred[:4]:
            q=variants[min(2,len(variants)-1)]['q']+' site:'+domain
            rss_candidates(q,'site:'+domain,60)
            if len(found)>=6: break

    # Strategy 3: Bing RSS. Unlike the HTML search page, this returns direct result URLs
    # and is much less sensitive to JavaScript/consent pages on cloud IPs.
    query=variants[min(2,len(variants)-1)]['q'] if variants else title
    try:
        bing_rss='https://www.bing.com/search?format=rss&q='+quote_plus(query)
        rr=fetch(bing_rss,timeout=6)
        note('FALLBACK_BING_RSS:'+str(getattr(rr,'status_code','?')))
        if rr.ok:
            root=ET.fromstring(rr.content)
            for item in root.findall('.//item')[:10]:
                link_el=item.find('link')
                href=(link_el.text or '').strip() if link_el is not None else ''
                add(href,'bing-rss',55)
                if len(found)>=8: break
    except Exception as e:
        note('FALLBACK_BING_RSS_ERROR:'+type(e).__name__+':'+str(e)[:80])

    # Strategy 4: normal search engines. Each engine is independent; one failure does not
    # poison the next strategy. DuckDuckGo remains last because cloud IPs are often limited.
    engines=(
        ('bing','https://www.bing.com/search?q='+quote_plus(query)+'&setlang=pt-BR'),
        ('google','https://www.google.com/search?q='+quote_plus(query)+'&hl=pt-BR&num=10'),
        ('ddg','https://html.duckduckgo.com/html/?q='+quote_plus(query)),
    )
    for engine,qurl in engines:
        try:
            rr=fetch(qurl,timeout=6)
            note('FALLBACK_SEARCH:'+engine+':'+str(getattr(rr,'status_code','?')))
            if not rr.ok: continue
            soup=BeautifulSoup(rr.text,'html.parser')
            # Search markup changes frequently on cloud/consent pages. Do not rely
            # on one CSS selector: inspect the first useful anchors as well.
            selectors=('li.b_algo h2 a','a.result__a') if engine!='google' else ('a[href]',)
            for sel in selectors:
                if not sel: continue
                for a in soup.select(sel)[:80]:
                    add(a.get('href'),'html-'+engine,30)
            # Last-resort extraction from the raw HTML catches URLs embedded in
            # scripts/JSON when the search page is rendered differently.
            for raw in re.findall(r'https?://[^\s\"<>]+', rr.text)[:200]:
                add(html.unescape(raw),'raw-'+engine,18)
        except Exception as e:
            note('FALLBACK_SEARCH_ERROR:'+engine+':'+type(e).__name__+':'+str(e)[:80])

    # Strategy 5: publisher-specific search queries. This is the important recovery path
    # when general search returns no parseable links. Only four trusted domains are tried,
    # and only the direct result URL is accepted.
    if len(found)<4 and time.monotonic() < resolver_deadline:
        for domain in preferred[:4]:
            if time.monotonic()>resolver_deadline: break
            q='site:'+domain+' '+query
            try:
                u='https://www.bing.com/search?format=rss&q='+quote_plus(q)
                rr=fetch(u,timeout=5)
                note('FALLBACK_SITE_RSS:'+domain+':'+str(getattr(rr,'status_code','?')))
                if rr.ok:
                    root=ET.fromstring(rr.content)
                    for item in root.findall('.//item')[:5]:
                        link_el=item.find('link')
                        href=(link_el.text or '').strip() if link_el is not None else ''
                        add(href,'bing-rss-site:'+domain,50)
                        if len(found)>=8: break
            except Exception as e:
                note('FALLBACK_SITE_RSS_ERROR:'+domain+':'+type(e).__name__)
            if len(found)>=8: break

    # Strategy 5.5: publisher-native RSS/search feeds. This bypasses search-engine
    # result-page markup and can return the article URL directly on WordPress-like
    # publishers. It is discovery only; the article body is still fetched and checked
    # later by the strict source-lock gate.
    if len(found)<4 and time.monotonic() < resolver_deadline:
        # Skip the first domains when they have already returned only non-article
        # roots/feed URLs in this resolver pass. This prevents burning the budget
        # on the same publisher repeatedly.
        feed_domains=preferred[:10]
        for domain in feed_domains:
            if time.monotonic() >= resolver_deadline: break
            try:
                feed_url='https://'+domain+'/feed/?s='+quote_plus(query)
                rr=fetch(feed_url,timeout=4)
                note('FALLBACK_PUBLISHER_FEED:'+domain+':'+str(getattr(rr,'status_code','?')))
                if rr.ok and ('xml' in str(rr.headers.get('content-type','')).lower() or rr.text.lstrip().startswith('<?xml')):
                    root=ET.fromstring(rr.content)
                    for item in root.findall('.//item')[:8]:
                        link=(item.findtext('link') or '').strip()
                        before=len(found)
                        add(link,'publisher-feed:'+domain,48)
                        if len(found)==before and link:
                            note('PUBLISHER_FEED_NONARTICLE:'+domain+':'+link[:120])
                        if len(found)>=8: break
            except Exception as e:
                note('FALLBACK_PUBLISHER_FEED_ERROR:'+domain+':'+type(e).__name__)
            if len(found)>=8: break

    # Final ranking: learned successful domains + discovery quality + original reason.
    def rank(item):
        priority,href,reason=item
        host=_resolver_domain(href); st=domain_stats.get(host,{})
        learned=min(25,int(st.get('success',0))*3)
        return priority+learned
    found.sort(key=rank,reverse=True)
    return [href for _,href,_ in found[:24]]


def _topic_title_overlap(title, lines):
    """Score whether a candidate body is about the same story."""
    title_words=set(_resolver_tokens(title))
    text_words=set(_resolver_tokens(' '.join(lines[:12])))
    if not title_words or not text_words: return 0.0
    base=sum(1 for w in title_words if w in text_words)/len(title_words)
    important=set(w for w in title_words if w in {'gta','gta6','vi','xbox','cloud','gaming','pc','microsoft','rockstar','streaming','jason','lucia','leonida','trailer','gameplay'})
    important_score=sum(1 for w in important if w in text_words)/max(1,len(important))
    return round(base*0.65+important_score*0.35,3)


def _topic_recovery_urls(topic):
    out=[]; seen=set()
    for u in (topic.get('recovery_urls') or []):
        u=str(u or '').strip()
        if u and u not in seen: seen.add(u); out.append(u)
    for u in _known_source_candidates(str(topic.get('title') or '')):
        u=str(u or '').strip()
        if u and u not in seen: seen.add(u); out.append(u)
    return out[:10]


def _fetch_direct_article_candidate(url, title, topic, strategy='direct-recovery', timeout=12):
    global _last_gnews_diagnostics
    url=str(url or '').strip()
    if not url or _is_google_news_url(url): return None
    try:
        p=urlparse(url); path=(p.path or '').lower()
        if any(tok in path for tok in ('/feed','/rss','/atom','/search','/tag/','/category/','/author/','/sitemap','/wp-json')): return None
        r=fetch(url,timeout=timeout); r.raise_for_status()
        final=str(getattr(r,'url','') or url).strip()
        if not final or _is_google_news_url(final): return None
        lines,method=_extract_article_body_from_html(r.text)
        if not lines:
            _resolver_learn(_resolver_domain(final),strategy,False); return None
        overlap=_topic_title_overlap(title,lines)
        if overlap < 0.18:
            _resolver_learn(_resolver_domain(final),'story-match',False); return None
        host=_resolver_domain(final); _resolver_learn(host,strategy,True)
        topic['_resolved_url']=final; topic['_source_used']=host; topic['_source_fallback']=True; topic['_resolver_score']=overlap
        _last_gnews_diagnostics=(list(_last_gnews_diagnostics or [])+[f'V54_DIRECT_RECOVERED:{host}:{method}'])[-24:]
        return lines,final,f'SECONDARY_{method}'
    except Exception as e:
        _last_gnews_diagnostics=(list(_last_gnews_diagnostics or [])+[f'V54_DIRECT_FAIL:{_resolver_domain(url)}:{type(e).__name__}'])[-24:]
        return None


def _fetch_topic_evidence(topic):
    global _last_gnews_diagnostics
    """V40.7: source-locked first, then same-story trusted-source fallback.

    The original publisher remains the preferred source. If it resolves correctly but
    blocks the server-side body (common with anti-bot/robots pages), the producer may
    use a second reputable publisher covering the exact same story. The fallback URL
    is stored as the factual source; the original URL is retained in the topic metadata.
    No RSS description, meta description, search snippet, or generic <main> is used.
    """
    original_url=str(topic.get('url') or '').strip()
    # V55: diagnostics are per production; old jobs can no longer pollute the next log.
    _last_gnews_diagnostics=[]
    try: _last_gnews_diagnostics=['V55_RESOLVER_START']
    except Exception: pass
    title=str(topic.get('title') or '').strip()
    source_name=str(topic.get('source') or '').strip()
    direct_candidates=_topic_recovery_urls(topic)
    if direct_candidates:
        _last_gnews_diagnostics=(list(_last_gnews_diagnostics or [])+[f'V54_DIRECT_RECOVERY_POOL:{len(direct_candidates)}'])[-24:]
        for direct_url in direct_candidates:
            recovered=_fetch_direct_article_candidate(direct_url,title,topic,'direct-recovery',timeout=12)
            if recovered:
                lines,final_url,method=recovered
                topic['_original_url']=original_url; topic['_source_original']=source_name
                return lines,final_url,method
    # V55 deterministic recovery: try a few independently validated direct GTA 6 articles
    # before spending more resolver budget. They still pass the strict body and story-match gates.
    v55_direct = [
        'https://gamenoticias.com.br/gta-6-50-novidades-incriveis-confirmadas-no-novo-jogo-da-rockstar/',
        'https://www.omelete.com.br/games/gta-6-revela-detalhes-da-historia-confira',
        'https://www.omelete.com.br/games/gta-6-gameplays-ineditos-novos'
    ]
    if 'gta 6' in title.lower() or 'gta vi' in title.lower():
        for direct_url in v55_direct:
            if direct_url in direct_candidates: continue
            recovered=_fetch_direct_article_candidate(direct_url,title,topic,'v55-known-direct',timeout=10)
            if recovered:
                lines,final_url,method=recovered
                topic['_original_url']=original_url; topic['_source_original']=source_name
                _last_gnews_diagnostics=(list(_last_gnews_diagnostics or [])+[f'V55_KNOWN_DIRECT_RECOVERED:{_resolver_domain(final_url)}'])[-24:]
                return lines,final_url,method

    # Important V42.2 change: a failed Google News decode MUST NOT end production.
    # The previous implementation returned BLOCKED_URL here and never reached the
    # secondary-source resolver. That made a temporary Google 429 indistinguishable
    # from a genuinely unresolved story. We now keep the unresolved URL as discovery
    # context and continue automatically to independent trusted-source discovery.
    url=_resolve_article_url(original_url, title, source_name)

    # Primary publisher: preserve strict source lock when its real article body is reachable.
    if url and not _is_google_news_url(url):
        try:
            r=fetch(url,timeout=22); r.raise_for_status()
            final_url=str(getattr(r,'url','') or url).strip()
            if not _is_google_news_url(final_url):
                lines,method=_extract_article_body_from_html(r.text)
                if lines:
                    topic['_original_url']=original_url
                    topic['_resolved_url']=final_url
                    topic['_source_original']=source_name
                    topic['_source_used']=source_name
                    _resolver_learn(_resolver_domain(final_url),'primary-source',True)
                    return lines, final_url, method
                _resolver_learn(_resolver_domain(final_url),'article-body-extraction',False)
        except Exception as e:
            try:
                _last_gnews_diagnostics=(list(_last_gnews_diagnostics or [])+[f'PRIMARY_FETCH_ERROR:{type(e).__name__}:{str(e)[:100]}'])[-24:]
            except Exception:
                pass

    # V42.2: autonomous secondary-source recovery. A Google News decoder failure
    # (especially HTTP 429) is treated as a discovery problem, never as a content
    # failure. We immediately switch to independent trusted publishers/search engines.
    try:
        diag_text=' | '.join(_last_gnews_diagnostics[-8:])
        if '429' in diag_text:
            _last_gnews_diagnostics=(list(_last_gnews_diagnostics or [])+['AUTONOMOUS_FALLBACK_TRIGGER:GOOGLE_429'])[-24:]
        else:
            _last_gnews_diagnostics=(list(_last_gnews_diagnostics or [])+['AUTONOMOUS_FALLBACK_TRIGGER:PRIMARY_UNRESOLVED'])[-24:]
    except Exception:
        pass
    # Secondary source fallback: adaptive same-story resolver. It can run a second
    # discovery pass with different semantic queries if the first candidate set fails.
    tried=set()
    resolver_deadline=time.monotonic()+32
    for resolver_pass in range(2):
        if time.monotonic()>resolver_deadline:
            try: _last_gnews_diagnostics=(list(_last_gnews_diagnostics or [])+['RESOLVER_BUDGET_EXCEEDED'])[-24:]
            except Exception: pass
            break
        # Pass 0 uses the normal adaptive resolver. Pass 1 deliberately broadens
        # the query by dropping the original publisher name, which helps when the
        # headline itself is too publisher-specific. The candidate function remains
        # source-locked and trusted-domain-only for factual extraction.
        if resolver_pass == 0:
            candidates=_article_url_candidates_from_search(title, source_name)
        else:
            broad_title=re.sub(r'\s+-\s+[^-]+$','',title).strip()
            broad_title=re.sub(r'\b(?:confirma|confirmou|revela|revelou|segundo executivo|diz executivo)\b','',broad_title,flags=re.I)
            candidates=_article_url_candidates_from_search(broad_title or title, '')
            try:
                _last_gnews_diagnostics=(list(_last_gnews_diagnostics or [])+['FALLBACK_PASS:2_BROAD_QUERY'])[-24:]
            except Exception:
                pass
        if not candidates: continue
        for alt_url in candidates:
            if time.monotonic()>resolver_deadline: break
            if alt_url in tried: continue
            tried.add(alt_url)
            host_guess=_resolver_domain(alt_url)
            # Defensive second gate before spending network time on a candidate.
            try:
                p=urlparse(alt_url); path=(p.path or '').lower()
                if any(tok in path for tok in ('/feed','/rss','/atom','/search','/tag/','/category/','/author/','/sitemap','/wp-json')):
                    continue
            except Exception:
                pass
            try:
                ar=fetch(alt_url,timeout=12); ar.raise_for_status()
                final_alt=str(getattr(ar,'url','') or alt_url).strip()
                if _is_google_news_url(final_alt): continue
                lines,method=_extract_article_body_from_html(ar.text)
                if not lines:
                    _resolver_learn(host_guess,'article-body-extraction',False)
                    continue
                overlap=_topic_title_overlap(title,lines)
                # 0.22 is the minimum only when important GTA/story entities also match.
                if overlap < 0.22:
                    _resolver_learn(host_guess,'story-match',False)
                    continue
                host=_resolver_domain(final_alt)
                _resolver_learn(host,'secondary-source',True)
                alt_name={
                    'tecnoblog.net':'Tecnoblog','omelete.com.br':'Omelete','exame.com':'Exame',
                    'terra.com.br':'Terra','meups.com.br':'MeuPlayStation','criticalhits.com.br':'Critical Hits',
                    'games.gg':'Games.gg','antihype.com.br':'Antihype','portaldopixel.com.br':'Portal do Pixel',
                    'portaldovideogame.com.br':'Portal do Videogame','centralxbox.com.br':'Central Xbox',
                    'flowgames.gg':'Flow Games','olhardigital.com.br':'Olhar Digital','tecmundo.com.br':'TecMundo',
                    'rockstargames.com':'Rockstar Games','leonidainteractive.com':'Leonida Interactive',
                    'lockegames.com.br':'Locke Games','gamestart.com.br':'GameStart','egamersworld.com':'EGamersWorld'
                }.get(host,host)
                topic['_original_url']=original_url
                topic['_resolved_url']=final_alt
                topic['_source_original']=source_name
                topic['_source_used']=alt_name
                topic['_source_fallback']=True
                topic['_resolver_score']=overlap
                _last_gnews_diagnostics=(list(_last_gnews_diagnostics or [])+[f'SECONDARY_RECOVERED:{host}:{method}'])[-24:]
                return lines, final_alt, f'SECONDARY_{method}'
            except Exception as e:
                _resolver_learn(host_guess,'candidate-fetch',False)
                continue

    # We reached the end only after exhausting trusted-source discovery.
    # Distinguish an unresolved Google URL from a resolved page with no article body
    # so the autonomous engine can learn which strategy actually failed.
    if not url or _is_google_news_url(url):
        return [], original_url, 'BLOCKED_URL'
    return [], url, 'BLOCKED_NO_ARTICLE_BODY'

def _evidence_sentences(desc, article_lines=None, title='', extraction_method=''):
    """V34: evidência SOMENTE do corpo da matéria. desc é deliberadamente ignorado."""
    raw=list(article_lines or [])
    if not raw:
        return []
    title_norm=re.sub(r'[^a-z0-9à-ÿ ]',' ',title.lower())
    title_words=set(w for w in title_norm.split() if len(w)>3)
    seen=set(); clean=[]
    for x in raw:
        x=re.sub(r'\s+',' ',x).strip(' -–—')
        if len(x)<35: continue
        low=x.lower()
        if any(bad in low for bad in ('leia também','publicidade','clique aqui','assine','cookies','newsletter')): continue
        # Bloqueia aparência de manchete/listagem.
        if len(re.findall(r'[:|–—-]',x))>=3 and len(x.split())<20: continue
        # Rejeita linhas excessivamente curtas ou fragmentadas.
        if len(x.split())<8: continue
        overlap=len(title_words.intersection(set(re.sub(r'[^a-z0-9à-ÿ ]',' ',low).split())))
        gta_relevance=any(k in low for k in ('gta 6','gta vi','grand theft auto vi','rockstar','vice city','jason','lucia','xbox cloud','cloud gaming'))
        if gta_relevance or overlap>=1:
            key=re.sub(r'\W+',' ',low).strip()
            if key not in seen:
                seen.add(key); clean.append(x)
    return clean[:5]

def _fact_sentence(text):
    text=re.sub(r'\s+',' ',str(text or '')).strip(' -–—')
    text=_strip_publisher_suffix(text)
    text=re.sub(r'^(?:segundo|conforme|de acordo com)\s+(?:o|a)\s+(?:material|conteúdo|publicação)[,:]?\s*','',text,flags=re.I)
    return text


def _safe_hook(title,kind):
    t=title.lower()
    if kind=='RUMOR': return 'ISSO SOBRE GTA 6 AINDA NÃO FOI CONFIRMADO'
    if kind=='NOTÍCIA':
        if any(k in t for k in ('confirm','confirma','oficial','revela','revelou','anuncia','anunciou')):
            return 'A ROCKSTAR ACABOU DE REVELAR UMA NOVIDADE'
        return 'UMA NOVA INFORMAÇÃO SOBRE GTA 6 CHAMOU ATENÇÃO'
    if kind=='MISTÉRIO': return 'ESSE DETALHE DE GTA 6 CHAMOU ATENÇÃO'
    return 'VOCÊ PERCEBEU ESSE DETALHE NO GTA 6?'



def _editorial_noise_score(text, headline=''):
    """Detects text that looks like a headline/metadata rather than article body."""
    t=re.sub(r'\s+',' ',str(text or '')).strip()
    low=t.lower()
    score=0
    if '|' in t or 'http://' in low or 'https://' in low: score += 3
    if re.search(r'\b(?:ign brasil|tudocelular|canaltech|olhar digital|adrenaline|terra|tecnoblog|the verge|uol|tecmundo)\b',low):
        score += 3
    if re.search(r'\b(?:terça|terca|segunda|quarta|quinta|sexta|sábado|sabado|domingo)-feira\s*\(\d{1,2}\)',low):
        score += 1
    if re.search(r'\b(?:revela|revelou|nega|nega que|garante|confirma|afirma|afirmou)\b',low) and len(t.split()) < 22:
        score += 1
    if headline:
        # V55.7: topic overlap alone is NOT headline contamination.
        # A narration is expected to repeat the subject/title naturally.
        # Only flag a near-verbatim short headline fragment.
        hw=set(re.findall(r'[a-zà-ÿ0-9]+',headline.lower()))
        tw=set(re.findall(r'[a-zà-ÿ0-9]+',low))
        if hw and tw:
            overlap=len(hw & tw)/max(1,len(hw))
            if overlap>=0.95 and len(t.split())<=16:
                score += 2
    return score

def _clean_evidence_for_script(items, headline):
    """Keep factual article-body sentences and reject headline-like fragments."""
    out=[]
    seen=set()
    for raw in items or []:
        x=_clean_narrative_text(_fact_sentence(raw))
        x=re.sub(r'\s+',' ',x).strip()
        words=re.findall(r"[A-Za-zÀ-ÿ0-9']+",x)
        if len(words)<8 or len(words)>42:
            continue
        if _editorial_noise_score(x,headline)>=3:
            continue
        key=re.sub(r'[^a-zà-ÿ0-9]+',' ',x.lower()).strip()
        if key in seen:
            continue
        seen.add(key)
        out.append(x.rstrip('.!?')+'.')
    return out

def _clean_narrative_text(text):
    """V41.1: limpa rastros de manchete, fonte e metadados sem inventar fatos."""
    t=BeautifulSoup(str(text or ''),'html.parser').get_text(' ',strip=True)
    t=re.sub(r'https?://\S+',' ',t)
    t=_strip_publisher_suffix(t)
    banned=[
        r'\b(?:score|confiança|confianca|matérias|materias|fontes|menções|mencoes)\s*[:=]?\s*\d+%?\b',
        r'\b(?:IGN\s*Brasil|TudoCelular(?:\.com)?|Canaltech|Olhar\s+Digital|Adrenaline|Omelete|Exame|UOL|TecMundo|Combo\s+Infinito|Rolling\s+Stone(?:\s+Brasil)?|Terra|Tecnoblog|The\s+Verge)\b',
        r'\b(?:radar|editor-chefe|editorial|pauta selecionada|produzir agora)\b',
        r'\b(?:leia mais|leia também|compartilhe|siga-nos|newsletter|publicidade)\b',
    ]
    for pat in banned:
        t=re.sub(pat,'',t,flags=re.I)
    t=re.sub(r'\s+',' ',t).strip(' -–—,;:')
    # Remove leftover separators commonly created when metadata is stripped.
    t=re.sub(r'\s+[|•]\s+',' ',t)
    return t

def _sentence_from_evidence(evidence):
    """Escolhe UMA evidência da matéria, evitando juntar frases de fontes diferentes."""
    for x in evidence:
        x=_fact_sentence(x)
        x=_clean_narrative_text(x)
        if len(re.findall(r"[A-Za-zÀ-ÿ0-9']+",x))>=8:
            return x.rstrip('.!?') + '.'
    return ''


def _is_source_recovery_error(exc):
    """Classify resolver/source failures that are safe to recover autonomously."""
    msg=str(exc or '').lower()
    keys=(
        'blocked_url','blocked_no_article_body','matéria sem corpo','materia sem corpo',
        'corpo principal extraído','corpo original confiável','resolver_budget_exceeded',
        'resolver budget','source-lock','source lock','sem evidência da matéria principal'
    )
    return any(k in msg for k in keys)


def _autonomous_make_script(jid, topic, topics):
    """V55: validates source before committing to a production topic and changes topic automatically on failure."""
    if not AUTONOMOUS_MODE:
        return topic, make_script(topic)
    candidates=[]; seen=set()
    recovery_pool=[topic] + list(topics or []) + list(FALLBACK_TOPICS)
    for t in recovery_pool:
        if not isinstance(t,dict): continue
        key=str(t.get('id') or t.get('title') or '').strip().lower()
        if not key or key in seen: continue
        seen.add(key); candidates.append(dict(t))
    candidates.sort(key=lambda x:(1 if x.get('recovery_urls') else 0, int(x.get('score',0))), reverse=True)
    candidates=candidates[:max(AUTONOMOUS_MAX_TOPIC_RECOVERY,6)]
    last_exc=None
    for attempt,candidate in enumerate(candidates,1):
        try:
            update_job(jid,title=str(candidate.get('title') or 'GTA 6'),opportunity=candidate,stage='AUTO-RECUPERAÇÃO',progress=min(30,24+attempt),
                       log=f'🤖 V54: validando fonte antes de renderizar — pauta {attempt}/{len(candidates)}: {candidate.get("title","")}')
            script=make_script(candidate)
            if attempt>1:
                update_job(jid,log=f'✅ V54 AUTO-TROCA: corpo original encontrado. Nova pauta: {candidate.get("title","")}')
            return candidate, script
        except Exception as exc:
            last_exc=exc
            if not _is_source_recovery_error(exc): raise
            try: _learn_event('V54_SOURCE_RECOVERY_FAILED',f'pauta descartada: {str(exc)[:500]}',candidate.get('title',''))
            except Exception: pass
            update_job(jid,log='⚠️ V54: pauta descartada por fonte não confiável/indisponível. Tentando automaticamente a próxima pauta...')
    if last_exc:
        raise ValueError('V55: nenhuma pauta com corpo original confiável foi encontrada após recuperação automática. Última falha: '+str(last_exc)[:600])
    raise ValueError('V55: nenhuma oportunidade disponível para recuperação de fonte.')


def make_script(topic):
    """V33 — Main Article Locked.
    Uma matéria principal. Um corpo principal. Um roteiro.
    Se a página não puder ser identificada/extraída com segurança, a produção falha
    em vez de preencher o vídeo com manchetes ou fatos de outras páginas.
    """
    title,desc,source,url=_source_evidence(topic)
    title=title or 'GTA 6'
    kind=str(topic.get('content_type') or 'CURIOSIDADE').upper()
    if kind not in ('RUMOR','MISTÉRIO','NOTÍCIA','CURIOSIDADE'):
        tl=title.lower()
        if any(k in tl for k in ('rumor','leak','vazamento','suposto','suposta')): kind='RUMOR'
        elif any(k in tl for k in ('teoria','pista','mistério','misterio','segredo','detalhe','escond')): kind='MISTÉRIO'
        elif any(k in tl for k in ('confirm','revel','anunci','atualização','update','novidade')): kind='NOTÍCIA'
        else: kind='CURIOSIDADE'

    article_lines,resolved_url,extraction_method=_fetch_topic_evidence(topic)
    if not article_lines or extraction_method.startswith('BLOCKED_'):
        raise ValueError(
                    f'MATÉRIA SEM CORPO ORIGINAL CONFIÁVEL — produção bloqueada ({extraction_method}). '
                    f'GoogleResolver={" | ".join(_last_gnews_diagnostics[-8:]) if _last_gnews_diagnostics else "sem diagnóstico"}'
                )
    evidence_raw=_evidence_sentences('',article_lines,title,extraction_method)
    evidence=_clean_evidence_for_script(evidence_raw,title)

    # Só aceita produção quando há conteúdo factual da matéria principal.
    if not evidence:
        raise ValueError('MATÉRIA SEM CORPO PRINCIPAL EXTRAÍDO — produção bloqueada para evitar mistura de manchetes.')

    angle,_=_editorial_angle(topic)
    headline=_clean_narrative_text(title.rstrip('.!?'))
    # Remove prefixos redundantes e publisher no título.
    headline=re.sub(r'^\s*(?:gta\s*6|gta\s*vi)\s*[:\-–—]\s*', 'GTA 6 — ', headline, flags=re.I)
    headline=_strip_publisher_suffix(headline)
    headline=re.sub(r'\s+',' ',headline).strip(' -–—')
    clean_topic=re.sub(r'^\s*GTA\s*6\s*[—:-]\s*','',headline,flags=re.I).strip()
    if not clean_topic:
        clean_topic='uma nova informação sobre GTA 6'

    hook_map={
        'NOTÍCIA':'A ROCKSTAR REVELOU UMA NOVA INFORMAÇÃO SOBRE GTA 6',
        'RUMOR':'ISSO SOBRE GTA 6 AINDA NÃO FOI CONFIRMADO',
        'MISTÉRIO':'ESSE DETALHE DE GTA 6 CHAMOU ATENÇÃO',
        'CURIOSIDADE':'VOCÊ JÁ TINHA PERCEBIDO ESSE DETALHE NO GTA 6?',
    }
    hook=hook_map[kind]

    # Usa no máximo dois fatos fortes do MESMO corpo principal.
    # Menos fatos, melhor retenção e menor chance de carregar ruído editorial.
    fact_parts=[]
    for item in evidence[:2]:
        item=_clean_narrative_text(item).rstrip('.!?')
        if item and item not in fact_parts:
            fact_parts.append(item)
    fact='. '.join(fact_parts)+'.'

    if kind=='NOTÍCIA':
        context=f'Uma nova informação envolvendo GTA 6 ganhou destaque: {clean_topic}.'
        payoff='O ponto principal é separar o que a matéria realmente informa daquilo que ainda seria apenas especulação.'
        cta='Você quer ver mais detalhes sobre isso no GTA 6?'
    elif kind=='RUMOR':
        context=f'Está circulando uma informação envolvendo GTA 6: {clean_topic}.'
        payoff='Até existir confirmação oficial, essa informação deve ser tratada como possibilidade, não como fato.'
        cta='Você acha que esse rumor pode se confirmar?'
    elif kind=='MISTÉRIO':
        context=f'Um detalhe envolvendo GTA 6 chamou atenção: {clean_topic}.'
        payoff='O interessante é analisar a pista sem transformar uma interpretação em confirmação.'
        cta='Você acha que esse detalhe significa alguma coisa?'
    else:
        context=f'Tem um detalhe de GTA 6 que merece atenção: {clean_topic}.'
        payoff='O mais importante é entender o que a própria matéria mostra antes de tirar conclusões.'
        cta='Você já tinha percebido esse detalhe?'

    sections={
        'hook':hook,
        'context':_clean_narrative_text(context),
        'proof':_clean_narrative_text(fact),
        'payoff':_clean_narrative_text(payoff),
        'cta':_clean_narrative_text(cta),
    }
    narration=' '.join(sections[k] for k in ('hook','context','proof','payoff','cta'))
    narration=_clean_narrative_text(narration)
    # Defesa final: nenhum título de outra pauta deve aparecer como bloco na fala.
    if narration.count('GTA 6')>4:
        narration=re.sub(r'\bGTA 6\b','GTA VI',narration,count=max(0,narration.count('GTA 6')-3),flags=re.I)
    # Não comparar a fala inteira com a manchete: o roteiro legítimo pode repetir
    # o assunto da pauta no contexto. A comparação com headline continua sendo
    # usada na limpeza das evidências, onde ela é apropriada.
    if _editorial_noise_score(narration)>=3:
        raise ValueError('GATE EDITORIAL: roteiro contaminado por manchete/metadado detectado antes da narração.')
    word_count=len(re.findall(r"[A-Za-zÀ-ÿ0-9']+",narration))
    estimated_seconds=max(20,min(60,round(word_count/2.55)))
    return {
        'title':headline,'narration':narration,'source':resolved_url or url,
        'source_name':source or str(topic.get('source') or 'Fonte da pauta'),'content_type':kind,
        'editorial_angle':angle,'editorial_hook':hook,
        'editorial_score':topic.get('editorial_score'),'editorial_decision':topic.get('editorial_decision','PRODUZIR'),
        'editorial_reason':topic.get('editorial_reason',''),'sections':sections,
        'evidence':evidence[:3],'word_count':word_count,'estimated_seconds':estimated_seconds,
        'script_version':'V51-SEMANTIC-CAPTION-VISUAL-REPETITION-GATE','extraction_method':extraction_method
    }

def build_dynamic_captions(script, topic, count=9):
    """V30 — captions são apenas da fala real; sem título, fonte ou metadados extras."""
    narration=re.sub(r'\s+',' ',str(script.get('narration','')).strip())
    sentences=[s.strip() for s in re.split(r'(?<=[.!?])\s+',narration) if s.strip()]
    return [x['text'] for x in build_short_timeline(script,topic, max(20,float(script.get('estimated_seconds',30))), count)] if narration else ['GTA 6']


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

def select_visuals(paths, topic_title, count=10):
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



def _editorial_penalty(topic):
    """Penaliza pautas que parecem clickbait, frágeis ou pouco aproveitáveis em Short."""
    title=str(topic.get('title','')).lower()
    p=0
    if topic.get('content_type')=='RUMOR': p += 7
    if topic.get('status')=='OBSERVAR': p += 8
    if int(topic.get('confidence',70) or 70) < 55: p += 10
    if int(topic.get('source_count',1) or 1) < 2 and topic.get('content_type')=='RUMOR': p += 8
    if any(k in title for k in ('pode ser','acredita','talvez','suposto','vazamento')): p += 4
    if len(title) > 105: p += 2
    return p


def _editorial_angle(topic):
    """Define o melhor ângulo narrativo sem inventar fatos novos."""
    title=str(topic.get('title','')).strip()
    kind=topic.get('content_type','CURIOSIDADE')
    if kind=='RUMOR':
        return ('Separar fato de especulação e explicar por que o rumor chamou atenção.',
                'ISSO SOBRE GTA 6 É VERDADE OU SÓ RUMOR?')
    if kind=='NOTÍCIA':
        return ('Explicar o que realmente foi confirmado e por que isso importa para GTA 6.',
                'A ROCKSTAR CONFIRMOU ISSO NO GTA 6')
    if kind=='MISTÉRIO':
        return ('Mostrar o detalhe e apresentar a interpretação sem tratá-la como confirmação.',
                'ESSE DETALHE DE GTA 6 PODE SER IMPORTANTE')
    return ('Apresentar o detalhe mais interessante e conectar com o que já foi mostrado oficialmente.',
            'VOCÊ PERCEBEU ESSE DETALHE NO GTA 6?')


def editor_chief_select(topics):
    """EDITOR-CHEFE V27: escolhe a pauta mais forte com regras editoriais explícitas."""
    if not topics:
        return None
    scored=[]
    for topic in topics:
        base=float(topic.get('score',0) or 0)
        conf=float(topic.get('confidence',70) or 70)
        sources=int(topic.get('source_count',1) or 1)
        mentions=int(topic.get('mentions',1) or 1)
        status=str(topic.get('status','')).upper()
        kind=topic.get('content_type','CURIOSIDADE')
        # O score do Radar continua importante, mas não manda sozinho na decisão.
        editorial=base*0.52 + conf*0.25 + min(20,sources*5)*0.12 + min(15,mentions*2)*0.06
        if status=='PRODUZIR AGORA': editorial += 7
        elif status=='PRODUZIR': editorial += 3
        if kind=='NOTÍCIA': editorial += 4
        elif kind=='MISTÉRIO': editorial += 2
        editorial -= _editorial_penalty(topic)
        # Uma pauta oficial é preferida quando scores são próximos.
        if str(topic.get('source','')).lower().find('rockstar')>=0:
            editorial += 3
        angle,hook=_editorial_angle(topic)
        item=dict(topic)
        item['editorial_score']=int(max(0,min(100,round(editorial))))
        item['editorial_angle']=angle
        item['editorial_hook']=hook
        item['editorial_decision']='PRODUZIR' if item['editorial_score']>=62 else 'OBSERVAR'
        if item['editorial_score']>=78 and conf>=65:
            item['editorial_decision']='PRODUZIR AGORA'
        item['editorial_reason']=f"Radar {int(base)}/100 + confiança {int(conf)}% + {sources} fonte(s); tipo {kind}."
        scored.append(item)
    scored.sort(key=lambda x:(x['editorial_score'],x.get('confidence',0),x.get('score',0)),reverse=True)
    return scored[0]


def choose_topic(data,topics):
    if data.get('id'):
        for o in topics:
            if o['id']==data['id']: return o
    custom=(data.get('topic') or '').strip()
    if custom:
        topic={'id':'custom','score':88,'priority':'ALTA','title':custom,'source':'Pesquisa editorial','url':ROCKSTAR_VI,'radar':False,'content_type':'CURIOSIDADE','confidence':70,'source_count':1}
        angle,hook=_editorial_angle(topic)
        topic.update(editorial_score=78,editorial_angle=angle,editorial_hook=hook,editorial_decision='PRODUZIR AGORA',editorial_reason='Assunto informado diretamente pelo usuário.')
        return topic
    return editor_chief_select(topics)


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
    # Branding is added only in the final timeline, as a watermark.
    im.save(dst,quality=84,optimize=True)
    im.close()


def _ffmpeg_executable():
    """Resolve FFmpeg robustly on Render/Linux.
    Prefer the system binary (already used by ffprobe/rendering), then fall back
    to imageio-ffmpeg only if it is installed. This prevents a missing optional
    Python module from breaking the entire production pipeline.
    """
    ff = shutil.which('ffmpeg')
    if ff:
        return ff
    try:
        import imageio_ffmpeg
        return str(imageio_ffmpeg.get_ffmpeg_exe())
    except Exception as e:
        raise RuntimeError('FFmpeg não encontrado no ambiente. Instale ffmpeg ou imageio-ffmpeg. Detalhe: '+str(e)[:500])


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
    """V32.0: gera áudio PT-BR e tenta capturar WordBoundary; se a versão do
    edge-tts instalada no Render não expuser esses eventos, a produção continua
    usando o fallback editorial sincronizado pela duração real do áudio."""
    if edge_tts is None:
        raise RuntimeError('edge-tts não disponível no servidor')
    last=None
    for voice in ['pt-BR-AntonioNeural','pt-BR-FranciscaNeural']:
        try:
            comm=edge_tts.Communicate(text,voice,rate='+3%',pitch='-2Hz')
            cues=[]
            with open(path,'wb') as fh:
                async for chunk in comm.stream():
                    typ=str(chunk.get('type',''))
                    low=typ.lower().replace('_','')
                    if typ=='audio':
                        fh.write(chunk.get('data',b''))
                        continue
                    # Edge-TTS já mudou a forma/nome desses eventos em algumas
                    # versões. Aceitamos variações sem quebrar a produção.
                    if 'wordboundary' in low or low in ('word','wordbound'):
                        try:
                            word=str(chunk.get('text') or chunk.get('word') or '').strip()
                            offset=chunk.get('offset',chunk.get('start',0))
                            dur=chunk.get('duration',chunk.get('length',0))
                            start=float(offset)/10_000_000.0
                            duration=float(dur)/10_000_000.0
                            if word:
                                cues.append({'word':word,'start':start,'duration':duration})
                        except Exception:
                            pass
            if path.exists() and path.stat().st_size>1000:
                return cues
        except Exception as e:
            last=e
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
        comp=vals[4]; csize=vals[8]; usize=vals[9]; fn=vals[10]; extra=vals[11]; comm=vals[12]; local=vals[16]
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
    """Baixa apenas os 6 clipes oficiais necessários, sem baixar o ZIP inteiro.
    Usa o diretório central de cache para que um próximo Short reaproveite os clipes.
    """
    outdir.mkdir(parents=True, exist_ok=True)
    cache=WORK/'official_video_cache'; cache.mkdir(parents=True, exist_ok=True)
    clips=sorted([p for p in cache.glob('rockstar_real_v251_*.mp4') if p.stat().st_size>20000])
    if len(clips)>=6:
        return clips[:6]
    try:
        if jid: update_job(jid,log='Lendo catálogo oficial da Rockstar e selecionando apenas os clipes necessários...')
        total,entries=_remote_zip_entries(ROCKSTAR_VIDEO_ZIP)
        media=[e for e in entries if e['name'].lower().endswith(('.mp4','.mov','.m4v'))]
        if len(media)<6:
            raise RuntimeError(f'O pacote oficial possui apenas {len(media)} vídeos utilizáveis.')
        preferred=[]
        for key in ('Jason','Lucia','Cal','Boobie','Raul','Brian','Real','Dre'):
            preferred += [e for e in media if key.lower() in Path(e['name']).stem.lower() and e not in preferred]
        chosen=(preferred+[e for e in media if e not in preferred])[:6]
        ff=_ffmpeg_executable()
        for i,entry in enumerate(chosen):
            target=cache/f'rockstar_real_v251_{i}.mp4'
            if target.exists() and target.stat().st_size>20000:
                continue
            raw=cache/f'raw_v251_{i}.mp4'
            if jid: update_job(jid,log=f'Baixando clipe oficial {i+1}/6: {Path(entry["name"]).stem}...')
            _remote_zip_extract(ROCKSTAR_VIDEO_ZIP,entry,raw)
            run_cmd([ff,'-loglevel','error','-y','-i',str(raw),'-t','5',
                     '-vf','scale=320:568:force_original_aspect_ratio=increase,crop=320:568,setsar=1,fps=15',
                     '-an','-c:v','libx264','-preset','ultrafast','-crf','29','-threads','1',
                     '-filter_threads','1','-filter_complex_threads','1','-x264-params','threads=1:lookahead-threads=1',
                     '-pix_fmt','yuv420p','-movflags','+faststart',str(target)],90)
            try: raw.unlink()
            except Exception: pass
        clips=sorted([p for p in cache.glob('rockstar_real_v251_*.mp4') if p.stat().st_size>20000])
        if len(clips)<6:
            raise RuntimeError(f'Apenas {len(clips)} clipes reais foram preparados.')
        return clips[:6]
    except Exception as e:
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



def _caption_overlay(path,caption,idx,total,W=320,H=568,highlight=None):
    """V41.1 — legenda editorial com quebra visual equilibrada.
    O texto continua sendo exatamente a fala; só a disposição em 1–2 linhas muda.
    Evita linhas com uma única palavra e quebras visualmente tortas.
    """
    im=Image.new('RGBA',(W,H),(0,0,0,0)); d=ImageDraw.Draw(im)

    # GTA OCULTO watermark: small, fixed, low opacity.
    wm=font(11,True)
    wm_text='GTA OCULTO'
    wb=d.textbbox((0,0),wm_text,font=wm)
    wx=W-wb[2]-14; wy=H-wb[3]-10
    d.text((wx,wy),wm_text,font=wm,fill=(255,255,255,105))

    f=font(24,True)
    text=re.sub(r'\s+',' ',str(caption)).strip().upper()
    words=text.split()
    if not words:
        im.save(path); return

    max_width=W-42

    # Build all valid 1/2-line splits and choose the most balanced one.
    # Never create a one-word second line when there is a better alternative.
    lines=[]
    if len(words)<=4:
        # Short phrases stay on one line when they fit.
        test=' '.join(words)
        if d.textbbox((0,0),test,font=f,stroke_width=1)[2] <= max_width:
            lines=[test]
        else:
            lines=[test]
    else:
        candidates=[]
        for cut in range(2,len(words)-1):
            a=' '.join(words[:cut]); b=' '.join(words[cut:])
            wa=d.textbbox((0,0),a,font=f,stroke_width=1)[2]
            wb2=d.textbbox((0,0),b,font=f,stroke_width=1)[2]
            if wa>max_width or wb2>max_width:
                continue
            # Prefer balanced visual width and 2+ words on each line.
            balance=abs(wa-wb2)
            count_balance=abs(len(words[:cut])-len(words[cut:]))*18
            candidates.append((balance+count_balance,cut,a,b))
        if candidates:
            _,cut,a,b=min(candidates,key=lambda x:x[0])
            lines=[a,b]
        else:
            # Fallback greedy wrap, still forbidding a lone final word.
            cur=''
            for w in words:
                test=(cur+' '+w).strip()
                if cur and d.textbbox((0,0),test,font=f,stroke_width=1)[2] > max_width:
                    lines.append(cur); cur=w
                else:
                    cur=test
            if cur: lines.append(cur)
            if len(lines)>2:
                # Merge the last line backwards where possible.
                tail=lines[-1]
                prev=lines[-2]
                merged=(prev+' '+tail).strip()
                if d.textbbox((0,0),merged,font=f,stroke_width=1)[2] <= max_width:
                    lines=lines[:-2]+[merged]
            if len(lines)==2 and len(lines[1].split())==1 and len(lines[0].split())>2:
                w=lines[1]
                parts=lines[0].split()
                candidate=' '.join(parts[-2:] + [w])
                first=' '.join(parts[:-2])
                if first and d.textbbox((0,0),candidate,font=f,stroke_width=1)[2] <= max_width:
                    lines=[first,candidate]

    lines=[x for x in lines if x.strip()]
    if not lines:
        im.save(path); return

    line_h=30
    box_h=22+len(lines)*line_h
    y=H-box_h-45
    d.rounded_rectangle((18,y,W-18,H-45),radius=13,fill=(3,5,9,210),outline=(255,255,255,70),width=1)

    yy=y+8
    hi=str(highlight or '').strip().upper()
    for line in lines[:2]:
        # Render the complete line at once for stable visual rhythm.
        d.text((W/2,yy),line,font=f,anchor='ma',fill='white',
               stroke_width=1,stroke_fill=(0,0,0,220))
        yy += line_h
    im.save(path)

def _clean_caption_phrase(text):
    text=re.sub(r"\s+", " ", str(text)).strip(" .!?,:;-")
    text=re.sub(r"^(?:gta\s*6\s*[:\-]\s*)", "", text, flags=re.I)
    return text.upper()


def _caption_phrases_from_sentence(sentence, max_words=7):
    """Divide a frase em blocos contíguos e naturais, priorizando 3–7 palavras.
    Nunca remove palavras importantes nem cria legendas com palavras fora da fala.
    """
    s=re.sub(r'\s+',' ',str(sentence)).strip(' .!?,:;-')
    if not s: return []
    words=s.split()
    if len(words)<=max_words:
        return [_clean_caption_phrase(s)] if len(words)>=3 else []

    # Pontos naturais de corte. Preferimos pontuação/conjunções antes de cortar no meio.
    boundary=set('e mas porque porém porem então entao quando enquanto se que para'.split())
    out=[]; i=0
    while i<len(words):
        remaining=len(words)-i
        if remaining<=max_words:
            chunk=words[i:]
            if len(chunk)>=3: out.append(_clean_caption_phrase(' '.join(chunk)))
            break
        target=min(max_words, max(4, round(remaining/2)))
        lo=max(i+3,target-2); hi=min(i+max_words,target+2,len(words)-1)
        cut=None
        # Procura uma conjunção no final do primeiro bloco, mantendo a conjunção no próximo.
        for j in range(hi,lo-1,-1):
            if words[j].lower().strip('.,!?;:') in boundary:
                if j-i>=3:
                    cut=j; break
        if cut is None:
            cut=i+target
        chunk=words[i:cut]
        if len(chunk)<3:
            cut=min(i+max_words,len(words)); chunk=words[i:cut]
        out.append(_clean_caption_phrase(' '.join(chunk)))
        i=cut
    return [x for x in out if 3<=len(x.split())<=max_words]


def _caption_words(text):
    """Tokeniza preservando pontuação para decidir cortes linguísticos naturais."""
    return re.findall(r"[^\s]+", re.sub(r'\s+', ' ', str(text)).strip())


def _caption_clean_word(word):
    return re.sub(r'^[\"“”‘’(\[]+|[\"“”‘’),.;:!?\]]+$', '', word).lower()


def _caption_is_bad_start(word):
    return _caption_clean_word(word) in {
        'e','de','do','da','em','no','na','que','um','uma','o','a','os','as',
        'para','com','por','mas','se','ou','ao','à','às','dos','das','num','numa'
    }


def _caption_is_bad_end(word):
    return _caption_clean_word(word) in {
        'e','de','do','da','em','no','na','que','um','uma','o','a','os','as',
        'para','com','por','mas','se','ou','ao','à','às','dos','das','num','numa'
    }


def _semantic_caption_chunks(sentence, min_words=3, max_words=7):
    """V51: segmenta legendas por unidade de sentido, preservando a ordem exata da fala.
    O objetivo é impedir cortes do tipo 'EM UMA' / 'NOVA' ou finais em preposição.
    Pontuação e conectores recebem prioridade; cortes ruins ficam muito caros.
    """
    raw=re.sub(r'\s+', ' ', str(sentence or '')).strip()
    if not raw: return []
    tokens=_caption_words(raw)
    if len(tokens)<=max_words:
        return [tokens] if len(tokens)>=min_words else [tokens]
    norm=lambda w:_caption_clean_word(w)
    bad_end={'e','de','do','da','em','no','na','que','um','uma','o','a','os','as','para','com','por','mas','se','ou','ao','à','às','dos','das','num','numa','sobre','entre','até','sem','como','pelo','pela','pelos','pelas','porém','porem','então','entao'}
    bad_start={'e','mas','porque','porém','porem','então','entao','quando','enquanto','que','para','com','de','do','da','em','no','na'}
    preferred={'e','mas','porque','porém','porem','então','entao','quando','enquanto','porque'}
    protected={('gta','6'),('gta','vi'),('vice','city'),('cloud','gaming'),('xbox','cloud','gaming'),('playstation','5'),('xbox','series')}
    def protected_cut(cut):
        left=[norm(x) for x in tokens[max(0,cut-3):cut]]
        right=[norm(x) for x in tokens[cut:cut+3]]
        for ph in protected:
            n=len(ph)
            if len(left)>=n and tuple(left[-n:])==ph: return True
            if len(right)>=n and tuple(right[:n])==ph: return True
        return False
    out=[]; i=0
    while i<len(tokens):
        rem=len(tokens)-i
        if rem<=max_words:
            out.append(tokens[i:]); break
        lo=i+min_words
        hi=min(i+max_words, len(tokens)-min_words)
        best=None
        target=min(max_words, 6 if rem>=10 else 5)
        for cut in range(lo,hi+1):
            left=tokens[i:cut]; right=tokens[cut:]
            if not right: continue
            lw=norm(left[-1]); rw=norm(right[0])
            score=abs(len(left)-target)*2.0
            if re.search(r'[.!?;:]$', left[-1]): score-=30
            elif re.search(r'[,)]$', left[-1]): score-=12
            if lw in bad_end: score+=45
            if rw in bad_start: score+=32
            if rw in preferred: score-=8
            if protected_cut(cut): score+=80
            # Evita blocos visualmente curtos demais.
            if len(left)<min_words: score+=25
            if len(right)<min_words and rem>max_words+min_words: score+=25
            cand=(score,cut)
            if best is None or cand<best: best=cand
        cut=best[1] if best else min(i+target,len(tokens))
        out.append(tokens[i:cut]); i=cut
    # Último passe: junta um fragmento curto ao vizinho sem criar corte ruim.
    fixed=[]
    for ch in out:
        if fixed and len(ch)<min_words and len(fixed[-1])+len(ch)<=max_words:
            fixed[-1].extend(ch)
        else:
            fixed.append(ch)
    return fixed

def _caption_phrase_chunks(sentence, min_words=3, max_words=10):
    """V30 — divide by meaning and punctuation, preserving the complete spoken phrase."""
    raw=re.sub(r'\s+',' ',str(sentence)).strip()
    if not raw: return []
    tokens=_caption_words(raw)
    if len(tokens)<=max_words:
        return [tokens] if len(tokens)>=min_words else ([tokens] if tokens else [])

    def norm(w):
        return _caption_clean_word(w).lower()
    bad_end={'e','de','do','da','em','no','na','que','um','uma','o','a','os','as','para','com','por','mas','se','ou','ao','à','às','dos','das','num','numa','sobre','entre','até','sem','como','pelo','pela','pelos','pelas'}
    bad_start=bad_end | {'porque','porém','porem','então','entao','quando','enquanto'}
    connectors={'e','mas','porque','porém','porem','então','entao','quando','enquanto'}
    protected={
        ('gta','6'),('gta','vi'),('vice','city'),('cloud','gaming'),('xbox','cloud'),('xbox','cloud','gaming'),
        ('jason','e','lucia'),('nível','inédito','de','realismo'),('nivel','inedito','de','realismo'),
        ('sistema','de','moral'),('mecânica','de','relacionamento'),('mecanica','de','relacionamento'),
        ('playstation','5'),('xbox','series')
    }
    def protected_cut(cut):
        left=[norm(x) for x in tokens[max(0,cut-4):cut]]
        right=[norm(x) for x in tokens[cut:cut+4]]
        for ph in protected:
            n=len(ph)
            for i in range(len(left)-n+1):
                if tuple(left[i:i+n])==ph and i+n==len(left): return True
            for i in range(len(right)-n+1):
                if tuple(right[i:i+n])==ph and i==0: return True
        return False

    chunks=[]; i=0
    while i<len(tokens):
        rem=len(tokens)-i
        if rem<=max_words:
            chunks.append(tokens[i:]); break
        target=7 if rem>=15 else max(5,round(rem/2))
        lo=i+min_words
        hi=min(len(tokens)-1,i+max_words)
        candidates=[]
        for cut in range(lo,hi+1):
            left=tokens[i:cut]; right=tokens[cut:]
            if len(right)>0 and len(right)<min_words and rem>max_words+min_words: continue
            lw=norm(left[-1]); rw=norm(right[0]) if right else ''
            score=abs(len(left)-target)*1.4
            if re.search(r'[,:;.!?]$',left[-1]): score-=18
            if lw in bad_end: score+=35
            if rw in bad_start: score+=35
            if rw in connectors: score-=8
            if protected_cut(cut): score+=45
            if len(left)>=8: score+=1
            candidates.append((score,cut))
        cut=min(i+target,len(tokens)) if not candidates else min(candidates)[1]
        chunks.append(tokens[i:cut]); i=cut

    # Merge tiny chunks without crossing protected expressions.
    out=[]
    for ch in chunks:
        if not ch: continue
        if out and len(ch)<min_words and len(out[-1])+len(ch)<=max_words:
            out[-1].extend(ch)
        else: out.append(ch)
    return out


def _merge_caption_chunks(chunks, target_count=10, max_words=12):
    """Reduz a quantidade de blocos sem destruir unidades de sentido."""
    chunks=[list(c) for c in chunks if c]
    while len(chunks)>target_count:
        best_idx=None; best_score=None
        for i in range(len(chunks)-1):
            merged=chunks[i]+chunks[i+1]
            if len(merged)>max_words:
                continue
            score=abs(len(merged)-8)
            last=_caption_clean_word(chunks[i][-1])
            first=_caption_clean_word(chunks[i+1][0])
            if last in {'e','de','do','da','em','no','na','que','para','com','por','mas'}: score-=4
            if first in {'e','mas','porque','porém','porem','então','entao'}: score-=2
            if best_score is None or score<best_score:
                best_score=score; best_idx=i
        if best_idx is None:
            # Último recurso: funde o par mais próximo mesmo que fique um pouco maior.
            best_idx=min(range(len(chunks)-1), key=lambda i: abs(len(chunks[i])+len(chunks[i+1])-9))
        chunks[best_idx:best_idx+2]=[chunks[best_idx]+chunks[best_idx+1]]
    return chunks


def _cue_clean(w):
    return re.sub(r'\s+',' ',str(w or '')).strip()


def _cue_bad_end(w):
    return re.sub(r'[^A-Za-zÀ-ÿ]','',str(w or '')).lower() in {
        'e','de','do','da','em','no','na','que','um','uma','o','a','os','as','para','com','por','mas','se','ou','ao','à','às','dos','das','num','numa','sobre','entre','até','sem'
    }


def _cue_bad_start(w):
    return re.sub(r'[^A-Za-zÀ-ÿ]','',str(w or '')).lower() in {
        'e','mas','porque','porém','porem','então','entao','quando','enquanto','para','com','de','do','da','em','no','na','que'
    }


def _protected_pair(left,right):
    a=re.sub(r'[^a-z0-9à-ÿ]','',left.lower())
    b=re.sub(r'[^a-z0-9à-ÿ]','',right.lower())
    return (a,b) in {('gta','6'),('gta','vi'),('vice','city'),('cloud','gaming'),('xbox','cloud'),('xbox','cloud','gaming')}


def _build_timed_caption_beats(word_cues, duration, count=10):
    """V31: legendas derivadas dos WordBoundary reais do TTS, não de janelas estimadas."""
    cues=[c for c in (word_cues or []) if _cue_clean(c.get('word'))]
    if not cues:
        return []
    beats=[]; cur=[]
    max_words=7; min_words=3
    for i,c in enumerate(cues):
        cur.append(c)
        word=_cue_clean(c['word'])
        nextc=cues[i+1] if i+1<len(cues) else None
        punct=bool(re.search(r'[.!?;:]$',word))
        pause=(float(nextc['start'])-float(c['start'])) if nextc else 0
        need=False
        if len(cur)>=max_words: need=True
        if punct and len(cur)>=min_words: need=True
        if nextc and pause>=0.42 and len(cur)>=min_words: need=True
        # Não corta expressões importantes nem deixa preposição/conjunção isolada.
        if need and nextc:
            if _cue_bad_end(word) or _cue_bad_start(nextc['word']): need=False
            if _protected_pair(word,nextc['word']): need=False
        if need:
            beats.append(cur); cur=[]
    if cur: beats.append(cur)

    # Une blocos muito curtos sem apagar nenhuma palavra.
    merged=[]
    for b in beats:
        if merged and len(b)<min_words and len(merged[-1])+len(b)<=max_words:
            merged[-1].extend(b)
        else: merged.append(b)
    beats=merged

    # Se houver blocos demais, funde pares vizinhos somente quando o sentido e o tamanho permitem.
    while len(beats)>max(1,count):
        best=None
        for i in range(len(beats)-1):
            a,b=beats[i],beats[i+1]
            if len(a)+len(b)>max_words: continue
            score=abs((len(a)+len(b))-6)
            if _cue_bad_end(a[-1]['word']): score-=5
            if _cue_bad_start(b[0]['word']): score-=3
            gap=float(b[0]['start'])-float(a[-1]['start'])
            if gap<0.6: score-=2
            if best is None or score<best[0]: best=(score,i)
        if best is None: break
        i=best[1]; beats[i:i+2]=[beats[i]+beats[i+1]]

    out=[]
    for b in beats:
        text=' '.join(_cue_clean(x['word']) for x in b)
        text=_clean_caption_phrase(text)
        start=float(b[0]['start']); end=max(start+0.35,float(b[-1]['start'])+max(0.25,float(b[-1].get('duration',0.25))))
        end=min(duration,end)
        ws=re.findall(r"[A-Za-zÀ-ÿ0-9']+",text)
        preferred=[w for w in ws if w.lower() in {'gta','6','rockstar','jason','lucia','leonida','vice','city','cloud','gaming','xbox','realismo','novidades','microsoft'}]
        highlight=preferred[0] if preferred else (ws[-1] if len(ws)>=5 else None)
        out.append({'text':text,'highlight':highlight,'start':start,'end':end,'duration':max(0.35,end-start)})
    # Corrige gaps/overlaps e garante cobertura até o fim real da fala.
    for i in range(len(out)-1):
        out[i]['end']=min(out[i]['end'],out[i+1]['start'])
        out[i]['duration']=max(0.3,out[i]['end']-out[i]['start'])
    if out:
        out[-1]['end']=max(out[-1]['end'],min(duration,float(cues[-1]['start'])+float(cues[-1].get('duration',0.25))))
        out[-1]['end']=min(duration,out[-1]['end'])
        out[-1]['duration']=max(0.3,out[-1]['end']-out[-1]['start'])
    return out


def build_short_timeline(script, topic, duration, count=10, word_cues=None):
    """V31: se houver WordBoundary, usa timestamps reais da voz; caso contrário usa fallback editorial."""
    if word_cues:
        # Edge-TTS pode devolver timestamps que cobrem apenas parte do áudio.
        # Nesse caso, nunca estenda o último bloco até o fim do MP3 (isso cria
        # legendas repetidas + uma cena congelada). Só usamos timestamps reais
        # quando eles cobrem praticamente toda a narração.
        try:
            cues_ok=[c for c in (word_cues or []) if _cue_clean(c.get('word'))]
            last_end=0.0
            if cues_ok:
                last=cues_ok[-1]
                last_end=float(last.get('start',0))+float(last.get('duration',0.25))
            coverage=last_end/max(0.1,float(duration))
        except Exception:
            coverage=0.0
        if coverage>=0.82:
            timed=_build_timed_caption_beats(word_cues,duration,count)
            if timed: return timed
    narration=re.sub(r'\s+',' ',str(script.get('narration','')).strip())
    if not narration:
        return [{'text':'GTA 6','duration':duration,'highlight':'GTA','start':0,'end':duration}]
    sentences=[s.strip() for s in re.split(r'(?<=[.!?])\s+',narration) if s.strip()]
    all_chunks=[]
    for sent in sentences: all_chunks.extend(_semantic_caption_chunks(sent,3,7))
    if not all_chunks: all_chunks=[_caption_words(narration)]
    all_chunks=_merge_caption_chunks(all_chunks,target_count=max(1,count),max_words=9)
    phrases=[]
    for ch in all_chunks:
        phrase=_clean_caption_phrase(' '.join(ch))
        if phrase and len(re.findall(r"[A-Za-zÀ-ÿ0-9']+",phrase))>=2: phrases.append(phrase)
    if not phrases: phrases=[_clean_caption_phrase(narration)]
    weights=[max(2,len(re.findall(r"[A-Za-zÀ-ÿ0-9']+",p))) for p in phrases]
    total=sum(weights) or 1
    raw=[duration*w/total for w in weights]
    if len(raw)>1:
        raw=[max(1.25,min(4.8,x)) for x in raw]; scale=duration/sum(raw); raw=[x*scale for x in raw]
    beats=[]; t=0
    for phrase,d in zip(phrases,raw):
        ws=re.findall(r"[A-Za-zÀ-ÿ0-9']+",phrase); preferred=[w for w in ws if w.lower() in {'gta','rockstar','jason','lucia','leonida','vice','city','cloud','gaming','xbox','realismo','novidades'}]
        h=preferred[0] if preferred else (ws[-1] if len(ws)>=5 else None)
        beats.append({'text':phrase,'highlight':h,'duration':d,'start':t,'end':t+d}); t+=d
    return beats

def _beat_keywords(text, topic_title):
    blob=(str(text)+' '+str(topic_title)).lower()
    groups=[
        ('lucia',['lucia']),
        ('jason',['jason']),
        ('vice',['vice city','vice']),
        ('leonida',['leonida']),
        ('carro',['car','carro','veículo','veiculo','road','estrada']),
        ('noite',['night','noite','sunset']),
        ('mapa',['map','mapa','cidade','city']),
        ('rockstar',['rockstar','confirm','oficial']),
        ('gta',['gta 6','gta vi','gta'])
    ]
    return [name for name,ks in groups if any(k in blob for k in ks)]

def _asset_relevance(path, title, beat_text, kind):
    txt=(str(path)+' '+str(title)+' '+str(beat_text)).lower()
    score=0
    for k,v in [('jason',16),('lucia',16),('vice',12),('leonida',12),('car',7),('night',6),('map',7),('city',5),('rockstar',4),('gta',3)]:
        if k in txt: score+=v
    # Video filenames are more informative than generic image filenames.
    if kind=='video': score+=3
    return score

def _choose_timeline_assets(video_clips, image_paths, beats, topic_title, variant=0):
    """V56: schedule assets for retention, not just relevance.
    Uses every unique asset before reuse, enforces motion variety, and protects
    the final seconds from immediately repeating an early visual.
    """
    videos=[p for p in video_clips if p]
    images=[p for p in image_paths if p]
    pool=[('video',p) for p in videos]+[('image',p) for p in images]
    chosen=[]; used=set()

    def recent_penalty(p, bi):
        pen=0
        recent=[x[1] for x in chosen[-3:]]
        if p in recent:
            pen += 90
        if chosen and chosen[-1][0]=='image' and p in [x[1] for x in chosen[-2:]]:
            pen += 35
        if beats and bi >= max(0, int(len(beats)*0.80)) and p in [x[1] for x in chosen[:3]]:
            pen += 75
        return pen

    for bi,beat in enumerate(beats):
        remaining=[(idx,kind,p) for idx,(kind,p) in enumerate(pool) if idx not in used]
        candidates=remaining or [(idx,kind,p) for idx,(kind,p) in enumerate(pool)]
        ranked=[]
        for idx,kind,p in candidates:
            score=_asset_relevance(p,topic_title,beat.get('text',''),kind)
            if bi==0 and kind=='video':
                score += 35
            if bi>0 and chosen[-1][0] != kind:
                score += 12
            if bi % 2 == 0 and kind=='video':
                score += 9
            if bi % 2 == 1 and kind=='image':
                score += 5
            if bi >= max(0,int(len(beats)*0.75)) and kind=='video':
                score += 16
            if variant and idx % 4 == (bi+variant)%4:
                score += 10
            score -= recent_penalty(p,bi)
            ranked.append((score,kind,p,idx))
        ranked.sort(key=lambda x:x[0],reverse=True)
        _,kind,p,idx=ranked[0]
        chosen.append((kind,p))
        used.add(idx)

    # Protect the ending from immediately reusing one of the opening visuals.
    if len(chosen)>=6:
        early={chosen[0][1],chosen[1][1]}
        for j in range(max(0,len(chosen)-3),len(chosen)):
            if chosen[j][1] in early:
                limit=max(2, len(chosen)-3)
                for k in range(2,limit):
                    if chosen[k][1] not in early and chosen[k][1] != chosen[j][1]:
                        chosen[j],chosen[k]=chosen[k],chosen[j]
                        break
    return chosen

def _normalize_visual_beats(beats, duration, max_scene=3.2):
    """Garante que nenhuma cena visual fique longa demais.
    O texto só permanece no intervalo real da fala; gaps de áudio viram
    cenas de apoio sem repetir a última legenda.
    """
    src=list(beats or [])
    if not src:
        return [{'text':'','highlight':None,'start':0.0,'end':float(duration),'duration':float(duration),'captionless':True}]
    out=[]
    cursor=0.0
    for b in src:
        start=max(0.0,float(b.get('start',cursor)))
        end=min(float(duration),float(b.get('end',start+float(b.get('duration',1.0)))))
        if start>cursor+0.12:
            gap=start-cursor
            while gap>0.05:
                d=min(max_scene,gap)
                out.append({'text':'','highlight':None,'start':cursor,'end':cursor+d,'duration':d,'captionless':True})
                cursor+=d; gap-=d
        if end<=start: continue
        span=end-start
        pieces=max(1,int(__import__('math').ceil(span/max_scene)))
        d=span/pieces
        for i in range(pieces):
            a=start+i*d; z=end if i==pieces-1 else start+(i+1)*d
            out.append({'text':str(b.get('text','')) if i==0 else '',
                        'highlight':b.get('highlight') if i==0 else None,
                        'start':a,'end':z,'duration':max(0.35,z-a),
                        'captionless':i>0})
        cursor=end
    if cursor<float(duration)-0.05:
        gap=float(duration)-cursor
        while gap>0.05:
            d=min(max_scene,gap)
            out.append({'text':'','highlight':None,'start':cursor,'end':cursor+d,'duration':d,'captionless':True})
            cursor+=d; gap-=d
    return out


def make_multimedia_video(video_clips, image_paths, audio, out, duration, captions, script=None, topic_title='GTA 6', beats=None, motion_boost=False, asset_variant=0):
    # FFmpeg/yuv420p requires even width/height. Keep the Render Free
    # intermediate at an even 320x568 and upscale only at the final render.
    INTER_W, INTER_H = 320, 568
    if INTER_W % 2 or INTER_H % 2:
        raise RuntimeError(f'Dimensões intermediárias inválidas: {INTER_W}x{INTER_H}.')
    """V25 editor: narration-driven timeline, 12 short beats, real clips + images.
    Still optimized for Render Free by encoding one scene at a time.
    """
    ff=_ffmpeg_executable()
    work=out.parent/'timeline'; work.mkdir(exist_ok=True)
    if len(video_clips)<3:
        raise RuntimeError('A edição precisa de pelo menos 3 vídeos reais.')
    if script is None:
        script={'narration':' '.join(captions)}
    beats=beats or build_short_timeline(script, {'title':topic_title}, duration, count=10)
    # Nunca permita que uma legenda/beat de timestamps incompletos vire uma
    # cena final de 10–15s. A timeline visual é normalizada independentemente.
    beats=_normalize_visual_beats(beats,duration,max_scene=2.4)
    # Use todos os assets disponíveis; quando há poucos, o renderer aplica
    # enquadramentos diferentes em cada reutilização em vez de congelar a tela.
    imgs=list(image_paths)[:6]
    assets=_choose_timeline_assets(video_clips,imgs,beats,topic_title,variant=asset_variant)
    scene_files=[]
    for i,(beat,(kind,src)) in enumerate(zip(beats,assets)):
        scene=work/f'scene_{i:02d}.mp4'; overlay=work/f'overlay_{i:02d}.png'
        _caption_overlay(overlay,beat['text'],i,len(beats),320,568,beat.get('highlight'))
        if kind=='video':
            # Movimento leve em todas as cenas. Em reparos, aumenta a amplitude.
            amp=18 if motion_boost else 7
            vf=f"scale=340:604:force_original_aspect_ratio=increase,crop=320:568:x='10+{amp}*sin(n/18)':y='18+{max(4,amp//2)}*cos(n/23)',setsar=1,fps=15"
            inp=['-stream_loop','-1','-i',str(src)]
        else:
            zoom='0.006' if motion_boost else '0.002'
            vf=f"scale=320:568:force_original_aspect_ratio=increase,crop=320:568,setsar=1,zoompan=z='min(zoom+{zoom},1.06)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s=320x568:fps=15"
            inp=['-loop','1','-i',str(src)]
        cmd=[ff,'-loglevel','error','-y']+inp+['-loop','1','-i',str(overlay),'-t',f'{beat["duration"]:.3f}',
             '-filter_complex',f'[0:v]{vf}[v];[1:v]format=rgba[o];[v][o]overlay=0:0:shortest=1[outv]',
             '-map','[outv]','-an','-c:v','libx264','-preset','ultrafast','-crf','28',
             '-threads','1','-filter_threads','1','-filter_complex_threads','1',
             '-x264-params','threads=1:lookahead-threads=1','-pix_fmt','yuv420p','-movflags','+faststart',str(scene)]
        run_cmd(cmd,75)
        scene_files.append(scene)
        try: overlay.unlink()
        except Exception: pass
    listfile=work/'timeline.txt'
    with listfile.open('w',encoding='utf-8') as f:
        for sf in scene_files: f.write(f"file '{sf.as_posix()}'\n")
    run_cmd([ff,'-loglevel','error','-y','-f','concat','-safe','0','-i',str(listfile),'-i',str(audio),
             '-t',f'{duration:.2f}','-vf','scale=540:960:flags=lanczos,format=yuv420p','-r','15',
             '-c:v','libx264','-preset','ultrafast','-crf','26','-threads','1','-filter_threads','1','-filter_complex_threads','1',
             '-x264-params','threads=1:lookahead-threads=1','-c:a','aac','-b:a','128k',
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
    ff=_ffmpeg_executable()
    run_cmd([ff,'-y','-f','concat','-safe','0','-i',str(listfile),'-i',str(audio),
             '-t',f'{duration:.2f}','-r','24','-c:v','libx264','-preset','ultrafast',
             '-crf','22','-threads','2','-profile:v','high','-pix_fmt','yuv420p',
             '-c:a','aac','-b:a','128k','-movflags','+faststart','-shortest',str(out)],300)


def make_cover(scene,title,out):
    im=Image.open(scene).convert('RGB')
    im=im.resize((1080,1920),Image.Resampling.LANCZOS)
    d=ImageDraw.Draw(im,'RGBA')
    d.rectangle((45,500,1035,1330),fill=(0,0,0,175),outline=(225,25,45),width=5)
    f=font(72,True); y=610
    for line in wrap_text(d,title,f,880)[:6]:
        d.text((100,y),line,font=f,fill='white',stroke_width=2,stroke_fill='black'); y+=88
    d.text((100,120),'GTA OCULTO',font=font(30,True),fill=(255,255,255,180))
    im.save(out,quality=92)

def _load_learning():
    with LEARNING_LOCK:
        if not LEARNING_FILE.exists():
            return {'version':'V42.2','errors':{},'strategies':{},'experiments':[],'updated_at':now_iso()}
        try:
            d=json.loads(LEARNING_FILE.read_text(encoding='utf-8'))
            if not isinstance(d,dict): raise ValueError('learning inválido')
            d.setdefault('version','V41.3'); d.setdefault('errors',{}); d.setdefault('strategies',{}); d.setdefault('experiments',[])
            return d
        except Exception:
            return {'version':'V42.2','errors':{},'strategies':{},'experiments':[],'updated_at':now_iso()}

def _save_learning(data):
    data['updated_at']=now_iso()
    _atomic_write_json(LEARNING_FILE,data)

def _learn_event(code, message, strategy=None, success=None):
    try:
        with LEARNING_LOCK:
            d=_load_learning()
            e=d['errors'].setdefault(code,{'count':0,'last':'','messages':[]})
            e['count']=int(e.get('count',0))+1; e['last']=now_iso()
            msgs=e.setdefault('messages',[]); msgs.append(str(message)[:500]); e['messages']=msgs[-8:]
            if strategy:
                st=d['strategies'].setdefault(code,{'uses':0,'success':0,'last':'','strategy':strategy})
                st['uses']=int(st.get('uses',0))+1; st['last']=now_iso(); st['strategy']=strategy
                if success is True: st['success']=int(st.get('success',0))+1
            _save_learning(d)
    except Exception:
        pass

def _repair_caption_beats(beats, duration, max_words=7):
    """V55.3: reconstrução semântica das legendas usando somente as palavras já faladas.
    Em vez de apenas juntar blocos ruins, achata a fala existente, resegmenta por
    unidades de sentido e redistribui o tempo proporcionalmente. Isso elimina falsos
    positivos como blocos terminando em preposição/conjunção.
    """
    if not beats:
        return []

    # Preserva exatamente o texto que já veio da narração; não cria palavras novas.
    raw_parts=[re.sub(r'\s+',' ',str(b.get('text','')).strip()) for b in beats if str(b.get('text','')).strip()]
    full=' '.join(raw_parts).strip()
    if not full:
        return []

    # Recria frases a partir de pontuação quando ela ainda existir; caso contrário,
    # usa a segmentação semântica existente no motor.
    sentences=[x.strip() for x in re.split(r'(?<=[.!?;:])\s+',full) if x.strip()]
    chunks=[]
    for sent in sentences:
        chunks.extend(_semantic_caption_chunks(sent, min_words=3, max_words=max_words))
    if not chunks:
        chunks=[_caption_words(full)]

    # Corrige fragmentos e limita a quantidade de blocos sem alterar a sequência.
    chunks=[list(c) for c in chunks if c]
    fixed=[]
    for ch in chunks:
        if fixed and len(ch)<3 and len(fixed[-1])+len(ch)<=max_words:
            fixed[-1].extend(ch)
        else:
            fixed.append(ch)
    chunks=_merge_caption_chunks(fixed,target_count=max(1,min(10,len(fixed))),max_words=max_words+2)

    # Se uma fusão criou um limite ruim, tenta uma nova segmentação global.
    bad_end={'e','de','do','da','em','no','na','que','um','uma','o','a','os','as','para','com','por','mas','se','ou','ao','à','às','dos','das','num','numa','sobre','entre','até','sem'}
    bad_start={'e','mas','porque','porém','porem','então','entao','quando','enquanto','para','com','de','do','da','em','no','na','que'}
    for i in range(len(chunks)-1):
        last=_caption_clean_word(chunks[i][-1]); first=_caption_clean_word(chunks[i+1][0])
        if (last in bad_end or first in bad_start) and len(chunks[i])+len(chunks[i+1])<=max_words+2:
            chunks[i:i+2]=[chunks[i]+chunks[i+1]]
            break

    # Intervalo temporal coberto pelos beats originais.
    start_time=float(beats[0].get('start',0.0))
    end_time=min(float(duration), max(float(b.get('end',0.0)) for b in beats))
    if end_time<=start_time:
        start_time=0.0; end_time=float(duration)
    span=max(0.5,end_time-start_time)
    weights=[max(1,len(c)) for c in chunks]
    total=sum(weights) or 1

    out=[]; cursor=start_time
    for i,ch in enumerate(chunks):
        d=span*(weights[i]/total)
        ce=end_time if i==len(chunks)-1 else cursor+d
        text=_clean_caption_phrase(' '.join(ch))
        if not text: continue
        ws=re.findall(r"[A-Za-zÀ-ÿ0-9']+",text)
        preferred=[w for w in ws if w.lower() in {'gta','6','rockstar','jason','lucia','leonida','vice','city','cloud','gaming','xbox','realismo','novidades','microsoft'}]
        highlight=preferred[0] if preferred else (ws[-1] if len(ws)>=5 else None)
        out.append({'text':text,'highlight':highlight,'start':cursor,'end':ce,'duration':max(0.3,ce-cursor)})
        cursor=ce

    # Sem sobreposição e cobertura final estável.
    for i in range(len(out)-1):
        out[i]['end']=min(out[i]['end'],out[i+1]['start'])
        out[i]['duration']=max(0.3,out[i]['end']-out[i]['start'])
    if out:
        out[-1]['end']=min(float(duration),max(out[-1]['end'],end_time))
        out[-1]['duration']=max(0.3,out[-1]['end']-out[-1]['start'])
    return out

def _caption_visual_split_quality(text, W=320):
    """Score 2-line visual balance using the exact caption font."""
    d=ImageDraw.Draw(Image.new('RGBA',(W,120),(0,0,0,0)))
    f=font(24,True)
    words=str(text or '').split()
    if len(words)<=4: return {'score':100,'lines':[' '.join(words)]}
    max_width=W-42
    candidates=[]
    for cut in range(2,len(words)-1):
        a=' '.join(words[:cut]); b=' '.join(words[cut:])
        wa=d.textbbox((0,0),a,font=f,stroke_width=1)[2]
        wb=d.textbbox((0,0),b,font=f,stroke_width=1)[2]
        if wa<=max_width and wb<=max_width:
            candidates.append((abs(wa-wb)+abs(cut-(len(words)-cut))*18,cut,a,b))
    if not candidates:
        return {'score':65,'lines':[str(text).upper()]}
    _,cut,a,b=min(candidates,key=lambda x:x[0])
    score=100
    if len(b.split())==1: score-=30
    if len(a.split())==1: score-=20
    return {'score':max(0,score),'lines':[a.upper(),b.upper()]}

def _audit_caption_quality(beats):
    bad_end=[]; bad_start=[]; long=[]; short=[]; visual_bad=[]
    bad_end_set={'e','de','do','da','em','no','na','que','um','uma','o','a','os','as','para','com','por','mas','se','ou','ao','à','às','dos','das','num','numa','sobre','entre','até','sem'}
    bad_start_set={'e','mas','porque','porém','porem','então','entao','quando','enquanto','para','com','de','do','da','em','no','na','que'}
    for b in beats or []:
        words=_caption_words(b.get('text',''))
        if not words: continue
        if _caption_clean_word(words[-1]) in bad_end_set: bad_end.append(b['text'])
        if _caption_clean_word(words[0]) in bad_start_set: bad_start.append(b['text'])
        if len(words)>7: long.append(b['text'])
        if len(words)<2: short.append(b['text'])
        vs=_caption_visual_split_quality(b.get('text',''))
        if vs['score']<85: visual_bad.append({'text':b.get('text',''),'lines':vs['lines']})
    total=max(1,len(beats or []))
    texts=[re.sub(r'\s+',' ',str(b.get('text','')).strip().lower()) for b in (beats or []) if str(b.get('text','')).strip()]
    repeated_adj=sum(1 for i in range(1,len(texts)) if texts[i] and texts[i]==texts[i-1])
    repeated_total=max(0,len(texts)-len(set(texts))) if texts else 0
    # V55.5: semantic boundary is independent from visual line balance.
    # A caption ending in a preposition is a warning; it is not by itself a production blocker.
    boundary_penalty=min(28, len(bad_end)*2 + len(bad_start)*2)
    penalty=min(65,boundary_penalty + len(long)*3 + len(short)*2 + len(visual_bad)*3 + repeated_adj*8 + repeated_total*3)
    return {
        'score':max(0,100-penalty),
        'bad_end':bad_end,'bad_start':bad_start,'long':long,'short':short,
        'visual_bad':visual_bad,'repeated_adjacent':repeated_adj,'repeated_total':repeated_total
    }


def _probe_media(path):
    ff=shutil.which('ffprobe') or 'ffprobe'
    try:
        cmd=[ff,'-v','error','-show_entries','format=duration,size:stream=index,codec_type,width,height,codec_name','-of','json',str(path)]
        out=subprocess.check_output(cmd,stderr=subprocess.DEVNULL,text=True,timeout=30)
        d=json.loads(out); streams=d.get('streams',[]); fmt=d.get('format',{})
        video=[x for x in streams if x.get('codec_type')=='video']; audio=[x for x in streams if x.get('codec_type')=='audio']
        return {'ok':True,'duration':float(fmt.get('duration') or 0),'size':int(fmt.get('size') or 0),'video':video,'audio':audio}
    except Exception as e:
        return {'ok':False,'error':str(e)[:500]}

def _visual_motion_audit(path):
    """Audita o MP4 real em baixa resolução para detectar congelamento/repetição visual.
    Não usa análise semântica: mede mudança real entre amostras do vídeo.
    """
    tmp=Path(str(path)+'.motion_audit')
    tmp.mkdir(parents=True,exist_ok=True)
    try:
        ff=_ffmpeg_executable()
        # 1 frame/s é suficiente para encontrar congelamentos longos sem pesar no Render.
        run_cmd([ff,'-loglevel','error','-y','-i',str(path),'-vf','fps=1,scale=80:142:flags=bilinear,format=gray',str(tmp/'frame_%04d.jpg')],45)
        frames=sorted(tmp.glob('frame_*.jpg'))
        if len(frames)<5:
            return {'score':60,'frozen_ratio':0.0,'longest_still_seconds':0.0,'sample_count':len(frames),'stale_runs':[],'error':'amostras insuficientes'}
        prev=None; diffs=[]
        for fp in frames:
            try:
                im=Image.open(fp).convert('L')
                if prev is not None:
                    diff=ImageChops.difference(prev,im)
                    stat=ImageStat.Stat(diff)
                    diffs.append(float(stat.mean[0]))
                prev=im
            except Exception:
                continue
        # Em material H.264, valores abaixo de ~1.6 por vários segundos indicam quadro visualmente parado.
        threshold=1.6
        stale_runs=[]; run=0; start=0
        for i,d in enumerate(diffs):
            if d<threshold:
                if run==0: start=i
                run+=1
            else:
                if run>=4: stale_runs.append({'start_s':start+1,'end_s':start+run+1,'duration_s':run})
                run=0
        if run>=4: stale_runs.append({'start_s':start+1,'end_s':start+run+1,'duration_s':run})
        longest=max([r['duration_s'] for r in stale_runs] or [0])
        frozen=sum(1 for d in diffs if d<threshold)/max(1,len(diffs))
        score=100
        if longest>=10: score-=55
        elif longest>=7: score-=42
        elif longest>=5: score-=30
        elif longest>=4: score-=18
        if frozen>0.55: score-=25
        elif frozen>0.40: score-=15
        elif frozen>0.28: score-=8
        score=max(0,min(100,score))
        return {'score':score,'frozen_ratio':round(frozen,3),'longest_still_seconds':longest,'sample_count':len(frames),'stale_runs':stale_runs[:8],'threshold':threshold}
    except Exception as e:
        return {'score':75,'frozen_ratio':0.0,'longest_still_seconds':0.0,'sample_count':0,'stale_runs':[],'error':str(e)[:400]}
    finally:
        try: shutil.rmtree(tmp,ignore_errors=True)
        except Exception: pass

def _caption_narration_alignment(beats, narration):
    """V55.8: validate captions against the *ordered narration sequence*.
    The old multiset check could falsely reject valid captions when a spoken
    word appeared more than once or when the caption engine skipped words.
    Captions must be composed only of narration words, in spoken order, while
    allowing omitted narration words between caption chunks.
    """
    def toks(s):
        raw=re.findall(r"[A-Za-zÀ-ÿ0-9']+", str(s or '').lower())
        return [re.sub(r'[^a-z0-9à-ÿ]', '', w) for w in raw if re.sub(r'[^a-z0-9à-ÿ]', '', w)]

    n=toks(narration)
    if not n:
        return {'score':0,'bad':[],'coverage':0.0,'foreign_ratio':1.0,'caption_count':0}

    # Normalize common typographic variants without changing words.
    aliases={'gta6':'gta', 'gtavi':'gta'}
    def norm(w): return aliases.get(w,w)
    n_norm=[norm(w) for w in n]

    bad=[]; total=0; foreign=0; cursor=0; matched=0
    max_skip=14
    for b in beats or []:
        text=str(b.get('text','')).strip()
        ct=[norm(w) for w in toks(text)]
        total += len(ct)
        if not ct: continue
        local_bad=[]
        for w in ct:
            # Find the next occurrence in the narration after the previous
            # matched token. We permit omitted spoken words between captions.
            found=None
            upper=min(len(n_norm), cursor+max_skip+1)
            for j in range(cursor, upper):
                if n_norm[j]==w:
                    found=j; break
            if found is None:
                # A word can legitimately recur after a larger gap; search the
                # rest of the narration before declaring it foreign.
                for j in range(cursor, len(n_norm)):
                    if n_norm[j]==w:
                        found=j; break
            if found is None:
                local_bad.append(w); foreign += 1
            else:
                matched += 1
                cursor=found+1
        if local_bad:
            bad.append({'text':text,'words':local_bad})

    coverage=matched/max(1,total)
    foreign_ratio=foreign/max(1,total)
    score=100
    if foreign_ratio>0.15: score-=50
    elif foreign_ratio>0.08: score-=35
    elif foreign_ratio>0.03: score-=20
    elif foreign_ratio>0: score-=8
    if bad and any(len(x['words'])>=3 for x in bad): score-=20

    return {
        'score':max(0,min(100,score)),
        'bad':bad[:12],
        'coverage':round(coverage,3),
        'foreign_ratio':round(foreign_ratio,3),
        'caption_count':len([b for b in beats or [] if str(b.get('text','')).strip()])
    }


def _visual_repetition_audit(path):
    """V52: detect repeated shots as SEQUENCES, not isolated similar frames.
    Two-second sampling + multi-frame sequence comparison catches a reused shot
    even when the camera/person keeps moving inside that shot.
    """
    tmp=Path(str(path)+'.repeat_audit')
    tmp.mkdir(parents=True,exist_ok=True)
    try:
        ff=_ffmpeg_executable()
        run_cmd([ff,'-loglevel','error','-y','-i',str(path),'-vf','fps=2,scale=48:85:flags=bilinear,format=gray',str(tmp/'f_%04d.jpg')],60)
        frames=sorted(tmp.glob('f_*.jpg'))
        if len(frames)<12:
            return {'score':70,'repeated_ratio':0.0,'longest_repeat_s':0.0,'pairs':[],'error':'amostras insuficientes'}
        imgs=[]
        for fp in frames:
            try: imgs.append(Image.open(fp).convert('L').resize((48,85)))
            except Exception: pass
        # Compare 3-second windows (6 samples) separated by at least 4 seconds.
        seq_len=6; min_gap=8; matches=[]
        for i in range(0,max(1,len(imgs)-seq_len+1)):
            for j in range(i+min_gap, max(i+min_gap, len(imgs)-seq_len+1)):
                ds=[]
                for k in range(seq_len):
                    stat=ImageStat.Stat(ImageChops.difference(imgs[i+k],imgs[j+k]))
                    ds.append(float(stat.mean[0]))
                avg=sum(ds)/len(ds)
                if avg<8.0:
                    matches.append((i,j,avg))
        # Merge matched windows into approximate repeated time coverage.
        marks=set()
        for i,j,d in matches:
            for k in range(seq_len): marks.add(i+k); marks.add(j+k)
        ratio=len(marks)/max(1,len(imgs))
        # Longest contiguous marked run, allowing one-sample gap.
        longest=0; cur=0
        for k in range(len(imgs)):
            if k in marks: cur+=1; longest=max(longest,cur)
            else: cur=0
        longest_s=longest/2.0
        score=100
        if ratio>=0.45: score-=45
        elif ratio>=0.30: score-=32
        elif ratio>=0.20: score-=20
        elif ratio>=0.12: score-=10
        if longest_s>=8: score-=40
        elif longest_s>=6: score-=30
        elif longest_s>=4: score-=18
        return {'score':max(0,min(100,score)),'repeated_ratio':round(ratio,3),'longest_repeat_s':round(longest_s,1),'pairs':[{'a_s':round(i/2,1),'b_s':round(j/2,1),'diff':round(d,2)} for i,j,d in matches[:12]],'sequence_window_s':3.0}
    except Exception as e:
        return {'score':65,'repeated_ratio':0.0,'longest_repeat_s':0.0,'pairs':[],'error':str(e)[:400]}
    finally:
        try: shutil.rmtree(tmp,ignore_errors=True)
        except Exception: pass

def audit_short(script, video, duration, beats, selected_videos, image_scenes):
    """Auditor V41: checks editorial, captions and actual MP4 before delivery."""
    issues=[]; checks={}
    narration=str(script.get('narration',''))
    words=len(re.findall(r"[A-Za-zÀ-ÿ0-9']+",narration))
    checks['roteiro']=100 if words>=70 and script.get('evidence') else 0
    if any(x in narration.lower() for x in ('radar','editor-chefe','score','confiança','fontes','matérias','produzir agora')):
        checks['roteiro']=0; issues.append(('EDITORIAL_METADATA','roteiro contém metadado interno'))
    if _editorial_noise_score(narration,str(script.get('title','')))>2:
        checks['roteiro']=max(0,checks['roteiro']-20)
        issues.append(('HEADLINE_CONTAMINATION','narração contém padrão de manchete ou metadado'))
    evidence=script.get('evidence') or []
    if not evidence:
        issues.append(('NO_EVIDENCE','roteiro sem evidência factual'))
        checks['roteiro']=0
    cap=_audit_caption_quality(beats); checks['legendas']=cap['score']
    alignment=_caption_narration_alignment(beats,narration); checks['alinhamento_legendas']=alignment['score']
    boundary_bad_count=len(cap.get('bad_end',[]))+len(cap.get('bad_start',[]))
    # V55.5: only actual semantic boundary violations can trigger this issue.
    # Visual wrapping, caption length and line balance are quality signals, not semantic-boundary failures.
    boundary_severe=(boundary_bad_count>=max(4,int(len(beats or [])*0.55)))
    if boundary_severe: issues.append(('CAPTIONS_BAD_BOUNDARY','legendas com cortes semanticamente ruins'))
    if alignment.get('foreign_ratio',0)>0.03 or alignment.get('score',100)<85:
        issues.append(('CAPTIONS_NOT_FROM_NARRATION',f'legendas contêm palavras fora da narração: {alignment.get("foreign_ratio",0)*100:.0f}%'))
    if cap.get('repeated_adjacent',0)>0: issues.append(('CAPTIONS_REPEATED','legenda repetida em blocos consecutivos'))
    media=_probe_media(video); checks['mp4']=100 if media.get('ok') else 0
    if not media.get('ok'): issues.append(('MEDIA_UNREADABLE',media.get('error','MP4 inválido')))
    else:
        dur=media['duration']; v=media['video']; a=media['audio']
        if not v: checks['mp4']-=50; issues.append(('NO_VIDEO_STREAM','MP4 sem vídeo'))
        if not a: checks['mp4']-=50; issues.append(('NO_AUDIO_STREAM','MP4 sem áudio'))
        if v and (int(v[0].get('width',0))!=540 or int(v[0].get('height',0))!=960):
            checks['mp4']-=15; issues.append(('WRONG_ASPECT','vídeo final não está em 540x960'))
        if abs(dur-float(duration))>1.5: checks['mp4']-=10; issues.append(('DURATION_DRIFT',f'duração final {dur:.2f}s vs áudio {duration:.2f}s'))
        if media['size']<150000: checks['mp4']-=15; issues.append(('TINY_OUTPUT','MP4 suspeito: arquivo muito pequeno'))
    checks['visuais']=100
    unique=len({str(x) for x in selected_videos})
    if unique<4: checks['visuais']-=15; issues.append(('LOW_VIDEO_VARIETY',f'apenas {unique} clipes únicos'))
    if len(image_scenes)<4: checks['visuais']-=5; issues.append(('LOW_IMAGE_VARIETY','poucas imagens auxiliares'))
    motion=_visual_motion_audit(video) if media.get('ok') else {'score':0,'error':'MP4 inválido'}
    checks['movimento']=int(motion.get('score',0))
    repetition=_visual_repetition_audit(video) if media.get('ok') else {'score':0,'error':'MP4 inválido'}
    checks['repeticao_visual']=int(repetition.get('score',0))
    if motion.get('longest_still_seconds',0)>=4:
        issues.append(('VISUAL_STAGNATION',f'visual praticamente parado por {motion.get("longest_still_seconds",0):.0f}s'))
    if motion.get('frozen_ratio',0)>=0.40:
        issues.append(('HIGH_FROZEN_RATIO',f'{motion.get("frozen_ratio",0)*100:.0f}% das transições amostradas com pouca mudança visual'))
    if repetition.get('repeated_ratio',0)>=0.28 or repetition.get('longest_repeat_s',0)>=4:
        issues.append(('VISUAL_REPETITION',f'repetição visual detectada: {repetition.get("repeated_ratio",0)*100:.0f}% das amostras / trecho repetido até {repetition.get("longest_repeat_s",0):.1f}s'))
    final=max(0,round((checks['roteiro']+checks['legendas']+checks['alinhamento_legendas']+checks['mp4']+checks['visuais']+checks['movimento']+checks['repeticao_visual'])/7))
    return {'score':final,'checks':checks,'issues':[{'code':c,'message':m} for c,m in issues],'media':media,'caption_audit':cap,'motion_audit':motion,'repetition_audit':repetition}

def self_heal(jid, script, video, duration, beats, selected_videos, image_scenes, topic, audio):
    """Run bounded safe repairs. No endless retry and no self-modifying source code."""
    audit=audit_short(script,video,duration,beats,selected_videos,image_scenes)
    if audit['score']>=92 and not any(x['code'] in {'CAPTIONS_NOT_FROM_NARRATION','VISUAL_REPETITION','VISUAL_STAGNATION','HIGH_FROZEN_RATIO'} for x in audit.get('issues',[])): return audit,beats,False
    repaired=False
    codes={x['code'] for x in audit['issues']}
    if 'VISUAL_STAGNATION' in codes or 'HIGH_FROZEN_RATIO' in codes or 'VISUAL_REPETITION' in codes:
        _learn_event('VISUAL_REPETITION','auditor detectou repetição/congelamento visual', 'testar múltiplas timelines com cenas curtas, ordem alternativa e movimento aumentado', None)
        update_job(jid,stage='AUTO-CORREÇÃO',progress=94,log='🧠 AUDITOR IA: visual repetitivo/congelado detectado. Testando variações de timeline automaticamente...')
        base_score=audit.get('score',0)
        best=None
        variants=[]
        if selected_videos: variants.append((list(reversed(selected_videos)), list(reversed(image_scenes)), 1))
        if selected_videos: variants.append((selected_videos[1:]+selected_videos[:1], image_scenes[1:]+image_scenes[:1], 2))
        if selected_videos: variants.append((selected_videos[::2]+selected_videos[1::2], image_scenes[::2]+image_scenes[1::2], 3))
        for attempt,(alt_videos,alt_images,variant) in enumerate(variants,1):
            video2=video.with_name(f'GTA_OCULTO_SHORT_VISUAL_REPAIR_{attempt}.mp4')
            try:
                make_multimedia_video(alt_videos,alt_images,audio,video2,duration,[b.get('text','') for b in beats],script,topic['title'],beats,motion_boost=True,asset_variant=variant)
                audit2=audit_short(script,video2,duration,beats,alt_videos,alt_images)
                if best is None or audit2.get('score',0)>best[0]:
                    best=(audit2.get('score',0),audit2,video2,alt_videos,alt_images)
                if audit2.get('score',0)>=90 and audit2.get('score',0)>base_score:
                    break
            except Exception as e:
                _learn_event('VISUAL_REPAIR_ERROR',f'variação {attempt} falhou: {e}',f'asset_variant={variant}',False)
                try: video2.unlink()
                except Exception: pass
        if best and best[0]>base_score:
            _,audit2,video2,alt_videos,alt_images=best
            os.replace(video2,video); selected_videos[:]=alt_videos; image_scenes[:]=alt_images; audit=audit2; repaired=True
            _learn_event('VISUAL_REPETITION','reparo visual concluído com melhor variante', 'múltiplas timelines + movimento aumentado', True)
        else:
            for attempt in range(1,len(variants)+1):
                try:
                    q=video.with_name(f'GTA_OCULTO_SHORT_VISUAL_REPAIR_{attempt}.mp4')
                    if q.exists(): q.unlink()
                except Exception: pass
            _learn_event('VISUAL_REPETITION','nenhuma variante melhorou o score', 'bloquear publicação para evitar Short visualmente ruim', False)
    if any(x['code'] in {'CAPTIONS_BAD_BOUNDARY','CAPTIONS_REPEATED','CAPTIONS_NOT_FROM_NARRATION'} for x in audit['issues']):
        _learn_event('CAPTIONS_BAD_BOUNDARY','auditor detectou cortes semânticos/visuais', 'resegmentar captions e equilibrar quebra de linha', None)
        new_beats=_repair_caption_beats(beats,duration,6)
        if new_beats and new_beats!=beats:
            update_job(jid,stage='AUTO-CORREÇÃO',progress=94,log='🧠 AUDITOR IA: legendas abaixo do padrão. Recalculando cortes semânticos e renderizando novamente...')
            caps=[b['text'] for b in new_beats]
            video2=video.with_name('GTA_OCULTO_SHORT_REPAIRED.mp4')
            make_multimedia_video(selected_videos,image_scenes,audio,video2,duration,caps,script,topic['title'],new_beats)
            os.replace(video2,video)
            audit2=audit_short(script,video,duration,new_beats,selected_videos,image_scenes)
            _learn_event('CAPTIONS_BAD_BOUNDARY','reparo de legendas concluído', 'resegmentar captions preservando fala', audit2['score']>=audit['score'])
            repaired=True; beats=new_beats; audit=audit2
            # V55.3: uma segunda passada só é feita se ainda houver bloqueio de legenda.
            if any(x.get('code') in {'CAPTIONS_BAD_BOUNDARY','CAPTIONS_REPEATED','CAPTIONS_NOT_FROM_NARRATION'} for x in audit.get('issues',[])):
                retry=_repair_caption_beats(beats,duration,7)
                if retry and retry!=beats:
                    video3=video.with_name('GTA_OCULTO_SHORT_REPAIRED_2.mp4')
                    make_multimedia_video(selected_videos,image_scenes,audio,video3,duration,[b['text'] for b in retry],script,topic['title'],retry)
                    audit3=audit_short(script,video3,duration,retry,selected_videos,image_scenes)
                    if audit3.get('score',0)>=audit.get('score',0) and not any(x.get('code') in {'CAPTIONS_BAD_BOUNDARY','CAPTIONS_REPEATED','CAPTIONS_NOT_FROM_NARRATION'} for x in audit3.get('issues',[])):
                        os.replace(video3,video); beats=retry; audit=audit3
                    else:
                        try: video3.unlink(missing_ok=True)
                        except Exception: pass
    return audit,beats,repaired

def evaluate(script,duration,scene_count,visual_quality,beats=None,video_count=0,image_count=0):
    """V25 quality gate: checks pacing, caption density, visual variety and hook."""
    score=100
    narration=str(script.get('narration','')).strip()
    words=re.findall(r"[A-Za-zÀ-ÿ0-9']+",narration)
    if duration<24 or duration>38: score-=7
    if len(words)<70: score-=8
    if '?' not in narration[:210]: score-=4
    if scene_count<10: score-=10
    if scene_count<10: score-=4
    if video_count<4: score-=8
    if image_count<4: score-=4
    if visual_quality<60: score-=12
    elif visual_quality<70: score-=7
    elif visual_quality<80: score-=3
    if beats:
        avg=sum(b.get('duration',0) for b in beats)/max(1,len(beats))
        if avg>3.3: score-=5
        if avg<1.9: score-=3
        # Penalize very long caption phrases.
        long_caps=sum(1 for b in beats if len(str(b.get('text','')).split())>6)
        score-=min(8,long_caps*2)
    return max(0,min(100,score))

def produce_job(jid):
    global PROCESSING
    try:
        update_job(jid,status='RUNNING',stage='PESQUISA',progress=5,log='Radar validando o assunto e coletando fontes oficiais...')
        topics,urls,_=research_official(); topics=topics or FALLBACK_TOPICS
        job=load_jobs()[jid]; topic=editor_chief_select([job['opportunity']]) or job['opportunity']; job['opportunity']=topic; jobs=load_jobs(); jobs[jid]['opportunity']=topic; save_jobs(jobs)
        update_job(jid,stage='ANÁLISE',progress=16,log=f'EDITOR-CHEFE: {topic.get("editorial_decision","PRODUZIR")} — {topic["title"]} | ângulo: {topic.get("editorial_angle","")}')
        update_job(jid,stage='ROTEIRO',progress=28,log='EDITOR-CHEFE → AGENTE AUTÔNOMO: validando corpo original, tentando estratégias e recuperando a pauta se necessário...')
        topic, script = _autonomous_make_script(jid, topic, topics)
        # Keep the rest of the proven rendering pipeline synchronized with the
        # topic actually selected by the autonomous recovery agent.
        job=load_jobs().get(jid,{})
        job['opportunity']=topic
        job['title']=topic.get('title',job.get('title','GTA 6'))
        jobs=load_jobs(); jobs[jid]=job; save_jobs(jobs)
        jobdir=WORK/jid; jobdir.mkdir(parents=True,exist_ok=True)
        update_job(jid,script=script,stage='VISUAIS',progress=40,log='Baixando visuais oficiais e montando cenas verticais...')
        paths=download_visuals(urls,jobdir/'visuals',topic['title'])
        image_order=select_visuals(paths,topic['title'],6)
        image_scenes=[]
        # A preparação visual não queima a legenda; o overlay final é desenhado
        # somente depois que temos a duração real da narração.
        for i,src in enumerate(image_order):
            dst=jobdir/f'image_{i}.jpg'; prepare_scene(src,dst,'',i,10); image_scenes.append(dst)
        update_job(jid,stage='NARRAÇÃO',progress=60,log='Gerando narração PT-BR e capturando timestamps reais da fala...'); audio=jobdir/'narracao.mp3'; word_cues=asyncio.run(make_tts(script['narration'],audio)); duration=duration_of_audio(audio)
        (jobdir/'word_cues.json').write_text(json.dumps(word_cues,ensure_ascii=False,indent=2),encoding='utf-8')
        beats=build_short_timeline(script,topic,duration,10,word_cues=word_cues)
        caps=[b['text'] for b in beats]
        sync_mode='timestamps reais do Edge-TTS' if word_cues else 'fallback editorial pela duração real do áudio'
        update_job(jid,progress=66,log=f'Narração pronta: {script.get("word_count",0)} palavras / {duration:.1f}s. Legendas em {len(beats)} blocos — {sync_mode}.')
        update_job(jid,stage='EDIÇÃO',progress=74,log=f'Obtendo vídeos oficiais da Rockstar e montando timeline com movimento real / {duration:.1f}s...')
        official_videos=download_official_video_clips(jobdir/'official_videos', jid)
        selected_videos=select_video_clips(official_videos,topic['title'],6)
        update_job(jid,log=f'{len(selected_videos)} vídeos oficiais disponíveis. Editando cortes reais em 9:16 / {duration:.1f}s...')
        video=jobdir/'GTA_OCULTO_SHORT.mp4'; make_multimedia_video(selected_videos,image_scenes,audio,video,duration,caps,script,topic['title'],beats)
        # Nunca deixe a capa derrubar uma produção já renderizada.
        if not image_scenes:
            fallback_cover=jobdir/'cover_fallback.jpg'
            make_fallback(fallback_cover,0,topic['title'])
            image_scenes=[fallback_cover]
        cover=jobdir/'CAPA.jpg'; make_cover(image_scenes[0],topic['title'],cover)
        update_job(jid,stage='AVALIAÇÃO',progress=92,log='Avaliando hook, ritmo, visuais, duração e sincronização real das legendas...'); visual_quality=100
        for sp in image_scenes:
            q=_image_quality(sp); visual_quality=min(visual_quality, max(0,q))
        # V41: auditor automático examina o MP4 real e tenta correções seguras antes do gate final.
        audit,beats,repaired=self_heal(jid,script,video,duration,beats,selected_videos,image_scenes,topic,audio)

        # V42: second independent bounded audit. It never replaces the proven
        # V41.3 renderer; it only gets one safe caption-repair attempt when the
        # independent audit detects weak caption segmentation.
        v42_audit = None
        if v42_full_audit:
            try:
                v42_audit = v42_full_audit(video, [b.get('text','') for b in beats], script.get('narration',''))
                if v42_audit.get('caption',{}).get('score',100) < 85 and v42_repair_captions:
                    repaired_caps = v42_repair_captions([b.get('text','') for b in beats], script.get('narration',''), target=max(6,min(10,len(beats) or 9)))
                    if repaired_caps and repaired_caps != [b.get('text','') for b in beats]:
                        repaired_beats=[]
                        n=min(len(repaired_caps),len(beats))
                        for i,c in enumerate(repaired_caps[:n]):
                            b=dict(beats[i]); b['text']=c; repaired_beats.append(b)
                        if repaired_beats:
                            video2=video.with_name('GTA_OCULTO_SHORT_V42_REPAIRED.mp4')
                            make_multimedia_video(selected_videos,image_scenes,audio,video2,duration,[b['text'] for b in repaired_beats],script,topic['title'],repaired_beats)
                            va2=v42_full_audit(video2,[b['text'] for b in repaired_beats],script.get('narration',''))
                            # V55.9: never accept an independent caption repair if it
                            # introduces words that are not present in the actual narration.
                            # The previous V42 repair could improve visual segmentation while
                            # silently introducing foreign/metadata text, which then caused the
                            # final strict caption gate to block the whole production.
                            va2_align = _caption_narration_alignment(repaired_beats, script.get('narration',''))
                            va2_safe = (va2_align.get('foreign_ratio', 1.0) <= 0.03 and
                                        va2_align.get('score', 0) >= 85)
                            if va2.get('score',0) >= v42_audit.get('score',0) and va2_safe:
                                os.replace(video2,video); beats=repaired_beats; repaired=True; v42_audit=va2
                            elif video2.exists():
                                video2.unlink()
                                if not va2_safe:
                                    v42_audit.setdefault('notes',[]).append('V55.9: reparo V42 descartado por desalinhamento com a narração.')
            except Exception as _v42e:
                v42_audit={'score':None,'error':str(_v42e)[:500]}

        score=evaluate(script,duration,len(beats),visual_quality,beats,len(selected_videos),len(image_scenes))
        score=min(score,audit.get('score',score))
        if v42_audit and isinstance(v42_audit.get('score'),(int,float)):
            score=min(score,int(v42_audit['score']))
        audit['v42_independent']=v42_audit
        (jobdir/'audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
        update_job(jid,stage='AVALIAÇÃO',progress=96,log=f'🧠 AUDITOR IA: {audit.get("score",0)}/100 | reparo automático: {"SIM" if repaired else "NÃO"} | problemas: {len(audit.get("issues",[]))}.')
        hard_issues={
            'CAPTIONS_NOT_FROM_NARRATION','CAPTIONS_BAD_BOUNDARY','CAPTIONS_REPEATED',
            'VISUAL_REPETITION','VISUAL_STAGNATION','HIGH_FROZEN_RATIO','MEDIA_UNREADABLE',
            'NO_VIDEO_STREAM','NO_AUDIO_STREAM','WRONG_ASPECT'
        }
        blocking=[i for i in audit.get('issues',[]) if i.get('code') in hard_issues]
        # V55.4: a mild boundary warning cannot block an otherwise aligned caption track.
        if any(i.get('code')=='CAPTIONS_BAD_BOUNDARY' for i in blocking):
            cap_a=audit.get('caption_audit',{}) or {}
            align_a=_caption_narration_alignment(beats,script.get('narration',''))
            severe_boundary=((len(cap_a.get('bad_end',[]))+len(cap_a.get('bad_start',[])))>=max(4,int(len(beats or [])*0.55)))
            if align_a.get('foreign_ratio',0)<=0.03 and align_a.get('score',100)>=85 and cap_a.get('repeated_adjacent',0)==0 and not severe_boundary:
                blocking=[i for i in blocking if i.get('code')!='CAPTIONS_BAD_BOUNDARY']
                audit.setdefault('notes',[]).append('V55.4: boundary leve aceito com alinhamento íntegro à narração.')
        if audit.get('score',0)<90 or blocking:
            for issue in audit.get('issues',[]): _learn_event(issue['code'],issue['message'])
            # V55.6: nunca ocultar o motivo quando o score reprova sem hard-block.
            all_codes=[]
            for issue in (audit.get('issues',[]) or []):
                code=str(issue.get('code','')).strip()
                if code and code not in all_codes:
                    all_codes.append(code)
            names=', '.join(i.get('code','') for i in blocking[:6])
            if not names:
                names=', '.join(all_codes[:10])
            details=[]
            for issue in (audit.get('issues',[]) or [])[:6]:
                code=str(issue.get('code','')).strip()
                msg=str(issue.get('message','')).strip()
                if code:
                    details.append(f'{code}: {msg[:180]}')
            detail_text=' | '.join(details)
            raise ValueError(
                'AUDITOR IA: gate estrito reprovou o vídeo após correções seguras'
                + (f' — score={audit.get("score",0)}; problemas: {names}' if names else f' — score={audit.get("score",0)}; nenhum código de problema registrado')
                + (f' — detalhes: {detail_text}' if detail_text else '')
                + '.'
            )
        # V52 strict caption gate: never approve captions that are not derived from the actual narration.
        cap_alignment=_caption_narration_alignment(beats,script.get('narration',''))
        if cap_alignment.get('foreign_ratio',0)>0.03 or cap_alignment.get('score',100)<85:
            raise ValueError('GATE CAPTIONS: legendas contêm texto que não pertence à narração. Produção bloqueada para autocorreção.')
        # V33 hard gate: rendering is not enough; reject editorially contaminated/weak scripts.
        banned_editorial=('radar','editor-chefe','score','confiança','fontes','matérias','produzir agora')
        low=narration_check=str(script.get('narration','')).lower()
        if any(x in low for x in banned_editorial):
            raise ValueError('GATE EDITORIAL: narração contém metadado interno.')
        if int(script.get('word_count',0) or 0) < 70:
            raise ValueError('GATE EDITORIAL: roteiro factual curto demais para um Short consistente.')
        if not script.get('evidence'):
            raise ValueError('GATE EDITORIAL: nenhuma evidência da matéria principal.')
        if str(script.get('source','')).lower().find('news.google.com') >= 0:
            raise ValueError('GATE SOURCE-LOCK: a URL final ainda é Google News.')
        if str(script.get('extraction_method','')).startswith('BLOCKED_'):
            raise ValueError('GATE SOURCE-LOCK: extração da matéria original não confiável.')
        meta={'title':topic['title'].upper()+' 👀','description':script['narration']+'\n\n🔎 GTA Oculto — onde os segredos vêm à tona.','hashtags':['#GTA6','#GTAVI','#GTAOculto','#RockstarGames','#GTA'],'tags':['GTA 6','GTA VI','GTA 6 Brasil','GTA 6 teorias','GTA 6 segredos','Rockstar Games','GTA Oculto'],'score':score,'audit_score':audit.get('score',0),'audit':audit,'script_version':script.get('script_version','V33.0-MAIN-ARTICLE-LOCKED')}
        (jobdir/'metadata.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
        update_job(jid,status='DONE',stage='PRONTO',progress=100,log=f'PRONTO — Short gerado e avaliado em {score}/100.',video=f'{jid}/GTA_OCULTO_SHORT.mp4',cover=f'{jid}/CAPA.jpg',score=score,metadata=meta)
        if AUTONOMOUS_ENGINE:
            try: AUTONOMOUS_ENGINE.on_done(jid,sys.modules[__name__])
            except Exception as _pub_e: update_job(jid,log=f'PRONTO — publicação automática aguardando configuração: {str(_pub_e)[:300]}')
    except Exception as e:
        import traceback
        tb=traceback.format_exc()
        recovered=None
        if AUTONOMOUS_ENGINE:
            try:
                recovered=AUTONOMOUS_ENGINE.on_error(jid,str(e)+'\n'+tb[-5000:],sys.modules[__name__])
            except Exception as _ae:
                recovered={'action':'QUARANTINE','reason':str(_ae)}
        if not recovered or recovered.get('action')=='QUARANTINE':
            update_job(jid,status='ERROR',stage='ERRO',progress=100,log='ERRO: '+str(e)+'\n'+tb[-3200:])
        else:
            update_job(jid,log=f'🤖 AUTO-RECUPERAÇÃO: {recovered.get("action")}. O agente continuará sem intervenção manual.')
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
def health():
    auto=AUTONOMOUS_ENGINE.status() if AUTONOMOUS_ENGINE else {'mode':'DEGRADED'}
    return jsonify(ok=True,app='GTA Oculto AI',version=BUILD_VERSION,processor='cloud',autonomous_mode=AUTONOMOUS_MODE,max_topic_recovery=AUTONOMOUS_MAX_TOPIC_RECOVERY,autonomy=auto)
@APP.get('/api/autonomy')
def autonomy_status():
    return jsonify(AUTONOMOUS_ENGINE.status() if AUTONOMOUS_ENGINE else {'mode':'DEGRADED'})

@APP.get('/api/state')
def state():
    # IMPORTANT: never wait on the production LOCK here. The producer/render
    # runs in a background thread inside the Gunicorn worker and may legitimately
    # spend minutes downloading/encoding media. Waiting for LOCK makes the
    # dashboard polling request hang until Gunicorn kills the worker with
    # WORKER TIMEOUT, which in turn kills the production thread.
    # jobs.json is written with atomic os.replace(), so a lock-free read is safe:
    # readers see either the previous complete JSON or the next complete JSON.
    js=list(load_jobs().values())[-30:]
    topics,updated,radar_status,radar_error,sources_ok=current_opportunities()
    editor_pick=editor_chief_select(topics) if topics else None

    # V40: NEVER execute the full editorial/source resolver inside /api/state.
    # The dashboard polls this endpoint repeatedly. make_script() can perform
    # external network resolution (Google News decoder/search) and could make
    # the browser appear to load forever. The real script is generated only
    # after /api/produce starts the production job.
    if editor_pick:
        editor_pick['script_preview'] = {
            'word_count': 0,
            'estimated_seconds': 0,
            'sections': {
                'hook': editor_pick.get('editorial_hook',''),
                'context': '',
                'proof': '',
                'payoff': editor_pick.get('editorial_angle',''),
                'cta': ''
            }
        }

    return jsonify(opportunities=topics,jobs=js,produced=sum(x.get('status')=='DONE' for x in js),queue=sum(x.get('status') in ('QUEUED','RUNNING') for x in js),radar_updated=updated,radar_status=radar_status,radar_error=radar_error,radar_sources_ok=sources_ok,editor_pick=editor_pick)
@APP.post('/api/research')
def research():
    try:
        radar=radar_scan(); return jsonify(ok=True,message=f'Radar atualizado: {len(radar.get("opportunities",[]))} oportunidades encontradas. Editor-Chefe pronto.',opportunities=radar.get('opportunities',[]),radar_updated=radar.get('updated_at'))
    except Exception as e: return jsonify(error=str(e)),502
@APP.post('/api/produce')
def produce():
    data=request.get_json(silent=True) or {}
    topics,_,_,_,_=current_opportunities()
    topic=choose_topic(data,topics)
    jid=uuid.uuid4().hex[:10]
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

def radar_loop():
    time.sleep(8)
    while True:
        try: radar_scan()
        except Exception: pass
        time.sleep(15*60)

def autonomy_loop():
    if not AUTONOMOUS_ENGINE: return
    while True:
        try:
            AUTONOMOUS_ENGINE.collect_analytics()
        except Exception: pass
        time.sleep(6*60*60)

threading.Thread(target=processor_loop,daemon=True).start()
threading.Thread(target=radar_loop,daemon=True).start()
threading.Thread(target=autonomy_loop,daemon=True).start()
if __name__=='__main__': APP.run(host='0.0.0.0',port=int(os.environ.get('PORT',5000)))

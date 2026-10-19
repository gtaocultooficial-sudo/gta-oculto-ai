# Internal editorial and crop-safety follow-up.
import struct, zlib
import os, json, uuid, threading, time, asyncio, subprocess, shutil, re, sys, math, statistics
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
from flask import Flask, request, jsonify, render_template_string, send_from_directory, redirect
from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageChops, ImageStat
try:
    from live_clipper import LiveClipper
except Exception:
    LiveClipper = None

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
try:
    from trend_brain import TrendBrain
    TREND_BRAIN = TrendBrain(WORK)
except Exception:
    TREND_BRAIN = None
WORK.mkdir(parents=True, exist_ok=True)
STATE_FILE = WORK / 'jobs.json'
PENDING_QUEUE_DIR = WORK / 'pending_queue'
PENDING_QUEUE_DIR.mkdir(parents=True, exist_ok=True)
LOCK = threading.RLock()
PROCESSING = False
# V43: autonomous recovery is ON by default. It may switch to another validated Radar topic
# when a source cannot be resolved, so a transient resolver failure never requires the owner
# to intervene manually. Set GTA_AUTONOMOUS_MODE=0 only to disable this behavior.
AUTONOMOUS_MODE = os.getenv('GTA_AUTONOMOUS_MODE','1').strip().lower() not in ('0','false','off','no')
AUTONOMOUS_MAX_TOPIC_RECOVERY = max(1, min(6, int(os.getenv('GTA_AUTONOMOUS_MAX_TOPIC_RECOVERY','5'))))
_last_gnews_diagnostics = []
UA = 'GTA-Oculto-AI/Cloud-Final/V55-SOURCE-RECOVERY-3' 
# V64.11-HOOK-RETENTION-20261009
ROCKSTAR_VI = 'https://www.rockstargames.com/VI'
ROCKSTAR_NEWS = 'https://www.rockstargames.com/newswire/article/4k138k8okkk483/grand-theft-auto-vi-an-extended-look-now-playing'
ROCKSTAR_VIDEO_ZIP = 'https://media-rockstargames-com.akamaized.net/VI/downloads/videos/GTAVI_Videos.zip'
BUILD_VERSION = 'V68.8-SELECTED-TOPIC-ALIGNMENT-GATE-20261019'

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
<div class="panel" id="analyticsPanel"><div class="radar-head"><div><h3>📊 RESUMO DO YOUTUBE ANALYTICS</h3><div class="muted" style="font-size:10px">Métricas reais dos vídeos do canal, conforme as permissões da conta conectada.</div></div><button class="btn" onclick="loadAnalytics(true)">↻ ATUALIZAR</button></div><div id="analyticsStatus" class="notice">Carregando resumo de métricas…</div><div class="stats"><div class="stat"><small>VISUALIZAÇÕES</small><b id="anViews">—</b></div><div class="stat"><small>MÉDIA POR VÍDEO</small><b id="anAverage">—</b></div><div class="stat"><small>INSCRITOS GANHOS</small><b id="anSubs">—</b></div><div class="stat"><small>CURTIDAS</small><b id="anLikes">—</b></div></div><div class="stats"><div class="stat"><small>TEMPO ASSISTIDO</small><b id="anMinutes">—</b></div><div class="stat"><small>DURAÇÃO MÉDIA</small><b id="anDuration">—</b></div><div class="stat"><small>COMENTÁRIOS</small><b id="anComments">—</b></div><div class="stat"><small>VÍDEOS ANALISADOS</small><b id="anCount">—</b></div></div><div id="analyticsAdvice" class="notice">A IA vai sugerir próximos testes quando houver dados suficientes.</div><div id="analyticsVideos"></div></div>
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

async function loadAnalytics(force){
 const box=document.getElementById('analyticsStatus');if(!box)return;if(force)box.textContent='Buscando dados do canal…';
 try{const r=await fetch('/api/analytics/summary'+(force?'?refresh=1':''),{cache:'no-store'});const d=await r.json();if(!r.ok||!d.ok){box.textContent='Analytics indisponível: '+(d.reason||d.error||'verifique a conexão e as permissões do YouTube.');return}
 const fmt=n=>Number(n||0).toLocaleString('pt-BR'),set=(id,v)=>{const e=document.getElementById(id);if(e)e.textContent=v};
 set('anViews',fmt(d.total_views));set('anAverage',fmt(d.average_views));set('anSubs',d.subscribers_available?fmt(d.subscribers_gained):'N/D');set('anLikes',d.likes_available?fmt(d.total_likes):'N/D');set('anMinutes',d.watch_minutes_available?fmt(Math.round(d.watch_minutes))+' min':'N/D');set('anDuration',d.duration_available?Math.floor(d.average_view_duration/60)+'m '+Math.round(d.average_view_duration%60)+'s':'N/D');set('anComments',d.comments_available?fmt(d.total_comments):'N/D');set('anCount',fmt(d.video_count));
 box.textContent='Período: '+(d.start||'—')+' a '+(d.end||'—')+' · Fonte: '+(d.source==='public_stats_fallback'?'estatísticas públicas do YouTube':'YouTube Analytics')+' · Atualizado: '+(d.checked_at?new Date(d.checked_at).toLocaleString('pt-BR'):'agora');
 document.getElementById('analyticsAdvice').textContent=d.recommendation||'Ainda não há dados suficientes para recomendações.';
 document.getElementById('analyticsVideos').innerHTML=d.videos&&d.videos.length?'<div class="table-head" style="display:grid;grid-template-columns:minmax(180px,1fr) 80px 80px 80px 80px;gap:8px"><div>VÍDEO</div><div>VIEWS</div><div>CURTIDAS</div><div>INSCRITOS</div><div>COMENT.</div></div>'+d.videos.map(v=>'<div class="row" style="grid-template-columns:minmax(180px,1fr) 80px 80px 80px 80px"><div class="title">'+esc(v.title||v.video_id)+'</div><div>'+fmt(v.views)+'</div><div>'+(v.likes_available?fmt(v.likes):'N/D')+'</div><div>'+(v.subscribers_available?fmt(v.subscribers_gained):'N/D')+'</div><div>'+(v.comments_available?fmt(v.comments):'N/D')+'</div></div>').join(''):'<div class="notice">Nenhum vídeo foi retornado pela fonte de métricas.</div>';
 }catch(e){box.textContent='Falha ao carregar o resumo. Tente atualizar novamente.'}}
load();setInterval(load,3000);setTimeout(()=>loadAnalytics(false),1800);
</script><section class="panel" id="liveClipperPanel" style="border-color:#2d6bff">
<h3>✂️ CORTES DE LIVE — IA AUTÔNOMA</h3>
<div class="notice">Aceita lives longas. O motor trabalha por blocos e procura os melhores momentos sem carregar a gravação inteira na memória.</div>
<div class="control"><input id="liveSource" placeholder="URL pública da gravação da live"><input id="liveMax" type="number" min="1" max="20" value="10" style="max-width:90px"><button class="btn red" onclick="startLiveClips()">ANALISAR LIVE</button></div>
<div id="liveStatus" class="notice" style="margin-top:8px">Aguardando uma live.</div>
<div id="liveResults"></div>
</section>
<script>
async function startLiveClips(){
 const source=document.getElementById('liveSource').value.trim(), max=parseInt(document.getElementById('liveMax').value||10);
 if(!source){document.getElementById('liveStatus').textContent='Cole a URL da gravação da live.';return}
 document.getElementById('liveStatus').textContent='Enfileirando análise...';
 const r=await fetch('/api/live/analyze',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url:source,max_clips:max})});
 const j=await r.json(); if(!j.ok){document.getElementById('liveStatus').textContent='Erro: '+(j.error||'falha');return}
 pollLive(j.job_id,source);
}
async function pollLive(id,source){
 const r=await fetch('/api/live/job/'+id),j=await r.json();
 document.getElementById('liveStatus').textContent=(j.stage||'PROCESSANDO')+' — '+(j.progress||0)+'%';
 if(j.status==='RUNNING'||j.status==='QUEUED'){setTimeout(()=>pollLive(id,source),4000);return}
 if(j.status==='ERROR'){document.getElementById('liveStatus').textContent='Erro: '+j.error;return}
 const clips=j.clips||[];
 document.getElementById('liveResults').innerHTML='<div class="notice">Encontrados '+clips.length+' cortes. Renderizando automaticamente...</div>';
 const rr=await fetch('/api/live/render',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url:source,clips})});
 const q=await rr.json(); if(!q.ok){document.getElementById('liveStatus').textContent='Erro no render: '+q.error;return}
 pollLiveRender(q.job_id);
}
async function pollLiveRender(id){
 const r=await fetch('/api/live/job/'+id),j=await r.json();
 document.getElementById('liveStatus').textContent=(j.stage||'RENDERIZANDO')+' — '+(j.progress||0)+'%';
 if(j.status==='RUNNING'||j.status==='QUEUED'){setTimeout(()=>pollLiveRender(id),4000);return}
 if(j.status==='ERROR'){document.getElementById('liveStatus').textContent='Erro: '+j.error;return}
 const links=(j.outputs||[]).map(x=>'<div style="margin:6px 0"><a href="/output/'+x+'" target="_blank" style="color:#7dc7ff">🎬 '+x.split('/').pop()+'</a></div>').join('');
 document.getElementById('liveResults').innerHTML='<div class="notice">✅ '+(j.outputs||[]).length+' cortes prontos.</div>'+links;
 document.getElementById('liveStatus').textContent='CORTES PRONTOS';
}
</script>
</body></html>'''
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


def _parse_rss(url, feed_name, timeout=18):
    items=[]
    try:
        r=fetch(url,timeout=timeout); r.raise_for_status()
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
    """Radar V64.9: coleta limitada por tempo, com diagnóstico por fonte."""
    started=time.monotonic()
    raw=[]; successful_sources=0; errors=[]
    # Duas consultas agregadas dão descoberta suficiente. Evitamos quatro feeds
    # idênticos bloqueando a fase de pesquisa por vários timeouts sequenciais.
    feeds=RADAR_FEEDS[:2]
    for name,url in feeds:
        if time.monotonic()-started > 14:
            errors.append('orçamento de radar esgotado antes de '+name)
            break
        try:
            batch=_parse_rss(url,name,timeout=6)
            if batch:
                successful_sources += 1
                raw.extend(batch)
            else:
                errors.append(name+' sem resultados')
        except Exception as e:
            errors.append(name+': '+str(e)[:120])
    # Newswire oficial é uma fonte complementar, não deve bloquear descoberta.
    if time.monotonic()-started < 15:
        try:
            r=fetch('https://www.rockstargames.com/br/newswire',timeout=5); r.raise_for_status()
            successful_sources += 1
            soup=BeautifulSoup(r.text,'html.parser')
            for a in soup.find_all('a',href=True):
                t=' '.join(a.stripped_strings).strip()
                href=urljoin('https://www.rockstargames.com/br/newswire',a['href'])
                if t and any(k in t.lower() for k in ('grand theft auto vi','gta vi','gta 6')):
                    raw.append({'title':t,'url':href,'published':'','source':'Rockstar Games','feed':'Rockstar Newswire','description':''})
        except Exception as e:
            errors.append('Rockstar Newswire: '+str(e)[:160])
    update_note='V64.9 radar: fontes_ok={} erros={}'.format(successful_sources,' | '.join(errors[:4]) or 'nenhum')

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
    if TREND_BRAIN and ranked:
        try:
            ranked=TREND_BRAIN.rank(ranked[:10])
            for item in ranked:
                item['score']=max(int(item.get('score',0)), int(item.get('trend_score',0)))
        except Exception:
            pass
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
    result=_save_radar(ranked[:10], status='OK', sources_ok=successful_sources)
    result['diagnostic']=update_note
    return result

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
    if custom:
        return {'id':'custom','score':88,'priority':'ALTA','title':custom,'source':'Pesquisa editorial','url':ROCKSTAR_VI,'radar':False}
    ranked=[dict(x) for x in (topics or [])]
    if TREND_BRAIN:
        try:
            ranked=TREND_BRAIN.rank(ranked)
        except Exception:
            pass
    return max(ranked,key=lambda x:(x.get('trend_score',x.get('score',0)),x.get('score',0)))


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
    generic_title_words={
        'gta','grand','theft','auto','game','gaming','jogo','jogos','novo','nova','novos','novas',
        'confirmado','confirmada','confirmados','confirmadas','novidade','novidades','detalhe','detalhes',
        'segredo','segredos','noticia','noticias','revela','revelou','rockstar','informacao','informacoes'
    }
    title_words=set(w for w in title_norm.split() if len(w)>3 and w not in generic_title_words)
    title_lower=str(title or '').lower()
    unrelated_entities=(
        (r'\bnetflix\b','netflix'),(r'\bprime video\b','prime video'),
        (r'\bdisney\s*\+?\b','disney+'),(r'\bparamount\s*\+?\b','paramount+'),
        (r'\bapple tv\s*\+?\b','apple tv+'),(r'\bcrunchyroll\b','crunchyroll'),
        (r'\bfortnite\b','fortnite'),(r'\bminecraft\b','minecraft'),
        (r'\broblox\b','roblox'),(r'\bcall of duty\b','call of duty')
    )
    seen=set(); clean=[]
    for x in raw:
        x=re.sub(r'\s+',' ',x).strip(' -–—')
        if len(x)<35: continue
        low=x.lower()
        if any(bad in low for bad in ('leia também','publicidade','clique aqui','assine','cookies','newsletter')): continue
        # Reject unrelated franchise/service references unless the selected topic explicitly covers them.
        if any(re.search(pattern,low,re.I) and not re.search(pattern,title_lower,re.I) for pattern,_name in unrelated_entities): continue
        # Block headline/list fragments and require stronger topical evidence than one generic word.
        if len(re.findall(r'[:|–—-]',x))>=3 and len(x.split())<20: continue
        if len(x.split())<8: continue
        sentence_words=set(re.sub(r'[^a-z0-9à-ÿ ]',' ',low).split())
        overlap=len(title_words.intersection(sentence_words))
        gta_relevance=any(k in low for k in ('gta 6','gta vi','grand theft auto vi','grand theft auto 6','rockstar','vice city','leonida','jason','lucia'))
        if gta_relevance or overlap>=2:
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



def _focused_work_story_hook(preferred_type=None):
    """Caption-safe question; keeps the subject phrase together and avoids a dangling preposition."""
    return 'O QUE LEVA JASON E LUCIA A BUSCAR TRABALHOS EM VICE CITY?'


def _learned_hook_variant(preferred_type, kind, focused_work_story, title):
    """Select a proven hook style without changing the underlying factual claim."""
    p=str(preferred_type or '').upper()
    k=str(kind or '').upper()
    if focused_work_story:
        return _focused_work_story_hook(p)
    variants={
        'CONFIRMACAO':'A ROCKSTAR REVELOU UMA NOVA INFORMAÇÃO SOBRE GTA 6',
        'RUMOR':'ISSO SOBRE GTA 6 AINDA NÃO FOI CONFIRMADO',
        'DETALHE':'ESSE DETALHE DE GTA 6 PODE TER MAIS IMPORTÂNCIA DO QUE PARECE',
        'CURIOSIDADE':'VOCÊ PERCEBEU ESSE DETALHE NO GTA 6?',
    }
    if p in variants:
        return variants[p]
    return None

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
        'resolver budget','source-lock','source lock','sem evidência da matéria principal',
        # Editorial topic drift is recoverable: discard this candidate and try
        # the next approved topic instead of rendering a mismatched Short.
        'selected_topic_mismatch','selected topic mismatch',
        'editorial_substance_insufficient'
    )
    return any(k in msg for k in keys)


def _autonomous_make_script(jid, topic, topics):
    """V55: validates source before committing to a production topic and changes topic automatically on failure."""
    if not AUTONOMOUS_MODE:
        # Capture the approved topic BEFORE make_script mutates topic['title']
        # into an evidence-based headline. QA must compare against the original topic.
        selected_topic_title=str(topic.get('title') or '')
        script=make_script(topic)
        script['selected_topic_title']=selected_topic_title
        return topic, script
    candidates=[]; seen=set()
    recovery_pool=[topic] + list(topics or []) + list(FALLBACK_TOPICS)
    for t in recovery_pool:
        if not isinstance(t,dict): continue
        key=str(t.get('id') or t.get('title') or '').strip().lower()
        if not key or key in seen: continue
        seen.add(key); candidates.append(dict(t))
    candidates.sort(key=lambda x:(1 if x.get('recovery_urls') else 0, int(x.get('score',0))), reverse=True)
    # V64.8: cap total de recuperação. O resolver já possui orçamento interno;
    # empilhar 5 pautas pode multiplicar chamadas externas e deixar o job sem progresso.
    candidates=candidates[:max(1, min(6, AUTONOMOUS_MAX_TOPIC_RECOVERY))]
    last_exc=None
    for attempt,candidate in enumerate(candidates,1):
        started=time.monotonic()
        title=str(candidate.get('title') or 'GTA 6')
        update_job(jid,title=title,opportunity=candidate,stage='AUTO-RECUPERAÇÃO',progress=min(30,24+attempt),
                   log=f'V64.8: validação de fonte {attempt}/{len(candidates)} — {title}')
        try:
            # Capture the approved topic BEFORE make_script mutates candidate['title']
            # into an evidence-based headline. Otherwise QA compares the narration
            # to the rewritten title and misses cross-topic drift.
            selected_topic_title=str(candidate.get('title') or '')
            script=make_script(candidate)
            # Preserve the original approved topic separately from the rewritten headline.
            script['selected_topic_title']=selected_topic_title
            # Preflight the spoken narration against the original approved topic
            # BEFORE spending time rendering a video. If it drifted, discard this
            # candidate and let the bounded recovery loop try another topic.
            preflight=_editorial_topic_alignment(
                selected_topic_title, script.get('narration',''), [], selected_topic_title
            )
            if not preflight.get('ok'):
                raise ValueError(
                    'SELECTED_TOPIC_MISMATCH: roteiro não corresponde à pauta aprovada: '
                    + ', '.join(preflight.get('issues',[])[:8])
                )
            elapsed=round(time.monotonic()-started,1)
            update_job(jid,log=f'V64.8: fonte validada em {elapsed}s; pauta aprovada: {title}')
            return candidate, script
        except Exception as exc:
            last_exc=exc
            diagnostic=f'{type(exc).__name__}: {str(exc)[:450]}'
            try: _learn_event('V64_SOURCE_RECOVERY_FAILED',diagnostic,title)
            except Exception: pass
            update_job(jid,log=f'V64.8: pauta descartada após {round(time.monotonic()-started,1)}s — {diagnostic}')
            if not _is_source_recovery_error(exc):
                raise
            if attempt < len(candidates):
                update_job(jid,log='V64.8: tentando uma única pauta alternativa; não vai reutilizar manchete sem corpo original.')
    if last_exc:
        raise ValueError(f'V64.9: nenhuma pauta passou pela validação editorial após {len(candidates)} tentativas. Última falha: '+str(last_exc)[:600])
    raise ValueError('V55: nenhuma oportunidade disponível para recuperação de fonte.')


def _headline_from_specific_evidence(title, evidence):
    """Build a Short headline from the exact evidence used, avoiding unsupported source entities."""
    original=_clean_narrative_text(str(title or '')).strip()
    text=' '.join(str(x or '') for x in (evidence or [])).lower()
    broad=bool(re.search(r'\b\d+\s+(?:novidades|detalhes|segredos|curiosidades|fatos|mistérios|misterios)\b',original,re.I))
    pair=bool(re.search(r'\bjason\b',text) and re.search(r'\blucia\b',text))
    work_money=any(re.search(p,text,re.I) for p in (
        r'\btrabalh\w*\b',r'\bempreg\w*\b',r'\bdinheiro\b',r'\bganhar\b',r'\brenda\b'
    ))
    if broad and pair and work_money:
        return 'GTA 6: Jason e Lucia estão trabalhando para ganhar dinheiro?'
    named_entities=('jason','lucia','leonida','vice city','rockstar','microsoft','xbox','playstation')
    unsupported=[name for name in named_entities
                 if re.search(r'\b'+re.escape(name)+r'\b',original,re.I)
                 and not re.search(r'\b'+re.escape(name)+r'\b',text,re.I)]
    if unsupported and evidence:
        fact=_clean_narrative_text(str(evidence[0])).strip(' .!?')
        if fact:
            fact=' '.join(fact.split())
            if len(fact)>82:
                fact=fact[:82].rsplit(' ',1)[0]
            return 'GTA 6 — '+fact
    return original



def _editorial_topic_alignment(title, narration, evidence, source_title=''):
    """V64.6: conservative, deterministic gate against listicle/headline drift."""
    title_text=_clean_narrative_text(str(title or '')).lower()
    narration_text=_clean_narrative_text(str(narration or '')).lower()
    evidence_text=' '.join(str(x or '') for x in (evidence or [])).lower()
    article_title=str(source_title or '').lower()
    all_body=' '.join((narration_text,evidence_text))

    def tokens(value):
        words=re.findall(r"[a-zà-ÿ0-9']+", value.lower())
        stop={'gta','6','gta6','the','a','o','e','de','do','da','em','no','na','os','as',
              'um','uma','que','para','com','por','mais','mas','como','esse','essa','isso','sobre',
              'novo','nova','novos','novas','jogo','jogos','rockstar','confirmado','confirmada',
              'confirmados','confirmadas','detalhe','detalhes','novidade','novidades'}
        return {w for w in words if len(w)>2 and w not in stop and not w.isdigit()}

    title_terms=tokens(title_text)
    body_terms=tokens(all_body)
    source_terms=tokens(article_title)
    narration_terms=tokens(narration_text)
    overlap=len(title_terms & body_terms)/max(1,len(title_terms))
    source_overlap=len(title_terms & source_terms)/max(1,len(title_terms)) if source_terms else 0.0
    source_narration_overlap=len(source_terms & narration_terms)/max(1,len(source_terms)) if source_terms else 1.0
    issues=[]

    # A headline count/listicle claim is a factual promise. It must not be
    # published by a Short that only gives one fact or never supports the count.
    listicle=re.search(r"\b(\d{1,3})\s+(novidades|detalhes|segredos|curiosidades|fatos|mistérios|misterios)\b", title_text, re.I)
    if listicle:
        count=int(listicle.group(1))
        list_words=re.findall(r"\b(?:novidades|detalhes|segredos|curiosidades|fatos|mistérios|misterios)\b", narration_text, re.I)
        enumerators=re.findall(r"\b(?:primeir[ao]|segund[ao]|terceir[ao]|quarta|quarto|quinta|quinto|sexta|sexto|sétima|sétimo|oitava|oitavo|nona|nono|décima|décimo|também|outro|outra|além disso|por fim)\b", narration_text, re.I)
        # Count-based titles ("50 novidades") are not accepted unless the
        # narration itself carries a genuine listicle structure.
        if count >= 10 or len(list_words) < 2 or len(enumerators) < 2:
            issues.append('headline_listicle_promise_not_delivered')

    # Named entities in the headline must be supported by actual script/evidence.
    for name in ('jason','lucia','leonida','vice city','rockstar','microsoft','xbox','playstation'):
        if re.search(r"\b"+re.escape(name)+r"\b", title_text) and not re.search(r"\b"+re.escape(name)+r"\b", all_body):
            issues.append('headline_entity_missing:'+name)

    if title_terms and overlap < 0.25:
        issues.append('headline_body_low_overlap')
    if title_terms and source_terms and source_overlap < 0.10 and overlap < 0.45:
        issues.append('headline_source_body_mismatch')
    # A title may be safely rewritten from evidence, but the spoken script still
    # must retain at least one meaningful connection to the original source headline.
    # This blocks a GTA 6 script about an unrelated topic that merely shares the franchise.
    if len(source_terms)>=4 and source_narration_overlap < 0.10:
        issues.append('source_headline_narration_mismatch')
    return {
        'ok': not issues,
        'score': max(0, round(100 - 45*len(issues))),
        'issues': sorted(set(issues)),
        'title_body_overlap': round(overlap, 3),
        'title_source_overlap': round(source_overlap, 3),
        'source_narration_overlap': round(source_narration_overlap, 3),
        'title_terms': sorted(title_terms),
        'body_terms': sorted(body_terms),
    }

def make_script(topic):
    """V33 — Main Article Locked.
    Uma matéria principal. Um corpo principal. Um roteiro.
    Se a página não puder ser identificada/extraída com segurança, a produção falha
    em vez de preencher o vídeo com manchetes ou fatos de outras páginas.
    """
    title,desc,source,url=_source_evidence(topic)
    source_headline=str(title or topic.get('title') or '')
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
    # Editorial substance gate: a Short needs at least two distinct factual
    # sentences from the SAME article. One fact padded with generic commentary
    # is not enough to justify a 30-second story.
    distinct_evidence=[]
    seen_evidence=set()
    for item in evidence:
        normalized=re.sub(r'[^a-zà-ÿ0-9]+',' ',str(item).lower()).strip()
        if normalized and normalized not in seen_evidence:
            seen_evidence.add(normalized)
            distinct_evidence.append(item)
    if len(distinct_evidence)<2:
        raise ValueError('EDITORIAL_SUBSTANCE_INSUFFICIENT: a matéria não trouxe duas evidências factuais distintas; pauta descartada para evitar narração genérica.')
    evidence=distinct_evidence

    angle,_=_editorial_angle(topic)
    # A listicle headline must not be reused for a Short that only covers one
    # narrow fact from that article. Match the title to the exact evidence used.
    headline=_headline_from_specific_evidence(title,evidence)
    headline=_clean_narrative_text(headline.rstrip('.!?'))
    # Remove prefixos redundantes e publisher no título.
    headline=re.sub(r'^\s*(?:gta\s*6|gta\s*vi)\s*[:\-–—]\s*', 'GTA 6 — ', headline, flags=re.I)
    headline=_strip_publisher_suffix(headline)
    headline=re.sub(r'\s+',' ',headline).strip(' -–—')
    # Keep the metadata, cover, and narration title synchronized with the chosen facts.
    topic['title']=headline
    clean_topic=re.sub(r'^\s*GTA\s*6\s*[—:-]\s*','',headline,flags=re.I).strip()
    if not clean_topic:
        clean_topic='uma nova informação sobre GTA 6'
    # V64.12: detecta pautas específicas pelo CORPO factual, não só pela manchete.
    # Isso evita que um título amplo transforme uma matéria específica em roteiro genérico.
    evidence_text=' '.join(evidence)
    focused_work_story=(
        bool(re.search(r'\bjason\b',evidence_text,re.I))
        and bool(re.search(r'\blucia\b',evidence_text,re.I))
        and bool(re.search(r'\b(?:trabalh\w*|empreg\w*|dinheiro|ganh\w*|renda)\b',evidence_text,re.I))
    )
    focused_story=(
        bool(re.search(r'\bjason\b',headline,re.I))
        and bool(re.search(r'\blucia\b',headline,re.I))
        and bool(re.search(r'\btrabalh\w*\b',headline,re.I))
        and bool(re.search(r'\b(?:dinheiro|ganh\w*)\b',headline,re.I))
    ) or focused_work_story

    # V64.12: hooks específicos vencem os hooks genéricos quando a evidência permite.
    if focused_work_story:
        hook=_focused_work_story_hook()
    elif kind=='NOTÍCIA':
        hook='A ROCKSTAR REVELOU UMA NOVA INFORMAÇÃO SOBRE GTA 6'
    elif kind=='RUMOR':
        hook='ISSO SOBRE GTA 6 AINDA NÃO FOI CONFIRMADO'
    elif kind=='MISTÉRIO':
        hook='ESSE DETALHE DE GTA 6 PODE TER MAIS IMPORTÂNCIA DO QUE PARECE'
    else:
        hook='TEM UM DETALHE NESSA HISTÓRIA DE GTA 6 QUE VALE A PENA VER'

    # V64.13: when Analytics has enough evidence, let the learned winning hook style
    # choose the presentation. The factual evidence and claims remain unchanged.
    learned_profile={}
    if TREND_BRAIN:
        try: learned_profile=TREND_BRAIN.recommend_editorial_profile() or {}
        except Exception: learned_profile={}
    learned_hook=_learned_hook_variant(learned_profile.get('preferred_hook_type'),kind,focused_work_story,headline)
    if learned_hook:
        hook=learned_hook

    # Use only the factual material needed for the story. The narration should
    # not restate the same idea in the hook, context, proof and payoff.
    learned_duration_bucket=str((learned_profile.get('preferred_duration') or {}).get('bucket') or '')
    # Closed-loop duration learning: use the learned winner to control factual
    # density before TTS, not only the number of visual beats.
    # Keep a compact learned-duration draft first; if it is too short, the verified next evidence sentence is added below.
    # Preserve two factual beats even in short-duration profiles; reduce filler,
    # not evidence. The narration can be shortened at the wording level later.
    selected_evidence=evidence[:2]
    fact_parts=[]
    for item in selected_evidence:
        item=_clean_narrative_text(item).rstrip('.!?')
        if focused_work_story:
            item=re.sub(r'^do pouco que foi mostrado,\s*','Até agora, ',item,flags=re.I)
        if item and item not in fact_parts:
            fact_parts.append(item)
    fact='. '.join(fact_parts)+'.'

    if focused_work_story:
        # Give each beat a distinct job: hook, evidence, context, caveat, CTA.
        fact='Até agora, Jason e Lucia parecem estar aceitando trabalhos para diferentes figuras importantes de Vice City, numa tentativa de conseguir dinheiro.'
        context='Essas cenas também situam a dupla no ambiente da cidade, antes de sabermos quais consequências essa rotina terá.'
        payoff='A informação não confirma que cada trabalho seja uma missão principal nem define o papel deles na trama.'
        cta='Você acha que isso vai ter impacto na história?'
    elif kind=='NOTÍCIA':
        context='O ponto agora é entender o alcance real dessa informação, sem confundir o fato com teorias da comunidade.'
        payoff='A conclusão precisa ficar dentro do que a fonte realmente confirmou, sem prometer mudanças que ela não anunciou.'
        cta='Você acha que isso muda alguma coisa no GTA 6?'
    elif kind=='RUMOR':
        context='O rumor chama atenção porque sugere uma possibilidade, mas ainda precisa ser separado dos fatos confirmados.'
        payoff='Sem confirmação oficial, essa hipótese não pode ser tratada como informação garantida.'
        cta='Você acha que esse rumor pode se confirmar?'
    elif kind=='MISTÉRIO':
        context='A pista pode abrir uma interpretação interessante, desde que a gente não confunda possibilidade com prova.'
        payoff='Uma pista isolada não confirma a teoria; é preciso mais evidência para fechar essa conclusão.'
        cta='O que você acha que isso significa?'
    else:
        context='O interesse está no que esse fato pode indicar para o jogo, sem ir além do que a matéria mostra.'
        payoff='A evidência é o ponto de partida; qualquer conclusão maior ainda depende de contexto e confirmação.'
        cta='Você já tinha percebido isso?'


    if learned_duration_bucket=='30-38s' and not focused_story:
        context += ' O contexto adicional ajuda a entender por que esse detalhe está chamando atenção agora.'
    # Replace generic context with the article's second distinct factual
    # beat. Keep the proof to the first beat so the script advances instead of
    # repeating a vague line such as "this also situates the duo in the city".
    if len(selected_evidence)>=2:
        fact=_clean_narrative_text(selected_evidence[0])
        context=_clean_narrative_text(selected_evidence[1])
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

    # V65: use verified evidence, never synthetic padding, to reach the 70-word floor.
    if word_count < 70 and not focused_story and len(evidence) > len(selected_evidence):
        extra=_clean_narrative_text(evidence[len(selected_evidence)]).rstrip('.!?')
        if extra and extra not in fact_parts:
            fact_parts.append(extra)
            sections['proof']=_clean_narrative_text('. '.join(fact_parts)+'.')
            narration=_clean_narrative_text(' '.join(sections[k] for k in ('hook','context','proof','payoff','cta')))
            word_count=len(re.findall(r"[A-Za-zÀ-ÿ0-9']+",narration))

    estimated_seconds=max(20,min(60,round(word_count/2.55)))
    return {
        'title':headline,'narration':narration,'source':resolved_url or url,
        'source_name':source or str(topic.get('source') or 'Fonte da pauta'),'content_type':kind,
        'editorial_angle':angle,'editorial_hook':hook,
        'editorial_score':topic.get('editorial_score'),'editorial_decision':topic.get('editorial_decision','PRODUZIR'),
        'editorial_reason':topic.get('editorial_reason',''),'sections':sections,
        'evidence':evidence[:3],'source_headline':source_headline,'word_count':word_count,'estimated_seconds':estimated_seconds,
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
    """Create a branded cover fallback only; never use synthetic cards as footage."""
    im=Image.new('RGB',(1080,1920),(8,10,15)); d=ImageDraw.Draw(im)
    for y in range(1920): d.line((0,y,1080,y),fill=(10+int(18*y/1920),8,15+int(20*y/1920)))
    d.rectangle((65,90,1015,1830),outline=(170,25,40),width=3)
    d.text((80,120),'GTA OCULTO',font=font(42,True),fill=(230,40,55))
    y=690
    for line in wrap_text(d,title,font(70,True),880)[:5]: d.text((80,y),line,font=font(70,True),fill='white'); y+=88
    d.text((80,1760),'GTA 6 • DETALHES E CURIOSIDADES',font=font(30,True),fill='white')
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
        # Official store product grids often pass generic image-quality checks.
        # Reject unusually pale catalog-like assets before they enter the story pool.
        if white > 0.22 or (white + lightgray) > 0.48 or green > 0.48:
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

def _visual_fingerprint(path):
    """Cheap perceptual fingerprint used to reject near-duplicate stills before render."""
    try:
        im=Image.open(path).convert('L').resize((32,32))
        a=list(im.getdata())
        # Difference hash catches the same composition even after resize/crop.
        small=im.resize((9,8))
        px=list(small.getdata())
        dh=0
        for k in range(8*8):
            x=k%9; y=k//9
            if px[y*9+x] > px[y*9+x+1]:
                dh |= (1<<k)
        # Low-resolution luminance signature catches near-identical frames with
        # small compression/color changes that can evade a simple dHash.
        mean=sum(a)/max(1,len(a))
        sig=tuple(int((v-mean)/8) for v in a[::2])
        return dh,sig
    except Exception:
        return None

def _visual_distance(fp1,fp2):
    if not fp1 or not fp2: return 999
    dh1,s1=fp1; dh2,s2=fp2
    h=(dh1^dh2).bit_count()
    n=min(len(s1),len(s2))
    if not n: return h
    # Mean absolute normalized luminance difference.
    sad=sum(abs(s1[k]-s2[k]) for k in range(n))/n
    return h + sad*0.35

def _is_near_duplicate(fp,selected_fps):
    # Hard visual lock: once a composition is selected, a visually equivalent
    # still cannot re-enter the Short. Threshold is intentionally conservative.
    return any(_visual_distance(fp,x) <= 10.5 for x in selected_fps)

def select_visuals(paths, topic_title, count=10):
    if not paths: return []
    count=max(0,min(int(count),len(paths)))
    if count==0: return []
    plans=_scene_keywords(topic_title)[:count]
    chosen=[]; used=set(); selected_fps=[]
    fingerprints={}
    for idx,item in enumerate(paths):
        p=item['path'] if isinstance(item,dict) else item
        fingerprints[idx]=_visual_fingerprint(p)

    def accept(idx):
        if idx in used: return False
        fp=fingerprints.get(idx)
        if fp and _is_near_duplicate(fp,selected_fps):
            return False
        chosen.append(idx); used.add(idx)
        if fp: selected_fps.append(fp)
        return True

    for kws in plans:
        ranked=[]
        for idx,item in enumerate(paths):
            if idx in used: continue
            p=item['path'] if isinstance(item,dict) else item
            fp=fingerprints.get(idx)
            if fp and _is_near_duplicate(fp,selected_fps):
                continue
            txt=_asset_text(item)
            # Reject store/catalog imagery when the story is about characters or plot.
            # A high-quality image is not automatically a relevant image.
            label_url=(str(item.get('label',''))+' '+str(item.get('url',''))).lower() if isinstance(item,dict) else ''
            merchandise_terms=('shop','store','merch','t-shirt','tshirt','hoodie','hat','cap','mug','keychain','apparel','clothing','shirt','poster','backpack','jacket','sock')
            if any(term in label_url for term in merchandise_terms):
                continue
            hits=sum(1 for k in kws if k in txt)
            # Never fill the story with unrelated official assets merely to reach a count.
            if hits <= 0:
                continue
            ranked.append((hits, _image_quality(p), idx))
        if ranked:
            ranked.sort(key=lambda x:(x[0],x[1]),reverse=True)
            accept(ranked[0][2])

    # Fill only with perceptually unique assets. Never recycle a still just to
    # reach the requested count; fewer unique visuals is safer than a slideshow loop.
    if len(chosen)<count:
        remaining=[]
        for idx in range(len(paths)):
            if idx in used: continue
            fp=fingerprints.get(idx)
            if fp and _is_near_duplicate(fp,selected_fps):
                continue
            item=paths[idx]
            label_url=(str(item.get('label',''))+' '+str(item.get('url',''))).lower() if isinstance(item,dict) else ''
            merchandise_terms=('shop','store','merch','t-shirt','tshirt','hoodie','hat','cap','mug','keychain','apparel','clothing','shirt','poster','backpack','jacket','sock')
            if any(term in label_url for term in merchandise_terms):
                continue
            # Fallback assets may have opaque CDN URLs and empty alt text.
            # Keep all non-merchandise official assets as a last resort, but prefer
            # keyword-matched assets above; the renderer still deduplicates frames.
            remaining.append(idx)
        remaining.sort(key=lambda idx:_image_quality(paths[idx]['path'] if isinstance(paths[idx],dict) else paths[idx]),reverse=True)
        for idx in remaining:
            if accept(idx) and len(chosen)>=count:
                break

    print(f'[VISUAL_DEDUP] requested={count} input={len(paths)} selected={len(chosen)} rejected_near_duplicates={len(paths)-len(chosen)}',flush=True)
    return [paths[i]['path'] if isinstance(paths[i],dict) else paths[i] for i in chosen[:count]]

def research_official():
    facts=[]; images=[]
    for url in [ROCKSTAR_VI,ROCKSTAR_NEWS,'https://www.rockstargames.com/VI/downloads/videos']:
        try:
            r=fetch(url); r.raise_for_status(); soup=BeautifulSoup(r.text,'html.parser')
            text=' '.join(soup.stripped_strings)
            facts.append(text[:16000])
            # The general GTA VI landing page contains store/product merchandising.
            # Keep it for research text, but never use its images as story footage.
            if url != ROCKSTAR_VI:
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
        learning={'learned':False}
        if TREND_BRAIN:
            try:
                learning=TREND_BRAIN.recommend_editorial_profile() or {'learned':False}
            except Exception:
                learning={'learned':False}
        # Closed-loop editorial ranking: once the channel has enough evidence,
        # favor a proven hook style, but keep the effect deliberately small so
        # a genuinely strong new topic can still beat the learned pattern.
        learned_type=str(learning.get('preferred_hook_type','')).upper()
        current_type=TREND_BRAIN._hook_type(hook) if TREND_BRAIN and hasattr(TREND_BRAIN,'_hook_type') else ''
        learning_conf=float(learning.get('confidence',0) or 0)
        learning_bonus=0
        if learning.get('learned') and learned_type and current_type==learned_type:
            learning_bonus=round(5*learning_conf)
            editorial+=learning_bonus
        type_bonus=0
        preferred_type=str((learning.get('preferred_content_type') or {}).get('type','')).upper()
        if learning.get('learned') and preferred_type and str(kind).upper()==preferred_type:
            samples=int((learning.get('preferred_content_type') or {}).get('samples',0) or 0)
            type_conf=min(1.0,max(0.0,(samples-1)/4.0))
            type_bonus=round(4*type_conf)
            editorial+=type_bonus
        # Aprendizado de embalagem: título e ângulo entram apenas como desempate.
        title_pattern_bonus=0
        preferred_title=(learning.get('preferred_title_pattern') or {})
        candidate_title_pattern=''
        try:
            candidate_title_pattern=TREND_BRAIN._title_pattern(topic.get('title','')) if TREND_BRAIN else ''
        except Exception:
            candidate_title_pattern=''
        if learning.get('learned') and preferred_title and candidate_title_pattern==str(preferred_title.get('pattern','')):
            samples=int(preferred_title.get('samples',0) or 0)
            title_conf=min(1.0,max(0.0,(samples-1)/4.0))
            title_pattern_bonus=round(3*title_conf)
            editorial+=title_pattern_bonus

        angle_bonus=0
        preferred_angle=(learning.get('preferred_angle_type') or {})
        candidate_angle_type=''
        try:
            candidate_angle_type=TREND_BRAIN._angle_type(angle) if TREND_BRAIN else ''
        except Exception:
            candidate_angle_type=''
        if learning.get('learned') and preferred_angle and candidate_angle_type==str(preferred_angle.get('type','')):
            samples=int(preferred_angle.get('samples',0) or 0)
            angle_conf=min(1.0,max(0.0,(samples-1)/4.0))
            angle_bonus=round(3*angle_conf)
            editorial+=angle_bonus

        # Duration learning stays conservative: it is a tie-breaker, not a hard rule.
        duration_bonus=0
        preferred_duration=learning.get('preferred_duration') or {}
        if learning.get('learned') and preferred_duration:
            target_bucket=str(preferred_duration.get('bucket',''))
            # The editor's current default is 30-38s; use metadata only when available.
            candidate_bucket=str(topic.get('duration_bucket','') or '')
            if not candidate_bucket:
                try:
                    candidate_bucket=TREND_BRAIN._duration_bucket(topic.get('duration_seconds',0)) if TREND_BRAIN else ''
                except Exception:
                    candidate_bucket=''
            if target_bucket and candidate_bucket==target_bucket:
                dsamples=int(preferred_duration.get('samples',0) or 0)
                duration_conf=min(1.0,max(0.0,(dsamples-1)/4.0))
                duration_bonus=round(2*duration_conf)
                editorial+=duration_bonus
        item['editorial_score']=int(max(0,min(100,round(editorial))))
        item['editorial_angle']=angle
        item['editorial_hook']=hook
        item['editorial_learning']=learning
        item['editorial_learning_bonus']=learning_bonus+type_bonus+title_pattern_bonus+angle_bonus+duration_bonus
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
    """Create a branded cover fallback only; never use synthetic cards as footage."""
    im=Image.new('RGB',(1080,1920),(8,10,15)); d=ImageDraw.Draw(im)
    for y in range(1920): d.line((0,y,1080,y),fill=(10+int(18*y/1920),8,15+int(20*y/1920)))
    d.rectangle((65,90,1015,1830),outline=(170,25,40),width=3)
    d.text((80,120),'GTA OCULTO',font=font(42,True),fill=(230,40,55))
    y=690
    for line in wrap_text(d,title,font(70,True),880)[:5]: d.text((80,y),line,font=font(70,True),fill='white'); y+=88
    d.text((80,1760),'GTA 6 • DETALHES E CURIOSIDADES',font=font(30,True),fill='white')
    im.save(path,quality=90)


def download_visuals(urls,outdir,title):
    """Collect visuals with a hard time budget so slow sources cannot stall production."""
    outdir.mkdir(parents=True,exist_ok=True); candidates=[]; seen=set()
    deadline=time.monotonic()+55.0
    for i,item in enumerate(urls[:36]):
        if time.monotonic()>=deadline:
            break
        u=item.get('url') if isinstance(item,dict) else item
        label=item.get('label','') if isinstance(item,dict) else ''
        # Do not ingest store/catalog URLs as narrative footage.
        _url_label=(str(u)+' '+str(label)).lower()
        if any(term in _url_label for term in ('/store/','rockstar-games-gear','merchandise','product-detail','product_image','/products/','shopify','t-shirt','tshirt','hoodie','apparel','clothing','keychain','backpack','mug')):
            continue
        raw=None
        try:
            raw=outdir/f'raw_{i}'
            with requests.get(u,headers={'User-Agent':UA,'Accept-Encoding':'identity'},timeout=(4,8),stream=True) as r:
                r.raise_for_status()
                ctype=(r.headers.get('content-type') or '').lower()
                if 'image' not in ctype and not u.lower().split('?')[0].endswith(('.jpg','.jpeg','.png','.webp','.avif')):
                    continue
                total=0
                with raw.open('wb') as f:
                    for chunk in r.iter_content(256*1024):
                        if time.monotonic()>=deadline:
                            raise TimeoutError('limite global de 45s para coleta visual atingido')
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
            slug=''.join(ch if ch.isalnum() else '_' for ch in (label or u.rsplit('/',1)[-1].split('?',1)[0]).lower())[:42].strip('_')
            p=outdir/f'good_{len(candidates):02d}_{slug}.jpg'; im.save(p,quality=88)
            im.close(); raw.unlink(missing_ok=True)
            key=(p.stat().st_size,label[:80])
            if key in seen: p.unlink(missing_ok=True); continue
            seen.add(key); candidates.append({'score':score,'path':p,'label':label,'url':u})
        except Exception:
            if raw:
                try: raw.unlink(missing_ok=True)
                except Exception: pass
    candidates.sort(key=lambda x:x['score'],reverse=True)
    # Never add synthetic fallback graphics to the footage pool. Missing real images
    # should reduce visual variety or fail QA, not become placeholder scenes.
    return candidates[:18]


def _edge_white_ratio(im):
    """Measure compressed near-white source borders at the outer frame edges."""
    try:
        small=im.convert('RGB').resize((90,160),Image.Resampling.BILINEAR)
        pixels=list(small.getdata())
        def is_edge_white(pixel):
            # JPEG/antialiasing often reduces source-white lettering below 235.
            return min(pixel)>220 and max(pixel)-min(pixel)<42
        left=[pixels[y*90+x] for y in range(160) for x in range(3)]
        right=[pixels[y*90+x] for y in range(160) for x in range(87,90)]
        return max(sum(is_edge_white(p) for p in left)/max(1,len(left)),
                   sum(is_edge_white(p) for p in right)/max(1,len(right)))
    except Exception:
        return 0.0


def _smart_crop(im,W,H,variant=0):
    im=im.convert('RGB')
    # Detect edge overlays even when the underlying asset is landscape rather
    # than already cropped to 9:16. Those assets can contain a thumbnail border
    # or partially clipped source-logo at one side.
    source_edge_white=_edge_white_ratio(im)
    edge_artifact=source_edge_white>=0.035
    scale=max(W/im.width,H/im.height)
    if edge_artifact:
        scale*=1.30 if im.width/im.height <= (W/H)*1.08 else 1.10
    nw,nh=int(im.width*scale),int(im.height*scale)
    big=im.resize((nw,nh),Image.Resampling.LANCZOS)
    max_left=max(0,nw-W); max_top=max(0,nh-H)
    positions=[0.01,0.16,0.32,0.50,0.68,0.84,0.99] if edge_artifact else [0.08,0.28,0.50,0.72,0.90]
    best=None
    for frac in positions:
        left=int(max_left*frac)
        top=int(max_top*(0.12 if edge_artifact else 0.50))
        crop=big.crop((left,top,left+W,top+H))
        sm=crop.resize((90,160),Image.Resampling.BILINEAR)
        px=list(sm.getdata()); n=len(px)
        white=sum(1 for r,g,b in px if r>242 and g>242 and b>242)/n
        gray=sum(1 for r,g,b in px if abs(r-g)<5 and abs(g-b)<5 and 150<r<242)/n
        spread=sum(max(p)-min(p) for p in px)/n
        # Edge contamination dominates the score: retaining even a thin white
        # strip or clipped lettering on a frame edge is an editorial defect.
        edge_white=_edge_white_ratio(crop)
        score=(1-white-gray)*80 + min(spread/35,2)*20 - edge_white*420
        if best is None or score>best[0]:
            best=(score,crop)
    result=best[1] if best else big.crop((max(0,max_left//2),max(0,max_top//2),max(0,max_left//2)+W,max(0,max_top//2)+H))
    # Final edge-safe pass: if a bright border remains, crop inward further and
    # choose the least contaminated position before considering image detail.
    if _edge_white_ratio(result)>=0.035:
        zoom=1.22
        zw,zh=int(W*zoom),int(H*zoom)
        enlarged=result.resize((zw,zh),Image.Resampling.LANCZOS)
        zx=max(0,zw-W); zy=max(0,zh-H)
        safer=[]
        for xf in (0.0,0.25,0.50,0.75,1.0):
            candidate=enlarged.crop((int(zx*xf),int(zy*0.35),int(zx*xf)+W,int(zy*0.35)+H))
            safer.append((_edge_white_ratio(candidate),candidate))
        result=min(safer,key=lambda item:item[0])[1]
    return result


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
    # Final trim after all zoom/pan operations: source thumbnails can carry a
    # compressed white border and clipped source lettering at the extreme edge.
    if _edge_white_ratio(im)>=0.035:
        trim=int(W*0.08)
        cleaned=im.crop((trim,0,W-trim,H)).resize((W,H),Image.Resampling.LANCZOS)
        im.close()
        im=cleaned
        if _edge_white_ratio(im)>=0.06:
            trim2=int(W*0.05)
            cleaned=im.crop((trim2,0,W-trim2,H)).resize((W,H),Image.Resampling.LANCZOS)
            im.close()
            im=cleaned
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


def _compress_long_tts_pauses(audio_path, word_cues=None, min_silence=0.70, keep_silence=0.14, threshold_db=-45):
    """Compacta pausas longas no TTS e desloca os WordBoundary pela mesma duração removida."""
    path=Path(audio_path)
    temp=path.with_name(path.stem+'_pausefix'+path.suffix)
    try:
        ff=_ffmpeg_executable()
        probe=subprocess.run(
            ['ffprobe','-v','error','-show_entries','format=duration','-of','default=nw=1:nk=1',str(path)],
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=25,check=True
        )
        duration=float(probe.stdout.strip())
        detected=subprocess.run(
            [ff,'-hide_banner','-i',str(path),'-vn','-af',f'silencedetect=noise={threshold_db}dB:d={min_silence:.3f}','-f','null','-'],
            stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True,timeout=60
        )
        starts=[float(x) for x in re.findall(r'silence_start:\s*([0-9.]+)',detected.stderr)]
        ends=[float(x) for x in re.findall(r'silence_end:\s*([0-9.]+)',detected.stderr)]
        if len(ends)<len(starts):
            ends.append(duration)
        ends=ends[:len(starts)]
        cuts=[]
        for start,end in zip(starts,ends):
            start=max(0.0,min(start,duration)); end=max(start,min(end,duration))
            if end-start < min_silence:
                continue
            cut_start=min(end,start+keep_silence)
            # Preserve a tiny natural tail instead of cutting audio flush at EOF.
            cut_end=max(cut_start,min(end,duration-0.08) if end>=duration-0.10 else end)
            if cut_end-cut_start>0.04:
                cuts.append((cut_start,cut_end))
        if not cuts:
            return path,list(word_cues or [])
        cuts.sort()
        merged=[]
        for a,b in cuts:
            if merged and a<=merged[-1][1]+0.01:
                merged[-1]=(merged[-1][0],max(merged[-1][1],b))
            else:
                merged.append((a,b))
        cuts=merged
        segments=[]; cursor=0.0
        for a,b in cuts:
            if a>cursor+0.025:
                segments.append((cursor,a))
            cursor=max(cursor,b)
        if duration>cursor+0.025:
            segments.append((cursor,duration))
        if len(segments)<2:
            return path,list(word_cues or [])
        graph=[]
        for i,(a,b) in enumerate(segments):
            graph.append(f'[0:a]atrim=start={a:.6f}:end={b:.6f},asetpts=PTS-STARTPTS[a{i}]')
        graph.append(''.join(f'[a{i}]' for i in range(len(segments)))+f'concat=n={len(segments)}:v=0:a=1[outa]')
        temp.unlink(missing_ok=True)
        run_cmd([ff,'-hide_banner','-loglevel','error','-y','-i',str(path),
                 '-filter_complex',';'.join(graph),'-map','[outa]','-vn',
                 '-c:a','libmp3lame','-q:a','3',str(temp)],120)
        if not temp.exists() or temp.stat().st_size<1000:
            raise RuntimeError('o áudio compactado não foi gerado corretamente')
        removed=sum(b-a for a,b in cuts)
        adjusted=[]
        for cue in (word_cues or []):
            c=dict(cue)
            try:
                start=float(c.get('start',0.0)); old_len=max(0.0,float(c.get('duration',0.0)))
                end=start+old_len
                shift=0.0; overlap=0.0
                for a,b in cuts:
                    if start>a:
                        shift+=max(0.0,min(start,b)-a)
                    overlap+=max(0.0,min(end,b)-max(start,a))
                c['start']=round(max(0.0,start-shift),4)
                c['duration']=round(max(0.03,old_len-overlap),4)
            except Exception:
                pass
            adjusted.append(c)
        os.replace(str(temp),str(path))
        print(f'[TTS_PAUSE_REPAIR] gaps={len(cuts)} removed={removed:.2f}s original={duration:.2f}s',flush=True)
        return path,adjusted
    except Exception as e:
        try: temp.unlink(missing_ok=True)
        except Exception: pass
        print(f'[TTS_PAUSE_REPAIR] skipped error={type(e).__name__}:{str(e)[:220]}',flush=True)
        return path,list(word_cues or [])


async def make_tts(text,path):
    """Gera narração PT-BR: tenta Edge-TTS e usa gTTS como fallback gratuito."""
    last=None
    if edge_tts is not None:
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
                        if 'wordboundary' in low or low in ('word','wordbound'):
                            try:
                                word=str(chunk.get('text') or chunk.get('word') or '').strip()
                                offset=chunk.get('offset',chunk.get('start',0))
                                dur=chunk.get('duration',chunk.get('length',0))
                                cue_start=float(offset)/10_000_000.0
                                cue_duration=float(dur)/10_000_000.0
                                if word:
                                    cues.append({'word':word,'start':cue_start,'duration':cue_duration})
                            except Exception:
                                pass
                if path.exists() and path.stat().st_size>1000:
                    expected_words=_caption_words(text)
                    # Without word-boundary events we cannot prove that Edge-TTS
                    # completed the approved narration. Retry/fall back instead of
                    # accepting audio whose spoken ending cannot be verified.
                    if expected_words and not cues:
                        raise RuntimeError(
                            'Edge-TTS não retornou eventos de palavras; integridade da narração não verificável'
                        )
                    if cues and expected_words:
                        expected_last=_caption_clean_word(expected_words[-1])
                        actual_last=_caption_clean_word(cues[-1].get('word',''))
                        if expected_last and actual_last and expected_last!=actual_last:
                            raise RuntimeError(
                                f'Edge-TTS parece truncado: último evento={actual_last!r}; esperado={expected_last!r}'
                            )
                    return cues
                last=RuntimeError('Edge-TTS terminou sem gerar áudio válido')
            except Exception as e:
                last=e
                try:
                    if path.exists(): path.unlink()
                except Exception:
                    pass
    else:
        last=RuntimeError('edge-tts não disponível no servidor')

    # Fallback gratuito em português brasileiro. Sem WordBoundary, o pipeline
    # usa a duração real do áudio para sincronizar as legendas.
    try:
        from gtts import gTTS
        try:
            if path.exists(): path.unlink()
        except Exception:
            pass
        gTTS(text=str(text), lang='pt', tld='com.br', slow=False).save(str(path))
        if path.exists() and path.stat().st_size>1000:
            print('[TTS] fallback=gTTS lang=pt tld=com.br', flush=True)
            return []
        raise RuntimeError('gTTS terminou sem gerar áudio válido')
    except Exception as fallback_error:
        raise RuntimeError(f'falha na narração Edge-TTS={last}; fallback gTTS={fallback_error}') from fallback_error

def _safe_filename(name):
    return re.sub(r'[^a-zA-Z0-9._-]+','_',name).strip('_')[:100]


def _http_total_size(url):
    headers={'User-Agent':UA,'Accept-Encoding':'identity'}
    try:
        r=requests.head(url,headers=headers,timeout=5,allow_redirects=True)
        n=int(r.headers.get('content-length','0') or 0)
        if n: return n
    except Exception:
        pass
    try:
        r=requests.get(url,headers={**headers,'Range':'bytes=0-0'},timeout=(5,8),stream=True)
        cr=r.headers.get('content-range','')
        m=re.search(r'/([0-9]+)$',cr)
        if r.status_code==206 and m: return int(m.group(1))
    except Exception:
        pass
    return 0


def _http_range(url,start,end):
    if end < start: return b''
    expected=end-start+1
    headers={'User-Agent':UA,'Accept-Encoding':'identity','Range':f'bytes={start}-{end}'}
    r=requests.get(url,headers=headers,timeout=(5,20),stream=False)
    if r.status_code != 206:
        raise RuntimeError(f'CDN não aceitou Range HTTP (status {r.status_code}).')
    content_range=r.headers.get('Content-Range','')
    match=re.fullmatch(r'bytes\s+(\d+)-(\d+)/(\d+|\*)',content_range.strip(),re.I)
    if not match:
        raise RuntimeError(f'CDN retornou Content-Range inválido: {content_range!r}')
    got_start,got_end=int(match.group(1)),int(match.group(2))
    if got_start!=start or got_end!=end:
        raise RuntimeError(f'CDN retornou faixa errada: pediu {start}-{end}, recebeu {got_start}-{got_end}.')
    if len(r.content)!=expected:
        raise RuntimeError(f'Faixa HTTP truncada: pediu {expected} bytes, recebeu {len(r.content)}.')
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
        comp=vals[4]; crc=vals[7]; csize=vals[8]; usize=vals[9]; fn=vals[10]; extra=vals[11]; comm=vals[12]; local=vals[16]
        nameb=cd[p+46:p+46+fn]
        try: name=nameb.decode('utf-8')
        except Exception: name=nameb.decode('cp437','replace')
        entries.append({'name':name,'compression':comp,'crc32':crc,'compressed':csize,'size':usize,'local':local})
        p += 46+fn+extra+comm
    if len(entries)<3: raise RuntimeError(f'ZIP oficial expôs apenas {len(entries)} arquivos.')
    return total,entries


def _remote_zip_extract(url,entry,target):
    """Extract one selected ZIP member with bounded RAM (2 MiB network chunks)."""
    local=_http_range(url,entry['local'],entry['local']+29)
    if local[:4] != b'PK\x03\x04':
        raise RuntimeError(f'Cabeçalho local inválido: {entry["name"]}')
    _,ver,flags,method,mtime,mdate,crc,csize,usize,fn,extra=struct.unpack('<4s5H3L2H',local)
    data_start=entry['local']+30+fn+extra
    data_end=data_start+entry['compressed']-1
    chunk_size=2*1024*1024
    written=0
    crc_actual=0
    dec=zlib.decompressobj(-15) if method==8 else None
    if method not in (0,8):
        raise RuntimeError(f'Compressão ZIP não suportada em {entry["name"]}: {method}')
    try:
        with target.open('wb') as out:
            cursor=data_start
            while cursor<=data_end:
                last=min(cursor+chunk_size-1,data_end)
                comp=_http_range(url,cursor,last)
                if not comp:
                    raise RuntimeError(f'Bloco ZIP vazio em {entry["name"]}')
                cursor=last+1
                if method==0:
                    out.write(comp)
                    written+=len(comp)
                    crc_actual=zlib.crc32(comp,crc_actual)
                    continue
                pending=comp
                while pending:
                    block=dec.decompress(pending,chunk_size)
                    pending=dec.unconsumed_tail
                    if block:
                        out.write(block)
                        written+=len(block)
                        crc_actual=zlib.crc32(block,crc_actual)
                    if not block and pending:
                        raise RuntimeError(f'Descompressão ZIP sem progresso em {entry["name"]}')
            if dec is not None:
                tail=dec.flush()
                if tail:
                    out.write(tail)
                    written+=len(tail)
                    crc_actual=zlib.crc32(tail,crc_actual)
        if entry.get('size') and written!=entry['size']:
            raise RuntimeError(f'Tamanho inesperado em {entry["name"]}: {written} de {entry["size"]} bytes.')
        expected_crc=entry.get('crc32')
        if expected_crc is not None and (crc_actual & 0xffffffff)!=expected_crc:
            raise RuntimeError(f'CRC32 inválido em {entry["name"]}: esperado={expected_crc:08x}, obtido={crc_actual & 0xffffffff:08x}; extração corrompida.')
    except Exception:
        try: target.unlink(missing_ok=True)
        except Exception: pass
        raise

def _is_rating_disclaimer_frame(path):
    """Detect ESRB/rating/disclaimer cards without OCR.
    These frames have a very distinctive structure: a mostly black frame with
    one or more wide, near-white horizontal bands containing dark text.
    """
    try:
        im=Image.open(path).convert('L')
        w,h=im.size
        if w < 120 or h < 120:
            return False
        # Downsample so the check is cheap on Render Free.
        im.thumbnail((240,426))
        pix=im.load()
        total=max(1,im.width*im.height)
        white_ratio=0.0; black_ratio=0.0; runs=0; run=0
        # Count white/black pixels and wide horizontal white bands without
        # adding numpy/OpenCV to the Render dependency set.
        for y in range(im.height):
            white_row=0
            for x in range(im.width):
                v=pix[x,y]
                if v>=245:
                    white_row+=1
                    white_ratio+=1
                if v<=18:
                    black_ratio+=1
            row_ratio=white_row/max(1,im.width)
            if row_ratio>=0.82:
                run+=1
            else:
                if run>=12: runs+=1
                run=0
        if run>=12: runs+=1
        white_ratio/=total
        black_ratio/=total
        # ESRB cards usually have several broad white bands plus a black field.
        return bool(runs>=2 and black_ratio>=0.28 and 0.10<=white_ratio<=0.55)
    except Exception:
        return False


def _video_contains_rating_disclaimer(path, sample_fps=2.0):
    """Return True when a video contains an ESRB/rating/disclaimer card."""
    p=Path(path)
    if not p.exists():
        return False
    tmp=Path(str(p)+'.rating_audit')
    tmp.mkdir(parents=True,exist_ok=True)
    try:
        ff=_ffmpeg_executable()
        run_cmd([
            ff,'-loglevel','error','-y','-i',str(p),
            '-vf',f'fps={sample_fps}:round=down,scale=240:426:force_original_aspect_ratio=decrease',
            '-q:v','5',str(tmp/'f_%04d.jpg')
        ],25)
        frames=sorted(tmp.glob('f_*.jpg'))
        bad=sum(1 for fp in frames if _is_rating_disclaimer_frame(fp))
        # Require at least two sampled frames so a normal transition frame does
        # not discard a valid gameplay clip.
        return bad>=2
    except Exception:
        return False
    finally:
        try: shutil.rmtree(tmp,ignore_errors=True)
        except Exception: pass


def _download_official_rockstar_cdn_proxies(cache, jid=None, limit_per_video=13):
    """Extract short moving clips from Rockstar's own public CDN without downloading a full trailer."""
    cache=Path(cache)
    cache.mkdir(parents=True,exist_ok=True)
    ff=_ffmpeg_executable()
    # Rockstar's official video page exposes the Extended Look under this media ID.
    # Use ranged, time-seeked downloads so only short segments are fetched.
    media_id='rk721912'
    # Sample across the full official Extended Look so the editor has enough
    # independent motion sources and does not fill most of a Short with stills.
    starts=[72.0,180.0,300.0,365.0,480.0,600.0,672.0,790.0,900.0,1015.0,1130.0,1260.0,1390.0]
    resolutions=['720p','1080p','2160p']
    accepted_starts=set()
    next_index=0
    for p in cache.glob('rockstar_real_v251_*.mp4'):
        m=re.search(r'_(\d+)\.mp4$',p.name)
        if m: next_index=max(next_index,int(m.group(1))+1)
    proxies=[]
    # Reuse previously verified CDN sources by source timestamp.
    for p in sorted(cache.glob('rockstar_real_v251_*.mp4')):
        try:
            meta=json.loads(p.with_suffix('.json').read_text(encoding='utf-8'))
            if meta.get('source')!='rockstar_cdn' or meta.get('start') is None:
                continue
            source_start=float(meta['start'])
            if source_start in accepted_starts:
                continue
            probe=_probe_media(p)
            if probe.get('ok') and probe.get('video') and float(probe.get('duration') or 0)>=4.0 and p.stat().st_size>20000:
                accepted_starts.add(source_start)
                proxies.append(p)
        except Exception:
            continue
    failures=[]
    for resolution in resolutions:
        url=f'https://videos-rockstargames-com.akamaized.net/v4/{media_id}/flv/en-us-{resolution}.mp4'
        for i,start in enumerate(starts):
            if len(proxies)>=int(limit_per_video):
                break
            # A lower-resolution retry must not create another filename for
            # footage from a timestamp already accepted at a prior resolution.
            if start in accepted_starts:
                continue
            target=cache/f'rockstar_real_v251_{next_index}.mp4'
            next_index+=1
            try:
                if jid:
                    update_job(jid,log=f'Obtendo trecho de vídeo oficial Rockstar ({resolution}, amostra {i+1}/{len(starts)})...')
                headers='Referer: https://www.rockstargames.com/\r\nUser-Agent: '+UA+'\r\n'
                # Input-side -ss lets FFmpeg request the selected byte range instead of
                # downloading the entire 26-minute source first.
                run_cmd([
                    ff,'-hide_banner','-loglevel','error','-y','-threads:v','1',
                    '-rw_timeout','30000000','-headers',headers,
                    '-ss',f'{start:.3f}','-i',url,'-t','8.5',
                    '-vf','scale=320:568:force_original_aspect_ratio=increase,crop=320:568,setsar=1,fps=12',
                    '-an','-c:v','libx264','-preset','ultrafast','-crf','31',
                    '-threads','1','-filter_threads','1','-filter_complex_threads','1',
                    '-x264-params','threads=1:lookahead-threads=1:rc-lookahead=0:sync-lookahead=0',
                    '-pix_fmt','yuv420p','-movflags','+faststart',str(target)
                ],120)
                pprobe=_probe_media(target) if target.exists() else {'ok':False,'duration':0,'video':[],'error':'arquivo não criado'}
                pduration=float(pprobe.get('duration') or 0)
                if not pprobe.get('ok') or not pprobe.get('video') or pduration<4.0 or target.stat().st_size<20000:
                    raise RuntimeError(f'trecho inválido duration={pduration:.2f}s bytes={target.stat().st_size if target.exists() else 0}; {pprobe.get("error","")}')
                if _video_contains_rating_disclaimer(target):
                    target.unlink(missing_ok=True)
                    raise RuntimeError('trecho descartado por tela de classificação/disclaimer')
                target.with_suffix('.json').write_text(
                    json.dumps({'source':'rockstar_cdn','start':float(start),'resolution':resolution,'duration':pduration},ensure_ascii=False),
                    encoding='utf-8'
                )
                proxies.append(target)
                accepted_starts.add(start)
                print(f'[OFFICIAL_ROCKSTAR_CDN] accepted={target.name} resolution={resolution} start={start:.1f}s duration={pduration:.2f}s',flush=True)
            except Exception as e:
                try: target.unlink(missing_ok=True)
                except Exception: pass
                reason=f'{resolution} @ {start:.1f}s: {str(e)[:220]}'
                failures.append(reason)
                print(f'[OFFICIAL_ROCKSTAR_CDN] rejected {reason}',flush=True)
                # If the first seek cannot open a resolution URL, test the next
                # resolution instead of retrying the same unavailable asset 5 times.
                if i == 0:
                    break
        if len(proxies)>=int(limit_per_video):
            break
    if len(proxies)<2:
        raise RuntimeError(f'CDN oficial da Rockstar forneceu apenas {len(proxies)} trechos válidos; necessários pelo menos 2. Últimos erros: {" | ".join(failures[-5:])}')
    print(f'[OFFICIAL_ROCKSTAR_CDN] ready proxies={len(proxies)}',flush=True)
    return proxies



def download_official_video_clips(outdir, jid=None):
    """Prepare a bounded pool of safe official clips and reject rating/disclaimer cards."""
    outdir.mkdir(parents=True, exist_ok=True)
    cache=WORK/'official_video_cache'
    cache.mkdir(parents=True, exist_ok=True)

    cached=[]
    cached_source_ids=set()
    for p in sorted(cache.glob('rockstar_real_v251_*.mp4')):
        meta_path=p.with_suffix('.json')
        try:
            meta=json.loads(meta_path.read_text(encoding='utf-8'))
            if meta.get('source')!='rockstar_cdn' or meta.get('start') is None:
                p.unlink(missing_ok=True); meta_path.unlink(missing_ok=True); continue
            source_id='cdn:'+str(round(float(meta['start']),1))
            if source_id in cached_source_ids:
                p.unlink(missing_ok=True); meta_path.unlink(missing_ok=True); continue
            if p.stat().st_size <= 20000:
                p.unlink(missing_ok=True); meta_path.unlink(missing_ok=True)
                continue
            probe=_probe_media(p)
            seconds=float(probe.get('duration') or 0)
            if not probe.get('ok') or not probe.get('video') or seconds < 4.0:
                print(f'[VIDEO_CACHE] removing_short={p.name} duration={seconds:.2f}s minimum=4.0s error={probe.get("error","no video or too short")}',flush=True)
                p.unlink(missing_ok=True); meta_path.unlink(missing_ok=True)
                continue
            cached.append(p)
            cached_source_ids.add(source_id)
        except Exception as e:
            print(f'[VIDEO_CACHE] removing_unreadable={p.name} error={str(e)[:180]}',flush=True)
            try: p.unlink(missing_ok=True)
            except Exception: pass
            try: meta_path.unlink(missing_ok=True)
            except Exception: pass
    # Prefer eight independent motion sources for Shorts. Four sources proved
    # insufficient in real renders: extracted frames were technically distinct
    # but kept showing the same characters/shots. Build a broader official pool
    # before falling back to still frames or blocking the timeline.
    target_clips = 13
    if len(cached) >= target_clips:
        return cached[:target_clips]
    try:
        if jid:
            update_job(jid,log='Lendo catálogo oficial da Rockstar e filtrando telas ESRB/disclaimers...')
        total,entries=_remote_zip_entries(ROCKSTAR_VIDEO_ZIP)
        media=[e for e in entries if e['name'].lower().endswith(('.mp4','.mov','.m4v'))]
        if len(media) < 2:
            raise RuntimeError(f'O pacote oficial possui apenas {len(media)} vídeos utilizáveis; são necessários pelo menos 2.')

        preferred=[]
        for key in ('Jason','Lucia','Cal','Boobie','Raul','Brian','Real','Dre'):
            preferred += [e for e in media if key.lower() in Path(e['name']).stem.lower() and e not in preferred]
        candidates=preferred+[e for e in media if e not in preferred]

        ff=_ffmpeg_executable()
        safe=list(cached)
        used_names={p.name for p in safe}
        candidate_failures=[]
        next_index=0
        for p in cache.glob('rockstar_real_v251_*.mp4'):
            m=re.search(r'_(\d+)\.mp4$',p.name)
            if m:
                next_index=max(next_index,int(m.group(1))+1)

        for entry in candidates:
            if len(safe) >= target_clips:
                break
            idx=next_index
            next_index += 1
            target=cache/f'rockstar_real_v251_{idx}.mp4'
            raw=cache/f'raw_v251_{idx}.mp4'
            try:
                if jid:
                    update_job(jid,log=f'Baixando clipe oficial para revisão visual: {Path(entry["name"]).stem}...')
                _remote_zip_extract(ROCKSTAR_VIDEO_ZIP,entry,raw)
                raw_probe=_probe_media(raw)
                raw_duration=float(raw_probe.get('duration') or 0)
                if not raw_probe.get('ok') or not raw_probe.get('video') or raw_duration < 4.0:
                    raise RuntimeError(f'fonte extraída curta/inválida: duration={raw_duration:.2f}s; mínimo 4.0s; bytes={raw.stat().st_size if raw.exists() else 0}; {raw_probe.get("error","sem stream de vídeo")}')
                if jid:
                    update_job(jid,log=f'Convertendo fonte validada ({raw_duration:.1f}s) para proxy leve 320x568...')
                # First try accurate output-side seeking. Some MP4 sources in the
                # official ZIP have edit lists/keyframes that make input-side
                # -ss return a tiny 0.2–0.7s proxy despite a longer source.
                proxy_errors=[]
                for attempt in range(2):
                    target.unlink(missing_ok=True)
                    seek_args=(['-ss','0.8'] if attempt==0 else [])
                    cmd=[
                        ff,'-hide_banner','-loglevel','error','-y','-threads:v','1',
                        *seek_args,'-i',str(raw),'-t','8.5',
                        '-vf','scale=320:568:force_original_aspect_ratio=increase,crop=320:568,setsar=1,fps=12',
                        '-an','-c:v','libx264','-preset','ultrafast','-crf','31',
                        '-threads','1','-filter_threads','1','-filter_complex_threads','1',
                        '-x264-params','threads=1:lookahead-threads=1:rc-lookahead=0:sync-lookahead=0',
                        '-pix_fmt','yuv420p','-movflags','+faststart',str(target)
                    ]
                    run_cmd(cmd,90)
                    proxy_probe=_probe_media(target) if target.exists() else {'ok':False,'duration':0,'video':[],'error':'arquivo não criado'}
                    proxy_duration=float(proxy_probe.get('duration') or 0)
                    if target.exists() and target.stat().st_size>20000 and proxy_probe.get('ok') and proxy_probe.get('video') and proxy_duration>=4.0:
                        break
                    proxy_errors.append(f'tentativa {attempt+1}: {proxy_duration:.2f}s; {proxy_probe.get("error","sem stream de vídeo")}')
                if not target.exists() or target.stat().st_size<=20000 or not proxy_probe.get('ok') or not proxy_probe.get('video') or proxy_duration<4.0:
                    raise RuntimeError(f'proxy curto/inválido após 2 tentativas; proxy={proxy_duration:.2f}s, mínimo=4.0s; fonte={raw_duration:.2f}s; '+ ' | '.join(proxy_errors))
                if _video_contains_rating_disclaimer(target):
                    if jid:
                        update_job(jid,log=f'Filtro visual: descartando clipe com tela ESRB/disclaimer — {Path(entry["name"]).stem}')
                    target.unlink(missing_ok=True)
                    continue
                safe.append(target)
                used_names.add(target.name)
            except Exception as e:
                reason=f'{Path(entry["name"]).stem}: {str(e)[:260]}'
                candidate_failures.append(reason)
                print(f'[OFFICIAL_CLIP_REJECTED] {reason}',flush=True)
                if jid:
                    update_job(jid,log=f'Clipe oficial ignorado: {reason[:300]}')
                try:
                    target.unlink(missing_ok=True)
                except Exception:
                    pass
                # The official ZIP has repeatedly returned extracted assets without
                # a valid video stream. Stop probing the whole catalogue after a few
                # failures and switch to the ranged-download CDN path.
                if len(candidate_failures) >= 4 and len(safe) < target_clips:
                    print(
                        f'[OFFICIAL_VIDEO_ZIP] early_fallback invalid_candidates={len(candidate_failures)} '
                        f'valid_cached={len(safe)} target={target_clips}',
                        flush=True
                    )
                    break
            finally:
                try:
                    raw.unlink(missing_ok=True)
                except Exception:
                    pass

        safe=[p for p in safe if p.exists() and p.stat().st_size>20000]
        if len(safe) < target_clips:
            details=' | '.join(candidate_failures[-6:]) or 'nenhum detalhe de rejeição registrado'
            raise RuntimeError(
                f'Apenas {len(safe)} de {target_clips} fontes oficiais com vídeo válido foram preparadas. '
                f'Acionando fallback para obter material em movimento. Últimas falhas: {details}'
            )
        return safe[:target_clips]
    except Exception as e:
        zip_error=str(e)[:900]
        print(f'[OFFICIAL_VIDEO_ZIP] insufficient valid motion clips: {zip_error}; trying Rockstar official CDN range-download fallback',flush=True)
        try:
            return _download_official_rockstar_cdn_proxies(cache,jid=jid,limit_per_video=13)
        except Exception as rockstar_error:
            raise RuntimeError(
                'Não foi possível obter vídeos oficiais utilizáveis. '
                f'Pacote de downloads: {zip_error}. Fallback CDN oficial: {str(rockstar_error)[:900]}'
            )


def _video_relevance(path,title):
    text=(path.stem+' '+title).lower()
    score=0
    groups=[('jason',12),('lucia',12),('vice',8),('leonida',8),('cal',4),('boobie',4),('raul',4),('brian',4),('real',4),('dre',4),('cover',1)]
    for k,v in groups:
        if k in text:
            score += v
    return score


def select_video_clips(videos,title,count=5):
    ranked=sorted(videos,key=lambda p:_video_relevance(p,title),reverse=True)
    return ranked[:count]


def _expand_video_clips_into_distinct_windows(video_clips, jobdir, windows_per_clip=3):
    """Split each source into valid, non-overlapping motion segments.

    Calculate segment count from the actual source duration instead of assuming
    every downloaded proxy is 8.5s. Seeking is input-side so FFmpeg extracts
    the intended section, and each segment is probed before it enters the pool.
    """
    ff=_ffmpeg_executable()
    outdir=Path(jobdir)/'video_windows'
    outdir.mkdir(parents=True,exist_ok=True)
    clips=[Path(p) for p in (video_clips or []) if p]
    expanded=[]
    for ci,clip in enumerate(clips):
        try:
            source_probe=_probe_media(clip)
            source_duration=float(source_probe.get('duration') or 0)
            if not source_probe.get('ok') or not source_probe.get('video') or source_duration < 4.0:
                print(
                    f'[VIDEO_WINDOWS] source_rejected={clip.name} duration={source_duration:.2f}s minimum=4.0s '
                    f'error={source_probe.get("error","no video or clip too short")}',
                    flush=True
                )
                continue
            # Create distinct 2–4.3s motion segments. Never reuse a clip too short
            # for two independent scenes: looping 1s sources creates visible repetition.
            count=min(max(1,int(windows_per_clip)),max(1,int(source_duration//2.0)))
            if count < 2:
                print(f'[VIDEO_WINDOWS] source_too_short={clip.name} duration={source_duration:.2f}s; skipped',flush=True)
                continue
            window_seconds=source_duration/count
            for wi in range(count):
                start=wi*window_seconds
                dst=outdir/f'{clip.stem}_window_{wi+1:02d}.mp4'
                try:
                    # Always recreate to avoid stale files from a different segmentation rule.
                    dst.unlink(missing_ok=True)
                    run_cmd([
                        ff,'-loglevel','error','-y',
                        '-ss',f'{start:.3f}','-i',str(clip),'-t',f'{window_seconds:.3f}',
                        '-vf','scale=320:568:force_original_aspect_ratio=increase,crop=320:568,setsar=1,fps=12',
                        '-an','-c:v','libx264','-preset','ultrafast','-crf','28',
                        '-threads','1','-filter_threads','1','-filter_complex_threads','1',
                        '-x264-params','threads=1:lookahead-threads=1:rc-lookahead=0:sync-lookahead=0',
                        '-pix_fmt','yuv420p','-movflags','+faststart',str(dst)
                    ],45)
                    if not dst.exists() or dst.stat().st_size < 5000:
                        raise RuntimeError('arquivo do segmento ausente ou pequeno')
                    segment_probe=_probe_media(dst)
                    segment_duration=float(segment_probe.get('duration') or 0)
                    if segment_probe.get('ok') and segment_probe.get('video') and segment_duration >= 2.0:
                        expanded.append(dst)
                    else:
                        dst.unlink(missing_ok=True)
                        print(
                            f'[VIDEO_WINDOWS] segment_rejected={dst.name} duration={segment_duration:.2f}s '
                            f'error={segment_probe.get("error","invalid or too-short segment")}',
                            flush=True
                        )
                except Exception as e:
                    print(
                        f'[VIDEO_WINDOWS] skip source={clip.name} window={wi+1} '
                        f'error={type(e).__name__}:{str(e)[:180]}',
                        flush=True
                    )
                    dst.unlink(missing_ok=True)
                    continue
        except Exception as e:
            print(f'[VIDEO_WINDOWS] source_probe_failed={clip.name} error={type(e).__name__}:{str(e)[:180]}',flush=True)
            continue
    # Interleave windows from different source moments. Source-first ordering
    # left 4–6 seconds from the same shot family together; round-robin creates
    # a change of footage every scene without recycling the same window.
    def _window_round_robin_key(path):
        stem=Path(path).stem
        parts=stem.rsplit('_window_',1)
        if len(parts)!=2 or not parts[1].isdigit():
            return (0,0,stem)
        source_stem=parts[0]
        source_tail=source_stem.rsplit('_',1)[-1]
        source_index=int(source_tail) if source_tail.isdigit() else 0
        return (int(parts[1]),source_index,source_stem)
    expanded.sort(key=_window_round_robin_key)
    print(f'[VIDEO_WINDOWS] expanded {len(clips)} source clips into {len(expanded)} valid windows; order=round_robin',flush=True)
    return expanded

def _frame_visual_hash(path):
    """Small dependency-light perceptual hash for near-duplicate frame rejection."""
    try:
        from PIL import Image, ImageOps
        with Image.open(path) as im:
            gray=ImageOps.grayscale(im).resize((8,8))
            vals=list(gray.getdata())
        mean=sum(vals)/max(1,len(vals))
        return tuple(v >= mean for v in vals)
    except Exception:
        return None

def _visually_distinct_from_pool(candidate, existing, max_distance=10):
    """Reject nearly identical frames even when filenames/timestamps differ."""
    h=_frame_visual_hash(candidate)
    if h is None:
        return True
    for prior in existing:
        ph=_frame_visual_hash(prior)
        if ph is None:
            continue
        if sum(a != b for a,b in zip(h,ph)) <= max_distance:
            return False
    return True

def _augment_scenes_with_real_video_frames(video_clips, image_scenes, jobdir, target=24):
    """Extract a wider set of genuine official-video frames as moving stills."""
    out=list(image_scenes or [])
    if len(out)>=target:
        return out[:target]
    ff=_ffmpeg_executable()
    clips=list(video_clips or [])
    # Round-robin across sources: the previous source-first loop could fill the
    # target from only the first two clips (12 frames each), concentrating the
    # entire Short on Lucia or the same armed character despite a larger pool.
    # Sample each source at one timestamp before taking a second sample from any
    # source, so the initial pool spans all available official clips.
    source_durations=[]
    for clip in clips:
        try:
            probe=_probe_media(Path(clip))
            duration=max(0.8,float(probe.get('duration') or 8.5))
        except Exception:
            duration=8.5
        source_durations.append(duration)
    sample_count=12
    for fi in range(sample_count):
        for idx,clip in enumerate(clips):
            if len(out)>=target:
                break
            duration=source_durations[idx]
            timestamp=min(max(0.05,0.05 + fi*max(0.0,duration-0.10)/(sample_count-1)),max(0.05,duration-0.05))
            dst=Path(jobdir)/f'official_frame_{idx:02d}_{fi:02d}.jpg'
            try:
                run_cmd([ff,'-loglevel','error','-y','-ss',f'{timestamp:.2f}','-i',str(clip),
                         '-frames:v','1','-vf','scale=540:960:force_original_aspect_ratio=increase,crop=540:960',
                         '-q:v','3',str(dst)],20)
                if dst.exists() and dst.stat().st_size>4000:
                    # Distinct timestamps can still show the same character/shot.
                    # Compare image content against the pool before accepting it.
                    if _visually_distinct_from_pool(dst, out):
                        out.append(dst)
                    else:
                        print(f'[VISUAL_POOL] rejected_near_duplicate={dst.name}',flush=True)
            except Exception:
                continue
        if len(out)>=target:
            break
    print(f'[VISUAL_POOL] official_video_sources={len(video_clips or [])} unique_frames={max(0,len(out)-len(image_scenes or []))} total_images={len(out)} target={target}',flush=True)
    return out[:target]


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
        for cut in range(1,len(words)):
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
        'para','com','por','mas','se','ou','ao','à','às','dos','das','num','numa','nem'
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
    bad_end={'e','de','do','da','em','no','na','que','um','uma','o','a','os','as','para','com','por','mas','se','ou','ao','à','às','dos','das','num','numa','sobre','entre','até','sem','como','pelo','pela','pelos','pelas','porém','porem','então','entao','nem'}
    bad_start={'e','mas','porque','porém','porem','então','entao','quando','enquanto','que','para','com','de','do','da','em','no','na'}
    preferred={'e','mas','porque','porém','porem','então','entao','quando','enquanto','porque','nem'}
    protected={('gta','6'),('gta','vi'),('vice','city'),('cloud','gaming'),('xbox','cloud','gaming'),('jason','e','lucia'),('playstation','5'),('xbox','series')}
    def protected_cut(cut):
        # A cut is protected only when it splits a protected expression across
        # its two sides (for example VICE | CITY), not when the whole phrase is
        # safely contained in one caption.
        left=[norm(x) for x in tokens[max(0,cut-3):cut]]
        right=[norm(x) for x in tokens[cut:cut+3]]
        for ph in protected:
            n=len(ph)
            for left_count in range(1,n):
                right_count=n-left_count
                if (len(left)>=left_count and len(right)>=right_count
                    and tuple(left[-left_count:])==ph[:left_count]
                    and tuple(right[:right_count])==ph[left_count:]):
                    return True
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
            if protected_cut(cut):
                continue
            left=tokens[i:cut]; right=tokens[cut:]
            if not right: continue
            lw=norm(left[-1]); rw=norm(right[0])
            score=abs(len(left)-target)*2.0
            if re.search(r'[.!?;:]$', left[-1]): score-=30
            elif re.search(r'[,)]$', left[-1]): score-=12
            if lw in bad_end: score+=45
            if rw in bad_start: score+=32
            if rw in preferred: score-=8
            # Evita blocos visualmente curtos demais.
            if len(left)<min_words: score+=25
            if len(right)<min_words and rem>max_words+min_words: score+=25
            cand=(score,cut)
            if best is None or cand<best: best=cand
        if best:
            cut=best[1]
        else:
            fallback=min(i+target,len(tokens))
            safe=[c for c in range(lo,hi+1) if not protected_cut(c)]
            cut=min(safe,key=lambda c:abs(c-fallback)) if safe else fallback
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
        # Prevent cutting inside a protected multiword phrase.
        left=[norm(x) for x in tokens[max(0,cut-4):cut]]
        right=[norm(x) for x in tokens[cut:cut+4]]
        for ph in protected:
            n=len(ph)
            for left_count in range(1,n):
                right_count=n-left_count
                if (len(left)>=left_count and len(right)>=right_count
                    and tuple(left[-left_count:])==ph[:left_count]
                    and tuple(right[:right_count])==ph[left_count:]):
                    return True
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
            if protected_cut(cut):
                continue
            left=tokens[i:cut]; right=tokens[cut:]
            if len(right)>0 and len(right)<min_words and rem>max_words+min_words: continue
            lw=norm(left[-1]); rw=norm(right[0]) if right else ''
            score=abs(len(left)-target)*1.4
            if re.search(r'[,:;.!?]$',left[-1]): score-=18
            if lw in bad_end: score+=35
            if rw in bad_start: score+=35
            if rw in connectors: score-=8
            if len(left)>=8: score+=1
            candidates.append((score,cut))
        if candidates:
            cut=min(candidates)[1]
        else:
            fallback=min(i+target,len(tokens))
            safe=[c for c in range(lo,hi+1) if not protected_cut(c)]
            cut=min(safe,key=lambda c:abs(c-fallback)) if safe else fallback
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
            if re.search(r'[.!?;:]$',str(chunks[i][-1])): score+=8
            if best_score is None or score<best_score:
                best_score=score; best_idx=i
        if best_idx is None:
            # Preserve short readable captions rather than violating the word limit.
            break
        chunks[best_idx:best_idx+2]=[chunks[best_idx]+chunks[best_idx+1]]
    return chunks


def _cue_clean(w):
    return re.sub(r'\s+',' ',str(w or '')).strip()


def _cue_bad_end(w):
    return re.sub(r'[^A-Za-zÀ-ÿ]','',str(w or '')).lower() in {
        'e','de','do','da','em','no','na','que','um','uma','o','a','os','as','para','com','por','mas','se','ou','ao','à','às','dos','das','num','numa','sobre','entre','até','sem','nem'
    }


def _cue_bad_start(w):
    return re.sub(r'[^A-Za-zÀ-ÿ]','',str(w or '')).lower() in {
        'e','mas','porque','porém','porem','então','entao','quando','enquanto','para','com','de','do','da','em','no','na','que'
    }


def _protected_pair(left,right):
    a=re.sub(r'[^a-z0-9à-ÿ]','',left.lower())
    b=re.sub(r'[^a-z0-9à-ÿ]','',right.lower())
    return (a,b) in {('gta','6'),('gta','vi'),('vice','city'),('cloud','gaming'),('xbox','cloud')}


def _protected_caption_boundary(current_cues,next_word):
    """Avoid cuts in protected names and paired terms across timed captions."""
    left=[re.sub(r'[^a-z0-9à-ÿ]','',_cue_clean(x.get('word','')).lower()) for x in (current_cues or [])[-3:]]
    right=re.sub(r'[^a-z0-9à-ÿ]','',_cue_clean(next_word).lower())
    seq=left+[right]
    protected={
        ('gta','6'),('gta','vi'),('vice','city'),('cloud','gaming'),
        ('xbox','cloud'),('jason','e','lucia'),('playstation','5'),('xbox','series')
    }
    for phrase in protected:
        n=len(phrase)
        if len(seq)>=n and tuple(seq[-n:])==phrase:
            return True
    return False


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
            # Keep conjunctions/prepositions attached to their phrase even when
            # the normal limit is reached; eight words is the absolute cap.
            protected=_protected_caption_boundary(cur,nextc['word']) or _protected_pair(word,nextc['word'])
            hard_split=len(cur)>=max_words+1
            if protected:
                need=False
            elif (_cue_bad_end(word) or _cue_bad_start(nextc['word'])) and not hard_split:
                need=False
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
            if re.search(r'[.!?;:]$',str(a[-1].get('word',''))): score+=8
            if gap>=0.6: score+=2
            elif gap<0.6: score-=2
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


def _learned_timeline_count(duration, fallback=10):
    """Map an Analytics-learned winning duration bucket to pacing density."""
    try:
        profile=TREND_BRAIN.recommend_editorial_profile() if TREND_BRAIN else {}
        pref=(profile or {}).get('preferred_duration') or {}
        bucket=str(pref.get('bucket') or '')
        s=float(duration or 0)
        actual='24-29s' if 24 <= s < 30 else ('30-38s' if 30 <= s < 39 else 'UNSUPPORTED')
        if bucket != actual: return fallback
        return {'24-29s':8,'30-38s':10}.get(bucket,fallback)
    except Exception:
        return fallback

def _partition_caption_tokens_for_count(tokens, target_count, max_words=7, min_words=3):
    """Find a low-cost full-coverage caption partition under the scene-count ceiling."""
    tokens=list(tokens or [])
    if not tokens:
        return []
    max_words=max(2,int(max_words)); min_words=max(1,int(min_words))
    requested=max(1,int(target_count))
    min_count=max(1,(len(tokens)+max_words-1)//max_words)
    max_count=min(requested,max(1,len(tokens)//min_words))
    if min_count>max_count:
        raise RuntimeError(
            f'GATE CAPTIONS: {len(tokens)} words cannot fit in <= {requested} captions '
            f'of {min_words}-{max_words} words.'
        )

    protected={
        ('gta','6'),('gta','vi'),('vice','city'),('cloud','gaming'),
        ('xbox','cloud','gaming'),('jason','e','lucia'),
        ('playstation','5'),('xbox','series')
    }
    bad_end={
        'e','de','do','da','em','no','na','que','um','uma','o','a','os','as',
        'para','com','por','mas','se','ou','ao','à','às','dos','das','num','numa',
        'sobre','entre','até','sem','como','pelo','pela','pelos','pelas','porém','porem','nem',
        'esse','essa','esses','essas','este','esta','estes','estas','aquele','aquela',
        'aqueles','aquelas','meu','minha','meus','minhas','seu','sua','seus','suas',
        'nosso','nossa','nossos','nossas'
    }
    bad_start={
        'e','mas','porque','porém','porem','então','entao','quando','enquanto',
        'que','para','com','de','do','da','em','no','na'
    }
    def norm(word):
        return _caption_clean_word(word)
    def protected_cut(cut):
        left=[norm(x) for x in tokens[max(0,cut-3):cut]]
        right=[norm(x) for x in tokens[cut:cut+3]]
        for phrase in protected:
            for left_count in range(1,len(phrase)):
                right_count=len(phrase)-left_count
                if (len(left)>=left_count and len(right)>=right_count
                    and tuple(left[-left_count:])==phrase[:left_count]
                    and tuple(right[:right_count])==phrase[left_count:]):
                    return True
        return False

    def solve(target):
        # Dynamic programming across token offsets finds globally valid cuts.
        # A local greedy choice can otherwise strand a preposition or connector
        # at the beginning/end of the last caption, even when another partition exists.
        n=len(tokens)
        dp=[[None]*(target+1) for _ in range(n+1)]
        dp[0][0]=(0.0,[])
        ideal_words=n/target
        for offset in range(n):
            for used in range(target):
                state=dp[offset][used]
                if state is None:
                    continue
                base_score,parts=state
                if used>0 and norm(tokens[offset]) in bad_start:
                    continue
                for size in range(min_words,max_words+1):
                    end=offset+size
                    if end>n:
                        break
                    remaining_slots=target-(used+1)
                    remaining=n-end
                    if remaining_slots==0:
                        if remaining:
                            continue
                    elif not (min_words*remaining_slots <= remaining <= max_words*remaining_slots):
                        continue
                    if norm(tokens[end-1]) in bad_end:
                        continue
                    if end<n and protected_cut(end):
                        continue
                    tail=tokens[end-1]
                    score=base_score + abs(size-ideal_words)*2.0
                    if re.search(r'[.!?;:]$',tail):
                        score-=12
                    elif re.search(r'[,)]$',tail):
                        score-=4
                    if end<n and norm(tokens[end]) in {'e','mas','porque','porém','porem','então','entao'}:
                        score-=2
                    candidate=(score,parts+[tokens[offset:end]])
                    old=dp[end][used+1]
                    if old is None or candidate[0]<old[0]:
                        dp[end][used+1]=candidate
        final=dp[n][target]
        if final is None:
            return None
        chunks=final[1]
        audit=_audit_caption_quality([{'text':_clean_caption_phrase(' '.join(c))} for c in chunks])
        if any(audit.get(key) for key in ('bad_end','bad_start','protected_splits','long','short','visual_bad')):
            return None
        return chunks

    for target in range(max_count,min_count-1,-1):
        chunks=solve(target)
        if chunks is not None:
            return chunks
    raise RuntimeError(
        f'GATE CAPTIONS: no grammatically safe partition fits <= {requested} captions; '
        'refusing to split a protected phrase or strand a preposition.'
    )



def _repair_caption_transcription_mismatches(beats, narration):
    """Repair a known WordBoundary text glitch only when the approved script proves the intended word."""
    out=[dict(b) for b in (beats or [])]
    approved=' '.join(re.findall(r"[A-Za-zÀ-ÿ0-9']+",str(narration or '').lower()))
    # Edge-TTS has occasionally labeled the spoken conjunction "que" as "quem".
    # Correct it only in the exact grammatical construction proven by narration.
    expected=bool(re.search(r"\bque\s+cada\s+trabalho\s+seja\b",approved))
    if not expected or re.search(r"\bquem\s+cada\s+trabalho\s+seja\b",approved):
        return out
    changed=False
    for i,b in enumerate(out):
        text=str(b.get('text',''))
        if re.search(r"\bquem(?=\s+cada\b)",text,re.I):
            b['text']=re.sub(r"\bquem(?=\s+cada\b)",'que',text,flags=re.I)
            changed=True
        elif re.search(r"\bquem\s*$",text,re.I) and i+1<len(out) and re.match(r"\s*cada\b",str(out[i+1].get('text','')),re.I):
            b['text']=re.sub(r"\bquem\s*$",'que',text,flags=re.I)
            changed=True
    if changed:
        print('[CAPTION_TEXT_REPAIR] corrected WordBoundary "quem cada" -> approved narration "que cada"',flush=True)
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
            if timed: return _repair_caption_transcription_mismatches(timed,script.get('narration',''))
    narration=re.sub(r'\s+',' ',str(script.get('narration','')).strip())
    if not narration:
        return [{'text':'GTA 6','duration':duration,'highlight':'GTA','start':0,'end':duration}]
    sentences=[s.strip() for s in re.split(r'(?<=[.!?])\s+',narration) if s.strip()]
    all_chunks=[]
    # Seven words is the audited maximum and gives enough flexibility to fit
    # the actual visual-slot count without losing protected word groups.
    for sent in sentences: all_chunks.extend(_semantic_caption_chunks(sent,3,7))
    if not all_chunks: all_chunks=[_caption_words(narration)]
    all_chunks=_merge_caption_chunks(all_chunks,target_count=max(1,count),max_words=7)
    if len(all_chunks)>max(1,int(count)):
        all_chunks=_partition_caption_tokens_for_count(_caption_words(narration),max(1,int(count)),max_words=7,min_words=2)
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
    return _repair_caption_transcription_mismatches(beats,narration)

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

VIDEO_SOURCE_MAX_USES=1


def _visual_source_key(path):
    """Return the original clip stem so cropped windows cannot masquerade as new sources."""
    stem=Path(path).stem
    return re.sub(r'_window_[0-9]+$','',stem,flags=re.I)


def _visual_source_capacity(paths, max_per_source=VIDEO_SOURCE_MAX_USES):
    """Count how many video windows can be used without exceeding the per-source budget."""
    counts={}
    for path in (paths or []):
        if not path:
            continue
        key=_visual_source_key(path)
        counts[key]=counts.get(key,0)+1
    return sum(min(max(0,int(max_per_source)),count) for count in counts.values())


def _choose_timeline_assets(video_clips, image_paths, beats, topic_title, variant=0):
    """V57: editor video-first.
    Prioriza material em movimento e usa imagens apenas como apoio editorial.
    Evita repetição imediata e garante variedade sem transformar o Short em slideshow.
    """
    videos=[p for p in video_clips if p]
    images=[p for p in image_paths if p]
    pool=[('video',p) for p in videos]+[('image',p) for p in images]
    chosen=[]; used=set(); asset_counts={}; source_counts={}
    def source_group(path):
        # Three windows cut from one trailer still count as one editorial source.
        return _visual_source_key(path)
    video_sources={source_group(p) for p in videos}
    # V61: repetition is now a hard budget, not just a score penalty.
    # The pool can shrink on Render Free after a restart, so the reuse budget is
    # calculated from the assets actually available. With 8 videos + 4 images
    # this yields 16 video + 8 image scenes; with 4 + 4 it yields 12 + 12.
    asset_total=max(1,len(videos)+len(images))
    # Images are supporting assets, not loopable footage: each still may appear
    # at most once in a Short. Video sources can repeat only because each proxy
    # is now 8.5s long and the renderer seeks to a materially different offset.
    image_max_reuse=1
    # V68: a amostra de QA (14/10) mostrou repetição perceptível mesmo com
    # janelas tecnicamente diferentes do mesmo trailer. Não contar _window_N como
    # nova cena editorial: limitar cada fonte original a UMA aparição por Short.
    # Se o pool de fontes oficiais for insuficiente, o gate deve bloquear em vez
    # de publicar um vídeo com o mesmo personagem/plano reciclado.
    video_max_reuse=VIDEO_SOURCE_MAX_USES
    max_reuse=max(image_max_reuse,video_max_reuse)
    video_capacity=_visual_source_capacity(videos,video_max_reuse) if videos else 0
    target_video=min(len(beats),video_capacity) if beats and videos else 0
    target_images=min(len(images), max(0, len(beats)-target_video)) if beats and images else 0
    print(f'[TIMELINE_VARIETY] videos={len(videos)} images={len(images)} video_max_reuse={video_max_reuse} target_video={target_video} target_images={target_images}',flush=True)
    if len(beats or []) > video_capacity + len(images):
        raise RuntimeError(
            f'GATE VISUAL: pool insuficiente para evitar repetição '
            f'({video_capacity} janelas de vídeo utilizáveis + {len(images)} imagens únicas '
            f'para {len(beats)} cenas). Buscar mais material oficial antes de renderizar.'
        )
    video_used=0

    def recent_penalty(p, bi):
        pen=0
        recent=[x[1] for x in chosen[-8:]]
        if p in recent: pen += 420
        if chosen and chosen[-1][1]==p: pen += 1000
        if beats and bi >= max(0, int(len(beats)*0.80)) and p in [x[1] for x in chosen[:2]]:
            pen += 180
        # Strongly prefer sources that have not been used yet.
        pen += asset_counts.get(p,0) * 180
        return pen

    def under_reuse_budget(p):
        # Images are one-shot support assets; video windows share a budget by
        # original source so cutting a trailer into windows cannot bypass it.
        kind='video' if p in videos else 'image'
        budget=video_max_reuse if kind=='video' else image_max_reuse
        count=source_counts.get(source_group(p),0) if kind=='video' else asset_counts.get(p,0)
        return count < budget

    for bi,beat in enumerate(beats):
        remaining=[(idx,kind,p) for idx,(kind,p) in enumerate(pool) if idx not in used]
        remaining_videos=[x for x in remaining if x[1]=='video']
        reusable_videos=[(idx,kind,p) for idx,(kind,p) in enumerate(pool) if kind=='video' and under_reuse_budget(p)]
        reusable_images=[(idx,kind,p) for idx,(kind,p) in enumerate(pool) if kind=='image' and under_reuse_budget(p)]
        target_image_count=max(0, len(beats)-target_video)
        image_slots={int(round((i+1)*len(beats)/(target_image_count+1)))-1 for i in range(target_image_count)} if target_image_count else set()
        image_due=(bi in image_slots) and bool(images)

        # V65: FRESH-FIRST é uma regra dura. Se ainda existe uma fonte de vídeo
        # que nunca apareceu, ela vence qualquer fonte já exibida. A penalidade
        # numérica anterior podia ser superada pela relevância semântica (Jason/
        # Lucia), causando o carrossel dos mesmos 4-5 planos.
        fresh_videos=[x for x in remaining_videos if under_reuse_budget(x[2])]
        fresh_images=[x for x in remaining if x[1]=='image' and under_reuse_budget(x[2])]
        remaining_slots=len(beats)-bi-1
        remaining_video_capacity=sum(1 for _idx,_kind,p in reusable_videos)
        can_use_image=image_due and (video_used + remaining_slots >= target_video) and bool(fresh_images or reusable_images)
        force_video=bool(videos) and video_used < target_video and not can_use_image and bool(reusable_videos)

        if can_use_image:
            candidates=fresh_images or reusable_images
        elif force_video:
            # Enquanto houver vídeo inédito, não aceite um vídeo reciclado.
            candidates=fresh_videos or reusable_videos
        elif fresh_videos:
            candidates=fresh_videos
        elif fresh_images:
            candidates=fresh_images
        elif reusable_videos:
            candidates=reusable_videos
        elif reusable_images:
            candidates=reusable_images
        else:
            candidates=remaining or [(idx,kind,p) for idx,(kind,p) in enumerate(pool)]

        # V62: balance source usage before semantic ranking. This prevents
        # one character/shot from winning repeatedly just because its filename
        # matches the topic better than the other clips.
        if force_video and candidates:
            min_count=min(source_counts.get(source_group(p),0) for _idx,_kind,p in candidates)
            candidates=[x for x in candidates if source_counts.get(source_group(x[2]),0)==min_count] or candidates
        ranked=[]
        for idx,kind,p in candidates:
            if force_video and kind!='video':
                continue
            score=_asset_relevance(p,topic_title,beat.get('text',''),kind)

            # Movimento é prioridade editorial: vídeos recebem grande vantagem.
            if kind=='video':
                score += 55
                if bi==0: score += 20
                if bi>=2: score += 12
            else:
                score -= 10

            # Nunca repetir o mesmo visual imediatamente.
            score -= recent_penalty(p,bi)

            # Relevância semântica continua valendo, mas não supera a prioridade
            # de movimento quando o vídeo é utilizável.
            if variant and idx % 4 == (bi+variant)%4:
                score += 6

            ranked.append((score,kind,p,idx))

        # Fallback caso a cota tenha acabado ou só existam imagens restantes.
        if not ranked:
            ranked=[]
            for idx,kind,p in candidates:
                score=_asset_relevance(p,topic_title,beat.get('text',''),kind)
                score += 40 if kind=='video' else -5
                score -= recent_penalty(p,bi)
                ranked.append((score,kind,p,idx))

        ranked.sort(key=lambda x:x[0],reverse=True)
        _,kind,p,idx=ranked[0]
        chosen.append((kind,p))
        asset_counts[p]=asset_counts.get(p,0)+1
        if kind=='video':
            source=source_group(p)
            source_counts[source]=source_counts.get(source,0)+1
        used.add(idx)
        if kind=='video':
            video_used += 1

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
    # FFmpeg/yuv420p requires even width/height. Keep per-scene intermediates at 540x960 for Render Free memory,
    # then upscale only the final concatenated master to the required 1080x1920 delivery dimensions.
    INTER_W, INTER_H = 540, 960
    if INTER_W % 2 or INTER_H % 2:
        raise RuntimeError(f'Dimensões intermediárias inválidas: {INTER_W}x{INTER_H}.')
    """V57 editor: narration-driven video-first timeline, short beats, real clips + limited images.
    Still optimized for Render Free by encoding one scene at a time.
    """
    ff=_ffmpeg_executable()
    work=out.parent/'timeline'; work.mkdir(exist_ok=True)
    if len(video_clips)<3 and len(image_paths)<8:
        raise RuntimeError('A edição precisa de 3 vídeos reais ou pelo menos 8 visuais únicos de fallback.')
    if script is None:
        script={'narration':' '.join(captions)}
    beats=beats or build_short_timeline(script, {'title':topic_title}, duration, count=10)
    # Cap scene count before normalization so the renderer cannot recreate more
    # scenes than the unique visual pool can support.
    if video_clips:
        visual_capacity=_visual_source_capacity(video_clips)+len(set(map(str,image_paths)))
        if 6 <= visual_capacity < len(beats):
            beats=build_short_timeline(script,{'title':topic_title},duration,count=visual_capacity,word_cues=None)
            if len(beats)>visual_capacity:
                raise RuntimeError(
                    f'GATE CAPTIONS: {len(beats)} semantic captions exceed the {visual_capacity}-scene visual pool; '
                    'refusing to split narration by raw word counts.'
                )
            print(f'[VISUAL_POOL] timeline_capped={len(beats)} capacity={visual_capacity}',flush=True)
    # Video-first timelines are normalized to short beats. In the controlled
    # image-only fallback, preserve one unique image per beat instead of splitting
    # each 2.5s beat into duplicates that would recycle the same stills.
    if video_clips:
        # Preserve the capped timeline exactly when it fits the unique visual pool.
        # Calling the normalizer here can split long beats and recreate the same
        # visual-capacity failure we just avoided.
        unique_pool=_visual_source_capacity(video_clips)+len(set(map(str,image_paths)))
        if len(beats) <= unique_pool:
            n=max(1,len(beats))
            beats=[dict(b, start=i*duration/n, end=(i+1)*duration/n, duration=duration/n) for i,b in enumerate(beats)]
        else:
            max_scene=2.0 if len(video_clips)<3 and len(image_paths)>=8 else 1.8
            beats=_normalize_visual_beats(beats,duration,max_scene=max_scene)
    else:
        n=max(1,len(beats))
        beats=[dict(b, start=i*duration/n, end=(i+1)*duration/n, duration=duration/n) for i,b in enumerate(beats)]
    # Last-mile gate: inspect the exact caption beats that will be painted onto
    # the output frames. Earlier prechecks ran before renderer compaction/retiming.
    _render_cap=_audit_caption_quality(beats)
    print(
        f"[RENDER_CAPTION_AUDIT] before score={_render_cap.get('score',0)} "
        f"bad_end={len(_render_cap.get('bad_end',[]))} "
        f"bad_start={len(_render_cap.get('bad_start',[]))} "
        f"protected_splits={len(_render_cap.get('protected_splits',[]))}",
        flush=True
    )
    if (_render_cap.get('bad_end') or _render_cap.get('bad_start')
        or _render_cap.get('protected_splits') or _render_cap.get('long')
        or _render_cap.get('short') or _render_cap.get('visual_bad')):
        _render_fixed=_repair_caption_beats(beats,float(duration),max_words=6)
        _render_fixed_cap=_audit_caption_quality(_render_fixed)
        if (_render_fixed_cap.get('bad_end') or _render_fixed_cap.get('bad_start')
            or _render_fixed_cap.get('protected_splits') or _render_fixed_cap.get('long')
            or _render_fixed_cap.get('short') or _render_fixed_cap.get('visual_bad')
            or not _render_fixed):
            raise RuntimeError(
                "RENDER_CAPTION_GATE: a segmentação final das legendas continua inválida: "
                f"{_render_fixed_cap}"
            )
        beats=_render_fixed
        print(
            f"[RENDER_CAPTION_AUDIT] repaired score={_render_fixed_cap.get('score',0)} "
            f"scenes={len(beats)}",
            flush=True
        )
    else:
        print(f"[RENDER_CAPTION_AUDIT] accepted score={_render_cap.get('score',0)}",flush=True)
    # Use todos os assets disponíveis; quando há poucos, o renderer aplica
    # enquadramentos diferentes em cada reutilização em vez de congelar a tela.
    # Keep all unique frames produced by the official-video extractor. The old [:18]
    # cap silently discarded frames even when augmentation had built a larger pool,
    # causing the visual gate to reject otherwise viable timelines.
    imgs=list(image_paths)[:24]
    assets=_choose_timeline_assets(video_clips,imgs,beats,topic_title,variant=asset_variant)
    scene_files=[]
    render_use_counts={}
    print(f'[RENDER] start title={topic_title[:100]} scenes={len(beats)} videos={len(videos) if (videos:=list(video_clips)) else 0} images={len(imgs)} duration={duration:.1f}s', flush=True)
    for i,(beat,(kind,src)) in enumerate(zip(beats,assets)):
        print(f'[RENDER] scene {i+1}/{len(beats)} start kind={kind} duration={float(beat.get("duration",0)):.2f}s source={Path(src).name}', flush=True)
        scene=work/f'scene_{i:02d}.mp4'; overlay=work/f'overlay_{i:02d}.png'
        _caption_overlay(overlay,beat['text'],i,len(beats),540,960,beat.get('highlight'))
        if kind=='video':
            # Movimento leve em todas as cenas. Em reparos, aumenta a amplitude.
            amp=28 if motion_boost else 10
            vf=f"scale=574:1020:force_original_aspect_ratio=increase,crop=540:960:x='10+{amp}*sin(n/18)':y='18+{max(4,amp//2)}*cos(n/23)',setsar=1,fps=30"
            # Reused clips start at different offsets so the same source is
            # not perceived as the exact same shot on every occurrence.
            reuse_n=render_use_counts.get(str(src),0)
            # V62: use six distinct windows across the 8.5s proxy. The previous
            # 6.4s cap caused the 5th/6th reuse to collapse onto nearly the same
            # opening, which is exactly the "same video came back" problem.
            # V65: em uma segunda aparição, desloca o trecho de forma clara.
            # O limite de 2 usos torna este offset determinístico e evita que
            # a mesma abertura do proxy volte praticamente igual.
            offset=(3.6 if asset_variant>0 else 0.0) if reuse_n==0 else 3.6
            zoom_variant=reuse_n % 2
            crop_w=540 + zoom_variant*10
            crop_h=960 + zoom_variant*18
            scale_w=574 + zoom_variant*18
            scale_h=1020 + zoom_variant*30
            vf=f"scale={scale_w}:{scale_h}:force_original_aspect_ratio=increase,crop={crop_w}:{crop_h}:x='10+{10+zoom_variant*8}*sin(n/18)':y='18+{max(4,10+zoom_variant*5)}*cos(n/23)',scale=540:960,setsar=1,fps=30"
            inp=['-stream_loop','-1','-threads:v','1','-probesize','1M','-analyzeduration','1M','-ss',f'{offset:.2f}','-i',str(src)]
        else:
            # Apply edge-safe preprocessing in the actual render path. Previously
            # the crop helper existed and its unit test passed, but image rendering
            # bypassed it and retained clipped source-edge lettering.
            prepared_source=work/f'image_safe_{i:02d}.jpg'
            prepare_scene(src,prepared_source,beat.get('text',''),i,len(beats))
            # V67.1: keep image motion alive for the whole beat. The former
            # zoom+0.003/frame hit the 1.06 cap in ~20 frames (~0.67 s), then
            # visually held still for most of a 2.14 s scene.
            zoom_rate='0.0014' if motion_boost else '0.00125'
            zoom_cap='1.09' if motion_boost else '1.085'
            vf=f"scale=540:960:force_original_aspect_ratio=increase,crop=540:960,setsar=1,zoompan=z='min(1+{zoom_rate}*on,{zoom_cap})':x='(iw-iw/zoom)/2+((iw-iw/zoom)/4)*sin(on/18)':y='(ih-ih/zoom)/2+((ih-ih/zoom)/4)*cos(on/23)':d=1:s=540x960:fps=30"
            inp=['-loop','1','-threads:v','1','-i',str(prepared_source)]
        cmd=[ff,'-loglevel','error','-y']+inp+['-threads:v','1','-loop','1','-i',str(overlay),'-t',f'{beat["duration"]:.3f}',
             '-filter_complex',f'[0:v]{vf}[v];[1:v]format=rgba[o];[v][o]overlay=0:0:shortest=1[outv]',
             '-map','[outv]','-an','-c:v','libx264','-preset','ultrafast','-crf','21',
             '-threads','1','-filter_threads','1','-filter_complex_threads','1',
             '-x264-params','threads=1:lookahead-threads=1:rc-lookahead=0:sync-lookahead=0','-pix_fmt','yuv420p','-movflags','+faststart',str(scene)]
        run_cmd(cmd,75)
        scene_files.append(scene)
        render_use_counts[str(src)]=render_use_counts.get(str(src),0)+1
        print(f'[RENDER] scene {i+1}/{len(beats)} done bytes={scene.stat().st_size if scene.exists() else 0}', flush=True)
        try: overlay.unlink()
        except Exception: pass
    listfile=work/'timeline.txt'
    with listfile.open('w',encoding='utf-8') as f:
        for sf in scene_files: f.write(f"file '{sf.as_posix()}'\n")
    print(f'[RENDER] concat start scenes={len(scene_files)} audio_bytes={Path(audio).stat().st_size if Path(audio).exists() else 0}', flush=True)
    run_cmd([ff,'-loglevel','error','-y','-f','concat','-safe','0','-i',str(listfile),'-i',str(audio),
             '-t',f'{duration:.2f}','-vf','scale=1080:1920:flags=lanczos,setsar=1,format=yuv420p','-r','30',
             '-c:v','libx264','-preset','ultrafast','-crf','20','-threads','1','-filter_threads','1','-filter_complex_threads','1',
             '-x264-params','threads=1:lookahead-threads=1:rc-lookahead=0:sync-lookahead=0','-force_key_frames','expr:gte(t,n_forced*2)','-c:a','aac','-b:a','160k',
             '-movflags','+faststart','-shortest',str(out)],300)
    print(f'[RENDER] concat done exists={out.exists()} bytes={out.stat().st_size if out.exists() else 0}', flush=True)
    for p in scene_files:
        try: p.unlink()
        except Exception: pass
    for p in work.glob('image_safe_*.jpg'):
        try: p.unlink()
        except Exception: pass
    try: listfile.unlink()
    except Exception: pass
    # Return exact caption beats painted into the MP4 for downstream post-render QA.
    return beats

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
    im=im.resize((540,960),Image.Resampling.BILINEAR)
    d=ImageDraw.Draw(im,'RGBA')
    d.rectangle((22,250,518,665),fill=(0,0,0,175),outline=(225,25,45),width=3)
    f=font(36,True); y=305
    for line in wrap_text(d,title,f,440)[:6]:
        d.text((50,y),line,font=f,fill='white',stroke_width=1,stroke_fill='black'); y+=44
    d.text((50,60),'GTA OCULTO',font=font(18,True),fill=(255,255,255,180))
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
    chunks=_merge_caption_chunks(fixed,target_count=max(1,min(16,len(fixed))),max_words=max_words)

    # Repair semantic boundaries without creating very long captions.
    bad_end={'e','de','do','da','em','no','na','que','um','uma','o','a','os','as','para','com','por','mas','se','ou','ao','à','às','dos','das','num','numa','sobre','entre','até','sem','nem','esse','essa','esses','essas','este','esta','estes','estas','aquele','aquela','aqueles','aquelas','meu','minha','meus','minhas','seu','sua','seus','suas','nosso','nossa','nossos','nossas'}
    bad_start={'e','mas','porque','porém','porem','então','entao','quando','enquanto','para','com','de','do','da','em','no','na','que'}
    i=0
    while i < len(chunks)-1:
        last=_caption_clean_word(chunks[i][-1]); first=_caption_clean_word(chunks[i+1][0])
        if (last in bad_end or first in bad_start) and len(chunks[i])+len(chunks[i+1])<=max_words:
            chunks[i:i+2]=[chunks[i]+chunks[i+1]]
            i=max(0,i-1)
        else:
            i+=1

    # Gate final de início de legenda: nenhum bloco pode começar com conector/preposição.
    # Se não houver espaço no bloco anterior, desloca uma palavra do fim anterior para
    # preservar a sequência falada e evitar cortes como "DE EMPREGOS..." isolados.
    bad_start_final={'e','mas','porque','porém','porem','então','entao','quando','enquanto','para','com','de','do','da','em','no','na','que'}
    changed=True
    guard=0
    while changed and guard < 32:
        changed=False
        guard+=1
        for idx in range(1,len(chunks)):
            if not chunks[idx]:
                continue
            first=_caption_clean_word(chunks[idx][0])
            if first not in bad_start_final:
                continue
            prev=chunks[idx-1]
            # "PARA" pode iniciar a continuação natural de "empregos para várias pessoas";
            # nesse caso, é melhor que a legenda anterior termine em "PARA".
            if first == 'para' and prev and _caption_clean_word(prev[-1]) == 'empregos':
                continue
            if len(prev)+1 <= max_words:
                prev.append(chunks[idx].pop(0))
                changed=True
            elif len(prev)>3 and len(chunks[idx])>3:
                chunks[idx].insert(0,prev.pop())
                changed=True
            if not chunks[idx]:
                chunks.pop(idx)
                break

    # Evita deixar preposição pendurada no fim de uma legenda quando a seguinte
    # comporta a palavra e a construção continua naturalmente (ex.: "empregos para").
    for idx in range(len(chunks)-1):
        if not chunks[idx] or not chunks[idx+1]:
            continue
        last=_caption_clean_word(chunks[idx][-1])
        nxt=_caption_clean_word(chunks[idx+1][0])
        if last == 'para' and nxt not in bad_start_final and len(chunks[idx+1]) < max_words and len(chunks[idx]) > 3:
            chunks[idx+1].insert(0,chunks[idx].pop())

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

def _caption_visual_split_quality(text, W=540):
    """Score line balance at the actual 540x960 export width."""
    d=ImageDraw.Draw(Image.new('RGBA',(W,120),(0,0,0,0)))
    f=font(24,True)
    words=str(text or '').split()
    if not words: return {'score':100,'lines':[]}
    single=' '.join(words)
    max_width=W-42
    if d.textbbox((0,0),single,font=f,stroke_width=1)[2] <= max_width:
        return {'score':100,'lines':[single.upper()]}
    # Short captions should be evaluated by actual fit, not word count alone.
    # Permit a balanced two-line split even for phrases of 2-4 words.
    candidates=[]
    for cut in range(1,len(words)):
        a=' '.join(words[:cut]); b=' '.join(words[cut:])
        wa=d.textbbox((0,0),a,font=f,stroke_width=1)[2]
        wb=d.textbbox((0,0),b,font=f,stroke_width=1)[2]
        if wa<=max_width and wb<=max_width:
            candidates.append((abs(wa-wb)+abs(cut-(len(words)-cut))*18,cut,a,b))
    if candidates:
        _,cut,a,b=min(candidates,key=lambda x:x[0])
        return {'score':100,'lines':[a.upper(),b.upper()]}
    # Retry at smaller but still readable sizes before failing the caption audit.
    for size in (22,20,18):
        fs=font(size,True)
        if d.textbbox((0,0),single,font=fs,stroke_width=1)[2] <= max_width:
            return {'score':90,'lines':[single.upper()],'font_size':size}
        smaller=[]
        for cut in range(1,len(words)):
            a=' '.join(words[:cut]); b=' '.join(words[cut:])
            wa=d.textbbox((0,0),a,font=fs,stroke_width=1)[2]
            wb=d.textbbox((0,0),b,font=fs,stroke_width=1)[2]
            if wa<=max_width and wb<=max_width:
                smaller.append((abs(wa-wb)+abs(cut-(len(words)-cut))*18,a,b))
        if smaller:
            _,a,b=min(smaller,key=lambda x:x[0])
            return {'score':90,'lines':[a.upper(),b.upper()],'font_size':size}
    return {'score':65,'lines':[str(text).upper()]}

def _audit_caption_quality(beats):
    bad_end=[]; bad_start=[]; long=[]; short=[]; visual_bad=[]; protected_splits=[]
    bad_end_set={'e','de','do','da','em','no','na','que','um','uma','o','a','os','as','para','com','por','mas','se','ou','ao','à','às','dos','das','num','numa','sobre','entre','até','sem','nem','esse','essa','esses','essas','este','esta','estes','estas','aquele','aquela','aqueles','aquelas','meu','minha','meus','minhas','seu','sua','seus','suas','nosso','nossa','nossos','nossas'}
    bad_start_set={'e','mas','porque','porém','porem','então','entao','quando','enquanto','para','com','de','do','da','em','no','na','que'}
    protected_phrases={
        ('gta','6'),('gta','vi'),('vice','city'),('cloud','gaming'),
        ('xbox','cloud','gaming'),('jason','e','lucia'),('playstation','5'),('xbox','series')
    }
    for bi,b in enumerate(beats or []):
        words=_caption_words(b.get('text',''))
        if not words: continue
        if _caption_clean_word(words[-1]) in bad_end_set: bad_end.append(b['text'])
        first=_caption_clean_word(words[0])
        # Aceita "PARA" quando é continuação gramatical de "empregos para várias pessoas".
        previous_words=_caption_words((beats[bi-1] or {}).get('text','')) if bi>0 else []
        valid_para_continuation=(first=='para' and previous_words and _caption_clean_word(previous_words[-1])=='empregos')
        if first in bad_start_set and not valid_para_continuation: bad_start.append(b['text'])
        if len(words)>7: long.append(b['text'])
        if len(words)<2: short.append(b['text'])
        vs=_caption_visual_split_quality(b.get('text',''))
        if vs['score']<85: visual_bad.append({'text':b.get('text',''),'lines':vs['lines']})

    # Check phrase integrity across each caption boundary, not only inside a block.
    clean_blocks=[
        [_caption_clean_word(w) for w in _caption_words((b or {}).get('text',''))]
        for b in (beats or [])
    ]
    for bi in range(len(clean_blocks)-1):
        left=clean_blocks[bi]; right=clean_blocks[bi+1]
        for phrase in protected_phrases:
            for left_count in range(1,len(phrase)):
                right_count=len(phrase)-left_count
                if (len(left)>=left_count and len(right)>=right_count
                    and tuple(left[-left_count:])==phrase[:left_count]
                    and tuple(right[:right_count])==phrase[left_count:]):
                    protected_splits.append({
                        'phrase':' '.join(phrase),
                        'left':(beats[bi] or {}).get('text',''),
                        'right':(beats[bi+1] or {}).get('text','')
                    })
    total=max(1,len(beats or []))
    texts=[re.sub(r'\s+',' ',str(b.get('text','')).strip().lower()) for b in (beats or []) if str(b.get('text','')).strip()]
    repeated_adj=sum(1 for i in range(1,len(texts)) if texts[i] and texts[i]==texts[i-1])
    repeated_total=max(0,len(texts)-len(set(texts))) if texts else 0
    # A caption ending in a preposition or splitting a protected name is a stronger warning.
    boundary_penalty=min(28, len(bad_end)*2 + len(bad_start)*2)
    penalty=min(65,boundary_penalty + len(long)*3 + len(short)*2 + len(visual_bad)*3 + repeated_adj*8 + repeated_total*3 + min(30,len(protected_splits)*15))
    return {
        'score':max(0,100-penalty),
        'bad_end':bad_end,'bad_start':bad_start,'long':long,'short':short,
        'visual_bad':visual_bad,'protected_splits':protected_splits,
        'repeated_adjacent':repeated_adj,'repeated_total':repeated_total
    }


MEDIA_VALIDATION_CACHE={}
MEDIA_VALIDATION_LOCK=threading.RLock()

def _probe_media(path):
    """Probe media with ffprobe when available, falling back to FFmpeg itself.

    Render images sometimes expose the FFmpeg binary without a sibling ffprobe.
    Treating that environment difference as invalid media silently discarded
    every official source and produced the misleading '0 valid segments' gate.
    """
    p=Path(path)
    try:
        ffprobe=shutil.which('ffprobe')
        if ffprobe:
            cmd=[ffprobe,'-v','error','-show_entries','format=duration,size:stream=index,codec_type,width,height,codec_name','-of','json',str(p)]
            out=subprocess.check_output(cmd,stderr=subprocess.DEVNULL,text=True,timeout=30)
            d=json.loads(out); streams=d.get('streams',[]); fmt=d.get('format',{})
            video=[x for x in streams if x.get('codec_type')=='video']; audio=[x for x in streams if x.get('codec_type')=='audio']
            duration=float(fmt.get('duration') or 0)
            # ffprobe can successfully parse a container that has no video stream.
            # Do not return ok=True in that case: include its actual signature and
            # ffprobe's stream listing so the extraction format can be diagnosed.
            if video and duration>0:
                return {'ok':True,'duration':duration,'size':int(fmt.get('size') or (p.stat().st_size if p.exists() else 0)),'video':video,'audio':audio}
            try:
                with p.open('rb') as _src:
                    _head=_src.read(96)
                _magic=_head[:32].hex()
                _ascii=''.join(chr(b) if 32<=b<127 else '.' for b in _head[:64])
            except Exception as _e:
                _magic='unreadable'; _ascii=str(_e)[:80]
            raise RuntimeError(f'ffprobe não encontrou vídeo válido: duration={duration:.2f}s; streams={streams!r}; bytes={p.stat().st_size if p.exists() else 0}; magic={_magic}; head={_ascii}')
        # FFmpeg prints stream metadata and duration to stderr even when ffprobe
        # is not installed. -i intentionally exits non-zero without an output;
        # that is expected and the diagnostic is what we parse.
        ff=_ffmpeg_executable()
        proc=subprocess.run([ff,'-hide_banner','-i',str(p)],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True,timeout=30)
        diagnostic=proc.stderr or ''
        dm=re.search(r'Duration:\\s*(\\d+):(\\d+):(\\d+(?:\\.\\d+)?)',diagnostic)
        if not dm:
            raise RuntimeError('FFmpeg não encontrou duração legível: '+diagnostic[-250:])
        duration=int(dm.group(1))*3600+int(dm.group(2))*60+float(dm.group(3))
        video=[]; audio=[]
        for line in diagnostic.splitlines():
            if 'Video:' in line:
                cm=re.search(r'Video:\\s*([^,\\s]+)',line)
                sm=re.search(r'(\\d{2,5})x(\\d{2,5})',line)
                video.append({'index':len(video),'codec_type':'video','codec_name':cm.group(1) if cm else 'unknown',
                              'width':int(sm.group(1)) if sm else 0,'height':int(sm.group(2)) if sm else 0})
            if 'Audio:' in line:
                cm=re.search(r'Audio:\\s*([^,\\s]+)',line)
                audio.append({'index':len(audio),'codec_type':'audio','codec_name':cm.group(1) if cm else 'unknown'})
        if not video:
            try:
                with p.open('rb') as _src:
                    _head=_src.read(96)
                _magic=_head[:32].hex()
                _ascii=''.join(chr(b) if 32<=b<127 else '.' for b in _head[:64])
            except Exception as _e:
                _magic='unreadable'; _ascii=str(_e)[:80]
            raise RuntimeError('FFmpeg não detectou stream de vídeo; '
                f'bytes={p.stat().st_size if p.exists() else 0}; magic={_magic}; head={_ascii}; '
                f'diagnostic={diagnostic[-700:]}')
        return {'ok':True,'duration':duration,'size':p.stat().st_size if p.exists() else 0,'video':video,'audio':audio}
    except Exception as e:
        return {'ok':False,'error':str(e)[:500]}

def _job_output_is_valid(job):
    """Count a job as produced only when its final MP4 exists and probes as real A/V media."""
    rel=str((job or {}).get('video') or '').strip()
    if not rel:
        return False
    try:
        path=(WORK/rel).resolve()
        path.relative_to(WORK.resolve())
        st=path.stat()
        if not path.is_file() or st.st_size < 50000:
            return False
        key=(str(path),st.st_mtime_ns,st.st_size)
        with MEDIA_VALIDATION_LOCK:
            cached=MEDIA_VALIDATION_CACHE.get(key)
        if cached is not None:
            return cached
        probe=_probe_media(path)
        videos=probe.get('video') or []
        audios=probe.get('audio') or []
        valid=bool(probe.get('ok') and probe.get('size',0)>=50000 and videos and audios and
                   10 <= float(probe.get('duration') or 0) <= 65 and
                   int(videos[0].get('height') or 0) > int(videos[0].get('width') or 0))
        with MEDIA_VALIDATION_LOCK:
            if len(MEDIA_VALIDATION_CACHE)>500:
                MEDIA_VALIDATION_CACHE.clear()
            MEDIA_VALIDATION_CACHE[key]=valid
        return valid
    except Exception:
        return False



def _log_visual_contact_sheet(video_path, jid):
    """Emit a tiny sampled contact sheet to logs so remote visual QA can inspect frames."""
    if os.getenv('GTA_VISUAL_QA_LOG','0').strip().lower() not in ('1','true','yes','on'):
        return
    tmp=Path(str(video_path)+'.visual_qa')
    try:
        import base64, io
        tmp.mkdir(parents=True,exist_ok=True)
        ff=_ffmpeg_executable()
        cmd=[ff,'-hide_banner','-loglevel','error','-y','-i',str(video_path),
             '-vf','fps=1/5,scale=80:142:force_original_aspect_ratio=decrease,pad=80:142:(ow-iw)/2:(oh-ih)/2',
             '-frames:v','6','-q:v','10',str(tmp/'frame_%02d.jpg')]
        subprocess.run(cmd,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,timeout=25,check=True)
        frames=[]
        for fp in sorted(tmp.glob('frame_*.jpg'))[:6]:
            try:
                with Image.open(fp) as im:
                    frames.append(im.convert('RGB').copy())
            except Exception:
                pass
        if not frames:
            print(f'[VISUAL_QA] job={jid} no_frames_extracted',flush=True)
            return
        sheet=Image.new('RGB',(240,284),(10,12,16))
        for i,im in enumerate(frames):
            sheet.paste(im.resize((80,142)),((i%3)*80,(i//3)*142))
        buf=io.BytesIO()
        sheet.save(buf,format='JPEG',quality=28,optimize=True)
        encoded=base64.b64encode(buf.getvalue()).decode('ascii')
        # Split into small log records to avoid truncation by log transport.
        chunks=[encoded[i:i+2800] for i in range(0,len(encoded),2800)]
        print(f'[VISUAL_QA_BEGIN] job={jid} chunks={len(chunks)} width=240 height=284',flush=True)
        for i,chunk in enumerate(chunks):
            print(f'[VISUAL_QA_DATA] job={jid} part={i+1}/{len(chunks)} data={chunk}',flush=True)
        print(f'[VISUAL_QA_END] job={jid}',flush=True)
    except Exception as e:
        print(f'[VISUAL_QA] job={jid} failed={type(e).__name__}: {str(e)[:250]}',flush=True)
    finally:
        try: shutil.rmtree(tmp,ignore_errors=True)
        except Exception: pass


def _visual_motion_audit(path):
    """Audita o MP4 real em baixa resolução para detectar congelamento/repetição visual.
    Não usa análise semântica: mede mudança real entre amostras do vídeo.
    """
    tmp=Path(str(path)+'.motion_audit')
    tmp.mkdir(parents=True,exist_ok=True)
    try:
        ff=_ffmpeg_executable()
        # One low-resolution sample per second catches 2-3s static image holds.
        run_cmd([ff,'-loglevel','error','-y','-i',str(path),'-vf','fps=1,scale=48:85:flags=bilinear,format=gray',str(tmp/'frame_%04d.jpg')],25)
        frames=sorted(tmp.glob('frame_*.jpg'))
        if len(frames)<4:
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
                if run>=2: stale_runs.append({'start_s':round(start+1,1),'end_s':round(start+run+1,1),'duration_s':round(run,1)})
                run=0
        if run>=2: stale_runs.append({'start_s':round(start+1,1),'end_s':round(start+run+1,1),'duration_s':round(run,1)})
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

    coverage=matched/max(1,total)  # share of displayed caption words found in narration
    narration_coverage=matched/max(1,len(n))  # share of spoken words represented in captions
    foreign_ratio=foreign/max(1,total)
    score=100
    if narration_coverage<0.55: score-=45
    elif narration_coverage<0.72: score-=28
    elif narration_coverage<0.85: score-=14
    if foreign_ratio>0.15: score-=50
    elif foreign_ratio>0.08: score-=35
    elif foreign_ratio>0.03: score-=20
    elif foreign_ratio>0: score-=8
    if bad and any(len(x['words'])>=3 for x in bad): score-=20

    return {
        'score':max(0,min(100,score)),
        'bad':bad[:12],
        'coverage':round(coverage,3),
        'narration_coverage':round(narration_coverage,3),
        'foreign_ratio':round(foreign_ratio,3),
        'caption_count':len([b for b in beats or [] if str(b.get('text','')).strip()])
    }


def _visual_repetition_audit(path):
    """Detecta repetição de takes curtos e sequências quase idênticas no MP4 final.

    A antiga auditoria comparava apenas janelas de quatro amostras (8 segundos).
    Isso deixava passar um take de 1–2 segundos reutilizado em outro ponto do Short.
    Agora combinamos comparação de sequência com hash perceptual de quadros isolados,
    exigindo distância temporal para não penalizar frames vizinhos do mesmo take.
    """
    tmp=Path(str(path)+'.repeat_audit')
    tmp.mkdir(parents=True,exist_ok=True)
    try:
        ff=_ffmpeg_executable()
        run_cmd([ff,'-loglevel','error','-y','-i',str(path),'-vf','fps=0.5,scale=40:71:flags=bilinear,format=gray',str(tmp/'f_%04d.jpg')],60)
        frames=sorted(tmp.glob('f_*.jpg'))
        if len(frames)<8:
            return {'score':70,'repeated_ratio':0.0,'longest_repeat_s':0.0,'pairs':[],'frame_repeat_pairs':[],'error':'amostras insuficientes'}
        imgs=[]
        for fp in frames:
            try: imgs.append(Image.open(fp).convert('L').resize((48,85)))
            except Exception: pass
        if len(imgs)<8:
            return {'score':70,'repeated_ratio':0.0,'longest_repeat_s':0.0,'pairs':[],'frame_repeat_pairs':[],'error':'quadros inválidos'}

        # 1) Repetição de sequências longas (4 quadros, amostrados a cada 2s).
        seq_len=4; min_gap=6; matches=[]
        for i in range(0,min(24,max(1,len(imgs)-seq_len+1))):
            for j in range(i+min_gap, min(len(imgs)-seq_len+1, i+32)):
                ds=[]
                for k in range(seq_len):
                    stat=ImageStat.Stat(ImageChops.difference(imgs[i+k],imgs[j+k]))
                    ds.append(float(stat.mean[0]))
                avg=sum(ds)/len(ds)
                if avg<8.0:
                    matches.append((i,j,avg))

        # 2) Repetição de takes isolados: average-hash numa grelha 8x8 reduz
        # sensibilidade à cor/compressão, mas preserva composição e silhuetas.
        # Só compara quadros separados por >=6s; takes vizinhos não contam como loop.
        hashes=[]
        for im in imgs:
            tiny=im.resize((8,8))
            values=list(tiny.getdata())
            mean=sum(values)/max(1,len(values))
            hashes.append(tuple(v>=mean for v in values))
        frame_matches=[]
        near_frame_matches=[]
        frame_marks=set()
        for i in range(len(hashes)):
            # Frames are sampled every 2 seconds. Only compare the immediately
            # adjacent sample as a "near" duplicate; a 4-second gap can cross two
            # editorial beats and often matches a similar GTA composition by chance.
            # A 4-second pair counts only if its hashes are exactly identical.
            # Shots much farther apart use the looser threshold to catch recycled footage.
            for j in range(i+1,len(hashes)):
                gap=j-i
                distance=sum(a!=b for a,b in zip(hashes[i],hashes[j]))
                near_duplicate=(gap==1 and distance<=2) or (gap==2 and distance==0)
                distant_duplicate=(gap>=3 and distance<=6)
                if near_duplicate or distant_duplicate:
                    frame_matches.append((i,j,distance))
                    if near_duplicate:
                        near_frame_matches.append((i,j,distance))
                    frame_marks.add(i); frame_marks.add(j)

        # União para cobertura/repetição geral. Runs consecutivos são medidos
        # somente nas sequências longas: pares isolados em instantes distantes
        # não devem ser interpretados como um take contínuo.
        marks=set(frame_marks)
        sequence_marks=set()
        for i,j,_d in matches:
            for k in range(seq_len):
                marks.add(i+k); marks.add(j+k)
                sequence_marks.add(i+k); sequence_marks.add(j+k)
        ratio=len(marks)/max(1,len(imgs))
        longest=0; cur=0
        for k in range(len(imgs)):
            if k in sequence_marks: cur+=1; longest=max(longest,cur)
            else: cur=0
        longest_s=longest*2.0
        score=100
        if ratio>=0.45: score-=45
        elif ratio>=0.30: score-=32
        elif ratio>=0.20: score-=20
        elif ratio>=0.12: score-=10
        if longest_s>=8: score-=40
        elif longest_s>=6: score-=30
        elif longest_s>=4: score-=18
        # One or two near-identical samples can be normal during a pan/transition.
        # Penalize gently; the blocking gate below requires a cluster.
        if len(near_frame_matches)==2: score-=4
        elif len(near_frame_matches)>=3: score-=min(20,8+4*(len(near_frame_matches)-3))
        return {
            'score':max(0,min(100,score)),
            'repeated_ratio':round(ratio,3),
            'longest_repeat_s':round(longest_s,1),
            'pairs':[{'a_s':round(i*2.0,1),'b_s':round(j*2.0,1),'diff':round(d,2),'kind':'sequence'} for i,j,d in matches[:12]],
            'frame_repeat_pairs':[{'a_s':round(i*2.0,1),'b_s':round(j*2.0,1),'hash_distance':int(d)} for i,j,d in frame_matches[:20]],
            'near_frame_repeat_pairs':[{'a_s':round(i*2.0,1),'b_s':round(j*2.0,1),'hash_distance':int(d)} for i,j,d in near_frame_matches[:20]],
            'method':'sequence+perceptual-frame-hash+near-duplicate-detection',
            'sequence_window_s':8.0
        }
    except Exception as e:
        print(f'[VISUAL_REPEAT_AUDIT_ERROR] {type(e).__name__}: {str(e)[:500]}',flush=True)
        return {'score':65,'repeated_ratio':0.0,'longest_repeat_s':0.0,'pairs':[],'frame_repeat_pairs':[],'error':f'{type(e).__name__}: {str(e)[:400]}'}
    finally:
        try: shutil.rmtree(tmp,ignore_errors=True)
        except Exception: pass

def _persistent_source_subtitle_audit(path):
    """Detect persistent two-line source subtitles above the editor's own lower-third.
    This deliberately uses only Pillow/stdlib: no OCR models or heavy runtime dependency.
    A single frame is not enough (posters/shirt graphics can resemble text); the same
    text-like two-line structure must appear in adjacent 0.5-second samples.
    """
    tmp=Path(str(path)+'.source_subtitle_audit')
    tmp.mkdir(parents=True,exist_ok=True)
    try:
        ff=_ffmpeg_executable()
        run_cmd([ff,'-loglevel','error','-y','-i',str(path),
                 '-vf','fps=2,scale=270:480:flags=bilinear,format=gray',
                 str(tmp/'frame_%04d.png')],60)
        frame_paths=sorted(tmp.glob('frame_*.png'))
        if len(frame_paths)<8:
            return {
                'embedded_subtitle':False,'sample_count':len(frame_paths),
                'hit_times_s':[],'method':'persistent-two-line-source-text',
                'error':'amostras insuficientes para auditar legendas-fonte'
            }
        hits=[]
        for fi,fp in enumerate(frame_paths):
            try:
                im=Image.open(fp).convert('L')
                iw,ih=im.size
                # Exclude the app's designed caption card at the bottom. Check
                # the left/lower video area where baked-in gameplay captions appear.
                x0,y0,x1,y1=0,int(0.66*ih),int(0.46*iw),int(0.81*ih)
                crop=im.crop((x0,y0,x1,y1))
                cw,ch=crop.size
                px=crop.load()
                binary=bytearray(cw*ch)
                for yy in range(ch):
                    off=yy*cw
                    for xx in range(cw):
                        binary[off+xx]=1 if px[xx,yy]>185 else 0
                visited=bytearray(cw*ch)
                components=[]
                for idx,val in enumerate(binary):
                    if not val or visited[idx]:
                        continue
                    stack=[idx]
                    visited[idx]=1
                    minx=cw; miny=ch; maxx=0; maxy=0; area=0
                    while stack:
                        z=stack.pop()
                        yy,xx=divmod(z,cw)
                        area+=1
                        if xx<minx: minx=xx
                        if xx>maxx: maxx=xx
                        if yy<miny: miny=yy
                        if yy>maxy: maxy=yy
                        ya=max(0,yy-1); yb=min(ch-1,yy+1)
                        xa=max(0,xx-1); xb=min(cw-1,xx+1)
                        for ny in range(ya,yb+1):
                            base=ny*cw
                            for nx in range(xa,xb+1):
                                ni=base+nx
                                if binary[ni] and not visited[ni]:
                                    visited[ni]=1
                                    stack.append(ni)
                    ww=maxx-minx+1
                    hh=maxy-miny+1
                    # Small bright components arranged like glyphs; large
                    # bright scene objects (shirts, car panels, sky) are ignored.
                    if 2<=area<=100 and 1<=ww<=18 and 2<=hh<=16:
                        components.append((minx,miny,ww,hh,area))
                rows=[]
                for comp in sorted(components,key=lambda z:z[1]+z[3]/2):
                    cy=comp[1]+comp[3]/2
                    target=None
                    for row in rows:
                        median_y=statistics.median([z[1]+z[3]/2 for z in row])
                        if abs(cy-median_y)<=3.5:
                            target=row
                            break
                    if target is None:
                        rows.append([comp])
                    else:
                        target.append(comp)
                text_rows=[]
                for row in rows:
                    xs=[z[0] for z in row]
                    heights=[z[3] for z in row]
                    span=max(z[0]+z[2] for z in row)-min(xs) if row else 0
                    if len(row)>=4 and span>=25 and 3<=statistics.median(heights)<=15:
                        text_rows.append({
                            'count':len(row),
                            'span':int(span),
                            'y':float(statistics.median([z[1] for z in row]))
                        })
                paired=False
                for ri in range(len(text_rows)):
                    for rj in range(ri+1,len(text_rows)):
                        separation=abs(text_rows[ri]['y']-text_rows[rj]['y'])
                        if 7<=separation<=28 and min(text_rows[ri]['count'],text_rows[rj]['count'])>=4:
                            paired=True
                if paired:
                    hits.append(fi)
            except Exception:
                continue
        # Two samples only 0.5s apart can be a transient HUD element or scene detail.
        # Require three consecutive half-second hits (at least 1s) to call it a
        # persistent source subtitle and avoid blocking on brief visual coincidences.
        has_persistent=False
        for idx in range(max(0,len(hits)-2)):
            a,b,c=hits[idx:idx+3]
            if b==a+1 and c==b+1:
                has_persistent=True
                break
        times=[round(i/2.0,1) for i in hits]
        return {
            'embedded_subtitle':has_persistent,
            'sample_count':len(frame_paths),
            'hit_times_s':times[:12],
            'method':'persistent-two-line-source-text',
            'error':''
        }
    except Exception as e:
        return {
            'embedded_subtitle':False,
            'sample_count':0,
            'hit_times_s':[],
            'method':'persistent-two-line-source-text',
            'error':f'{type(e).__name__}: {str(e)[:250]}'
        }
    finally:
        try: shutil.rmtree(tmp,ignore_errors=True)
        except Exception: pass


def _visual_contamination_audit(path):
    """Final gate for rating/disclaimer cards and baked-in source subtitles."""
    bad=_video_contains_rating_disclaimer(path,sample_fps=2.0)
    source_text=_persistent_source_subtitle_audit(path)
    return {
        'score':0 if bad or source_text.get('embedded_subtitle') or source_text.get('error') else 100,
        'rating_disclaimer':bool(bad),
        'embedded_subtitle':bool(source_text.get('embedded_subtitle')),
        'subtitle_times':source_text.get('hit_times_s',[]),
        'subtitle_audit_error':source_text.get('error',''),
        'method':'horizontal-band-structure+persistent-source-text',
        'ok':not bad and not source_text.get('embedded_subtitle') and not source_text.get('error')
    }

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
    editorial_alignment=_editorial_topic_alignment(
        script.get('title') or '', narration, evidence,
        script.get('source_headline') or ''
    )
    # V68.8: preserve and validate the originally selected topic as a separate
    # invariant. The generated headline can be rewritten from evidence, but that
    # must not allow metadata for one topic to accompany narration about another.
    selected_topic=str(script.get('selected_topic_title') or '').strip()
    if selected_topic:
        # V68.9: evidence can support facts, but it must never compensate for
        # narration that has drifted away from the originally selected topic.
        # Compare the selected topic directly against spoken narration only.
        selected_alignment=_editorial_topic_alignment(
            selected_topic, narration, [], selected_topic
        )
        editorial_alignment['selected_topic_score']=selected_alignment['score']
        editorial_alignment['selected_topic_issues']=selected_alignment['issues']
        if not selected_alignment['ok']:
            editorial_alignment['ok']=False
            editorial_alignment['issues']=sorted(set(
                editorial_alignment.get('issues',[])+
                ['selected_topic_mismatch:'+issue for issue in selected_alignment['issues']]
            ))
            editorial_alignment['score']=min(editorial_alignment['score'],selected_alignment['score'])
    checks['alinhamento_pauta']=editorial_alignment['score']
    if not editorial_alignment['ok']:
        issues.append(('HEADLINE_SCRIPT_MISMATCH',
            'título, pauta e narração não estão alinhados: '+', '.join(editorial_alignment['issues'])))
    if not evidence:
        issues.append(('NO_EVIDENCE','roteiro sem evidência factual'))
        checks['roteiro']=0
    cap=_audit_caption_quality(beats); checks['legendas']=cap['score']
    alignment=_caption_narration_alignment(beats,narration); checks['alinhamento_legendas']=alignment['score']
    if cap.get('score',100)<85:
        # Try to repair caption segmentation once before blocking the entire Short.
        # Caption beats are derived from the narration, so reflowing word boundaries
        # is safe and does not alter the spoken script or factual content.
        try:
            _rebuilt=_repair_caption_beats(beats, float(duration))
            _rebuilt_audit=_audit_caption_quality(_rebuilt)
            _current_bad=len(cap.get('bad_end',[]))+len(cap.get('bad_start',[]))+len(cap.get('long',[]))+len(cap.get('short',[]))
            _rebuilt_bad=len(_rebuilt_audit.get('bad_end',[]))+len(_rebuilt_audit.get('bad_start',[]))+len(_rebuilt_audit.get('long',[]))+len(_rebuilt_audit.get('short',[]))
            if _rebuilt_audit.get('score',0)>cap.get('score',0) or _rebuilt_bad<_current_bad:
                beats=_rebuilt
                cap=_rebuilt_audit
                checks['legendas']=cap['score']
        except Exception as _caption_repair_error:
            print(f'[CAPTION_REPAIR] safe reflow failed: {str(_caption_repair_error)[:180]}',flush=True)
        if cap.get('score',100)<85:
            issues.append(('CAPTIONS_LOW_QUALITY',f'qualidade visual/segmentação das legendas abaixo do mínimo: {cap.get("score",0)}/100'))
    if alignment.get('narration_coverage',1.0)<0.98:
        issues.append(('CAPTIONS_INCOMPLETE',f'legendas representam apenas {alignment.get("narration_coverage",0)*100:.0f}% da narração'))
    boundary_bad_count=len(cap.get('bad_end',[]))+len(cap.get('bad_start',[]))
    # V55.5: only actual semantic boundary violations can trigger this issue.
    # Visual wrapping, caption length and line balance are quality signals, not semantic-boundary failures.
    boundary_severe=(boundary_bad_count>=max(4,int(len(beats or [])*0.55)))
    protected_splits=cap.get('protected_splits',[]) or []
    if boundary_severe or protected_splits:
        detail=('; termos divididos: '+', '.join(sorted({x.get('phrase','') for x in protected_splits if x.get('phrase')}))) if protected_splits else ''
        issues.append(('CAPTIONS_BAD_BOUNDARY','legendas com cortes semanticamente ruins'+detail))
    if alignment.get('foreign_ratio',0)>0.005 or alignment.get('score',100)<92:
        issues.append(('CAPTIONS_NOT_FROM_NARRATION',f'legendas contêm palavras fora da narração: {alignment.get("foreign_ratio",0)*100:.0f}%'))
    if cap.get('repeated_adjacent',0)>0: issues.append(('CAPTIONS_REPEATED','legenda repetida em blocos consecutivos'))
    media=_probe_media(video); checks['mp4']=100 if media.get('ok') else 0
    if not media.get('ok'): issues.append(('MEDIA_UNREADABLE',media.get('error','MP4 inválido')))
    else:
        dur=media['duration']; v=media['video']; a=media['audio']
        if not v: checks['mp4']-=50; issues.append(('NO_VIDEO_STREAM','MP4 sem vídeo'))
        if not a: checks['mp4']-=50; issues.append(('NO_AUDIO_STREAM','MP4 sem áudio'))
        actual_dims=(int(v[0].get('width',0)),int(v[0].get('height',0))) if v else (0,0)
        allowed_dims={(540,960),(720,1280),(1080,1920)}
        if v and actual_dims not in allowed_dims:
            checks['mp4']-=15; issues.append(('WRONG_ASPECT',f'dimensão do vídeo fora dos perfis verticais suportados: {actual_dims[0]}x{actual_dims[1]}'))
        if abs(dur-float(duration))>1.5: checks['mp4']-=10; issues.append(('DURATION_DRIFT',f'duração final {dur:.2f}s vs áudio {duration:.2f}s'))
        if media['size']<150000: checks['mp4']-=15; issues.append(('TINY_OUTPUT','MP4 suspeito: arquivo muito pequeno'))
    visual_safety=_visual_contamination_audit(video)
    checks['seguranca_visual']=visual_safety.get('score',0)
    if visual_safety.get('rating_disclaimer'):
        issues.append(('VISUAL_CONTAMINATION','tela ESRB/disclaimer detectada no vídeo final'))
    if visual_safety.get('embedded_subtitle'):
        times=', '.join(f'{t:.1f}s' for t in visual_safety.get('subtitle_times',[])[:4])
        issues.append(('VISUAL_SOURCE_SUBTITLE',
            'texto/legenda embutido no clipe-fonte foi detectado acima das legendas do editor'
            +(f' em {times}' if times else '')))
    if visual_safety.get('subtitle_audit_error'):
        issues.append(('VISUAL_SUBTITLE_AUDIT_FAILED',
            'a checagem de legendas embutidas não conseguiu concluir: '
            +str(visual_safety.get('subtitle_audit_error'))[:200]))
    checks['visuais']=100
    unique=len({str(x) for x in selected_videos})
    unique_images=len({str(x) for x in image_scenes})
    # A healthy fallback may contain only 2 official video clips plus a large
    # pool of unique researched/official frames. Count the combined visual pool.
    visual_pool=unique*2+unique_images
    if unique<4 and visual_pool<12:
        checks['visuais']-=15; issues.append(('LOW_VIDEO_VARIETY',f'apenas {unique} clipes únicos e {unique_images} imagens distintas'))
    # Image variety is optional on Render Free: never reject a healthy
    # video merely because the research returned fewer than four usable images.
    if len(images_available if 'images_available' in locals() else []) >= 4 and len(image_scenes)<2:
        checks['visuais']-=5; issues.append(('LOW_IMAGE_VARIETY','poucas imagens auxiliares'))
    # V67: Inspect the actual final MP4 by default. Asset-count-only motion
    # proxies missed 2-3s static holds. Sampling is downscaled to keep this bounded.
    # GTA_DEEP_VISUAL_AUDIT=0 is available only as a temporary resource fallback.
    deep_visual=os.getenv('GTA_DEEP_VISUAL_AUDIT','1').strip().lower() in {'1','true','yes','on'}
    if media.get('ok'):
        # A auditoria de repetição é obrigatória: deixar essa checagem atrás de
        # GTA_DEEP_VISUAL_AUDIT permitia que o plano Free aprovasse takes repetidos
        # com base apenas na contagem de arquivos distintos. A varredura é leve
        # (quadros pequenos em baixa frequência) e sempre roda no MP4 final.
        repetition=_visual_repetition_audit(video)
        print(
            f"[VISUAL_REPEAT_AUDIT] method={repetition.get('method','unknown')} "
            f"score={repetition.get('score',0)} ratio={repetition.get('repeated_ratio',0)} "
            f"pairs={len(repetition.get('frame_repeat_pairs',[])) + len(repetition.get('pairs',[]))} "
            f"error={str(repetition.get('error',''))[:180]}",
            flush=True
        )
        if deep_visual:
            motion=_visual_motion_audit(video)
        else:
            unique_visual_assets=len({str(x) for x in selected_videos})
            scene_assets=unique_visual_assets + len({str(x) for x in image_scenes})
            motion_score=94 if unique_visual_assets>=4 and scene_assets>=7 else (80 if unique_visual_assets>=3 else 60)
            motion={
                'score':motion_score,'frozen_ratio':0.0,'longest_still_seconds':0.0,
                'sample_count':0,'method':'timeline_structure',
                'note':'Proxy estrutural; auditoria quadro a quadro de movimento desativada no plano Free'
            }
    else:
        unique_visual_assets=len({str(x) for x in selected_videos})
        scene_assets=unique_visual_assets + len({str(x) for x in image_scenes})
        motion_score=94 if unique_visual_assets>=4 and scene_assets>=7 else (80 if unique_visual_assets>=3 else 60)
        repetition_score=94 if unique_visual_assets>=5 else (84 if unique_visual_assets>=3 else 65)
        motion={
            'score':motion_score,'frozen_ratio':0.0,'longest_still_seconds':0.0,
            'sample_count':0,'method':'timeline_structure',
            'note':'Proxy estrutural; mídia inválida; varredura visual não executada'
        }
        repetition={
            'score':repetition_score,'repeated_ratio':0.0,'longest_repeat_s':0.0,
            'pairs':[],'method':'asset_diversity',
            'note':'Proxy estrutural; mídia inválida; varredura visual não executada'
        }
    checks['movimento']=int(motion.get('score',0))
    if repetition.get('error'):
        checks['repeticao_visual']=0
        issues.append(('VISUAL_AUDIT_FAILED','auditoria de repetição visual não conseguiu inspecionar o MP4: '+str(repetition.get('error'))[:240]))
    else:
        checks['repeticao_visual']=int(repetition.get('score',0))
    if motion.get('longest_still_seconds',0)>=2:
        issues.append(('VISUAL_STAGNATION',f'visual praticamente parado por {motion.get("longest_still_seconds",0):.0f}s'))
    if motion.get('frozen_ratio',0)>=0.28:
        issues.append(('HIGH_FROZEN_RATIO',f'{motion.get("frozen_ratio",0)*100:.0f}% das transições amostradas com pouca mudança visual'))
    if not repetition.get('error') and (len(repetition.get('near_frame_repeat_pairs',[]))>=3 or repetition.get('score',100)<85 or repetition.get('repeated_ratio',0)>=0.24 or repetition.get('longest_repeat_s',0)>=4):
        issues.append(('VISUAL_REPETITION',f'repetição visual detectada: {repetition.get("repeated_ratio",0)*100:.0f}% das amostras / trecho repetido até {repetition.get("longest_repeat_s",0):.1f}s; quadros próximos repetidos={len(repetition.get("near_frame_repeat_pairs",[]))}'))
    final=max(0,round((checks['roteiro']+checks['alinhamento_pauta']+checks['legendas']+checks['alinhamento_legendas']+checks['mp4']+checks['visuais']+checks['movimento']+checks['repeticao_visual'])/8))
    return {'score':final,'checks':checks,'issues':[{'code':c,'message':m} for c,m in issues],'media':media,'caption_audit':cap,'motion_audit':motion,'repetition_audit':repetition}

def self_heal(jid, script, video, duration, beats, selected_videos, image_scenes, topic, audio):
    """Run bounded safe repairs. No endless retry and no self-modifying source code."""
    audit=audit_short(script,video,duration,beats,selected_videos,image_scenes)
    if audit['score']>=92 and not any(x['code'] in {'CAPTIONS_BAD_BOUNDARY','CAPTIONS_NOT_FROM_NARRATION','CAPTIONS_REPEATED','CAPTIONS_INCOMPLETE','CAPTIONS_LOW_QUALITY','VISUAL_REPETITION','VISUAL_STAGNATION','HIGH_FROZEN_RATIO','VISUAL_SOURCE_SUBTITLE','VISUAL_SUBTITLE_AUDIT_FAILED'} for x in audit.get('issues',[])): return audit,beats,False
    repaired=False
    codes={x['code'] for x in audit['issues']}
    if 'VISUAL_STAGNATION' in codes or 'HIGH_FROZEN_RATIO' in codes or 'VISUAL_REPETITION' in codes or 'VISUAL_SOURCE_SUBTITLE' in codes:
        # V66.9: o vídeo final é o objeto de QA. Se a auditoria real encontrar
        # repetição/congelamento, refazemos UMA única vez com outra combinação
        # de assets e movimento. Isso elimina a necessidade de o proprietário
        # baixar/enviar o MP4 para inspeção manual a cada produção.
        _learn_event(
            'VISUAL_REPETITION',
            'auditor detectou repetição/congelamento visual',
            're-render automático único com variante visual + motion boost',
            None
        )
        repair_path=Path(str(video)+'.visual_repair.mp4')
        try:
            update_job(
                jid,
                stage='AVALIAÇÃO',
                progress=95,
                log='🧠 AUDITOR IA: repetição/congelamento detectado. Refazendo a edição automaticamente (1/1)...'
            )
            beats=make_multimedia_video(
                selected_videos,
                image_scenes,
                audio,
                repair_path,
                duration,
                [b.get('text','') for b in beats],
                script=script,
                topic_title=topic.get('title','GTA 6'),
                beats=beats,
                motion_boost=True,
                asset_variant=1
            )
            repaired_probe=_probe_media(repair_path)
            if not repaired_probe.get('ok'):
                raise RuntimeError('reparo visual gerou MP4 inválido')
            # Auditar o arquivo temporário ANTES de substituir o vídeo original.
            # Se a variante não resolver a repetição, preservamos o MP4 original
            # para diagnóstico e o gate final bloqueia a entrega.
            repaired_audit=audit_short(script,repair_path,duration,beats,selected_videos,image_scenes)
            if any(x.get('code') in {'VISUAL_REPETITION','VISUAL_STAGNATION','HIGH_FROZEN_RATIO','VISUAL_SOURCE_SUBTITLE'} for x in repaired_audit.get('issues',[])):
                raise RuntimeError('a reedição ainda apresenta repetição/congelamento visual')
            os.replace(repair_path,video)
            audit=repaired_audit
            repaired=True
            update_job(
                jid,
                stage='AVALIAÇÃO',
                progress=95,
                log=f'🧠 AUDITOR IA: reedição automática concluída e aprovada ({audit.get("score",0)}/100).'
            )
        except Exception as visual_repair_error:
            try:
                if repair_path.exists():
                    repair_path.unlink()
            except Exception:
                pass
            _learn_event(
                'VISUAL_REPAIR_FAILED',
                'reparo visual automático não conseguiu eliminar o problema',
                str(visual_repair_error)[:500],
                False
            )
            update_job(
                jid,
                stage='AVALIAÇÃO',
                progress=95,
                log='🛑 AUDITOR IA: repetição visual permaneceu após a única reedição automática. Produção será bloqueada.'
            )
    caption_codes={'CAPTIONS_BAD_BOUNDARY','CAPTIONS_REPEATED','CAPTIONS_NOT_FROM_NARRATION','CAPTIONS_LOW_QUALITY','CAPTIONS_INCOMPLETE'}
    if any(x['code'] in caption_codes for x in audit['issues']):
        _learn_event(
            'CAPTIONS_BAD_BOUNDARY',
            'auditor detectou legenda que exige correção',
            'resegmentação semântica e uma única renderização corretiva antes do gate final',
            None
        )
        repair_path=Path(str(video)+'.caption_repair.mp4')
        try:
            update_job(
                jid,
                stage='AVALIAÇÃO',
                progress=95,
                log='🧠 AUDITOR IA: corrigindo a segmentação das legendas e renderizando novamente (1/1)...'
            )
            repaired_beats=build_short_timeline(script,topic,duration,count=min(15,max(12,len(beats or []))),word_cues=None)
            if not repaired_beats:
                raise RuntimeError('reconstrução a partir do roteiro aprovado não produziu legendas')
            _rebuild_audit=_audit_caption_quality(repaired_beats)
            if _rebuild_audit.get('bad_end') or _rebuild_audit.get('bad_start') or _rebuild_audit.get('protected_splits') or _rebuild_audit.get('long') or _rebuild_audit.get('short'):
                raise RuntimeError('legendas reconstruídas a partir do roteiro não passaram na auditoria semântica: '+json.dumps(_rebuild_audit,ensure_ascii=False)[:400])
            repaired_captions=[str(b.get('text','')).strip() for b in repaired_beats]
            if any(not caption for caption in repaired_captions):
                raise RuntimeError('resegmentação produziu legenda vazia')
            repaired_beats=make_multimedia_video(
                selected_videos,
                image_scenes,
                audio,
                repair_path,
                duration,
                repaired_captions,
                script=script,
                topic_title=topic.get('title','GTA 6'),
                beats=repaired_beats,
                motion_boost=False,
                asset_variant=0
            )
            repair_probe=_probe_media(repair_path)
            if not repair_probe.get('ok') or not repair_probe.get('video') or not repair_probe.get('audio'):
                raise RuntimeError('renderização corretiva gerou mídia inválida')
            repaired_audit=audit_short(script,repair_path,duration,repaired_beats,selected_videos,image_scenes)
            remaining_caption_issues=[i.get('code') for i in repaired_audit.get('issues',[]) if i.get('code') in caption_codes]
            if remaining_caption_issues:
                raise RuntimeError('auditoria ainda reprova legendas: '+', '.join(remaining_caption_issues))
            # Preserve the original until the corrected MP4 passes caption QA.
            os.replace(repair_path,video)
            audit=repaired_audit
            beats=repaired_beats
            repaired=True
            _learn_event(
                'CAPTIONS_REPAIR_SUCCEEDED',
                'resegmentação e renderização corretiva passaram pela auditoria de legendas',
                'resegmentação semântica max_words=6 + auditoria do MP4 renderizado',
                True
            )
            update_job(
                jid,
                stage='AVALIAÇÃO',
                progress=95,
                log=f'🧠 AUDITOR IA: legendas corrigidas e revalidadas ({audit.get("checks",{}).get("legendas",0)}/100).'
            )
        except Exception as caption_repair_error:
            try:
                if repair_path.exists():
                    repair_path.unlink()
            except Exception:
                pass
            _learn_event(
                'CAPTIONS_REPAIR_FAILED',
                'renderização corretiva de legendas não passou na auditoria',
                str(caption_repair_error)[:500],
                False
            )
            update_job(
                jid,
                stage='AVALIAÇÃO',
                progress=95,
                log='🛑 AUDITOR IA: legendas continuam reprovadas após uma tentativa de correção; mantendo o bloqueio.'
            )
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
    if video_count<4: score-=8
    if image_count<2: score-=4
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
    print(f'[JOB {jid}] START production worker',flush=True)
    try:
        update_job(jid,status='RUNNING',stage='PESQUISA',progress=5,log='V64.9: pesquisa limitada a 2 feeds RSS (6s cada) + Newswire opcional (5s).')
        print(f'[JOB {jid}] stage=RESEARCH start',flush=True)
        topics,urls,_=research_official(); topics=topics or FALLBACK_TOPICS
        print(f'[JOB {jid}] stage=RESEARCH done topics={len(topics)} visual_urls={len(urls)}',flush=True)
        radar_status=_load_radar()
        update_job(jid,progress=12,log='V64.9: pesquisa encerrada; fontes_ok={} status={} erro={}'.format(radar_status.get('sources_ok',0),radar_status.get('status','?'),radar_status.get('error') or radar_status.get('diagnostic','sem detalhe')))
        job=load_jobs()[jid]; topic=editor_chief_select([job['opportunity']]) or job['opportunity']; job['opportunity']=topic; jobs=load_jobs(); jobs[jid]['opportunity']=topic; save_jobs(jobs)
        update_job(jid,stage='ANÁLISE',progress=16,log=f'EDITOR-CHEFE: {topic.get("editorial_decision","PRODUZIR")} — {topic["title"]} | ângulo: {topic.get("editorial_angle","")}')
        update_job(jid,stage='ROTEIRO',progress=28,log='EDITOR-CHEFE → AGENTE AUTÔNOMO: validando corpo original, tentando estratégias e recuperando a pauta se necessário...')
        print(f'[JOB {jid}] stage=SCRIPT start topic={topic.get("title","")[:100]}',flush=True)
        topic, script = _autonomous_make_script(jid, topic, topics)
        print(f'[JOB {jid}] stage=SCRIPT done words={script.get("word_count",0)}',flush=True)
        # Keep the production card synchronized with the actual script that
        # passed preflight. A recovered candidate may replace the originally
        # selected topic; leaving the old job title would label a Jason/Lucia
        # video as a Leonida story even when the content gate correctly switched topics.
        final_script_title=str(script.get('title') or topic.get('title') or 'GTA 6').strip()
        if final_script_title:
            topic['title']=final_script_title
        topic['selected_topic_title']=str(script.get('selected_topic_title') or '')
        job=load_jobs().get(jid,{})
        job['opportunity']=topic
        job['title']=final_script_title
        jobs=load_jobs(); jobs[jid]=job; save_jobs(jobs)
        update_job(jid,title=final_script_title,opportunity=topic,
                   log='Pauta sincronizada com o título do roteiro aprovado; auditoria continua obrigatória.')
        jobdir=WORK/jid; jobdir.mkdir(parents=True,exist_ok=True)
        update_job(jid,script=script,stage='VISUAIS',progress=40,log='Baixando visuais oficiais e montando cenas verticais...')
        print(f'[JOB {jid}] stage=VISUALS download start',flush=True)
        # Prefer real official motion clips, but prepare a bounded image fallback up front.
        # Rockstar's own VI pages provide permitted visual references; selecting them
        # semantically lets a Short finish when the remote ZIP clip extraction is broken.
        image_candidates=download_visuals(urls,jobdir/'official_images',topic.get('title','GTA 6'))
        image_scenes=select_visuals(image_candidates,topic.get('title','GTA 6'),count=2)
        update_job(jid,progress=44,log=f'Plano visual: {len(image_scenes)} imagens de apoio (máximo 2); priorizando vídeos reais.')
        update_job(jid,stage='NARRAÇÃO',progress=60,log='Gerando narração PT-BR e capturando timestamps reais da fala...')
        print(f'[JOB {jid}] stage=TTS start',flush=True)
        audio=jobdir/'narracao.mp3'; word_cues=asyncio.run(make_tts(script['narration'],audio)); audio,word_cues=_compress_long_tts_pauses(audio,word_cues); duration=duration_of_audio(audio)
        print(f'[JOB {jid}] stage=TTS done audio_bytes={audio.stat().st_size if audio.exists() else 0} duration={duration:.1f}',flush=True)
        (jobdir/'word_cues.json').write_text(json.dumps(word_cues,ensure_ascii=False,indent=2),encoding='utf-8')
        # Editorial pacing: use more short beats so stills do not linger for 3-4 seconds.
        # Keep the narration duration unchanged; only increase the visual/caption beat density.
        timeline_count=max(14,_learned_timeline_count(duration,14))
        beats=build_short_timeline(script,topic,duration,timeline_count,word_cues=word_cues)
        # V63: corrigir a segmentação antes do encode final. Evita re-renderizações
        # completas posteriores no Render Free sem abrir mão do gate de legendas.
        _pre_cap=_audit_caption_quality(beats)
        _pre_align=_caption_narration_alignment(beats,script.get('narration',''))
        # If TTS word-boundary events omitted or corrupted words, rebuild captions from
        # the complete approved narration instead of repeatedly repairing incomplete text.
        if (_pre_align.get('foreign_ratio',0)>0.0 or _pre_align.get('narration_coverage',1.0)<0.98) and script.get('narration'):
            _complete_beats=build_short_timeline(script,topic,duration,_learned_timeline_count(duration,14),word_cues=None)
            if _complete_beats:
                beats=_complete_beats
            _pre_cap=_audit_caption_quality(beats)
            _pre_align=_caption_narration_alignment(beats,script.get('narration',''))
        if beats and (_pre_cap.get('score',100)<92 or _pre_cap.get('bad_start') or _pre_cap.get('bad_end') or _pre_cap.get('long') or _pre_cap.get('repeated_adjacent',0)):
            # Corrige também falhas pontuais de fronteira; nota alta não deve deixar uma legenda começar por 'de', 'para', 'e' etc.
            _fixed_beats=_repair_caption_beats(beats,duration,7)
            if _fixed_beats:
                beats=_fixed_beats
        _pre_cap=_audit_caption_quality(beats)
        _pre_align=_caption_narration_alignment(beats,script.get('narration',''))
        print(
            f"[CAPTION_PRECHECK] job={jid} score={_pre_cap.get('score',0)} "
            f"bad_end={len(_pre_cap.get('bad_end',[]))} "
            f"bad_start={len(_pre_cap.get('bad_start',[]))} "
            f"protected_splits={len(_pre_cap.get('protected_splits',[]))} "
            f"visual_bad={len(_pre_cap.get('visual_bad',[]))} "
            f"long={len(_pre_cap.get('long',[]))} short={len(_pre_cap.get('short',[]))} "
            f"repeated_adjacent={_pre_cap.get('repeated_adjacent',0)}",
            flush=True
        )
        # V68: fronteiras gramaticais são um sinal de qualidade, mas a heurística
        # pode marcar continuações naturais (ex.: demonstrativos/possessivos). Bloquear
        # qualquer ocorrência deixa a fila em ERROR sem produzir vídeo. Só falha fechado
        # quando os fragmentos dominam a timeline; problemas residuais leves são registrados.
        _boundary_count=len(_pre_cap.get('bad_end',[]))+len(_pre_cap.get('bad_start',[]))
        _boundary_limit=max(4,int(len(beats or [])*0.55))
        if _boundary_count>=_boundary_limit:
            raise ValueError(f'GATE CAPTIONS: fragmentos gramaticais graves após autocorreção ({_boundary_count}/{len(beats or [])} blocos).')
        if _boundary_count:
            print(f'[CAPTION_QA] job={jid} warning residual_boundaries={_boundary_count} blocks={len(beats or [])}; continuing to alignment/score gates',flush=True)
        if _pre_cap.get('score',100)<85:
            raise ValueError(f'GATE CAPTIONS: qualidade das legendas abaixo de 85/100 após autocorreção ({_pre_cap.get("score",0)}/100).')
        if _pre_align.get('foreign_ratio',0)>0.005 or _pre_align.get('narration_coverage',1.0)<0.98:
            raise ValueError('GATE CAPTIONS: as legendas não representam corretamente a narração após autocorreção.')
        caps=[b['text'] for b in beats]
        sync_mode='timestamps reais do Edge-TTS' if word_cues else 'fallback editorial pela duração real do áudio'
        update_job(jid,progress=66,log=f'Narração pronta: {script.get("word_count",0)} palavras / {duration:.1f}s. Legendas em {len(beats)} blocos — {sync_mode}.')
        update_job(jid,stage='EDIÇÃO',progress=74,log=f'Obtendo vídeos oficiais da Rockstar e montando timeline com movimento real / {duration:.1f}s...')
        print(f'[JOB {jid}] stage=OFFICIAL_VIDEO_DOWNLOAD start',flush=True)
        try:
            official_videos=download_official_video_clips(jobdir/'official_videos', jid)
        except Exception as _video_source_error:
            raise RuntimeError(
                f'GATE VISUAL: não foi possível obter vídeos oficiais com movimento suficiente; '
                f'não vou publicar um slideshow como substituto. {str(_video_source_error)[:700]}'
            )
        print(f'[JOB {jid}] stage=OFFICIAL_VIDEO_DOWNLOAD done count={len(official_videos)}',flush=True)
        # Do not mix stills extracted from the same clips with their moving footage.
        selected_videos=_expand_video_clips_into_distinct_windows(
            official_videos,jobdir,windows_per_clip=3
        ) if official_videos else []
        # Fallback seguro: se o recorte em janelas falhar, usar as fontes de vídeo
        # originais que passaram no probe. Cada fonte continua sendo movimento real;
        # a montagem recorta a duração de cada cena sem inventar quadros repetidos.
        if official_videos and len(selected_videos)<4:
            valid_sources=[]
            for _clip in official_videos or []:
                try:
                    _probe=_probe_media(Path(_clip))
                    if _probe.get('ok') and _probe.get('video') and float(_probe.get('duration') or 0)>=2.0:
                        valid_sources.append(Path(_clip))
                except Exception:
                    continue
            if len(valid_sources)>=4:
                print(f'[VIDEO_WINDOWS_FALLBACK] using {len(valid_sources)} validated original motion sources; segmented_windows={len(selected_videos)}',flush=True)
                selected_videos=valid_sources
            else:
                raise RuntimeError(
                    f'GATE VISUAL: recorte gerou {len(selected_videos)} segmentos utilizáveis e só {len(valid_sources)} fontes '
                    f'com movimento de pelo menos 2s; imagens disponíveis={len(image_scenes)}. '
                    'A produção foi bloqueada para não entregar um slideshow no lugar de vídeo.'
                )
        source_video_count=len(selected_videos)
        update_job(
            jid,
            log=f'{len(official_videos)} fontes oficiais divididas em {source_video_count} segmentos com movimento; '
                'frames estáticos das mesmas fontes excluídos para evitar repetição. '
                f'Editando em 9:16 / {duration:.1f}s...'
        )
        # Fit the edit to the actual one-use visual pool before rendering.
        # Timeline selection permits each original official source once and each
        # unique still once; counting two windows per source overstated capacity.
        available_slots=_visual_source_capacity(selected_videos)+len(set(map(str,image_scenes)))
        if available_slots < len(beats) and available_slots >= 6:
            fallback_count=min(available_slots,16)
            beats=build_short_timeline(script,topic,duration,fallback_count,word_cues=None)
            if len(beats)>fallback_count:
                raise RuntimeError(
                    f'GATE CAPTIONS: {len(beats)} semantic captions exceed the {fallback_count}-scene visual pool; '
                    'refusing to split narration by raw word counts.'
                )
            _fallback_cap=_audit_caption_quality(beats)
            if any(_fallback_cap.get(key) for key in ('bad_end','bad_start','protected_splits','long','short','visual_bad')):
                raise RuntimeError(f'GATE CAPTIONS: visual fallback captions failed final audit: {_fallback_cap}')
            caps=[b['text'] for b in beats]
            print(f'[JOB {jid}] visual fallback scenes={len(beats)} images={len(image_scenes)} videos={len(selected_videos)}',flush=True)
            update_job(jid,log=f'Fallback controlado: {len(selected_videos)} vídeos + {len(image_scenes)} visuais únicos; timeline reduzida para {len(beats)} cenas sem reciclagem.')
        if available_slots<len(beats):
            raise RuntimeError(f'GATE VISUAL: só {available_slots} slots visuais distintos para {len(beats)} cenas; não vou reciclar planos.')
        video=jobdir/'GTA_OCULTO_SHORT.mp4'
        print(f'[JOB {jid}] stage=RENDER start',flush=True)
        beats=make_multimedia_video(selected_videos,image_scenes,audio,video,duration,caps,script,topic['title'],beats)
        print(f'[JOB {jid}] stage=RENDER done exists={video.exists()} bytes={video.stat().st_size if video.exists() else 0}',flush=True)
        # Nunca deixe a capa derrubar uma produção já renderizada.
        print(f'[JOB {jid}] stage=POST_RENDER cover start',flush=True)
        if not image_scenes:
            fallback_cover=jobdir/'cover_fallback.jpg'
            make_fallback(fallback_cover,0,topic['title'])
            image_scenes=[fallback_cover]
        cover=jobdir/'CAPA.jpg'; make_cover(image_scenes[0],topic['title'],cover)
        print(f'[JOB {jid}] stage=POST_RENDER cover done exists={cover.exists()} bytes={cover.stat().st_size if cover.exists() else 0}',flush=True)
        update_job(jid,stage='AVALIAÇÃO',progress=92,log='Avaliando hook, ritmo, duração e sincronização real das legendas...')
        # V63.3: os mesmos arquivos já foram avaliados na seleção de visuais.
        # Não reler/redimensionar todos antes da auditoria final no Render Free.
        _unique_motion_sources=_visual_source_capacity(selected_videos)
        visual_quality=94 if _unique_motion_sources>=10 else (88 if _unique_motion_sources>=8 else (78 if _unique_motion_sources>=6 else 60))
        update_job(jid,stage='AVALIAÇÃO',progress=93,log='QA 1/3: integridade do MP4, codecs, áudio e duração...')
        # V41: auditor automático examina o MP4 real e tenta correções seguras antes do gate final.
        print(f'[JOB {jid}] stage=QA start',flush=True)
        audit,beats,repaired=self_heal(jid,script,video,duration,beats,selected_videos,image_scenes,topic,audio)
        print(f'[JOB {jid}] stage=QA done score={audit.get("score",0)} issues={len(audit.get("issues",[]))}',flush=True)
        update_job(jid,stage='AVALIAÇÃO',progress=94,log='QA 2/3 concluído: auditor editorial, legenda e mídia.')

        # V42: second independent bounded audit. It never replaces the proven
        # V41.3 renderer; it only gets one safe caption-repair attempt when the
        # independent audit detects weak caption segmentation.
        v42_audit = None
        if v42_full_audit and os.getenv('GTA_V42_AUDIT','0').strip().lower() in {'1','true','yes','on'}:
            try:
                update_job(jid,stage='AVALIAÇÃO',progress=95,log='QA 3/3: auditor independente V42 opcional...')
                v42_audit = v42_full_audit(video, [b.get('text','') for b in beats], script.get('narration',''))
            except Exception as _v42e:
                v42_audit={'score':None,'error':str(_v42e)[:500]}

        print(f'[JOB {jid}] stage=EVALUATE start',flush=True)
        score=evaluate(script,duration,len(beats),visual_quality,beats,len(selected_videos),len(image_scenes))
        print(f'[JOB {jid}] stage=EVALUATE done score={score}',flush=True)
        score=min(score,audit.get('score',score))
        if v42_audit and isinstance(v42_audit.get('score'),(int,float)):
            score=min(score,int(v42_audit['score']))
        audit['v42_independent']=v42_audit
        (jobdir/'audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
        update_job(jid,stage='AVALIAÇÃO',progress=96,log='🧠 AUDITOR IA: {}/100 | alinhamento pauta/roteiro: {}/100 | reparo automático: {} | problemas: {}.'.format(audit.get('score',0), audit.get('checks',{}).get('alinhamento_pauta',0), 'SIM' if repaired else 'NÃO', len(audit.get('issues',[]))))
        hard_issues={
            'HEADLINE_SCRIPT_MISMATCH','LOW_VIDEO_VARIETY',
            'CAPTIONS_NOT_FROM_NARRATION','CAPTIONS_BAD_BOUNDARY','CAPTIONS_REPEATED',
            'CAPTIONS_LOW_QUALITY','CAPTIONS_INCOMPLETE',
            'VISUAL_REPETITION','VISUAL_STAGNATION','HIGH_FROZEN_RATIO','VISUAL_AUDIT_FAILED','MEDIA_UNREADABLE',
            'NO_VIDEO_STREAM','NO_AUDIO_STREAM','WRONG_ASPECT','VISUAL_CONTAMINATION'
        }
        blocking=[i for i in audit.get('issues',[]) if i.get('code') in hard_issues]
        if (len(selected_videos)<4 and len(image_scenes)>=8) or (len(selected_videos)>=2 and len(image_scenes)>=8):
            blocking=[i for i in blocking if i.get('code')!='LOW_VIDEO_VARIETY']
        # V55.4: a mild boundary warning cannot block an otherwise aligned caption track.
        if any(i.get('code')=='CAPTIONS_BAD_BOUNDARY' for i in blocking):
            cap_a=audit.get('caption_audit',{}) or {}
            align_a=_caption_narration_alignment(beats,script.get('narration',''))
            severe_boundary=((len(cap_a.get('bad_end',[]))+len(cap_a.get('bad_start',[])))>=max(4,int(len(beats or [])*0.55)))
            if align_a.get('foreign_ratio',0)<=0.005 and align_a.get('score',100)>=92 and align_a.get('narration_coverage',1.0)>=0.98 and cap_a.get('repeated_adjacent',0)==0 and not severe_boundary:
                blocking=[i for i in blocking if i.get('code')!='CAPTIONS_BAD_BOUNDARY']
                audit.setdefault('notes',[]).append('V55.4: boundary leve aceito com alinhamento íntegro à narração.')
        if audit.get('score',0)<85 or blocking:
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
        if cap_alignment.get('foreign_ratio',0)>0.005 or cap_alignment.get('score',100)<92 or cap_alignment.get('narration_coverage',1.0)<0.98:
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
        final_video=jobdir/'GTA_OCULTO_SHORT.mp4'
        print(f'[JOB {jid}] stage=FINAL_VALIDATION start',flush=True)
        final_probe=_probe_media(final_video)
        print(f'[JOB {jid}] stage=FINAL_VALIDATION probe ok={final_probe.get("ok")} size={final_probe.get("size")} duration={final_probe.get("duration")}',flush=True)
        final_videos=final_probe.get('video') or []
        final_audios=final_probe.get('audio') or []
        if not (final_probe.get('ok') and final_probe.get('size',0)>=50000 and final_videos and final_audios and
                10 <= float(final_probe.get('duration') or 0) <= 65 and
                int(final_videos[0].get('height') or 0) > int(final_videos[0].get('width') or 0)):
            raise RuntimeError('VALIDAÇÃO FINAL: MP4 não passou no ffprobe (arquivo, vídeo vertical, áudio ou duração). Detalhe: '+json.dumps(final_probe,ensure_ascii=False)[:1200])
        meta['media_validation']={'ok':True,'size':final_probe['size'],'duration':final_probe['duration'],'video_codec':final_videos[0].get('codec_name'),'audio_codec':final_audios[0].get('codec_name'),'width':final_videos[0].get('width'),'height':final_videos[0].get('height')}
        (jobdir/'metadata.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
        update_job(jid,status='DONE',stage='PRONTO',progress=100,log=f'PRONTO — MP4 validado (vídeo + áudio + duração + vertical), nota {score}/100.',video=f'{jid}/GTA_OCULTO_SHORT.mp4',cover=f'{jid}/CAPA.jpg',score=score,metadata=meta,media_validation=meta['media_validation'])
        _log_visual_contact_sheet(final_video,jid)
        if AUTONOMOUS_ENGINE:
            try: AUTONOMOUS_ENGINE.on_done(jid,sys.modules[__name__])
            except Exception as _pub_e: update_job(jid,log=f'PRONTO — publicação automática aguardando configuração: {str(_pub_e)[:300]}')
    except Exception as e:
        import traceback
        tb=traceback.format_exc()
        print(f'[JOB {jid}] ERROR {type(e).__name__}: {str(e)[:1800]}',flush=True)
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


# V64.13: disparo de produção de teste controlado pelo servidor.
# Útil para validar uma versão recém-publicada sem depender de POST externo.
BOOT_PRODUCE_ONCE = os.getenv('GTA_BOOT_PRODUCE_ONCE','0').strip().lower() in ('1','true','yes','on')
BOOT_PRODUCE_TAG = os.getenv('GTA_BOOT_PRODUCE_TAG','legacy').strip() or 'legacy'
BOOT_PRODUCE_MARKER = WORK / ('.boot_produce_once_done' if BOOT_PRODUCE_TAG == 'legacy' else '.boot_produce_once_done_' + BOOT_PRODUCE_TAG.replace('/','_').replace('\\\\','_').replace(' ','_'))

def boot_produce_once():
    if not BOOT_PRODUCE_ONCE or BOOT_PRODUCE_MARKER.exists():
        return
    time.sleep(12)
    try:
        with APP.test_request_context('/api/produce', method='POST', json={}):
            response = produce()
        if getattr(response, 'status_code', 500) < 300:
            BOOT_PRODUCE_MARKER.write_text(now_iso(), encoding='utf-8')
            print('[BOOT_PRODUCE] Test production queued successfully.', flush=True)
        else:
            print(f'[BOOT_PRODUCE] Queue returned status {getattr(response, "status_code", "?")}; will retry on next server restart.', flush=True)
    except Exception as e:
        print(f'[BOOT_PRODUCE] Failed: {type(e).__name__}: {e}', flush=True)

def processor_loop():
    global PROCESSING
    # A Render deploy/restart can terminate the production thread without giving
    # it a chance to mark the job as finished. Recover RUNNING jobs immediately
    # on the first queue scan after boot; never do this again while this process
    # is alive, otherwise the watchdog could requeue its own active job.
    startup_recovery_pending=True
    while True:
        try:
            pending_files=[]
            pending_jobs=[]
            for pending_path in sorted(PENDING_QUEUE_DIR.glob('*.json'))[:20]:
                try:
                    pending_job=json.loads(pending_path.read_text(encoding='utf-8'))
                    if isinstance(pending_job,dict) and pending_job.get('id'):
                        pending_files.append(pending_path)
                        pending_jobs.append(pending_job)
                except Exception:
                    continue
            with LOCK:
                jobs=load_jobs()
                for pending_job in pending_jobs:
                    jobs.setdefault(str(pending_job['id']),pending_job)
                # If Render restarts after a long encode, a previous RUNNING job
                # is recovered instead of disappearing from the queue. Startup
                # recovery is safe because it only runs once per process lifetime.
                now=time.time()
                if startup_recovery_pending:
                    for j in jobs.values():
                        if j.get('status')=='RUNNING':
                            j['status']='QUEUED'; j['stage']='FILA'; j['progress']=0
                            j['log']='Watchdog de inicialização: Render reiniciou durante a produção. Job recuperado automaticamente para nova execução.'
                            j['recovered_at']=now_iso()
                    startup_recovery_pending=False
                for j in jobs.values():
                    if j.get('status')=='RUNNING':
                        try:
                            age=now-datetime.fromisoformat(j.get('updated_at','')).timestamp()
                        except Exception:
                            age=0
                        # V61 watchdog: a produção cloud não pode prender a fila
                        # indefinidamente se a thread morrer ou ficar órfã.
                        # 20 min é acima do tempo normal de pesquisa/TTS/render
                        # no plano Free, mas curto o bastante para recuperar a fila.
                        if age>1200:
                            j['status']='QUEUED'; j['stage']='FILA'; j['progress']=0
                            j['log']='Watchdog V61: produção RUNNING ficou sem atualização por 20 min. Job recuperado automaticamente.'
                            j['recovered_at']=now_iso()
                save_jobs(jobs)
                target=next((j for j in jobs.values() if j.get('status')=='QUEUED'),None)
            for pending_path in pending_files:
                try: pending_path.unlink(missing_ok=True)
                except Exception: pass
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
    return jsonify(ok=True,app='GTA Oculto AI',version=BUILD_VERSION,commit=os.environ.get('RENDER_GIT_COMMIT','unknown'),processor='cloud',autonomous_mode=AUTONOMOUS_MODE,max_topic_recovery=AUTONOMOUS_MAX_TOPIC_RECOVERY,autonomy=auto)
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

    produced=sum(1 for x in js if x.get('status')=='DONE' and _job_output_is_valid(x))
    return jsonify(opportunities=topics,jobs=js,produced=produced,queue=sum(x.get('status') in ('QUEUED','RUNNING') for x in js),radar_updated=updated,radar_status=radar_status,radar_error=radar_error,radar_sources_ok=sources_ok,editor_pick=editor_pick)
@APP.post('/api/research')
def research():
    try:
        radar=radar_scan(); return jsonify(ok=True,message=f'Radar atualizado: {len(radar.get("opportunities",[]))} oportunidades encontradas. Editor-Chefe pronto.',opportunities=radar.get('opportunities',[]),radar_updated=radar.get('updated_at'))
    except Exception as e: return jsonify(error=str(e)),502
@APP.route('/api/produce', methods=['GET','POST'])
def produce():
    # V64.2: enqueue through an isolated one-file queue; do not contend with
    # the processor's jobs-state lock while a video is being rendered.
    data=request.get_json(silent=True) or {}
    try:
        radar=_load_radar()
        topics=radar.get('opportunities') or FALLBACK_TOPICS
    except Exception:
        topics=FALLBACK_TOPICS
    topic=None
    requested_id=str(data.get('id') or '').strip()
    if requested_id:
        topic=next((dict(x) for x in topics if str(x.get('id',''))==requested_id),None)
    custom=str(data.get('topic') or '').strip()
    if topic is None and custom:
        topic={'id':'custom','score':88,'priority':'ALTA','title':custom,'source':'Pesquisa editorial','url':ROCKSTAR_VI,'radar':False}
    if topic is None:
        topic=max((dict(x) for x in topics),key=lambda x:(float(x.get('trend_score',0) or 0),float(x.get('score',0) or 0)))
    jid=uuid.uuid4().hex[:10]
    job={'id':jid,'title':topic['title'],'opportunity':topic,'status':'QUEUED','stage':'FILA','progress':0,'log':'Tarefa recebida. A produção cloud começará automaticamente.','video':None,'cover':None,'created_at':now_iso()}
    try:
        _atomic_write_json(PENDING_QUEUE_DIR / f'{jid}.json',job)
    except Exception as e:
        print(f'[PRODUCE_API] queue write failed: {type(e).__name__}: {e}',flush=True)
        return jsonify(ok=False,error='Não foi possível colocar o job na fila: '+str(e)[:300]),500
    print(f'[PRODUCE_API] queued job={jid} via pending file',flush=True)
    return jsonify(ok=True,job_id=jid,title=topic['title'])

@APP.get('/api/analytics/summary')
def analytics_summary():
    if not AUTONOMOUS_ENGINE:
        return jsonify(ok=False,reason='AUTONOMOUS_ENGINE_UNAVAILABLE'),503
    engine=AUTONOMOUS_ENGINE
    if request.args.get('refresh') == '1':
        try: engine.collect_analytics()
        except Exception as e: return jsonify(ok=False,reason='ANALYTICS_COLLECTION_FAILED: '+str(e)[:250]),502
    try: raw=(engine.memory.summary().get('metrics',{}) or {}).get('latest_analytics') or {}
    except Exception: raw={}
    last=getattr(engine,'last_analytics_result',None) or {}
    if not raw or not raw.get('ok'):
        return jsonify(ok=False,reason=last.get('reason') or 'Ainda não há coleta válida. Confira a configuração OAuth e as permissões do YouTube Analytics.',checked_at=last.get('checked_at')),503
    headers=[str(x.get('name','')).lower().replace(' ','') if isinstance(x,dict) else str(x).lower().replace(' ','') for x in (raw.get('headers') or [])]
    videos=[]
    for row in raw.get('rows') or []:
        if not isinstance(row,(list,tuple)): continue
        item={headers[i]:row[i] for i in range(min(len(headers),len(row)))}
        vid=str(item.get('video','') or '')
        if not vid: continue
        def num(key):
            try: return float(item.get(key,0) or 0)
            except (ValueError,TypeError): return 0.0
        videos.append({'video_id':vid,'title':vid,'views':int(num('views')),'likes':int(num('likes')),'likes_available':'likes' in headers,'comments':int(num('comments')),'comments_available':'comments' in headers,'subscribers_gained':int(num('subscribersgained')),'subscribers_available':'subscribersgained' in headers and raw.get('mode')!='public_stats_fallback','average_view_duration':num('averageviewduration'),'estimated_minutes_watched':num('estimatedminuteswatched')})
    try:
        token=os.getenv('YOUTUBE_TOKEN_JSON','').strip()
        if token and videos:
            import base64
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build
            if token.startswith('base64:'): token=base64.b64decode(token[7:]).decode()
            creds=Credentials.from_authorized_user_info(json.loads(token),['https://www.googleapis.com/auth/youtube.upload'])
            yt=build('youtube','v3',credentials=creds,cache_discovery=False); byid={v['video_id']:v for v in videos}
            for i in range(0,len(videos),50):
                ids=[v['video_id'] for v in videos[i:i+50]]
                for item in yt.videos().list(part='snippet,statistics',id=','.join(ids)).execute().get('items',[]):
                    v=byid.get(item.get('id'))
                    if v:
                        v['title']=(item.get('snippet') or {}).get('title') or v['title']; st=item.get('statistics') or {}
                        if 'likes' not in headers and 'likeCount' in st: v['likes']=int(st.get('likeCount',0) or 0);v['likes_available']=True
                        if 'comments' not in headers and 'commentCount' in st: v['comments']=int(st.get('commentCount',0) or 0);v['comments_available']=True
    except Exception: pass
    total=sum(v['views'] for v in videos); avg=round(total/len(videos)) if videos else 0
    likes_avail=any(v['likes_available'] for v in videos); subs_avail=any(v['subscribers_available'] for v in videos); comments_avail=any(v['comments_available'] for v in videos)
    watch_avail='estimatedminuteswatched' in headers; duration_avail='averageviewduration' in headers; source=raw.get('mode','youtube_analytics')
    recommendation='Ainda não há dados suficientes para recomendar um padrão.'
    if videos:
        top=max(videos,key=lambda v:v['views']); recommendation=f"Entre os vídeos retornados, ‘{top['title']}’ lidera com {top['views']} visualizações. Use o assunto e o gancho como hipótese para novos testes; isso não garante repetir o resultado."
    return jsonify(ok=True,start=raw.get('start'),end=raw.get('end'),source=source,video_count=len(videos),total_views=total,average_views=avg,total_likes=sum(v['likes'] for v in videos),likes_available=likes_avail,subscribers_gained=sum(v['subscribers_gained'] for v in videos),subscribers_available=subs_avail,total_comments=sum(v['comments'] for v in videos),comments_available=comments_avail,watch_minutes=sum(v['estimated_minutes_watched'] for v in videos),watch_minutes_available=watch_avail,average_view_duration=(sum(v['average_view_duration'] for v in videos)/len(videos) if videos else 0),duration_available=duration_avail,videos=sorted(videos,key=lambda v:v['views'],reverse=True)[:20],recommendation=recommendation,checked_at=last.get('checked_at'))

@APP.get('/api/youtube/status')
def youtube_status():
    if not AUTONOMOUS_ENGINE:
        return jsonify(enabled=False, configured=False, reason='AUTONOMOUS_ENGINE_UNAVAILABLE')
    pub=getattr(AUTONOMOUS_ENGINE,'publisher',None)
    if not pub:
        return jsonify(enabled=False, configured=False, reason='YOUTUBE_PUBLISHER_UNAVAILABLE')
    return jsonify(
        enabled=bool(getattr(pub,'enabled',False)),
        configured=bool(getattr(pub,'token_json','')),
        privacy=os.getenv('YOUTUBE_PRIVACY','private'),
        analytics_enabled=bool(getattr(getattr(AUTONOMOUS_ENGINE,'analytics',None),'enabled',False)),
    )

@APP.post('/api/publish/<jid>')
def publish_existing(jid):
    """Manually publish one validated DONE job; useful for the first private test."""
    if not AUTONOMOUS_ENGINE:
        return jsonify(ok=False,error='AUTONOMOUS_ENGINE indisponível.'),503
    job=load_jobs().get(jid)
    if not job:
        return jsonify(ok=False,error='job não encontrado'),404
    if job.get('status')!='DONE':
        return jsonify(ok=False,error='O job precisa estar DONE antes da publicação.'),409
    rel=str(job.get('video') or '').strip()
    if not rel:
        return jsonify(ok=False,error='Este job não possui vídeo final.'),409
    try:
        video=(WORK/rel).resolve()
        if WORK.resolve() not in video.parents:
            return jsonify(ok=False,error='caminho de vídeo inválido'),400
    except Exception:
        return jsonify(ok=False,error='caminho de vídeo inválido'),400
    if not video.exists() or video.stat().st_size < 50000:
        return jsonify(ok=False,error='MP4 final não encontrado ou inválido no workspace.'),409
    meta=job.get('metadata') or {}
    pub=AUTONOMOUS_ENGINE.publisher.upload(video,meta)
    if pub.get('ok'):
        try:
            if AUTONOMOUS_ENGINE.trend_brain:
                AUTONOMOUS_ENGINE.trend_brain.record_publication(job.get('opportunity') or {},meta,pub.get('video_id'))
        except Exception:
            pass
        update_job(jid,stage='PUBLICAÇÃO',log=f'▶️ YouTube: publicação manual concluída ({pub.get("video_id")}).',youtube=pub)
        return jsonify(ok=True,youtube=pub)
    update_job(jid,log=f'⚠️ YouTube: publicação não concluída — {pub.get("reason","erro desconhecido")}',youtube=pub)
    return jsonify(ok=False,youtube=pub),502

@APP.get('/api/job/<jid>')
def one(jid):
    j=load_jobs().get(jid)
    if j: return jsonify(j)
    pending=PENDING_QUEUE_DIR / f'{jid}.json'
    if pending.exists():
        try: return jsonify(json.loads(pending.read_text(encoding='utf-8')))
        except Exception: pass
    return jsonify(error='not found'),404
LIVE_JOBS_FILE = WORK / 'live_jobs.json'
LIVE_JOBS_LOCK = threading.RLock()

def _live_jobs():
    try:
        return json.loads(LIVE_JOBS_FILE.read_text(encoding='utf-8'))
    except Exception:
        return {}

def _save_live_jobs(d):
    tmp=LIVE_JOBS_FILE.with_suffix('.tmp')
    tmp.write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding='utf-8')
    os.replace(tmp,LIVE_JOBS_FILE)

def _live_update(jid, **fields):
    with LIVE_JOBS_LOCK:
        d=_live_jobs(); j=d.setdefault(jid,{'id':jid}); j.update(fields); j['updated_at']=now_iso(); _save_live_jobs(d)

def _live_analyze_worker(jid, source, max_clips):
    try:
        _live_update(jid,status='RUNNING',stage='ANALISANDO',progress=5,log='Analisando a live em blocos, sem carregar o vídeo inteiro na memória.')
        result=LiveClipper(WORK).analyze(source,max_clips=max_clips,job_id=jid)
        _live_update(jid,status='DONE',stage='CORTES_ENCONTRADOS',progress=100,result=result,clips=result.get('clips',[]),log=f'Encontrados {len(result.get("clips",[]))} cortes candidatos.')
    except Exception as e:
        _live_update(jid,status='ERROR',stage='ERRO',progress=100,error=str(e)[:2500])

def _live_render_worker(jid, source, clips):
    try:
        _live_update(jid,status='RUNNING',stage='RENDERIZANDO',progress=5,log='Renderizando os melhores cortes em vertical 9:16.')
        jobdir=WORK/'live_clips'/jid; jobdir.mkdir(parents=True,exist_ok=True)
        engine=LiveClipper(WORK); outputs=[]
        total=min(20,len(clips))
        for i,clip in enumerate(clips[:20],1):
            out=engine.render_clip(source,clip,jobdir,i); outputs.append(str(out.relative_to(WORK)))
            _live_update(jid,progress=int(5+(i/total)*90),log=f'Corte {i}/{total} renderizado.')
        _live_update(jid,status='DONE',stage='PRONTO',progress=100,outputs=outputs,log=f'{len(outputs)} cortes prontos.')
    except Exception as e:
        _live_update(jid,status='ERROR',stage='ERRO',progress=100,error=str(e)[:2500])

@APP.post('/api/live/analyze')
def live_analyze():
    if not LiveClipper: return jsonify(error='Live Clipper indisponível no servidor.'),503
    data=request.get_json(silent=True) or {}
    source=str(data.get('url') or data.get('source') or '').strip()
    try: max_clips=max(1,min(20,int(data.get('max_clips',10) or 10)))
    except Exception: max_clips=10
    if not source: return jsonify(error='Informe a URL pública ou caminho do arquivo da live.'),400
    jid='live-'+uuid.uuid4().hex[:10]
    _live_update(jid,status='QUEUED',stage='FILA',progress=0,source=source,max_clips=max_clips)
    threading.Thread(target=_live_analyze_worker,args=(jid,source,max_clips),daemon=True).start()
    return jsonify(ok=True,job_id=jid)

@APP.post('/api/live/render')
def live_render():
    if not LiveClipper: return jsonify(error='Live Clipper indisponível no servidor.'),503
    data=request.get_json(silent=True) or {}
    source=str(data.get('url') or data.get('source') or '').strip()
    clips=data.get('clips') or []
    if not source or not isinstance(clips,list) or not clips: return jsonify(error='Informe source e clips.'),400
    jid='live-'+uuid.uuid4().hex[:10]
    _live_update(jid,status='QUEUED',stage='FILA_RENDER',progress=0,source=source,clips=clips[:20])
    threading.Thread(target=_live_render_worker,args=(jid,source,clips[:20]),daemon=True).start()
    return jsonify(ok=True,job_id=jid)

@APP.get('/api/live/job/<jid>')
def live_job(jid):
    j=_live_jobs().get(jid)
    return (jsonify(j) if j else (jsonify(error='not found'),404))

@APP.get('/output/<path:p>')
def output(p):
    full=(WORK/p).resolve(); base=WORK.resolve()
    if not str(full).startswith(str(base)):
        return 'Not found',404
    if full.exists():
        return send_from_directory(full.parent,full.name,as_attachment=False)
    # Render Free has ephemeral local storage. If a published MP4 was removed
    # after a restart/redeploy, recover transparently through the durable YouTube copy.
    parts=Path(p).parts
    jid=parts[0] if parts else ''
    try:
        job=load_jobs().get(jid,{})
        yt=job.get('youtube') or {}
        vid=str(yt.get('video_id') or '').strip()
        if vid:
            return redirect(f'https://www.youtube.com/watch?v={quote(vid)}',code=302)
    except Exception:
        pass
    return 'Not found',404

def radar_loop():
    time.sleep(8)
    while True:
        try: radar_scan()
        except Exception: pass
        time.sleep(15*60)

def autonomy_loop():
    if not AUTONOMOUS_ENGINE: return
    # Run one early diagnostic after boot, then retain the six-hour cadence.
    # This confirms whether the configured OAuth token really has Analytics scope.
    time.sleep(45)
    while True:
        try:
            AUTONOMOUS_ENGINE.collect_analytics()
        except Exception as e:
            print(f'[AUTONOMY] analytics loop error: {type(e).__name__}: {str(e)[:300]}', flush=True)
        time.sleep(6*60*60)

threading.Thread(target=processor_loop,daemon=True).start()
threading.Thread(target=boot_produce_once,daemon=True).start()
threading.Thread(target=radar_loop,daemon=True).start()
threading.Thread(target=autonomy_loop,daemon=True).start()
if __name__=='__main__': APP.run(host='0.0.0.0',port=int(os.environ.get('PORT',5000)))
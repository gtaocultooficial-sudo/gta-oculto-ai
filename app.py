import struct, zlib
import os, json, uuid, threading, time, asyncio, subprocess, shutil, re, sys, math
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

import requests
import xml.etree.ElementTree as ET
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
UA = 'GTA-Oculto-AI/Cloud-Final/1.2-V28'
ROCKSTAR_VI = 'https://www.rockstargames.com/VI'
ROCKSTAR_NEWS = 'https://www.rockstargames.com/newswire/article/4k138k8okkk483/grand-theft-auto-vi-an-extended-look-now-playing'
ROCKSTAR_VIDEO_ZIP = 'https://media-rockstargames-com.akamaized.net/VI/downloads/videos/GTAVI_Videos.zip'

FALLBACK_TOPICS = [
    {'id':'leonida','score':96,'priority':'ALTA','title':'GTA 6: o detalhe de Leonida que pode mudar a história','source':'Rockstar Games','url':ROCKSTAR_VI},
    {'id':'jason-lucia','score':93,'priority':'ALTA','title':'Jason e Lucia: o que a Rockstar já confirmou oficialmente','source':'Rockstar Games','url':ROCKSTAR_VI},
    {'id':'estado-leonida','score':90,'priority':'ALTA','title':'A história de GTA 6 vai muito além de Vice City','source':'Rockstar Games','url':ROCKSTAR_NEWS},
    {'id':'detalhes','score':84,'priority':'MÉDIA','title':'Os detalhes escondidos que a Rockstar colocou em GTA 6','source':'Rockstar Games','url':ROCKSTAR_VI},
]

RADAR_FILE = WORK / 'radar.json'
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
    let epType=String(ep.content_type||'CURIOSIDADE').toUpperCase();let epMats=Number(ep.mentions||1);let epSources=Number(ep.source_count||1);let epConf=Math.max(0,Math.min(100,Number(ep.confidence||0)));let epScore=Number(ep.score||0);let epEd=Number(ep.editorial_score||0);let decisionClass=decision==='OBSERVAR'?'obs':'';let icon=epType==='RUMOR'?'⚠️':(epType==='NOTÍCIA'?'📰':'🔎');document.getElementById('editorPick').innerHTML=`<div class="editor-shell"><div class="editor-head"><div class="editor-brand"><div class="editor-icon">🧠</div><div><h2>EDITOR-CHEFE</h2><p>Analisa o Radar, escolhe a melhor pauta e prepara a produção.</p></div></div><div class="editor-actions"><div class="editor-status">✓ PAUTA SELECIONADA</div></div></div><div class="editor-grid-main"><div class="editor-cover"><div class="editor-cover-icon">${icon}</div></div><div class="editor-content"><span class="editor-tag">${esc(epType)}</span><div class="editor-title">${esc(ep.title)}</div><div class="editor-metrics"><div class="editor-metric"><small>SCORE RADAR</small><b class="metric-green">${epScore}/100</b></div><div class="editor-metric"><small>SCORE EDITORIAL</small><b class="metric-purple">${epEd}/100</b></div><div class="editor-metric"><small>CONFIANÇA</small><b>${epConf}%</b></div><div class="editor-metric"><small>MATÉRIAS</small><b>${epMats}</b></div><div class="editor-metric"><small>FONTES</small><b>${epSources}</b></div></div><div class="editor-copy"><div class="editor-hook"><b>⚡ HOOK DO VÍDEO</b><span>${esc(ep.editorial_hook||'')}</span></div><div class="editor-angle"><b>🎯 ÂNGULO EDITORIAL</b><span>${esc(ep.editorial_angle||'')}</span></div></div><div class="script-preview"><div class="script-head"><div><b>📝 ROTEIRO AUTOMÁTICO</b><span>V28 · estrutura pronta para narração</span></div><div class="script-stats">${Number((ep.script_preview||{}).word_count||0)} palavras · ~${Number((ep.script_preview||{}).estimated_seconds||0)}s</div></div><div class="script-flow"><div><small>HOOK</small><span>${esc(((ep.script_preview||{}).sections||{}).hook||ep.editorial_hook||'')}</span></div><div><small>CONTEXTO</small><span>${esc(((ep.script_preview||{}).sections||{}).context||'')}</span></div><div><small>FATO / VERIFICAÇÃO</small><span>${esc(((ep.script_preview||{}).sections||{}).proof||'')}</span></div><div><small>PAYOFF</small><span>${esc(((ep.script_preview||{}).sections||{}).payoff||ep.editorial_angle||'')}</span></div><div><small>CTA</small><span>${esc(((ep.script_preview||{}).sections||{}).cta||'')}</span></div></div></div><div class="meta">${esc(ep.editorial_reason||'')}</div></div><div class="editor-decision ${decisionClass}"><div class="decision-check">${decision==='OBSERVAR'?'◌':'✓'}</div><div class="decision-word">${esc(decision)}</div><div class="decision-reason">${esc(ep.editorial_reason||'Pauta selecionada pelo Editor-Chefe.')}</div><button class="editor-produce" onclick="createShort('${ep.id||''}')">⚡ PRODUZIR AGORA</button></div></div></div>`;
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
        tmp=RADAR_FILE.with_suffix('.tmp')
        tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
        tmp.replace(RADAR_FILE)
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


def make_script(topic):
    """V28 — Roteirista automático: cria um roteiro editorial estruturado, curto e narrável em PT-BR."""
    title=str(topic.get('title','GTA 6')).strip()
    t=title.lower()
    kind=str(topic.get('content_type') or 'CURIOSIDADE').upper()
    if kind not in ('RUMOR','MISTÉRIO','NOTÍCIA','CURIOSIDADE'):
        if any(k in t for k in ('rumor','leak','vazamento','suposto','suspeita')): kind='RUMOR'
        elif any(k in t for k in ('teoria','theory','pista','mistério','misterio','segredo','detalhe','escond')): kind='MISTÉRIO'
        elif any(k in t for k in ('confirm','revel','anunci','news','notícia','noticia','atualização','update','garante','explica')): kind='NOTÍCIA'
        else: kind='CURIOSIDADE'

    angle=str(topic.get('editorial_angle') or _editorial_angle(topic)[0]).strip()
    hook=str(topic.get('editorial_hook') or _editorial_angle(topic)[1]).strip()
    confidence=topic.get('confidence')
    source_count=int(topic.get('source_count',1) or 1)
    mentions=int(topic.get('mentions',1) or 1)
    source_name=str(topic.get('source','Radar GTA VI')).strip()
    conf_text=f'As informações reunidas pelo Radar aparecem em {mentions} matéria(s), de {source_count} fonte(s), com confiança estimada em {confidence}%.' if confidence is not None else ''

    # O roteiro não inventa detalhes ausentes da pauta. Ele trabalha com o título,
    # classificação e sinais de verificação disponíveis no Radar.
    if kind=='RUMOR':
        opening=hook
        context=f'Está circulando a seguinte informação sobre GTA 6: {title}.'
        proof='O Radar encontrou sinais de repercussão, mas isso não transforma a informação em confirmação oficial.'
        payoff=f'{angle} O ponto aqui é separar o que foi noticiado do que ainda é especulação.'
        cta='Se isso se confirmar, você acha que muda alguma coisa importante no jogo?'
    elif kind=='NOTÍCIA':
        opening=hook
        context=f'A pauta que está chamando atenção é esta: {title}.'
        proof=f'{conf_text} O mais importante é entender exatamente o que a notícia sustenta, sem aumentar a manchete.'
        payoff=f'{angle} Isso dá um contexto melhor para entender por que o assunto está repercutindo agora.'
        cta='Você acha que essa novidade vai fazer diferença em GTA 6?'
    elif kind=='MISTÉRIO':
        opening=hook
        context=f'Existe um detalhe que chamou atenção em GTA 6: {title}.'
        proof='O detalhe pode gerar interpretações, mas interpretação não deve ser apresentada como confirmação.'
        payoff=f'{angle} O interessante é observar a conexão sem transformar uma hipótese em fato.'
        cta='Coincidência ou pista? Quero saber a sua teoria.'
    else:
        opening=hook
        context=f'Olha esse detalhe de GTA 6: {title}.'
        proof=f'{conf_text} O assunto ganhou destaque porque pode ser conectado ao que já foi mostrado sobre o jogo.' if conf_text else 'O assunto ganhou destaque porque pode ser conectado ao que já foi mostrado sobre o jogo.'
        payoff=f'{angle} E é justamente essa conexão que deixa a pauta interessante.'
        cta='Você já tinha percebido esse detalhe?'

    # Evita excesso de contexto e mantém o vídeo em faixa curta de Shorts.
    body=[opening, context, proof, payoff, cta]
    narration=' '.join(x.strip() for x in body if x.strip())
    words=len(re.findall(r"\b[\wÀ-ÿ'’-]+\b", narration))
    # Velocidade aproximada de narração PT-BR; o áudio real continua sendo a referência.
    estimated_seconds=max(22, min(58, round(words/2.35)))

    return {
        'title':title,
        'narration':narration,
        'source':topic.get('url',ROCKSTAR_VI),
        'source_name':source_name,
        'content_type':kind,
        'editorial_angle':angle,
        'editorial_hook':hook,
        'editorial_score':topic.get('editorial_score'),
        'editorial_decision':topic.get('editorial_decision','PRODUZIR'),
        'editorial_reason':topic.get('editorial_reason',''),
        'sections':{
            'hook':opening,
            'context':context,
            'proof':proof,
            'payoff':payoff,
            'cta':cta,
        },
        'word_count':words,
        'estimated_seconds':estimated_seconds,
        'script_version':'V28'
    }


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


def make_script(topic):
    """Editor-Chefe V27: transforma a pauta escolhida em roteiro com ângulo e hook próprios."""
    title=str(topic.get('title','GTA 6')).strip()
    t=title.lower()
    kind=topic.get('content_type') or 'CURIOSIDADE'
    if kind not in ('RUMOR','MISTÉRIO','NOTÍCIA','CURIOSIDADE'):
        if any(k in t for k in ('rumor','leak','vazamento','suposto')): kind='RUMOR'
        elif any(k in t for k in ('teoria','theory','pista','mistério','misterio','segredo','detalhe','escond')): kind='MISTÉRIO'
        elif any(k in t for k in ('confirm','revel','anunci','news','notícia','noticia','atualização','update')): kind='NOTÍCIA'
        else: kind='CURIOSIDADE'
    angle=str(topic.get('editorial_angle') or _editorial_angle(topic)[0])
    hook=str(topic.get('editorial_hook') or _editorial_angle(topic)[1])
    confidence=topic.get('confidence')
    source_count=topic.get('source_count',1)
    source_name=topic.get('source','Pesquisa editorial')
    verification=(f"A pauta aparece em {source_count} fonte(s) e está com confiança estimada de {confidence}%." if confidence is not None else '')

    if kind=='RUMOR':
        narration=(f'{hook}. {title}. '
        f'{verification} O ponto importante é não confundir repercussão com confirmação oficial. '
        f'{angle} Até agora, o que não estiver confirmado pela Rockstar precisa ser tratado como possibilidade. '
        'Se isso se confirmar, pode mudar a forma como enxergamos essa parte de GTA 6. '
        'Você acha que existe algo por trás dessa informação?')
    elif kind=='MISTÉRIO':
        narration=(f'{hook}. {title}. '
        f'{angle} Esse detalhe chama atenção porque se conecta ao que a Rockstar já mostrou sobre GTA 6. '
        'Mas existe uma diferença entre uma pista e uma confirmação: aqui estamos falando de interpretação. '
        'Se essa leitura estiver certa, ela pode revelar algo interessante sobre Leonida. '
        'Você acha que isso é coincidência ou pista?')
    elif kind=='NOTÍCIA':
        narration=(f'{hook}. {title}. '
        f'{verification} {angle} O que importa aqui é o impacto dessa informação para o jogo, e não apenas a manchete. '
        'A Rockstar já confirmou parte do cenário de GTA 6, mas qualquer conclusão além disso precisa ser apresentada com cuidado. '
        'Agora a pergunta é: o que essa novidade pode mudar no jogo?')
    else:
        narration=(f'{hook}. {title}. '
        f'{angle} Quando colocamos esse detalhe ao lado do material oficial de GTA 6, ele fica ainda mais interessante. '
        'Isso não significa que exista uma confirmação por trás da interpretação, mas é um ponto que vale observar. '
        'Você já tinha percebido esse detalhe?')

    return {'title':title,'narration':narration,'source':topic.get('url',ROCKSTAR_VI),
            'source_name':source_name,'content_type':kind,
            'editorial_angle':angle,'editorial_hook':hook,
            'editorial_score':topic.get('editorial_score'),
            'editorial_decision':topic.get('editorial_decision','PRODUZIR'),
            'editorial_reason':topic.get('editorial_reason','')}

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
    # Branding is added only in the final timeline, as a watermark.
    im.save(dst,quality=84,optimize=True)
    im.close()


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
        ff=str(__import__('imageio_ffmpeg').get_ffmpeg_exe())
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
    """Editorial Shorts caption + discreet GTA OCULTO watermark.
    The watermark is branding, never a headline. Captions stay short and content-led.
    """
    im=Image.new('RGBA',(W,H),(0,0,0,0)); d=ImageDraw.Draw(im)

    # --- GTA OCULTO watermark: small, fixed, low-opacity, bottom-right ---
    wm=font(11,True)
    wm_text='GTA OCULTO'
    wb=d.textbbox((0,0),wm_text,font=wm)
    wx=W-(wb[2]-wb[0])-12; wy=H-(wb[3]-wb[1])-13
    d.rounded_rectangle((wx-7,wy-4,wx+(wb[2]-wb[0])+7,wy+(wb[3]-wb[1])+4),radius=6,fill=(0,0,0,75))
    d.text((wx,wy),wm_text,font=wm,fill=(255,255,255,105))

    f=font(24,True)
    text=re.sub(r'\s+',' ',str(caption)).strip().upper()
    words=text.split()
    lines=[]; cur=''
    for w in words:
        test=(cur+' '+w).strip()
        if d.textbbox((0,0),test,font=f,stroke_width=1)[2] <= W-40:
            cur=test
        else:
            if cur: lines.append(cur)
            cur=w
    if cur: lines.append(cur)
    lines=lines[:2]
    if not lines:
        im.save(path); return

    # Caption sits above the lower safe area and watermark, with a cleaner pill.
    line_h=30
    box_h=22+len(lines)*line_h
    y=H-box_h-45
    d.rounded_rectangle((18,y,W-18,H-45),radius=13,fill=(3,5,9,210),outline=(255,255,255,70),width=1)
    yy=y+8
    hi=(str(highlight or '').upper()).strip()
    for line in lines:
        parts=line.split()
        if hi and hi in parts:
            widths=[d.textlength(w,font=f) for w in parts]
            spaces=d.textlength(' ',font=f)
            totalw=sum(widths)+spaces*(len(parts)-1)
            x=(W-totalw)/2
            for w,ww in zip(parts,widths):
                fill=(255,52,68,255) if w==hi else (255,255,255,255)
                d.text((x,yy),w,font=f,fill=fill,stroke_width=1,stroke_fill=(0,0,0,220))
                x += ww+spaces
        else:
            bb=d.textbbox((0,0),line,font=f,stroke_width=1)
            x=(W-(bb[2]-bb[0]))/2
            d.text((x,yy),line,font=f,fill='white',stroke_width=1,stroke_fill=(0,0,0,220))
        yy += line_h
    im.save(path)

def _clean_caption_phrase(text):
    text=re.sub(r"\s+", " ", str(text)).strip(" .!?,:;-")
    text=re.sub(r"^(?:gta\s*6\s*[:\-]\s*)", "", text, flags=re.I)
    return text.upper()


def _caption_phrases_from_sentence(sentence, max_words=7):
    """Keep contiguous natural phrases; never rebuild a caption from random keywords."""
    s=re.sub(r"\s+", " ", sentence).strip(" .!?\n")
    if not s:
        return []
    # Prefer clauses that already sound natural when spoken.
    clauses=[c.strip(" ,:;-\")('") for c in re.split(r"\s*(?:[:;]|,\s+(?:mas|e|porque|então|entao|porém|porem|só que|e isso|o que))\s*", s, flags=re.I) if c.strip()]
    if len(clauses)==1:
        clauses=[c.strip() for c in re.split(r"\s+(?:e|mas|porque|quando|se|que)\s+", s, maxsplit=1, flags=re.I) if c.strip()]
    out=[]
    for clause in clauses:
        words=clause.split()
        if len(words)<=max_words:
            out.append(_clean_caption_phrase(clause))
        else:
            # Split at a natural midpoint, preserving the original word order.
            mid=len(words)//2
            left=' '.join(words[:mid]); right=' '.join(words[mid:])
            if len(left.split())>=3: out.append(_clean_caption_phrase(left))
            if len(right.split())>=2: out.append(_clean_caption_phrase(right))
    return [x for x in out if 2<=len(x.split())<=max_words]


def build_short_timeline(script, topic, duration, count=10):
    """Create cinematic editorial captions from complete phrases in the narration.
    V25.6 deliberately avoids the old keyword-scrambling behavior. Captions are
    derived from contiguous spoken phrases, then shortened only at natural
    punctuation/conjunction boundaries.
    """
    narration=str(script.get('narration','')).strip()
    title=str(topic.get('title','GTA 6')).strip()
    kind=script.get('content_type','CURIOSIDADE')
    if not narration:
        return [{'text':'GTA 6','duration':duration,'highlight':'GTA'}]

    hooks={
        'RUMOR':'⚠️ ISSO AINDA NÃO FOI CONFIRMADO',
        'MISTÉRIO':'👁️ ESSE DETALHE PODE SER IMPORTANTE',
        'NOTÍCIA':'🚨 A ROCKSTAR REVELOU ISSO',
        'CURIOSIDADE':'😳 VOCÊ PERCEBEU ESSE DETALHE?'
    }
    endings={
        'RUMOR':'RUMOR OU PISTA REAL?',
        'MISTÉRIO':'E SE ISSO NÃO FOR COINCIDÊNCIA?',
        'NOTÍCIA':'O QUE ISSO MUDA NO GTA 6?',
        'CURIOSIDADE':'VOCÊ JÁ TINHA PERCEBIDO?'
    }

    beats=[{'text':hooks.get(kind,hooks['CURIOSIDADE']),'highlight':None}]

    # The title becomes a factual second beat, preserving its natural wording.
    title_clean=_clean_caption_phrase(title)
    if title_clean:
        if len(title_clean.split())>7:
            tw=title_clean.split()
            # Keep the most informative half without reordering words.
            title_clean=' '.join(tw[:7])
        beats.append({'text':title_clean,'highlight':None})

    # Spoken sentences -> natural short phrases.
    sentences=[s.strip() for s in re.split(r'(?<=[.!?])\s+', narration) if len(s.strip())>8]
    for sent in sentences:
        for phrase in _caption_phrases_from_sentence(sent,7):
            if phrase in {b['text'] for b in beats}:
                continue
            # Avoid captions that are just a weak connector.
            if len(re.findall(r"[A-ZÀ-Ý0-9]+",phrase))<2:
                continue
            words=phrase.split()
            # Highlight an important proper noun / GTA term, otherwise the final strong word.
            preferred=[w for w in words if w.lower().strip('.,!?') in {
                'gta','gta6','vi','rockstar','jason','lucia','leonida','vice','city','mapa','história','historia','detalhe','confirmado','confirmou','rumor','teoria'
            }]
            highlight=(preferred[0] if preferred else (words[-1] if len(words)>2 else None))
            beats.append({'text':phrase,'highlight':highlight})
            if len(beats)>=count-1:
                break
        if len(beats)>=count-1:
            break

    beats.append({'text':endings.get(kind,endings['CURIOSIDADE']),'highlight':None})

    # Deduplicate while preserving narrative order.
    unique=[]; seen=set()
    for b in beats:
        t=b['text']
        if t and t not in seen:
            seen.add(t); unique.append(b)
    beats=unique[:count]

    # If the story is short, add one or two contiguous sentence phrases—not keyword piles.
    if len(beats)<5:
        for sent in sentences:
            phrase=_clean_caption_phrase(sent)
            if 2<=len(phrase.split())<=9 and phrase not in seen:
                beats.insert(-1,{'text':phrase,'highlight':None}); seen.add(phrase)
            if len(beats)>=min(count,6): break

    beats=beats[:count]
    weights=[max(2,len(re.findall(r"\w+",b['text']))) for b in beats]
    durations=[duration*w/sum(weights) for w in weights]
    for _ in range(5):
        durations=[max(1.65,min(4.0,d)) for d in durations]
        scale=duration/sum(durations)
        durations=[d*scale for d in durations]
    for b,d in zip(beats,durations):
        b['duration']=d
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

def _choose_timeline_assets(video_clips, image_paths, beats, topic_title):
    """Assign unique assets where possible and avoid repetitive adjacent shots."""
    pool=[]
    for p in video_clips: pool.append(('video',p))
    for p in image_paths: pool.append(('image',p))
    chosen=[]; used=set()
    for bi,beat in enumerate(beats):
        ranked=[]
        for idx,(kind,p) in enumerate(pool):
            if idx in used:
                continue
            s=_asset_relevance(p,topic_title,beat['text'],kind)
            # Prefer video on hook and then alternate motion/still where possible.
            if bi==0 and kind=='video': s+=25
            if chosen and chosen[-1][1]==p: s-=100
            if bi%2==0 and kind=='video': s+=5
            ranked.append((s,kind,p,idx))
        if not ranked:
            # Reuse the least-recent asset only when unique assets are exhausted.
            ranked=[(_asset_relevance(p,topic_title,beat['text'],kind),kind,p,idx) for idx,(kind,p) in enumerate(pool)]
        ranked.sort(key=lambda x:x[0],reverse=True)
        _,kind,p,idx=ranked[0]
        chosen.append((kind,p))
        used.add(idx)
    return chosen

def make_multimedia_video(video_clips, image_paths, audio, out, duration, captions, script=None, topic_title='GTA 6'):
    # FFmpeg/yuv420p requires even width/height. Keep the Render Free
    # intermediate at an even 320x568 and upscale only at the final render.
    INTER_W, INTER_H = 320, 568
    if INTER_W % 2 or INTER_H % 2:
        raise RuntimeError(f'Dimensões intermediárias inválidas: {INTER_W}x{INTER_H}.')
    """V25 editor: narration-driven timeline, 12 short beats, real clips + images.
    Still optimized for Render Free by encoding one scene at a time.
    """
    ff=str(__import__('imageio_ffmpeg').get_ffmpeg_exe())
    work=out.parent/'timeline'; work.mkdir(exist_ok=True)
    if len(video_clips)<3:
        raise RuntimeError('A edição precisa de pelo menos 3 vídeos reais.')
    if script is None:
        script={'narration':' '.join(captions)}
    beats=build_short_timeline(script, {'title':topic_title}, duration, count=10)
    # Use up to six images so the timeline can reach 10-12 cuts without repeating shots.
    imgs=list(image_paths)[:5]
    assets=_choose_timeline_assets(video_clips,imgs,beats,topic_title)
    # Keep the exact audio length by adjusting the final beat.
    diff=duration-sum(b['duration'] for b in beats)
    beats[-1]['duration']=max(1.0,beats[-1]['duration']+diff)
    scene_files=[]
    for i,(beat,(kind,src)) in enumerate(zip(beats,assets)):
        scene=work/f'scene_{i:02d}.mp4'; overlay=work/f'overlay_{i:02d}.png'
        _caption_overlay(overlay,beat['text'],i,len(beats),320,568,beat.get('highlight'))
        if kind=='video':
            vf='scale=320:568:force_original_aspect_ratio=increase,crop=320:568,setsar=1,fps=15'
            inp=['-stream_loop','-1','-i',str(src)]
        else:
            vf="scale=320:568:force_original_aspect_ratio=increase,crop=320:568,setsar=1,zoompan=z='min(zoom+0.002,1.04)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s=320x568:fps=15"
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
    ff=str(__import__('imageio_ffmpeg').get_ffmpeg_exe())
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
        update_job(jid,stage='ROTEIRO',progress=28,log='EDITOR-CHEFE → ROTEIRISTA V28: criando hook, contexto, verificação, payoff e CTA...'); script=make_script(topic)
        jobdir=WORK/jid; jobdir.mkdir(parents=True,exist_ok=True)
        update_job(jid,script=script,stage='VISUAIS',progress=40,log='Baixando visuais oficiais e montando cenas verticais...')
        paths=download_visuals(urls,jobdir/'visuals',topic['title'])
        caps=build_dynamic_captions(script, topic, 10)
        image_order=select_visuals(paths,topic['title'],6)
        image_scenes=[]
        for i,src in enumerate(image_order):
            dst=jobdir/f'image_{i}.jpg'; prepare_scene(src,dst,caps[min(i,len(caps)-1)],i,10); image_scenes.append(dst)
        update_job(jid,stage='NARRAÇÃO',progress=60,log='Gerando narração PT-BR...'); audio=jobdir/'narracao.mp3'; asyncio.run(make_tts(script['narration'],audio)); duration=duration_of_audio(audio)
        update_job(jid,stage='EDIÇÃO',progress=74,log=f'Obtendo vídeos oficiais da Rockstar e montando timeline com movimento real / {duration:.1f}s...')
        official_videos=download_official_video_clips(jobdir/'official_videos', jid)
        selected_videos=select_video_clips(official_videos,topic['title'],6)
        update_job(jid,log=f'{len(selected_videos)} vídeos oficiais disponíveis. Editando cortes reais em 9:16 / {duration:.1f}s...')
        video=jobdir/'GTA_OCULTO_SHORT.mp4'; make_multimedia_video(selected_videos,image_scenes,audio,video,duration,caps,script,topic['title'])
        # Nunca deixe a capa derrubar uma produção já renderizada.
        if not image_scenes:
            fallback_cover=jobdir/'cover_fallback.jpg'
            make_fallback(fallback_cover,0,topic['title'])
            image_scenes=[fallback_cover]
        cover=jobdir/'CAPA.jpg'; make_cover(image_scenes[0],topic['title'],cover)
        update_job(jid,stage='AVALIAÇÃO',progress=92,log='Avaliando hook, ritmo, visuais, duração, formato e legendas...'); visual_quality=100
        for sp in image_scenes:
            q=_image_quality(sp); visual_quality=min(visual_quality, max(0,q))
        beats=build_short_timeline(script,topic,duration,10)
        score=evaluate(script,duration,len(beats),visual_quality,beats,len(selected_videos),len(image_scenes))
        meta={'title':topic['title'].upper()+' 👀','description':script['narration']+'\n\n🔎 GTA Oculto — onde os segredos vêm à tona.','hashtags':['#GTA6','#GTAVI','#GTAOculto','#RockstarGames','#GTA'],'tags':['GTA 6','GTA VI','GTA 6 Brasil','GTA 6 teorias','GTA 6 segredos','Rockstar Games','GTA Oculto'],'score':score}
        (jobdir/'metadata.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
        update_job(jid,status='DONE',stage='PRONTO',progress=100,log=f'PRONTO — Short gerado e avaliado em {score}/100.',video=f'{jid}/GTA_OCULTO_SHORT.mp4',cover=f'{jid}/CAPA.jpg',score=score,metadata=meta)
    except Exception as e:
        import traceback
        tb=traceback.format_exc()
        update_job(jid,status='ERROR',stage='ERRO',progress=100,log='ERRO: '+str(e)+'\n'+tb[-3200:])
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
def health(): return jsonify(ok=True,app='GTA Oculto AI',version='V28-ROTEIRO-AUTOMATICO',processor='cloud')
@APP.get('/api/state')
def state():
    with LOCK:
        js=list(load_jobs().values())[-30:]
    topics,updated,radar_status,radar_error,sources_ok=current_opportunities()
    editor_pick=editor_chief_select(topics) if topics else None
    if editor_pick:
        try:
            editor_pick['script_preview']=make_script(editor_pick)
        except Exception as e:
            editor_pick['script_preview']={'error':str(e)}
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

threading.Thread(target=processor_loop,daemon=True).start()
threading.Thread(target=radar_loop,daemon=True).start()
if __name__=='__main__': APP.run(host='0.0.0.0',port=int(os.environ.get('PORT',5000)))

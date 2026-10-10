"""GTA OCULTO AI V42 - bounded editorial/technical auditor.
No external AI/API is required. It uses deterministic checks and bounded repair strategies.
"""
from __future__ import annotations
import json, re, subprocess, shutil
from pathlib import Path

STOP = {'a','o','e','de','do','da','em','no','na','os','as','um','uma','que','isso','para','com','por','mais','mas','como','esse','essa','se','é','ser','já','ou','dos','das','ao','à','às'}
BAD = {'radar','score','confiança','editor-chefe','fontes','matérias','pesquisa editorial','sistema','metadados'}


def _words(s):
    return re.findall(r"[A-Za-zÀ-ÿ0-9']+", str(s or ''))


def _norm(s):
    return re.sub(r'\s+', ' ', str(s or '')).strip()


def caption_audit(captions, narration=''):
    caps=[_norm(c) for c in captions if _norm(c)]
    issues=[]; score=100
    seen=set()
    for c in caps:
        u=c.upper()
        if u in seen:
            score-=5; issues.append('caption_repeated')
        seen.add(u)
        n=len(_words(c))
        if n < 3:
            score-=4; issues.append('caption_too_short')
        if n > 8:
            score-=5; issues.append('caption_too_long')
        if len(c) > 38:
            score-=4; issues.append('caption_too_wide')
        if any(b in u.lower() for b in BAD):
            score-=15; issues.append('internal_metadata')
        if c.endswith((' DE',' DA',' DO',' PARA',' COM',' E',' OU',' QUE',' A',' O')):
            score-=7; issues.append('dangling_function_word')
    if narration:
        nwords=set(w.lower() for w in _words(narration) if len(w)>3)
        if caps:
            overlap=sum(1 for c in caps if any(w.lower() in nwords for w in _words(c)))
            if overlap < max(2, len(caps)//3):
                score-=10; issues.append('low_narration_alignment')
    return {'score':max(0,min(100,score)), 'issues':sorted(set(issues)), 'count':len(caps)}


def repair_captions(captions, narration='', target=9):
    """Bounded repair: rebuild captions strictly from contiguous narration words."""
    words=_words(narration or '')
    if not words:
        return []
    # Aim for compact 4-6 word blocks. Every emitted word must exist in the
    # original narration and remain contiguous, so the alignment gate can
    # never be weakened by the repair itself.
    target=max(6,min(10,int(target or 9)))
    chunks=[]
    i=0
    while i < len(words):
        remaining=len(words)-i
        slots=max(1,target-len(chunks))
        size=max(4,min(6,round(remaining/slots)))
        end=min(len(words),i+size)
        while end < len(words) and words[end-1].lower() in STOP and end < len(words):
            end += 1
        chunk=' '.join(words[i:end]).upper()
        if 3 <= len(_words(chunk)) <= 8 and len(chunk) <= 38:
            chunks.append(chunk)
        i=end
    # If the first pass produced too many chunks, merge adjacent chunks only
    # when the merged caption still fits the strict width/word limits.
    while len(chunks)>target:
        best=None
        for k in range(len(chunks)-1):
            merged=f"{chunks[k]} {chunks[k+1]}"
            if len(_words(merged))<=8 and len(merged)<=38:
                best=(k,merged); break
        if not best:
            break
        k,merged=best
        chunks=chunks[:k]+[merged]+chunks[k+2:]
    return chunks[:target]



def hook_audit(narration=''):
    """Score the opening of a Short for immediate curiosity and clarity."""
    text=_norm(narration)
    if not text: return {'score':0,'issues':['hook_missing']}
    first=re.split(r'(?<=[.!?])\\s+',text,maxsplit=1)[0].strip()
    words=_words(first)
    score=100; issues=[]
    if len(words)<5:
        score-=20; issues.append('hook_too_short')
    if len(words)>24:
        score-=18; issues.append('hook_too_long')
    lower=first.lower()
    curiosity=('?' in first or any(x in lower for x in ('segredo','detalhe','ninguém','pode mudar','descobriu','revelou','por que','como','confirmou','escondido')))
    if not curiosity:
        score-=18; issues.append('hook_low_curiosity')
    if any(x in lower for x in ('radar','editor-chefe','score','confiança','fontes','pesquisa editorial')):
        score-=30; issues.append('hook_internal_metadata')
    return {'score':max(0,min(100,score)),'issues':sorted(set(issues)),'text':first}

def technical_video_audit(video_path):
    p=Path(video_path)
    if not p.exists(): return {'score':0,'issues':['video_missing']}
    try:
        ffprobe=shutil.which('ffprobe')
        if not ffprobe:
            # Some imageio-ffmpeg versions no longer expose get_ffprobe_exe.
            # Render normally provides ffprobe system-wide; if unavailable,
            # report a bounded diagnostic instead of crashing the audit.
            return {'score':70,'issues':['ffprobe_unavailable'], 'error':'ffprobe executable not found'}
        cmd=[ffprobe,'-v','error','-show_streams','-show_format','-of','json',str(p)]
        data=json.loads(subprocess.check_output(cmd,stderr=subprocess.STDOUT,text=True,timeout=20))
        streams=data.get('streams',[]); vs=next((s for s in streams if s.get('codec_type')=='video'),None); aud=next((s for s in streams if s.get('codec_type')=='audio'),None)
        score=100; issues=[]
        if not vs: score-=50; issues.append('no_video')
        else:
            w=int(vs.get('width') or 0); h=int(vs.get('height') or 0)
            if h <= w: score-=20; issues.append('not_vertical')
            if w < 480 or h < 800: score-=5; issues.append('low_resolution')
            dur=float(data.get('format',{}).get('duration') or 0)
            if dur < 15 or dur > 60: score-=8; issues.append('duration_outlier')
        if not aud: score-=15; issues.append('no_audio')
        return {'score':max(0,min(100,score)),'issues':issues,'video':vs,'audio':aud,'duration':float(data.get('format',{}).get('duration') or 0)}
    except Exception as e:
        return {'score':70,'issues':['ffprobe_failed'], 'error':str(e)}


def full_audit(video_path, captions, narration=''):
    ca=caption_audit(captions,narration); ha=hook_audit(narration); va=technical_video_audit(video_path)
    score=round(ca['score']*0.40 + ha['score']*0.20 + va['score']*0.40)
    return {'score':score,'caption':ca,'hook':ha,'technical':va,'ok':score>=78}

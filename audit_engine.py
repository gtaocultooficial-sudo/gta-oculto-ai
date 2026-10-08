"""GTA OCULTO AI V42 - bounded editorial/technical auditor.
No external AI/API is required. It uses deterministic checks and bounded repair strategies.
"""
from __future__ import annotations
import json, re, subprocess
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
    """Bounded repair: keeps editorial opener/ending but replaces mechanically broken chunks."""
    raw=[_norm(c) for c in captions if _norm(c)]
    # Preserve obvious editorial opener/ending while rebuilding middle captions from complete sentences.
    opener = raw[0] if raw else ''
    ending = raw[-1] if raw else ''
    sentences=[_norm(x) for x in re.split(r'[.!?]+', str(narration or '')) if len(_words(x))>=4]
    mids=[]
    for sent in sentences:
        ws=_words(sent)
        # Build phrase chunks on semantic boundaries, 4-7 words, never ending on a connector.
        i=0
        while i < len(ws):
            end=min(len(ws), i+6)
            # Extend/trim so the chunk doesn't end in a weak connector.
            while end < len(ws) and ws[end-1].lower() in STOP:
                end += 1
            chunk=' '.join(ws[i:end]).upper()
            if 3 <= len(_words(chunk)) <= 8 and len(chunk) <= 38:
                mids.append(chunk)
            i=end
    # Deduplicate and remove internal/system phrases.
    out=[]; seen=set()
    for c in [opener]+mids+[ending]:
        c=_norm(c)
        if not c: continue
        if any(x in c.lower() for x in BAD): continue
        if c.upper() in seen: continue
        seen.add(c.upper()); out.append(c)
    if len(out)<target:
        # Prefer original good captions as a last resort, never inventing facts.
        for c in raw:
            if c.upper() not in seen and 3 <= len(_words(c)) <= 8 and len(c)<=38:
                seen.add(c.upper()); out.append(c)
            if len(out)>=target: break
    return out[:target]


def technical_video_audit(video_path):
    p=Path(video_path)
    if not p.exists(): return {'score':0,'issues':['video_missing']}
    try:
        from imageio_ffmpeg import get_ffprobe_exe
        ffprobe=get_ffprobe_exe()
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
    ca=caption_audit(captions,narration); va=technical_video_audit(video_path)
    score=round(ca['score']*0.45 + va['score']*0.55)
    return {'score':score,'caption':ca,'technical':va,'ok':score>=78}

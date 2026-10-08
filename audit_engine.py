import json, re, subprocess, shutil
from pathlib import Path

class AuditEngine:
    def _ffprobe(self, path):
        ffprobe=shutil.which('ffprobe')
        if not ffprobe: return {'ok':False,'error':'ffprobe_unavailable'}
        p=subprocess.run([ffprobe,'-v','error','-show_entries','format=duration:stream=codec_type,width,height,r_frame_rate,codec_name','-of','json',str(path)],capture_output=True,text=True,timeout=30)
        if p.returncode: return {'ok':False,'error':p.stderr[-1000:]}
        try: return {'ok':True,**json.loads(p.stdout)}
        except Exception as e: return {'ok':False,'error':str(e)}

    def audit_video(self, video, script=None, captions=None):
        video=Path(video); checks={}; score=100
        if not video.exists(): return {'ok':False,'score':0,'issues':['video_missing'],'checks':{}}
        meta=self._ffprobe(video); checks['ffprobe']=meta
        if not meta.get('ok'): score-=35; issues=['ffprobe_failed']
        else:
            issues=[]; streams=meta.get('streams',[]); vs=[x for x in streams if x.get('codec_type')=='video']; aud=[x for x in streams if x.get('codec_type')=='audio']
            fmt=meta.get('format',{}); dur=float(fmt.get('duration') or 0)
            if not vs: issues.append('no_video'); score-=40
            else:
                w,h=vs[0].get('width'),vs[0].get('height')
                if not (h and w and h>w): issues.append('not_vertical'); score-=20
                if w and w<480: issues.append('low_width'); score-=8
                fps=vs[0].get('r_frame_rate','0/1')
                try: fpsv=eval(fps,{'__builtins__':{}},{})
                except Exception: fpsv=0
                if fpsv<15: issues.append('low_fps'); score-=6
            if not aud: issues.append('no_audio'); score-=25
            if dur<15 or dur>60: issues.append('duration_outlier'); score-=8
        if script:
            text=str(script.get('narration','')).strip()
            if len(text)<180: issues.append('short_narration'); score-=8
            if len(re.findall(r'\b(Radar|Editor-Chefe|score|confidence|fontes|sistema interno)\b',text,re.I))>=1:
                issues.append('internal_metadata_in_narration'); score-=18
            if re.search(r'\b(segunda|terça|quarta|quinta|sexta|sábado|domingo)-feira\b',text,re.I):
                issues.append('possible_metadata_date_fragment'); score-=4
        if captions:
            bad=0
            for c in captions:
                t=str(c.get('text','') if isinstance(c,dict) else c).strip()
                if len(t.split())<=1: bad+=1
                if re.search(r'^(6|5|4|3|2|1)[:\-]\s*',t): bad+=1
                if re.search(r'\b(IGN Brasil|Adrenaline|Tecnoblog|Terra|Rockstar Games)\b',t,re.I): bad+=1
            if bad: issues.append(f'caption_fragments_or_source_names:{bad}'); score-=min(20,bad*4)
        score=max(0,min(100,score))
        return {'ok':score>=78,'score':score,'issues':issues,'checks':checks}

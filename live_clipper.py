import json, math, os, re, shutil, subprocess, time, uuid
from pathlib import Path

class LiveClipper:
    """Free-first live clipping engine.

    Works in bounded chunks so long recordings do not need to be loaded into RAM.
    It can use local files or HTTP media URLs. If faster-whisper is installed it
    can enrich scoring with transcript/emotion cues; otherwise it falls back to
    FFmpeg audio/silence signals.
    """
    def __init__(self, workspace):
        self.root = Path(workspace)
        self.root.mkdir(parents=True, exist_ok=True)
        self.live_root = self.root / "live_clips"
        self.live_root.mkdir(parents=True, exist_ok=True)

    def _ffmpeg(self):
        p = shutil.which("ffmpeg")
        if p: return p
        try:
            import imageio_ffmpeg
            return imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            raise RuntimeError("FFmpeg não encontrado.")

    def _ffprobe(self):
        p = shutil.which("ffprobe")
        if p: return p
        raise RuntimeError("ffprobe não encontrado.")

    def _run(self, cmd, timeout=180):
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           text=True, timeout=timeout)
        if p.returncode:
            raise RuntimeError((p.stderr or "FFmpeg error")[-2500:])
        return p.stdout

    def probe(self, source):
        out = self._run([self._ffprobe(), "-v", "error", "-show_entries",
                         "format=duration,size", "-of", "json", str(source)], 60)
        data = json.loads(out).get("format", {})
        streams=data.get("streams") or []
        video=next((s for s in streams if s.get("codec_type")=="video"), {})
        fps=video.get("r_frame_rate") or "30/1"
        try:
            num,den=[float(x) for x in str(fps).split("/",1)]
            fps_value=max(1,min(60,num/den if den else 30))
        except Exception:
            fps_value=30.0
        return {"duration": float(data.get("duration", 0) or 0),
                "size": int(data.get("size", 0) or 0),
                "width": int(video.get("width",0) or 0),
                "height": int(video.get("height",0) or 0),
                "fps": fps_value}

    def _silence_map(self, source, duration):
        # Low-cost signal scan. Audio is downmixed to mono and sampled at 8 kHz.
        # The scan is bounded and does not retain the media in Python memory.
        out = self._run([self._ffmpeg(), "-hide_banner", "-i", str(source),
                         "-vn", "-af", "silencedetect=noise=-32dB:d=0.35",
                         "-f", "null", "-"], timeout=max(180, int(duration/2)+120))
        starts=[]; ends=[]
        for line in out.splitlines():
            m=re.search(r"silence_start:\s*([0-9.]+)", line)
            if m: starts.append(float(m.group(1)))
            m=re.search(r"silence_end:\s*([0-9.]+)", line)
            if m: ends.append(float(m.group(1)))
        return starts, ends

    def _candidate_windows(self, duration, starts, ends, max_candidates=60):
        # For long lives, first create coarse 15-min windows and then prefer
        # positions immediately before/after meaningful silence boundaries.
        candidates=[]
        for i, start in enumerate(range(0, max(1, int(duration)), 900)):
            end=min(duration, start+900)
            center=(start+end)/2
            candidates.append((center, start, end, "chunk"))
        for s in starts + ends:
            if 8 < s < duration-8:
                candidates.append((s, max(0,s-28), min(duration,s+20), "boundary"))
        # Deduplicate by 5-second buckets.
        uniq={}
        for center,a,b,kind in candidates:
            key=round(center/5)
            old=uniq.get(key)
            if old is None or kind=="boundary":
                uniq[key]=(center,a,b,kind)
        return list(uniq.values())[:max_candidates]

    def _transcript_score(self, source, start, duration):
        try:
            from faster_whisper import WhisperModel
        except Exception:
            return 0, ""
        try:
            model=WhisperModel(os.getenv("WHISPER_MODEL","tiny"), device="cpu", compute_type="int8")
            wav=self.live_root/"_semantic_probe.wav"
            self._run([self._ffmpeg(),"-hide_banner","-y","-ss",str(start),"-t",str(duration),"-i",str(source),"-vn","-ac","1","-ar","16000","-c:a","pcm_s16le",str(wav)],90)
            segments,_=model.transcribe(str(wav),language="pt",beam_size=1,vad_filter=True)
            text=" ".join((s.text or "").strip() for s in segments).strip()
            low=text.lower()
            hooks=("mano","caralho","olha","corre","polícia","policia","viatura","prisão","preso","tiro","foge","fugiu","perseguição","perseguicao","kkkk","hahaha","não acredito","nao acredito","meu deus","agora")
            hits=sum(1 for h in hooks if h in low)
            exclam=text.count("!")+text.count("?")
            score=min(30,hits*4+min(10,exclam*2))
            try: wav.unlink()
            except Exception: pass
            return score,text[:500]
        except Exception:
            return 0, ""
    def _score_window(self, source, a, b, kind):
        # Detect speech/activity level without decoding the full source.
        # astats gives mean volume; silences give contextual boundaries.
        mid=(a+b)/2
        length=min(48.0, max(18.0,b-a))
        start=max(0.0,mid-length/2)
        try:
            out=self._run([self._ffmpeg(), "-hide_banner", "-ss", str(start),
                           "-t", str(length), "-i", str(source), "-vn",
                           "-af", "volumedetect", "-f", "null", "-"], 90)
            m=re.search(r"mean_volume:\s*(-?[0-9.]+) dB", out)
            peak=re.search(r"max_volume:\s*(-?[0-9.]+) dB", out)
            mean=float(m.group(1)) if m else -35
            pk=float(peak.group(1)) if peak else -12
        except Exception:
            mean,pk=-30,-12
        activity=max(0,min(100,(mean+45)*2.2))
        peak_score=max(0,min(20,(pk+30)*0.7))
        boundary_bonus=12 if kind=="boundary" else 0
        duration_bonus=8 if 24<=length<=48 else 0
        reaction_bonus=10 if pk > -8 and mean > -24 else (5 if pk > -12 and mean > -28 else 0)
        semantic_score, _ = self._transcript_score(source,start,length)
        score=max(0,min(100,round(activity+peak_score+boundary_bonus+duration_bonus+reaction_bonus+semantic_score)))
        return score

    def analyze(self, source, max_clips=10, job_id=None):
        info=self.probe(source)
        duration=info["duration"]
        if duration < 20:
            raise RuntimeError("A live precisa ter pelo menos 20 segundos.")
        # Chunk-based: a 3h live is scanned as one stream, but candidate rendering
        # is always bounded to short windows.
        starts,ends=self._silence_map(source,duration)
        windows=self._candidate_windows(duration,starts,ends,max(40,max_clips*6))
        scored=[]
        for center,a,b,kind in windows:
            score=self._score_window(source,a,b,kind)
            scored.append({
                "start":round(max(0,a),2),"end":round(min(duration,b),2),
                "duration":round(min(48,b-a),2),"score":score,
                "kind":kind,"center":round(center,2)
            })
        scored.sort(key=lambda x:x["score"],reverse=True)
        # Non-maximum suppression: do not return five cuts from the same event.
        selected=[]
        for c in scored:
            if all(abs(c["center"]-x["center"])>=65 for x in selected):
                selected.append(c)
            if len(selected)>=max_clips: break
        selected=sorted(selected,key=lambda x:x["start"])
        return {"ok":True,"duration":duration,"size":info["size"],
                "candidate_count":len(scored),"clips":selected,
                "engine":"V1-LIVE-BLOCKS+REACTION-SCORE+SEMANTIC-OPTIONAL","transcript":"optional"}

    def render_clip(self, source, clip, outdir, index=1):
        outdir=Path(outdir); outdir.mkdir(parents=True,exist_ok=True)
        target=outdir/f"LIVE_CORTE_{index:02d}.mp4"
        start=float(clip["start"]); duration=float(clip["duration"])
        # Quality Engine V59:
        # preserve source FPS, avoid destructive center crops on landscape GTA,
        # keep the full gameplay frame over a blurred vertical background,
        # and encode a cleaner master with CRF 18.
        info=self.probe(source)
        src_fps=max(24.0,min(60.0,float(info.get("fps",30) or 30)))
        fps_arg=f"{src_fps:.3f}".rstrip("0").rstrip(".")
        w=int(info.get("width",0) or 0); h=int(info.get("height",0) or 0)
        if h and w and h>w:
            vf=("scale=1080:1920:force_original_aspect_ratio=decrease,"
                "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black,setsar=1")
        else:
            vf=("split=2[fg][bg];"
                "[bg]scale=1080:1920:force_original_aspect_ratio=increase,"
                "crop=1080:1920,gblur=sigma=28,"
                "eq=brightness=-0.10:saturation=0.85[bg2];"
                "[fg]scale=1080:1920:force_original_aspect_ratio=decrease,"
                "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=black@0[fg2];"
                "[bg2][fg2]overlay=(W-w)/2:(H-h)/2,setsar=1")
        self._run([self._ffmpeg(),"-hide_banner","-y","-ss",str(start),"-i",
                   str(source),"-t",str(duration),"-vf",vf,"-r",fps_arg,
                   "-c:v","libx264","-preset","medium","-crf","18",
                   "-pix_fmt","yuv420p","-c:a","aac","-b:a","160k",
                   "-movflags","+faststart",str(target)],timeout=420)
        return target

    def status(self):
        return {"enabled":True,"engine":"V1-LIVE-BLOCKS+REACTION-SCORE",
                "chunk_seconds":900,"max_clip_seconds":48,
                "memory_safe":True,"vertical_master":"1080x1920","quality":"CRF18","audio":"AAC160k"}

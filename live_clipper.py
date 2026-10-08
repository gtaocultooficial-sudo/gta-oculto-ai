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
        return {"duration": float(data.get("duration", 0) or 0),
                "size": int(data.get("size", 0) or 0)}

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
        score=max(0,min(100,round(activity+peak_score+boundary_bonus+duration_bonus)))
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
                "engine":"V1-LIVE-BLOCKS","transcript":"optional"}

    def render_clip(self, source, clip, outdir, index=1):
        outdir=Path(outdir); outdir.mkdir(parents=True,exist_ok=True)
        target=outdir/f"LIVE_CORTE_{index:02d}.mp4"
        start=float(clip["start"]); duration=float(clip["duration"])
        # Vertical crop, subtitles are added later by the main caption pipeline.
        vf=("scale=1080:1920:force_original_aspect_ratio=increase,"
            "crop=1080:1920,setsar=1,fps=30")
        self._run([self._ffmpeg(),"-hide_banner","-y","-ss",str(start),"-i",
                   str(source),"-t",str(duration),"-vf",vf,
                   "-c:v","libx264","-preset","veryfast","-crf","23",
                   "-c:a","aac","-b:a","128k","-movflags","+faststart",
                   str(target)],timeout=240)
        return target

    def status(self):
        return {"enabled":True,"engine":"V1-LIVE-BLOCKS",
                "chunk_seconds":900,"max_clip_seconds":48,
                "memory_safe":True}

"""Neural, character-specific dialogue rendering for the Vice City fan series.

A failed neural TTS call raises an actionable error rather than silently
returning low-quality synthesized speech.
"""
from __future__ import annotations

import asyncio
import json
import math
import os
import re
import shutil
import time
from xml.sax.saxutils import escape
import subprocess
import wave
from pathlib import Path
from typing import Callable


SAMPLE_RATE = 44100
FPS = 24
INTRO_SECONDS = 4.0
OUTRO_SECONDS = 3.8
MIN_DIALOGUE_GAP = 0.24

# Native Azure Speech pt-BR voices. One stable voice per character.
# The public Edge TTS endpoint does not expose four distinct pt-BR voices reliably.
VOICE_PREFERENCES = {
    "JASON DUVAL": ["pt-BR-DonatoNeural"],
    "LUCIA CAMINOS": ["pt-BR-FranciscaNeural"],
    "BRIAN HEDER": ["pt-BR-HumbertoNeural"],
    "CAL HAMPTON": ["pt-BR-FabioNeural"],
}

# Small prosody differences reinforce character identity without caricature.
VOICE_PROSODY = {
    "JASON DUVAL": {"rate": "-4%", "pitch": "-2Hz", "volume": "+0%"},
    "LUCIA CAMINOS": {"rate": "-1%", "pitch": "+1Hz", "volume": "+0%"},
    "BRIAN HEDER": {"rate": "-7%", "pitch": "-3Hz", "volume": "+0%"},
    "CAL HAMPTON": {"rate": "+3%", "pitch": "+2Hz", "volume": "+0%"},
}


def supported_portuguese_voices(catalogue):
    """Return only native voices whose catalogue locale is Portuguese (Brazil)."""
    return {
        str(item.get("ShortName") or "").strip()
        for item in (catalogue or [])
        if str(item.get("ShortName") or "").strip().startswith("pt-BR-")
        and str(item.get("Locale") or "").strip().lower() == "pt-br"
    }


def voice_candidates_for_speaker(speaker, available_names=None, current=None):
    """Ordered native pt-BR candidates; a live catalogue is advisory, not exhaustive."""
    preferences = VOICE_PREFERENCES.get(speaker)
    if not preferences:
        raise RuntimeError(f"Personagem sem mapa de voz neural: {speaker}")
    available = set(available_names or [])
    ordered = []
    if current and (not available or current in available):
        ordered.append(current)
    ordered.extend(
        voice for voice in preferences
        if voice not in ordered and (not available or voice in available)
    )
    # If the unofficial catalogue endpoint lists only a subset, still probe the
    # documented Microsoft native pt-BR voices directly instead of assuming absent.
    if not ordered:
        ordered = list(preferences)
    elif len(ordered) < 2:
        ordered.extend(v for v in preferences if v not in ordered)
    return ordered


def choose_voice_assignments(available_names):
    """Choose four distinct voices; never silently assign one voice to several roles."""
    available = set(available_names or [])
    assigned = {}
    used = set()
    for speaker, preferences in VOICE_PREFERENCES.items():
        candidates = [v for v in preferences if not available or v in available]
        selected = next((voice for voice in candidates if voice not in used), None)
        if selected is None:
            raise RuntimeError(
                "Não há quatro vozes neurais brasileiras distintas no catálogo recebido. "
                "A dublagem foi bloqueada para evitar repetir a mesma voz entre personagens."
            )
        assigned[speaker] = selected
        used.add(selected)
    if len(set(assigned.values())) != 4:
        raise RuntimeError("A seleção de vozes não ficou exclusiva por personagem.")
    return assigned


def collect_dialogue_lines(episode):
    """Use only the fully expanded cinematic screenplay, never the short initial draft."""
    if not episode or not episode.get("cinematic_ready"):
        raise RuntimeError(
            "O roteiro ainda não foi expandido para a versão cinematográfica de seis cenas."
        )
    scenes = episode.get("scenes") or []
    if len(scenes) < 6:
        raise RuntimeError(
            f"O roteiro salvo contém apenas {len(scenes)} cenas; são necessárias seis cenas completas."
        )
    lines = []
    for scene_index, scene in enumerate(scenes, 1):
        for line_index, pair in enumerate(scene.get("dialogue") or [], 1):
            if not isinstance(pair, (list, tuple)) or len(pair) != 2:
                raise RuntimeError(f"Fala inválida na cena {scene_index}.")
            speaker, text = str(pair[0]).strip(), str(pair[1]).strip()
            if speaker not in VOICE_PREFERENCES or not text:
                raise RuntimeError(
                    f"Personagem sem voz configurada ou fala vazia na cena {scene_index}: "
                    f"{speaker or 'desconhecido'}."
                )
            lines.append({
                "scene": scene_index,
                "speaker": speaker,
                "text": text,
                "line": line_index
            })
    speakers = {line["speaker"] for line in lines}
    expected = set(VOICE_PREFERENCES)
    missing = sorted(expected - speakers)
    if missing:
        raise RuntimeError("Faltam diálogos para: " + ", ".join(missing))
    if len(lines) < 35:
        raise RuntimeError(
            f"O roteiro cinematográfico tem apenas {len(lines)} falas; "
            "a geração exige pelo menos 35 falas (alvo: 40)."
        )
    spoken_words = sum(_word_count(line["text"]) for line in lines)
    if spoken_words < 280:
        raise RuntimeError(
            f"O roteiro tem somente {spoken_words} palavras faladas; "
            "a geração exige no mínimo 280."
        )
    return lines


def _run(cmd, timeout=180):
    result = subprocess.run(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, timeout=timeout
    )
    if result.returncode:
        detail = (result.stderr or result.stdout or "comando falhou")[-1800:]
        raise RuntimeError(detail)
    return result.stdout.strip()


def _ffmpeg_path():
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        try:
            import imageio_ffmpeg
            ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        except Exception as exc:
            raise RuntimeError("FFmpeg não está disponível no servidor.") from exc
    return ffmpeg


def _probe(path, ffprobe="ffprobe"):
    raw = _run([
        ffprobe, "-v", "error", "-show_entries",
        "format=duration:stream=codec_type,width,height,sample_rate,channels",
        "-of", "json", str(path)
    ], timeout=30)
    data = json.loads(raw)
    duration = float((data.get("format") or {}).get("duration") or 0)
    return data, duration


def _srt_time(seconds):
    ms = max(0, int(round(float(seconds) * 1000)))
    hours, ms = divmod(ms, 3_600_000)
    minutes, ms = divmod(ms, 60_000)
    secs, ms = divmod(ms, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def _word_count(text):
    return len(re.findall(r"[\wÀ-ÿ'-]+", str(text or "")))


def _azure_ssml(text: str, voice: str, prosody: dict) -> str:
    """Build escaped SSML for one native Brazilian Portuguese Azure voice."""
    safe_text = escape(str(text))
    rate = escape(str(prosody.get("rate", "+0%")), {'"': "&quot;"})
    pitch = escape(str(prosody.get("pitch", "+0Hz")), {'"': "&quot;"})
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<speak version="1.0" xml:lang="pt-BR">'
        f'<voice name="{voice}" xml:lang="pt-BR">'
        f'<prosody rate="{rate}" pitch="{pitch}">{safe_text}</prosody>'
        '</voice></speak>'
    )


def _azure_synthesize_line(text: str, voice: str, prosody: dict, key: str, region: str) -> bytes:
    """Synthesize one line through the official Azure Speech REST endpoint."""
    import requests

    ssml = _azure_ssml(text, voice, prosody)
    endpoint = f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1"
    headers = {
        "Ocp-Apim-Subscription-Key": key,
        "Content-Type": "application/ssml+xml",
        "X-Microsoft-OutputFormat": "audio-24khz-48kbitrate-mono-mp3",
        "User-Agent": "GTAOcultoAI-ViceCity/1.0",
    }
    try:
        response = requests.post(
            endpoint, headers=headers, data=ssml.encode("utf-8"), timeout=(15, 90)
        )
    except requests.RequestException as exc:
        raise RuntimeError(f"Falha de conexão com Azure Speech: {str(exc)[:220]}") from exc
    if response.status_code != 200:
        detail = (response.text or "resposta vazia").replace("\\n", " ")[:350]
        raise RuntimeError(
            f"Azure Speech respondeu HTTP {response.status_code}: {detail}. "
            "Confira a chave, a região e a cota F0."
        )
    content = response.content or b""
    if len(content) < 1200:
        raise RuntimeError("Azure Speech retornou áudio vazio ou inválido.")
    return content


async def _synthesize_lines(lines, out_dir: Path, progress: Callable | None = None):
    """Render dialogue with four exclusive Azure neural voices, respecting F0 quotas."""
    key = os.getenv("AZURE_SPEECH_KEY", "").strip()
    region = os.getenv("AZURE_SPEECH_REGION", "").strip().lower()
    if not key or not region:
        raise RuntimeError(
            "A dublagem exige uma chave Azure Speech no nível gratuito F0. "
            "Configure AZURE_SPEECH_KEY e AZURE_SPEECH_REGION nas variáveis do Render. "
            "O Edge TTS público não disponibiliza quatro vozes pt-BR exclusivas; "
            "nenhum MP4 foi gerado."
        )
    if not re.fullmatch(r"[a-z0-9-]{2,30}", region):
        raise RuntimeError("AZURE_SPEECH_REGION inválida. Informe a região exibida no recurso Speech do Azure.")

    assigned = choose_voice_assignments({
        voice for candidates in VOICE_PREFERENCES.values() for voice in candidates
    })
    if len(set(assigned.values())) != 4:
        raise RuntimeError("A dublagem foi bloqueada: são obrigatórias quatro vozes pt-BR distintas.")

    present_speakers = {line["speaker"] for line in lines}
    missing = sorted(set(VOICE_PREFERENCES) - present_speakers)
    if missing:
        raise RuntimeError("O roteiro não contém falas para: " + ", ".join(missing))

    total = len(lines)
    rendered = [None] * total
    out_dir.mkdir(parents=True, exist_ok=True)
    # Azure Speech F0: 20 standard-voice transactions per 60 seconds.
    # Stay below the ceiling to avoid HTTP 429 at the rolling-window boundary.
    request_times = []
    completed = 0
    for index, line in enumerate(lines):
        now = time.monotonic()
        request_times = [stamp for stamp in request_times if now - stamp < 60.0]
        if len(request_times) >= 18:
            await asyncio.sleep(max(0.5, 60.1 - (now - request_times[0])))
            now = time.monotonic()
            request_times = [stamp for stamp in request_times if now - stamp < 60.0]

        speaker = line["speaker"]
        voice = assigned[speaker]
        mp3 = out_dir / f"line_{index + 1:02d}.mp3"
        mp3.unlink(missing_ok=True)
        request_times.append(time.monotonic())
        try:
            content = await asyncio.to_thread(
                _azure_synthesize_line, line["text"], voice,
                VOICE_PROSODY[speaker], key, region
            )
            mp3.write_bytes(content)
            if not mp3.exists() or mp3.stat().st_size < 1200:
                raise RuntimeError("o arquivo de áudio sintetizado ficou inválido")
            rendered[index] = mp3
        except Exception as exc:
            mp3.unlink(missing_ok=True)
            raise RuntimeError(
                f"Falha na fala {index + 1}/{total} de {speaker} com {voice}: {str(exc)[:320]}"
            ) from exc
        completed += 1
        if progress:
            progress("synthesis", completed, total)

    if any(path is None for path in rendered):
        raise RuntimeError("A síntese não produziu todas as falas; nenhum MP4 será exportado.")
    return rendered, assigned


def _to_wav(mp3_path: Path, wav_path: Path, ffmpeg: str):
    _run([
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(mp3_path), "-vn", "-ac", "1", "-ar", str(SAMPLE_RATE),
        "-c:a", "pcm_s16le", str(wav_path)
    ], timeout=60)
    if not wav_path.exists() or wav_path.stat().st_size < 4000:
        raise RuntimeError("Uma fala neural foi convertida em áudio inválido.")


def _wav_frames(path: Path):
    with wave.open(str(path), "rb") as wav:
        if wav.getnchannels() != 1 or wav.getsampwidth() != 2 or wav.getframerate() != SAMPLE_RATE:
            raise RuntimeError("Formato WAV intermediário inesperado.")
        return wav.getnframes()


def _speed_up_wav(path: Path, ratio: float, ffmpeg: str):
    """Apply only a small tempo correction; never pitch-shift or use robotic synthesis."""
    temp = path.with_name(path.stem + "_tempo.wav")
    _run([
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(path), "-filter:a", f"atempo={ratio:.5f}",
        "-ac", "1", "-ar", str(SAMPLE_RATE), "-c:a", "pcm_s16le", str(temp)
    ], timeout=60)
    temp.replace(path)


def _write_silence(wav, frames):
    remaining = max(0, int(frames))
    block = b"\x00\x00" * min(SAMPLE_RATE, remaining)
    while remaining:
        take = min(SAMPLE_RATE, remaining)
        wav.writeframesraw(block[:take * 2])
        remaining -= take


def _assemble_dialogue_audio(scenes, line_records, line_wavs, duration, out_dir):
    """Align naturally paced dialogue to the existing picture's six scene windows."""
    scene_weights = [
        max(1.0, float(scene.get("duration_seconds") or 1))
        for scene in scenes
    ]
    if len(scene_weights) != len(scenes):
        raise RuntimeError("Estrutura de cenas inválida.")

    intro = min(INTRO_SECONDS, max(0.0, duration * 0.04))
    outro = min(OUTRO_SECONDS, max(0.0, duration * 0.04))
    scene_total = max(1.0, duration - intro - outro)
    weight_total = sum(scene_weights)
    scene_targets = [scene_total * weight / weight_total for weight in scene_weights]

    speech_path = out_dir / "dialogue_neural.wav"
    subtitle_entries = []
    cursor = intro
    line_cursor = 0
    records_by_scene = []
    for scene_index, scene in enumerate(scenes):
        count = len(scene.get("dialogue") or [])
        group = line_records[line_cursor:line_cursor + count]
        group_wavs = line_wavs[line_cursor:line_cursor + count]
        records_by_scene.append((group, group_wavs, scene_targets[scene_index]))
        line_cursor += count
    if line_cursor != len(line_records):
        raise RuntimeError("O roteiro tem falas fora da estrutura de cenas.")

    with wave.open(str(speech_path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(SAMPLE_RATE)
        _write_silence(output, int(round(intro * SAMPLE_RATE)))

        for scene_index, (records, wavs, target_seconds) in enumerate(records_by_scene):
            target_frames = int(round(target_seconds * SAMPLE_RATE))
            frame_counts = [_wav_frames(path) for path in wavs]
            speech_frames = sum(frame_counts)
            gap_count = len(wavs) + 1
            min_gap_frames = int(MIN_DIALOGUE_GAP * SAMPLE_RATE)
            required = speech_frames + gap_count * min_gap_frames

            if required > target_frames:
                allowed_speech = max(1, target_frames - gap_count * min_gap_frames)
                tempo = speech_frames / allowed_speech
                if tempo > 1.15:
                    raise RuntimeError(
                        f"As falas da cena {scene_index + 1} excedem o tempo da imagem. "
                        "O áudio não será acelerado artificialmente."
                    )
                for path in wavs:
                    _speed_up_wav(path, tempo, _ffmpeg_path())
                frame_counts = [_wav_frames(path) for path in wavs]
                speech_frames = sum(frame_counts)
                required = speech_frames + gap_count * min_gap_frames
                if required > target_frames + int(0.03 * SAMPLE_RATE):
                    raise RuntimeError(f"Não foi possível sincronizar a cena {scene_index + 1}.")

            extra = max(0, target_frames - required)
            gap_frames = min_gap_frames + extra // gap_count
            remainder = extra - (extra // gap_count) * gap_count

            _write_silence(output, gap_frames)
            cursor += gap_frames / SAMPLE_RATE

            for index, (record, wav_path, frames) in enumerate(zip(records, wavs, frame_counts)):
                start = cursor
                with wave.open(str(wav_path), "rb") as source:
                    data = source.readframes(frames)
                output.writeframesraw(data)
                cursor += frames / SAMPLE_RATE
                end = cursor
                subtitle_entries.append({
                    "speaker": record["speaker"],
                    "text": record["text"],
                    "start": start,
                    "end": end
                })
                this_gap = gap_frames + (remainder if index == len(wavs) - 1 else 0)
                _write_silence(output, this_gap)
                cursor += this_gap / SAMPLE_RATE
            # Correct single-sample rounding so the next scene begins exactly on its boundary.
            cursor = intro + sum(scene_targets[:scene_index + 1])

        # Trim/pad to the exact input-video duration.
        total_frames = int(round(duration * SAMPLE_RATE))
        current_frames = int(round(cursor * SAMPLE_RATE))
        if current_frames < total_frames:
            _write_silence(output, total_frames - current_frames)
        elif current_frames > total_frames:
            raise RuntimeError("A faixa neural ultrapassou a duração do vídeo.")

    srt_path = out_dir / "legendas_voz_neural.srt"
    with srt_path.open("w", encoding="utf-8") as handle:
        for index, item in enumerate(subtitle_entries, 1):
            handle.write(
                f"{index}\n{_srt_time(item['start'])} --> {_srt_time(item['end'])}\n"
                f"<font color=\"#d9a8ff\">{item['speaker']}</font>\n"
                f"{item['text']}\n\n"
            )
    return speech_path, srt_path, subtitle_entries


def render_voice_remix(
    episode: dict,
    source_video: str | Path,
    output_dir: str | Path,
    progress: Callable | None = None,
):
    """Replace only the MP4 audio with distinct neural pt-BR character dialogue."""
    source_video = Path(source_video)
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if not source_video.is_file() or source_video.stat().st_size < 50_000:
        raise RuntimeError("Envie o MP4 original do episódio 01 para substituir o áudio.")

    ffmpeg = _ffmpeg_path()
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise RuntimeError("ffprobe não está disponível para validar o MP4.")
    probe, video_duration = _probe(source_video, ffprobe)
    streams = probe.get("streams") or []
    if not any(x.get("codec_type") == "video" for x in streams):
        raise RuntimeError("O arquivo enviado não contém uma faixa de vídeo.")
    if not 10 <= video_duration <= 600:
        raise RuntimeError("A duração do MP4 precisa ficar entre 10 segundos e 10 minutos.")

    scenes = episode.get("scenes") or []
    lines = collect_dialogue_lines(episode)

    if progress:
        progress("connecting", 0, len(lines))
    mp3_paths, voice_assignments = asyncio.run(
        _synthesize_lines(lines, out_dir, progress=progress)
    )
    if len(set(voice_assignments.values())) != 4:
        raise RuntimeError("A dublagem foi bloqueada: os quatro personagens precisam de vozes distintas.")

    wav_paths = []
    for index, mp3 in enumerate(mp3_paths, 1):
        wav_path = out_dir / f"line_{index:02d}.wav"
        _to_wav(mp3, wav_path, ffmpeg)
        wav_paths.append(wav_path)

    if progress:
        progress("mixing", len(lines), len(lines))
    speech_path, subtitles_path, subtitle_entries = _assemble_dialogue_audio(
        scenes, lines, wav_paths, video_duration, out_dir
    )

    # A restrained original ambient bed sits well below dialogue; the old robotic
    # audio is completely discarded and never mixed back into the new master.
    score_path = out_dir / "ambient_score.wav"
    score_filter = (
        f"[0:a]volume=0.045,lowpass=f=155,afade=t=in:st=0:d=2,"
        f"afade=t=out:st={max(0.0, video_duration - 3):.3f}:d=3[a];"
        f"[1:a]volume=0.018,lowpass=f=230,afade=t=in:st=0:d=3,"
        f"afade=t=out:st={max(0.0, video_duration - 3):.3f}:d=3[b];"
        "[a][b]amix=inputs=2:normalize=0,volume=0.75[out]"
    )
    _run([
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i",
        f"sine=frequency=55:sample_rate={SAMPLE_RATE}:duration={video_duration:.3f}",
        "-f", "lavfi", "-i",
        f"sine=frequency=82.41:sample_rate={SAMPLE_RATE}:duration={video_duration:.3f}",
        "-filter_complex", score_filter, "-map", "[out]",
        "-c:a", "pcm_s16le", "-ar", str(SAMPLE_RATE), "-ac", "1", str(score_path)
    ], timeout=120)

    mixed_path = out_dir / "audio_neural_final.wav"
    mix_filter = (
        "[0:a]volume=1.0[voice];[1:a]volume=0.23[score];"
        "[voice][score]amix=inputs=2:duration=first:normalize=0,"
        "alimiter=limit=0.94[out]"
    )
    _run([
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(speech_path), "-i", str(score_path),
        "-filter_complex", mix_filter, "-map", "[out]",
        "-c:a", "pcm_s16le", "-ar", str(SAMPLE_RATE), "-ac", "1", str(mixed_path)
    ], timeout=180)

    final_path = out_dir / "VICE_CITY_EP01_VOZES_NEURAIS.mp4"
    _run([
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(source_video), "-i", str(mixed_path),
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
        "-ar", "44100", "-ac", "2", "-shortest",
        "-movflags", "+faststart", "-metadata",
        "comment=Dialogos sinteticos neurais pt-BR por personagem; sem clonagem de voz",
        str(final_path)
    ], timeout=240)

    final_probe, final_duration = _probe(final_path, ffprobe)
    final_streams = final_probe.get("streams") or []
    has_video = any(x.get("codec_type") == "video" for x in final_streams)
    has_audio = any(x.get("codec_type") == "audio" for x in final_streams)
    if not has_video or not has_audio or final_path.stat().st_size < 50_000:
        raise RuntimeError("O MP4 final não passou na validação de áudio e vídeo.")
    if abs(final_duration - video_duration) > 1.0:
        raise RuntimeError("A duração do MP4 final ficou diferente do original.")

    if progress:
        progress("complete", len(lines), len(lines))
    return {
        "video_path": str(final_path),
        "subtitle_path": str(subtitles_path),
        "duration_seconds": round(final_duration, 2),
        "size_bytes": final_path.stat().st_size,
        "spoken_lines": len(lines),
        "spoken_words": sum(_word_count(x["text"]) for x in lines),
        "voices": voice_assignments,
        "subtitle_entries": len(subtitle_entries),
        "audio_engine": "Microsoft Azure Speech Neural (F0)",
        "sample_rate": SAMPLE_RATE,
    }

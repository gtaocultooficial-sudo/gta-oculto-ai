"""Neural, character-specific dialogue rendering for the Vice City fan series.

This module deliberately has no eSpeak or gTTS fallback. A failed neural TTS call
raises an actionable error rather than silently returning robotic audio.
"""
from __future__ import annotations

import asyncio
import json
import math
import re
import shutil
import subprocess
import wave
from pathlib import Path
from typing import Callable


SAMPLE_RATE = 44100
FPS = 24
INTRO_SECONDS = 4.0
OUTRO_SECONDS = 3.8
MIN_DIALOGUE_GAP = 0.24

# Prefer distinct pt-BR neural voices, not pitch-shifted copies of one voice.
VOICE_PREFERENCES = {
    "JASON DUVAL": [
        "pt-BR-DonatoNeural", "pt-BR-FabioNeural",
        "pt-BR-MacerioMultilingualNeural", "pt-BR-AntonioNeural"
    ],
    "LUCIA CAMINOS": [
        "pt-BR-ThalitaMultilingualNeural", "pt-BR-FranciscaNeural",
        "pt-BR-BrendaNeural", "pt-BR-LeilaNeural"
    ],
    "BRIAN HEDER": [
        "pt-BR-AntonioNeural", "pt-BR-HumbertoNeural",
        "pt-BR-NicolauNeural", "pt-BR-ValerioNeural"
    ],
    "CAL HAMPTON": [
        "pt-BR-JulioNeural", "pt-BR-FabioNeural",
        "pt-BR-NicolauNeural", "pt-BR-MacerioMultilingualNeural"
    ],
}

# Small prosody differences reinforce character identity without caricature.
VOICE_PROSODY = {
    "JASON DUVAL": {"rate": "-4%", "pitch": "-2Hz", "volume": "+0%"},
    "LUCIA CAMINOS": {"rate": "-1%", "pitch": "+1Hz", "volume": "+0%"},
    "BRIAN HEDER": {"rate": "-7%", "pitch": "-3Hz", "volume": "+0%"},
    "CAL HAMPTON": {"rate": "+3%", "pitch": "+2Hz", "volume": "+0%"},
}


def choose_voice_assignments(available_names):
    """Choose four distinct neural pt-BR voices from the live Edge TTS catalogue."""
    available = set(available_names or [])
    assigned = {}
    used = set()
    for speaker, preferences in VOICE_PREFERENCES.items():
        selected = next(
            (voice for voice in preferences if voice in available and voice not in used),
            None
        )
        if selected is None:
            raise RuntimeError(
                "O catálogo Edge TTS não disponibilizou quatro vozes brasileiras "
                "distintas. Vozes necessárias: " + ", ".join(VOICE_PREFERENCES)
            )
        assigned[speaker] = selected
        used.add(selected)
    return assigned


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


async def _synthesize_lines(lines, out_dir: Path, progress: Callable | None = None):
    try:
        import edge_tts
    except Exception as exc:
        raise RuntimeError(
            "Edge TTS não está instalado no servidor. Nenhuma voz local robótica será usada."
        ) from exc

    try:
        catalogue = await edge_tts.list_voices()
    except Exception as exc:
        raise RuntimeError(
            "Não foi possível acessar o serviço de vozes neurais da Microsoft: "
            + str(exc)[:300]
        ) from exc

    available = {
        str(item.get("ShortName", ""))
        for item in catalogue
        if str(item.get("Locale", "")).lower() == "pt-br"
    }
    voices = choose_voice_assignments(available)
    semaphore = asyncio.Semaphore(3)
    completed = 0
    total = len(lines)
    rendered = [None] * total

    async def one(index, line):
        nonlocal completed
        speaker = line["speaker"]
        voice = voices[speaker]
        prosody = VOICE_PROSODY[speaker]
        mp3 = out_dir / f"line_{index + 1:02d}.mp3"
        async with semaphore:
            try:
                communicate = edge_tts.Communicate(
                    text=line["text"],
                    voice=voice,
                    rate=prosody["rate"],
                    pitch=prosody["pitch"],
                    volume=prosody["volume"],
                )
                await communicate.save(str(mp3))
            except Exception as exc:
                raise RuntimeError(
                    f"Falha na voz neural de {speaker} ({voice}): {str(exc)[:280]}"
                ) from exc
        if not mp3.exists() or mp3.stat().st_size < 1500:
            raise RuntimeError(f"A voz neural de {speaker} não gerou áudio válido.")
        rendered[index] = mp3
        completed += 1
        if progress:
            progress("synthesis", completed, total)
    await asyncio.gather(*(one(i, item) for i, item in enumerate(lines)))
    return rendered, voices


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
    lines = []
    for scene_index, scene in enumerate(scenes, 1):
        for line_index, pair in enumerate(scene.get("dialogue") or [], 1):
            if not isinstance(pair, (list, tuple)) or len(pair) != 2:
                raise RuntimeError(f"Fala inválida na cena {scene_index}.")
            speaker, text = str(pair[0]).strip(), str(pair[1]).strip()
            if speaker not in VOICE_PREFERENCES or not text:
                raise RuntimeError(f"Personagem sem voz configurada: {speaker or 'desconhecido'}.")
            lines.append({
                "scene": scene_index,
                "speaker": speaker,
                "text": text,
                "line": line_index
            })
    if not lines:
        raise RuntimeError("O episódio não tem diálogos para dublar.")

    if progress:
        progress("connecting", 0, len(lines))
    mp3_paths, voice_assignments = asyncio.run(
        _synthesize_lines(lines, out_dir, progress=progress)
    )

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
        "audio_engine": "Microsoft Edge Neural TTS",
        "sample_rate": SAMPLE_RATE,
    }

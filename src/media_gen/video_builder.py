"""
src/media_gen/video_builder.py
------------------------------
Gera vídeo vertical (1080x1920) dinâmico a partir da imagem gerada, com suporte a:
- Efeito Ken Burns (pan/zoom contínuo 1.0x -> 1.10x) para evitar detecção de imagem estática
- Gate de validação de voz neural (Edge-TTS)
- Mixagem inteligente de voz + música ambiente de fundo
- Motor primário de alta performance via FFmpeg CLI e fallback MoviePy
"""
from pathlib import Path
import random
import subprocess
import os
import re

from config.settings import VIDEO_DURATION, OUTPUT_VIDEOS, AUDIO_PATH
from src.media_gen.tts import generate_narration
from src.utils.logger import get_logger

log = get_logger(__name__)


def get_available_audio_tracks() -> list[Path]:
    """Retorna arquivos de áudio disponíveis em data/audio."""
    if not AUDIO_PATH.is_dir():
        return []
    valid_exts = {".mp3", ".wav", ".m4a", ".aac", ".ogg"}
    return [
        p for p in AUDIO_PATH.iterdir()
        if p.is_file() and p.suffix.lower() in valid_exts and not p.name.startswith("temp_") and not p.name.startswith("teste_")
    ]


def _get_audio_duration(path: Path) -> float:
    """Calcula duração exata de arquivo de áudio via ffprobe."""
    try:
        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(path)
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5)
        if res.returncode == 0 and res.stdout.strip():
            return float(res.stdout.strip())
    except Exception:
        pass
    return 0.0


def _build_video_ffmpeg(
    image_path: Path,
    out_file: Path,
    dur: int,
    tts_audio: Path | None,
    bg_music: Path | None
) -> bool:
    """Renderiza vídeo dinâmico com efeito Ken Burns e mixagem via FFmpeg CLI."""
    total_frames = max(24, int(dur * 24))
    zoom_step = 0.10 / total_frames

    # Ken Burns filter: zoom suave contínuo em direção ao centro
    video_filter = (
        f"zoompan=z='min(zoom+{zoom_step:.6f},1.10)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
        f"d=1:s=1080x1920:fps=24"
    )

    fade_start = max(1, dur - 2)

    try:
        if tts_audio and Path(tts_audio).is_file() and bg_music and Path(bg_music).is_file():
            cmd = [
                "ffmpeg", "-y", "-loop", "1",
                "-i", str(image_path),
                "-i", str(tts_audio),
                "-i", str(bg_music),
                "-filter_complex",
                f"[0:v]{video_filter}[vout];"
                f"[1:a]volume=1.0[vocal];"
                f"[2:a]volume=0.12,afade=t=out:st={fade_start}:d=2[bg];"
                f"[vocal][bg]amix=inputs=2:duration=longest:dropout_transition=2[aout]",
                "-map", "[vout]",
                "-map", "[aout]",
                "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "192k",
                "-t", str(dur),
                str(out_file)
            ]
        elif tts_audio and Path(tts_audio).is_file():
            cmd = [
                "ffmpeg", "-y", "-loop", "1",
                "-i", str(image_path),
                "-i", str(tts_audio),
                "-filter_complex",
                f"[0:v]{video_filter}[vout];[1:a]volume=1.0[aout]",
                "-map", "[vout]",
                "-map", "[aout]",
                "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "192k",
                "-t", str(dur),
                str(out_file)
            ]
        elif bg_music and Path(bg_music).is_file():
            cmd = [
                "ffmpeg", "-y", "-loop", "1",
                "-i", str(image_path),
                "-i", str(bg_music),
                "-filter_complex",
                f"[0:v]{video_filter}[vout];"
                f"[1:a]volume=0.95,afade=t=out:st={fade_start}:d=2[aout]",
                "-map", "[vout]",
                "-map", "[aout]",
                "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "192k",
                "-t", str(dur),
                str(out_file)
            ]
        else:
            cmd = [
                "ffmpeg", "-y", "-loop", "1",
                "-i", str(image_path),
                "-filter_complex", f"[0:v]{video_filter}[vout]",
                "-map", "[vout]",
                "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-t", str(dur),
                str(out_file)
            ]

        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if res.returncode == 0 and out_file.is_file() and out_file.stat().st_size > 1000:
            return True
        else:
            log.warning(f"FFmpeg CLI falhou ({res.stderr[:200]}). Tentando fallback MoviePy...")
    except Exception as exc:
        log.warning(f"Erro ao executar FFmpeg CLI: {exc}. Tentando fallback MoviePy...")

def _build_multislide_video_ffmpeg(
    slides: list[Path],
    out_file: Path,
    dur: int,
    tts_audio: Path | None,
    bg_music: Path | None
) -> bool:
    """Renderiza vídeo sequencial multi-cena (Ken Burns em cada lâmina + mixagem) via FFmpeg CLI."""
    n = len(slides)
    if n == 0:
        return False
    if n == 1:
        return _build_video_ffmpeg(slides[0], out_file, dur, tts_audio, bg_music)

    dur_each = dur / n
    fps = 24
    frames_each = max(24, int(dur_each * fps))
    zoom_step = 0.06 / frames_each

    inputs = []
    for s in slides:
        inputs.extend(["-loop", "1", "-t", f"{dur_each:.2f}", "-i", str(s)])

    if tts_audio and Path(tts_audio).is_file():
        inputs.extend(["-i", str(tts_audio)])
    if bg_music and Path(bg_music).is_file():
        inputs.extend(["-i", str(bg_music)])

    filters = []
    concat_inputs = []
    for i in range(n):
        # Alterna dinamicamente a movimentação de câmera:
        # Cenas pares: Zoom In contínuo (1.0 -> 1.07)
        # Cenas ímpares: Zoom Out contínuo (1.07 -> 1.0)
        if i % 2 == 0:
            z_expr = f"min(zoom+{zoom_step:.6f},1.07)"
        else:
            z_expr = f"if(lte(zoom,1.0),1.07,max(1.0,zoom-{zoom_step:.6f}))"

        f_scene = (
            f"[{i}:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
            f"zoompan=z='{z_expr}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            f"d=1:s=1080x1920:fps={fps},setpts=PTS-STARTPTS[v{i}]"
        )
        filters.append(f_scene)
        concat_inputs.append(f"[v{i}]")

    concat_str = "".join(concat_inputs) + f"concat=n={n}:v=1:a=0[vconcat]"
    filters.append(concat_str)

    fade_start = max(1, dur - 2)
    has_tts = tts_audio and Path(tts_audio).is_file()
    has_bg = bg_music and Path(bg_music).is_file()

    audio_idx_tts = n if has_tts else None
    audio_idx_bg = (n + 1 if has_tts else n) if has_bg else None

    if has_tts and has_bg:
        filters.append(
            f"[{audio_idx_tts}:a]volume=1.0[vocal];"
            f"[{audio_idx_bg}:a]volume=0.12,afade=t=out:st={fade_start}:d=2[bg];"
            f"[vocal][bg]amix=inputs=2:duration=longest:dropout_transition=2[aout]"
        )
        map_audio = "[aout]"
    elif has_tts:
        filters.append(f"[{audio_idx_tts}:a]volume=1.0[aout]")
        map_audio = "[aout]"
    elif has_bg:
        filters.append(f"[{audio_idx_bg}:a]volume=0.95,afade=t=out:st={fade_start}:d=2[aout]")
        map_audio = "[aout]"
    else:
        map_audio = None

    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", ";".join(filters),
        "-map", "[vconcat]",
    ]
    if map_audio:
        cmd.extend(["-map", map_audio, "-c:a", "aac", "-b:a", "192k"])

    cmd.extend([
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-t", str(dur),
        str(out_file)
    ])

    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if res.returncode == 0 and out_file.is_file() and out_file.stat().st_size > 1000:
            return True
        else:
            log.warning(f"FFmpeg multi-slide falhou ({res.stderr[:250]}).")
    except Exception as exc:
        log.warning(f"Erro no FFmpeg multi-slide: {exc}")

    return False


def _build_video_moviepy(
    image_path: Path,
    out_file: Path,
    dur: int,
    tts_audio: Path | None,
    bg_music: Path | None
) -> bool:
    """Renderiza vídeo de fallback via MoviePy."""
    try:
        try:
            from moviepy import ImageClip, AudioFileClip, CompositeAudioClip
        except ImportError:
            from moviepy.editor import ImageClip, AudioFileClip, CompositeAudioClip

        try:
            clip = ImageClip(str(image_path), duration=dur)
        except Exception:
            clip = ImageClip(str(image_path))
            if hasattr(clip, "with_duration"):
                clip = clip.with_duration(dur)
            else:
                clip = clip.set_duration(dur)

        tts_clip = None
        if tts_audio and tts_audio.is_file():
            try:
                tts_clip = AudioFileClip(str(tts_audio))
            except Exception:
                pass

        audio_layers = []
        if tts_clip:
            audio_layers.append(tts_clip)

        bg_clip = None
        if bg_music and Path(bg_music).is_file():
            try:
                raw_bg = AudioFileClip(str(bg_music))
                bg_sub = raw_bg.subclipped(0, dur) if hasattr(raw_bg, "subclipped") else raw_bg.subclip(0, dur)
                vol_factor = 0.12 if tts_clip else 0.95
                if hasattr(bg_sub, "with_volume_scaled"):
                    bg_sub = bg_sub.with_volume_scaled(vol_factor)
                elif hasattr(bg_sub, "volumex"):
                    bg_sub = bg_sub.volumex(vol_factor)
                audio_layers.append(bg_sub)
                bg_clip = bg_sub
            except Exception:
                pass

        final_audio = None
        if len(audio_layers) > 1:
            final_audio = CompositeAudioClip(audio_layers)
        elif len(audio_layers) == 1:
            final_audio = audio_layers[0]

        if final_audio:
            clip = clip.with_audio(final_audio) if hasattr(clip, "with_audio") else clip.set_audio(final_audio)

        clip.write_videofile(
            str(out_file),
            fps=24,
            codec="libx264",
            audio_codec="aac" if final_audio else None,
            ffmpeg_params=["-pix_fmt", "yuv420p"],
            logger=None
        )
        clip.close()
        if tts_clip:
            tts_clip.close()
        if bg_clip:
            bg_clip.close()

        return out_file.is_file() and out_file.stat().st_size > 1000
    except Exception as exc:
        log.error(f"MoviePy fallback também falhou: {exc}")
        return False


def generate_video_from_image(
    image_path: Path,
    output_path: Path | None = None,
    duration: int | None = None,
    audio_path: Path | None = None,
    narration_text: str | None = None,
    with_narration: bool = True,
    slides: list[Path] | None = None
) -> Path | None:
    """
    Renderiza vídeo dinâmico 9:16 (1080x1920) com efeito Ken Burns e áudio mixado.
    Se o post possui carrossel com múltiplas cenas (scenes/ ou slide_*.png),
    gera um vídeo sequencial dinâmico que alterna as imagens e frases automaticamente!
    Garante que se narração foi solicitada, o vídeo não será publicado sem voz.
    """
    from config.settings import VIDEO_DURATION_VERSE, VIDEO_DURATION_SAINT
    default_dur = VIDEO_DURATION_SAINT if (slides and len(slides) > 2) else VIDEO_DURATION_VERSE
    dur = duration or default_dur
    # Nome previsível do arquivo de saída
    if output_path:
        out_file = Path(output_path)
    else:
        # Tenta extrair id do post do caminho para evitar sobreescrita genérica como 'slide_01.mp4'
        match_id = re.search(r'(?:post|verse|carousel)_(\d+)', str(image_path))
        if match_id:
            out_file = OUTPUT_VIDEOS / f"post_{int(match_id.group(1)):04d}.mp4"
        else:
            out_file = OUTPUT_VIDEOS / f"{image_path.stem}.mp4"

    # 1. Gate Crítico de Narração Neural
    tts_audio: Path | None = None
    if with_narration and narration_text:
        from config.settings import ENABLE_AUDIO_CTA, CTA_VERSE_TEXT
        text_to_narrate = narration_text.strip()
        # Se CTA estiver ativo e o texto ainda não tiver chamada de encerramento
        if ENABLE_AUDIO_CTA and CTA_VERSE_TEXT:
            lower_end = text_to_narrate[-140:].lower()
            if not any(k in lower_end for k in ("compartilhe", "salve", "siga", "curta")):
                from src.media_gen.tts import build_verse_narration_text
                text_to_narrate = build_verse_narration_text(text_to_narrate)

        tts_temp = OUTPUT_VIDEOS / f"{out_file.stem}_narration.mp3"
        tts_audio = generate_narration(text_to_narrate, tts_temp)
        if not tts_audio or not tts_audio.is_file():
            err_msg = (
                f"Falha crítica na geração de narração neural para '{image_path.stem}'. "
                f"Renderização abortada para evitar publicação de vídeo mudo sem retenção."
            )
            log.error(err_msg)
            raise RuntimeError(err_msg)

        # Ajusta duração baseado na fala + 1s de respiro musical final (evita vácuo de silêncio)
        tts_dur = _get_audio_duration(tts_audio)
        if tts_dur > 0:
            computed_dur = max(6, int(round(tts_dur + 1.0)))
            dur = max(duration, computed_dur) if duration else computed_dur

    # 2. Seleciona trilha ambiente de fundo
    bg_music = audio_path
    if not bg_music:
        tracks = get_available_audio_tracks()
        if tracks:
            bg_music = random.choice(tracks)
    if bg_music and Path(bg_music).is_file():
        log.info(f"Trilha de fundo selecionada: {Path(bg_music).name}")

    # 3. Identifica se há múltiplas lâminas/cenas (Carrossel -> Vídeo multi-cena)
    # REGRA: Para vídeos verticais (TikTok/Reels/Shorts), prioriza SEMPRE cenas verticais (scenes/scene_*.png)
    slides_to_use: list[Path] = []
    
    # 1º: Procura pasta 'scenes' (cenas 9:16 sem textos de 'deslize para o lado')
    cand_dirs = []
    if slides and len(slides) > 0:
        cand_dirs.append(Path(slides[0]).parent)
    if image_path:
        cand_dirs.append(Path(image_path).parent)
        cand_dirs.append(Path(image_path).parent.parent)

    for c_dir in cand_dirs:
        if c_dir.name.lower() == "scenes":
            found = sorted([s for s in c_dir.glob("scene_*.png") if s.is_file()])
            if len(found) > 1:
                slides_to_use = found
                break
        scenes_sub = c_dir / "scenes"
        if scenes_sub.is_dir():
            found = sorted([s for s in scenes_sub.glob("scene_*.png") if s.is_file()])
            if len(found) > 1:
                slides_to_use = found
                break

    # 2º: Fallback para lista explícita ou slide_*.png
    if not slides_to_use:
        if slides:
            slides_to_use = [Path(s) for s in slides if Path(s).is_file()]
        elif image_path:
            p = Path(image_path).resolve()
            found = sorted([s for s in p.parent.glob("slide_*.png") if s.is_file()])
            if len(found) > 1:
                slides_to_use = found

    # 4. Renderiza com Ken Burns via FFmpeg primário
    if len(slides_to_use) > 1:
        log.info(f"Renderizando vídeo multi-cena sequencial com {len(slides_to_use)} lâminas dinâmicas...")
        success = _build_multislide_video_ffmpeg(slides_to_use, out_file, dur, tts_audio, bg_music)
        if not success:
            success = _build_video_ffmpeg(slides_to_use[0], out_file, dur, tts_audio, bg_music)
    else:
        success = _build_video_ffmpeg(image_path, out_file, dur, tts_audio, bg_music)
        if not success:
            success = _build_video_moviepy(image_path, out_file, dur, tts_audio, bg_music)

    # 5. Limpeza de áudio temporário de voz
    if tts_audio and tts_audio.is_file():
        try:
            tts_audio.unlink()
        except Exception:
            pass

    if success:
        log.info(f"Vídeo dinâmico gerado com sucesso: {out_file.name} (Ken Burns 1080x1920, {dur}s)")
        return out_file

    log.error(f"Falha ao gerar vídeo para {image_path.name}")
    return None
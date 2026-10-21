"""
src/media_gen/tts.py
--------------------
Geração de voz neural brasileira gratuita e de alta qualidade com Edge-TTS.
Suporta vozes:
  - pt-BR-AntonioNeural (Voz masculina profunda, ideal para reflexão bíblica)
  - pt-BR-FranciscaNeural (Voz feminina suave e acolhedora)
"""
import asyncio
from pathlib import Path
import re
import subprocess
import edge_tts

from src.utils.logger import get_logger

log = get_logger(__name__)

DEFAULT_VOICE = "pt-BR-AntonioNeural"


ABBREVIATIONS = {
    "gn": "Gênesis", "ex": "Êxodo", "êx": "Êxodo", "lv": "Levítico", "nm": "Números",
    "dt": "Deuteronômio", "js": "Josué", "jz": "Juízes", "rt": "Rute",
    "1sm": "Primeiro Samuel", "2sm": "Segundo Samuel", "1rs": "Primeiro Reis", "2rs": "Segundo Reis",
    "1cr": "Primeiro Crônicas", "2cr": "Segundo Crônicas", "ed": "Esdras", "ne": "Neemias",
    "et": "Ester", "jó": "Jó", "sl": "Salmos", "pv": "Provérbios", "ec": "Eclesiastes",
    "ct": "Cantares", "is": "Isaías", "jr": "Jeremias", "lm": "Lamentações", "ez": "Ezequiel",
    "dn": "Daniel", "os": "Oséias", "jl": "Joel", "am": "Amós", "ob": "Obadias",
    "jn": "Jonas", "mq": "Miqueias", "na": "Naum", "hc": "Habacuque", "sf": "Sofonias",
    "ag": "Ageu", "zc": "Zacarias", "ml": "Malaquias", "mt": "Mateus", "mc": "Marcos",
    "lc": "Lucas", "jo": "João", "at": "Atos", "rm": "Romanos", "1co": "Primeira Coríntios",
    "2co": "Segunda Coríntios", "gl": "Gálatas", "ef": "Efésios", "fp": "Filipenses",
    "cl": "Colossenses", "1ts": "Primeira Tessalonicenses", "2ts": "Segunda Tessalonicenses",
    "1tm": "Primeira Timóteo", "2tm": "Segunda Timóteo", "tt": "Tito", "fm": "Filemom",
    "hb": "Hebreus", "tg": "Tiago", "1pe": "Primeiro Pedro", "2pe": "Segundo Pedro",
    "1jo": "Primeiro João", "2jo": "Segundo João", "3jo": "Terceiro João", "jd": "Judas",
    "ap": "Apocalipse"
}

MASC_BOOKS = {
    "samuel", "reis", "cronicas", "crônicas", "tessalonicenses",
    "timoteo", "timóteo", "pedro", "joao", "joão"
}


def expand_book_title(prefix: str, book: str) -> str:
    """Expande nomes abreviados e ajusta numerais ordinais (ex: '1 Coríntios' -> 'Primeira Coríntios')."""
    cleaned_book = book.strip()
    cleaned_prefix = prefix.strip() if prefix else ""

    combined_key = f"{cleaned_prefix}{cleaned_book}".lower().replace(" ", "")
    if combined_key in ABBREVIATIONS:
        return ABBREVIATIONS[combined_key]
    if cleaned_book.lower() in ABBREVIATIONS:
        return ABBREVIATIONS[cleaned_book.lower()]

    if cleaned_prefix:
        b_norm = cleaned_book.lower()
        is_masc = any(b_norm.startswith(m) for m in MASC_BOOKS)
        if "1" in cleaned_prefix:
            pref = "Primeiro" if is_masc else "Primeira"
        elif "2" in cleaned_prefix:
            pref = "Segundo" if is_masc else "Segunda"
        elif "3" in cleaned_prefix:
            pref = "Terceiro" if is_masc else "Terceira"
        else:
            pref = cleaned_prefix
        return f"{pref} {cleaned_book}"

    return cleaned_book


def convert_biblical_references(text: str) -> str:
    """
    Converte referências bíblicas escritas para pronúncia natural em voz alta.
    Exemplos:
      'Marcos 10: 2-4' -> 'Marcos, capítulo 10, versículos de 2 a 4'
      'João 3:16'      -> 'João, capítulo 3, versículo 16'
      'Salmos 23:1-3'  -> 'Salmos, capítulo 23, versículos de 1 a 3'
    """
    def _repl_ref(m: re.Match) -> str:
        prefix = m.group(1) or ""
        book = m.group(2)
        cap = m.group(3).strip()
        v_start = m.group(4).strip()
        v_end = m.group(5)
        v_extra = m.group(6)

        full_book = expand_book_title(prefix, book)

        if v_end:
            v_text = f"versículos de {v_start} a {v_end.strip()}"
        elif v_extra:
            v_text = f"versículos {v_start} e {v_extra.strip()}"
        else:
            v_text = f"versículo {v_start}"

        return f"{full_book}, capítulo {cap}, {v_text}."

    pattern = re.compile(
        r"\b(?:([1-3]|1ª|2ª|3ª|1º|2º|3º)\s*)?"
        r"([A-Za-zÀ-ÿ]+)\s+"
        r"(\d+)\s*:\s*"
        r"(\d+)"
        r"(?:"
        r"(?:\s*[-–—eàa]\s*|\s+a\s+)(\d+)"
        r"|"
        r"(?:\s*,\s*|\s+e\s+)(\d+)"
        r")?",
        re.IGNORECASE
    )

    text = pattern.sub(_repl_ref, text)

    # Trata citações isoladas de versículos como 'vs. 2-4' ou 'v. 16'
    text = re.sub(r"\b(?:vs\.|versículos)\s*(\d+)\s*[-–—]\s*(\d+)", r"versículos de \1 a \2", text, flags=re.IGNORECASE)
    text = re.sub(r"\b(?:v\.|versículo)\s*(\d+)", r"versículo \1", text, flags=re.IGNORECASE)

    # Caso reste algum padrão numérico de capítulo e versículo isolado: ' 10: 2-4'
    text = re.sub(r"(?<=\s)(\d+)\s*:\s*(\d+)\s*[-–—]\s*(\d+)", r"capítulo \1, versículos de \2 a \3", text)
    text = re.sub(r"(?<=\s)(\d+)\s*:\s*(\d+)", r"capítulo \1, versículo \2", text)

    return text


def clean_text_for_speech(raw_text: str) -> str:
    """Limpa hashtags e converte referências bíblicas para uma leitura falada humana."""
    # 1. Remove hashtags das redes sociais
    text = re.sub(r"#\S+", "", raw_text)

    # 2. Converte citações bíblicas (ex: Marcos 10: 2-4) antes de remover traços
    text = convert_biblical_references(text)

    # 3. Transforma quebras de linha em pausas de frase
    text = re.sub(r"\n+", ". ", text)

    # 4. Converte intervalos de anos e números (ex: 1515 - 1582 -> 1515 a 1582)
    # Suporta padrões: '1515 - 1582', '1515–1582', '(1515-1582)'
    text = re.sub(r"(?<=\b)(\d{3,4})\s*[-–—]\s*(\d{3,4})(?=\b)", r"\1 a \2", text)
    # Para intervalos numéricos gerais com traço entre espaços (ex: 10 - 20)
    text = re.sub(r"(?<=\d)\s+[-–—]\s+(?=\d)", " a ", text)

    # 5. Remove traços decorativos restantes
    text = text.replace("—", " ").replace("–", " ")
    text = re.sub(r"(?<!\d)-(?!\d)", " ", text)

    # 6. Normaliza pontuação e espaços múltiplos
    text = re.sub(r"\.+", ".", text)
    text = re.sub(r"\s*,\s*", ", ", text)
    text = re.sub(r"\s*\.\s*", ". ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


async def _async_generate_speech(text: str, output_path: Path, voice: str) -> bool:
    voices_to_try = [voice]
    alt_voice = "pt-BR-FranciscaNeural" if voice != "pt-BR-FranciscaNeural" else "pt-BR-AntonioNeural"
    voices_to_try.append(alt_voice)

    clean = clean_text_for_speech(text)
    if not clean:
        return False

    output_path.parent.mkdir(parents=True, exist_ok=True)
    for v in voices_to_try:
        try:
            communicate = edge_tts.Communicate(clean, v)
            await communicate.save(str(output_path))
            if output_path.is_file() and output_path.stat().st_size > 500:
                log.info(f"Edge-TTS gerado com voz {v}")
                return True
        except Exception as exc:
            log.warning(f"Erro no Edge-TTS com {v}: {exc}. Tentando próxima opção...")
    return False


def _generate_narration_segment(
    text: str,
    output_path: Path,
    voice: str = DEFAULT_VOICE
) -> Path | None:
    """Gera áudio para um único segmento de texto via Edge-TTS com fallback para gTTS."""
    # 1. Tenta Edge-TTS (Vozes Neurais de estúdio)
    try:
        success = asyncio.run(_async_generate_speech(text, output_path, voice))
        if success and output_path.is_file() and output_path.stat().st_size > 500:
            log.info(f"Narração neural Edge-TTS gerada com sucesso: {output_path.name}")
            return output_path
    except Exception as exc:
        log.warning(f"Falha no Edge-TTS ({exc}). Acionando fallback gTTS...")

    # 2. Fallback de alta disponibilidade via gTTS (Google Text-to-Speech)
    try:
        from gtts import gTTS
        clean = clean_text_for_speech(text)
        if clean:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            tts = gTTS(text=clean, lang="pt", tld="com.br")
            tts.save(str(output_path))
            if output_path.is_file() and output_path.stat().st_size > 500:
                log.info(f"Narração gerada via fallback gTTS (pt-BR): {output_path.name}")
                return output_path
    except Exception as exc_gtts:
        log.error(f"Falha também no fallback gTTS: {exc_gtts}")

    return None


def generate_narration(
    text: str,
    output_path: Path,
    voice: str = DEFAULT_VOICE
) -> Path | None:
    """
    Gera áudio da narração sincronizado.
    Suporta marcadores solenes de pausa [PAUSE:segundos] intercalando silêncio acústico via FFmpeg.
    """
    if "[PAUSE" not in text:
        return _generate_narration_segment(text, output_path, voice)

    # Divide pelos marcadores de pausa (ex: [PAUSE:1.5] ou [PAUSE])
    raw_parts = re.split(r"\[PAUSE(?::([\d.]+))?\]", text)
    segments: list[str] = []
    pauses: list[float] = []
    idx = 0
    while idx < len(raw_parts):
        seg = (raw_parts[idx] or "").strip()
        segments.append(seg)
        if idx + 1 < len(raw_parts):
            p_val = float(raw_parts[idx + 1]) if raw_parts[idx + 1] else 1.5
            pauses.append(p_val)
            idx += 2
        else:
            idx += 1

    temp_files: list[tuple[Path, float]] = []
    try:
        for s_idx, seg in enumerate(segments):
            if not seg:
                continue
            seg_path = output_path.parent / f"temp_seg_{output_path.stem}_{s_idx}.mp3"
            res = _generate_narration_segment(seg, seg_path, voice)
            if not res or not seg_path.is_file():
                log.warning(f"Falha ao gerar segmento {s_idx} da narração.")
                continue
            pause_sec = pauses[s_idx] if s_idx < len(pauses) else 0.0
            temp_files.append((seg_path, pause_sec))

        if not temp_files:
            return None
        if len(temp_files) == 1:
            temp_files[0][0].replace(output_path)
            return output_path

        # Mescla os segmentos com o silêncio calibrado via FFmpeg
        inputs = []
        filter_parts = []
        concat_inputs = []
        for i, (f_path, pause_sec) in enumerate(temp_files):
            inputs.extend(["-i", str(f_path)])
            concat_inputs.append(f"[{i}:a]")
            if pause_sec > 0 and i < len(temp_files) - 1:
                silence_label = f"[silence{i}]"
                filter_parts.append(f"aevalsrc=0:d={pause_sec}:s=24000:c=mono{silence_label};")
                concat_inputs.append(silence_label)

        total_nodes = len(concat_inputs)
        filter_str = "".join(filter_parts) + f"{''.join(concat_inputs)}concat=n={total_nodes}:v=0:a=1[aout]"
        cmd = [
            "ffmpeg", "-y",
            *inputs,
            "-filter_complex", filter_str,
            "-map", "[aout]",
            "-c:a", "libmp3lame", "-b:a", "192k",
            str(output_path)
        ]
        res_ff = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if res_ff.returncode == 0 and output_path.is_file():
            log.info(f"Narração com pausa solene ({len(temp_files)} segmentos) gerada: {output_path.name}")
            return output_path
        else:
            log.error(f"Erro ao concatenar segmentos com pausa no FFmpeg ({res_ff.stderr[:200]}). Usando fallback linear.")
            clean_text = re.sub(r"\[PAUSE(?::[\d.]+)?\]", ". ", text)
            return _generate_narration_segment(clean_text, output_path, voice)
    finally:
        for f_path, _ in temp_files:
            try:
                f_path.unlink(missing_ok=True)
            except Exception:
                pass


def build_verse_narration_text(
    formatted_text: str,
    reference: str | None = None,
    with_cta: bool | None = None,
    hook_title: str | None = None
) -> str:
    """
    Constrói o texto para narração neural de versículos bíblicos:
    1. Gancho inicial de impacto (Hook) para retenção nos 2 primeiros segundos
    2. Texto do versículo bíblico limpo
    3. Citação da referência bíblica formatada para fala humana
    4. Pausa solene de 1.2s
    5. CTA falado de encerramento para engajamento (Amém nos comentários e compartilhamento)
    """
    from config.settings import ENABLE_AUDIO_CTA, CTA_VERSE_TEXT

    use_cta = ENABLE_AUDIO_CTA if with_cta is None else with_cta

    raw_verse = formatted_text
    ref_found = reference or ""

    if "\n\n—" in raw_verse:
        parts = raw_verse.split("\n\n—", 1)
        raw_verse = parts[0].strip()
        if not ref_found:
            ref_found = parts[1].strip()
    elif "\n—" in raw_verse:
        parts = raw_verse.split("\n—", 1)
        raw_verse = parts[0].strip()
        if not ref_found:
            ref_found = parts[1].strip()

    clean_v = raw_verse.strip(' "\'“”«»')

    spoken_ref = ""
    if ref_found:
        spoken_ref = convert_biblical_references(ref_found.strip())

    narration_parts = []
    if hook_title and hook_title.strip():
        clean_hook = hook_title.strip(' "\'“”«»')
        if not clean_hook.endswith((".", "!", "?")):
            clean_hook += "."
        narration_parts.append(clean_hook)
        narration_parts.append("[PAUSE:0.6]")

    narration_parts.append(clean_v)
    if spoken_ref and spoken_ref.lower() not in clean_v.lower():
        narration_parts.append(spoken_ref)

    if use_cta and CTA_VERSE_TEXT:
        narration_parts.append("[PAUSE:1.2]")
        narration_parts.append(CTA_VERSE_TEXT)

    full = " ".join([p for p in narration_parts if p]).strip()
    full = re.sub(r"\s+", " ", full)
    return full

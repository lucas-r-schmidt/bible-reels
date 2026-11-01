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


def select_voice_profile(source: str = "", reference: str = "", text: str = "") -> tuple[str, str, str]:
    """
    Retorna o perfil ideal de locução neural (voz, rate, pitch) para Edge-TTS:
    - Marianas / Santas / Novenas Marianas: pt-BR-FranciscaNeural (suave e solene, rate=-4%, pitch=-1Hz)
    - Evangelho do Dia / Salmos / Grandes Orações: pt-BR-AntonioNeural (solene e profundo, rate=-5%, pitch=-2Hz)
    - Santo do Dia (narrativa biográfica e testemunho): pt-BR-AntonioNeural (envolvente, rate=-2%, pitch=-1Hz)
    - Padrão geral: pt-BR-AntonioNeural (rate=0%, pitch=0Hz)
    """
    comb = f"{source} {reference} {text}".lower()
    is_marian = any(k in comb for k in ("maria", "senhora", "nossa senhora", "aparecida", "fátima", "fatima", "madonna", "rosário", "rosario"))
    is_female_saint = any(k in comb for k in ("santa ", "beata ", "madre ", "teresa", "rita", "dulce", "clara", "monica", "mônica", "irmã"))

    if is_marian or is_female_saint:
        return "pt-BR-FranciscaNeural", "-4%", "-1Hz"

    if source in ("gospel", "evangelho") or "evangelho" in comb:
        return "pt-BR-AntonioNeural", "-5%", "-2Hz"

    if source in ("prayer", "psalm", "novena") or any(k in comb for k in ("salmo", "oração", "oracao", "novena")):
        return "pt-BR-AntonioNeural", "-5%", "-2Hz"

    if source in ("saint", "santo") or "santo do dia" in comb:
        return "pt-BR-AntonioNeural", "-2%", "-1Hz"

    return DEFAULT_VOICE, "+0%", "+0Hz"


ABBREVIATIONS = {
    "gn": "Gênesis", "gen": "Gênesis", "ex": "Êxodo", "êx": "Êxodo", "lv": "Levítico", "nm": "Números",
    "dt": "Deuteronômio", "js": "Josué", "jz": "Juízes", "rt": "Rute",
    "1sm": "Primeiro Samuel", "2sm": "Segundo Samuel", "1rs": "Primeiro Reis", "2rs": "Segundo Reis",
    "1cr": "Primeiro Crônicas", "2cr": "Segundo Crônicas", "ed": "Esdras", "ne": "Neemias",
    "et": "Ester", "jó": "Jó", "sl": "Salmos", "sal": "Salmos", "pv": "Provérbios", "ec": "Eclesiastes",
    "ecl": "Eclesiastes", "eclo": "Eclesiástico", "si": "Sirácida", "sb": "Sabedoria", "sab": "Sabedoria",
    "ct": "Cantares", "is": "Isaías", "jr": "Jeremias", "lm": "Lamentações", "br": "Baruc", "ez": "Ezequiel",
    "dn": "Daniel", "os": "Oséias", "jl": "Joel", "am": "Amós", "ob": "Obadias",
    "jn": "Jonas", "mq": "Miqueias", "na": "Naum", "hc": "Habacuque", "sf": "Sofonias",
    "ag": "Ageu", "zc": "Zacarias", "ml": "Malaquias",
    "mt": "Mateus", "mat": "Mateus", "mateus": "Mateus",
    "mc": "Marcos", "mar": "Marcos", "marcos": "Marcos",
    "lc": "Lucas", "luc": "Lucas", "lucas": "Lucas",
    "jo": "João", "joao": "João", "joão": "João",
    "at": "Atos", "atos": "Atos", "rm": "Romanos", "rom": "Romanos",
    "1co": "Primeira Coríntios", "1cor": "Primeira Coríntios",
    "2co": "Segunda Coríntios", "2cor": "Segunda Coríntios",
    "gl": "Gálatas", "gal": "Gálatas", "ef": "Efésios", "efe": "Efésios",
    "fp": "Filipenses", "fl": "Filipenses", "fil": "Filipenses",
    "cl": "Colossenses", "col": "Colossenses",
    "1ts": "Primeira Tessalonicenses", "1tes": "Primeira Tessalonicenses",
    "2ts": "Segunda Tessalonicenses", "2tes": "Segunda Tessalonicenses",
    "1tm": "Primeira Timóteo", "1tim": "Primeira Timóteo",
    "2tm": "Segunda Timóteo", "2tim": "Segunda Timóteo",
    "tt": "Tito", "fm": "Filemom",
    "hb": "Hebreus", "heb": "Hebreus", "tg": "Tiago", "tia": "Tiago",
    "1pe": "Primeiro Pedro", "1ped": "Primeiro Pedro",
    "2pe": "Segundo Pedro", "2ped": "Segundo Pedro",
    "1jo": "Primeiro João", "2jo": "Segundo João", "3jo": "Terceiro João", "jd": "Judas",
    "ap": "Apocalipse", "apoc": "Apocalipse"
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
    Suporta padrão com dois-pontos (João 3:16) e padrão litúrgico católico com vírgula (Lc 12,39-48).
    Exemplos:
      'Marcos 10: 2-4'                   -> 'Marcos, capítulo 10, versículos de 2 a 4'
      'Lc 12,39-48'                      -> 'Lucas, capítulo 12, versículos de 39 a 48'
      'Evangelho (Lc 12,39-48) - 21/10'  -> 'Evangelho segundo São Lucas, capítulo 12, versículos de 39 a 48'
      'Salmos 23:1-3'                    -> 'Salmos, capítulo 23, versículos de 1 a 3'
    """
    # 1. Trata títulos litúrgicos como 'Evangelho (Lc 12,39-48) - 21/10'
    m_liturg = re.search(r"Evangelho\s*\((?:([1-3]|1ª|2ª|3ª)?\s*([A-Za-zÀ-ÿ]+)\s*(\d+)\s*[,:]\s*(\d+)(?:[-–—eàa](\d+))?)\)(?:\s*-\s*\d{1,2}/\d{1,2})?", text, re.IGNORECASE)
    if m_liturg:
        pref = m_liturg.group(1) or ""
        bk = m_liturg.group(2)
        c = m_liturg.group(3)
        vs = m_liturg.group(4)
        ve = m_liturg.group(5)
        full_b = expand_book_title(pref, bk)
        saint_b = f"São {full_b}" if full_b in ("Mateus", "Marcos", "Lucas", "João") else full_b
        v_phrase = f"versículos de {vs} a {ve}" if ve else f"versículo {vs}"
        liturg_speech = f"Evangelho segundo {saint_b}, capítulo {c}, {v_phrase}."
        text = text[:m_liturg.start()] + liturg_speech + text[m_liturg.end():]

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

    # Aceita tanto ':' quanto ',' como separador capítulo-versículo
    pattern = re.compile(
        r"\b(?:([1-3]|1ª|2ª|3ª|1º|2º|3º)\s*)?"
        r"([A-Za-zÀ-ÿ]+)\s*"
        r"(\d+)\s*[:,]\s*"
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

    # Caso reste algum padrão numérico de capítulo e versículo isolado: ' 10: 2-4' ou ' 10, 2-4'
    text = re.sub(r"(?<=\s)(\d+)\s*[:,]\s*(\d+)\s*[-–—]\s*(\d+)", r"capítulo \1, versículos de \2 a \3", text)
    text = re.sub(r"(?<=\s)(\d+)\s*[:,]\s*(\d+)", r"capítulo \1, versículo \2", text)

    # Limpa referências remanescentes entre parênteses como '(Lucas, capítulo 12, versículos de 39 a 48.)'
    text = re.sub(r"\(([^()]*capítulo[^()]*)\)", r"\1", text)
    # Limpa datas residuais no final da referência (ex: '- 21/10')
    text = re.sub(r"\s*-\s*\d{1,2}/\d{1,2}\b", "", text)

    return text


def clean_text_for_speech(raw_text: str) -> str:
    """Limpa hashtags e converte referências bíblicas para uma leitura falada humana."""
    # 1. Remove hashtags das redes sociais
    text = re.sub(r"#\S+", "", raw_text)

    # 2. Converte citações bíblicas (ex: Marcos 10: 2-4, Lc 12,39-48) antes de remover traços
    text = convert_biblical_references(text)

    # 3. Transforma quebras de linha em pausas de frase
    text = re.sub(r"\n+", ". ", text)

    # 4. Remove números de versículos litúrgicos embutidos no meio do texto
    # Ex: '39 "Ficai certos:' -> '"Ficai certos:', ': 39 "' -> ': "'
    text = re.sub(r"(?<=\s)\d+\s*(?=[\"“«A-ZÀ-Ú])", "", text)
    text = re.sub(r"(?<=[:—–-])\s*\d+\s*(?=[\"“«A-ZÀ-Ú])", " ", text)

    # 5. Converte intervalos de anos e números (ex: 1515 - 1582 -> 1515 a 1582)
    text = re.sub(r"(?<=\b)(\d{3,4})\s*[-–—]\s*(\d{3,4})(?=\b)", r"\1 a \2", text)
    text = re.sub(r"(?<=\d)\s+[-–—]\s+(?=\d)", " a ", text)

    # 6. Remove traços decorativos restantes
    text = text.replace("—", " ").replace("–", " ")
    text = re.sub(r"(?<!\d)-(?!\d)", " ", text)

    # 7. Normaliza pontuação e espaços múltiplos
    text = re.sub(r"\.+", ".", text)
    text = re.sub(r"\s*,\s*", ", ", text)
    text = re.sub(r"\s*\.\s*", ". ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def format_ass_time(seconds: float) -> str:
    """Converte segundos em string de timestamp ASS (H:MM:SS.cs)."""
    hrs = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    centis = int(round((seconds - int(seconds)) * 100))
    if centis >= 100:
        secs += 1
        centis = 0
    return f"{hrs}:{mins:02d}:{secs:02d}.{centis:02d}"


def split_sentence_into_subtitles(text: str, max_words: int = 8, max_chars: int = 42) -> list[list[str]]:
    """
    Divide a fala em linhas completas o suficiente para transmitir a história,
    sem fragmentar o texto em pequenos pedaços de apenas 3 a 5 palavras.
    """
    words = text.strip().split()
    if not words:
        return []
    chunks: list[list[str]] = []
    curr: list[str] = []
    curr_len = 0
    for w in words:
        break_punct = False
        if curr and len(curr) >= 2 and curr[-1].endswith((",", ";", ":", ".", "!", "?", "—")):
            break_punct = True

        if curr and (break_punct or len(curr) >= max_words or (curr_len + len(w) + 1 > max_chars)):
            chunks.append(curr)
            curr = [w]
            curr_len = len(w)
        else:
            curr.append(w)
            curr_len += len(w) + 1
    if curr:
        chunks.append(curr)
    return chunks


def build_ass_file(sentences: list[tuple[float, float, str]], output_path: Path) -> Path | None:
    """
    Gera arquivo de legendas no padrão ASS (Advanced SubStation Alpha)
    com efeito dinâmico Karaoke e cores litúrgicas (Dourado ativo / Branco inativo).
    """
    header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Karaoke,Montserrat,54,&H002FD4FF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,3.5,1.5,5,90,90,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events: list[str] = []
    for s_start, s_dur, text in sentences:
        clean_s = text.strip()
        if not clean_s:
            continue
        chunks = split_sentence_into_subtitles(clean_s, max_words=8, max_chars=42)
        if not chunks:
            continue

        words = clean_s.split()
        total_sentence_chars = max(1, sum(len(w) for w in words))
        c_start = s_start

        for chunk in chunks:
            chunk_chars = sum(len(w) for w in chunk)
            c_dur = s_dur * (chunk_chars / total_sentence_chars)
            c_end = c_start + c_dur

            total_cs = max(10, int(round(c_dur * 100)))
            w_cs_list: list[int] = []
            for w in chunk:
                w_cs = max(10, int(round((len(w) / max(1, chunk_chars)) * total_cs)))
                w_cs_list.append(w_cs)
            diff = total_cs - sum(w_cs_list)
            if w_cs_list:
                w_cs_list[-1] = max(10, w_cs_list[-1] + diff)

            k_parts = [f"{{\\k{cs}}}{w}" for w, cs in zip(chunk, w_cs_list)]
            k_text = " ".join(k_parts)
            line = f"Dialogue: 0,{format_ass_time(c_start)},{format_ass_time(c_end)},Karaoke,,0,0,0,,{k_text}"
            events.append(line)
            c_start = c_end

    output_path.parent.mkdir(parents=True, exist_ok=True)
    full_content = header + "\n".join(events) + "\n"
    output_path.write_text(full_content, encoding="utf-8")
    log.info(f"Legendas ASS karaoke geradas: {output_path.name} ({len(events)} blocos de texto)")
    return output_path


async def _async_generate_speech(
    text: str,
    output_path: Path,
    voice: str,
    rate: str = "+0%",
    pitch: str = "+0Hz"
) -> tuple[bool, list[tuple[float, float, str]]]:
    voices_to_try = [voice]
    alt_voice = "pt-BR-FranciscaNeural" if voice != "pt-BR-FranciscaNeural" else "pt-BR-AntonioNeural"
    voices_to_try.append(alt_voice)

    clean = clean_text_for_speech(text)
    if not clean:
        return False, []

    output_path.parent.mkdir(parents=True, exist_ok=True)
    for v in voices_to_try:
        try:
            communicate = edge_tts.Communicate(clean, v, rate=rate, pitch=pitch)
            audio = bytearray()
            sentences: list[tuple[float, float, str]] = []
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio.extend(chunk["data"])
                elif chunk["type"] == "SentenceBoundary":
                    s_sec = chunk["offset"] / 10_000_000
                    d_sec = chunk["duration"] / 10_000_000
                    sentences.append((s_sec, d_sec, chunk["text"]))

            if len(audio) > 500:
                output_path.write_bytes(audio)
                log.info(f"Edge-TTS gerado com voz {v} ({len(sentences)} frases capturadas)")
                return True, sentences
        except Exception as exc:
            log.warning(f"Erro no Edge-TTS com {v}: {exc}. Tentando próxima opção...")
    return False, []


def _generate_narration_segment(
    text: str,
    output_path: Path,
    voice: str = DEFAULT_VOICE,
    rate: str = "+0%",
    pitch: str = "+0Hz"
) -> tuple[Path | None, list[tuple[float, float, str]]]:
    """Gera áudio e metadados de sincronia para um segmento via Edge-TTS com fallback para gTTS."""
    # 1. Tenta Edge-TTS (Vozes Neurais com marcação de tempo)
    try:
        success, sentences = asyncio.run(_async_generate_speech(text, output_path, voice, rate=rate, pitch=pitch))
        if success and output_path.is_file() and output_path.stat().st_size > 500:
            log.info(f"Narração neural Edge-TTS gerada com sucesso: {output_path.name}")
            return output_path, sentences
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
                words = clean.split()
                est_dur = max(2.0, len(words) / 2.5)
                sentences = [(0.0, est_dur, clean)]
                return output_path, sentences
    except Exception as exc_gtts:
        log.error(f"Falha também no fallback gTTS: {exc_gtts}")

    return None, []


def _get_audio_duration_seconds(path: Path) -> float:
    """Lê a duração exata do arquivo de áudio via ffprobe."""
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


def generate_narration(
    text: str,
    output_path: Path,
    voice: str = DEFAULT_VOICE,
    ass_output_path: Path | None = None,
    rate: str = "+0%",
    pitch: str = "+0Hz"
) -> Path | None:
    """
    Gera áudio da narração sincronizado e opcionalmente exporta arquivo de legendas ASS.
    Suporta marcadores solenes de pausa [PAUSE:segundos] intercalando silêncio acústico via FFmpeg.
    """
    if "[PAUSE" not in text:
        audio_res, sentences = _generate_narration_segment(text, output_path, voice, rate=rate, pitch=pitch)
        if audio_res and ass_output_path and sentences:
            build_ass_file(sentences, ass_output_path)
        return audio_res

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
    all_sentences: list[tuple[float, float, str]] = []
    t_cursor = 0.0

    try:
        for s_idx, seg in enumerate(segments):
            if not seg:
                continue
            seg_path = output_path.parent / f"temp_seg_{output_path.stem}_{s_idx}.mp3"
            res_path, seg_sentences = _generate_narration_segment(seg, seg_path, voice, rate=rate, pitch=pitch)
            if not res_path or not seg_path.is_file():
                log.warning(f"Falha ao gerar segmento {s_idx} da narração.")
                continue

            seg_dur = _get_audio_duration_seconds(seg_path)
            for s_start, s_dur, s_text in seg_sentences:
                all_sentences.append((t_cursor + s_start, s_dur, s_text))

            pause_sec = pauses[s_idx] if s_idx < len(pauses) else 0.0
            temp_files.append((seg_path, pause_sec))
            t_cursor += seg_dur + pause_sec

        if not temp_files:
            return None

        if len(temp_files) == 1:
            temp_files[0][0].replace(output_path)
            if ass_output_path and all_sentences:
                build_ass_file(all_sentences, ass_output_path)
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
            if ass_output_path and all_sentences:
                build_ass_file(all_sentences, ass_output_path)
            return output_path
        else:
            log.error(f"Erro ao concatenar segmentos com pausa no FFmpeg ({res_ff.stderr[:200]}). Usando fallback linear.")
            clean_text = re.sub(r"\[PAUSE(?::[\d.]+)?\]", ". ", text)
            linear_res, linear_s = _generate_narration_segment(clean_text, output_path, voice, rate=rate, pitch=pitch)
            if linear_res and ass_output_path and linear_s:
                build_ass_file(linear_s, ass_output_path)
            return linear_res
    finally:
        for f_path, _ in temp_files:
            try:
                f_path.unlink(missing_ok=True)
            except Exception:
                pass


def generate_narration_with_subtitles(
    text: str,
    output_audio_path: Path,
    output_ass_path: Path,
    voice: str = DEFAULT_VOICE,
    rate: str = "+0%",
    pitch: str = "+0Hz"
) -> tuple[Path | None, Path | None]:
    """Gera áudio neural e arquivo de legendas ASS karaoke sincronizadas."""
    audio_res = generate_narration(text, output_audio_path, voice=voice, ass_output_path=output_ass_path, rate=rate, pitch=pitch)
    ass_res = output_ass_path if (output_ass_path and output_ass_path.is_file()) else None
    return audio_res, ass_res


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


def build_gospel_narration_text(
    reference: str,
    text: str,
    homily_reflection: str = "",
    celebration: str = "",
    key_passage: str = "",
    concise: bool = True
) -> str:
    """
    Constrói o texto da narração solene para o Evangelho do Dia:
    1. Abertura solene: "Evangelho do Dia. Proclamação do Evangelho de Jesus Cristo segundo São Lucas, capítulo X... Glória a Vós, Senhor."
    2. Texto da Palavra (Conciso de 45-65s para Reels/Shorts/TikTok ou Integral para vídeos longos)
    3. Conclusão: "Palavra da Salvação. Glória a Vós, Senhor."
    4. Homilia / Aplicação prática
    5. Bênção e CTA devocional
    """
    # 1. Normaliza referência e detecta evangelista
    ref_raw = reference.strip()
    m_inner = re.search(r"\(([^)]+)\)", ref_raw)
    clean_ref = m_inner.group(1).strip() if m_inner else ref_raw
    clean_ref = re.sub(r"\s*-\s*\d{1,2}/\d{1,2}", "", clean_ref).strip()

    ref_clean_low = clean_ref.lower()
    evangelist = "São Mateus"
    if "lc" in ref_clean_low or "lucas" in ref_clean_low:
        evangelist = "São Lucas"
    elif "mc" in ref_clean_low or "marcos" in ref_clean_low:
        evangelist = "São Marcos"
    elif "jo" in ref_clean_low or "joão" in ref_clean_low or "joao" in ref_clean_low:
        evangelist = "São João"
    elif "mt" in ref_clean_low or "mateus" in ref_clean_low:
        evangelist = "São Mateus"

    # Converte referência bíblica (ex: Lc 12,39-48 -> Lucas, capítulo 12, versículos de 39 a 48)
    spoken_ref_text = convert_biblical_references(clean_ref).rstrip(".")
    # Se já começar com o nome do livro, remove o nome redundante se for adicionar 'segundo São X'
    book_only = spoken_ref_text.split(",")[0].strip() if "," in spoken_ref_text else ""
    cap_verse_part = spoken_ref_text[len(book_only):].lstrip(", ").strip() if book_only else spoken_ref_text

    if cap_verse_part:
        proclamation_header = f"Evangelho do Dia. Proclamação do Evangelho de Jesus Cristo segundo {evangelist}, {cap_verse_part}."
    else:
        proclamation_header = f"Evangelho do Dia. Proclamação do Evangelho de Jesus Cristo segundo {evangelist}."

    # 2. Define o corpo bíblico proclamado (conciso para Reels/Shorts ou integral)
    full_body = clean_text_for_speech(text)
    if concise:
        if key_passage and key_passage.strip():
            body_to_narrate = clean_text_for_speech(key_passage)
        else:
            # Seleciona de forma inteligente as primeiras 2 a 3 frases mais fortes do ensinamento
            sentences = [s.strip() for s in re.split(r"(?<=[.?!])\s+", full_body) if s.strip()]
            candidate_parts = []
            cur_len = 0
            for s in sentences:
                candidate_parts.append(s)
                cur_len += len(s)
                if cur_len >= 260 and len(candidate_parts) >= 2:
                    break
            body_to_narrate = " ".join(candidate_parts) if candidate_parts else full_body[:320]
    else:
        body_to_narrate = full_body

    parts = [
        proclamation_header,
        "Glória a Vós, Senhor.",
        "[PAUSE:1.0]",
        body_to_narrate,
        "[PAUSE:1.0]",
        "Palavra da Salvação. Glória a Vós, Senhor.",
    ]

    if homily_reflection and homily_reflection.strip():
        parts.append("[PAUSE:1.0]")
        parts.append(f"Reflexão de hoje: {clean_text_for_speech(homily_reflection)}")

    parts.append("[PAUSE:1.2]")
    parts.append("Que a luz do Evangelho guarde seus passos. Escreva Amém nos comentários, deixe sua intenção e compartilhe a Palavra de Deus.")

    full = " ".join(parts).strip()
    return re.sub(r"\s+", " ", full)


def build_prayer_narration_text(
    reference: str,
    text: str,
    hook_title: str = "",
    concise: bool = True
) -> str:
    """
    Monta texto solene de narração neural com pausas para orações clássicas, salmos e novenas.
    Garante tempo de vídeo entre 35s e 55s para alto engajamento no Reels/Shorts/TikTok.
    """
    clean_ref = convert_biblical_references(reference)
    clean_body = clean_text_for_speech(text)

    # Limpa menção de autor ou referência no final do texto
    clean_body = re.sub(r"—\s*[^—]+$", "", clean_body).strip()

    if concise and len(clean_body) > 350:
        sentences = [s.strip() for s in re.split(r"(?<=[.?!])\s+", clean_body) if s.strip()]
        candidate = []
        c_len = 0
        for s in sentences:
            candidate.append(s)
            c_len += len(s)
            if c_len >= 260 and len(candidate) >= 2:
                break
        body_to_narrate = " ".join(candidate) if candidate else clean_body[:320]
    else:
        body_to_narrate = clean_body

    is_psalm = "salmo" in reference.lower()
    parts = []
    if hook_title:
        parts.append(clean_text_for_speech(hook_title) + ".")
        parts.append("[PAUSE:0.8]")

    if is_psalm:
        parts.append(f"Oração com o {clean_ref}. Rezemos juntos pedindo a proteção e a paz de Deus.")
    else:
        parts.append(f"Rezemos juntos: {clean_ref}.")
    parts.append("[PAUSE:1.0]")
    parts.append(body_to_narrate)
    parts.append("[PAUSE:1.0]")
    if is_psalm:
        parts.append("Que este Salmo blinde a sua mente e a sua casa contra todo mal. Escreva Amém nos comentários, deixe seu pedido de oração e compartilhe com quem precisa de paz hoje.")
    else:
        parts.append("Que a paz e a bênção do Senhor repousem sobre a sua casa e toda a sua família. Escreva Amém nos comentários, deixe seu pedido de oração e compartilhe.")

    full = " ".join(parts).strip()
    return re.sub(r"\s+", " ", full)


def build_novena_narration_text(
    reference: str,
    text: str,
    hook_title: str = "",
    concise: bool = True
) -> str:
    """
    Constrói texto de narração para a Novena Litúrgica com a abertura devocional escolhida:
    "{novena_day}º Dia da Novena de {saint_name}. Rezemos juntos pela sua causa mais urgente."
    """
    m_day = re.search(r"\((\d{1,2})[ºoªa]?\s*dia\)", reference, re.IGNORECASE)
    day_str = f"{m_day.group(1)}º" if m_day else ""

    clean_saint = reference.split("(")[0].strip()
    clean_saint = re.sub(r"^novena\s+de\s+", "", clean_saint, flags=re.IGNORECASE).strip()
    if not clean_saint:
        clean_saint = "Santo Intercessor"

    if day_str:
        opening = f"{day_str} Dia da Novena de {clean_saint}. Rezemos juntos pela sua causa mais urgente."
    else:
        opening = f"Novena de {clean_saint}. Rezemos juntos pela sua causa mais urgente."

    clean_body = clean_text_for_speech(text)
    clean_body = re.sub(r"—\s*[^—]+$", "", clean_body).strip()
    clean_body = re.sub(r"^oração\s+do\s+\d+[ºoªa]?\s*dia\s*[:\-\.]*", "", clean_body, flags=re.IGNORECASE).strip()

    if concise and len(clean_body) > 350:
        sentences = [s.strip() for s in re.split(r"(?<=[.?!])\s+", clean_body) if s.strip()]
        candidate = []
        c_len = 0
        for s in sentences:
            candidate.append(s)
            c_len += len(s)
            if c_len >= 260 and len(candidate) >= 2:
                break
        body_to_narrate = " ".join(candidate) if candidate else clean_body[:320]
    else:
        body_to_narrate = clean_body

    parts = [
        opening,
        "[PAUSE:1.0]",
        body_to_narrate,
        "[PAUSE:1.0]",
        f"Que por intercessão de {clean_saint}, o Senhor atenda a sua prece. Escreva Amém e coloque o seu pedido de oração nos comentários. Compartilhe esta bênção."
    ]

    full = " ".join(parts).strip()
    return re.sub(r"\s+", " ", full)

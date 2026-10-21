"""
src/processor/ai_formatter.py
------------------------------
Usa Gemini Flash (Free Tier) com output estruturado JSON.
Formata texto, gera hashtags e cria prompt visual cinematográfico.
"""
import json
import re

import google.generativeai as genai
import requests

from config.settings import GEMINI_API_KEY, GEMINI_MODEL, CONTENT_LANGUAGE, GROQ_API_KEY, GROQ_MODEL
from src.utils.logger import get_logger

log = get_logger(__name__)

_configured = False

def _configure_genai() -> None:
    global _configured
    if not _configured:
        if not GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY não configurada no .env")
        genai.configure(api_key=GEMINI_API_KEY)
        _configured = True

def _build_prompt(reference: str, text: str, theme: str = "general") -> str:
    if theme == "morning":
        theme_directive = """DIRETRIZ DE TEMA MATINAL (06:00):
- Foco em reflexão inspiradora de força, coragem e direcionamento matinal para hashtags e visual_prompt.
- Inclua nas hashtags termos como: bomdia, forca, devocionalmatinal, fe, esperanca, versiculododia.
- O visual_prompt DEVE ser um nascer do sol dourado, raios de luz atravessando montanhas ou floresta, atmosfera revigorante."""
    elif theme == "midday":
        theme_directive = """DIRETRIZ DE TEMA DO MEIO-DIA (12:00):
- Foco em renovação de forças, sabedoria bíblica, perseverança e motivação para continuar o dia com fé.
- Inclua nas hashtags termos como: meiodia, fe, perseveranca, forca, sabedoria, reflexaododia, versiculododia.
- O visual_prompt DEVE ser raios de sol radiantes ao meio-dia sobre montanhas ou campos verdejantes, céu claro e iluminação inspiradora."""
    elif theme == "evening":
        theme_directive = """DIRETRIZ DE TEMA NOTURNO (18:00):
- Foco em serenidade, paz, gratidão e descanso noturno para hashtags e visual_prompt.
- Inclua nas hashtags termos como: boanoite, gratidao, paz, descanso, alivio, oracaodanoite, fe.
- O visual_prompt DEVE ser um entardecer sereno, pôr do sol suave sobre lago calmo ou céu estrelado tranquilo."""
    else:
        theme_directive = "Foco em reflexão bíblica de fé, esperança e paz para hashtags e visual_prompt."

    return f"""Você é um especialista em conteúdo bíblico e cristão para redes sociais (Instagram Reels, TikTok e Kwai).

{theme_directive}

REGRA CRÍTICA E INEGOCIÁVEL DE FIDELIDADE BÍBLICA:
O texto do versículo bíblico NÃO PODE SER ALTERADO, PARAFRASEADO, RESUMIDO OU ADAPTADO POETICAMENTE.
Deve ser 100% FIEL e EXATO ao texto sagrado original da Bíblia fornecido abaixo.
NUNCA invente palavras, nem altere a tradução, nem adicione frases próprias no texto do versículo.

Versículo bíblico:
Referência: {reference}
Texto Sagrado: {text}

Gere um objeto JSON estrito com exatamente as seguintes chaves:
{{
  "hook_title": "Gancho magnético de 3 a 6 palavras impactantes para prender a atenção nos primeiros 2 segundos do Reel (ex: 'Deus tem um recado para você', 'Leia antes de dormir', 'Uma bênção para sua casa', 'Não perca a fé hoje').",
  "formatted_text": "{text}\\n\\n— {reference}",
  "hashtags": ["lista", "de", "10", "a", "15", "hashtags", "sem", "o", "simbolo", "#"],
  "visual_prompt": "Descrição cinematográfica em inglês para fundo de vídeo/imagem (natureza, paisagem serena, sem pessoas, sem texto). Máximo 50 palavras."
}}"""

def format_verse_groq(reference: str, text: str, theme: str = "general") -> dict | None:
    """Fallback usando Groq Cloud API."""
    import os
    from dotenv import load_dotenv
    from config.settings import ROOT_DIR
    load_dotenv(ROOT_DIR / ".env", override=True)

    api_key = os.getenv("GROQ_API_KEY") or GROQ_API_KEY
    model_name = os.getenv("GROQ_MODEL") or GROQ_MODEL or "openai/gpt-oss-120b"

    if not api_key:
        log.warning("GROQ_API_KEY não configurada no .env.")
        return None

    prompt = _build_prompt(reference, text, theme=theme)
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": "Você é um assistente especialista que responde exclusivamente em formato json válido, sem texto adicional."},
            {"role": "user", "content": prompt}
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.7,
        "max_tokens": 1024
    }

    try:
        res = requests.post(url, headers=headers, json=payload, timeout=25)
        if res.status_code != 200:
            log.warning(f"Groq API retornou status {res.status_code}: {res.text[:200]}")
            res.raise_for_status()

        data = res.json()
        content = data["choices"][0]["message"]["content"].strip()
        result = json.loads(content)

        if not all(k in result for k in ("formatted_text", "hashtags", "visual_prompt")):
            log.warning("Chaves ausentes no JSON da Groq.")
            return None

        result["hashtags"] = [
            tag.lstrip("#").strip()
            for tag in result["hashtags"]
            if isinstance(tag, str) and tag.strip()
        ]

        hook = result.get("hook_title", "").strip(' "\'“”«»')
        result["hook_title"] = hook if (hook and len(hook) <= 60) else "UMA PALAVRA PARA SEU CORAÇÃO"

        # Fidelidade bíblica absoluta: o texto bíblico nunca é alterado por paráfrase
        result["formatted_text"] = f"{text.strip()}\n\n— {reference.strip()}"

        log.info(f"Formatado com sucesso via Groq ({model_name}): {reference} ({len(result['hashtags'])} hashtags)")
        return result
    except Exception as exc:
        log.error(f"Erro na Groq API: {exc}")
        return None

def format_verse(reference: str, text: str, theme: str = "general") -> dict | None:
    # 1. Tenta Gemini Flash primeiro
    try:
        _configure_genai()
        prompt = _build_prompt(reference, text, theme=theme)
        model = genai.GenerativeModel(GEMINI_MODEL)
        generation_config = {
            "temperature": 0.7,
            "max_output_tokens": 2048,
            "response_mime_type": "application/json",
        }

        response = model.generate_content(
            prompt,
            generation_config=generation_config,
            request_options={"timeout": 6.0}
        )
        raw = response.text.strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)

        result = json.loads(raw)
        if all(k in result for k in ("formatted_text", "hashtags", "visual_prompt")):
            result["hashtags"] = [
                tag.lstrip("#").strip()
                for tag in result["hashtags"]
                if isinstance(tag, str) and tag.strip()
            ]
            hook = result.get("hook_title", "").strip(' "\'“”«»')
            result["hook_title"] = hook if (hook and len(hook) <= 60) else "UMA PALAVRA PARA SEU CORAÇÃO"
            # Fidelidade bíblica absoluta: o texto bíblico nunca é alterado por paráfrase
            result["formatted_text"] = f"{text.strip()}\n\n— {reference.strip()}"
            log.info(f"Formatado via Gemini: {reference} ({len(result['hashtags'])} hashtags, hook: {result['hook_title']})")
            return result
        else:
            log.warning("Chaves ausentes no retorno do Gemini.")
    except Exception as exc:
        log.warning(f"Gemini falhou ({exc}). Acionando IA de backup Groq...")

    # 2. Fallback automático: Groq Cloud (Llama 3)
    groq_result = format_verse_groq(reference, text, theme=theme)
    if groq_result:
        return groq_result

    log.error("Todas as APIs de IA falharam (Gemini e Groq). Usando template local.")
    return None


def format_saint_post(reference: str, text: str, saint_metadata: dict | None = None, is_eve: bool = True) -> dict:
    """
    Formata publicação dedicada ao 'Santo do Dia'.
    Se is_eve=True (publicação na véspera às 20:30), a legenda convida os fiéis para
    a celebração do dia seguinte (ex: 'Amanhã, 15 de Outubro, celebramos...').
    """
    saint = saint_metadata or {}
    saint_name = saint.get("name") or reference.split("(")[0].strip()
    saint_title = saint.get("title", "Intercessor da Fé")
    history_ctx = saint.get("history", "")
    prayer_ctx = saint.get("prayer", "")
    date_str = saint.get("date_str", "")

    eve_instruction = (
        f"Este post celebra a memória litúrgica de {saint_name} ({date_str}). A introdução da legenda deve saudar os devotos celebrando {saint_name} ({date_str}) de forma atemporal e reverente (ex: '🕊️ Santo do Dia: {saint_name} ({date_str}) — Celebramos a memória litúrgica...'), preparando o coração para a oração e a bênção. Evite palavras restritivas como 'amanhã' para que a publicação seja perfeita tanto na vigília noturna (YouTube/TikTok) quanto na manhã litúrgica (Instagram)."
        if date_str else
        f"Este post celebra a memória litúrgica de {saint_name}."
    )

    # Monta prompt especializado para redes sociais
    prompt = f"""Você é um especialista em conteúdo católico devocional e engajamento para Instagram Reels, TikTok e Kwai.
Crie um post completo para a solenidade do Santo:
Santo: {saint_name}
Data Litúrgica: {date_str}
Título: {saint_title}
Citação/Oração Central: {text}
Contexto Histórico: {history_ctx}
Oração Tradicional: {prayer_ctx}
Instrução Temporal: {eve_instruction}

Retorne EXCLUSIVAMENTE um objeto JSON estrito com exatamente as seguintes chaves:
{{
  "card_text": "{text}\\n\\n— {saint_name}",
  "caption": "Legenda completa e formatada com emojis respeitosos. DEVE conter: 1) Título marcante indicando o Santo e a data litúrgica; 2) História concisa e inspiradora de 2 parágrafos; 3) Oração poderosa; 4) Chamada para reflexão/comentário (ex: Deixe seu Amém); 5) Bloco de hashtags no final.",
  "hashtags": ["santododia", "fe", "oracao", "catolicismo", "igrejacatolica", "reelsbrasil", "devocional"],
  "visual_prompt": "Cinematic sacred and reverent scene, warm golden divine light rays, sacred art style, peaceful and majestic holy atmosphere, serene church architecture or soft clouds with subtle halo illumination, no text, no modern objects, 8k resolution"
}}"""

    # 1. Tenta Gemini Flash
    try:
        _configure_genai()
        model = genai.GenerativeModel(GEMINI_MODEL)
        generation_config = {
            "temperature": 0.6,
            "max_output_tokens": 2048,
            "response_mime_type": "application/json",
        }
        res = model.generate_content(prompt, generation_config=generation_config)
        raw = res.text.strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        data = json.loads(raw)

        if data.get("caption") and data.get("visual_prompt"):
            hashtags = [
                tag.lstrip("#").strip()
                for tag in data.get("hashtags", [])
                if isinstance(tag, str) and tag.strip()
            ]
            card_txt = f"{text.strip()}\n\n— {saint_name}"
            log.info(f"Post do Santo do Dia ({saint_name}) formatado com sucesso via Gemini.")
            return {
                "hook_title": f"SANTO DO DIA: {saint_name.upper()}",
                "formatted_text": card_txt,
                "caption": data["caption"].strip(),
                "hashtags": hashtags,
                "visual_prompt": data["visual_prompt"].strip()
            }
    except Exception as exc:
        log.warning(f"Falha ao formatar Santo do Dia via Gemini ({exc}). Tentando fallback...")

    # 2. Fallback determinístico de alta fidelidade
    clean_saint_tag = re.sub(r"[^a-zA-Z0-9]", "", saint_name.lower())
    hashtags = [
        "santododia", clean_saint_tag, "catolicismo", "oracao", "fe",
        "igrejacatolica", "devocional", "bencaos", "reelsbrasil", "cristao"
    ]
    tags_line = " ".join([f"#{t}" for t in hashtags])

    date_label = f"({date_str})" if date_str else ""
    header_title = f"🕊️ Memória Litúrgica: {saint_name} {date_label}".strip()
    intro_lead = f"Amanhã, a Igreja celebra com reverência o testemunho de fé de {saint_name}." if is_eve else f"Hoje a Igreja celebra com reverência o testemunho de fé de {saint_name}."

    history_text = history_ctx or f"{intro_lead} Modelo de virtude, amor a Deus e entrega aos irmãos."
    prayer_text = prayer_ctx or f"Ó Deus, que nos destes em {saint_name} um exemplo admirável de fé e caridade, concedei-nos por sua intercessão a graça de permanecermos firmes na esperança. Amém."

    caption = (
        f"{header_title}\n"
        f"✨ {saint_title}\n\n"
        f"📖 Um pouco de sua história:\n"
        f"{history_text}\n\n"
        f"🙏 Oração:\n"
        f"\"{prayer_text}\"\n\n"
        f"Deixe seu \"Amém\" nos comentários e compartilhe esta bênção! 🙏\n\n"
        f"{tags_line}"
    )

    card_text = f"{text.strip()}\n\n— {saint_name}"
    visual_prompt = (
        f"Cinematic sacred art of {saint_name}, holy golden celestial rays, ethereal reverent atmosphere, "
        f"divine light, peaceful and sacred ambiance, baroque oil painting masterpiece, no modern elements"
    )

    log.info(f"Usando template de alta fidelidade para Santo do Dia ({saint_name}).")
    return {
        "hook_title": f"SANTO DO DIA: {saint_name.upper()}",
        "formatted_text": card_text,
        "caption": caption,
        "hashtags": hashtags,
        "visual_prompt": visual_prompt
    }
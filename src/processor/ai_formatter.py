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
    elif theme == "ansiedade":
        theme_directive = """DIRETRIZ DE CURA DA ANSIEDADE E AFLIÇÃO:
- O gancho (hook_title) DEVE interromper o padrão com empatia para quem está angustiado (ex: 'Se você acordou angustiado hoje, pare e ouça', 'Deus acalma a sua ansiedade agora', 'Respire fundo e receba esta paz').
- Inclua nas hashtags: ansiedade, pazinterior, alivio, fe, deusnocontrole, confianca."""
    elif theme == "cansaco":
        theme_directive = """DIRETRIZ PARA CANSAÇO E SOBRECARGA:
- O gancho (hook_title) DEVE acolher a dor silenciosa de quem está esgotado (ex: 'Deus viu as lágrimas que você engoliu em silêncio', 'Quando o peso for demais, lembre-se disso', 'Para quem não tem mais forças hoje').
- Inclua nas hashtags: cansaco, forca, renovacao, descansaemdeus, perseveranca."""
    elif theme == "medo":
        theme_directive = """DIRETRIZ CONTRA O MEDO E INCERTEZA:
- O gancho (hook_title) DEVE gerar segurança inabalável (ex: 'Não tenha medo do amanhã: Deus já está lá', 'Deus assume o comando da sua causa hoje', 'Você não está desamparado nesta batalha').
- Inclua nas hashtags: naotemas, coragem, vitoria, protecaodivina, fe."""
    elif theme == "familia":
        theme_directive = """DIRETRIZ PARA FAMÍLIA E LAR:
- O gancho (hook_title) DEVE blindar o lar e os filhos (ex: '30 segundos para blindar seu lar contra todo mal', 'Receba esta bênção sobre a sua casa hoje', 'Nenhum mal prevalecerá contra a sua família').
- Inclua nas hashtags: familia, lardepaz, bencaodivina, casadeoracao, amorfamiliar."""
    elif theme == "sunday_blessing":
        theme_directive = """DIRETRIZ DE DOMINGO (BÊNÇÃO DA SEMANA):
- O gancho (hook_title) DEVE abençoar a semana que se inicia (ex: 'Receba a bênção de Deus para a sua nova semana', 'Antes de começar a semana, consagre seus passos', 'Uma semana de vitórias começa com esta palavra').
- Inclua nas hashtags: felizdomingo, bencaodasemana, diadosenhor, fe, gratidao."""
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
  "hook_title": "Gancho magnético de 4 a 8 palavras para os PRIMEIROS 3 SEGUNDOS do vídeo. Use interrupção de padrão, acolhimento de dor ou promessa concreta (ex: 'Não continue seu dia sem ouvir isso', 'Se seu coração está pesado, ouça agora', '30 segundos para blindar sua casa'). NUNCA use frases batidas como 'Deus tem um recado para você', 'Leia antes de dormir' ou 'Uma palavra para seu coração'.",
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
    if not date_str:
        date_match = re.search(r"\((\d{1,2}/\d{1,2})\)", reference)
        if date_match:
            date_str = date_match.group(1)

    eve_instruction = (
        f"Este post celebra a memória litúrgica de {saint_name} ({date_str}). A introdução da legenda deve saudar os devotos celebrando {saint_name} ({date_str}) de forma atemporal e reverente (ex: '🕊️ Santo do Dia: {saint_name} ({date_str}) — Celebramos a memória litúrgica...'), preparando o coração para a oração e a bênção. Evite palavras restritivas como 'amanhã' para que a publicação seja perfeita tanto na vigília noturna (YouTube/TikTok) quanto na manhã litúrgica (Instagram)."
        if date_str else
        f"Este post celebra a memória litúrgica de {saint_name}."
    )

    # Monta prompt especializado para redes sociais
    prompt = f"""Você é um especialista em conteúdo católico devocional e historiador para Instagram Reels, TikTok e Kwai.
Crie um post completo para a memória litúrgica do Santo do Dia:
Santo: {saint_name}
Data Litúrgica: {date_str}
Título/Epíteto: {saint_title}
Citação/Lema: {text}
Contexto Histórico e Biografia: {history_ctx}
Oração Tradicional: {prayer_ctx}
Instrução Temporal: {eve_instruction}

OBJETIVO CRÍTICO DA LEGENDA (CAPTION):
A legenda DEVE ser primordialmente focada em CONTAR A HISTÓRIA DE VIDA DE {saint_name} de forma rica, inspiradora e detalhada, narrando sua origem, vocação, testemunho, milagres ou atos de santidade e legado de fé, utilizando como base as informações do Contexto Histórico acima.

Estrutura OBRIGATÓRIA da chave "caption":
1) Título marcante de abertura:
🕊️ Santo do Dia: {saint_name} ({date_str}) — {saint_title}

2) A História de {saint_name} (seção principal da legenda):
Contar com riqueza de detalhes a trajetória de vida, feitos históricos e santidade de {saint_name} (2 a 3 parágrafos envolventes e inspiradores).

3) Oração de Intercessão:
Oração solene dedicada a {saint_name} terminando com Amém.

4) Chamada de Fé (CTA):
"Deixe o seu 'Amém' nos comentários e peça a intercessão de {saint_name} para sua vida e família! 🙏✨"

5) Bloco de hashtags no final.

Retorne EXCLUSIVAMENTE um objeto JSON estrito com exatamente as seguintes chaves:
{{
  "hook_title": "Gancho magnético de 4 a 8 palavras para os PRIMEIROS 3 SEGUNDOS do vídeo despertando curiosidade biográfica e fé inabalável (ex: 'O que esse santo fez vai te dar forças hoje', 'A história secreta deste santo da sua causa', 'Antes de desistir hoje, conheça a história dele'). NUNCA use rótulos jornalísticos como 'SANTO DO DIA: NOME'.",
  "card_text": "{text}\\n\\n— {saint_name}",
  "caption": "Texto completo da legenda seguindo rigorosamente a estrutura acima, narrando a história de vida do santo com profundidade e reverência.",
  "hashtags": ["santododia", "fe", "oracao", "catolicismo", "igrejacatolica", "reelsbrasil", "devocional"],
  "visual_prompt": "Cinematic sacred and reverent scene of {saint_name}, warm golden divine light rays, sacred art style, peaceful and majestic holy atmosphere, serene church architecture or soft clouds with subtle halo illumination, no text, no modern objects, 8k resolution"
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
        res = model.generate_content(
            prompt,
            generation_config=generation_config,
            request_options={"timeout": 10.0}
        )
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
            raw_h = data.get("hook_title", "").strip(' "\'“”«»')
            final_hook = raw_h if (raw_h and len(raw_h) <= 70 and not raw_h.lower().startswith("santo do dia")) else f"O QUE {saint_name.upper()} FEZ EM VIDA VAI MUDAR SUA FÉ HOJE"
            log.info(f"Post do Santo do Dia ({saint_name}) formatado com sucesso via Gemini (hook: {final_hook}).")
            return {
                "hook_title": final_hook,
                "formatted_text": card_txt,
                "caption": data["caption"].strip(),
                "hashtags": hashtags,
                "visual_prompt": data["visual_prompt"].strip()
            }
    except Exception as exc:
        log.warning(f"Falha ao formatar Santo do Dia via Gemini ({exc}). Tentando Groq...")

    # 2. Tenta Groq Fallback
    try:
        from config.settings import GROQ_API_KEY, GROQ_MODEL
        if GROQ_API_KEY:
            res_groq = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
                json={
                    "model": GROQ_MODEL or "llama-3.1-8b-instant",
                    "messages": [
                        {"role": "system", "content": "Responda exclusivamente em formato JSON estrito."},
                        {"role": "user", "content": prompt},
                    ],
                    "response_format": {"type": "json_object"},
                    "temperature": 0.3,
                },
                timeout=12,
            )
            if res_groq.ok:
                data_g = json.loads(res_groq.json()["choices"][0]["message"]["content"])
                if data_g.get("caption") and data_g.get("visual_prompt"):
                    hashtags = [
                        tag.lstrip("#").strip()
                        for tag in data_g.get("hashtags", [])
                        if isinstance(tag, str) and tag.strip()
                    ]
                    raw_h = data_g.get("hook_title", "").strip(' "\'“”«»')
                    final_hook = raw_h if (raw_h and len(raw_h) <= 70 and not raw_h.lower().startswith("santo do dia")) else f"O QUE {saint_name.upper()} FEZ EM VIDA VAI MUDAR SUA FÉ HOJE"
                    log.info(f"Post do Santo do Dia ({saint_name}) formatado com sucesso via Groq (hook: {final_hook}).")
                    return {
                        "hook_title": final_hook,
                        "formatted_text": f"{text.strip()}\n\n— {saint_name}",
                        "caption": data_g["caption"].strip(),
                        "hashtags": hashtags,
                        "visual_prompt": data_g["visual_prompt"].strip()
                    }
    except Exception as exc:
        log.warning(f"Falha ao formatar Santo do Dia via Groq ({exc}). Usando template determinístico...")

    # 3. Fallback determinístico de alta fidelidade contando a história do santo
    clean_saint_tag = re.sub(r"[^a-zA-Z0-9]", "", saint_name.lower())
    hashtags = [
        "santododia", clean_saint_tag, "catolicismo", "oracao", "fe",
        "igrejacatolica", "devocional", "bencaos", "reelsbrasil", "cristao"
    ]
    tags_line = " ".join([f"#{t}" for t in hashtags])

    date_label = f"({date_str})" if date_str else ""
    header_title = f"🕊️ Santo do Dia: {saint_name} {date_label}".strip()
    intro_lead = f"Hoje a Igreja celebra com profunda reverência o testemunho de fé e a santidade de {saint_name}."

    history_text = history_ctx or f"{intro_lead} Um luminoso exemplo de virtude, fidelidade ao Evangelho e entrega total a Deus."
    prayer_text = prayer_ctx or f"Ó Deus, que nos destes em {saint_name} um exemplo admirável de fé e caridade, concedei-nos por sua intercessão a graça de permanecermos firmes na esperança. Amém."

    caption = (
        f"{header_title} — {saint_title}\n\n"
        f"📖 Conheça a história de {saint_name}:\n\n"
        f"{history_text}\n\n"
        f"🙏 Oração de Intercessão:\n"
        f"\"{prayer_text}\"\n\n"
        f"Deixe o seu \"Amém\" nos comentários e peça a intercessão de {saint_name} para sua vida e família! 🙏✨\n\n"
        f"{tags_line}"
    )

    card_text = f"{text.strip()}\n\n— {saint_name}"
    visual_prompt = (
        f"Cinematic sacred art of {saint_name}, holy golden celestial rays, ethereal reverent atmosphere, "
        f"divine light, peaceful and sacred ambiance, baroque oil painting masterpiece, no modern elements"
    )

    log.info(f"Usando template de alta fidelidade para Santo do Dia ({saint_name}).")
    return {
        "hook_title": f"O QUE {saint_name.upper()} FEZ EM VIDA VAI TE DAR FORÇAS HOJE",
        "formatted_text": card_text,
        "caption": caption,
        "hashtags": hashtags,
        "visual_prompt": visual_prompt
    }


def format_gospel_post(reference: str, text: str, celebration: str = "") -> dict:
    """
    Formata o Evangelho do Dia para publicação em vídeo/carrossel.
    Garante fidelidade 100% ao texto do Evangelho e gera reflexão pastoral/homilia concisa.
    Extrai o 'key_passage' para exibição visual nítida e narração dinâmica (50-65s) para Reels/Shorts.
    """
    # Limpa referência para evitar duplicações como 'Evangelho (Evangelho (Lc 12...))'
    m_inner = re.search(r"\(([^)]+)\)", reference)
    clean_ref = m_inner.group(1).strip() if m_inner else reference.strip()
    clean_ref = re.sub(r"\s*-\s*\d{1,2}/\d{1,2}", "", clean_ref).strip()

    prompt = f"""Você é um teólogo e liturgista católico especialista em redes sociais cristãs (Instagram Reels, TikTok e Kwai).
Abaixo está o Evangelho Oficial do Dia proclamado pela Igreja Católica:
Celebração Litúrgica: {celebration}
Referência Bíblica: {clean_ref}
Texto Sagrado:
{text}

REGRA CRÍTICA INEGOCIÁVEL:
NUNCA altere ou parafraseie o texto bíblico do Evangelho.

Gere um objeto JSON estrito com as seguintes chaves:
{{
  "hook_title": "Gancho magnético de 4 a 8 palavras para os PRIMEIROS 3 SEGUNDOS do vídeo. Use urgência e acolhimento direto da dor (ex: 'Não continue seu dia sem ouvir isso hoje', 'Se o seu coração está pesado, ouça Jesus agora', 'Você precisava ouvir essa passagem hoje', 'Antes de continuar seu dia, receba esta palavra'). NUNCA use rótulos como 'O Evangelho do Dia', 'Palavra de Salvação' ou 'Evangelho de Hoje'.",
  "key_passage": "O trecho ou versículo central mais impactante do Evangelho lido (2 a 4 versículos exatos, cópia 100% fiel do texto acima, sem alterar nenhuma palavra, máximo 300 caracteres) para ser exibido na tela do vídeo.",
  "homily_reflection": "Uma reflexão pastoral/homilia concisa e profunda de 1 parágrafo (máximo 200 caracteres) aplicando a mensagem de Jesus para a vida diária dos fiéis hoje.",
  "caption": "Legenda completa para redes sociais contendo: 1) Título solene '📖 Evangelho do Dia — {clean_ref}'; 2) Celebração se houver; 3) Texto completo do Evangelho; 4) Reflexão pastoral/homilia; 5) Chamada devocional ('Deixe seu Amém e compartilhe a Boa Nova'); 6) Bloco de hashtags católicas.",
  "hashtags": ["evangelhododia", "palavradosenhor", "liturgiadiaria", "catolicismo", "fe", "evangelho", "reelsbrasil", "cristao", "bencaos"],
  "visual_prompt": "Cinematic holy bible on altar, soft golden divine sunbeams, ancient reverent church ambiance, sacred illumination, peaceful and sacred, 8k"
}}"""

    # 1. Tenta Gemini
    try:
        _configure_genai()
        model = genai.GenerativeModel(GEMINI_MODEL)
        res = model.generate_content(
            prompt,
            generation_config={"temperature": 0.5, "response_mime_type": "application/json"},
            request_options={"timeout": 8.0}
        )
        raw = res.text.strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        data = json.loads(raw)
        if data.get("caption") and data.get("hook_title"):
            hashtags = [t.lstrip("#").strip() for t in data.get("hashtags", []) if isinstance(t, str) and t.strip()]
            key_p = data.get("key_passage", "").strip() or text.strip()[:300]
            raw_g = data["hook_title"].strip(' "\'“”«»')
            final_ghook = raw_g if (raw_g and len(raw_g) <= 70 and not any(k in raw_g.lower() for k in ("evangelho do dia", "palavra de salvação"))) else "NÃO CONTINUE SEU DIA SEM OUVIR ISSO HOJE"
            return {
                "hook_title": final_ghook,
                "formatted_text": f"{text.strip()}\n\n— {clean_ref}",
                "key_passage": key_p,
                "homily_reflection": data.get("homily_reflection", "").strip(),
                "caption": data["caption"].strip(),
                "hashtags": hashtags,
                "visual_prompt": data.get("visual_prompt", "Cinematic holy bible with soft sunlight on altar")
            }
    except Exception as exc:
        log.warning(f"Falha ao formatar Evangelho via Gemini ({exc}). Tentando Groq...")

    # 2. Tenta Groq
    try:
        if GROQ_API_KEY:
            res = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
                json={
                    "model": GROQ_MODEL or "llama-3.1-8b-instant",
                    "messages": [
                        {"role": "system", "content": "Responda exclusivamente JSON estrito."},
                        {"role": "user", "content": prompt}
                    ],
                    "response_format": {"type": "json_object"},
                    "temperature": 0.3
                },
                timeout=12
            )
            if res.ok:
                data = json.loads(res.json()["choices"][0]["message"]["content"])
                if data.get("caption") and data.get("hook_title"):
                    hashtags = [t.lstrip("#").strip() for t in data.get("hashtags", []) if isinstance(t, str) and t.strip()]
                    key_p = data.get("key_passage", "").strip() or text.strip()[:300]
                    raw_g = data["hook_title"].strip(' "\'“”«»')
                    final_ghook = raw_g if (raw_g and len(raw_g) <= 70 and not any(k in raw_g.lower() for k in ("evangelho do dia", "palavra de salvação"))) else "NÃO CONTINUE SEU DIA SEM OUVIR ISSO HOJE"
                    return {
                        "hook_title": final_ghook,
                        "formatted_text": f"{text.strip()}\n\n— {clean_ref}",
                        "key_passage": key_p,
                        "homily_reflection": data.get("homily_reflection", "").strip(),
                        "caption": data["caption"].strip(),
                        "hashtags": hashtags,
                        "visual_prompt": data.get("visual_prompt", "Cinematic holy bible with soft sunlight on altar")
                    }
    except Exception as exc:
        log.warning(f"Falha ao formatar Evangelho via Groq ({exc}).")

    # 3. Fallback determinístico
    clean_text = text.strip()
    sentences = [s.strip() for s in re.split(r"(?<=[.?!])\s+", clean_text) if s.strip()]
    key_fallback = " ".join(sentences[:2]) if len(sentences) >= 2 else clean_text[:280]
    celebration_line = f"✨ {celebration}\n\n" if celebration else ""
    caption = (
        f"📖 Evangelho do Dia — {clean_ref}\n"
        f"{celebration_line}"
        f"\"{clean_text}\"\n\n"
        f"🙏 Reflexão: A Palavra do Senhor nos convida a manter o coração vigilante e acolher a Sua misericórdia no dia a dia.\n\n"
        f"Deixe seu \"Amém\" nos comentários e compartilhe esta mensagem sagrada! 🙏\n\n"
        f"#evangelhododia #liturgiadiaria #fe #jesus #palavradedeus #catolicismo #reelsbrasil"
    )
    return {
        "hook_title": "NÃO CONTINUE SEU DIA SEM OUVIR ISSO HOJE",
        "formatted_text": f"{clean_text}\n\n— {clean_ref}",
        "key_passage": key_fallback,
        "homily_reflection": "A Palavra do Senhor nos convida a manter o coração vigilante e acolher a Sua misericórdia hoje.",
        "caption": caption,
        "hashtags": ["evangelhododia", "liturgiadiaria", "fe", "jesus", "palavradedeus", "catolicismo"],
        "visual_prompt": "Cinematic holy bible with soft divine illumination on altar"
    }


def format_community_prayer_post(comments_list: list[dict[str, Any]]) -> dict:
    """
    Formata uma publicação de Oração Comunitária baseada nos pedidos e nomes de seguidores reais.
    """
    authors = []
    for c in comments_list:
        name = (c.get("author_name") or "").strip()
        # Limpa @ ou caracteres estranhos
        name = re.sub(r"^@+", "", name).strip()
        if name and name not in authors and len(name) <= 25:
            authors.append(name)

    names_str = ", ".join(authors[:6]) if authors else "nossa comunidade e famílias"

    prompt = f"""Você é um sacerdote/pastor dedicando um momento especial de intercessão e oração pelos inscritos da página.
Nomes de inscritos que pediram oração recentemente: {names_str}.

Gere um objeto JSON estrito com:
{{
  "hook_title": "ORAÇÃO PELOS NOSSOS IRMÃOS",
  "prayer_text": "Oração solene de intercessão e súplica a Deus abençoando nominalmente os irmãos ({names_str}) e todas as famílias da nossa comunidade (máximo 4 linhas devocionais com Amém).",
  "caption": "Legenda afetuosa e inspiradora mencionando que estivemos em oração pelas intenções de {names_str} e de todos os inscritos. Convide os seguidores a deixarem seus novos pedidos nos comentários. Termine com hashtags de oração e fé.",
  "hashtags": ["oracaododia", "intercessao", "comunidadedefe", "oracao", "familia", "fe", "reelsbrasil", "amigosdedeus"],
  "visual_prompt": "Warm candle glowing softly in peaceful sanctuary, hands united in prayer, divine golden ambient light, peaceful and sacred"
}}"""

    # 1. Tenta Gemini
    try:
        _configure_genai()
        model = genai.GenerativeModel(GEMINI_MODEL)
        res = model.generate_content(
            prompt,
            generation_config={"temperature": 0.6, "response_mime_type": "application/json"},
            request_options={"timeout": 7.0}
        )
        data = json.loads(res.text.strip())
        if data.get("prayer_text") and data.get("caption"):
            hashtags = [t.lstrip("#").strip() for t in data.get("hashtags", []) if isinstance(t, str) and t.strip()]
            return {
                "hook_title": "ORAÇÃO PELOS NOSSOS IRMÃOS",
                "formatted_text": f"{data['prayer_text'].strip()}\n\n— Intenções de {names_str}",
                "caption": data["caption"].strip(),
                "hashtags": hashtags,
                "visual_prompt": data.get("visual_prompt", "Warm candle glowing softly in peaceful sanctuary")
            }
    except Exception as exc:
        log.warning(f"Falha ao formatar oração comunitária via Gemini ({exc}).")

    fallback_prayer = (
        f"Senhor Jesus, nós colocamos em Vossas mãos as vidas, lares e aflições de {names_str} "
        f"e de todos os nossos irmãos que nos acompanham. Que a Tua paz repouse sobre cada família e que nenhuma lágrima "
        f"seja em vão. Derrama Tuas bênçãos e dá-nos a vitória pela fé. Amém."
    )
    caption = (
        f"🙏 Momento de Oração Comunitária pelos Nossos Irmãos\n\n"
        f"Hoje nossa oração sobe aos Céus de modo especial por: {names_str} e por todas as intenções do nosso canal.\n\n"
        f"\"{fallback_prayer}\"\n\n"
        f"Deixe o seu nome e seu pedido de oração nos comentários! Estaremos rezando por você na próxima oração comunitária. 🙏✨\n\n"
        f"#oracaododia #intercessao #fe #deuscuidadenois #oracao #comunidadedefe #reelsbrasil"
    )
    return {
        "hook_title": "ORAÇÃO PELOS NOSSOS IRMÃOS",
        "formatted_text": f"{fallback_prayer}\n\n— Intenções da Comunidade",
        "caption": caption,
        "hashtags": ["oracaododia", "intercessao", "fe", "oracao", "comunidadedefe"],
        "visual_prompt": "Warm candle glowing softly in peaceful sanctuary, hands united in prayer"
    }


def format_novena_post(novena_meta: dict[str, Any]) -> dict:
    """
    Formata publicação seriada de Novena Litúrgica (Dia 1 a 9).
    """
    saint_name = novena_meta.get("saint_name", "Santo Intercessor")
    novena_day = novena_meta.get("novena_day", 1)
    total_days = novena_meta.get("total_days", 9)
    feast_date = novena_meta.get("feast_date", "")
    feast_title = novena_meta.get("feast_title", "Memória Solene")
    s_data = novena_meta.get("saint_data", {})
    prayer_text = s_data.get("prayer", "")
    history_ctx = s_data.get("history", "")

    clean_saint_tag = re.sub(r"[^a-zA-Z0-9]", "", saint_name.lower())
    clean_saint_tag = clean_saint_tag or "novena"

    prompt = f"""Você é um editor litúrgico católico e especialista em redes sociais devocionais.
Crie um post para a Novena Litúrgica:
Santo: {saint_name}
Dia da Novena: {novena_day}º Dia de {total_days}
Festa Solene em: {feast_date} ({feast_title})
Oração Tradicional: {prayer_text}
Contexto Histórico: {history_ctx}

ESTRUTURA OBRIGATÓRIA DA LEGENDA:
1) Título marcante: 🕊️ Novena de {saint_name} — {novena_day}º Dia (Festa em {feast_date})
2) Meditação do Dia: 1 parágrafo profundo sobre a virtude a ser praticada neste {novena_day}º dia (ex: fé, perseverança, confiança, caridade) à luz do testemunho de {saint_name}.
3) Oração Oficial da Novena: Prece fervorosa clamando a intercessão de {saint_name}.
4) Chamada Devocional (CTA): "Comente 'Eu Creio' e escreva sua intenção neste {novena_day}º Dia! Reze conosco até a grande festa em {feast_date}. Compartilhe com sua família! 🙏✨"
5) Hashtags no final.

Retorne EXCLUSIVAMENTE um JSON estrito:
{{
  "hook_title": "Gancho magnético de 4 a 8 palavras para os PRIMEIROS 3 SEGUNDOS do vídeo destacando perseverança e resposta à dor (ex: 'Não desista hoje: o {novena_day}º dia é onde a vitória começa', 'Entregue sua causa aflita neste {novena_day}º dia', 'Deus viu as suas lágrimas: reze o {novena_day}º dia'). NUNCA use rótulos como 'NOVENA: {novena_day}º DIA'.",
  "card_text": "Oração do {novena_day}º Dia\\n\\n{prayer_text}\\n\\n— Festa em {feast_date}",
  "caption": "Legenda completa formatada conforme estrutura acima.",
  "hashtags": ["novena", "{clean_saint_tag}", "fe", "oracao", "santododia", "catolicismo", "milagres", "reelsbrasil"],
  "visual_prompt": "Cinematic sacred altar with nine burning candles, reverent golden divine rays illuminating sacred statue or image of {saint_name}, peaceful church atmosphere, 8k resolution"
}}"""

    try:
        _configure_genai()
        model = genai.GenerativeModel(GEMINI_MODEL)
        res = model.generate_content(
            prompt,
            generation_config={"temperature": 0.6, "response_mime_type": "application/json"},
            request_options={"timeout": 8.0}
        )
        data = json.loads(res.text.strip())
        if data.get("caption") and data.get("card_text"):
            tags = [t.lstrip("#").strip() for t in data.get("hashtags", []) if isinstance(t, str) and t.strip()]
            raw_h = data.get("hook_title", "").strip(' "\'“”«»')
            final_h = raw_h if (raw_h and len(raw_h) <= 70 and not raw_h.lower().startswith("novena:")) else f"NÃO DESISTA HOJE: O {novena_day}º DIA É ONDE A GRAÇA COMEÇA"
            return {
                "hook_title": final_h,
                "formatted_text": data["card_text"].strip(),
                "caption": data["caption"].strip(),
                "hashtags": tags,
                "visual_prompt": data.get("visual_prompt", f"Cinematic sacred altar with candles, holy art of {saint_name}")
            }
    except Exception as exc:
        log.warning(f"Falha ao formatar novena via Gemini ({exc}). Tentando Groq...")

    # 2. Tenta Groq
    try:
        from config.settings import GROQ_API_KEY, GROQ_MODEL
        if GROQ_API_KEY:
            res_groq = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
                json={
                    "model": GROQ_MODEL or "llama-3.1-8b-instant",
                    "messages": [
                        {"role": "system", "content": "Responda exclusivamente JSON estrito."},
                        {"role": "user", "content": prompt}
                    ],
                    "response_format": {"type": "json_object"},
                    "temperature": 0.6
                },
                timeout=10
            )
            if res_groq.status_code == 200:
                data = json.loads(res_groq.json()["choices"][0]["message"]["content"])
                if data.get("card_text") and data.get("caption"):
                    tags = [t.lstrip("#").strip() for t in data.get("hashtags", []) if isinstance(t, str) and t.strip()]
                    raw_h = data.get("hook_title", "").strip(' "\'“”«»')
                    final_h = raw_h if (raw_h and len(raw_h) <= 70 and not raw_h.lower().startswith("novena:")) else f"NÃO DESISTA HOJE: O {novena_day}º DIA É ONDE A GRAÇA COMEÇA"
                    return {
                        "hook_title": final_h,
                        "formatted_text": data["card_text"].strip(),
                        "caption": data["caption"].strip(),
                        "hashtags": tags,
                        "visual_prompt": data.get("visual_prompt", f"Cinematic sacred altar with candles, holy art of {saint_name}")
                    }
    except Exception as exc:
        log.warning(f"Falha ao formatar novena via Groq ({exc}). Usando fallback determinístico...")

    header = f"🕊️ Novena de {saint_name} — {novena_day}º Dia de {total_days}"
    sub = f"✨ Grande Festa em {feast_date} • {feast_title}"
    fallback_card = f"{novena_day}º Dia da Novena de {saint_name}\n\n\"{prayer_text}\"\n\n— Solenidade em {feast_date}"
    fallback_caption = (
        f"{header}\n{sub}\n\n"
        f"Hoje nos unimos em oração no {novena_day}º dia desta santa novena. Entregamos a Deus todas as causas aflitas, intenções de saúde e necessidades de nossas famílias sob a poderosa intercessão de {saint_name}.\n\n"
        f"🙏 Oração do {novena_day}º Dia:\n"
        f"\"{prayer_text}\"\n\n"
        f"Comente \"Eu creio\" e deixe seus pedidos de oração neste {novena_day}º dia da novena! Convide sua família para rezar junto até a grande festa em {feast_date}. 🙏✨\n\n"
        f"#novena #{clean_saint_tag} #fe #oracao #santododia #catolicismo #milagres #reelsbrasil"
    )
    return {
        "hook_title": f"NÃO DESISTA HOJE: O {novena_day}º DIA É ONDE A GRAÇA COMEÇA",
        "formatted_text": fallback_card,
        "caption": fallback_caption,
        "hashtags": ["novena", clean_saint_tag, "fe", "oracao", "santododia", "catolicismo"],
        "visual_prompt": f"Cinematic sacred scene of {saint_name}, glowing golden candles, holy sanctuary, peaceful divine light, 8k"
    }


def format_prayer_post(reference: str, text: str) -> dict:
    """
    Formata grandes orações clássicas (Salmo 91, São Bento, etc.) e Salmos Litúrgicos.
    """
    clean_title = reference.split("(")[0].strip()
    is_psalm = "salmo" in reference.lower()

    hook_default = "30 SEGUNDOS PARA BLINDAR A SUA CASA HOJE" if is_psalm else "COLOQUE A MÃO NO CORAÇÃO E RECEBA ESTA ORAÇÃO"
    icon = "📜" if is_psalm else "🙏"

    clean_text = text.strip()
    card_text = f"{clean_text[:380].rsplit(' ', 1)[0]}...\n\n— {clean_title}" if len(clean_text) > 400 else f"{clean_text}\n\n— {clean_title}"

    prompt = f"""Você é um especialista em conteúdo bíblico e orações para redes sociais.
Formate uma publicação devocional impactante:
Título/Referência: {clean_title}
Texto da Oração/Salmo: {clean_text[:2000]}

Gere um objeto JSON estrito com:
{{
  "hook_title": "Gancho magnético de 4 a 8 palavras para os PRIMEIROS 3 SEGUNDOS do vídeo. Use proteção do lar ou alívio imediato (ex para Salmo: '30 segundos para blindar sua casa contra todo mal', 'Coloque a mão no coração e ouça este Salmo', 'Se o seu coração está aflito, ouça agora'; ex para Oração: 'Oração poderosa: nenhum mal entrará na sua casa', 'Reze isso agora e sinta a paz entrar no seu lar', 'Blinde sua família antes de dormir com esta oração'). NUNCA use rótulos como 'SALMO DE PROTEÇÃO' ou 'ORAÇÃO PARA SEU LAR'.",
  "caption": "Legenda completa com: 1) Título honroso ({icon} {clean_title}); 2) Introdução convidando para momento de paz e proteção no lar; 3) Texto da oração/salmo em destaque; 4) Bênção final e chamada fraterna para compartilhar no WhatsApp da família e comentar Amém; 5) Bloco de hashtags.",
  "hashtags": ["oracao", "fe", "salmo", "protecaodivina", "deus", "paznolar", "catolicismo", "reelsbrasil"],
  "visual_prompt": "Cinematic peaceful sanctuary, rays of heavenly morning sunlight piercing through stained glass, gentle glowing candles, sacred calm atmosphere, no text, 8k resolution"
}}"""

    try:
        _configure_genai()
        model = genai.GenerativeModel(GEMINI_MODEL)
        res = model.generate_content(
            prompt,
            generation_config={"temperature": 0.6, "response_mime_type": "application/json"},
            request_options={"timeout": 8.0}
        )
        data = json.loads(res.text.strip())
        if data.get("caption"):
            tags = [t.lstrip("#").strip() for t in data.get("hashtags", []) if isinstance(t, str) and t.strip()]
            raw_h = data.get("hook_title", "").strip(' "\'“”«»')
            final_h = raw_h if (raw_h and len(raw_h) <= 70 and not any(k in raw_h.lower() for k in ("salmo de proteção", "oração poderosa"))) else hook_default
            return {
                "hook_title": final_h,
                "formatted_text": card_text,
                "caption": data["caption"].strip(),
                "hashtags": tags,
                "visual_prompt": data.get("visual_prompt", "Cinematic peaceful sanctuary, glowing candles, holy light")
            }
    except Exception as exc:
        log.warning(f"Falha ao formatar oração clássica via Gemini ({exc}). Tentando Groq...")

    # 2. Tenta Groq
    try:
        from config.settings import GROQ_API_KEY, GROQ_MODEL
        if GROQ_API_KEY:
            res_groq = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
                json={
                    "model": GROQ_MODEL or "llama-3.1-8b-instant",
                    "messages": [
                        {"role": "system", "content": "Responda exclusivamente JSON estrito."},
                        {"role": "user", "content": prompt}
                    ],
                    "response_format": {"type": "json_object"},
                    "temperature": 0.6
                },
                timeout=10
            )
            if res_groq.status_code == 200:
                data = json.loads(res_groq.json()["choices"][0]["message"]["content"])
                if data.get("caption"):
                    tags = [t.lstrip("#").strip() for t in data.get("hashtags", []) if isinstance(t, str) and t.strip()]
                    raw_h = data.get("hook_title", "").strip(' "\'“”«»')
                    final_h = raw_h if (raw_h and len(raw_h) <= 70 and not any(k in raw_h.lower() for k in ("salmo de proteção", "oração poderosa"))) else hook_default
                    return {
                        "hook_title": final_h,
                        "formatted_text": card_text,
                        "caption": data["caption"].strip(),
                        "hashtags": tags,
                        "visual_prompt": data.get("visual_prompt", "Cinematic peaceful sanctuary, glowing candles, holy light")
                    }
    except Exception as exc:
        log.warning(f"Falha ao formatar oração clássica via Groq ({exc}). Usando fallback...")

    caption = (
        f"{icon} {clean_title}\n\n"
        f"Faça uma pausa e receba esta palavra de proteção e refúgio para o seu coração e para a sua casa.\n\n"
        f"\"{clean_text}\"\n\n"
        f"Que a paz do Senhor guarde a sua mente e a sua família hoje e sempre. Deixe seu \"Amém\" nos comentários e envie este vídeo para alguém que precisa de forças hoje! 🙏🕊️\n\n"
        f"#oracao #salmododia #protecaodivina #fe #deus #paz #catolicismo #reelsbrasil"
    )
    return {
        "hook_title": hook_default,
        "formatted_text": card_text,
        "caption": caption,
        "hashtags": ["oracao", "fe", "salmododia", "protecaodivina", "paz", "deus"],
        "visual_prompt": "Cinematic peaceful sanctuary, rays of heavenly sunlight, gentle glowing candles, sacred calm atmosphere"
    }
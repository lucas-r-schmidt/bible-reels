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
- O gancho (hook_title) DEVE falar diretamente com quem está ansioso ou angustiado (ex: 'Para o coração ansioso hoje', 'Deus acalma sua ansiedade', 'Respire fundo e ouça isso').
- Inclua nas hashtags: ansiedade, pazinterior, alivio, fe, deusnocontrole, confianca."""
    elif theme == "cansaco":
        theme_directive = """DIRETRIZ PARA CANSAÇO E SOBRECARGA:
- O gancho (hook_title) DEVE acolher quem está esgotado ou sobrecarregado (ex: 'Para quem está cansado hoje', 'Deus renova tuas forças', 'Quando o peso for demais').
- Inclua nas hashtags: cansaco, forca, renovacao, descansaemdeus, perseveranca."""
    elif theme == "medo":
        theme_directive = """DIRETRIZ CONTRA O MEDO E INCERTEZA:
- O gancho (hook_title) DEVE inspirar coragem e segurança em Deus (ex: 'Não tenha medo do amanhã', 'Deus está no comando', 'Coragem, Ele cuida de você').
- Inclua nas hashtags: naotemas, coragem, vitoria, protecaodivina, fe."""
    elif theme == "familia":
        theme_directive = """DIRETRIZ PARA FAMÍLIA E LAR:
- O gancho (hook_title) DEVE abençoar o lar e a família (ex: 'Uma bênção para seu lar', 'Proteção para sua família', 'A paz na sua casa').
- Inclua nas hashtags: familia, lardepaz, bencaodivina, casadeoracao, amorfamiliar."""
    elif theme == "sunday_blessing":
        theme_directive = """DIRETRIZ DE DOMINGO (BÊNÇÃO DA SEMANA):
- O gancho (hook_title) DEVE preparar a alma e abençoar a semana que se inicia (ex: 'Bênção para sua nova semana', 'Domingo de paz e graça', 'Comece a semana com Deus').
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


def format_gospel_post(reference: str, text: str, celebration: str = "") -> dict:
    """
    Formata o Evangelho do Dia para publicação em vídeo/carrossel.
    Garante fidelidade 100% ao texto do Evangelho e gera reflexão pastoral/homilia concisa.
    """
    prompt = f"""Você é um teólogo e liturgista católico especialista em redes sociais cristãs.
Abaixo está o Evangelho Oficial do Dia proclamado pela Igreja Católica:
Celebração Litúrgica: {celebration}
Referência Bíblica: {reference}
Texto Sagrado:
{text}

REGRA CRÍTICA INEGOCIÁVEL:
NUNCA altere o texto bíblico do Evangelho.

Gere um objeto JSON estrito com as seguintes chaves:
{{
  "hook_title": "Gancho de 3 a 6 palavras impactantes para prender a atenção nos primeiros 2 segundos do Reel (ex: 'O Evangelho de Hoje para Você', 'Jesus tem um recado para sua vida', 'Palavra de Salvação para Hoje').",
  "homily_reflection": "Uma reflexão pastoral/homilia concisa e profunda de 1 parágrafo (máximo 250 caracteres) aplicando a mensagem de Jesus para a vida diária dos fiéis hoje.",
  "caption": "Legenda completa para redes sociais contendo: 1) Título solene '📖 Evangelho do Dia ({reference})'; 2) Texto do Evangelho ou trecho central; 3) Reflexão pastoral/homilia; 4) Chamada devocional ('Deixe seu Amém e compartilhe a Boa Nova'); 5) Bloco de hashtags católicas.",
  "hashtags": ["evangelhododia", "palavradosenhor", "liturgiadiaria", "catolicismo", "fe", "evangelho", "reelsbrasil", "cristao", "bencaos"],
  "visual_prompt": "Cinematic holy bible on wooden altar with soft divine sunbeams, ancient reverent church ambiance, sacred illumination, peaceful and sacred, 8k"
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
        raw = res.text.strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        data = json.loads(raw)
        if data.get("caption") and data.get("hook_title"):
            hashtags = [t.lstrip("#").strip() for t in data.get("hashtags", []) if isinstance(t, str) and t.strip()]
            return {
                "hook_title": data["hook_title"].strip(),
                "formatted_text": f"{text.strip()}\n\n— {reference.strip()}",
                "homily_reflection": data.get("homily_reflection", "").strip(),
                "caption": data["caption"].strip(),
                "hashtags": hashtags,
                "visual_prompt": data.get("visual_prompt", "Cinematic holy bible with soft sunlight")
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
                    return {
                        "hook_title": data["hook_title"].strip(),
                        "formatted_text": f"{text.strip()}\n\n— {reference.strip()}",
                        "homily_reflection": data.get("homily_reflection", "").strip(),
                        "caption": data["caption"].strip(),
                        "hashtags": hashtags,
                        "visual_prompt": data.get("visual_prompt", "Cinematic holy bible with soft sunlight")
                    }
    except Exception as exc:
        log.warning(f"Falha ao formatar Evangelho via Groq ({exc}).")

    # 3. Fallback determinístico
    clean_text = text.strip()
    caption = (
        f"📖 Evangelho do Dia — {reference}\n"
        f"✨ {celebration}\n\n"
        f"\"{clean_text[:500]}...\"\n\n"
        f"🙏 Que a Palavra de Cristo ilumine o seu caminhar hoje. Deixe seu \"Amém\" e compartilhe essa bênção!\n\n"
        f"#evangelhododia #liturgiadiaria #fe #jesus #palavradedeus #catolicismo #reelsbrasil"
    )
    return {
        "hook_title": "O EVANGELHO DO DIA PARA VOCÊ",
        "formatted_text": f"{clean_text}\n\n— {reference.strip()}",
        "homily_reflection": "A Palavra do Senhor nos convida a manter os corações atentos e confiantes na Sua divina misericórdia.",
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
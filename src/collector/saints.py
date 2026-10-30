"""
src/collector/saints.py
-----------------------
Módulo de coleta e curadoria do "Santo do Dia".
Fluxo hierárquico oficial:
1. Catálogo curado local (data/saints/saints_calendar.json).
2. Fontes católicas oficiais (Canção Nova / CNBB e Vatican News PT) com enriquecimento via IA e auto-cache local.
3. Fallback via IA (Gemini Flash / Groq) caso as fontes web estejam inacessíveis.
"""
from datetime import date, datetime
import hashlib
import html
import json
from pathlib import Path
import re
from typing import Any

import requests

from src.processor.db_manager import DBManager
from src.utils.logger import get_logger

log = get_logger(__name__)

SAINTS_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "saints" / "saints_calendar.json"

MONTH_NAMES_PT = [
    "", "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"
]


def _hash_content(key: str) -> str:
    return hashlib.sha256(key.strip().lower().encode("utf-8")).hexdigest()


def load_saints_catalog(filepath: Path | None = None) -> dict[str, dict[str, Any]]:
    path = filepath or SAINTS_FILE
    if not path.is_file():
        log.warning(f"Arquivo de santos não encontrado em {path}")
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception as exc:
        log.error(f"Erro ao carregar catálogo de santos: {exc}")
        return {}


def save_saint_to_catalog(target_date: date, saint_data: dict[str, Any], filepath: Path | None = None) -> None:
    """Persiste o santo validado no catálogo local para cache permanente."""
    path = filepath or SAINTS_FILE
    key = f"{target_date.month:02d}-{target_date.day:02d}"
    try:
        catalog = load_saints_catalog(path)
        entry = {
            "name": saint_data.get("name", "").strip(),
            "title": saint_data.get("title", "").strip(),
            "quote": saint_data.get("quote", "").strip(),
            "prayer": saint_data.get("prayer", "").strip(),
            "history": saint_data.get("history", "").strip(),
        }
        if saint_data.get("image_url"):
            entry["image_url"] = saint_data["image_url"]
        if saint_data.get("source_url"):
            entry["source_url"] = saint_data["source_url"]

        if entry["name"] and entry["history"]:
            catalog[key] = entry
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(catalog, f, ensure_ascii=False, indent=2)
            log.info(f"Santo do dia {key} ({entry['name']}) salvo no catálogo local ({path.name}).")
    except Exception as exc:
        log.warning(f"Não foi possível salvar santo no catálogo local: {exc}")


def _clean_html_text(raw_html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", raw_html)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _split_saint_name_and_title(full_heading: str, invocation_line: str = "") -> tuple[str, str]:
    """Separa o nome canônico do santo e seu título/epíteto a partir do cabeçalho da Canção Nova."""
    cleaned = full_heading.strip()
    inv_name = ""
    if invocation_line:
        m_inv = re.match(r"^([^,]+),\s*rogai\s+por\s+n[oó]s", invocation_line.strip(), flags=re.IGNORECASE)
        if m_inv:
            inv_name = m_inv.group(1).strip()

    if "," in cleaned:
        parts = [p.strip() for p in cleaned.split(",", 1)]
        name_part, title_part = parts[0], parts[1]
        if title_part:
            title_part = title_part[0].upper() + title_part[1:]
        return name_part, title_part or "Memória Litúrgica"

    if ":" in cleaned:
        parts = [p.strip() for p in cleaned.split(":", 1)]
        return parts[0], parts[1].capitalize()

    if inv_name and inv_name.lower() in cleaned.lower() and len(cleaned) > len(inv_name) + 5:
        idx = cleaned.lower().find(inv_name.lower()) + len(inv_name)
        rest = cleaned[idx:].strip(" ,–—-")
        if rest:
            return inv_name, rest[0].upper() + rest[1:]

    return inv_name or cleaned, "Memória Litúrgica e Testemunho de Fé"


def check_active_novena(target_date: date | None = None) -> dict[str, Any] | None:
    """
    Verifica se a data atual cai em algum período de novena tradicional (9 dias antes de grande solenidade).
    Retorna os dados da festa, nome do santo e o número do dia da novena (1 a 9).
    """
    from datetime import timedelta
    d = target_date or date.today()
    catalog = load_saints_catalog()

    # Checa santos de 1 a 9 dias à frente
    for delta in range(1, 10):
        future_date = d + timedelta(days=delta)
        key = f"{future_date.month:02d}-{future_date.day:02d}"
        if key in catalog and catalog[key].get("has_novena"):
            saint_info = catalog[key]
            novena_day = 10 - delta
            return {
                "novena_day": novena_day,
                "total_days": 9,
                "saint_name": saint_info.get("name"),
                "feast_date": future_date.strftime("%d/%m"),
                "feast_title": saint_info.get("title"),
                "saint_data": saint_info,
            }
    return None


def fetch_saint_from_cancaonova(target_date: date) -> dict[str, Any] | None:
    """
    Consulta a fonte oficial da Canção Nova (santo.cancaonova.com) para a data especificada.
    Usa o endpoint oficial do calendário litúrgico para descobrir a URL exata do dia e extrair
    nome, título, história, oração tradicional e imagem oficial.
    """
    day = target_date.day
    month = target_date.month
    year = target_date.year
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) BibleReels/1.0"}

    try:
        # 1. Consulta o widget de calendário do mês para obter o link oficial do dia
        r_cal = requests.post(
            "https://santo.cancaonova.com/wp-admin/admin-ajax.php",
            data={
                "action": "widget-ajax",
                "sMes": str(month),
                "sAno": str(year),
                "title": "",
                "type": "santo",
                "ajax": "true",
            },
            headers=headers,
            timeout=12,
        )
        r_cal.encoding = "utf-8"
        if not r_cal.ok:
            return None

        pattern = rf'href=["\'](https://santo\.cancaonova\.com/santo/[^"\']+\?sDia={day}&(?:amp;)?sMes={month}[^"\']*)["\']'
        m_url = re.search(pattern, r_cal.text)
        if not m_url:
            return None

        saint_url = html.unescape(m_url.group(1))
        r_page = requests.get(saint_url, headers=headers, timeout=12)
        r_page.encoding = "utf-8"
        if not r_page.ok:
            return None

        html_doc = r_page.text

        # 2. Extrai título principal (h1.entry-title)
        h1_m = re.search(r'<h1[^>]*class=["\'][^"\']*entry-title[^"\']*["\'][^>]*>(.*?)</h1>', html_doc, re.S)
        raw_h1 = _clean_html_text(h1_m.group(1)) if h1_m else ""
        if not raw_h1:
            return None

        # 3. Isola o bloco de conteúdo do artigo
        c_start = html_doc.find("entry-content")
        c_end = html_doc.find("</article>", c_start)
        block = html_doc[c_start:c_end] if (c_start != -1 and c_end != -1) else html_doc

        # Extrai a melhor imagem oficial do artigo
        best_img = None
        srcset_m = re.search(r'srcset=["\']([^"\']*img\.cancaonova\.com[^"\']+)["\']', block)
        if srcset_m:
            candidates = [c.strip().split(" ")[0] for c in srcset_m.group(1).split(",") if c.strip()]
            if candidates:
                best_img = candidates[-1]
        if not best_img:
            img_m = re.search(r'<img[^>]+src=["\'](https://img\.cancaonova\.com/[^"\']+)["\']', block)
            if img_m:
                best_img = img_m.group(1)

        # Corta antes da seção "Outros santos e beatos"
        outros_idx = block.lower().find("outros santos e beatos")
        main_block = block[:outros_idx] if outros_idx != -1 else block

        # 4. Extrai parágrafos e subtítulos
        elements: list[tuple[str, str]] = []
        for em in re.finditer(r"<(p|h2|h3)[^>]*>(.*?)</\1>", main_block, re.S):
            tag = em.group(1).lower()
            txt = _clean_html_text(em.group(2))
            if len(txt) > 2:
                elements.append((tag, txt))

        invocation_line = ""
        prayer_text = ""
        subtitle_quote = ""
        body_paragraphs: list[str] = []

        for idx, (tag, txt) in enumerate(elements):
            low = txt.lower()
            if "rogai por nós" in low or "rogai por nos" in low:
                invocation_line = txt
                continue
            if tag in ("h2", "h3") and ":" in txt and not subtitle_quote:
                subtitle_quote = txt
                continue
            if low in ("minha oração", "minha oracao", "oração", "oracao"):
                if idx + 1 < len(elements):
                    cand_prayer = elements[idx + 1][1].strip(' "“”\'')
                    if len(cand_prayer) > 20:
                        prayer_text = cand_prayer
                continue
            # Ignora cabeçalhos curtos de seção (ex: "Origens", "Páscoa", "Adolescência")
            if len(txt) < 45 and not txt.endswith("."):
                continue
            if prayer_text and txt.strip(' "“”\'') == prayer_text:
                continue
            if len(txt) >= 50:
                body_paragraphs.append(txt)

        saint_name, saint_title = _split_saint_name_and_title(raw_h1, invocation_line)

        if subtitle_quote and saint_title == "Memória Litúrgica e Testemunho de Fé":
            _, sub_t = _split_saint_name_and_title(subtitle_quote)
            if sub_t:
                saint_title = sub_t

        # Monta biografia concisa em 2 parágrafos a partir do texto oficial
        if len(body_paragraphs) >= 2:
            history_raw = f"{body_paragraphs[0]}\n\n{body_paragraphs[1]}"
        elif body_paragraphs:
            history_raw = body_paragraphs[0]
        else:
            history_raw = f"Hoje a Igreja celebra a memória litúrgica de {saint_name} ({saint_title})."

        full_article_text = "\n\n".join(body_paragraphs[:6])

        # Se não encontrou oração explícita, cria oração litúrgica fiel ao santo
        if not prayer_text:
            prayer_text = (
                f"Ó Deus, que nos destes em {saint_name} um luminoso exemplo de fé e caridade, "
                f"concedei-nos por sua intercessão a graça de viver segundo o Evangelho. "
                f"{invocation_line or f'{saint_name}, rogai por nós!'} Amém."
            )
        elif not prayer_text.lower().endswith(("amém.", "amém!", "amém")):
            prayer_text = f"{prayer_text.rstrip('.')} Amém."

        quote_text = subtitle_quote if (subtitle_quote and len(subtitle_quote) <= 150) else (
            body_paragraphs[0][:145].rsplit(" ", 1)[0] + "..." if body_paragraphs and len(body_paragraphs[0]) > 150 else (body_paragraphs[0] if body_paragraphs else f"{saint_name}, rogai por nós!")
        )

        raw_result = {
            "name": saint_name,
            "title": saint_title,
            "quote": quote_text,
            "prayer": prayer_text,
            "history": history_raw,
            "full_article": full_article_text,
            "image_url": best_img,
            "source_url": saint_url,
            "source_provider": "cancaonova",
        }

        # Refina quote e resumo biográfico via IA mantendo 100% de fidelidade aos fatos extraídos
        enriched = _enrich_official_saint_with_ai(raw_result, target_date)
        log.info(f"Santo do dia {day:02d}/{month:02d} obtido da fonte oficial Canção Nova: {enriched['name']}")
        return enriched

    except Exception as exc:
        log.warning(f"Erro ao consultar Canção Nova para {day:02d}/{month:02d}: {exc}")
        return None


def fetch_saint_from_vaticannews(target_date: date) -> dict[str, Any] | None:
    """
    Fallback oficial secundário: consulta o portal Vatican News PT (vaticannews.va/pt/santo-do-dia).
    """
    day = target_date.day
    month = target_date.month
    url = f"https://www.vaticannews.va/pt/santo-do-dia/{month:02d}/{day:02d}.html"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) BibleReels/1.0"}

    try:
        r = requests.get(url, headers=headers, timeout=12)
        r.encoding = "utf-8"
        if not r.ok:
            return None

        html_doc = r.text
        headings = []
        for hm in re.finditer(r"<h2[^>]*>(.*?)</h2>", html_doc, re.S):
            h_txt = _clean_html_text(hm.group(1))
            if h_txt and h_txt.lower() not in ("menu", "busca", "santo do dia"):
                headings.append(h_txt)

        if not headings:
            return None

        sections = []
        for sm in re.finditer(r'<div[^>]*class=["\']([^"\']*section__content[^"\']*)["\'][^>]*>(.*?)</div>', html_doc, re.S):
            cls = sm.group(1)
            if "intro--saint" in cls:
                continue
            s_txt = _clean_html_text(sm.group(2)).replace("Leia tudo...", "").strip()
            if len(s_txt) > 30:
                sections.append(s_txt)

        raw_heading = headings[0]
        # Converte abreviação "S. " para "São / Santo"
        raw_heading = re.sub(r"^S\.\s+", "São ", raw_heading)
        saint_name, saint_title = _split_saint_name_and_title(raw_heading)
        bio = sections[0] if sections else f"Memória litúrgica de {saint_name}, celebrada pela Igreja em {day:02d}/{month:02d}."

        raw_result = {
            "name": saint_name,
            "title": saint_title,
            "quote": bio[:145].rsplit(" ", 1)[0] + "..." if len(bio) > 150 else bio,
            "prayer": f"Senhor Deus, que nos destes em {saint_name} um modelo de fidelidade ao Evangelho, concedei-nos por sua intercessão crescer na fé e na caridade. Amém.",
            "history": bio,
            "full_article": "\n\n".join(sections),
            "source_url": url,
            "source_provider": "vaticannews",
        }
        enriched = _enrich_official_saint_with_ai(raw_result, target_date)
        log.info(f"Santo do dia {day:02d}/{month:02d} obtido do Vatican News: {enriched['name']}")
        return enriched
    except Exception as exc:
        log.warning(f"Erro ao consultar Vatican News para {day:02d}/{month:02d}: {exc}")
        return None


def _enrich_official_saint_with_ai(official_data: dict[str, Any], target_date: date) -> dict[str, Any]:
    """
    Usa o texto oficial extraído da Canção Nova / Vatican News como contexto estrito (RAG)
    para polir a citação (quote) e estruturar a biografia em 2 parágrafos para os slides,
    sem jamais alterar qual é o santo nem inventar fatos.
    """
    saint_name = official_data["name"]
    saint_title = official_data["title"]
    article = official_data.get("full_article") or official_data.get("history", "")
    existing_prayer = official_data.get("prayer", "")

    prompt = f"""Você é um editor litúrgico católico. Abaixo estão os dados OFICIAIS extraídos diretamente do portal Santo do Dia ({official_data.get('source_provider', 'Canção Nova')}) para o dia {target_date.day:02d}/{target_date.month:02d}:

SANTO OFICIAL: {saint_name}
TÍTULO OFICIAL: {saint_title}
ORAÇÃO EXTRAÍDA: {existing_prayer}
TEXTO BIOGRÁFICO OFICIAL:
{article[:3000]}

REGRA INEGOCIÁVEL:
Mantenha EXATAMENTE o mesmo Santo ({saint_name}). NÃO troque por outro santo. Baseie-se estritamente nos fatos do texto oficial acima.

Retorne EXCLUSIVAMENTE um JSON válido com as chaves:
{{
  "name": "{saint_name}",
  "title": "Título conciso e honroso do santo (ex: '{saint_title}')",
  "quote": "Uma frase célebre dita pelo santo ou síntese inspiradora de sua fé baseada no texto (máximo 140 caracteres, em português)",
  "prayer": "Mantenha a oração extraída acima ou refine-a em 2 a 4 linhas devocionais terminando com Amém.",
  "history": "Resumo biográfico envolvente em exatamente 2 parágrafos separados por \\n\\n, fiel ao texto oficial."
}}"""

    # 1. Tenta Gemini
    try:
        import google.generativeai as genai
        from config.settings import GEMINI_API_KEY, GEMINI_MODEL
        if GEMINI_API_KEY and GEMINI_API_KEY.startswith("AIza"):
            genai.configure(api_key=GEMINI_API_KEY)
            model = genai.GenerativeModel(GEMINI_MODEL or "gemini-1.5-flash")
            res = model.generate_content(
                prompt,
                generation_config={"response_mime_type": "application/json"},
                request_options={"timeout": 8.0},
            )
            data = json.loads(res.text.strip())
            if data.get("quote") and data.get("history"):
                official_data["title"] = data.get("title") or saint_title
                official_data["quote"] = data["quote"].strip()
                official_data["prayer"] = data.get("prayer") or existing_prayer
                official_data["history"] = data["history"].strip()
                return official_data
    except Exception as exc:
        log.debug(f"Enriquecimento Gemini indisponível ({exc}). Tentando Groq...")

    # 2. Tenta Groq
    try:
        from config.settings import GROQ_API_KEY, GROQ_MODEL
        if GROQ_API_KEY:
            res = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
                json={
                    "model": GROQ_MODEL or "llama-3.1-8b-instant",
                    "messages": [
                        {"role": "system", "content": "Responda exclusivamente em formato JSON válido."},
                        {"role": "user", "content": prompt},
                    ],
                    "response_format": {"type": "json_object"},
                    "temperature": 0.2,
                },
                timeout=12,
            )
            if res.ok:
                data = json.loads(res.json()["choices"][0]["message"]["content"])
                if data.get("quote") and data.get("history"):
                    official_data["title"] = data.get("title") or saint_title
                    official_data["quote"] = data["quote"].strip()
                    official_data["prayer"] = data.get("prayer") or existing_prayer
                    official_data["history"] = data["history"].strip()
                    return official_data
    except Exception as exc:
        log.debug(f"Enriquecimento Groq indisponível ({exc}). Usando extração direta.")

    return official_data



def _fetch_saint_from_ai(target_date: date) -> dict[str, str] | None:
    """Fallback via Gemini / Groq para consultar o santo oficial do dia."""
    day = target_date.day
    month_name = MONTH_NAMES_PT[target_date.month]

    prompt = f"""Você é um teólogo e historiador especialista em liturgia da Igreja Católica Apostólica Romana no Brasil.
Identifique o Santo, Beato ou a Solenidade Litúrgica celebrada no dia {day} de {month_name}.

REGRA OBRIGATÓRIA DE PRIORIDADE HIERÁRQUICA:
1. PRIORIDADE MÁXIMA: Calendário Litúrgico Próprio do Brasil (aprovado pela CNBB). Se houver solenidade, festa ou memória própria do Brasil nesta data (ex: santos/beatos brasileiros, padroeiros do Brasil), use-a OBRIGATORIAMENTE.
2. SEGUNDA PRIORIDADE: Grandes memórias, celebrações ou devoções tradicionais vivenciadas com forte relevância no Brasil nesta data (ex: aparições marianas comemoradas em santuários brasileiros).
3. TERCEIRA PRIORIDADE (apenas se não houver celebração relevante no Brasil): Santo ou Solenidade do Calendário Romano Geral / Universal da Igreja Católica mundial.

Responda EXCLUSIVAMENTE em formato JSON estrito com exatamente as seguintes chaves:
{{
  "name": "Nome do Santo ou Solenidade",
  "title": "Título ou Patrono (ex: Padroeira do Brasil, Memória Litúrgica no Brasil)",
  "quote": "Frase de impacto dita pelo santo ou trecho célebre de oração atribuída a ele (máximo 150 caracteres, em português)",
  "prayer": "Oração curta de intercessão ou invocação tradicional (2 a 4 linhas)",
  "history": "Biografia concisa em 2 parágrafos contando quem foi, o que realizou e por que é celebrado na fé cristã."
}}"""

    # 1. Tenta Gemini Flash (se chave for válida)
    try:
        import google.generativeai as genai
        from config.settings import GEMINI_API_KEY, GEMINI_MODEL
        if GEMINI_API_KEY and GEMINI_API_KEY.startswith("AIza"):
            genai.configure(api_key=GEMINI_API_KEY)
            model = genai.GenerativeModel(GEMINI_MODEL or "gemini-1.5-flash")
            res = model.generate_content(
                prompt,
                generation_config={"response_mime_type": "application/json"},
                request_options={"timeout": 6.0}
            )
            data = json.loads(res.text.strip())
            if data.get("name") and data.get("quote"):
                log.info(f"Santo do dia {day}/{target_date.month} consultado com sucesso via Gemini: {data['name']}")
                return data
    except Exception as exc:
        log.warning(f"Falha ao consultar santo do dia via Gemini ({exc}). Tentando Groq...")

    # 2. Tenta Groq Fallback
    try:
        import requests
        from config.settings import GROQ_API_KEY, GROQ_MODEL
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
                timeout=15
            )
            if res.ok:
                data = json.loads(res.json()["choices"][0]["message"]["content"])
                if data.get("name") and data.get("quote"):
                    log.info(f"Santo do dia consultado com sucesso via Groq: {data['name']}")
                    return data
    except Exception as exc:
        log.warning(f"Falha ao consultar santo do dia via Groq: {exc}")

    return None


def get_saint_for_date(target_date: date | None = None, refresh: bool = False) -> dict[str, Any]:
    """
    Obtém os dados do Santo do Dia para uma data específica (ou hoje por padrão).
    Ordem de prioridade:
    1. Catálogo curado local (data/saints/saints_calendar.json), exceto se refresh=True
    2. Portal oficial Canção Nova (santo.cancaonova.com) — Calendário CNBB / Brasil
    3. Portal oficial Vatican News PT (vaticannews.va) — Martirológio Romano
    4. Fallback via IA (Gemini / Groq)
    """
    d = target_date or date.today()
    key = f"{d.month:02d}-{d.day:02d}"

    if not refresh:
        catalog = load_saints_catalog()
        if key in catalog:
            entry = dict(catalog[key])
            entry["date_str"] = f"{d.day:02d}/{d.month:02d}"
            entry["date_iso"] = d.isoformat()
            return entry

    log.info(f"Consultando fontes católicas oficiais para {d.day:02d}/{d.month:02d}...")

    # 1. Fonte Oficial Primária: Canção Nova (Brasil / CNBB)
    official_cn = fetch_saint_from_cancaonova(d)
    if official_cn:
        save_saint_to_catalog(d, official_cn)
        official_cn["date_str"] = f"{d.day:02d}/{d.month:02d}"
        official_cn["date_iso"] = d.isoformat()
        return official_cn

    # 2. Fonte Oficial Secundária: Vatican News PT (Santa Sé)
    official_vn = fetch_saint_from_vaticannews(d)
    if official_vn:
        save_saint_to_catalog(d, official_vn)
        official_vn["date_str"] = f"{d.day:02d}/{d.month:02d}"
        official_vn["date_iso"] = d.isoformat()
        return official_vn

    # 3. Fallback IA caso os portais oficiais estejam fora do ar
    log.info(f"Fontes web indisponíveis para {key}. Acionando fallback IA...")
    ai_saint = _fetch_saint_from_ai(d)
    if ai_saint:
        save_saint_to_catalog(d, ai_saint)
        ai_saint["date_str"] = f"{d.day:02d}/{d.month:02d}"
        ai_saint["date_iso"] = d.isoformat()
        return ai_saint

    log.error(f"Nenhum santo do dia identificado pelas fontes oficiais nem pela IA para {key}.")
    return None


def collect_saint_of_day(
    db: DBManager,
    target_date: date | None = None,
    force: bool = False
) -> dict[str, Any] | None:
    """
    Coleta e persiste no banco de dados o Santo do Dia como item de conteúdo (tabela verses).
    Garante idempotência evitando inserções duplicadas para o mesmo dia.
    Em caso de falha, NUNCA substitui por outro tipo de conteúdo (como versículo avulso).
    Retorna None para que o pipeline aborte de forma segura.
    """
    d = target_date or date.today()
    try:
        saint = get_saint_for_date(d, refresh=force)
    except Exception as exc:
        log.error(f"Falha ao identificar Santo do Dia para {d.strftime('%d/%m')}: {exc}. Abortando sem substituição.")
        return None

    if not saint or not saint.get("name") or not saint.get("quote"):
        log.error(f"Santo do dia não encontrado ou incompleto para {d.strftime('%d/%m')}. Abortando sem substituição.")
        return None

    content_hash = _hash_content(f"saint_{d.isoformat()}_{saint['name']}")

    if db.verse_exists(content_hash):
        row = db.conn.execute("SELECT * FROM verses WHERE hash = ?", (content_hash,)).fetchone()
        log.info(f"Santo do dia já registrado para {saint['date_str']}: {saint['name']} (ID {row['id']})")
        return {**saint, "verse_id": row["id"], "already_exists": True}

    ref = f"{saint['name']} ({saint['date_str']})"
    quote_text = saint.get("quote", "").strip()

    verse_id = db.insert_verse(
        source="saint",
        reference=ref,
        text=quote_text,
        content_hash=content_hash,
        translation=saint.get("title", "Santo do Dia")
    )

    log.info(f"Santo do dia coletado e registrado com sucesso: {ref} (ID {verse_id})")
    return {**saint, "verse_id": verse_id, "already_exists": False}


def collect_novena_of_day(
    db: DBManager,
    target_date: date | None = None
) -> dict[str, Any] | None:
    """
    Identifica se há novena litúrgica ativa para a data (1 a 9 dias antes da grande festa).
    Registra no banco de dados com source='novena' de forma idempotente.
    """
    d = target_date or date.today()
    nov = check_active_novena(d)
    if not nov:
        return None

    saint_name = nov["saint_name"]
    novena_day = nov["novena_day"]
    feast_date = nov["feast_date"]
    s_data = nov.get("saint_data", {})
    prayer = s_data.get("prayer") or f"Ó Deus, por intercessão de {saint_name}, concedei-nos a graça que Vos pedimos neste {novena_day}º dia de novena. Amém."

    ref = f"Novena de {saint_name} ({novena_day}º Dia) - {d.strftime('%d/%m')}"
    c_hash = _hash_content(f"novena_{d.isoformat()}_{saint_name}_{novena_day}")

    if db.verse_exists(c_hash):
        row = db.conn.execute("SELECT * FROM verses WHERE hash = ?", (c_hash,)).fetchone()
        log.info(f"Novena já registrada para hoje: {ref} (ID {row['id']})")
        return {**nov, "verse_id": row["id"], "already_exists": True}

    verse_id = db.insert_verse(
        source="novena",
        reference=ref,
        text=prayer,
        content_hash=c_hash,
        translation=f"Dia {novena_day} de {nov['total_days']} • Festa em {feast_date}"
    )

    log.info(f"Novena registrada com sucesso: {ref} (ID {verse_id})")
    return {**nov, "verse_id": verse_id, "already_exists": False}


SAINTS_IMAGES_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "saints" / "images"


def fetch_saint_image_from_wikimedia(saint_name: str, target_date: date | None = None) -> Path | None:
    """
    Busca imagem canônica oficial de domínio público na Wikipedia / Wikimedia Commons
    pelo nome do santo e salva em cache local em data/saints/images.
    """
    if not saint_name:
        return None

    import io
    import re
    from PIL import Image
    import requests

    SAINTS_IMAGES_DIR.mkdir(parents=True, exist_ok=True)

    clean_name = saint_name.split("(")[0].strip()
    slug = re.sub(r"[^a-z0-9]+", "_", clean_name.lower()).strip("_")
    d = target_date or date.today()
    date_key = f"{d.month:02d}-{d.day:02d}"

    headers = {"User-Agent": "BibleReelsBot/1.0 (contact@biblereels.local)"}
    api_url = "https://pt.wikipedia.org/w/api.php"

    image_url = None

    # 1. Consulta por título exato com redirects
    try:
        params = {
            "action": "query",
            "titles": clean_name,
            "prop": "pageimages",
            "piprop": "original|thumbnail",
            "pithumbsize": 1280,
            "format": "json",
            "redirects": 1
        }
        res = requests.get(api_url, params=params, headers=headers, timeout=12)
        if res.ok:
            pages = res.json().get("query", {}).get("pages", {})
            for pid, pdata in pages.items():
                if pid != "-1":
                    orig = pdata.get("original", {}).get("source")
                    thumb = pdata.get("thumbnail", {}).get("source")
                    candidate = orig or thumb
                    if candidate and not candidate.lower().endswith((".svg", ".gif")):
                        image_url = candidate
                        break
    except Exception as exc:
        log.warning(f"Erro na busca direta Wikipedia para '{clean_name}': {exc}")

    # 2. Fallback: busca por gerador de pesquisa
    if not image_url:
        try:
            params_search = {
                "action": "query",
                "generator": "search",
                "gsrsearch": clean_name,
                "gsrlimit": 3,
                "prop": "pageimages",
                "piprop": "original|thumbnail",
                "pithumbsize": 1280,
                "format": "json"
            }
            res = requests.get(api_url, params=params_search, headers=headers, timeout=12)
            if res.ok:
                pages = res.json().get("query", {}).get("pages", {})
                for pid, pdata in pages.items():
                    orig = pdata.get("original", {}).get("source")
                    thumb = pdata.get("thumbnail", {}).get("source")
                    candidate = orig or thumb
                    if candidate and not candidate.lower().endswith((".svg", ".gif")):
                        image_url = candidate
                        break
        except Exception as exc:
            log.warning(f"Erro na busca generator Wikipedia para '{clean_name}': {exc}")

    if not image_url:
        return None

    # 3. Download e persistência em cache
    try:
        log.info(f"Baixando imagem canônica da Wikipedia para {clean_name}...")
        r = requests.get(image_url, headers=headers, timeout=20)
        r.raise_for_status()

        img = Image.open(io.BytesIO(r.content)).convert("RGB")
        out_slug = SAINTS_IMAGES_DIR / f"{slug}.jpg"
        img.save(out_slug, format="JPEG", quality=95)

        if target_date:
            out_date = SAINTS_IMAGES_DIR / f"{date_key}.jpg"
            img.save(out_date, format="JPEG", quality=95)

        log.info(f"Imagem oficial de {clean_name} salva com sucesso em {out_slug.name}")
        return out_slug
    except Exception as exc:
        log.error(f"Falha ao salvar imagem da Wikipedia para '{clean_name}': {exc}")
        return None


def fetch_saint_images_from_wikimedia(saint_name: str, max_count: int = 5, target_date: date | None = None) -> list[Path]:
    """
    Busca múltiplas imagens sacras autênticas e pinturas na Wikipedia / Wikimedia Commons
    pelo nome do santo e salva em cache local em data/saints/images.
    Evita ambiguidade com municípios/cidades homônimas e fotos de fachadas de igrejas.
    """
    if not saint_name:
        return []

    import io
    import re
    from PIL import Image
    import requests

    SAINTS_IMAGES_DIR.mkdir(parents=True, exist_ok=True)

    clean_name = saint_name.split("(")[0].strip()
    slug = re.sub(r"[^a-z0-9]+", "_", clean_name.lower()).strip("_")
    without_prefix = re.sub(r"^(São|Santo|Santa|Beato|Beata)\s+", "", clean_name, flags=re.IGNORECASE).strip()
    headers = {"User-Agent": "BibleReelsBot/1.0 (contact@biblereels.local)"}

    # Candidatos ordenados: prioriza títulos estritamente sacros para evitar cidades/municípios
    candidates_pt = [
        without_prefix,
        f"{without_prefix} (santo)",
        f"{without_prefix} (santa)",
        f"{clean_name} (santo)",
        f"{clean_name} (santa)",
        clean_name,
    ]

    image_urls: list[str] = []

    # 0. Inclui imagem oficial do catálogo / Canção Nova se disponível
    catalog = load_saints_catalog()
    if target_date:
        d_key = f"{target_date.month:02d}-{target_date.day:02d}"
        cat_img = (catalog.get(d_key) or {}).get("image_url")
        if cat_img and cat_img not in image_urls:
            image_urls.append(cat_img)
    if not image_urls:
        for entry in catalog.values():
            if entry.get("name", "").lower() == clean_name.lower() and entry.get("image_url"):
                image_urls.append(entry["image_url"])
                break

    forbidden_terms = (
        "logo", "flag", "icon", "map", "disambig", "symbol",
        "bandeira", "brasão", "brasao", "farm-fresh", "igreja.", "igreja_",
        "paroquia", "paróquia", "fachada", "mapa", "location", "commons-logo"
    )

    # 1. Busca em Wikipedia em Português
    for cand in candidates_pt:
        if len(image_urls) >= max_count:
            break
        try:
            params = {
                "action": "query",
                "titles": cand,
                "prop": "pageimages|categories|images",
                "piprop": "original",
                "cllimit": 25,
                "imlimit": 25,
                "redirects": 1,
                "format": "json"
            }
            res = requests.get("https://pt.wikipedia.org/w/api.php", params=params, headers=headers, timeout=12)
            if not res.ok:
                continue
            pages = res.json().get("query", {}).get("pages", {})
            for pid, pdata in pages.items():
                if pid == "-1":
                    continue

                # Ignora se for página de município, cidade ou desambiguação
                cats = [c.get("title", "").lower() for c in pdata.get("categories", [])]
                cats_str = " ".join(cats)
                if any(k in cats_str for k in ("município", "municípios", "cidades do", "distritos", "desambiguação")):
                    continue

                orig_url = pdata.get("original", {}).get("source")
                if orig_url and not any(k in orig_url.lower() for k in forbidden_terms):
                    if orig_url not in image_urls:
                        image_urls.append(orig_url)

                titles = [img["title"] for img in pdata.get("images", [])]
                valid_titles = [
                    t for t in titles
                    if any(t.lower().endswith(ext) for ext in (".jpg", ".jpeg", ".png"))
                    and not any(k in t.lower() for k in forbidden_terms)
                ][:max_count + 3]

                if valid_titles:
                    info_params = {
                        "action": "query",
                        "titles": "|".join(valid_titles),
                        "prop": "imageinfo",
                        "iiprop": "url",
                        "format": "json"
                    }
                    info_res = requests.get("https://pt.wikipedia.org/w/api.php", params=info_params, headers=headers, timeout=12)
                    if info_res.ok:
                        for ipage in info_res.json().get("query", {}).get("pages", {}).values():
                            if ipage.get("imageinfo"):
                                u = ipage["imageinfo"][0].get("url")
                                if u and u not in image_urls and not any(k in u.lower() for k in forbidden_terms):
                                    image_urls.append(u)
        except Exception as exc:
            log.warning(f"Erro ao buscar Wikipedia PT para '{cand}': {exc}")

    # 2. Se faltarem imagens, consulta Wikipedia em Inglês e Wikimedia Commons
    if len(image_urls) < max_count:
        en_cand = [
            f"Saint {without_prefix}",
            f"{without_prefix}",
            f"Peter of Alcantara" if "pedro" in clean_name.lower() else f"Saint {without_prefix}"
        ]
        for cand in en_cand:
            if len(image_urls) >= max_count:
                break
            try:
                res_en = requests.get(
                    "https://en.wikipedia.org/w/api.php",
                    params={
                        "action": "query",
                        "titles": cand,
                        "prop": "pageimages|images",
                        "piprop": "original",
                        "imlimit": 25,
                        "redirects": 1,
                        "format": "json"
                    },
                    headers=headers,
                    timeout=12
                )
                if res_en.ok:
                    pages_en = res_en.json().get("query", {}).get("pages", {})
                    for pid, pdata in pages_en.items():
                        if pid == "-1":
                            continue
                        orig_u = pdata.get("original", {}).get("source")
                        if orig_u and orig_u not in image_urls and not any(k in orig_u.lower() for k in forbidden_terms):
                            image_urls.append(orig_u)

                        titles_en = [img["title"] for img in pdata.get("images", [])]
                        valid_en = [
                            t for t in titles_en
                            if any(t.lower().endswith(ext) for ext in (".jpg", ".jpeg", ".png"))
                            and not any(k in t.lower() for k in forbidden_terms)
                        ][:max_count + 3]

                        if valid_en:
                            info_r = requests.get(
                                "https://en.wikipedia.org/w/api.php",
                                params={
                                    "action": "query",
                                    "titles": "|".join(valid_en),
                                    "prop": "imageinfo",
                                    "iiprop": "url",
                                    "format": "json"
                                },
                                headers=headers,
                                timeout=12
                            )
                            if info_r.ok:
                                for ip in info_r.json().get("query", {}).get("pages", {}).values():
                                    if ip.get("imageinfo"):
                                        u = ip["imageinfo"][0].get("url")
                                        if u and u not in image_urls and not any(k in u.lower() for k in forbidden_terms):
                                            image_urls.append(u)
            except Exception as exc:
                log.warning(f"Erro ao buscar Wikipedia EN para '{cand}': {exc}")

    downloaded_paths: list[Path] = []
    for idx, u in enumerate(image_urls[:max_count], start=1):
        try:
            out_path = SAINTS_IMAGES_DIR / f"{slug}_{idx:02d}.jpg"
            r = requests.get(u, headers=headers, timeout=15)
            if r.ok:
                img = Image.open(io.BytesIO(r.content)).convert("RGB")
                img.save(out_path, format="JPEG", quality=92)
                if idx == 1:
                    primary_path = SAINTS_IMAGES_DIR / f"{slug}.jpg"
                    img.save(primary_path, format="JPEG", quality=92)
                    if target_date:
                        date_key = f"{target_date.month:02d}-{target_date.day:02d}"
                        img.save(SAINTS_IMAGES_DIR / f"{date_key}.jpg", format="JPEG", quality=92)
                downloaded_paths.append(out_path)
        except Exception as e_down:
            log.warning(f"Erro ao baixar imagem {idx} de {clean_name}: {e_down}")

    return downloaded_paths



def get_saint_images(saint_name: str = "", count: int = 5, target_date: date | None = None) -> list[Path]:
    """
    Localiza ou baixa uma lista de imagens sacras correspondentes ao santo informado.
    Garante que o nome do santo tenha precedência estrita sobre a data para evitar trocas indesejadas.
    """
    SAINTS_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    import re
    images: list[Path] = []

    # 1. Prioridade absoluta: buscar por slug do santo
    if saint_name:
        clean_name = saint_name.split("(")[0].strip()
        slug = re.sub(r"[^a-z0-9]+", "_", clean_name.lower()).strip("_")

        # Procura arquivos numerados (ex: sao_francisco_de_assis_01.jpg, etc.)
        for ext in (".jpg", ".jpeg", ".png", ".webp"):
            for i in range(1, count + 1):
                c = SAINTS_IMAGES_DIR / f"{slug}_{i:02d}{ext}"
                if c.is_file() and c not in images:
                    images.append(c)

        # Procura arquivo único principal (ex: sao_francisco_de_assis.jpg)
        if not images:
            for ext in (".jpg", ".jpeg", ".png", ".webp"):
                c = SAINTS_IMAGES_DIR / f"{slug}{ext}"
                if c.is_file() and c not in images:
                    images.append(c)

        # Procura por correspondência parcial das palavras-chave
        if not images:
            keywords = [w for w in slug.split("_") if len(w) >= 4 and w not in ("santo", "santa", "nossa", "senhora")]
            for p in sorted(SAINTS_IMAGES_DIR.iterdir()):
                if p.is_file() and p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"):
                    p_stem = p.stem.lower()
                    if any(k in p_stem for k in keywords):
                        if p not in images:
                            images.append(p)

        # Se não encontrar ou tiver menos que o count, busca e baixa da Wikipedia
        if len(images) < count:
            fetched = fetch_saint_images_from_wikimedia(clean_name, max_count=count, target_date=target_date)
            for f in fetched:
                if f not in images:
                    images.append(f)

    # 2. Se e somente se o nome não for informado, usa correspondência por data MM-DD
    if not images and target_date:
        date_key = f"{target_date.month:02d}-{target_date.day:02d}"
        for ext in (".jpg", ".jpeg", ".png", ".webp"):
            c = SAINTS_IMAGES_DIR / f"{date_key}{ext}"
            if c.is_file():
                images.append(c)
                break

    return images


def get_saint_image(saint_name: str = "", target_date: date | None = None) -> Path | None:
    """Retorna a melhor imagem única para o santo (usando precedência estrita do nome)."""
    imgs = get_saint_images(saint_name=saint_name, count=1, target_date=target_date)
    return imgs[0] if imgs else None



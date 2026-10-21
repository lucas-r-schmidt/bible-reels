"""
src/collector/liturgy.py
------------------------
Módulo de coleta oficial da Liturgia Diária da Igreja Católica.
Fonte primária: Canção Nova (liturgia.cancaonova.com) - Calendário Litúrgico CNBB.
Extrai:
- Evangelho do Dia (referência bíblica exata, proclamação e texto fiel)
- Salmo Responsorial (referência, refrão e estrofes)
- Cor Litúrgica e Tempo / Memória
"""
from datetime import date, datetime
import hashlib
import html
from pathlib import Path
import re
from typing import Any

import requests

from src.processor.db_manager import DBManager
from src.utils.logger import get_logger

log = get_logger(__name__)


def _hash_content(key: str) -> str:
    return hashlib.sha256(key.strip().lower().encode("utf-8")).hexdigest()


def _clean_text(raw_html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", raw_html)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def fetch_liturgy_of_day(target_date: date | None = None) -> dict[str, Any] | None:
    """
    Coleta os textos litúrgicos oficiais do dia via portal Canção Nova.
    Retorna dicionário com 'gospel', 'psalm', 'header' e metadados litúrgicos.
    """
    d = target_date or date.today()
    day, month, year = d.day, d.month, d.year
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) BibleReels/1.0"}

    try:
        # 1. Consulta o widget mensal da liturgia
        r_cal = requests.post(
            "https://liturgia.cancaonova.com/wp-admin/admin-ajax.php",
            data={
                "action": "widget-ajax",
                "sMes": str(month),
                "sAno": str(year),
                "title": "",
                "type": "liturgia",
                "ajax": "true",
            },
            headers=headers,
            timeout=12,
        )
        r_cal.encoding = "utf-8"
        if not r_cal.ok:
            log.warning(f"Falha no calendário de liturgia ({r_cal.status_code})")
            return None

        pattern = rf'href=["\'](https://liturgia\.cancaonova\.com/liturgia/[^"\']+\?sDia={day}&(?:amp;)?sMes={month}[^"\']*)["\']'
        m_url = re.search(pattern, r_cal.text)
        if not m_url:
            log.warning(f"URL de liturgia não encontrada para {day:02d}/{month:02d}")
            return None

        liturgy_url = html.unescape(m_url.group(1))
        r_page = requests.get(liturgy_url, headers=headers, timeout=12)
        r_page.encoding = "utf-8"
        if not r_page.ok:
            return None

        html_doc = r_page.text

        # 2. Extrai cabeçalho da celebração
        h1_m = re.search(r'<h1[^>]*class=["\'][^"\']*entry-title[^"\']*["\'][^>]*>(.*?)</h1>', html_doc, re.S)
        celebration_title = _clean_text(h1_m.group(1)) if h1_m else f"Liturgia de {day:02d}/{month:02d}"

        # 3. Extrai o Evangelho (pane com 'Evangelho')
        evangelho_data: dict[str, str] = {}
        idx_ev = html_doc.find('id="liturgia-4"')
        if idx_ev == -1:
            idx_ev = html_doc.find('Evangelho (')
            if idx_ev != -1:
                idx_ev = html_doc.rfind('<div id="liturgia-', 0, idx_ev)

        if idx_ev != -1:
            idx_ev_end = html_doc.find('id="liturgia-5"', idx_ev)
            if idx_ev_end == -1:
                idx_ev_end = html_doc.find('</div>\n\t\t\t\t\t</div>', idx_ev)
            if idx_ev_end == -1:
                idx_ev_end = idx_ev + 4000
            ev_block = html_doc[idx_ev:idx_ev_end]

            paras = []
            for p in re.finditer(r'<p[^>]*>(.*?)</p>', ev_block, re.S):
                c = _clean_text(p.group(1))
                if c and not c.startswith(('iframe', '<div', 'var ', 'jQuery')):
                    paras.append(c)

            ref_ev = ""
            for p in paras:
                if "evangelho (" in p.lower():
                    m_ref = re.search(r'\((.*?)\)', p)
                    if m_ref:
                        ref_ev = m_ref.group(1).strip()
                    break

            # Limpa e filtra o corpo do evangelho
            ev_body_paras = []
            capture = False
            for p in paras:
                low = p.lower()
                if "proclamação do evangelho" in low:
                    capture = True
                    continue
                if capture:
                    if low.startswith("— palavra da salvação") or low.startswith("- palavra da salvação"):
                        break
                    if not low.startswith(("- glória a vós", "— glória a vós")):
                        ev_body_paras.append(p)

            evangelho_text = " ".join(ev_body_paras).strip()
            # Remove numeração de versículos no meio do texto (ex: "1 o Senhor escolheu... 2 E dizia...")
            evangelho_text = re.sub(r'(?<=\s)\d+\s+(?=[A-ZÀ-Úa-zà-ú])', '', evangelho_text).strip()

            evangelho_data = {
                "reference": ref_ev or "Evangelho do Dia",
                "text": evangelho_text,
                "celebration": celebration_title,
                "url": liturgy_url,
            }

        # 4. Extrai o Salmo Responsorial (pane liturgia-2)
        salmo_data: dict[str, str] = {}
        idx_sl = html_doc.find('id="liturgia-2"')
        if idx_sl != -1:
            idx_sl_end = html_doc.find('id="liturgia-3"', idx_sl)
            if idx_sl_end == -1:
                idx_sl_end = html_doc.find('id="liturgia-4"', idx_sl)
            if idx_sl_end == -1:
                idx_sl_end = idx_sl + 3500
            sl_block = html_doc[idx_sl:idx_sl_end]

            sl_paras = []
            for p in re.finditer(r'<p[^>]*>(.*?)</p>', sl_block, re.S):
                c = _clean_text(p.group(1))
                if c and 'iframe' not in c:
                    sl_paras.append(c)

            ref_sl = ""
            refrao_sl = ""
            estrofes_sl = []
            for p in sl_paras:
                if "responsório" in p.lower():
                    ref_sl = p.replace("Responsório", "").strip()
                elif not refrao_sl and p.startswith("-"):
                    refrao_sl = p.lstrip("- ").strip()
                elif p.startswith("-"):
                    estrofes_sl.append(p.lstrip("- ").strip())

            salmo_data = {
                "reference": ref_sl or "Salmo Responsorial",
                "refrain": refrao_sl,
                "verses": estrofes_sl,
                "text": f"Refrão: {refrao_sl}\n\n" + "\n\n".join(estrofes_sl),
                "url": liturgy_url,
            }

        log.info(f"Liturgia do dia {day:02d}/{month:02d} coletada com sucesso (Evangelho: {evangelho_data.get('reference')}, Salmo: {salmo_data.get('reference')})")
        return {
            "date_str": f"{day:02d}/{month:02d}",
            "date_iso": d.isoformat(),
            "celebration": celebration_title,
            "gospel": evangelho_data,
            "psalm": salmo_data,
            "url": liturgy_url,
        }

    except Exception as exc:
        log.error(f"Erro ao consultar liturgia diária para {d.strftime('%d/%m/%Y')}: {exc}")
        return None


def collect_gospel_of_day(db: DBManager, target_date: date | None = None) -> dict[str, Any] | None:
    """
    Coleta o Evangelho do Dia e persiste na tabela 'verses' com source='gospel'.
    Retorna o dict pronto com verse_id.
    """
    d = target_date or date.today()
    liturgy = fetch_liturgy_of_day(d)
    if not liturgy or not liturgy.get("gospel", {}).get("text"):
        log.warning("Evangelho não disponível para esta data.")
        return None

    g = liturgy["gospel"]
    ref = f"Evangelho ({g['reference']}) - {d.strftime('%d/%m')}"
    content_hash = _hash_content(f"gospel_{d.isoformat()}_{g['reference']}")

    if db.verse_exists(content_hash):
        row = db.conn.execute("SELECT * FROM verses WHERE hash = ?", (content_hash,)).fetchone()
        log.info(f"Evangelho do dia já coletado: {ref} (ID {row['id']})")
        return {**g, "date_str": liturgy["date_str"], "celebration": liturgy["celebration"], "verse_id": row["id"]}

    verse_id = db.insert_verse(
        source="gospel",
        reference=ref,
        text=g["text"],
        content_hash=content_hash,
        translation=liturgy["celebration"]
    )

    log.info(f"Evangelho do dia registrado no banco com sucesso: {ref} (ID {verse_id})")
    return {**g, "date_str": liturgy["date_str"], "celebration": liturgy["celebration"], "verse_id": verse_id}


def collect_psalm_of_day(db: DBManager, target_date: date | None = None) -> dict[str, Any] | None:
    """
    Coleta o Salmo Responsorial e persiste na tabela 'verses' com source='psalm'.
    """
    d = target_date or date.today()
    liturgy = fetch_liturgy_of_day(d)
    if not liturgy or not liturgy.get("psalm", {}).get("text"):
        return None

    sl = liturgy["psalm"]
    ref = f"Salmo ({sl['reference']}) - {d.strftime('%d/%m')}"
    content_hash = _hash_content(f"psalm_{d.isoformat()}_{sl['reference']}")

    if db.verse_exists(content_hash):
        row = db.conn.execute("SELECT * FROM verses WHERE hash = ?", (content_hash,)).fetchone()
        return {**sl, "date_str": liturgy["date_str"], "celebration": liturgy["celebration"], "verse_id": row["id"]}

    verse_id = db.insert_verse(
        source="psalm",
        reference=ref,
        text=sl["text"],
        content_hash=content_hash,
        translation=sl.get("refrain", "Salmo Responsorial")
    )

    return {**sl, "date_str": liturgy["date_str"], "celebration": liturgy["celebration"], "verse_id": verse_id}


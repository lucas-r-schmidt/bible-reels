"""
src/analytics/metrics_collector.py
----------------------------------
Loop de Métricas e Feedback (Analytics) Litúrgico.
Coleta estatísticas de engajamento diretamente da API do Buffer (YouTube, TikTok, Instagram),
persiste no SQLite e identifica os melhores horários e temas de maior retenção.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config.settings import DB_PATH
from src.processor.db_manager import DBManager
from src.publisher.buffer_api import _gql, list_channels
from src.utils.logger import get_logger

log = get_logger(__name__)


def infer_post_theme(text: str) -> str:
    """Classifica o post dentro dos pilares litúrgicos para análise temática."""
    t = (text or "").lower()
    if any(k in t for k in ("santo do dia", "santa ", "são ", "sao ", "liturgia diária")):
        return "saint"
    if any(k in t for k in ("novena", "campanha")):
        return "novena"
    if any(k in t for k in ("salmo ", "salmos")):
        return "psalm"
    if any(k in t for k in ("evangelho", "boa nova")):
        return "gospel"
    if any(k in t for k in ("oração", "oracao", "prece", "amém", "rezar")):
        return "prayer"
    return "faith"


def parse_post_hour(sent_at_str: str) -> int:
    """Extrai a hora no fuso horário de Brasília (UTC-3)."""
    if not sent_at_str:
        return 12
    try:
        clean_str = sent_at_str.replace("Z", "+00:00")
        dt_utc = datetime.fromisoformat(clean_str)
        # Converte para UTC-3 (Horário de Brasília)
        dt_br = dt_utc.astimezone(timezone(timedelta(hours=-3)))
        return dt_br.hour
    except Exception:
        return 12


def collect_buffer_metrics(db: DBManager | None = None) -> dict[str, Any]:
    """
    Sincroniza todas as métricas de posts enviados via Buffer.
    Grava dados no banco e retorna sumário com rankings e insights.
    """
    close_db = False
    if db is None:
        db = DBManager(DB_PATH)
        close_db = True

    try:
        orgs_data = _gql("query { account { organizations { id name } } }")
        orgs = (orgs_data.get("account") or {}).get("organizations") or []
        if not orgs:
            log.warning("Nenhuma organização encontrada na conta do Buffer.")
            return {}

        org_id = orgs[0]["id"]
        channels = list_channels()
        ch_ids = [c["id"] for c in channels]
        if not ch_ids:
            log.warning("Nenhum canal social conectado no Buffer.")
            return {}

        log.info(f"Coletando métricas do Buffer para {len(ch_ids)} canais...")

        q = f"""
        query {{
          posts(input: {{
            organizationId: "{org_id}",
            filter: {{
              channelIds: {json.dumps(ch_ids)},
              status: [sent]
            }}
          }}) {{
            edges {{
              node {{
                id
                text
                sentAt
                externalLink
                channelService
                metrics {{
                  name
                  value
                  unit
                  type
                  description
                }}
              }}
            }}
          }}
        }}
        """
        res = _gql(q)
        edges = (res.get("posts") or {}).get("edges") or []
        log.info(f"Buffer retornou {len(edges)} posts enviados recentes.")

        synced_count = 0
        for edge in edges:
            node = edge.get("node") or {}
            post_id = node.get("id")
            if not post_id:
                continue

            platform = str(node.get("channelService") or "unknown").lower()
            ext_link = node.get("externalLink") or ""
            sent_at = node.get("sentAt") or ""
            text = node.get("text") or ""
            text_snippet = text.splitlines()[0][:100] if text else ""
            theme = infer_post_theme(text)
            hour_br = parse_post_hour(sent_at)

            # Métricas estruturadas
            views = 0
            likes = 0
            comments = 0
            shares = 0
            reach = 0
            eng_rate = 0.0
            watch_time = 0.0

            raw_metrics = node.get("metrics") or []
            for m in raw_metrics:
                m_type = str(m.get("type") or "").lower()
                m_name = str(m.get("name") or "").lower()
                val = m.get("value") or 0

                if m_type == "views" or "views" in m_name:
                    views = int(val)
                elif m_type == "reactions" or "reaction" in m_name or "like" in m_name:
                    likes = int(val)
                elif m_type == "comments" or "comment" in m_name:
                    comments = int(val)
                elif m_type == "shares" or "share" in m_name:
                    shares = int(val)
                elif m_type == "reach" or "reach" in m_name:
                    reach = int(val)
                elif m_type == "engagementrate" or "eng. rate" in m_name:
                    eng_rate = float(val)
                elif m_type == "totaltimewatched":
                    watch_time = float(val) * 60.0  # minutos para segundos
                elif m_type == "averagetimewatched":
                    if watch_time == 0:
                        watch_time = float(val)

            db.upsert_post_metric(
                buffer_post_id=post_id,
                platform=platform,
                external_link=ext_link,
                sent_at=sent_at,
                text_snippet=text_snippet,
                theme=theme,
                post_hour=hour_br,
                views=views,
                likes=likes,
                comments=comments,
                shares=shares,
                reach=reach,
                engagement_rate=eng_rate,
                watch_time_sec=watch_time,
                raw_metrics=json.dumps(raw_metrics, ensure_ascii=False)
            )
            synced_count += 1

        log.info(f"Sincronização concluída: {synced_count} posts atualizados na base de Analytics.")
        summary = db.get_analytics_summary()
        return summary
    finally:
        if close_db and db:
            db.close()


def print_analytics_report(summary: dict[str, Any]) -> None:
    """Exibe relatório formatado no terminal."""
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    totals = summary.get("totals") or {}
    print("\n" + "=" * 60)
    print("      PAINEL DE ANALYTICS & FEEDBACK LITÚRGICO")
    print("=" * 60)
    print(f"Posts Sincronizados:  {totals.get('total_posts', 0)}")
    print(f"Visualizações Totais: {totals.get('total_views', 0):,}")
    print(f"Reações / Curtidas:   {totals.get('total_likes', 0):,}")
    print(f"Comentários:          {totals.get('total_comments', 0):,}")
    print(f"Compartilhamentos:    {totals.get('total_shares', 0):,}")
    print(f"Taxa Média de Engaj.: {totals.get('avg_engagement_rate') or 0}%")

    print("\n--- Desempenho por Rede Social ---")
    for plat in summary.get("by_platform", []):
        p_name = plat.get("platform", "").upper()
        p_posts = plat.get("posts_count", 0)
        p_views = plat.get("views", 0)
        p_likes = plat.get("likes", 0)
        print(f"- {p_name:<10}: {p_posts} posts | {p_views} views | {p_likes} likes | Engaj.: {plat.get('avg_engagement_rate')}%")

    print("\n--- Ranking por Tema Litúrgico (Melhor Retenção) ---")
    for t in summary.get("themes", []):
        theme_name = t.get("theme", "").capitalize()
        avg_v = t.get("avg_views", 0)
        tot_v = t.get("total_views", 0)
        posts_c = t.get("posts_count", 0)
        print(f"- {theme_name:<10}: {avg_v} views/post (Total: {tot_v} em {posts_c} posts)")

    print("\n--- Melhores Horários de Publicação ---")
    for h in summary.get("hourly", [])[:5]:
        hour = h.get("post_hour", 0)
        avg_v = h.get("avg_views", 0)
        tot_v = h.get("total_views", 0)
        print(f"- {hour:02d}:00h: {avg_v} views/post (Total: {tot_v} views)")

    print("\n--- Top Posts em Engajamento ---")
    for p in summary.get("top_posts", []):
        plat = p.get("platform", "").upper()
        v = p.get("views", 0)
        l = p.get("likes", 0)
        raw_snip = (p.get("text_snippet") or "").strip()
        snip = raw_snip.encode("ascii", errors="replace").decode("ascii")
        link = p.get("external_link") or "Link n/d"
        print(f"[{plat}] {v} views | {l} likes -> {snip}")
        print(f"       Link: {link}")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    summary = collect_buffer_metrics()
    print_analytics_report(summary)

"""
src/community/youtube_client.py
-------------------------------
Cliente para leitura e envio de respostas a comentários via YouTube Data API v3.
"""
from typing import Any
from googleapiclient.discovery import build

from src.community.auth_youtube import get_youtube_credentials
from src.utils.logger import get_logger

log = get_logger("youtube_client")


class YouTubeClient:
    def __init__(self):
        creds = get_youtube_credentials()
        if not creds:
            raise RuntimeError(
                "Credenciais do YouTube não configuradas ou token expirado.\n"
                "Execute: python -m src.community.auth_youtube para autorizar o canal."
            )
        self.service = build("youtube", "v3", credentials=creds, cache_discovery=False)
        self.channel_id, self.channel_title = self._fetch_channel_info()

    def _fetch_channel_info(self) -> tuple[str, str]:
        """Obtém ID e título do canal autenticado."""
        try:
            resp = self.service.channels().list(part="snippet", mine=True).execute()
            items = resp.get("items", [])
            if items:
                ch_id = items[0]["id"]
                title = items[0]["snippet"]["title"]
                log.info(f"Canal do YouTube conectado: {title} (ID: {ch_id})")
                return ch_id, title
        except Exception as exc:
            log.error(f"Erro ao identificar canal do YouTube: {exc}")
        return "", ""

    def get_unanswered_comments(self, max_results: int = 50) -> list[dict[str, Any]]:
        """
        Lista comentários recentes recebidos nos vídeos do canal que ainda não foram respondidos por nós.
        """
        if not self.channel_id:
            return []

        unanswered = []
        try:
            # allThreadsRelatedToChannelId traz comentários de todos os vídeos do canal ordenados por data
            req = self.service.commentThreads().list(
                part="snippet,replies",
                allThreadsRelatedToChannelId=self.channel_id,
                maxResults=max_results,
                order="time"
            )
            resp = req.execute()

            for item in resp.get("items", []):
                snippet = item.get("snippet", {})
                top_comment = snippet.get("topLevelComment", {}).get("snippet", {})
                comment_id = item.get("id") or top_comment.get("id")

                author_channel = top_comment.get("authorChannelId", {}).get("value", "")
                # Ignora se o comentário foi feito pelo próprio canal criador
                if author_channel == self.channel_id:
                    continue

                # Verifica se o nosso canal já respondeu a esta thread
                replies = item.get("replies", {}).get("comments", [])
                already_replied = any(
                    r.get("snippet", {}).get("authorChannelId", {}).get("value") == self.channel_id
                    for r in replies
                )

                if not already_replied:
                    unanswered.append({
                        "comment_id": comment_id,
                        "video_id": snippet.get("videoId", ""),
                        "author_name": top_comment.get("authorDisplayName", "Irmão(ã)"),
                        "text": top_comment.get("textDisplay", "").strip(),
                        "published_at": top_comment.get("publishedAt", ""),
                        "like_count": top_comment.get("likeCount", 0),
                    })

            log.info(f"Comentários novos não respondidos encontrados: {len(unanswered)}")
        except Exception as exc:
            log.error(f"Erro ao buscar comentários do YouTube: {exc}")

        return unanswered

    def reply_to_comment(self, parent_comment_id: str, reply_text: str) -> dict[str, Any] | None:
        """Envia resposta a um comentário específico na thread."""
        try:
            body = {
                "snippet": {
                    "parentId": parent_comment_id,
                    "textOriginal": reply_text
                }
            }
            res = self.service.comments().insert(part="snippet", body=body).execute()
            log.info(f"Resposta publicada no YouTube (Comment #{parent_comment_id})")
            return res
        except Exception as exc:
            log.error(f"Erro ao responder comentário #{parent_comment_id} no YouTube: {exc}")
            return None

"""
src/community/agent.py
----------------------
Agente autônomo de monitoramento e interação em comentários do YouTube Shorts.
"""
import argparse
import random
import time

from config.settings import DB_PATH
from src.community.comment_ai import analyze_and_generate_reply
from src.community.youtube_client import YouTubeClient
from src.processor.db_manager import DBManager
from src.utils.logger import get_logger

log = get_logger("community_agent")


def run_interaction_cycle(limit_per_run: int = 15) -> int:
    """
    Executa um ciclo completo de verificação e resposta aos comentários.
    Retorna o número de comentários respondidos.
    """
    db = DBManager(DB_PATH)
    try:
        try:
            client = YouTubeClient()
        except Exception as exc:
            log.error(f"Não foi possível inicializar YouTubeClient: {exc}")
            return 0

        comments = client.get_unanswered_comments(max_results=limit_per_run * 2)
        if not comments:
            log.info("Nenhum comentário pendente de resposta.")
            return 0

        replied_count = 0
        for item in comments:
            if replied_count >= limit_per_run:
                break

            c_id = item["comment_id"]
            if db.is_comment_processed(c_id):
                continue

            author = item["author_name"]
            text = item["text"]
            log.info(f"Analisando comentário de {author}: '{text[:60]}...'")

            ai_res = analyze_and_generate_reply(author, text)
            sentiment = ai_res.get("sentiment", "general")
            should_reply = ai_res.get("should_reply", True)
            reply_text = ai_res.get("reply_text", "")

            if not should_reply:
                log.info(f"Comentário #{c_id} classificado como {sentiment}. Ignorando resposta.")
                db.log_comment_interaction(
                    platform="youtube",
                    channel_id=client.channel_id,
                    video_id=item["video_id"],
                    comment_id=c_id,
                    author_name=author,
                    comment_text=text,
                    sentiment=sentiment,
                    reply_text="",
                    status="ignored"
                )
                continue

            # Publica resposta no YouTube
            res = client.reply_to_comment(c_id, reply_text)
            if res:
                reply_id = res.get("id", "")
                db.log_comment_interaction(
                    platform="youtube",
                    channel_id=client.channel_id,
                    video_id=item["video_id"],
                    comment_id=c_id,
                    author_name=author,
                    comment_text=text,
                    sentiment=sentiment,
                    reply_text=reply_text,
                    reply_id=reply_id,
                    status="replied"
                )
                replied_count += 1
                log.info(f"✅ Resposta enviada para {author}: '{reply_text}'")

                # Intervalo humanizado entre respostas para segurança anti-spam
                delay = random.uniform(8, 16)
                log.debug(f"Aguardando {delay:.1f}s antes da próxima resposta...")
                time.sleep(delay)
            else:
                db.log_comment_interaction(
                    platform="youtube",
                    channel_id=client.channel_id,
                    video_id=item["video_id"],
                    comment_id=c_id,
                    author_name=author,
                    comment_text=text,
                    sentiment=sentiment,
                    reply_text=reply_text,
                    status="failed"
                )

        log.info(f"Ciclo finalizado. Total de respostas enviadas: {replied_count}")
        return replied_count
    finally:
        db.close()


def run_daemon(interval_minutes: int = 20) -> None:
    """Executa o agente em modo de monitoramento contínuo em segundo plano."""
    log.info(f"Iniciando Agente de Comunidade do YouTube em modo Daemon (Intervalo: {interval_minutes} min)...")
    while True:
        try:
            run_interaction_cycle()
        except Exception as exc:
            log.error(f"Erro inesperado no ciclo do agente: {exc}")

        log.info(f"Próxima checagem em {interval_minutes} minutos.")
        time.sleep(interval_minutes * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="YouTube Community Agent")
    parser.add_argument("--once", action="store_true", help="Executa apenas uma rodada de verificação e encerra")
    parser.add_argument("--daemon", action="store_true", help="Executa como serviço contínuo")
    parser.add_argument("--interval", type=int, default=20, help="Intervalo em minutos no modo daemon")
    args = parser.parse_args()

    if args.daemon:
        run_daemon(interval_minutes=args.interval)
    else:
        run_interaction_cycle()

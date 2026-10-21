"""
src/community/comment_ai.py
---------------------------
Cérebro de IA (Gemini Flash) para moderação, análise de sentimento e geração
de respostas afetuosas, personalizadas e humanizadas para o YouTube Shorts.
"""
import json
import random

from config.settings import GEMINI_API_KEY, GEMINI_MODEL
from src.utils.logger import get_logger

log = get_logger("comment_ai")


FALLBACK_REPLIES = [
    "Amém! Que Deus abençoe grandemente a sua vida e a sua família hoje e sempre! 🙏✨",
    "Glória a Deus! Que a paz que excede todo o entendimento guarde o seu coração! 🙌❤️",
    "Muito obrigado pelo carinho! Que o seu dia seja repleto de paz, saúde e vitórias! 🌟",
    "Amém! Estamos juntos em oração. Permaneça firme e com o coração em Deus! 🙏🕊️",
    "Que bênção ter você aqui conosco! Receba todo o amor e a força do Senhor! ✨🙏",
]


def analyze_and_generate_reply(author_name: str, comment_text: str) -> dict:
    """
    Analisa sentimento do comentário e cria uma resposta fraterna via Gemini.
    Retorna dict com keys: sentiment, should_reply, reply_text.
    """
    clean_author = author_name.strip().lstrip("@") or "Irmão(ã)"

    try:
        import google.generativeai as genai
        if not GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY ausente.")
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel(GEMINI_MODEL)

        prompt = f"""Você é o criador e administrador de um canal cristão e inspiracional de vídeos curtos (YouTube Shorts e Reels).
Um seguidor chamado "{clean_author}" deixou o seguinte comentário em um vídeo:
"{comment_text}"

Sua tarefa:
1. Classifique a intenção do comentário em: "oracao" (pedido de oração/ajuda), "amem" (concordância/glória a Deus), "gratidao" (elogio/agradecimento), "duvida" (pergunta), ou "spam_hater" (links, ofensas, xingamentos ou bots).
2. Se for "spam_hater", defina should_reply como false.
3. Se for genuíno, crie uma resposta acolhedora, carinhosa, fraterna e natural (máximo 140 caracteres).
- Use linguagem calorosa e humana (como um verdadeiro irmão na fé).
- Se for pedido de oração, garanta que está orando por ele(a).
- Se for 'Amém' ou elogio, agradeça e profetize bênçãos sobre o dia dele(a).
- Use 1 ou 2 emojis adequados (ex: 🙏, ✨, 🙌).

Retorne estritamente um JSON com a estrutura:
{{
  "sentiment": "oracao|amem|gratidao|duvida|spam_hater",
  "should_reply": true,
  "reply_text": "Sua resposta aqui"
}}"""

        res = model.generate_content(prompt, generation_config={"response_mime_type": "application/json"})
        data = json.loads(res.text.strip())
        return {
            "sentiment": data.get("sentiment", "general"),
            "should_reply": bool(data.get("should_reply", True)),
            "reply_text": data.get("reply_text", "").strip() or random.choice(FALLBACK_REPLIES),
        }
    except Exception as exc:
        log.warning(f"Falha na IA ao analisar comentário ({exc}). Usando resposta de contingência.")
        # Análise básica de regras se a IA falhar
        lower = comment_text.lower()
        if any(w in lower for w in ("http", "www", ".com", "whatsapp", "crypto", "link", "pix")):
            return {"sentiment": "spam_hater", "should_reply": False, "reply_text": ""}
        return {
            "sentiment": "general",
            "should_reply": True,
            "reply_text": random.choice(FALLBACK_REPLIES),
        }

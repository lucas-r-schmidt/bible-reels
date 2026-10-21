"""
scripts/login_tiktok.py
-----------------------
Abre o navegador para autenticar no TikTok uma única vez e salvar a sessão.
"""
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.publisher.tiktok_direct import setup_tiktok_session

if __name__ == "__main__":
    print("=" * 60)
    print("      CONEXÃO DIRETA COM TIKTOK (PLAYWRIGHT)")
    print("=" * 60)
    print("Abrindo navegador... Faça login na sua conta pessoal do TikTok.")
    print("Dica: Use o QR Code do app do TikTok no celular para entrar em 5 segundos.")
    print("=" * 60)
    success = setup_tiktok_session()
    if success:
        print("\n[SUCESSO] Sessão salva em data/tiktok_session.json!")
        print("Agora o Bible Reels pode postar no TikTok 100% automático em segundo plano.")
    else:
        print("\n[FALHA] Não foi possível salvar a sessão. Tente novamente.")

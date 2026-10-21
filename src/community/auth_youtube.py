"""
src/community/auth_youtube.py
-----------------------------
Autenticação OAuth 2.0 oficial para o YouTube Data API v3.
Gera e armazena o token de acesso + refresh token em config/youtube_token.json.
"""
import os
import sys
import json
from pathlib import Path
from dotenv import load_dotenv

from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

from config.settings import ROOT_DIR
from src.utils.logger import get_logger

log = get_logger("auth_youtube")

load_dotenv(ROOT_DIR / ".env")

SCOPES = ["https://www.googleapis.com/auth/youtube.force-ssl"]
TOKEN_FILE = ROOT_DIR / "config" / "youtube_token.json"
CLIENT_SECRET_FILE = ROOT_DIR / "config" / "client_secret.json"


def get_youtube_credentials() -> Credentials | None:
    """Carrega credenciais existentes com renovação automática de token expirado."""
    creds = None
    if TOKEN_FILE.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
        except Exception as exc:
            log.warning(f"Erro ao ler {TOKEN_FILE.name}: {exc}")

    if creds and creds.expired and creds.refresh_token:
        try:
            log.info("Renovando token OAuth do YouTube expirado...")
            creds.refresh(Request())
            with open(TOKEN_FILE, "w", encoding="utf-8") as f:
                f.write(creds.to_json())
            log.info("Token OAuth do YouTube renovado com sucesso!")
        except Exception as exc:
            log.error(f"Falha ao renovar token OAuth do YouTube: {exc}")
            creds = None

    return creds


def run_oauth_flow(headless: bool = False) -> Credentials:
    """Executa o fluxo de login OAuth 2.0 no navegador ou via console."""
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)

    client_config = None
    if CLIENT_SECRET_FILE.exists():
        flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET_FILE), SCOPES)
    else:
        client_id = os.getenv("YOUTUBE_CLIENT_ID", "").strip()
        client_secret = os.getenv("YOUTUBE_CLIENT_SECRET", "").strip()
        if not client_id or not client_secret:
            raise RuntimeError(
                "Credenciais do YouTube não encontradas!\n"
                "Coloque o arquivo 'client_secret.json' na pasta config/ OU\n"
                "defina YOUTUBE_CLIENT_ID e YOUTUBE_CLIENT_SECRET no .env."
            )
        client_config = {
            "installed": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": ["http://localhost:8088/"]
            }
        }
        flow = InstalledAppFlow.from_client_config(client_config, SCOPES)

    if headless or "--console" in sys.argv:
        log.info("Iniciando fluxo OAuth para console...")
        auth_url, _ = flow.authorization_url(prompt="consent", access_type="offline")
        print("\n" + "=" * 60)
        print(" AUTENTICAÇÃO DO YOUTUBE SHORTS (1-CLIQUE)")
        print("=" * 60)
        print("1. Abra este link no seu navegador:")
        print(f"\n{auth_url}\n")
        print("2. Faça login com a conta do seu canal do YouTube e autorize.")
        print("3. Cole o código ou a URL de redirecionamento completa abaixo:")
        code = input("\nCódigo de autorização: ").strip()
        flow.fetch_token(code=code)
        creds = flow.credentials
    else:
        log.info("Abrindo navegador para autorizar acesso ao canal do YouTube...")
        creds = flow.run_local_server(port=8088, prompt="consent", access_type="offline")

    with open(TOKEN_FILE, "w", encoding="utf-8") as f:
        f.write(creds.to_json())

    log.info(f"Token do YouTube salvo com sucesso em: {TOKEN_FILE}")
    return creds


if __name__ == "__main__":
    print("\n=== Verificação de Credenciais do YouTube ===")
    existing = get_youtube_credentials()
    if existing and existing.valid:
        print("✅ Credenciais válidas encontradas em config/youtube_token.json!")
    else:
        print("Iniciando fluxo de login...")
        creds = run_oauth_flow(headless="--headless" in sys.argv or "--console" in sys.argv)
        print("✅ Concluído com sucesso!")

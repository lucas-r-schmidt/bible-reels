"""
web_server.py — Inicializador do servidor web do Bible Reels.
"""
import sys
import webbrowser
from src.web.server import run_web_server

if __name__ == "__main__":
    port = 5000
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        port = int(sys.argv[1])
    
    url = f"http://localhost:{port}"
    print(f"\n========================================================")
    print(f"      BIBLE REELS — PAINEL VISUAL DE AUTOMAÇÃO          ")
    print(f"========================================================")
    print(f" Servidor rodando em: {url}")
    print(f" Pressione Ctrl+C no terminal para parar o servidor.\n")
    
    # Abre navegador automaticamente se não for headless
    if "--no-browser" not in sys.argv:
        try:
            webbrowser.open(url)
        except Exception:
            pass
            
    run_web_server(port)

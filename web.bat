@echo off
setlocal
title Bible Reels Studio — Painel Visual

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [ERRO] Ambiente virtual .venv nao encontrado!
    echo Crie o venv e instale as dependencias antes de executar.
    pause
    exit /b 1
)

echo Iniciando Painel Visual no navegador...
.venv\Scripts\python.exe web_server.py

pause

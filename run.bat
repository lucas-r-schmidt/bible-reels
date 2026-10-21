@echo off
setlocal
title Bible Reels Automator

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [ERRO] Ambiente virtual .venv nao encontrado!
    echo Crie o venv e instale as dependencias antes de executar.
    pause
    exit /b 1
)

if not "%~1"=="" (
    .venv\Scripts\python.exe main.py %*
    exit /b %ERRORLEVEL%
)

:menu
cls
echo ========================================================
echo               BIBLE REELS AUTOMATION ENGINE             
echo ========================================================
echo.
echo [0] Abrir Painel Visual no Navegador (Web Dashboard)
echo [1] Executar Completo (Video + n8n Webhook - Padrao)
echo [2] Executar Completo (Video + Postproxy)
echo [3] Executar Somente Imagens (n8n Webhook)
echo [4] Listar Perfis Conectados no Postproxy
echo [5] Iniciar Daemon Diario (06:00 e 18:00)
echo [6] Conectar / Fazer Login no TikTok (Playwright)
echo [7] Conectar Canal do YouTube (OAuth 2.0)
echo [8] Iniciar Agente de Comentarios do YouTube
echo [9] Sair
echo.
set /p opcao="Escolha uma opcao [0-9]: "

if "%opcao%"=="0" goto op0
if "%opcao%"=="1" goto op1
if "%opcao%"=="2" goto op2
if "%opcao%"=="3" goto op3
if "%opcao%"=="4" goto op4
if "%opcao%"=="5" goto op5
if "%opcao%"=="6" goto op6
if "%opcao%"=="7" goto op7
if "%opcao%"=="8" goto op8
if "%opcao%"=="9" goto fim
goto menu

:op0
echo.
echo Abrindo Painel Visual...
.venv\Scripts\python.exe web_server.py
goto pausa

:op1
echo.
echo Executando pipeline completo com video para n8n (Webhook)...
.venv\Scripts\python.exe main.py --all --video --publisher webhook
goto pausa

:op2
echo.
echo Executando pipeline completo com video para Postproxy...
.venv\Scripts\python.exe main.py --all --video --publisher postproxy
goto pausa

:op3
echo.
echo Executando pipeline de imagens para n8n...
.venv\Scripts\python.exe main.py --all --publisher webhook
goto pausa

:op4
echo.
echo Consultando perfis Postproxy...
.venv\Scripts\python.exe main.py --list-profiles
goto pausa

:op5
echo.
echo Iniciando daemon diario (06:00 e 18:00 com video e n8n)...
.venv\Scripts\python.exe main.py --daemon --video --publisher webhook
goto pausa

:op6
echo.
.venv\Scripts\python.exe scripts/login_tiktok.py
goto pausa

:op7
echo.
echo Conectando ao canal do YouTube via Google OAuth...
.venv\Scripts\python.exe -m src.community.auth_youtube
goto pausa

:op8
echo.
echo Iniciando Agente de Comentarios do YouTube (verificando a cada 20 min)...
.venv\Scripts\python.exe -m src.community.agent --daemon --interval 20
goto pausa

:pausa
echo.
pause
goto menu

:fim
exit /b 0

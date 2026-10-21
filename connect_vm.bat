@echo off
setlocal

set "SSH_KEY=C:\Users\Lucas\Documents\Oracle Cloud 2CPU\ssh-key-2026-09-25.key"
set "SSH_TARGET=ubuntu@157.151.28.236"

where ssh >nul 2>&1
if errorlevel 1 (
    echo OpenSSH nao foi encontrado. Verifique se o cliente SSH esta instalado.
    pause
    exit /b 1
)

if not exist "%SSH_KEY%" (
    echo Chave SSH nao encontrada:
    echo "%SSH_KEY%"
    pause
    exit /b 1
)

ssh -i "%SSH_KEY%" %SSH_TARGET%
exit /b %ERRORLEVEL%

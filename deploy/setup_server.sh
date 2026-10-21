#!/usr/bin/env bash
# =============================================================================
# Setup automatizado do Bible Reels no servidor Linux (Oracle Cloud Ubuntu/Debian)
# =============================================================================

set -e

echo "=== [1/4] Atualizando pacotes do sistema e instalando dependências ==="
sudo apt-get update -y
sudo apt-get install -y python3 python3-pip python3-venv ffmpeg git curl

echo "=== [2/4] Ajustando fuso horário para Brasília (America/Sao_Paulo) ==="
sudo timedatectl set-timezone America/Sao_Paulo

echo "=== [3/4] Criando ambiente virtual Python e instalando dependências ==="
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/playwright install --with-deps chromium

echo "=== [4/4] Criando diretórios necessários ==="
mkdir -p data/db data/audio logs output/images output/videos output/queue

echo "=== [5/5] Configurando serviço Systemd para execução autônoma ==="
sudo cp deploy/bible-reels-scheduler.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable bible-reels-scheduler.service

echo ""
echo "=========================================================="
echo " Instalação concluída com sucesso!"
echo " Para iniciar o agendador autônomo agora: sudo systemctl start bible-reels-scheduler"
echo " Para ver logs: journalctl -u bible-reels-scheduler -f"
echo " Horário do servidor configurado para: $(date)"
echo "=========================================================="

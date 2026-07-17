#!/usr/bin/env bash
# Provisiona o backend do StormWatch numa VM Ubuntu (Oracle Always Free, ARM).
# Rode a partir de ~/storm-watch/backend:  bash ../infra/oracle/setup.sh
set -euo pipefail

echo "==> Criando 2 GB de swap (importante na VM de 1 GB - E2.1.Micro)"
if ! sudo swapon --show | grep -q /swapfile; then
  sudo fallocate -l 2G /swapfile
  sudo chmod 600 /swapfile
  sudo mkswap /swapfile
  sudo swapon /swapfile
  echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
fi

echo "==> Instalando dependências do sistema"
sudo apt-get update
sudo apt-get install -y python3-venv python3-pip git

echo "==> Criando ambiente virtual e instalando pacotes Python"
python3 -m venv .venv
.venv/bin/pip install --upgrade pip wheel
# netCDF4 e opencv-python-headless têm wheels para ARM64 (aarch64); instala direto.
# Se o build do netCDF4 falhar, rode antes:
#   sudo apt-get install -y libhdf5-dev libnetcdf-dev
.venv/bin/pip install -r requirements.txt

echo "==> Gerando chaves VAPID (copie para o .env)"
.venv/bin/python scripts/gen_vapid.py

cat <<'MSG'

Dependências instaladas.

Próximos passos:
  1. cp .env.example .env  e cole as chaves VAPID acima + ajuste CORS_ORIGINS.
  2. Instale o serviço systemd:
       sudo cp ../infra/oracle/stormwatch.service /etc/systemd/system/
       sudo systemctl daemon-reload
       sudo systemctl enable --now stormwatch
       systemctl status stormwatch
  3. Teste local na VM:  curl http://127.0.0.1:8000/health
  4. Exponha via Cloudflare Tunnel (ver infra/oracle/DEPLOY_ORACLE.md).
MSG

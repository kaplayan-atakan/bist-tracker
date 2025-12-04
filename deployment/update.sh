#!/usr/bin/env bash
# =============================================================================
# BİST Trading Bot - Update Script
# =============================================================================
#
# git pull yaptıktan sonra tek komutla bot'u günceller:
# - Yeni bağımlılıkları yükler
# - İzinleri düzeltir
# - Servisi yeniden başlatır
#
# Kullanım:
#   cd /home/botuser/bist-tracker
#   git pull
#   sudo bash deployment/update.sh
#
# =============================================================================

set -euo pipefail

# =============================================================================
# Configuration
# =============================================================================

BOT_USER="botuser"
BOT_GROUP="botuser"
INSTALL_DIR="/home/${BOT_USER}/bist-tracker"
WORKING_DIR="${INSTALL_DIR}/core-src"
VENV_DIR="${INSTALL_DIR}/.venv"
PIP_BIN="${VENV_DIR}/bin/pip"
SERVICE_NAME="bist-trading-bot"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }
step()  { echo -e "${BLUE}[STEP]${NC} $1"; }

# =============================================================================
# Main
# =============================================================================

echo ""
echo -e "${GREEN}=============================================${NC}"
echo -e "${GREEN}  BİST Trading Bot - Update Script           ${NC}"
echo -e "${GREEN}=============================================${NC}"
echo ""

# Root kontrolü
if [[ $EUID -ne 0 ]]; then
    error "Bu script root olarak çalıştırılmalıdır: sudo bash $0"
fi

# Kurulum dizini kontrolü
if [[ ! -f "${WORKING_DIR}/main.py" ]]; then
    error "main.py bulunamadı: ${WORKING_DIR}/main.py"
fi

# 1. Bağımlılıkları güncelle
step "[1/4] Python bağımlılıkları güncelleniyor..."
if [[ -f "${WORKING_DIR}/requirements.txt" ]]; then
    sudo -u "${BOT_USER}" "${PIP_BIN}" install -r "${WORKING_DIR}/requirements.txt" -q
    info "Bağımlılıklar güncellendi"
else
    warn "requirements.txt bulunamadı"
fi

# 2. Log dizinlerini kontrol et
step "[2/4] Dizinler kontrol ediliyor..."
mkdir -p "${INSTALL_DIR}/logs"
mkdir -p "${WORKING_DIR}/logs"
info "Log dizinleri hazır"

# 3. İzinleri düzelt
step "[3/4] İzinler düzeltiliyor..."
chown -R "${BOT_USER}:${BOT_GROUP}" "${INSTALL_DIR}"
chmod +x "${INSTALL_DIR}/deployment/"*.sh 2>/dev/null || true
info "İzinler düzeltildi"

# 4. Servisi yeniden başlat
step "[4/4] Servis yeniden başlatılıyor..."
systemctl daemon-reload
systemctl restart "${SERVICE_NAME}"

sleep 3

if systemctl is-active --quiet "${SERVICE_NAME}"; then
    info "✅ Servis başarıyla güncellendi ve çalışıyor!"
else
    warn "⚠️ Servis başlatılamadı!"
    warn "   Kontrol: sudo journalctl -u ${SERVICE_NAME} -n 50"
fi

echo ""
echo -e "${GREEN}=============================================${NC}"
echo -e "${GREEN}  Güncelleme Tamamlandı!                     ${NC}"
echo -e "${GREEN}=============================================${NC}"
echo ""
echo "  Log izleme:"
echo "    tail -f ${INSTALL_DIR}/logs/bot.log"
echo "    sudo journalctl -u ${SERVICE_NAME} -f"
echo ""
echo -e "  Türkiye saati: ${YELLOW}$(TZ=Europe/Istanbul date '+%Y-%m-%d %H:%M:%S')${NC}"
echo ""

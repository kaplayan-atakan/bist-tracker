#!/usr/bin/env bash
# =============================================================================
# BİST Trading Bot - Uninstall Script
# =============================================================================
#
# Servisi kaldırır. Bot dosyaları ve kullanıcı hesabı silinmez.
#
# Kullanım: sudo bash deployment/uninstall_service.sh
#
# =============================================================================

set -euo pipefail

# Configuration
SERVICE_NAME="bist-trading-bot"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
LOGROTATE_FILE="/etc/logrotate.d/${SERVICE_NAME}"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info() { echo -e "${GREEN}[INFO]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }

# =============================================================================
# Main
# =============================================================================

echo ""
echo -e "${YELLOW}=============================================${NC}"
echo -e "${YELLOW}  BİST Trading Bot - Uninstall Script        ${NC}"
echo -e "${YELLOW}=============================================${NC}"
echo ""

# Root kontrolü
if [[ $EUID -ne 0 ]]; then
    echo -e "${RED}Bu script root olarak çalıştırılmalıdır: sudo bash $0${NC}"
    exit 1
fi

# 1. Servisi durdur
info "Servis durduruluyor..."
systemctl stop "${SERVICE_NAME}" 2>/dev/null || true

# 2. Servisi devre dışı bırak
info "Servis devre dışı bırakılıyor..."
systemctl disable "${SERVICE_NAME}" 2>/dev/null || true

# 3. Service dosyasını sil
info "Service dosyası siliniyor..."
rm -f "${SERVICE_FILE}"

# 4. Logrotate config'ini sil
info "Logrotate config siliniyor..."
rm -f "${LOGROTATE_FILE}"

# 5. Systemd'yi yenile
info "Systemd yenileniyor..."
systemctl daemon-reload

echo ""
echo -e "${GREEN}=============================================${NC}"
echo -e "${GREEN}  Servis Başarıyla Kaldırıldı                ${NC}"
echo -e "${GREEN}=============================================${NC}"
echo ""
echo "  Not: Bot dosyaları ve kullanıcı hesabı silinmedi."
echo ""
echo "  Tamamen silmek için:"
echo "    sudo rm -rf /home/botuser/bist-tracker"
echo "    sudo userdel -r botuser"
echo ""

#!/bin/bash
#
# BİST Trading Bot - Servis Kaldırma Scripti
#
# Kullanım:
#   chmod +x uninstall_service.sh
#   sudo ./uninstall_service.sh
#

set -e

# Renkli çıktı
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${YELLOW}=============================================${NC}"
echo -e "${YELLOW}  BİST Trading Bot - Servis Kaldırma         ${NC}"
echo -e "${YELLOW}=============================================${NC}"

# Root kontrolü
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}Lütfen root olarak çalıştırın: sudo ./uninstall_service.sh${NC}"
    exit 1
fi

SERVICE_NAME="bist-trading-bot"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

echo ""
echo -e "${YELLOW}[1/3] Servis durduruluyor...${NC}"
if systemctl is-active --quiet ${SERVICE_NAME}; then
    systemctl stop ${SERVICE_NAME}
    echo "  Servis durduruldu"
else
    echo "  Servis zaten çalışmıyor"
fi

echo ""
echo -e "${YELLOW}[2/3] Servis devre dışı bırakılıyor...${NC}"
if systemctl is-enabled --quiet ${SERVICE_NAME} 2>/dev/null; then
    systemctl disable ${SERVICE_NAME}
    echo "  Servis devre dışı bırakıldı"
else
    echo "  Servis zaten devre dışı"
fi

echo ""
echo -e "${YELLOW}[3/3] Servis dosyası siliniyor...${NC}"
if [ -f "${SERVICE_FILE}" ]; then
    rm ${SERVICE_FILE}
    systemctl daemon-reload
    echo "  Servis dosyası silindi"
else
    echo "  Servis dosyası bulunamadı"
fi

echo ""
echo -e "${GREEN}=============================================${NC}"
echo -e "${GREEN}  Servis Başarıyla Kaldırıldı               ${NC}"
echo -e "${GREEN}=============================================${NC}"
echo ""
echo "  Not: Bot dosyaları ve kullanıcı hesabı silinmedi."
echo ""
echo "  Tamamen silmek için:"
echo "    sudo rm -rf /home/botuser/bist-tracker"
echo "    sudo userdel -r botuser"
echo ""

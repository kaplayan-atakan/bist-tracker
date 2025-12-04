#!/bin/bash
#
# BİST Trading Bot - VPS Kurulum Scripti
# Ubuntu 20.04+ için test edilmiştir.
#
# Kullanım:
#   chmod +x install_service.sh
#   sudo ./install_service.sh
#

set -e  # Hata durumunda dur

# Renkli çıktı
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}=============================================${NC}"
echo -e "${GREEN}  BİST Trading Bot - VPS Kurulum Scripti    ${NC}"
echo -e "${GREEN}=============================================${NC}"

# Root kontrolü
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}Lütfen root olarak çalıştırın: sudo ./install_service.sh${NC}"
    exit 1
fi

# Değişkenler
BOT_USER="botuser"
BOT_HOME="/home/${BOT_USER}"
BOT_DIR="${BOT_HOME}/bist-tracker"
VENV_DIR="${BOT_DIR}/.venv"
LOGS_DIR="${BOT_DIR}/logs"
SERVICE_NAME="bist-trading-bot"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo ""
echo -e "${YELLOW}[1/8] Sistem güncelleniyor...${NC}"
apt update -q

echo ""
echo -e "${YELLOW}[2/8] Gerekli paketler yükleniyor...${NC}"
apt install -y python3 python3-pip python3-venv git curl

echo ""
echo -e "${YELLOW}[3/8] Bot kullanıcısı kontrol ediliyor...${NC}"
if id "${BOT_USER}" &>/dev/null; then
    echo "  Kullanıcı '${BOT_USER}' zaten mevcut"
else
    echo "  Kullanıcı '${BOT_USER}' oluşturuluyor..."
    useradd -m -s /bin/bash ${BOT_USER}
    echo "  Kullanıcı oluşturuldu"
fi

echo ""
echo -e "${YELLOW}[4/8] Dizin yapısı oluşturuluyor...${NC}"
mkdir -p ${BOT_DIR}
mkdir -p ${LOGS_DIR}

# Bot dosyalarını kopyala (eğer script bot dizininden çalıştırılıyorsa)
if [ -d "${SCRIPT_DIR}/../core-src" ]; then
    echo "  Bot dosyaları kopyalanıyor..."
    cp -r ${SCRIPT_DIR}/../core-src ${BOT_DIR}/
    chown -R ${BOT_USER}:${BOT_USER} ${BOT_DIR}
    echo "  Dosyalar kopyalandı"
else
    echo -e "${YELLOW}  Not: Bot dosyaları manuel olarak ${BOT_DIR}/core-src dizinine kopyalanmalı${NC}"
fi

echo ""
echo -e "${YELLOW}[5/8] Python virtual environment oluşturuluyor...${NC}"
if [ -d "${VENV_DIR}" ]; then
    echo "  Virtual environment zaten mevcut, atlanıyor..."
else
    sudo -u ${BOT_USER} python3 -m venv ${VENV_DIR}
    echo "  Virtual environment oluşturuldu"
fi

echo ""
echo -e "${YELLOW}[6/8] Python paketleri yükleniyor...${NC}"
if [ -f "${BOT_DIR}/core-src/requirements.txt" ]; then
    sudo -u ${BOT_USER} ${VENV_DIR}/bin/pip install --upgrade pip
    sudo -u ${BOT_USER} ${VENV_DIR}/bin/pip install -r ${BOT_DIR}/core-src/requirements.txt
    echo "  Paketler yüklendi"
else
    echo -e "${YELLOW}  Uyarı: requirements.txt bulunamadı${NC}"
fi

echo ""
echo -e "${YELLOW}[7/8] Systemd servisi yükleniyor...${NC}"
cp ${SCRIPT_DIR}/bist-trading-bot.service ${SERVICE_FILE}

# Servisi yeniden yükle
systemctl daemon-reload
systemctl enable ${SERVICE_NAME}
echo "  Servis yüklendi ve etkinleştirildi"

echo ""
echo -e "${YELLOW}[8/8] Dizin izinleri ayarlanıyor...${NC}"
chown -R ${BOT_USER}:${BOT_USER} ${BOT_DIR}
chmod 750 ${BOT_DIR}
chmod 750 ${LOGS_DIR}
echo "  İzinler ayarlandı"

echo ""
echo -e "${GREEN}=============================================${NC}"
echo -e "${GREEN}  Kurulum Tamamlandı!                        ${NC}"
echo -e "${GREEN}=============================================${NC}"
echo ""
echo "  Sonraki Adımlar:"
echo "  ----------------"
echo ""
echo "  1. Telegram ayarlarını yapılandırın:"
echo "     sudo nano /etc/systemd/system/${SERVICE_NAME}.service"
echo "     # TELEGRAM_BOT_TOKEN ve TELEGRAM_CHAT_ID satırlarını düzenleyin"
echo ""
echo "  2. Servisi başlatın:"
echo "     sudo systemctl start ${SERVICE_NAME}"
echo ""
echo "  3. Durumu kontrol edin:"
echo "     sudo systemctl status ${SERVICE_NAME}"
echo ""
echo "  4. Logları izleyin:"
echo "     sudo journalctl -u ${SERVICE_NAME} -f"
echo "     veya"
echo "     tail -f ${LOGS_DIR}/bot.log"
echo ""
echo "  5. Servisi durdurmak için:"
echo "     sudo systemctl stop ${SERVICE_NAME}"
echo ""
echo -e "${GREEN}Türkiye saati: $(TZ=Europe/Istanbul date '+%Y-%m-%d %H:%M:%S')${NC}"

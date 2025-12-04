#!/usr/bin/env bash
# =============================================================================
# BİST Trading Bot - VPS Installation Script
# =============================================================================
# 
# Production-ready kurulum scripti. Tüm deployment tecrübeleri dahil edilmiştir:
# - İzin sorunları çözüldü (botuser:botuser ownership)
# - Tüm log dizinleri oluşturuluyor
# - Basitleştirilmiş systemd service dosyası
# - Mutlak Python path kullanımı
#
# Kullanım:
#   1. Repo'yu /home/botuser/bist-tracker dizinine klonla
#   2. sudo bash deployment/install_service.sh
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
PYTHON_BIN="${VENV_DIR}/bin/python"
PIP_BIN="${VENV_DIR}/bin/pip"
SERVICE_NAME="bist-trading-bot"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
LOGROTATE_FILE="/etc/logrotate.d/${SERVICE_NAME}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# =============================================================================
# Helper Functions
# =============================================================================

info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }
step()  { echo -e "${BLUE}[STEP]${NC} $1"; }

print_banner() {
    echo ""
    echo -e "${GREEN}=============================================${NC}"
    echo -e "${GREEN}  BİST Trading Bot - Installation Script     ${NC}"
    echo -e "${GREEN}=============================================${NC}"
    echo ""
}

# =============================================================================
# Pre-flight Checks
# =============================================================================

check_root() {
    if [[ $EUID -ne 0 ]]; then
        error "Bu script root olarak çalıştırılmalıdır: sudo bash $0"
    fi
}

check_user_exists() {
    if ! id "${BOT_USER}" &>/dev/null; then
        info "Kullanıcı '${BOT_USER}' oluşturuluyor..."
        useradd -m -s /bin/bash "${BOT_USER}"
        info "Kullanıcı oluşturuldu"
    else
        info "Kullanıcı '${BOT_USER}' zaten mevcut"
    fi
}

check_install_dir() {
    if [[ ! -d "${INSTALL_DIR}" ]]; then
        error "Kurulum dizini bulunamadı: ${INSTALL_DIR}\nÖnce repo'yu klonlayın: git clone <repo> ${INSTALL_DIR}"
    fi
    if [[ ! -f "${WORKING_DIR}/main.py" ]]; then
        error "main.py bulunamadı: ${WORKING_DIR}/main.py"
    fi
    info "Kurulum dizini doğrulandı: ${INSTALL_DIR}"
}

# =============================================================================
# Installation Steps
# =============================================================================

install_system_deps() {
    step "[1/7] Sistem bağımlılıkları yükleniyor..."
    apt-get update -qq
    apt-get install -y -qq python3 python3-pip python3-venv git curl > /dev/null 2>&1
    info "Sistem bağımlılıkları yüklendi"
}

create_directories() {
    step "[2/7] Dizinler oluşturuluyor..."
    
    # Ana log dizini (systemd çıktısı için)
    mkdir -p "${INSTALL_DIR}/logs"
    
    # Core-src log dizini (scan_errors.log, bist_bot.log için)
    mkdir -p "${WORKING_DIR}/logs"
    
    info "Dizinler oluşturuldu:"
    info "  - ${INSTALL_DIR}/logs"
    info "  - ${WORKING_DIR}/logs"
}

setup_venv() {
    step "[3/7] Python virtual environment kuruluyor..."
    
    if [[ ! -d "${VENV_DIR}" ]]; then
        sudo -u "${BOT_USER}" python3 -m venv "${VENV_DIR}"
        info "Virtual environment oluşturuldu: ${VENV_DIR}"
    else
        info "Virtual environment zaten mevcut"
    fi
    
    info "Python bağımlılıkları yükleniyor..."
    sudo -u "${BOT_USER}" "${PIP_BIN}" install --upgrade pip -q
    
    if [[ -f "${WORKING_DIR}/requirements.txt" ]]; then
        sudo -u "${BOT_USER}" "${PIP_BIN}" install -r "${WORKING_DIR}/requirements.txt" -q
        info "Bağımlılıklar yüklendi"
    else
        warn "requirements.txt bulunamadı: ${WORKING_DIR}/requirements.txt"
    fi
}

fix_permissions() {
    step "[4/7] Dosya izinleri ayarlanıyor..."
    
    # Tüm dosyaları botuser'a ata
    chown -R "${BOT_USER}:${BOT_GROUP}" "${INSTALL_DIR}"
    
    # Çalıştırılabilir scriptler
    chmod +x "${INSTALL_DIR}/deployment/"*.sh 2>/dev/null || true
    
    # Dizin izinleri
    chmod 755 "${INSTALL_DIR}"
    chmod 755 "${INSTALL_DIR}/logs"
    chmod 755 "${WORKING_DIR}/logs"
    
    info "İzinler ayarlandı (owner: ${BOT_USER}:${BOT_GROUP})"
}

create_service() {
    step "[5/7] Systemd servisi oluşturuluyor..."
    
    # Basit, test edilmiş service dosyası
    cat << EOF > "${SERVICE_FILE}"
[Unit]
Description=BIST Trading Bot - Automated Stock Scanner
After=network.target

[Service]
Type=simple
User=${BOT_USER}
Group=${BOT_GROUP}
WorkingDirectory=${WORKING_DIR}
Environment=PYTHONUNBUFFERED=1
Environment=TZ=Europe/Istanbul
ExecStart=${PYTHON_BIN} main.py
Restart=on-failure
RestartSec=30
StandardOutput=append:${INSTALL_DIR}/logs/bot.log
StandardError=append:${INSTALL_DIR}/logs/error.log

[Install]
WantedBy=multi-user.target
EOF

    info "Service dosyası oluşturuldu: ${SERVICE_FILE}"
}

setup_logrotate() {
    step "[6/7] Log rotation ayarlanıyor..."
    
    cat << EOF > "${LOGROTATE_FILE}"
${INSTALL_DIR}/logs/*.log {
    daily
    rotate 14
    compress
    delaycompress
    missingok
    notifempty
    create 0640 ${BOT_USER} ${BOT_GROUP}
}

${WORKING_DIR}/logs/*.log {
    daily
    rotate 14
    compress
    delaycompress
    missingok
    notifempty
    create 0640 ${BOT_USER} ${BOT_GROUP}
}
EOF

    info "Log rotation yapılandırıldı: ${LOGROTATE_FILE}"
}

enable_service() {
    step "[7/7] Servis etkinleştiriliyor..."
    
    systemctl daemon-reload
    systemctl enable "${SERVICE_NAME}"
    
    # Eğer servis zaten çalışıyorsa restart, değilse start
    if systemctl is-active --quiet "${SERVICE_NAME}"; then
        systemctl restart "${SERVICE_NAME}"
        info "Servis yeniden başlatıldı"
    else
        systemctl start "${SERVICE_NAME}"
        info "Servis başlatıldı"
    fi
    
    # Durumu kontrol et
    sleep 3
    
    if systemctl is-active --quiet "${SERVICE_NAME}"; then
        info "✅ Servis başarıyla çalışıyor!"
    else
        warn "⚠️ Servis başlatılamadı. Kontrol edin:"
        warn "   sudo journalctl -u ${SERVICE_NAME} -n 50"
        warn "   sudo ${PYTHON_BIN} ${WORKING_DIR}/main.py"
    fi
}

# =============================================================================
# Summary
# =============================================================================

print_summary() {
    echo ""
    echo -e "${GREEN}=============================================${NC}"
    echo -e "${GREEN}  Kurulum Tamamlandı!                        ${NC}"
    echo -e "${GREEN}=============================================${NC}"
    echo ""
    echo "  Servis: ${SERVICE_NAME}"
    echo "  Kullanıcı: ${BOT_USER}"
    echo "  Dizin: ${INSTALL_DIR}"
    echo "  Loglar:"
    echo "    - ${INSTALL_DIR}/logs/bot.log"
    echo "    - ${INSTALL_DIR}/logs/error.log"
    echo "    - ${WORKING_DIR}/logs/bist_bot.log"
    echo ""
    echo "  Yönetim Komutları:"
    echo "    sudo systemctl status ${SERVICE_NAME}"
    echo "    sudo systemctl restart ${SERVICE_NAME}"
    echo "    sudo systemctl stop ${SERVICE_NAME}"
    echo "    sudo journalctl -u ${SERVICE_NAME} -f"
    echo ""
    echo "  Log İzleme:"
    echo "    tail -f ${INSTALL_DIR}/logs/bot.log"
    echo "    tail -f ${WORKING_DIR}/logs/bist_bot.log"
    echo ""
    echo -e "  Türkiye saati: ${YELLOW}$(TZ=Europe/Istanbul date '+%Y-%m-%d %H:%M:%S')${NC}"
    echo ""
}

# =============================================================================
# Main
# =============================================================================

main() {
    print_banner
    
    # Pre-flight checks
    check_root
    check_user_exists
    check_install_dir
    
    # Installation
    install_system_deps
    create_directories
    setup_venv
    fix_permissions
    create_service
    setup_logrotate
    enable_service
    
    # Done
    print_summary
}

main "$@"

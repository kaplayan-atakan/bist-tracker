#!/usr/bin/env bash
# =============================================================================
# BİST Tracker - Update Script
# =============================================================================
# Canonical unit files in repo, copied to /etc/systemd/system/ on every run.
#
# Usage:
#   cd /home/botuser/bist-tracker
#   git pull
#   sudo bash deployment/update.sh
# =============================================================================

set -euo pipefail

# =============================================================================
# Constants
# =============================================================================

BOT_USER="botuser"
INSTALL_DIR="/home/botuser/bist-tracker"
VENV="${INSTALL_DIR}/.venv"
PYTHON="${VENV}/bin/python"
PIP="${VENV}/bin/pip"
SERVICE_DIR="/etc/systemd/system"

SERVICES=("bist-trading-bot" "bist-pmr-bot")

# =============================================================================
# Helpers
# =============================================================================

info()  { echo "[INFO] $1"; }
ok()    { echo "[OK]   $1"; }
err()   { echo "[ERROR] $1" >&2; exit 1; }

# =============================================================================
# Validations
# =============================================================================

echo ""
echo "==========================================="
echo "  BİST Tracker - Update Script"
echo "==========================================="
echo ""

# Must be root
if [[ $EUID -ne 0 ]]; then
    err "Bu script root olarak çalıştırılmalı: sudo bash $0"
fi

# Check install dir
if [[ ! -d "${INSTALL_DIR}" ]]; then
    err "Kurulum dizini bulunamadı: ${INSTALL_DIR}"
fi

# Check Python
if [[ ! -x "${PYTHON}" ]]; then
    err "Python bulunamadı: ${PYTHON} - Önce venv oluşturun."
fi

info "Validations passed"

# =============================================================================
# 1. Ensure log directories
# =============================================================================

info "[1/6] Log dizinleri oluşturuluyor..."

mkdir -p "${INSTALL_DIR}/logs"
mkdir -p "${INSTALL_DIR}/core-src/logs"
chown -R "${BOT_USER}:${BOT_USER}" "${INSTALL_DIR}/logs"
chown -R "${BOT_USER}:${BOT_USER}" "${INSTALL_DIR}/core-src/logs"

ok "Log dizinleri hazır"

# =============================================================================
# 2. Install Python dependencies
# =============================================================================

info "[2/6] Python bağımlılıkları yükleniyor..."

CORE_REQ="${INSTALL_DIR}/core-src/requirements.txt"
PMR_REQ="${INSTALL_DIR}/pmr/requirements.txt"

if [[ ! -f "${CORE_REQ}" ]]; then
    err "Eksik: ${CORE_REQ}"
fi

if [[ ! -f "${PMR_REQ}" ]]; then
    err "Eksik: ${PMR_REQ}"
fi

sudo -u "${BOT_USER}" "${PIP}" install -q -r "${CORE_REQ}"
sudo -u "${BOT_USER}" "${PIP}" install -q -r "${PMR_REQ}"

ok "Python bağımlılıkları yüklendi"

# =============================================================================
# 3. Fix permissions
# =============================================================================

info "[3/6] İzinler düzeltiliyor..."

chown -R "${BOT_USER}:${BOT_USER}" "${INSTALL_DIR}"
chmod +x "${INSTALL_DIR}/deployment/"*.sh 2>/dev/null || true

ok "İzinler düzeltildi"

# =============================================================================
# 4. Copy canonical unit files
# =============================================================================

info "[4/6] Service dosyaları kopyalanıyor..."

cp "${INSTALL_DIR}/deployment/bist-trading-bot.service" "${SERVICE_DIR}/bist-trading-bot.service"
chmod 0644 "${SERVICE_DIR}/bist-trading-bot.service"

cp "${INSTALL_DIR}/deployment/bist-pmr-bot.service" "${SERVICE_DIR}/bist-pmr-bot.service"
chmod 0644 "${SERVICE_DIR}/bist-pmr-bot.service"

ok "Unit dosyaları ${SERVICE_DIR}/ içine kopyalandı"

# =============================================================================
# 5. Reload systemd and restart services
# =============================================================================

info "[5/6] Systemd yeniden yükleniyor ve servisler başlatılıyor..."

systemctl daemon-reload

for svc in "${SERVICES[@]}"; do
    systemctl enable "${svc}" --quiet 2>/dev/null || true
    systemctl restart "${svc}"
done

ok "Servisler yeniden başlatıldı"

# =============================================================================
# 6. Health check
# =============================================================================

info "[6/6] Sağlık kontrolü..."

FAILED=0

for svc in "${SERVICES[@]}"; do
    if systemctl is-active --quiet "${svc}"; then
        ok "${svc} çalışıyor ✓"
    else
        echo ""
        echo "[ERROR] ${svc} başlatılamadı!"
        echo ""
        systemctl status "${svc}" --no-pager || true
        echo ""
        journalctl -u "${svc}" -n 50 --no-pager || true
        echo ""
        FAILED=1
    fi
done

if [[ $FAILED -eq 1 ]]; then
    err "Bir veya daha fazla servis başlatılamadı. Yukarıdaki logları inceleyin."
fi

# =============================================================================
# Done
# =============================================================================

echo ""
echo "==========================================="
echo "  Güncelleme Tamamlandı!"
echo "==========================================="
echo ""
echo "  Log izleme komutları:"
echo "    sudo journalctl -u bist-trading-bot -f"
echo "    sudo journalctl -u bist-pmr-bot -f"
echo "    tail -f ${INSTALL_DIR}/logs/bot.log"
echo "    tail -f ${INSTALL_DIR}/logs/pmr.log"
echo ""
echo "  Türkiye saati: $(TZ=Europe/Istanbul date '+%Y-%m-%d %H:%M:%S')"
echo ""

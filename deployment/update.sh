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

# =============================================================================
# Helpers
# =============================================================================

info()  { echo "[INFO] $1"; }
ok()    { echo "[OK]   $1"; }
warn()  { echo "[WARN] $1"; }
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

# Detect which modules exist
HAS_TRADING_BOT=false
HAS_PMR_BOT=false

if [[ -f "${INSTALL_DIR}/core-src/main.py" ]]; then
    HAS_TRADING_BOT=true
fi

if [[ -f "${INSTALL_DIR}/pmr/cli.py" ]]; then
    HAS_PMR_BOT=true
fi

info "Validations passed"
info "Trading Bot: ${HAS_TRADING_BOT}, PMR Bot: ${HAS_PMR_BOT}"

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

# Core requirements (mandatory)
if [[ -f "${CORE_REQ}" ]]; then
    sudo -u "${BOT_USER}" "${PIP}" install -q -r "${CORE_REQ}"
    ok "core-src/requirements.txt yüklendi"
else
    err "Eksik: ${CORE_REQ}"
fi

# PMR requirements (optional - warn and continue if missing)
if [[ -f "${PMR_REQ}" ]]; then
    sudo -u "${BOT_USER}" "${PIP}" install -q -r "${PMR_REQ}"
    ok "pmr/requirements.txt yüklendi"
else
    warn "pmr/requirements.txt bulunamadı, PMR bağımlılık yüklemesi atlanıyor"
fi

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

# Trading Bot service (mandatory)
if [[ -f "${INSTALL_DIR}/deployment/bist-trading-bot.service" ]]; then
    cp "${INSTALL_DIR}/deployment/bist-trading-bot.service" "${SERVICE_DIR}/bist-trading-bot.service"
    chmod 0644 "${SERVICE_DIR}/bist-trading-bot.service"
    ok "bist-trading-bot.service kopyalandı"
else
    warn "bist-trading-bot.service bulunamadı"
fi

# PMR Bot service (optional)
if [[ -f "${INSTALL_DIR}/deployment/bist-pmr-bot.service" ]]; then
    cp "${INSTALL_DIR}/deployment/bist-pmr-bot.service" "${SERVICE_DIR}/bist-pmr-bot.service"
    chmod 0644 "${SERVICE_DIR}/bist-pmr-bot.service"
    ok "bist-pmr-bot.service kopyalandı"
else
    warn "bist-pmr-bot.service bulunamadı"
fi

# =============================================================================
# 5. Reload systemd and restart services
# =============================================================================

info "[5/6] Systemd yeniden yükleniyor ve servisler başlatılıyor..."

systemctl daemon-reload

# Trading Bot
if [[ "${HAS_TRADING_BOT}" == "true" ]]; then
    systemctl enable "bist-trading-bot" --quiet 2>/dev/null || true
    systemctl restart "bist-trading-bot"
    ok "bist-trading-bot yeniden başlatıldı"
else
    warn "Trading Bot modülü bulunamadı, servis atlanıyor"
fi

# PMR Bot
if [[ "${HAS_PMR_BOT}" == "true" ]]; then
    systemctl enable "bist-pmr-bot" --quiet 2>/dev/null || true
    systemctl restart "bist-pmr-bot"
    ok "bist-pmr-bot yeniden başlatıldı"
else
    warn "PMR Bot modülü bulunamadı, servis atlanıyor"
fi

# =============================================================================
# 6. Health check
# =============================================================================

info "[6/6] Sağlık kontrolü..."

FAILED=0

# Trading Bot health check
if [[ "${HAS_TRADING_BOT}" == "true" ]]; then
    if systemctl is-active --quiet "bist-trading-bot"; then
        ok "bist-trading-bot çalışıyor ✓"
    else
        echo ""
        echo "[ERROR] bist-trading-bot başlatılamadı!"
        echo ""
        systemctl status "bist-trading-bot" --no-pager || true
        echo ""
        journalctl -u "bist-trading-bot" -n 50 --no-pager || true
        echo ""
        FAILED=1
    fi
fi

# PMR Bot health check
if [[ "${HAS_PMR_BOT}" == "true" ]]; then
    if systemctl is-active --quiet "bist-pmr-bot"; then
        ok "bist-pmr-bot çalışıyor ✓"
    else
        echo ""
        echo "[ERROR] bist-pmr-bot başlatılamadı!"
        echo ""
        systemctl status "bist-pmr-bot" --no-pager || true
        echo ""
        journalctl -u "bist-pmr-bot" -n 50 --no-pager || true
        echo ""
        FAILED=1
    fi
fi

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

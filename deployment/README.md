# BİST Tracker - VPS Deployment

Production deployment guide for Ubuntu VPS. Both bots (Trading Bot + PMR Bot) run independently.

---

## Canonical Files

| File | Description |
|------|-------------|
| `deployment/bist-trading-bot.service` | Trading Bot systemd unit (copied to `/etc/systemd/system/`) |
| `deployment/bist-pmr-bot.service` | PMR Bot systemd unit (copied to `/etc/systemd/system/`) |
| `deployment/update.sh` | Update script (copies unit files, installs deps, restarts services) |

---

## Update After Code Changes

This is the canonical workflow to update both bots on VPS:

```bash
cd /home/botuser/bist-tracker
git pull
sudo bash deployment/update.sh
```

The `update.sh` script will:
1. Create log directories
2. Install Python dependencies from both `core-src/requirements.txt` and `pmr/requirements.txt`
3. Fix permissions
4. Copy unit files to `/etc/systemd/system/`
5. Reload systemd and restart both services
6. Verify both services are running

---

## Service Management

### Trading Bot

```bash
sudo systemctl status bist-trading-bot
sudo systemctl start bist-trading-bot
sudo systemctl stop bist-trading-bot
sudo systemctl restart bist-trading-bot
```

### PMR Bot

```bash
sudo systemctl status bist-pmr-bot
sudo systemctl start bist-pmr-bot
sudo systemctl stop bist-pmr-bot
sudo systemctl restart bist-pmr-bot
```

---

## Log Commands

### Trading Bot Logs

```bash
# Systemd journal (realtime)
sudo journalctl -u bist-trading-bot -f

# Last 100 lines
sudo journalctl -u bist-trading-bot -n 100 --no-pager

# File logs
tail -f /home/botuser/bist-tracker/logs/bot.log
tail -f /home/botuser/bist-tracker/logs/error.log
tail -f /home/botuser/bist-tracker/core-src/logs/bist_bot.log
```

### PMR Bot Logs

```bash
# Systemd journal (realtime)
sudo journalctl -u bist-pmr-bot -f

# Last 100 lines
sudo journalctl -u bist-pmr-bot -n 100 --no-pager

# File logs
tail -f /home/botuser/bist-tracker/logs/pmr.log
tail -f /home/botuser/bist-tracker/logs/pmr_error.log
```

---

## Fresh Install

```bash
# 1. Connect to VPS
ssh root@your-vps-ip

# 2. Create bot user (if not exists)
useradd -m -s /bin/bash botuser

# 3. Clone repo
git clone https://github.com/your-repo/bist-tracker.git /home/botuser/bist-tracker

# 4. Create venv
sudo -u botuser python3 -m venv /home/botuser/bist-tracker/.venv

# 5. Run install script
sudo bash /home/botuser/bist-tracker/deployment/install_service.sh
```

---

## Environment Variables

Telegram credentials are read from `.env` file:

```bash
# Create .env in project root
cat > /home/botuser/bist-tracker/.env << 'EOF'
TELEGRAM_BOT_TOKEN=your_token_here
TELEGRAM_CHAT_ID=your_chat_id_here
DRY_RUN_MODE=false
EOF

chown botuser:botuser /home/botuser/bist-tracker/.env
chmod 600 /home/botuser/bist-tracker/.env
```

---

## Troubleshooting

### Service not starting

```bash
# Check status
sudo systemctl status bist-trading-bot
sudo systemctl status bist-pmr-bot

# View recent logs
sudo journalctl -u bist-trading-bot -n 50 --no-pager
sudo journalctl -u bist-pmr-bot -n 50 --no-pager

# Manual run (for debugging)
sudo -u botuser /home/botuser/bist-tracker/.venv/bin/python /home/botuser/bist-tracker/core-src/main.py
sudo -u botuser /home/botuser/bist-tracker/.venv/bin/python -m pmr.cli continuous
```

### Permission errors

```bash
# Fix ownership
sudo chown -R botuser:botuser /home/botuser/bist-tracker

# Re-run update script
sudo bash /home/botuser/bist-tracker/deployment/update.sh
```

### Missing Python modules

```bash
# Reinstall dependencies
sudo -u botuser /home/botuser/bist-tracker/.venv/bin/pip install -r /home/botuser/bist-tracker/core-src/requirements.txt
sudo -u botuser /home/botuser/bist-tracker/.venv/bin/pip install -r /home/botuser/bist-tracker/pmr/requirements.txt
```

---

## Directory Structure

```
/home/botuser/bist-tracker/
├── .venv/                      # Python virtual environment
├── .env                        # Telegram credentials
├── core-src/                   # Trading Bot code
│   ├── main.py
│   ├── requirements.txt
│   └── logs/
├── pmr/                        # PMR Bot code
│   ├── cli.py
│   └── requirements.txt
├── deployment/
│   ├── bist-trading-bot.service  # Canonical unit file
│   ├── bist-pmr-bot.service      # Canonical unit file
│   ├── update.sh                 # Update script
│   └── README.md
└── logs/                       # Shared log directory
    ├── bot.log
    ├── error.log
    ├── pmr.log
    └── pmr_error.log
```

---

## Quick Reference

| Item | Value |
|------|-------|
| **User** | `botuser` |
| **Install Dir** | `/home/botuser/bist-tracker` |
| **Venv** | `/home/botuser/bist-tracker/.venv` |
| **Python** | `/home/botuser/bist-tracker/.venv/bin/python` |
| **Trading Bot Service** | `bist-trading-bot` |
| **PMR Bot Service** | `bist-pmr-bot` |
| **Timezone** | `Europe/Istanbul` |
| **Market Hours** | 10:00-18:00 (Mon-Fri) |

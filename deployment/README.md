# BİST Trading Bot - Deployment Guide

Bu döküman, BİST Trading Bot'un bir Linux sunucusuna (Ubuntu/Debian) deployment sürecini açıklar.

## 📋 Gereksinimler

- **OS**: Ubuntu 20.04+ / Debian 11+
- **Python**: 3.10+
- **RAM**: Minimum 512MB
- **Disk**: Minimum 1GB
- **Network**: Outbound HTTPS (TradingView, Telegram API)

## ⏱️ Veri Gecikmesi Uyarısı

> **ÖNEMLİ**: TradingView free tier ile veriler **15 dakika gecikmelidir**.
> 
> Bu gecikme:
> - ✅ **Swing trading** için uygundur
> - ✅ **Pozisyon trading** için uygundur
> - ❌ **Day trading / Scalping** için uygun DEĞİLDİR
>
> Gerçek zamanlı veri için TradingView Pro hesabı + authentication gerekir.

## 🚀 Kurulum Adımları

### 1. Sistem Hazırlığı

```bash
# Sistem güncelle
sudo apt update && sudo apt upgrade -y

# Python ve bağımlılıkları kur
sudo apt install -y python3 python3-pip python3-venv git

# Log dizini oluştur
sudo mkdir -p /var/log/bist-trading-bot
sudo chown ubuntu:ubuntu /var/log/bist-trading-bot
```

### 2. Proje Kurulumu

```bash
# Proje dizinine git
cd /home/ubuntu

# Repo'yu klonla (veya kopyala)
git clone https://github.com/yourusername/bist-tracker.git
cd bist-tracker

# Virtual environment oluştur
python3 -m venv venv
source venv/bin/activate

# Bağımlılıkları yükle
pip install -r core-src/requirements.txt
```

### 3. Konfigürasyon

```bash
# Config dosyasını düzenle
nano core-src/config.py
```

Değiştirilmesi gereken ayarlar:

```python
# Telegram ayarları (ZORUNLU)
TELEGRAM_BOT_TOKEN = "your_actual_bot_token"
TELEGRAM_CHAT_ID = "your_actual_chat_id"

# Dry-run modu (test için True, production için False)
DRY_RUN_MODE = False
```

### 4. Smoke Test

Deployment öncesi smoke test çalıştır:

```bash
cd /home/ubuntu/bist-tracker/core-src
source ../venv/bin/activate
python test_mvp_integration.py
```

Tüm testler geçmeliyse devam et.

### 5. Systemd Service Kurulumu

```bash
# Service dosyasını kopyala
sudo cp /home/ubuntu/bist-tracker/deployment/bist-trading-bot.service /etc/systemd/system/

# Systemd'yi yenile
sudo systemctl daemon-reload

# Service'i etkinleştir (boot'ta otomatik başlasın)
sudo systemctl enable bist-trading-bot

# Service'i başlat
sudo systemctl start bist-trading-bot
```

### 6. Durum Kontrolü

```bash
# Service durumu
sudo systemctl status bist-trading-bot

# Canlı loglar
sudo journalctl -u bist-trading-bot -f

# Log dosyaları
tail -f /var/log/bist-trading-bot/bot.log
tail -f /var/log/bist-trading-bot/error.log
```

## 📊 Log Yönetimi

### Logrotate Kurulumu (Önerilen)

```bash
# Logrotate config oluştur
sudo nano /etc/logrotate.d/bist-trading-bot
```

İçerik:

```
/var/log/bist-trading-bot/*.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
    create 0640 ubuntu ubuntu
    postrotate
        systemctl reload bist-trading-bot > /dev/null 2>&1 || true
    endscript
}
```

## 🔧 Yönetim Komutları

```bash
# Durdur
sudo systemctl stop bist-trading-bot

# Başlat
sudo systemctl start bist-trading-bot

# Yeniden başlat
sudo systemctl restart bist-trading-bot

# Logları görüntüle
sudo journalctl -u bist-trading-bot -f --since "1 hour ago"

# Devre dışı bırak (boot'ta başlamasın)
sudo systemctl disable bist-trading-bot
```

## 🐛 Sorun Giderme

### Bot başlamıyor

1. Logları kontrol et:
   ```bash
   sudo journalctl -u bist-trading-bot -n 50
   ```

2. Manuel çalıştır:
   ```bash
   cd /home/ubuntu/bist-tracker/core-src
   source ../venv/bin/activate
   python main.py
   ```

### Telegram mesajları gelmiyor

1. `DRY_RUN_MODE = False` olduğundan emin ol
2. Bot token ve chat ID'yi kontrol et
3. Telegram API erişimini kontrol et:
   ```bash
   curl https://api.telegram.org/bot<TOKEN>/getMe
   ```

### Veri çekilemiyor

1. Provider sağlığını kontrol et (loglardan)
2. Network bağlantısını kontrol et:
   ```bash
   curl -I https://scanner.tradingview.com/turkey/scan
   ```

### Yüksek CPU/RAM kullanımı

1. Service limitlerini kontrol et (`bist-trading-bot.service`)
2. `SCAN_INTERVAL_SECONDS` değerini artır
3. `BIST_SYMBOLS` listesini küçült

## 📈 İzleme ve Alerting

### Uptime Kontrolü (Önerilen)

```bash
# Basit health check script
nano /home/ubuntu/check-bot.sh
```

```bash
#!/bin/bash
if ! systemctl is-active --quiet bist-trading-bot; then
    echo "Bot down! Restarting..."
    sudo systemctl restart bist-trading-bot
fi
```

```bash
chmod +x /home/ubuntu/check-bot.sh

# Crontab'a ekle (5 dakikada bir kontrol)
crontab -e
# Ekle: */5 * * * * /home/ubuntu/check-bot.sh
```

## 🔐 Güvenlik Notları

1. **API Token'ları**: Hiçbir zaman Git'e commit etme
2. **Firewall**: Sadece gerekli portları aç
3. **Updates**: Sistemi düzenli güncelle
4. **Backup**: Config dosyalarını yedekle

## 📝 Versiyon Notları

### v2.0 (MVP)
- Provider katmanı entegrasyonu
- TradingView HTTP + WebSocket desteği
- 15 dakika veri gecikmesi uyarısı
- Graceful shutdown
- Systemd service desteği

---

Sorular için: [GitHub Issues](https://github.com/yourusername/bist-tracker/issues)

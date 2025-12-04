# BİST Trading Bot - VPS Deployment

Production-tested deployment guide for Ubuntu VPS.

## Hızlı Başlangıç

### İlk Kurulum (Fresh Install)

```bash
# 1. VPS'e bağlan
ssh root@your-vps-ip

# 2. Bot kullanıcısı oluştur (yoksa)
useradd -m -s /bin/bash botuser

# 3. Repo'yu klonla
git clone https://github.com/your-repo/bist-tracker.git /home/botuser/bist-tracker

# 4. Kurulum scriptini çalıştır
sudo bash /home/botuser/bist-tracker/deployment/install_service.sh
```

### Güncelleme (Update)

```bash
# 1. Kodu çek
cd /home/botuser/bist-tracker
sudo -u botuser git pull

# 2. Güncelle ve yeniden başlat
sudo bash deployment/update.sh
```

---

## Dizin Yapısı

```
/home/botuser/bist-tracker/
├── .venv/                      # Python virtual environment
├── core-src/                   # Ana kod
│   ├── main.py                 # Entry point
│   ├── config.py               # Ayarlar
│   ├── logs/                   # Bot logları (bist_bot.log)
│   └── ...
├── deployment/                 # Deployment scriptleri
│   ├── install_service.sh      # İlk kurulum
│   ├── update.sh               # Güncelleme
│   ├── uninstall_service.sh    # Kaldırma
│   └── README.md               # Bu dosya
├── logs/                       # Systemd logları (bot.log, error.log)
└── ...
```

---

## Servis Yönetimi

```bash
# Durum kontrolü
sudo systemctl status bist-trading-bot

# Başlat / Durdur / Yeniden başlat
sudo systemctl start bist-trading-bot
sudo systemctl stop bist-trading-bot
sudo systemctl restart bist-trading-bot

# Otomatik başlatmayı aç/kapat
sudo systemctl enable bist-trading-bot
sudo systemctl disable bist-trading-bot
```

---

## Log İzleme

```bash
# Systemd logları (realtime)
sudo journalctl -u bist-trading-bot -f

# Son 100 satır
sudo journalctl -u bist-trading-bot -n 100

# Bot logları
tail -f /home/botuser/bist-tracker/logs/bot.log
tail -f /home/botuser/bist-tracker/core-src/logs/bist_bot.log

# Hata logları
tail -f /home/botuser/bist-tracker/logs/error.log
```

---

## Ortam Değişkenleri

Telegram credentials `.env` dosyasında veya environment'ta:

```bash
# Option 1: .env dosyası (core-src içinde)
echo "TELEGRAM_BOT_TOKEN=your_token" >> /home/botuser/bist-tracker/core-src/.env
echo "TELEGRAM_CHAT_ID=your_chat_id" >> /home/botuser/bist-tracker/core-src/.env

# Option 2: Systemd override
sudo systemctl edit bist-trading-bot
# Ekle:
# [Service]
# Environment="TELEGRAM_BOT_TOKEN=your_token"
# Environment="TELEGRAM_CHAT_ID=your_chat_id"
```

---

## Troubleshooting

### Bot başlamıyor
```bash
# Manuel çalıştır
sudo -u botuser /home/botuser/bist-tracker/.venv/bin/python /home/botuser/bist-tracker/core-src/main.py

# Detaylı loglar
sudo journalctl -u bist-trading-bot -n 100 --no-pager
```

### Permission denied hataları
```bash
# İzinleri düzelt
sudo chown -R botuser:botuser /home/botuser/bist-tracker
```

### Python modül bulunamadı
```bash
# Bağımlılıkları yeniden yükle
sudo -u botuser /home/botuser/bist-tracker/.venv/bin/pip install -r /home/botuser/bist-tracker/core-src/requirements.txt
```

---

## Tam Kaldırma

```bash
# Servisi kaldır
sudo bash /home/botuser/bist-tracker/deployment/uninstall_service.sh

# Dosyaları sil (opsiyonel)
sudo rm -rf /home/botuser/bist-tracker

# Kullanıcıyı sil (opsiyonel)
sudo userdel -r botuser
```

---

## Önemli Bilgiler

| Parametre | Değer |
|-----------|-------|
| **User** | `botuser` |
| **Install Dir** | `/home/botuser/bist-tracker` |
| **Working Dir** | `/home/botuser/bist-tracker/core-src` |
| **Venv** | `/home/botuser/bist-tracker/.venv` |
| **Python** | `/home/botuser/bist-tracker/.venv/bin/python` |
| **Service** | `bist-trading-bot` |
| **Timezone** | `Europe/Istanbul` |
| **Market Hours** | 10:00-18:00 (Pazartesi-Cuma) |

---

## Veri Gecikmesi Uyarısı

> **ÖNEMLİ**: TradingView free tier ile veriler **15 dakika gecikmelidir**.
> 
> Bu gecikme:
> - ✅ **Swing trading** için uygundur
> - ✅ **Pozisyon trading** için uygundur
> - ❌ **Day trading / Scalping** için uygun DEĞİLDİR

---

## Güncelleme Notları

**v1.1 (Current):**
- ✅ Timezone sorunu düzeltildi (`utils/timezone.py`)
- ✅ TradingView HTTP öncelikli (`config.py`)
- ✅ İki ayrı log dizini desteği
- ✅ Production-tested deployment scriptleri

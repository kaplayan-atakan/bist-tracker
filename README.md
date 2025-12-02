# BİST Trading Bot

Borsa İstanbul (BIST) için otomatik hisse tarama ve sinyal üretim botu.

## Özellikler

- 📊 **Teknik Analiz**: MA, MACD, RSI, ADX, Stochastic indikatörleri
- 🔍 **Otomatik Tarama**: Belirli aralıklarla tüm BİST hisselerini tarar
- 📱 **Telegram Bildirimleri**: Sinyal üretildiğinde anlık bildirim
- ⏱️ **Cooldown Sistemi**: Aynı hisse için tekrar sinyal spam'ini önler
- 🔌 **Multi-Provider**: TradingView, Yahoo Finance desteği

## Kurulum

```bash
cd core-src
pip install -r requirements.txt
python main.py
```

## Veri Gecikmesi

⚠️ **Önemli**: TradingView free tier ile veriler 15 dakika gecikmelidir.
- ✅ Swing trading için uygundur
- ❌ Day trading için uygun DEĞİLDİR

## Yapılandırma

`config.py` dosyasından veya `.env` dosyasından ayarları yapılandırın:

- `TELEGRAM_BOT_TOKEN`: Telegram bot token'ı
- `TELEGRAM_CHAT_ID`: Telegram chat ID
- `DRY_RUN_MODE`: Test modu (true = mesaj göndermez)

## Deployment

Linux sunucuya deployment için `deployment/README.md` dosyasına bakın.

## Lisans

MIT

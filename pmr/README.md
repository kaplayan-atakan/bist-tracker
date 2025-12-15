# BIST Pre-Manipulation Radar (PMR) v1.0

## 📋 Genel Bakış

BIST Pre-Manipulation Radar (PMR), Borsa İstanbul’da manipülasyon **hazırlık** evresindeki hisseleri tespit etmek için geliştirilmiş erken uyarı sistemidir.

### 🎯 Amaç

Manipülasyon genelde şu evrelerde gerçekleşir:

1. **Hazırlık (Sessiz)** ← PMR burada devreye girer
1. **Başlama (İlk Hareket)**
1. **Patlama (Herkes Görür)** ← Artık geç

PMR, 1. evrede “sessiz toplama”, “volatilite sıkışması”, “emir defteri emilimi” gibi sinyalleri yakalayarak erken uyarı verir.

-----

## 🔧 Kurulum

### Gereksinimler

- Python 3.8+
- pip

### Adımlar

```bash
# 1. Kütüphaneleri yükle
pip install -r requirements.txt

# 2. Konfigürasyonu düzenle (opsiyonel)
# pmr/config.py dosyasını açıp ayarları düzenleyin
nano pmr/config.py

# 3. Çalıştır
python -m pmr.cli
```

-----

## 🚀 Kullanım

### Modlar

#### 1. Sürekli Tarama (Varsayılan)

```bash
python -m pmr.cli continuous
```

- Her 2 dakikada bir tüm evreni tarar
- Yüksek skorlu hisseleri Telegram’a bildirir
- Watchlist’e otomatik ekler

#### 2. Tek Hisse Tarama

```bash
python -m pmr.cli single THYAO
```

- Belirtilen hisseyi tek seferlik tarar
- Detaylı sonuç gösterir

#### 3. Evren Tarama (Bir Kez)

```bash
python -m pmr.cli scan
```

- Tüm evreni bir kez tarar
- Özet rapor verir

#### 4. Watchlist Raporu

```bash
python -m pmr.cli report
```

- Mevcut watchlist’i gösterir
- Top 10 yüksek skorlu hisseleri listeler

-----

## 📊 Skorlama Sistemi

PMR, 0-100 arası skor üretir:

### Alt Skorlar (Toplam: 100)

|Modül               |Maksimum|Açıklama                               |
|--------------------|--------|---------------------------------------|
|**A** - Accumulation|30      |OBV/ADL ve fiyat ayrışması             |
|**V** - Volatility  |20      |ATR ve BB sıkışması                    |
|**O** - Order Book  |25      |L2 emilim/baskı (L2 varsa)             |
|**F** - Flow        |15      |İşlem akışı dengesizliği (prints varsa)|
|**C** - Context     |10      |Sosyal sessizlik, KAP, likidite profili|

### Etiketler

|Skor |Etiket               |Anlamı             |
|-----|---------------------|-------------------|
|≥75  |🔥 Hazırlık Çok Yüksek|Watchlist öncelik 1|
|60-74|🟠 Hazırlık Yüksek    |Yakından takip et  |
|45-59|🟡 Hazırlık Orta      |İzle               |
|<45  |🟢 Düşük Risk         |Normal             |

-----

## 🔍 Modüller Detay

### A: Accumulation Divergence (0-30)

**Amaç:** Sessiz toplama var mı?

**Mantık:**

- Fiyat yatay (slope ~0)
- OBV yükseliyor (slope > 0)
- ADL yükseliyor (slope > 0)

**Puanlama:**

- Fiyat yatay + OBV↑: +15
- Fiyat yatay + ADL↑: +10
- Her ikisi de↑: +5 bonus

### V: Volatility Compression (0-20)

**Amaç:** Tahta sıkışmış mı?

**Mantık:**

- ATR düşük (son 20 günün alt %25’i)
- Bollinger Band Width düşük

**Puanlama:**

- ATR düşük: +10
- BBW düşük: +10

### O: Order Book Absorption (0-25)

**Amaç:** Satış emiliyor mu?

**Mantık:**

- Ask tarafında lot azalması (-%30+)
- Fiyat yatay/stabil
- Bid tarafında stabilite

**Puanlama:**

- Ask azalması + fiyat stabil: +15
- Bid stabilite: +10

### F: Flow Footprint (0-15)

**Amaç:** Agresif alım var ama fiyat bastırılıyor mu?

**Mantık:**

- Net delta pozitif yüksek (z-score > 2)
- Fiyat yükselmiyor

**Puanlama:**

- Agresif alım + fiyat bastırılıyor: +15

### C: Context (0-10)

**Amaç:** Hazırlık için uygun zemin var mı?

**Puanlama:**

- Sosyal sessizlik: +3
- KAP yok: +2
- Düşük likidite: +5

-----

## ⚙️ Konfigürasyon

`pmr/config.py` dosyasında ayarlanabilir parametreler:

### Tarama Ayarları

```python
SCAN_INTERVAL_SECONDS = 120  # Tarama aralığı
MIN_DAILY_VOLUME_TL = 30_000_000  # Minimum günlük hacim
```

### Telegram Ayarları

```python
TELEGRAM_ENABLED = True
TELEGRAM_BOT_TOKEN = "YOUR_BOT_TOKEN"
TELEGRAM_CHAT_ID = "YOUR_CHAT_ID"
```

### Skor Eşikleri

```python
SCORE_THRESHOLD_VERY_HIGH = 75
SCORE_THRESHOLD_HIGH = 60
SCORE_THRESHOLD_MEDIUM = 45
```

-----

## 📡 Veri Kaynakları

### Gerekli Veriler (Minimum)

- ✅ 1dk/5dk OHLCV
- ✅ Günlük OHLCV

### Opsiyonel (Gücü Artırır)

- L2 Order Book (O modülü için)
- Trade Prints (F modülü için)
- KAP Akışı (C modülü için)
- Sosyal medya (C modülü için)

### Mock Mode

Şu an bot **mock mode**’da çalışıyor (test verisi). Gerçek veri entegrasyonu için:

1. `pmr/data.py` → `_api_ohlcv()`, `_api_orderbook()` fonksiyonlarını doldurun
1. `pmr/config.py` → `DATA_SOURCE = "api"` yapın
1. API key’leri girin

-----

## 🛡️ False Positive Koruması

PMR, yanlış alarm riskini azaltmak için çeşitli filtreler içerir:

### FP-1: Normal Sıkışma

Sıkışma var ama divergence yoksa → skor kırılır

### FP-2: Haber Öncesi

Çok fazla KAP varsa → event-driven olabilir uyarısı

### FP-3: Likidite Tuzağı

Spread çok geniş veya hacim çok düşük → işlem yasak etiketi

-----

## 📈 Örnek Çıktı

### Telegram Bildirimi

```
🧠 PMR ERKEN UYARI (Hazırlık Tespiti)

Hisse: SMALLCAP1
PMR Score: 78.0 / 100 🔥
Etiket: 🔥 Hazırlık Çok Yüksek

📊 Nedenler:
• Accumulation (27p): OBV↑ fiyat yatay (slope: 0.0123), ADL↑ fiyat yatay (slope: 0.0098), OBV ve ADL aynı anda↑
• Volatilite sıkışması (18p): ATR düşük (percentile: 12.5), BB Width düşük (percentile: 8.3)
• Context (11p): Düşük hacim: 15.0M TL, Geniş spread: 1.50%

⚠️ Orta likidite (dikkatli ol)

✅ Watchlist öncelik 1
⚠️ Patlama başladığında 'erken' biter; risk artar.

⏰ 2025-12-12 14:30:45
```

### Watchlist Raporu

```
📋 PMR WATCHLIST RAPORU
Tarih: 2025-12-12 14:35:00
Aktif hisse sayısı: 3

🔥 ÇOK YÜKSEK HAZIRLIK:
  • SMALLCAP1: 78.0
  • SMALLCAP2: 76.5

🟠 YÜKSEK HAZIRLIK:
  • THYAO: 62.3
```

-----

## 🚨 Başlama Alarmı

PMR, hazırlık evresinden sonra **başlama**yı da algılar:

### Tetikleyiciler

- Hacim spike (≥3× ortalama)
- Fiyat +%1+ hareket
- L2’de hızlı iptal artışı (opsiyonel)

### Alarm Mesajı

```
🚨 BAŞLAMA ALARMI 🚨

Hisse: SMALLCAP1
⚠️ PATLAMA BAŞLADI! Hacim spike + fiyat +%1

⚠️ Hazırlık evresi bitti; risk yükseldi!
```

-----

## 📁 Dosya Yapısı

```
.
├── pmr/
│   ├── cli.py                 # Ana çalıştırma scripti
│   ├── config.py              # Konfigürasyon
│   ├── data.py                # Veri sağlayıcı
│   ├── features.py            # Feature çıkarımı
│   ├── scoring.py             # Skorlama motoru
│   ├── notifier.py            # Telegram & watchlist
│   ├── scanner.py             # Ana tarayıcı
│   └── tests/                 # Testler
├── requirements.txt           # Bağımlılıklar
└── pmr/README.md              # Bu dosya
```

-----

## ⚖️ Yasal Uyarı

**ÖNEMLİ:**

- Bu yazılım yalnızca **eğitim ve araştırma** amaçlıdır
- Finansal tavsiye değildir
- Manipülasyon yasadışıdır - bu bot manipülasyon yapmaz, tespit etmeye çalışır
- Gerçek yatırım kararlarında kullanmadan önce profesyonel danışmanlık alın
- Yazarlar, bu yazılımın kullanımından doğacak hiçbir zarardan sorumlu değildir

-----

## 🤝 Katkıda Bulunma

Geliştirmeler için öneriler:

- Daha gelişmiş ML modelleri (LSTM, Transformer)
- Gerçek zamanlı L2 streaming
- Sosyal medya sentiment analizi
- KAP otomatik parse
- Web dashboard

-----

## 📞 Destek

Sorularınız için:

- GitHub Issues kullanın
- Dökümentasyonu okuyun
- pmr/config.py ayarlarını kontrol edin

-----

## 📝 Lisans

Bu proje MIT lisansı altında yayınlanmıştır.

-----

**v1.0 - İlk Sürüm**
*Son güncelleme: Aralık 2025*

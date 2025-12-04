"""
BİST Trading Bot - Configuration Module
Tüm bot parametreleri burada merkezi olarak yönetilir
"""

# ================== GENEL AYARLAR ==================
# Tarama modu:
#   - "open_close": Açılış+kapanış (günde 2 tarama)
#   - "continuous": Sürekli tarama (eski davranış)
#   - "hybrid": Günlük trend yenileme + intraday tarama (ÖNERİLEN)
SCAN_MODE = "hybrid"  # Dual-frequency: günlük + 15dk intraday

# ===== HYBRID MOD AYARLARI =====
# İntraday tarama aralığı (saniye)
# 15 dakika = 900 saniye (TradingView 15dk gecikmeli olduğu için ideal)
INTRADAY_SCAN_INTERVAL = 900  # 15 dakika

# Günlük veri yenileme saatleri (açılış öncesi + kapanış sonrası)
DAILY_DATA_REFRESH_TIMES = ["09:55", "18:05"]

# Tarama penceresi
SCAN_START_TIME = "10:00"
SCAN_END_TIME = "18:00"

# İlk taramayı açılıştan kaç dakika sonra yap?
# 15dk gecikme olduğu için, 10:15'te ilk gerçek veri gelir
FIRST_SCAN_DELAY_MINUTES = 15

# ===== ESKİ MOD AYARLARI (geriye dönük uyumluluk) =====
# Tarama aralığı (saniye) - sadece continuous modda kullanılır
SCAN_INTERVAL_SECONDS = 300  # 5 dakika

# Piyasa kontrol aralığı (saniye) - açılış/kapanış beklerken
MARKET_CHECK_INTERVAL = 60  # 1 dakika

# Çalışma saatleri (Türkiye saati)
MARKET_OPEN_HOUR = 10
MARKET_CLOSE_HOUR = 18

# ================== FİLTRELEME PARAMETRELERİ ==================
# Minimum günlük hacim (TL)
MIN_DAILY_TL_VOLUME = 1_000_000  # 1 milyon TL

# Fiyat bandı filtreleri
MIN_PRICE = 5.0  # TL
MAX_PRICE = 500.0  # TL

# Spread filtresi (yüzde)
# BİST spreads tipik olarak %1-3 aralığında
# Kapanışa yakın (17:30+) spread'ler doğal olarak genişler
MAX_SPREAD_PERCENT = 3.0  # Normal market saatleri için
MAX_SPREAD_PERCENT_CLOSE = 5.0  # Kapanışa yakın (17:30-18:00)

# ================== SKORLAMA BARAJLARI ==================
ULTRA_BUY_THRESHOLD = 16  # 20 üzerinden 16+
STRONG_BUY_THRESHOLD = 13  # 20 üzerinden 13-15
WATCHLIST_THRESHOLD = 10  # 20 üzerinden 10-12

# Blok maksimum puanları
MAX_TREND_SCORE = 5
MAX_MOMENTUM_SCORE = 5
MAX_VOLUME_SCORE = 5
MAX_FUNDAMENTAL_PA_SCORE = 5

# ================== COOLDOWN SİSTEMİ ==================
# Aynı hisse için sinyal gönderme aralığı (dakika)
SIGNAL_COOLDOWN_MINUTES = 60

# ================== TELEGRAM AYARLARI ==================
# Bu bilgileri kendi Telegram bot token'ınız ile değiştirin
import os
TELEGRAM_BOT_TOKEN = "7611453017:AAFAz9jBsUQ-N6RUdQ8pnct0gIzV2UeEmIM"
TELEGRAM_CHAT_ID = "5883922751"

# Dry-run modu (True ise Telegram'a göndermez, sadece log'lar)
DRY_RUN_MODE = os.getenv("DRY_RUN_MODE", "false").lower() == "true"

# ================== VERİ KAYNAĞI AYARLARI ==================
# Eski ayar (geriye dönük uyumluluk için korunuyor)
DATA_PROVIDER = 'yfinance'

# API rate limit ayarları
API_RATE_LIMIT_CALLS = 100
API_RATE_LIMIT_PERIOD = 60  # saniye

# Cache süresi (saniye)
CACHE_DURATION_SECONDS = 60

# ================== PROVIDER AYARLARI (Sprint 2) ==================
# 
# VERİ GECİKMESİ UYARISI:
# ===============================
# Anonim kullanımda TradingView verileri 15 DAKİKA gecikmelidir.
# Bu, TradingView'ın "delayed_streaming_900" modudur.
# Gerçek zamanlı veri için TradingView hesabı + authentication gerekir (gelecek sprint).
#
# Provider Hiyerarşisi:
# -------------------
# - TradingView HTTP: İntraday anlık veriler için PRIMARY
#   * Screener API (~200-250ms latency)
#   * Batch sorgu desteği (50 sembol/istek)
#   * Sector, market cap, PE, PB verileri
#
# - TradingView WebSocket: Gerçek zamanlı streaming için
#   * Quote stream (fiyat, değişim, hacim)
#   * Otomatik reconnect
#   * Mum (bar) aggregation
#
# - Yahoo (yfinance): Günlük veriler + fundamentals için
#   * Güvenilir geçmiş veri
#   * Kapsamlı fundamental data
#
# - Finnhub: Backup (FREE tier BİST'i DESTEKLEMİYOR!)
#
# Öncelik Sıralaması:
# ------------------
# TradingView HTTP primary intraday için - REST API ile OHLCV çekimi
# NOT: tradingview_ws sadece realtime quote stream içindir, OHLCV alamaz
DATA_PRIORITY_INTRADAY = ["tradingview_http", "yahoo"]  # Intraday için (WS kaldırıldı)
DATA_PRIORITY_DAILY = ["yahoo"]  # Günlük veri için (Yahoo daha güvenilir)
DATA_PRIORITY_FUNDAMENTALS = ["tradingview_http", "yahoo"]  # Temel analiz için

# Gerçek zamanlı streaming provider
STREAMING_PROVIDER_INTRADAY = "tradingview_ws"

# ================== TRADINGVIEW HTTP AYARLARI ==================
TRADINGVIEW_HTTP_ENABLED = True
TRADINGVIEW_HTTP_BASE_URL = "https://scanner.tradingview.com/turkey/scan"
TRADINGVIEW_HTTP_TIMEOUT = 10  # saniye
TRADINGVIEW_HTTP_BATCH_SIZE = 50  # Tek istekte max sembol
TRADINGVIEW_HTTP_MIN_INTERVAL = 0.5  # saniye - rate limit koruması

# ================== TRADINGVIEW WEBSOCKET AYARLARI ==================
TRADINGVIEW_WS_ENABLED = True
TRADINGVIEW_WS_URL = "wss://data.tradingview.com/socket.io/websocket"
TRADINGVIEW_WS_ORIGIN = "https://data.tradingview.com"
TRADINGVIEW_WS_HEARTBEAT_INTERVAL = 10  # saniye
TRADINGVIEW_WS_RECONNECT_MAX_ATTEMPTS = 5
TRADINGVIEW_WS_MESSAGE_TIMEOUT = 30  # saniye

# TradingView eski isimler (geriye dönük uyumluluk)
TRADINGVIEW_ENABLED = TRADINGVIEW_WS_ENABLED
TRADINGVIEW_HEARTBEAT_INTERVAL = TRADINGVIEW_WS_HEARTBEAT_INTERVAL
TRADINGVIEW_RECONNECT_MAX_ATTEMPTS = TRADINGVIEW_WS_RECONNECT_MAX_ATTEMPTS
TRADINGVIEW_MESSAGE_TIMEOUT = TRADINGVIEW_WS_MESSAGE_TIMEOUT

# ================== FINNHUB AYARLARI ==================
# DİKKAT: Finnhub FREE tier BİST sembollerini DESTEKLEMİYOR!
# 403 Forbidden hatası verir. Premium abonelik gerekli.
import os
FINNHUB_ENABLED = False  # Devre dışı - BİST'te çalışmıyor
FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY", "")
FINNHUB_BASE_URL = "https://finnhub.io/api/v1"
FINNHUB_TIMEOUT = 30  # saniye
FINNHUB_MAX_RETRIES = 3
FINNHUB_RATE_LIMIT_CALLS = 60  # dakikada max çağrı
FINNHUB_RATE_LIMIT_PERIOD = 60  # saniye

# ================== YAHOO (YFINANCE) AYARLARI ==================
YAHOO_ENABLED = True
YAHOO_CACHE_DURATION = 60  # saniye

# ================== PROVIDER SAĞLIK KONTROLÜ ==================
PROVIDER_HEALTH_CHECK_INTERVAL = 60  # saniye

# ================== TEKNİK İNDİKATÖR PARAMETRELERİ ==================
# Hareketli ortalama periyotları
MA_SHORT = 10
MA_MEDIUM = 20
MA_LONG = 50

# RSI parametreleri
RSI_PERIOD = 14
RSI_OVERSOLD = 30
RSI_OVERBOUGHT = 70
RSI_HEALTHY_MIN = 50
RSI_HEALTHY_MAX = 70

# MACD parametreleri
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9

# ADX parametreleri
ADX_PERIOD = 14
ADX_TREND_THRESHOLD = 20

# Stochastic parametreleri
STOCH_K_PERIOD = 14
STOCH_D_PERIOD = 3
STOCH_OVERSOLD = 20

# Volume parametreleri
VOLUME_MA_PERIOD = 20
VOLUME_SPIKE_THRESHOLD = 1.5  # 20 günlük ortalamanın kaç katı

# OBV trend analizi
OBV_TREND_PERIOD = 10

# ================== PRICE ACTION PARAMETRELERİ ==================
# Güçlü yeşil mum - kapanış pozisyonu
STRONG_GREEN_THRESHOLD = 0.75  # Günlük range'in üst %25'inde

# Alt fitil oranı
LOWER_WICK_RATIO = 1.5  # Gövdenin kaç katı olmalı

# Collapse kontrolü
COLLAPSE_CHECK_DAYS = 5
COLLAPSE_THRESHOLD_PERCENT = -10  # Tek günde %10+ düşüş

# Breakout kontrolü
BREAKOUT_VOLUME_MULTIPLIER = 1.3

# ================== TEMEL ANALİZ PARAMETRELERİ ==================
# F/K oranı filtreleri (opsiyonel)
MIN_PE_RATIO = 0
MAX_PE_RATIO = 50

# PD/DD oranı
MAX_PB_RATIO = 3.0

# ================== VERİ GECİKMESİ AYARLARI (MVP Sprint) ==================
# TradingView anonim kullanımda veriler 15 dakika gecikmelidir.
# Bu, TradingView'ın "delayed_streaming_900" modudur.
# Gerçek zamanlı veri için TradingView Pro hesabı + authentication gerekir.
DATA_DELAY_ENABLED = True
DATA_DELAY_MINUTES = 15
DATA_DELAY_WARNING_TEXT = "⏱️ Veriler 15 dakika gecikmelidir (TradingView free tier)"

# ================== VERİ KESİNTİSİ AYARLARI ==================
# Veri alınamazsa kaç gün sonra Telegram uyarısı gönderilsin
DATA_OUTAGE_ALERT_DAYS = 2

# Veri çekme retry ayarları
DATA_FETCH_MAX_RETRIES = 3  # Maksimum deneme sayısı
DATA_FETCH_RETRY_DELAY = 5  # Denemeler arası bekleme (saniye)

# ================== LOGLAMA AYARLARI ==================
LOG_FILE = 'bist_bot.log'
LOG_LEVEL = 'INFO'  # DEBUG, INFO, WARNING, ERROR
LOG_LEVEL_THIRD_PARTY = 'WARNING'  # yfinance, aiohttp, websockets vb. için
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
LOG_DATE_FORMAT = '%Y-%m-%d %H:%M:%S'

# ================== SEMBOL DOĞRULAMA AYARLARI ==================
# Sembol listesi doğrulaması
SYMBOL_VALIDATION_ENABLED = True
SYMBOL_FALLBACK_TO_HARDCODED = True  # Fetch başarısız olursa hardcoded liste kullan

# ================== KARA LİSTE ==================
# Tarama dışı bırakılacak semboller
BLACKLIST_SYMBOLS = [
    # Buraya aşırı volatil veya sorunlu hisseler eklenebilir
]

# ================== BİST SEMBOL LİSTESİ ==================
# 442 doğrulanmış BİST sembolü (yfinance ile test edildi)
# Son güncelleme: Aralık 2025
# Kaynak: TradingView Scanner API + yfinance doğrulaması
# Güncelleme için: python test.py (proje root'unda)
BIST_SYMBOLS = [
    'A1YEN', 'ADEL', 'ADGYO', 'AEFES', 'AFYON', 'AGESA', 'AGHOL', 'AGROT',
    'AGYO', 'AHGAZ', 'AHSGY', 'AKBNK', 'AKENR', 'AKFGY', 'AKFIS', 'AKGRT',
    'AKMGY', 'AKSA', 'AKSEN', 'AKSGY', 'AKYHO', 'ALARK', 'ALBRK', 'ALFAS',
    'ALGYO', 'ALKA', 'ALKIM', 'ALTNY', 'ALVES', 'ANGEN', 'ANHYT', 'ANSGR',
    'ARDYZ', 'ARENA', 'ARMGD', 'ARSAN', 'ARTMS', 'ARZUM', 'ASELS', 'ASGYO',
    'ASTOR', 'ASUZU', 'ATAGY', 'ATEKS', 'ATLAS', 'ATSYH', 'AVGYO', 'AVHOL',
    'AVOD', 'AVTUR', 'AYDEM', 'AYEN', 'AYES', 'AYGAZ', 'AZTEK', 'BAGFS',
    'BAHKM', 'BAKAB', 'BALAT', 'BALSU', 'BANVT', 'BARMA', 'BASGZ', 'BAYRK',
    'BEGYO', 'BERA', 'BESLR', 'BEYAZ', 'BFREN', 'BIENY', 'BIGEN', 'BIGTK',
    'BIMAS', 'BINBN', 'BINHO', 'BIOEN', 'BIZIM', 'BJKAS', 'BMSTL', 'BNTAS',
    'BOBET', 'BORLS', 'BORSK', 'BOSSA', 'BRISA', 'BRKO', 'BRKSN', 'BRKVY',
    'BRLSM', 'BRMEN', 'BRSAN', 'BRYAT', 'BULGS', 'BURVA', 'BVSAN', 'BYDNR',
    'DAGI', 'DARDL', 'DERHL', 'DERIM', 'DESA', 'DEVA', 'DGGYO', 'DGNMO',
    'DIRIT', 'DITAS', 'DMRGD', 'DMSAS', 'DNISI', 'DOAS', 'DOFER', 'DOFRB',
    'DOGUB', 'DOHOL', 'DOKTA', 'DSTKF', 'DUNYH', 'DURDO', 'DURKN', 'DYOBY',
    'DZGYO', 'EBEBK', 'EDATA', 'EFOR', 'EGEEN', 'EGEGY', 'EGGUB', 'EGSER',
    'EKGYO', 'EKIZ', 'EKOS', 'EKSUN', 'EMKEL', 'EMNIS', 'ENERY', 'ENJSA',
    'ENKAI', 'ENSRI', 'ENTRA', 'ERBOS', 'EREGL', 'ERSU', 'ESEN', 'ETILR',
    'ETYAT', 'EUHOL', 'EUKYO', 'EUREN', 'EUYO', 'EYGYO', 'FENER', 'FONET',
    'FORMT', 'FRIGO', 'FROTO', 'FZLGY', 'GARAN', 'GARFA', 'GEDIK', 'GEDZA',
    'GENIL', 'GENTS', 'GEREL', 'GESAN', 'GLBMD', 'GLDTR', 'GLRMK', 'GLRYH',
    'GLYHO', 'GMSTR', 'GMTAS', 'GOKNR', 'GOLTS', 'GOODY', 'GRNYO', 'GRSEL',
    'GRTHO', 'GSDHO', 'GSRAY', 'GUBRF', 'GUNDG', 'GZNMI', 'HALKB', 'HATEK',
    'HATSN', 'HDFGS', 'HEDEF', 'HEKTS', 'HKTM', 'HLGYO', 'HOROZ', 'HRKET',
    'HTTBT', 'HUNER', 'HURGZ', 'IDGYO', 'IEYHO', 'IHAAS', 'IHEVA', 'IHGZT',
    'IHLAS', 'IHLGM', 'IHYAY', 'IMASM', 'INDES', 'INFO', 'INGRM', 'INTEK',
    'INTEM', 'INVEO', 'INVES', 'ISBIR', 'ISBTR', 'ISDMR', 'ISFIN', 'ISGLK',
    'ISGSY', 'ISGYO', 'ISMEN', 'ISSEN', 'ISYAT', 'IZENR', 'IZFAS', 'IZINV',
    'JANTS', 'KAREL', 'KARSN', 'KARTN', 'KATMR', 'KBORU', 'KENT', 'KERVN',
    'KFEIN', 'KGYO', 'KIMMR', 'KLGYO', 'KLKIM', 'KLMSN', 'KLNMA', 'KLRHO',
    'KLSER', 'KLSYN', 'KNFRT', 'KONKA', 'KONTR', 'KONYA', 'KORDS', 'KOTON',
    'KRDMA', 'KRDMB', 'KRDMD', 'KRGYO', 'KRONT', 'KRSTL', 'KRTEK', 'KRVGD',
    'KSTUR', 'KTLEV', 'KTSKR', 'KUVVA', 'KUYAS', 'KZBGY', 'KZGYO', 'LIDER',
    'LIDFA', 'LILAK', 'LINK', 'LKMNH', 'LOGO', 'LRSHO', 'LUKSK', 'LYDHO',
    'MAALT', 'MAGEN', 'MAKIM', 'MAKTK', 'MANAS', 'MARBL', 'MARKA', 'MARMR',
    'MARTI', 'MAVI', 'MEDTR', 'MEGMT', 'MEKAG', 'MERIT', 'MERKO', 'METRO',
    'MGROS', 'MHRGY', 'MIATK', 'MNDRS', 'MNDTR', 'MOBTL', 'MOGAN', 'MRGYO',
    'MRSHL', 'MSGYO', 'MTRKS', 'MTRYO', 'MZHLD', 'NATEN', 'NETAS', 'NIBAS',
    'NTGAZ', 'NTHOL', 'NUGYO', 'OBAMS', 'ODAS', 'OFSYM', 'ONRYT', 'ORMA',
    'OSMEN', 'OSTIM', 'OTKAR', 'OTTO', 'OYAYO', 'OYLUM', 'OYYAT', 'OZATD',
    'OZGYO', 'OZKGY', 'OZRDN', 'OZSUB', 'OZYSR', 'QNBFK', 'QNBTR', 'QTEMZ',
    'QUAGR', 'RALYH', 'RAYSG', 'REEDR', 'RGYAS', 'RODRG', 'RTALB', 'RUBNS',
    'RYGYO', 'RYSAS', 'SAFKR', 'SAHOL', 'SAMAT', 'SANEL', 'SANFM', 'SANKO',
    'SARKY', 'SASA', 'SAYAS', 'SDTTR', 'SEGMN', 'SEGYO', 'SEKFK', 'SEKUR',
    'SELVA', 'SERNT', 'SEYKM', 'SILVR', 'SKBNK', 'SKTAS', 'SKYMD', 'SMART',
    'SMRTG', 'SMRVA', 'SNGYO', 'SNKRN', 'SODSN', 'SOKM', 'SRVGY', 'SUMAS',
    'SUNTK', 'SURGY', 'TABGD', 'TARKM', 'TATEN', 'TATGD', 'TAVHL', 'TBORG',
    'TDGYO', 'TEHOL', 'TEKTU', 'TERA', 'TEZOL', 'TGSAS', 'THYAO', 'TKFEN',
    'TKNSA', 'TLMAN', 'TMSN', 'TOASO', 'TRALT', 'TRENJ', 'TRGYO', 'TRHOL',
    'TRMET', 'TSGYO', 'TSKB', 'TTKOM', 'TTRAK', 'TUKAS', 'TUREX', 'TURGG',
    'TURSG', 'UFUK', 'ULAS', 'ULKER', 'ULUFA', 'ULUUN', 'UNLU', 'USAK',
    'USDTR', 'VAKBN', 'VAKFA', 'VAKFN', 'VAKKO', 'VANGD', 'VBTYZ', 'VERTU',
    'VERUS', 'VESTL', 'VKFYO', 'VKGYO', 'VKING', 'VRGYO', 'VSNMD', 'YATAS',
    'YAYLA', 'YBTAS', 'YEOTK', 'YESIL', 'YGGYO', 'YGYO', 'YIGIT', 'YKBNK',
    'YKSLN', 'YONGA', 'YUNSA', 'YYLGD', 'ZEDUR', 'ZGOLD', 'ZOREN', 'ZRE20',
    'ZRGYO', 'ZSR25',
]

# ================== VERI ÇERÇEVESİ AYARLARI ==================
# Kaç günlük geçmiş veri çekilecek
HISTORICAL_DAYS = 100

# OHLCV data timeframe
PRIMARY_TIMEFRAME = '1d'  # Günlük data
INTRADAY_TIMEFRAME = '15m'  # İntraday için
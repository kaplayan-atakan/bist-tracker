"""
BİST Trading Bot - Configuration Module
Tüm bot parametreleri burada merkezi olarak yönetilir
"""

# ================== GENEL AYARLAR ==================
# Tarama aralığı (saniye)
SCAN_INTERVAL_SECONDS = 300  # 5 dakika

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
MAX_SPREAD_PERCENT = 0.5

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
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8198117366:AAHzc6j-fbwpzqowRArUdO__g6aYOkfeZqk")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "8070220440")

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
DATA_PRIORITY_INTRADAY = ["tradingview_http", "yahoo"]  # Intraday için
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

# ================== KARA LİSTE ==================
# Tarama dışı bırakılacak semboller
BLACKLIST_SYMBOLS = [
    # Buraya aşırı volatil veya sorunlu hisseler eklenebilir
]

# ================== BİST SEMBOL LİSTESİ ==================
# Ana BİST hisseleri (yfinance için .IS uzantısı eklenir)
# Bu listeyi güncel BİST-100 sembolleriyle güncelleyebilirsiniz
BIST_SYMBOLS = [
    'THYAO', 'ASELS', 'KCHOL', 'EREGL', 'AKBNK', 'SISE', 'SAHOL', 'GARAN',
    'ISCTR', 'PETKM', 'TUPRS', 'HALKB', 'BIMAS', 'VAKBN', 'TAVHL', 'YKBNK',
    'TCELL', 'PGSUS', 'TOASO', 'TTKOM', 'KOZAL', 'KOZAA', 'ARCLK', 'EKGYO',
    'SODA', 'FROTO', 'AEFES', 'VESBE', 'ODAS', 'DOHOL', 'ENKAI', 'BRSAN',
    'MGROS', 'ULKER', 'BRISA', 'AYGAZ', 'OTKAR', 'NETAS', 'CCOLA', 'SOKM',
    'KRDMD', 'AKSA', 'LOGO', 'GESAN', 'ALARK', 'INDES', 'MAVI', 'KARSN',
    'TURSG', 'KONTR', 'KLMSN', 'EUPWR', 'HEKTS', 'ANACM', 'SISE', 'CIMSA'
]

# ================== VERI ÇERÇEVESİ AYARLARI ==================
# Kaç günlük geçmiş veri çekilecek
HISTORICAL_DAYS = 100

# OHLCV data timeframe
PRIMARY_TIMEFRAME = '1d'  # Günlük data
INTRADAY_TIMEFRAME = '15m'  # İntraday için
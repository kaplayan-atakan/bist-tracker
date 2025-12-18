import os
from dotenv import load_dotenv

# .env dosyasını yükle
load_dotenv()

# ==================== GENEL AYARLAR ====================
SCAN_INTERVAL_SECONDS = 120  # 2 dakikada bir tara
L2_SNAPSHOT_INTERVAL = 5  # Saniye (eğer L2 varsa)

# ==================== EVREN FILTRELERI ====================
MIN_DAILY_VOLUME_TL = 30_000_000  # 30M TL minimum günlük hacim
MIN_PRICE = 0.01  # Minimum hisse fiyatı
MAX_SPREAD_PERCENT = 5.0  # Maksimum spread %

# ==================== FEATURE PARAMETRELERI ====================
# Accumulation
ACC_LOOKBACK_BARS_5M = 60  # 5 saatlik 5dk bar
ACC_LOOKBACK_BARS_1M = 120  # 2 saatlik 1dk bar
PRICE_FLAT_THRESHOLD = 0.002  # ±0.2% fiyat yatay sayılır

# Volatility Compression
ATR_PERIOD = 14
BB_PERIOD = 20
BB_STD = 2
COMPRESSION_PERCENTILE = 25  # Alt %25'lik dilim

# Order Book Absorption
ABSORPTION_WINDOW_MINUTES = 10
ASK_REDUCTION_THRESHOLD = 0.30  # %30 azalma
PRICE_STABILITY_THRESHOLD = 0.003  # ±0.3%

# Flow Footprint
FLOW_WINDOW_MINUTES = 10
FLOW_SIGMA_THRESHOLD = 2.0  # Standart sapma eşiği

# Context
SOCIAL_SILENCE_THRESHOLD = 0.3  # Mention oranı (normal günlere göre)
KAP_LOOKBACK_DAYS = 7

# ==================== SKORLAMA SİSTEMİ ====================
# Maksimum puanlar
MAX_ACCUMULATION = 30
MAX_VOLATILITY = 20
MAX_ABSORPTION = 25
MAX_FLOW = 15
MAX_CONTEXT = 10
MAX_TOTAL = 100

# Eşikler
SCORE_THRESHOLD_VERY_HIGH = 75  # 🔥
SCORE_THRESHOLD_HIGH = 60       # 🟠
SCORE_THRESHOLD_MEDIUM = 45     # 🟡
# < 45 = 🟢 Düşük

# ==================== RİSK KORUMASI ====================
ILLIQUID_VOLUME_THRESHOLD = 10_000_000  # 10M TL altı çok düşük
ILLIQUID_SPREAD_THRESHOLD = 3.0  # %3 üstü spread riskli

# ==================== BAŞLAMA ALARMI ====================
START_VOLUME_MULTIPLIER = 3.0  # ADV'nin 3 katı
START_PRICE_CHANGE = 0.01  # %1 yukarı

# ==================== TELEGRAM ====================
TELEGRAM_ENABLED = True
TELEGRAM_BOT_TOKEN="7611453017:AAFAz9jBsUQ-N6RUdQ8pnct0gIzV2UeEmIM"
TELEGRAM_CHAT_ID="5883922751"

# ==================== VERİ KAYNAKLARI ====================
# Bu kısımlar gerçek API'lerinize göre güncellenmelidir
DATA_SOURCE = os.getenv("DATA_SOURCE", "mock")  # "mock", "api", "yfinance"
API_BASE_URL = "https://api.example.com"
API_KEY = "YOUR_API_KEY"

# ==================== LOGGING ====================
LOG_LEVEL = "INFO"
LOG_FILE = "pmr_bot.log"

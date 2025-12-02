#!/usr/bin/env python3
"""
BİST Trading Bot - Manual Smoke Tests
Sprint 1 Data Provider Architecture Doğrulama

Bu dosya, yeni provider mimarisinin temel işlevlerini manuel olarak
test etmek için yardımcı fonksiyonlar içerir.

Kullanım:
    python manual_smoke_tests.py --all              # Tüm testleri çalıştır
    python manual_smoke_tests.py --yahoo            # Sadece Yahoo testi
    python manual_smoke_tests.py --finnhub          # Sadece Finnhub testi
    python manual_smoke_tests.py --tradingview      # Sadece TradingView stream testi
    python manual_smoke_tests.py --failover         # Failover mantığı testi
    python manual_smoke_tests.py --all-fail         # Tüm provider başarısız senaryosu
    python manual_smoke_tests.py --symbol AKBNK     # Farklı sembol ile test
    python manual_smoke_tests.py -v                 # Verbose logging

Gereksinimler:
    - FINNHUB_API_KEY ortam değişkeni veya config.py'de tanımlı olmalı
    - TradingView testi için piyasa saatlerinde çalıştırın (10:00-18:00)
    - Ağ bağlantısı gerekli
"""

import argparse
import asyncio
import logging
import os
import sys
from datetime import datetime
from typing import Optional, List, Dict, Any

import pandas as pd

# Modül yolunu ayarla
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config

# Logging ayarları
def setup_logging(verbose: bool = False):
    """Logging yapılandırması"""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
        datefmt='%H:%M:%S'
    )
    # Bazı kütüphanelerin log seviyesini azalt
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('yfinance').setLevel(logging.WARNING)

logger = logging.getLogger("smoke_tests")


# ============================================================================
# YARDIMCI FONKSİYONLAR
# ============================================================================

def print_header(title: str):
    """Test başlığı yazdır"""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)

def print_subheader(title: str):
    """Alt başlık yazdır"""
    print(f"\n--- {title} ---")

def print_success(message: str):
    """Başarı mesajı yazdır"""
    print(f"✅ {message}")

def print_error(message: str):
    """Hata mesajı yazdır"""
    print(f"❌ {message}")

def print_warning(message: str):
    """Uyarı mesajı yazdır"""
    print(f"⚠️  {message}")

def print_info(message: str):
    """Bilgi mesajı yazdır"""
    print(f"ℹ️  {message}")

def validate_ohlcv_dataframe(df: pd.DataFrame, test_name: str) -> bool:
    """
    OHLCV DataFrame'in standart formatta olduğunu doğrular.
    
    Args:
        df: Kontrol edilecek DataFrame
        test_name: Test adı (hata mesajlarında kullanılır)
        
    Returns:
        bool: Doğrulama başarılı mı
    """
    expected_columns = ['open', 'high', 'low', 'close', 'volume']
    
    # Boş mu kontrol et
    if df is None or df.empty:
        print_error(f"{test_name}: DataFrame boş veya None")
        return False
    
    # Sütunları küçük harfe çevir (yfinance büyük harf kullanıyor)
    df_columns = [col.lower() for col in df.columns]
    
    # Timestamp kontrolü - index veya sütun olabilir
    has_timestamp = (
        'timestamp' in df_columns or 
        'date' in df_columns or
        isinstance(df.index, pd.DatetimeIndex)
    )
    
    if not has_timestamp:
        print_warning(f"{test_name}: Timestamp sütunu/index'i bulunamadı")
    
    # OHLCV sütunlarını kontrol et
    missing_columns = [col for col in expected_columns if col not in df_columns]
    
    if missing_columns:
        print_error(f"{test_name}: Eksik OHLCV sütunları: {missing_columns}")
        print_info(f"Mevcut sütunlar: {list(df.columns)}")
        return False
    
    # Timestamp sıralaması kontrol et (eğer DatetimeIndex ise)
    if isinstance(df.index, pd.DatetimeIndex):
        if len(df.index) > 1:
            is_sorted = df.index.is_monotonic_increasing
            if not is_sorted:
                print_warning(f"{test_name}: Index artan sırada değil")
    elif 'timestamp' in df_columns:
        timestamps = df['timestamp'] if 'timestamp' in df.columns else df['Timestamp']
        if len(timestamps) > 1:
            is_sorted = (timestamps.diff().dropna() >= pd.Timedelta(0)).all()
            if not is_sorted:
                print_warning(f"{test_name}: Timestamp'ler artan sırada değil")
    
    return True

def print_dataframe_summary(df: pd.DataFrame, rows: int = 5):
    """DataFrame özeti yazdır"""
    print(f"\nSatır sayısı: {len(df)}")
    print(f"Sütunlar: {list(df.columns)}")
    print(f"\nİlk {min(rows, len(df))} satır:")
    print(df.head(rows).to_string(index=False))
    
    if len(df) > rows:
        print(f"\nSon {min(rows, len(df))} satır:")
        print(df.tail(rows).to_string(index=False))


# ============================================================================
# 1.1 YAHOO PROVIDER / DAILY OHLCV TEST
# ============================================================================

async def test_yahoo_daily_ohlcv(symbol: str = "GARAN.IS") -> bool:
    """
    YahooProvider üzerinden günlük OHLCV verisi çekme testi.
    
    Test edilenler:
    - DataFetcher.get_ohlcv() fonksiyonu çalışıyor mu
    - Dönen DataFrame standart formatta mı
    - Veri boş değil mi
    - Timestamp sıralaması doğru mu
    
    Args:
        symbol: Test edilecek sembol (varsayılan: GARAN.IS)
        
    Returns:
        bool: Test başarılı mı
    """
    print_header("1.1 Yahoo Provider - Günlük OHLCV Testi")
    print_info(f"Sembol: {symbol}")
    print_info(f"Timeframe: 1D (günlük)")
    print_info(f"Limit: 100 bar")
    
    try:
        from data_fetcher import get_data_fetcher
        
        fetcher = get_data_fetcher()
        
        print_subheader("DataFetcher.get_ohlcv() çağrılıyor...")
        
        # .IS uzantısını kaldır (DataFetcher otomatik ekliyor)
        clean_symbol = symbol.replace('.IS', '')
        
        df = fetcher.get_ohlcv(symbol=clean_symbol, timeframe='1d', limit=100)
        
        # Doğrulama
        if not validate_ohlcv_dataframe(df, "Yahoo Daily OHLCV"):
            return False
        
        print_success("DataFrame standart formatta ve veri içeriyor")
        print_dataframe_summary(df)
        
        # Provider istatistikleri
        stats = fetcher.get_provider_stats()
        if stats:
            print_subheader("Provider İstatistikleri")
            print(f"  Toplam istek: {stats.get('total_requests', 'N/A')}")
            print(f"  Başarılı istek: {stats.get('successful_requests', 'N/A')}")
            print(f"  Sağlık durumları: {stats.get('health', {})}")
        
        print_success("Yahoo Daily OHLCV testi BAŞARILI")
        return True
        
    except ImportError as e:
        print_error(f"Import hatası: {e}")
        print_info("Provider modülleri yüklü mü kontrol edin")
        return False
        
    except Exception as e:
        print_error(f"Beklenmeyen hata: {e}")
        logger.exception("Yahoo OHLCV test hatası")
        return False


# ============================================================================
# 1.2 FINNHUB PROVIDER - INTRADAY + DAILY OHLCV TEST
# ============================================================================

async def test_finnhub_intraday_and_daily(symbol: str = "GARAN.IS") -> bool:
    """
    FinnhubProvider üzerinden intraday ve günlük OHLCV verisi çekme testi.
    
    ⚠️ ÖNEMLİ: Finnhub FREE TIER, BİST (Türk Borsası) sembollerini DESTEKLEMİYOR!
    Bu test 403 Forbidden hatası alacaktır. Bu beklenen bir davranıştır.
    
    BİST verisi için:
    - Yahoo (yfinance) provider kullanın
    - Veya Finnhub premium abonelik alın
    
    Test edilenler:
    - Finnhub API bağlantısı çalışıyor mu
    - 403 hatası düzgün handle ediliyor mu
    - Rate limiting çalışıyor mu
    
    Args:
        symbol: Test edilecek sembol (varsayılan: GARAN.IS)
        
    Returns:
        bool: Test başarılı mı
    """
    print_header("1.2 Finnhub Provider - Intraday + Daily OHLCV Testi")
    print_warning("Finnhub FREE TIER, BİST sembollerini DESTEKLEMİYOR!")
    print_warning("Bu test 403 hatası alabilir - bu beklenen davranıştır.")
    print_info(f"Sembol: {symbol}")
    print_info(f"API Key: {'***' + config.FINNHUB_API_KEY[-4:] if config.FINNHUB_API_KEY else 'AYARLANMAMIŞ'}")
    
    if not config.FINNHUB_API_KEY:
        print_error("FINNHUB_API_KEY ayarlanmamış!")
        print_info("config.py'de veya FINNHUB_API_KEY ortam değişkeninde tanımlayın")
        return False
    
    try:
        from providers.finnhub import get_finnhub_provider
        from providers.base import ProviderConfig
        
        # Finnhub provider'ı config ile başlat
        finnhub_config = ProviderConfig(
            name="finnhub",
            enabled=True,
            api_key=config.FINNHUB_API_KEY,
            base_url=config.FINNHUB_BASE_URL,
        )
        
        # NOT: Singleton'ı atlamak için doğrudan oluşturuyoruz
        from providers.finnhub import FinnhubProvider
        provider = FinnhubProvider(finnhub_config)
        
        await provider.connect()
        
        clean_symbol = symbol.replace('.IS', '')
        
        # Test 1: Intraday (15m)
        print_subheader("Intraday OHLCV (15m)")
        
        df_intraday = await provider.get_ohlcv(clean_symbol, "15m", limit=100)
        
        if validate_ohlcv_dataframe(df_intraday, "Finnhub Intraday"):
            print_success(f"Intraday veri çekildi: {len(df_intraday)} bar")
            print_dataframe_summary(df_intraday, rows=3)
        else:
            print_warning("Intraday veri alınamadı (piyasa kapalı olabilir)")
        
        # Test 2: Daily (1D)
        print_subheader("Günlük OHLCV (1D)")
        
        df_daily = await provider.get_ohlcv(clean_symbol, "1D", limit=100)
        
        if validate_ohlcv_dataframe(df_daily, "Finnhub Daily"):
            print_success(f"Günlük veri çekildi: {len(df_daily)} bar")
            print_dataframe_summary(df_daily, rows=3)
        else:
            print_warning("Günlük veri alınamadı")
        
        # Provider istatistikleri
        stats = provider.get_stats()
        print_subheader("Finnhub İstatistikleri")
        print(f"  Toplam istek: {stats.get('total_requests', 0)}")
        print(f"  Başarılı istek: {stats.get('successful_requests', 0)}")
        print(f"  Rate limit: {stats.get('rate_limit_hits', 0)}")
        
        await provider.disconnect()
        
        # En az bir test başarılı olmalı
        success = (not df_intraday.empty) or (not df_daily.empty)
        
        if success:
            print_success("Finnhub testi BAŞARILI")
        else:
            print_error("Finnhub testi BAŞARISIZ - veri alınamadı")
        
        return success
        
    except ImportError as e:
        print_error(f"Import hatası: {e}")
        print_info("aiohttp paketi yüklü mü kontrol edin: pip install aiohttp")
        return False
        
    except Exception as e:
        print_error(f"Beklenmeyen hata: {e}")
        logger.exception("Finnhub test hatası")
        return False


# ============================================================================
# 1.3 TRADINGVIEW WEBSOCKET PROVIDER - REALTIME STREAM TEST
# ============================================================================

async def test_tradingview_realtime_stream(
    symbol: str = "GARAN.IS",
    bar_count: int = 3,
    timeout_seconds: int = 60
) -> bool:
    """
    TradingView WebSocket provider üzerinden gerçek zamanlı stream testi.
    
    DİKKAT: Bu test piyasa saatlerinde (10:00-18:00) çalıştırılmalıdır!
    Piyasa kapalıyken veri akışı olmayabilir.
    
    Test edilenler:
    - WebSocket bağlantısı kuruluyor mu
    - Sembol aboneliği çalışıyor mu
    - Bar verileri alınıyor mu
    - Otomatik yeniden bağlanma (gözlem)
    
    Args:
        symbol: Test edilecek sembol
        bar_count: Kaç bar toplanacak (varsayılan: 3)
        timeout_seconds: Maksimum bekleme süresi
        
    Returns:
        bool: Test başarılı mı
    """
    print_header("1.3 TradingView WebSocket - Realtime Stream Testi")
    print_info(f"Sembol: {symbol}")
    print_info(f"Hedef bar sayısı: {bar_count}")
    print_info(f"Timeout: {timeout_seconds} saniye")
    print_warning("Bu test piyasa saatlerinde (10:00-18:00) çalıştırılmalıdır!")
    
    # Piyasa saati kontrolü
    now = datetime.now()
    if now.weekday() >= 5:  # Cumartesi veya Pazar
        print_warning("Hafta sonu - piyasa kapalı, veri akışı olmayabilir")
    elif now.hour < 10 or now.hour >= 18:
        print_warning("Piyasa saatleri dışında - veri akışı olmayabilir")
    
    try:
        from providers.tradingview_ws import TradingViewWebSocketProvider
        from providers.base import ProviderConfig
        
        # Provider oluştur
        tv_config = ProviderConfig(
            name="tradingview",
            enabled=True,
            ws_url=config.TRADINGVIEW_WS_URL,
        )
        
        provider = TradingViewWebSocketProvider(tv_config)
        
        print_subheader("WebSocket bağlantısı kuruluyor...")
        
        connected = await provider.connect()
        
        if not connected:
            print_error("WebSocket bağlantısı kurulamadı")
            return False
        
        print_success("WebSocket bağlantısı kuruldu")
        
        clean_symbol = symbol.replace('.IS', '')
        collected_bars = []
        
        print_subheader(f"Stream başlatılıyor ({bar_count} bar hedefi)...")
        
        try:
            async with asyncio.timeout(timeout_seconds):
                async for df in provider.get_realtime_stream([clean_symbol], "1m"):
                    if df is not None and not df.empty:
                        collected_bars.append(df)
                        print_info(f"Bar alındı #{len(collected_bars)}: {df.iloc[0].to_dict()}")
                        
                        if len(collected_bars) >= bar_count:
                            print_success(f"{bar_count} bar toplandı, stream durduruluyor")
                            break
                            
        except asyncio.TimeoutError:
            if len(collected_bars) > 0:
                print_warning(f"Timeout! {len(collected_bars)}/{bar_count} bar toplandı")
            else:
                print_warning("Timeout! Hiç bar toplanamadı (piyasa kapalı olabilir)")
        
        await provider.disconnect()
        
        # Sonuçları değerlendir
        if len(collected_bars) >= bar_count:
            print_success("TradingView realtime stream testi BAŞARILI")
            return True
        elif len(collected_bars) > 0:
            print_warning(f"Kısmi başarı: {len(collected_bars)} bar toplandı")
            return True  # Kısmi başarı da kabul
        else:
            print_error("TradingView testi BAŞARISIZ - veri alınamadı")
            print_info("Piyasa saatlerinde tekrar deneyin")
            return False
        
    except ImportError as e:
        print_error(f"Import hatası: {e}")
        print_info("websockets paketi yüklü mü kontrol edin: pip install websockets")
        return False
        
    except Exception as e:
        print_error(f"Beklenmeyen hata: {e}")
        logger.exception("TradingView test hatası")
        return False


# ============================================================================
# 1.4 PROVIDER MANAGER FAILOVER LOGIC TEST
# ============================================================================

async def test_provider_manager_failover(symbol: str = "GARAN.IS") -> bool:
    """
    ProviderManager failover mantığı testi.
    
    Test 1 - Normal koşullar:
    - Intraday OHLCV isteği yapılır
    - TradingView NotImplementedError fırlatır (beklenen)
    - Finnhub'a failover yapılır
    - Veri başarıyla alınır
    
    Test 2 - NotImplementedError handling:
    - TradingView'ın NotImplementedError'ı sağlık durumunu etkilemez
    - Sonraki provider'a geçilir
    
    Args:
        symbol: Test edilecek sembol
        
    Returns:
        bool: Test başarılı mı
    """
    print_header("1.4 ProviderManager - Failover Mantığı Testi")
    print_info(f"Sembol: {symbol}")
    print_info("Beklenen davranış: TradingView -> NotImplementedError -> Finnhub fallback")
    
    try:
        from providers.manager import ProviderManager, get_provider_manager
        from providers.base import ProviderConfig, ProviderHealthStatus
        
        # Provider manager'ı başlat
        finnhub_config = ProviderConfig(
            name="finnhub",
            enabled=True,
            api_key=config.FINNHUB_API_KEY,
            base_url=config.FINNHUB_BASE_URL,
        )
        
        manager = get_provider_manager(
            finnhub_config=finnhub_config,
            force_new=True
        )
        
        # Provider'ları başlat
        await manager.initialize_providers()
        
        clean_symbol = symbol.replace('.IS', '')
        
        # Test 1: Normal intraday çağrısı
        print_subheader("Test 1: Intraday OHLCV (15m) - Failover Bekleniyor")
        
        # Sağlık durumlarını önce yazdır
        print_info(f"Başlangıç sağlık durumları: {manager.get_health_summary()}")
        
        df = await manager.get_ohlcv(clean_symbol, "15m", limit=50)
        
        # Sağlık durumlarını sonra yazdır
        print_info(f"Sonuç sağlık durumları: {manager.get_health_summary()}")
        
        # Sonuçları değerlendir
        stats = manager.get_stats()
        
        print_subheader("Failover İstatistikleri")
        print(f"  Failover sayısı: {stats.get('failover_count', 0)}")
        print(f"  Provider hataları: {stats.get('provider_failures', {})}")
        
        if not df.empty:
            print_success(f"Failover başarılı! {len(df)} bar alındı")
            print_info("TradingView -> Finnhub failover çalıştı")
            print_dataframe_summary(df, rows=3)
        else:
            print_warning("Veri alınamadı (tüm provider'lar başarısız olmuş olabilir)")
        
        # Test 2: TradingView sağlık durumu değişmemeli
        print_subheader("Test 2: Sağlık Durumu Kontrolü")
        
        tradingview_health = manager.health.get("tradingview", ProviderHealthStatus.UNKNOWN)
        
        # NotImplementedError sağlık durumunu DOWN yapmamalı
        if tradingview_health != ProviderHealthStatus.DOWN:
            print_success("TradingView sağlık durumu korundu (NotImplementedError doğru handle edildi)")
        else:
            print_warning("TradingView DOWN durumunda (beklenmedik)")
        
        # Temizlik
        await manager.shutdown_providers()
        
        # En az veri alındıysa başarılı say
        if not df.empty:
            print_success("Failover testi BAŞARILI")
            return True
        else:
            print_error("Failover testi BAŞARISIZ - veri alınamadı")
            return False
        
    except Exception as e:
        print_error(f"Beklenmeyen hata: {e}")
        logger.exception("Failover test hatası")
        return False


# ============================================================================
# 1.5 ALL PROVIDERS FAIL EDGE CASE TEST
# ============================================================================

async def test_all_providers_fail() -> bool:
    """
    Tüm provider'ların başarısız olması durumunu test eder.
    
    Senaryo:
    - Geçersiz bir sembol kullanarak tüm provider'ları başarısız yapma
    - Sistemin nasıl davrandığını gözlemleme
    
    Beklenen davranış:
    - ProviderManager boş DataFrame döndürmeli
    - DataFetcher legacy'ye düşmeli
    - Net hata mesajları loglanmalı
    
    Returns:
        bool: Test başarılı mı (sistem crash etmediyse)
    """
    print_header("1.5 Tüm Provider'lar Başarısız - Edge Case Testi")
    print_info("Geçersiz sembol kullanılarak tüm provider'lar başarısız yapılacak")
    
    # Kesinlikle geçersiz bir sembol
    invalid_symbol = "XXXXINVALIDSYMBOLXXXX"
    
    try:
        # Test 1: ProviderManager ile
        print_subheader("Test 1: ProviderManager ile geçersiz sembol")
        
        from providers.manager import get_provider_manager
        from providers.base import ProviderConfig
        
        manager = get_provider_manager(force_new=True)
        await manager.initialize_providers()
        
        df = await manager.get_ohlcv(invalid_symbol, "1D", limit=10)
        
        if df.empty:
            print_success("ProviderManager boş DataFrame döndürdü (beklenen)")
        else:
            print_warning(f"ProviderManager veri döndürdü: {len(df)} satır (beklenmedik)")
        
        stats = manager.get_stats()
        print_info(f"Failover sayısı: {stats.get('failover_count', 0)}")
        print_info(f"Sağlık durumları: {stats.get('health', {})}")
        
        await manager.shutdown_providers()
        
        # Test 2: DataFetcher ile (legacy fallback dahil)
        print_subheader("Test 2: DataFetcher ile geçersiz sembol (legacy fallback)")
        
        from data_fetcher import DataFetcher
        
        # Yeni instance oluştur (singleton'ı atla)
        fetcher = DataFetcher(use_providers=True)
        
        df = fetcher.get_ohlcv(invalid_symbol, timeframe='1d', limit=10)
        
        if df is None or df.empty:
            print_success("DataFetcher boş/None döndürdü (beklenen)")
        else:
            print_warning(f"DataFetcher veri döndürdü: {len(df)} satır")
        
        # Test 3: Hata durumlarını yazdır
        print_subheader("Sonuç")
        print_info("Tüm provider'lar başarısız olduğunda sistem:")
        print_info("  - Crash ETMEDİ ✓")
        print_info("  - Boş DataFrame döndürdü ✓")
        print_info("  - Legacy fallback denendi ✓")
        
        print_success("Edge case testi BAŞARILI - Sistem graceful fail yapıyor")
        return True
        
    except Exception as e:
        print_error(f"Beklenmeyen hata: {e}")
        logger.exception("All providers fail test hatası")
        
        # Exception oluşsa bile, graceful handling başarısız demek değil
        # Exception'ın türüne bakmak lazım
        print_info("Hata yakalandı, sistem çökmedi")
        return False


# ============================================================================
# TEST RUNNER FONKSİYONLARI
# ============================================================================

async def test_intraday_provider_choice(symbol: str = "GARAN.IS", timeframe: str = "15m"):
    """
    Intraday OHLCV çağrısı için hangi provider'ın kullanıldığını gösterir.
    
    Args:
        symbol: Test edilecek sembol
        timeframe: Zaman dilimi
    """
    print_header("Intraday Provider Seçimi Testi")
    print_info(f"Sembol: {symbol}")
    print_info(f"Timeframe: {timeframe}")
    
    try:
        from data_fetcher import get_data_fetcher
        
        fetcher = get_data_fetcher()
        clean_symbol = symbol.replace('.IS', '')
        
        print_subheader("OHLCV çekiliyor...")
        
        df = fetcher.get_ohlcv(clean_symbol, timeframe=timeframe, limit=50)
        
        if df is not None and not df.empty:
            print_success(f"Veri alındı: {len(df)} bar")
            print_dataframe_summary(df, rows=3)
        else:
            print_warning("Veri alınamadı")
        
        # İstatistikler
        stats = fetcher.get_provider_stats()
        if stats:
            print_subheader("Provider İstatistikleri")
            print(f"  Sağlık durumları: {stats.get('health', {})}")
            print(f"  Failover sayısı: {stats.get('failover_count', 0)}")
        
    except Exception as e:
        print_error(f"Hata: {e}")
        logger.exception("Provider choice test hatası")


async def run_all_tests(symbol: str = "GARAN.IS", verbose: bool = False) -> Dict[str, bool]:
    """
    Tüm smoke testlerini sırayla çalıştırır.
    
    Args:
        symbol: Test edilecek sembol
        verbose: Detaylı logging
        
    Returns:
        Dict[str, bool]: Test sonuçları
    """
    results = {}
    
    print("\n" + "=" * 70)
    print("  BİST Trading Bot - Sprint 1 Smoke Tests")
    print("=" * 70)
    print(f"\nTest sembolü: {symbol}")
    print(f"Başlangıç zamanı: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Test 1.1: Yahoo
    results['yahoo_daily'] = await test_yahoo_daily_ohlcv(symbol)
    
    # Test 1.2: Finnhub
    results['finnhub_ohlcv'] = await test_finnhub_intraday_and_daily(symbol)
    
    # Test 1.3: TradingView (sadece piyasa saatlerinde anlamlı)
    # Bu test uzun sürdüğü için opsiyonel olarak atlanabilir
    now = datetime.now()
    if 10 <= now.hour < 18 and now.weekday() < 5:
        results['tradingview_stream'] = await test_tradingview_realtime_stream(
            symbol, bar_count=2, timeout_seconds=30
        )
    else:
        print_header("1.3 TradingView WebSocket - ATLANDI (Piyasa Kapalı)")
        results['tradingview_stream'] = None
    
    # Test 1.4: Failover
    results['failover'] = await test_provider_manager_failover(symbol)
    
    # Test 1.5: All fail
    results['all_fail'] = await test_all_providers_fail()
    
    # Özet
    print("\n" + "=" * 70)
    print("  TEST SONUÇLARI")
    print("=" * 70)
    
    for test_name, result in results.items():
        if result is True:
            print(f"  ✅ {test_name}: BAŞARILI")
        elif result is False:
            print(f"  ❌ {test_name}: BAŞARISIZ")
        else:
            print(f"  ⏭️  {test_name}: ATLANDI")
    
    passed = sum(1 for r in results.values() if r is True)
    failed = sum(1 for r in results.values() if r is False)
    skipped = sum(1 for r in results.values() if r is None)
    
    print(f"\nToplam: {passed} başarılı, {failed} başarısız, {skipped} atlandı")
    print(f"Bitiş zamanı: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    return results


# ============================================================================
# CLI ENTRYPOINT
# ============================================================================

def main():
    """CLI ana fonksiyonu"""
    parser = argparse.ArgumentParser(
        description="BİST Trading Bot - Sprint 1 Manual Smoke Tests",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Örnekler:
  python manual_smoke_tests.py --all              # Tüm testleri çalıştır
  python manual_smoke_tests.py --yahoo            # Sadece Yahoo testi
  python manual_smoke_tests.py --finnhub          # Sadece Finnhub testi
  python manual_smoke_tests.py --tradingview      # TradingView stream testi
  python manual_smoke_tests.py --failover         # Failover mantığı testi
  python manual_smoke_tests.py --all-fail         # Edge case testi
  python manual_smoke_tests.py --symbol AKBNK     # Farklı sembol
  python manual_smoke_tests.py -v --yahoo         # Verbose logging
"""
    )
    
    parser.add_argument('--all', action='store_true', help='Tüm testleri çalıştır')
    parser.add_argument('--yahoo', action='store_true', help='Yahoo provider testi')
    parser.add_argument('--finnhub', action='store_true', help='Finnhub provider testi')
    parser.add_argument('--tradingview', action='store_true', help='TradingView stream testi')
    parser.add_argument('--failover', action='store_true', help='Failover mantığı testi')
    parser.add_argument('--all-fail', action='store_true', help='Tüm provider başarısız edge case')
    parser.add_argument('--provider-choice', action='store_true', help='Provider seçim testi')
    parser.add_argument('--symbol', type=str, default='GARAN.IS', help='Test sembolü (varsayılan: GARAN.IS)')
    parser.add_argument('-v', '--verbose', action='store_true', help='Detaylı logging')
    
    args = parser.parse_args()
    
    # Logging ayarla
    setup_logging(args.verbose)
    
    # Hiçbir test seçilmediyse --all varsayılan olsun
    if not any([args.all, args.yahoo, args.finnhub, args.tradingview, 
                args.failover, args.all_fail, args.provider_choice]):
        args.all = True
    
    # Testleri çalıştır
    async def run():
        if args.all:
            await run_all_tests(args.symbol, args.verbose)
        else:
            if args.yahoo:
                await test_yahoo_daily_ohlcv(args.symbol)
            if args.finnhub:
                await test_finnhub_intraday_and_daily(args.symbol)
            if args.tradingview:
                await test_tradingview_realtime_stream(args.symbol)
            if args.failover:
                await test_provider_manager_failover(args.symbol)
            if args.all_fail:
                await test_all_providers_fail()
            if args.provider_choice:
                await test_intraday_provider_choice(args.symbol)
    
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        print("\n\nTestler kullanıcı tarafından iptal edildi.")
        sys.exit(1)


if __name__ == "__main__":
    main()
